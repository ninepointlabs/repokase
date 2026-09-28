"""GitHub OAuth device flow (RFC 8628). Public client: no secret, ever.

Works for both OAuth Apps (scopes honoured, non-expiring tokens) and GitHub
Apps (scopes ignored, 8h tokens plus a refresh token).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass

import httpx

DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
# GitHub measures the interval strictly and answers slow_down (+5s) to polls
# that arrive exactly on time; a small margin avoids that penalty.
POLL_MARGIN = 1

# Module-level so tests can patch it; resolved at call time.
_sleep = asyncio.sleep

log = logging.getLogger(__name__)


class DeviceFlowError(Exception):
    """A terminal device-flow failure. `code` is GitHub's error code or ours."""

    MESSAGES = {
        "access_denied": "Authorization was cancelled on GitHub.",
        "expired_token": "The code expired before it was entered. Start again for a new code.",
        "device_flow_disabled": "Device flow is not enabled for this GitHub app.",
        "incorrect_client_credentials": "GitHub does not recognise this app's client ID.",
        "unsupported_grant_type": "GitHub rejected the sign-in request.",
        "incorrect_device_code": "GitHub rejected the device code. Start again.",
        "bad_refresh_token": "Your session could not be renewed. Please sign in again.",
        "network": "Could not reach GitHub. Check your connection and try again.",
    }

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(self.MESSAGES.get(code, detail or f"GitHub sign-in failed ({code})."))


@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass
class TokenSet:
    access_token: str
    scope: str = ""
    token_type: str = "bearer"
    # Present only for expiring (GitHub App) tokens. Unix timestamps.
    refresh_token: str | None = None
    expires_at: float | None = None
    refresh_expires_at: float | None = None

    @property
    def scopes(self) -> set[str]:
        return {s.strip() for s in self.scope.replace(",", " ").split() if s.strip()}

    def needs_refresh(self, now: float | None = None, margin: float = 120) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) >= self.expires_at - margin

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TokenSet:
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})

    @classmethod
    def from_response(cls, data: dict, now: float | None = None) -> TokenSet:
        now = now or time.time()
        expires_in = data.get("expires_in")
        refresh_in = data.get("refresh_token_expires_in")
        return cls(
            access_token=data["access_token"],
            scope=data.get("scope", ""),
            token_type=data.get("token_type", "bearer"),
            refresh_token=data.get("refresh_token"),
            expires_at=now + int(expires_in) if expires_in else None,
            refresh_expires_at=now + int(refresh_in) if refresh_in else None,
        )


async def _post(client: httpx.AsyncClient, url: str, data: dict) -> dict:
    try:
        resp = await client.post(url, data=data, headers={"Accept": "application/json"})
    except httpx.TransportError as exc:
        raise DeviceFlowError("network", str(exc)) from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 500:
        raise DeviceFlowError("network", f"HTTP {resp.status_code}")
    if not isinstance(body, dict):
        raise DeviceFlowError("unexpected_response")
    if resp.status_code >= 400 and "error" not in body:
        body["error"] = f"http_{resp.status_code}"
    return body


async def request_code(
    client: httpx.AsyncClient, client_id: str, scopes: Iterable[str]
) -> DeviceCode:
    body = await _post(client, DEVICE_CODE_URL, {"client_id": client_id, "scope": " ".join(scopes)})
    if "error" in body:
        raise DeviceFlowError(body["error"], body.get("error_description"))
    try:
        return DeviceCode(
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            expires_in=int(body["expires_in"]),
            interval=int(body.get("interval", 5)),
        )
    except (KeyError, ValueError) as exc:
        raise DeviceFlowError("unexpected_response", str(exc)) from exc


async def poll_for_token(
    client: httpx.AsyncClient,
    client_id: str,
    code: DeviceCode,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> TokenSet:
    """Poll until the user authorizes, honouring interval and slow_down."""
    sleep = sleep or _sleep
    interval = max(1, code.interval)
    deadline = clock() + code.expires_in
    while True:
        await sleep(interval + POLL_MARGIN)
        if clock() >= deadline:
            raise DeviceFlowError("expired_token")
        body = await _post(
            client,
            TOKEN_URL,
            {"client_id": client_id, "device_code": code.device_code, "grant_type": DEVICE_GRANT},
        )
        error = body.get("error")
        # Never log the body: it may contain the token.
        log.debug("device poll: %s (interval %ss)", error or "token received", interval)
        if error is None and "access_token" in body:
            return TokenSet.from_response(body)
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            # GitHub returns the new minimum interval; RFC 8628 says add 5s otherwise.
            interval = int(body.get("interval", interval + 5))
            continue
        raise DeviceFlowError(error or "unexpected_response", body.get("error_description"))


async def refresh_token(client: httpx.AsyncClient, client_id: str, refresh: str) -> TokenSet:
    """Exchange a refresh token. Device-flow tokens need no client secret."""
    body = await _post(
        client,
        TOKEN_URL,
        {"client_id": client_id, "grant_type": "refresh_token", "refresh_token": refresh},
    )
    if "error" in body or "access_token" not in body:
        raise DeviceFlowError(body.get("error", "bad_refresh_token"), body.get("error_description"))
    return TokenSet.from_response(body)
