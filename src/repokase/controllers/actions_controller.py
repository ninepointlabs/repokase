"""Repository actions exposed to QML as the `Actions` singleton.

Every mutation goes through `_run`, which serialises actions, maps API
failures to a sentence the UI can show (plus an SSO authorization link when
GitHub provides one), and applies successful changes to the cache and the
list model in place, without waiting for a full refresh.
"""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..api import actions as api
from ..api.errors import ApiError, AuthExpired, GraphQLError, ScopeMissing, SsoRequired
from ..cache import store
from .auth_controller import AuthController
from .detail_controller import explain
from .repo_controller import RepoController

log = logging.getLogger(__name__)

DELETE_SCOPE = "delete_repo"
ADMIN = {"ADMIN"}


class ActionsController(QObject):
    changed = Signal()
    # message for the status bar
    done = Signal(str)
    deleted = Signal(str)
    # A scope is missing: QML runs re-authorization, then retries.
    scopeNeeded = Signal(str, str)

    def __init__(self, auth: AuthController, repos: RepoController, parent=None):
        super().__init__(parent)
        self._auth = auth
        self._repos = repos
        self._busy = ""
        self._error = ""
        self._error_url = ""
        self._task: asyncio.Task | None = None

    # -------------------------------------------------------------- helpers
    def _repo(self, node_id: str) -> dict | None:
        return self._repos.source.get_repo(node_id)

    def _set(self, **values) -> None:
        for key, value in values.items():
            setattr(self, f"_{key}", value)
        self.changed.emit()

    def _start(self, label: str, coro) -> None:
        if self._busy:
            coro.close()
            return
        self._set(busy=label, error="", error_url="")
        self._task = asyncio.ensure_future(coro)

    async def _run(self, action: str, node_id: str, call, on_success) -> None:
        try:
            result = await call()
        except asyncio.CancelledError:
            raise
        except AuthExpired:
            self._set(busy="")
            await self._auth.expire_session()
            return
        except ScopeMissing as exc:
            self._set(busy="", error=explain(exc, action))
            return
        except SsoRequired as exc:
            self._set(busy="", error=explain(exc, action), error_url=exc.url or "")
            return
        except (ApiError, GraphQLError, ValueError) as exc:
            message = str(exc) if isinstance(exc, (ValueError, GraphQLError)) else explain(exc, action)
            self._set(busy="", error=message)
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("Action failed: %s", action)
            self._set(busy="", error=f"Could not {action}: {exc}")
            return
        message = on_success(result)
        self._set(busy="")
        if message:
            self.done.emit(message)

    def _apply(self, node_id: str, fields: dict) -> None:
        account_id = self._auth.account_id
        if account_id is not None:
            store.update_repo_fields(self._repos.conn, account_id, node_id, fields)
        self._repos.source.update_repo(node_id, **{k: v for k, v in fields.items() if k in store.MUTABLE_REPO_FIELDS})
        self._repos.repoUpdated.emit(node_id)

    # -------------------------------------------------------------- queries
    @Slot(str, result="QVariantMap")
    def capabilities(self, node_id: str) -> dict:
        """What the viewer may do to this repo, and why not."""
        repo = self._repo(node_id) or {}
        admin = repo.get("viewer_permission") in ADMIN
        maintain = repo.get("viewer_permission") in {"ADMIN", "MAINTAIN"}
        archived = bool(repo.get("is_archived"))
        fork = bool(repo.get("is_fork"))
        need_admin = "Needs admin access to this repository."
        return {
            "archive": admin,
            "archiveWhy": "" if admin else need_admin,
            "visibility": admin and not archived and not fork,
            "visibilityWhy": need_admin if not admin
            else "Archived repositories are read-only. Unarchive first." if archived
            else "A fork's visibility follows its parent repository." if fork
            else "",
            "description": maintain and not archived,
            "descriptionWhy": "Needs admin or maintain access." if not maintain
            else "Archived repositories are read-only. Unarchive first." if archived
            else "",
            "delete": admin,
            "deleteWhy": "" if admin else need_admin,
            "hasDeleteScope": self._auth.hasScope(DELETE_SCOPE),
            # Internal only exists for organization repos on GitHub Enterprise;
            # offer it only when the repo already uses it.
            "canInternal": repo.get("visibility") == "INTERNAL",
        }

    # -------------------------------------------------------------- actions
    @Slot(str, bool)
    def setArchived(self, node_id: str, archived: bool) -> None:
        repo = self._repo(node_id)
        if not repo:
            return
        verb = "archive" if archived else "unarchive"

        def success(fields):
            self._apply(node_id, fields)
            return f"{'Archived' if archived else 'Unarchived'} {repo['full_name']}"

        self._start(
            "Archiving…" if archived else "Unarchiving…",
            self._run(f"{verb} the repository", node_id, lambda: api.set_archived(self._auth.api, node_id, archived), success),
        )

    @Slot(str, str)
    def setVisibility(self, node_id: str, visibility: str) -> None:
        repo = self._repo(node_id)
        if not repo:
            return

        def success(fields):
            self._apply(node_id, fields)
            return f"{repo['full_name']} is now {visibility.lower()}"

        self._start(
            "Changing visibility…",
            self._run("change visibility", node_id, lambda: api.set_visibility(self._auth.api, repo["full_name"], visibility), success),
        )

    @Slot(str, str)
    def setDescription(self, node_id: str, description: str) -> None:
        repo = self._repo(node_id)
        if not repo:
            return

        def success(fields):
            self._apply(node_id, fields)
            return "Description updated"

        self._start(
            "Saving description…",
            self._run("update the description", node_id, lambda: api.set_description(self._auth.api, repo["full_name"], description), success),
        )

    @Slot(str, str)
    def deleteRepo(self, node_id: str, typed_name: str) -> None:
        repo = self._repo(node_id)
        if not repo:
            return
        # The UI enforces this too; never trust a single layer for deletes.
        if typed_name.strip() != repo["full_name"]:
            self._set(error="The name you typed does not match. Nothing was deleted.")
            return
        if not self._auth.hasScope(DELETE_SCOPE):
            self.scopeNeeded.emit(DELETE_SCOPE, node_id)
            return

        def success(_):
            account_id = self._auth.account_id
            if account_id is not None:
                store.delete_repo(self._repos.conn, account_id, node_id)
            self._repos.source.remove_repo(node_id)
            self._repos.reposReloaded.emit()
            self.deleted.emit(node_id)
            return f"Deleted {repo['full_name']}"

        self._start(
            "Deleting…",
            self._run("delete the repository", node_id, lambda: api.delete_repo(self._auth.api, repo["full_name"]), success),
        )

    # ------------------------------------------------------------------- bulk
    @Slot("QVariantList", bool)
    def bulkArchive(self, node_ids: list, archived: bool) -> None:
        """Archive/unarchive several repos one by one, reporting per repo."""
        repos = [r for r in (self._repo(str(n)) for n in node_ids) if r]
        todo = [r for r in repos if r.get("viewer_permission") in ADMIN and bool(r.get("is_archived")) != archived]
        skipped = len(repos) - len(todo)
        verb = "Archived" if archived else "Unarchived"

        async def go():
            failures: list[str] = []
            for i, repo in enumerate(todo, 1):
                self._set(busy=f"{'Archiving' if archived else 'Unarchiving'} {i}/{len(todo)}…")
                try:
                    fields = await api.set_archived(self._auth.api, repo["node_id"], archived)
                except AuthExpired:
                    self._set(busy="")
                    await self._auth.expire_session()
                    return
                except (ApiError, GraphQLError) as exc:
                    failures.append(f"{repo['full_name']}: {exc}")
                    continue
                self._apply(repo["node_id"], fields)
            done = len(todo) - len(failures)
            parts = [f"{verb} {done} of {len(repos)}"]
            if skipped:
                parts.append(f"{skipped} skipped (already {'archived' if archived else 'active'} or no admin access)")
            self._set(busy="", error=("Failed: " + "; ".join(failures)) if failures else "")
            self.done.emit(" · ".join(parts))
            self._repos.clearMarks()

        self._start("Working…", go())

    @Slot()
    def clearError(self) -> None:
        self._set(error="", error_url="")

    async def settle(self) -> None:
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    # ----------------------------------------------------------- properties
    busy = Property(bool, lambda self: bool(self._busy), notify=changed)
    busyLabel = Property(str, lambda self: self._busy, notify=changed)
    error = Property(str, lambda self: self._error, notify=changed)
    errorUrl = Property(str, lambda self: self._error_url, notify=changed)
    descriptionMax = Property(int, lambda self: api.DESCRIPTION_MAX, constant=True)
