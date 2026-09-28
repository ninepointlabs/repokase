"""Repository list state exposed to QML as the `Repos` singleton.

Opens instantly from the SQLite cache, then refreshes from GitHub in the
background; the cache is replaced atomically once a full fetch succeeds.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections import Counter
from datetime import datetime

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from ..api import health as health_api
from ..api import repos as repos_api
from ..api.errors import ApiError, AuthExpired, NetworkError, RateLimited
from ..cache import store
from ..models.repo_model import RepoFilterModel, RepoListModel
from .auth_controller import AuthController

log = logging.getLogger(__name__)

AUTO_REFRESH_MS = 15 * 60 * 1000
# Opening the app within this window of the last sync skips the startup fetch.
FRESH_ENOUGH_S = 60
UI_STATE_KEY = "ui.repoList"


def _parse_ts(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class AccountCache:
    """Adapter handed to AuthController for offline starts."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save(self, viewer: dict) -> None:
        store.save_account(self._conn, viewer)

    def load(self) -> dict | None:
        return store.load_account(self._conn)


class RepoController(QObject):
    changed = Signal()
    categoriesChanged = Signal()
    # Emitted after the cache is (re)loaded into the model.
    reposReloaded = Signal()
    # One repo changed in place (topics, categories, later: actions).
    repoUpdated = Signal(str)
    marksChanged = Signal()

    def __init__(self, auth: AuthController, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._auth = auth
        self._conn = conn
        self._source = RepoListModel(self)
        self._proxy = RepoFilterModel(self._source, self)
        self._refreshing = False
        self._progress = ""
        self._error = ""
        self._warnings: list[str] = []
        self._last_synced = 0.0
        self._languages: list[str] = []
        self._categories: list[dict] = []
        # Bulk selection ("marks"), separate from the keyboard cursor.
        self._marked: set[str] = set()
        self._owners: list[str] = []
        self._task: asyncio.Task | None = None
        self._restoring_ui = False

        self._timer = QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._clock = QTimer(self)
        self._clock.setInterval(30_000)
        self._clock.timeout.connect(self.changed)  # re-evaluates relative times

        auth.signedIn.connect(self._on_signed_in)
        auth.signedOut.connect(self._on_signed_out)
        self._proxy.changed.connect(self._save_ui_state)

    # ------------------------------------------------------------ lifecycle
    def _on_signed_in(self) -> None:
        account_id = self._auth.account_id
        if account_id is None:
            return
        self._restoring_ui = True
        self._proxy.restore(store.get_setting(self._conn, UI_STATE_KEY, {}))
        self._restoring_ui = False
        self._load_cache(account_id)
        self._timer.start()
        self._clock.start()
        if time.time() - self._last_synced > FRESH_ENOUGH_S:
            self.refresh()

    def _on_signed_out(self) -> None:
        # The cache is kept (it is what makes the next start instant); only the
        # in-memory view is cleared. Categories are local and never deleted here.
        self._timer.stop()
        self._clock.stop()
        if self._task and not self._task.done():
            self._task.cancel()
        self._source.set_repos([])
        self._marked.clear()
        self.marksChanged.emit()
        self._categories = []
        self.categoriesChanged.emit()
        self._set(refreshing=False, progress="", error="", warnings=[], last_synced=0.0)

    def _load_cache(self, account_id: int) -> None:
        repos = store.load_repos(self._conn, account_id)
        ids = {r["node_id"] for r in repos}
        if self._marked - ids:
            self._marked &= ids
            self.marksChanged.emit()
        for r in repos:
            r["marked"] = r["node_id"] in self._marked
        self._source.set_repos(repos)
        sync = store.get_sync(self._conn, account_id, "repos") or {}
        self._last_synced = _parse_ts(sync.get("last_success"))
        self._update_facets(repos)
        self._load_categories()
        log.info("Loaded %d repos from cache", len(repos))
        self.changed.emit()
        self.reposReloaded.emit()

    def _update_facets(self, repos: list[dict]) -> None:
        langs = Counter(r["primary_language"] for r in repos if r.get("primary_language"))
        self._languages = [name for name, _ in langs.most_common()]
        me = self._auth.property("login")
        owners = Counter(r["owner"] for r in repos)
        self._owners = sorted(owners, key=lambda o: (o != me, o.lower()))

    def _save_ui_state(self) -> None:
        if not self._restoring_ui:
            store.set_setting(self._conn, UI_STATE_KEY, self._proxy.state())

    def _set(self, **values) -> None:
        for key, value in values.items():
            setattr(self, f"_{key}", value)
        self.changed.emit()

    # -------------------------------------------------------------- refresh
    @Slot()
    def refresh(self) -> None:
        if self._refreshing or self._auth.account_id is None:
            return
        self._task = asyncio.ensure_future(self._refresh())
        self._task.add_done_callback(self._refresh_done)

    def _refresh_done(self, task: asyncio.Task) -> None:
        if task.cancelled() or task.exception() is None:
            return
        log.error("Repo refresh crashed", exc_info=task.exception())
        self._set(refreshing=False, progress="", error=f"Refresh failed: {task.exception()}")

    async def _refresh(self) -> None:
        account_id = self._auth.account_id
        self._set(refreshing=True, progress="Refreshing…", error="")

        def progress(done: int, total: int) -> None:
            self._set(progress=f"Fetched {done} of {total}")

        try:
            result = await repos_api.fetch_all_repos(self._auth.api, on_progress=progress)
        except AuthExpired:
            self._set(refreshing=False, progress="")
            await self._auth.expire_session()
            return
        except RateLimited as exc:
            when = time.strftime("%H:%M", time.localtime(exc.reset_at)) if exc.reset_at else "later"
            self._fail(account_id, f"GitHub rate limit reached. Try again after {when}.")
            return
        except NetworkError:
            self._fail(account_id, "Offline: could not reach GitHub. Showing cached data.")
            return
        except ApiError as exc:
            self._fail(account_id, str(exc))
            return
        if self._auth.account_id != account_id:
            return  # signed out or switched mid-fetch
        store.replace_repos(self._conn, account_id, result.repos)
        store.mark_sync(self._conn, account_id, "repos")
        self._load_cache(account_id)
        warnings = list(result.warnings)
        warnings += await self._check_health(account_id, result.repos)
        self._set(refreshing=False, progress="", warnings=sorted(set(warnings)))

    async def _check_health(self, account_id: int, repos: list[dict]) -> list[str]:
        """Score every repo; failures here never fail the refresh."""
        self._set(progress="Checking health…")
        try:
            signals, warnings = await health_api.fetch_signals(self._auth.api, [r["node_id"] for r in repos])
        except AuthExpired:
            await self._auth.expire_session()
            return []
        except (ApiError, NetworkError) as exc:
            log.info("Health check skipped: %s", exc)
            return [f"Health check skipped: {exc}"]
        results = {r["node_id"]: health_api.compute_health(r, signals.get(r["node_id"])) for r in repos}
        if self._auth.account_id != account_id:
            return []
        store.save_health(self._conn, account_id, results, signals)
        self._load_cache(account_id)
        return warnings

    def _fail(self, account_id: int | None, message: str) -> None:
        if account_id is not None:
            store.mark_sync(self._conn, account_id, "repos", error=message)
        self._set(refreshing=False, progress="", error=message)

    # ----------------------------------------------------------- categories
    def _load_categories(self) -> None:
        self._categories = store.list_categories(self._conn, self._auth.account_id)
        self.categoriesChanged.emit()

    def _category_call(self, fn, *args) -> str:
        """Run a category mutation; returns an error message or ""."""
        try:
            fn(self._conn, *args)
        except store.CategoryError as exc:
            return str(exc)
        self._load_categories()
        return ""

    @Slot(str, result=str)
    def createCategory(self, name: str) -> str:
        return self._category_call(store.create_category, name)

    @Slot(int, str, result=str)
    def renameCategory(self, category_id: int, name: str) -> str:
        return self._category_call(store.rename_category, category_id, name)

    @Slot(int)
    def deleteCategory(self, category_id: int) -> None:
        store.delete_category(self._conn, category_id)
        if self._proxy.property("category") == category_id:
            self._proxy.setProperty("category", -1)
        # Drop the id from every repo that had it.
        for repo in self._source.repos():
            if category_id in (repo.get("category_ids") or []):
                self._source.update_repo(
                    repo["node_id"], category_ids=[c for c in repo["category_ids"] if c != category_id]
                )
        self._load_categories()

    @Slot(int, int)
    def moveCategory(self, category_id: int, delta: int) -> None:
        store.move_category(self._conn, category_id, delta)
        self._load_categories()

    @Slot(str, int)
    def toggleCategory(self, node_id: str, category_id: int) -> None:
        account_id = self._auth.account_id
        repo = self._source.get_repo(node_id)
        if account_id is None or repo is None:
            return
        on = category_id not in (repo.get("category_ids") or [])
        store.set_repo_category(self._conn, account_id, node_id, category_id, on)
        self._source.update_repo(node_id, category_ids=store.repo_category_ids(self._conn, account_id, node_id))
        self._load_categories()
        self.repoUpdated.emit(node_id)

    @Slot(str, result="QVariantMap")
    def repo(self, node_id: str) -> dict:
        return dict(self._source.get_repo(node_id) or {})

    @Slot(int, result=int)
    def categoryIdAt(self, position: int) -> int:
        """Category id for keyboard slot 1..9 (sidebar order), or -1."""
        return self._categories[position - 1]["id"] if 1 <= position <= len(self._categories) else -1

    def _uncategorized(self) -> int:
        return sum(1 for r in self._source.repos() if not r.get("category_ids"))

    # ----------------------------------------------------------------- marks
    def _mark(self, node_id: str, on: bool) -> None:
        if (node_id in self._marked) == on or self._source.get_repo(node_id) is None:
            return
        (self._marked.add if on else self._marked.discard)(node_id)
        self._source.update_repo(node_id, marked=on)

    @Slot(str)
    def toggleMark(self, node_id: str) -> None:
        self._mark(node_id, node_id not in self._marked)
        self.marksChanged.emit()

    @Slot(str, bool)
    def setMarked(self, node_id: str, on: bool) -> None:
        self._mark(node_id, on)
        self.marksChanged.emit()

    @Slot(int, int)
    def markRange(self, row_a: int, row_b: int) -> None:
        """Mark visible rows a..b inclusive (list order)."""
        lo, hi = sorted((row_a, row_b))
        for row in range(max(0, lo), min(self._proxy.rowCount() - 1, hi) + 1):
            repo = self._proxy.get(row)
            if repo:
                self._mark(repo["node_id"], True)
        self.marksChanged.emit()

    @Slot()
    def markAllVisible(self) -> None:
        self.markRange(0, self._proxy.rowCount() - 1)

    @Slot()
    def clearMarks(self) -> None:
        for node_id in list(self._marked):
            self._mark(node_id, False)
        self.marksChanged.emit()

    def marked_ids(self) -> list[str]:
        return [r["node_id"] for r in self._source.repos() if r["node_id"] in self._marked]

    def _hidden_marks(self) -> int:
        visible = {self._proxy.get(i)["node_id"] for i in range(self._proxy.rowCount())}
        return len(self._marked - visible)

    @Slot(int, bool)
    def setCategoryForMarked(self, category_id: int, on: bool) -> None:
        account_id = self._auth.account_id
        if account_id is None:
            return
        with store.transaction(self._conn):
            for node_id in self.marked_ids():
                store.set_repo_category(self._conn, account_id, node_id, category_id, on)
        for node_id in self.marked_ids():
            self._source.update_repo(node_id, category_ids=store.repo_category_ids(self._conn, account_id, node_id))
            self.repoUpdated.emit(node_id)
        self._load_categories()

    # ---------------------------------------------------------------- slots
    @Slot(str)
    def openUrl(self, url: str) -> None:
        if url.startswith("https://github.com/"):
            QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    @Slot()
    def dismissError(self) -> None:
        self._set(error="")

    # ----------------------------------------------------------- properties
    list = Property(QObject, lambda self: self._proxy, constant=True)
    total = Property(int, lambda self: self._source.rowCount(), notify=changed)
    refreshing = Property(bool, lambda self: self._refreshing, notify=changed)
    progress = Property(str, lambda self: self._progress, notify=changed)
    error = Property(str, lambda self: self._error, notify=changed)
    warnings = Property("QVariantList", lambda self: self._warnings, notify=changed)
    lastSynced = Property(float, lambda self: self._last_synced * 1000, notify=changed)
    now = Property(float, lambda self: time.time() * 1000, notify=changed)
    languages = Property("QVariantList", lambda self: self._languages, notify=changed)
    owners = Property("QVariantList", lambda self: self._owners, notify=changed)
    categories = Property("QVariantList", lambda self: self._categories, notify=categoriesChanged)
    markedCount = Property(int, lambda self: len(self._marked), notify=marksChanged)
    markedIds = Property("QVariantList", lambda self: self.marked_ids(), notify=marksChanged)
    hiddenMarked = Property(int, lambda self: self._hidden_marks(), notify=marksChanged)
    uncategorized = Property(int, lambda self: self._uncategorized(), notify=categoriesChanged)

    # For other controllers.
    @property
    def source(self) -> RepoListModel:
        return self._source

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn
