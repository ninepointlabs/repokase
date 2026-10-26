"""What the sign-in screen and About say about where the token is kept."""

import httpx
import pytest
from PySide6.QtCore import QCoreApplication

from repokase.auth.device_flow import DeviceCode, TokenSet
from repokase.auth.token_store import MemoryTokenStore, TokenStoreError
from repokase.controllers import auth_controller
from repokase.controllers.auth_controller import AuthController

from test_cache import VIEWER

NO_KEYRING = "No Secret Service is available."


class NoKeyring:
    def load(self):
        raise TokenStoreError(NO_KEYRING)

    def save(self, token):
        raise TokenStoreError(NO_KEYRING)

    def clear(self):
        raise TokenStoreError(NO_KEYRING)


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def signed_in_flow(monkeypatch):
    """Device flow and viewer lookup that succeed without the network."""
    async def request_code(http, client_id, scopes):
        return DeviceCode("dev", "ABCD-1234", "https://github.com/login/device", 900, 5)

    async def poll_for_token(http, client_id, code):
        return TokenSet("t", scope="repo")

    async def fetch_viewer(api):
        return dict(VIEWER)

    monkeypatch.setattr(auth_controller.device_flow, "request_code", request_code)
    monkeypatch.setattr(auth_controller.device_flow, "poll_for_token", poll_for_token)
    monkeypatch.setattr(auth_controller, "fetch_viewer", fetch_viewer)


async def make(store):
    http = httpx.AsyncClient()
    return AuthController(store=store, http=http), http


async def test_no_keyring_notice_says_you_can_still_sign_in(qapp):
    auth, http = await make(NoKeyring())
    await auth._restore()
    assert auth.property("state") == "signedOut"
    notice = auth.property("notice")
    assert notice.startswith(NO_KEYRING)
    assert "You can still sign in" in notice
    assert "memory for this session only" in notice and "never on disk" in notice
    assert auth.property("tokenStorage") == "none"
    await auth.aclose()
    await http.aclose()


async def test_signing_in_without_keyring_keeps_the_notice_and_reports_memory(qapp, signed_in_flow):
    auth, http = await make(NoKeyring())
    await auth._restore()
    await auth._login()
    assert auth.property("state") == "signedIn"
    assert auth.property("tokenStorage") == "memory"
    # Still told after sign-in, not cleared by loading the account.
    assert "memory for this session only" in auth.property("notice")
    await auth.aclose()
    await http.aclose()


async def test_signing_in_with_keyring_reports_keyring(qapp, signed_in_flow):
    store = MemoryTokenStore()
    auth, http = await make(store)
    await auth._restore()
    assert auth.property("tokenStorage") == "none"
    await auth._login()
    assert auth.property("tokenStorage") == "keyring"
    assert auth.property("notice") == ""
    assert store.load().access_token == "t"
    await auth._forget()
    assert auth.property("tokenStorage") == "none"
    await auth.aclose()
    await http.aclose()


async def test_restored_token_is_reported_as_keyring(qapp, signed_in_flow):
    auth, http = await make(MemoryTokenStore(TokenSet("saved")))
    await auth._restore()
    assert auth.property("state") == "signedIn"
    assert auth.property("tokenStorage") == "keyring"
    await auth.aclose()
    await http.aclose()
