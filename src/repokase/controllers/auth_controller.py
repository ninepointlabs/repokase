"""Sign-in state machine exposed to QML as the `Auth` singleton."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from .. import config
from ..api.client import GitHubClient, RateLimit
from ..api.repos import fetch_viewer
from ..api.errors import ApiError, AuthExpired, NetworkError
from ..auth import device_flow
from ..auth.device_flow import DeviceFlowError, TokenSet
from ..auth.token_store import SecretServiceTokenStore, TokenStore, TokenStoreError

log = logging.getLogger(__name__)


class AuthController(QObject):
    changed = Signal()
    signedIn = Signal()
    signedOut = Signal()
    # Re-authorization for extra scopes finished; the new token is active.
    reauthorized = Signal()

    # States: starting, signedOut, requesting, awaitingUser, signedIn
    def __init__(
        self,
        store: TokenStore | None = None,
        http: httpx.AsyncClient | None = None,
        accounts=None,
        parent=None,
    ):
        """`accounts` caches the viewer for offline starts: save(viewer), load() -> viewer | None."""
        super().__init__(parent)
        self._accounts = accounts
        self._store = store or SecretServiceTokenStore()
        # Secret Service calls can block on an unlock prompt; keep them off the
        # UI thread, serialized on one thread (one D-Bus connection).
        self._keyring = ThreadPoolExecutor(max_workers=1, thread_name_prefix="keyring")
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))
        self._token: TokenSet | None = None
        self._state = "starting"
        self._error = ""
        self._notice = ""
        self._user_code = ""
        self._verification_uri = ""
        self._expires_at = 0.0
        self._requested_scopes: tuple[str, ...] = config.BASE_SCOPES
        self._reason = ""
        self._viewer: dict = {}
        self._rate: RateLimit | None = None
        self._task: asyncio.Task | None = None
        # In-app re-authorization (extra scopes) runs beside the signed-in UI:
        # "", "requesting", "awaitingUser", "error".
        self._reauth = ""
        self._reauth_error = ""
        self._reauth_task: asyncio.Task | None = None
        self._refresh_lock = asyncio.Lock()
        self.api = GitHubClient(self._http, self.access_token, on_rate_limit=self._on_rate)

    # ---------------------------------------------------------------- helpers
    def _set(self, **values) -> None:
        for key, value in values.items():
            setattr(self, f"_{key}", value)
        self.changed.emit()

    async def _store_call(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self._keyring, fn, *args)

    def _spawn(self, coro) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.ensure_future(coro)
        self._task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        # Surface crashes instead of letting the UI sit in a stale state.
        if task.cancelled() or task.exception() is None:
            return
        exc = task.exception()
        log.error("Sign-in task failed", exc_info=exc)
        self._set(
            state="signedIn" if self._viewer and self._token else "signedOut",
            error=f"Something went wrong during sign-in: {exc}",
        )

    def _on_rate(self, rl: RateLimit) -> None:
        if rl.resource in ("core", "graphql"):
            self._rate = rl
            self.changed.emit()

    async def access_token(self) -> str:
        if self._token is None:
            raise AuthExpired()
        if self._token.needs_refresh():
            await self._refresh()
        return self._token.access_token

    async def _refresh(self) -> None:
        async with self._refresh_lock:
            token = self._token
            if token is None or not token.needs_refresh():
                return
            if not token.refresh_token:
                raise AuthExpired()
            # The headless traffic job shares this keyring entry and may have
            # refreshed (rotating the refresh token) since we loaded it.
            try:
                stored = await self._store_call(self._store.load)
            except TokenStoreError:
                stored = None
            if stored and stored.access_token != token.access_token and not stored.needs_refresh():
                self._token = stored
                return
            refresh_with = (stored or token).refresh_token or token.refresh_token
            try:
                new = await device_flow.refresh_token(self._http, config.github_client_id(), refresh_with)
            except DeviceFlowError as exc:
                if exc.code == "network":
                    raise NetworkError(exc.detail or "") from exc
                raise AuthExpired() from exc
            self._token = new
            await self._persist(new)

    async def _persist(self, token: TokenSet) -> None:
        try:
            await self._store_call(self._store.save, token)
            self._notice = ""
        except TokenStoreError as exc:
            log.warning("Token not persisted: %s", exc)
            self._notice = f"{exc} You will need to sign in again next time."
        self.changed.emit()

    # ------------------------------------------------------------ startup
    @Slot()
    def restore(self) -> None:
        self._spawn(self._restore())

    async def _restore(self) -> None:
        try:
            token = await self._store_call(self._store.load)
        except TokenStoreError as exc:
            self._set(state="signedOut", notice=str(exc))
            return
        if token is None:
            self._set(state="signedOut")
            return
        self._token = token
        await self._load_viewer(restoring=True)

    async def _load_viewer(self, restoring: bool = False) -> None:
        try:
            viewer = await fetch_viewer(self.api)
        except AuthExpired:
            await self.expire_session()
            return
        except NetworkError:
            cached = self._accounts.load() if self._accounts else None
            if restoring and cached:
                # Offline start: stay signed in with the cached identity.
                # The repo refresh reports the offline state; no second notice here.
                self._set(viewer=cached, state="signedIn")
                self.signedIn.emit()
                return
            raise
        except ApiError as exc:
            self._set(state="signedOut", error=str(exc))
            return
        if self._accounts:
            self._accounts.save(viewer)
        self._set(viewer=viewer, state="signedIn", error="", notice="")
        self.signedIn.emit()

    async def expire_session(self) -> None:
        """The token was revoked or expired for good: back to the login screen."""
        await self._forget()
        self._set(state="signedOut", error=AuthExpired().args[0])
        self.signedOut.emit()

    @property
    def account_id(self) -> int | None:
        value = self._viewer.get("databaseId")
        return int(value) if value is not None else None

    # -------------------------------------------------------------- login
    @Slot()
    def startLogin(self) -> None:
        self._requested_scopes = config.BASE_SCOPES
        self._reason = ""
        self._spawn(self._login())

    def current_scopes(self) -> set[str]:
        return set(self.api.granted_scopes or (self._token.scopes if self._token else set()))

    @Slot(str, result=bool)
    def hasScope(self, scope: str) -> bool:
        return scope in self.current_scopes()

    @Slot(str, str)
    def requestScope(self, scope: str, reason: str) -> None:
        """Re-authorize in place with one more scope (e.g. delete_repo).

        Stays signed in throughout: the current token keeps working until the
        new one is granted, and nothing changes if the user cancels.
        """
        if self._reauth_task and not self._reauth_task.done():
            self._reauth_task.cancel()
        scopes = tuple(sorted(set(config.BASE_SCOPES) | self.current_scopes() | {scope}))
        self._reason = reason
        self._reauth_task = asyncio.ensure_future(self._reauthorize(scopes, scope))

    async def _reauthorize(self, scopes: tuple[str, ...], needed: str) -> None:
        self._set(reauth="requesting", reauth_error="", user_code="", verification_uri="")
        client_id = config.github_client_id()
        try:
            code = await device_flow.request_code(self._http, client_id, scopes)
            self._set(
                reauth="awaitingUser",
                user_code=code.user_code,
                verification_uri=code.verification_uri,
                expires_at=time.time() + code.expires_in,
            )
            token = await device_flow.poll_for_token(self._http, client_id, code)
            # The browser may be signed in to a different GitHub account.
            async def new_token() -> str:
                return token.access_token

            probe = GitHubClient(self._http, new_token)
            viewer = await fetch_viewer(probe)
        except asyncio.CancelledError:
            raise
        except (DeviceFlowError, ApiError) as exc:
            self._set(reauth="error", reauth_error=str(exc), user_code="")
            return
        if viewer.get("databaseId") != self._viewer.get("databaseId"):
            self._set(
                reauth="error",
                user_code="",
                reauth_error=f"You authorized as @{viewer.get('login')}, but Repokase is signed in as "
                f"@{self._viewer.get('login')}. Switch accounts on github.com and try again.",
            )
            return
        granted = token.scopes | (probe.granted_scopes or set())
        if needed not in granted:
            self._set(reauth="error", user_code="", reauth_error=f"GitHub did not grant the {needed} permission.")
            return
        self._token = token
        self.api.granted_scopes = None  # re-read from the next response
        await self._persist(token)
        self._set(reauth="", reauth_error="", user_code="", verification_uri="", reason="")
        self.reauthorized.emit()

    @Slot()
    def cancelReauth(self) -> None:
        if self._reauth_task and not self._reauth_task.done():
            self._reauth_task.cancel()
        self._set(reauth="", reauth_error="", user_code="", verification_uri="", reason="")

    async def _login(self) -> None:
        self._set(state="requesting", error="", user_code="", verification_uri="")
        client_id = config.github_client_id()
        try:
            code = await device_flow.request_code(self._http, client_id, self._requested_scopes)
            self._set(
                state="awaitingUser",
                user_code=code.user_code,
                verification_uri=code.verification_uri,
                expires_at=time.time() + code.expires_in,
            )
            token = await device_flow.poll_for_token(self._http, client_id, code)
        except asyncio.CancelledError:
            raise
        except DeviceFlowError as exc:
            self._set(state="signedIn" if self._viewer and self._token else "signedOut", error=str(exc))
            return
        log.debug("device flow complete; saving token")
        self._token = token
        await self._persist(token)
        log.debug("token saved; loading account")
        self._set(user_code="", verification_uri="", reason="")
        try:
            await self._load_viewer()
        except NetworkError as exc:
            self._set(state="signedOut", error=str(exc))

    @Slot()
    def cancelLogin(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._set(
            state="signedIn" if self._viewer and self._token else "signedOut",
            user_code="",
            verification_uri="",
            reason="",
        )

    @Slot()
    def openBrowser(self) -> None:
        if self._verification_uri:
            QDesktopServices.openUrl(QUrl(self._verification_uri))

    @Slot()
    def copyCode(self) -> None:
        if self._user_code:
            QGuiApplication.clipboard().setText(self._user_code)

    @Slot(str)
    def openUrl(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------ sign out
    async def _forget(self) -> None:
        self._token = None
        self._viewer = {}
        try:
            await self._store_call(self._store.clear)
        except TokenStoreError as exc:
            log.warning("Could not clear keyring: %s", exc)

    @Slot()
    def signOut(self) -> None:
        async def run():
            await self._forget()
            self._set(state="signedOut", error="", notice="")
            self.signedOut.emit()

        self._spawn(run())

    async def aclose(self) -> None:
        for task in (self._task, self._reauth_task):
            if task and not task.done():
                task.cancel()
        await self._http.aclose()
        self._keyring.shutdown(wait=False)

    # --------------------------------------------------------- properties
    state = Property(str, lambda self: self._state, notify=changed)
    error = Property(str, lambda self: self._error, notify=changed)
    notice = Property(str, lambda self: self._notice, notify=changed)
    userCode = Property(str, lambda self: self._user_code, notify=changed)
    verificationUri = Property(str, lambda self: self._verification_uri, notify=changed)
    expiresAt = Property(float, lambda self: self._expires_at * 1000, notify=changed)  # ms, for QML Date
    reason = Property(str, lambda self: self._reason, notify=changed)
    reauthState = Property(str, lambda self: self._reauth, notify=changed)
    reauthError = Property(str, lambda self: self._reauth_error, notify=changed)
    login = Property(str, lambda self: self._viewer.get("login", ""), notify=changed)
    displayName = Property(str, lambda self: self._viewer.get("name") or "", notify=changed)
    avatarUrl = Property(str, lambda self: self._viewer.get("avatarUrl", ""), notify=changed)
    profileUrl = Property(str, lambda self: self._viewer.get("url", ""), notify=changed)
    scopes = Property(
        str,
        lambda self: ", ".join(sorted(self.api.granted_scopes or (self._token.scopes if self._token else set()))),
        notify=changed,
    )
    rateRemaining = Property(int, lambda self: self._rate.remaining if self._rate and self._rate.remaining is not None else -1, notify=changed)
    rateLimit = Property(int, lambda self: self._rate.limit if self._rate and self._rate.limit else -1, notify=changed)
    rateResetAt = Property(float, lambda self: (self._rate.reset_at or 0) * 1000 if self._rate else 0, notify=changed)
