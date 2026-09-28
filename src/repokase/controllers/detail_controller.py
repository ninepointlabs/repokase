"""Selected-repository detail, exposed to QML as the `Detail` singleton."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ..api import rest
from ..api.errors import ApiError, AuthExpired, NetworkError, NotFound, RateLimited, ScopeMissing, SsoRequired
from ..cache import store
from .auth_controller import AuthController
from .repo_controller import RepoController

log = logging.getLogger(__name__)

# Selection moves fast with j/k; only fetch once it settles.
FETCH_DEBOUNCE_MS = 350
RUNS_STALE_S = 120
WRITE_PERMISSIONS = {"ADMIN", "MAINTAIN"}


def _age_s(iso: str | None) -> float:
    if not iso:
        return float("inf")
    try:
        return time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("inf")


def explain(exc: Exception, action: str, access: str = "admin or maintain") -> str:
    if isinstance(exc, NetworkError):
        return f"Offline: could not {action}."
    if isinstance(exc, SsoRequired):
        return f"This organization requires SSO for Repokase. Authorize it on GitHub, then try again."
    if isinstance(exc, ScopeMissing):
        return f"Repokase needs more GitHub permission to {action}."
    if isinstance(exc, RateLimited):
        return f"GitHub rate limit reached; could not {action}."
    if isinstance(exc, NotFound):
        return f"Could not {action}: the repository was not found or you lost access."
    if isinstance(exc, ApiError) and exc.status == 403:
        return f"GitHub refused: you need {access} access to {action}."
    return f"Could not {action}: {exc}"


class DetailController(QObject):
    changed = Signal()  # selected repo
    runsChanged = Signal()
    topicsChanged = Signal()  # topic save state only

    def __init__(self, auth: AuthController, repos: RepoController, parent=None):
        super().__init__(parent)
        self._auth = auth
        self._repos = repos
        self._node_id = ""
        self._repo: dict = {}
        self._runs: list[dict] = []
        self._runs_loading = False
        self._runs_error = ""
        self._runs_synced = ""
        self._topics_busy = False
        self._topics_error = ""
        self._runs_task: asyncio.Task | None = None
        self._topics_task: asyncio.Task | None = None

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(FETCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._fetch_if_stale)

        repos.reposReloaded.connect(self._reload_repo)
        repos.repoUpdated.connect(lambda nid: nid == self._node_id and self._reload_repo())
        auth.signedOut.connect(lambda: self.select(""))

    # ------------------------------------------------------------ selection
    @Slot(str)
    def select(self, node_id: str) -> None:
        if node_id == self._node_id:
            return
        self._node_id = node_id
        if self._runs_task and not self._runs_task.done():
            self._runs_task.cancel()
        self._runs_error = ""
        self._runs_loading = False
        self._set_topics(error="")
        self._reload_repo()
        self._load_cached_runs()
        if node_id:
            self._debounce.start()
        else:
            self._debounce.stop()

    def _reload_repo(self) -> None:
        repo = self._repos.source.get_repo(self._node_id) if self._node_id else None
        self._repo = dict(repo) if repo else {}
        self.changed.emit()

    def _load_cached_runs(self) -> None:
        account_id = self._auth.account_id
        if not self._node_id or account_id is None:
            self._runs, self._runs_synced = [], ""
        else:
            conn = self._repos.conn
            self._runs = store.load_workflow_runs(conn, account_id, self._node_id)
            sync = store.get_sync(conn, account_id, f"runs:{self._node_id}") or {}
            self._runs_synced = sync.get("last_success") or ""
        self.runsChanged.emit()

    def _fetch_if_stale(self) -> None:
        if self._node_id and _age_s(self._runs_synced) > RUNS_STALE_S:
            self.refreshRuns()

    # ----------------------------------------------------------------- runs
    @Slot()
    def refreshRuns(self) -> None:
        if not self._repo:
            return
        if self._runs_task and not self._runs_task.done():
            self._runs_task.cancel()
        self._runs_task = asyncio.ensure_future(self._fetch_runs(self._node_id, self._repo["full_name"]))

    async def _fetch_runs(self, node_id: str, full_name: str) -> None:
        account_id = self._auth.account_id
        self._runs_loading, self._runs_error = True, ""
        self.runsChanged.emit()
        try:
            runs = await rest.list_workflow_runs(self._auth.api, full_name)
        except asyncio.CancelledError:
            raise
        except AuthExpired:
            await self._auth.expire_session()
            return
        except Exception as exc:  # noqa: BLE001 - surfaced in the pane
            if node_id == self._node_id:
                self._runs_loading, self._runs_error = False, explain(exc, "load workflow runs")
                self.runsChanged.emit()
            if not isinstance(exc, ApiError):
                log.exception("Workflow run fetch failed")
            return
        if account_id is None:
            return
        store.replace_workflow_runs(self._repos.conn, account_id, node_id, runs)
        if node_id == self._node_id:
            self._runs_loading = False
            self._load_cached_runs()

    # --------------------------------------------------------------- topics
    @Slot(str, result="QVariantMap")
    def checkTopic(self, raw: str) -> dict:
        try:
            return {"ok": True, "topic": rest.normalize_topic(raw), "error": ""}
        except rest.TopicError as exc:
            return {"ok": False, "topic": "", "error": str(exc)}

    @Slot("QVariantList")
    def saveTopics(self, topics: list) -> None:
        if not self._repo or self._topics_busy:
            return
        try:
            cleaned = rest.validate_topics([str(t) for t in topics])
        except rest.TopicError as exc:
            self._set_topics(error=str(exc))
            return
        self._topics_task = asyncio.ensure_future(self._save_topics(self._node_id, self._repo["full_name"], cleaned))

    async def _save_topics(self, node_id: str, full_name: str, topics: list[str]) -> None:
        self._set_topics(busy=True, error="")
        try:
            saved = await rest.replace_topics(self._auth.api, full_name, topics)
        except AuthExpired:
            self._set_topics(busy=False)
            await self._auth.expire_session()
            return
        except Exception as exc:  # noqa: BLE001
            self._set_topics(busy=False, error=explain(exc, "update topics"))
            if not isinstance(exc, (ApiError, rest.TopicError)):
                log.exception("Topic update failed")
            return
        account_id = self._auth.account_id
        if account_id is not None:
            store.set_repo_topics(self._repos.conn, account_id, node_id, saved)
            self._repos.source.update_repo(node_id, topics=saved)
        self._set_topics(busy=False, error="")
        self._repos.repoUpdated.emit(node_id)

    def _set_topics(self, busy: bool | None = None, error: str | None = None) -> None:
        before = (self._topics_busy, self._topics_error)
        if busy is not None:
            self._topics_busy = busy
        if error is not None:
            self._topics_error = error
        if (self._topics_busy, self._topics_error) != before:
            self.topicsChanged.emit()

    @Slot()
    def clearTopicsError(self) -> None:
        self._set_topics(error="")

    # ---------------------------------------------------------------- links
    @Slot(str, result=str)
    def link(self, kind: str) -> str:
        url = self._repo.get("url", "")
        suffix = {
            "repo": "",
            "issues": "/issues",
            "pulls": "/pulls",
            "actions": "/actions",
            "releases": "/releases",
            "settings": "/settings",
            "insights": "/pulse",
        }.get(kind)
        return url + suffix if url and suffix is not None else ""

    @Slot(str, result=str)
    def cloneUrl(self, kind: str) -> str:
        full = self._repo.get("full_name", "")
        if not full:
            return ""
        return f"git@github.com:{full}.git" if kind == "ssh" else f"https://github.com/{full}.git"

    # ----------------------------------------------------------- properties
    nodeId = Property(str, lambda self: self._node_id, notify=changed)
    repo = Property("QVariantMap", lambda self: self._repo, notify=changed)
    hasRepo = Property(bool, lambda self: bool(self._repo), notify=changed)
    canAdmin = Property(bool, lambda self: self._repo.get("viewer_permission") in WRITE_PERMISSIONS, notify=changed)
    topicsBusy = Property(bool, lambda self: self._topics_busy, notify=topicsChanged)
    topicsError = Property(str, lambda self: self._topics_error, notify=topicsChanged)
    runs = Property("QVariantList", lambda self: self._runs, notify=runsChanged)
    runsLoading = Property(bool, lambda self: self._runs_loading, notify=runsChanged)
    runsError = Property(str, lambda self: self._runs_error, notify=runsChanged)
    runsSynced = Property(str, lambda self: self._runs_synced, notify=runsChanged)
