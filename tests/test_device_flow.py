import httpx
import pytest
import respx

from repokase.auth import device_flow
from repokase.auth.device_flow import (
    DEVICE_CODE_URL,
    TOKEN_URL,
    DeviceCode,
    DeviceFlowError,
    TokenSet,
)

CODE = DeviceCode("dev123", "ABCD-1234", "https://github.com/login/device", 900, 5)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
async def http():
    async with httpx.AsyncClient() as client:
        yield client


@respx.mock
async def test_request_code_sends_client_id_and_scopes_without_secret(http):
    route = respx.post(DEVICE_CODE_URL).respond(
        json={
            "device_code": "dev123",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
    )
    code = await device_flow.request_code(http, "Ov23test", ["read:user", "repo", "workflow"])
    assert code == CODE
    body = route.calls.last.request.content.decode()
    assert "client_id=Ov23test" in body
    assert "scope=read%3Auser+repo+workflow" in body
    assert "secret" not in body
    assert route.calls.last.request.headers["accept"] == "application/json"


@respx.mock
async def test_request_code_error(http):
    respx.post(DEVICE_CODE_URL).respond(json={"error": "device_flow_disabled"})
    with pytest.raises(DeviceFlowError) as exc:
        await device_flow.request_code(http, "x", [])
    assert exc.value.code == "device_flow_disabled"


@respx.mock
async def test_poll_pending_then_success(http):
    clock = FakeClock()
    respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"error": "authorization_pending"}),
            httpx.Response(200, json={"error": "authorization_pending"}),
            httpx.Response(200, json={"access_token": "gho_x", "scope": "repo,read:user,workflow", "token_type": "bearer"}),
        ]
    )
    token = await device_flow.poll_for_token(http, "x", CODE, sleep=clock.sleep, clock=clock.clock)
    assert token.access_token == "gho_x"
    assert token.scopes == {"repo", "read:user", "workflow"}
    assert token.expires_at is None and not token.needs_refresh()
    assert clock.sleeps == [6, 6, 6]


@respx.mock
async def test_poll_slow_down_uses_returned_interval(http):
    clock = FakeClock()
    respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"error": "slow_down", "interval": 10}),
            httpx.Response(200, json={"error": "slow_down"}),
            httpx.Response(200, json={"access_token": "gho_x"}),
        ]
    )
    await device_flow.poll_for_token(http, "x", CODE, sleep=clock.sleep, clock=clock.clock)
    assert clock.sleeps == [6, 11, 16]


@pytest.mark.parametrize("error", ["access_denied", "expired_token", "incorrect_device_code"])
@respx.mock
async def test_poll_terminal_errors(http, error):
    clock = FakeClock()
    respx.post(TOKEN_URL).respond(json={"error": error})
    with pytest.raises(DeviceFlowError) as exc:
        await device_flow.poll_for_token(http, "x", CODE, sleep=clock.sleep, clock=clock.clock)
    assert exc.value.code == error
    assert str(exc.value)  # user-facing message


@respx.mock
async def test_poll_stops_at_local_expiry(http):
    clock = FakeClock()
    respx.post(TOKEN_URL).respond(json={"error": "authorization_pending"})
    short = DeviceCode("d", "u", "https://github.com/login/device", 14, 5)
    with pytest.raises(DeviceFlowError) as exc:
        await device_flow.poll_for_token(http, "x", short, sleep=clock.sleep, clock=clock.clock)
    assert exc.value.code == "expired_token"


@respx.mock
async def test_network_error_is_mapped(http):
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("boom"))
    clock = FakeClock()
    with pytest.raises(DeviceFlowError) as exc:
        await device_flow.poll_for_token(http, "x", CODE, sleep=clock.sleep, clock=clock.clock)
    assert exc.value.code == "network"


@respx.mock
async def test_expiring_token_and_refresh(http):
    respx.post(TOKEN_URL).respond(
        json={
            "access_token": "ghu_new",
            "expires_in": 28800,
            "refresh_token": "ghr_new",
            "refresh_token_expires_in": 15897600,
        }
    )
    token = await device_flow.refresh_token(http, "x", "ghr_old")
    assert token.access_token == "ghu_new"
    assert token.refresh_token == "ghr_new"
    assert token.expires_at and not token.needs_refresh()
    assert token.needs_refresh(now=token.expires_at - 60)
    body = respx.calls.last.request.content.decode()
    assert "grant_type=refresh_token" in body and "secret" not in body


def test_tokenset_roundtrip():
    t = TokenSet("a", scope="repo", refresh_token="r", expires_at=1.0)
    assert TokenSet.from_dict(t.to_dict() | {"unknown": 1}) == t
