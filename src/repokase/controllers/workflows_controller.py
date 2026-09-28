"""GitHub Actions controls, exposed to QML as the `Workflows` singleton."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ..api import workflows as api
from ..api.errors import ApiError, AuthExpired, SsoRequired
from .auth_controller import AuthController
from .detail_controller import DetailController, explain
from .repo_controller import RepoController

log = logging.getLogger(__name__)

WRITE = {"ADMIN", "MAINTAIN", "WRITE"}
# GitHub needs a moment before new or re-run runs show up in the list.
RUNS_RELOAD_DELAY_MS = 4000


class WorkflowsController(QObject):
    changed = Signal()
    done = Signal(str)

    def __init__(self, auth: AuthController, repos: RepoController, detail: DetailController, parent=None):
        super().__init__(parent)
        self._auth = auth
        self._repos = repos
        self._detail = detail
        self._busy = ""
        self._error = ""
        self._error_url = ""
        self._loading = False
        self._dispatchables: list[dict] = []
        self._branches: list[str] = []
        self._default_branch = ""
        self._loaded_for = ""
        self._task: asyncio.Task | None = None
        self._reload = QTimer(self)
        self._reload.setSingleShot(True)
        self._reload.setInterval(RUNS_RELOAD_DELAY_MS)
        self._reload.timeout.connect(detail.refreshRuns)

    def _set(self, **values) -> None:
        for k, v in values.items():
            setattr(self, f"_{k}", v)
        self.changed.emit()

    def _repo(self, node_id: str) -> dict | None:
        return self._repos.source.get_repo(node_id)

    async def _guard(self, action: str, coro):
        """Await `coro`, mapping failures to UI state. Returns (ok, result)."""
        try:
            return True, await coro
        except asyncio.CancelledError:
            raise
        except AuthExpired:
            self._set(busy="", loading=False)
            await self._auth.expire_session()
        except SsoRequired as exc:
            self._set(busy="", loading=False, error=explain(exc, action, "write"), error_url=exc.url or "")
        except ValueError as exc:
            self._set(busy="", loading=False, error=str(exc))
        except ApiError as exc:
            self._set(busy="", loading=False, error=explain(exc, action, "write"))
        except Exception as exc:  # noqa: BLE001
            log.exception("Workflow action failed")
            self._set(busy="", loading=False, error=f"Could not {action}: {exc}")
        return False, None

    def _spawn(self, coro) -> None:
        if self._task and not self._task.done():
            coro.close()
            return
        self._task = asyncio.ensure_future(coro)

    @Slot(str, result=bool)
    def canRun(self, node_id: str) -> bool:
        repo = self._repo(node_id) or {}
        return repo.get("viewer_permission") in WRITE and not repo.get("is_archived")

    # ------------------------------------------------------------- run actions
    @Slot(str, int, str)
    def runAction(self, node_id: str, run_id: int, action: str) -> None:
        repo = self._repo(node_id)
        if not repo or action not in ("rerun", "rerun-failed", "cancel"):
            return
        label = {"rerun": "Re-running…", "rerun-failed": "Re-running failed jobs…", "cancel": "Cancelling…"}[action]
        verb = {"rerun": "re-run the workflow", "rerun-failed": "re-run failed jobs", "cancel": "cancel the run"}[action]

        async def go():
            self._set(busy=label, error="", error_url="")
            ok, _ = await self._guard(verb, api.run_action(self._auth.api, repo["full_name"], run_id, action))
            if ok:
                self._set(busy="")
                self.done.emit({"rerun": "Re-run started", "rerun-failed": "Re-running failed jobs",
                                "cancel": "Cancel requested"}[action])
                self._reload.start()

        self._spawn(go())

    # ---------------------------------------------------------------- dispatch
    @Slot(str)
    def loadDispatch(self, node_id: str) -> None:
        repo = self._repo(node_id)
        if not repo:
            return

        async def go():
            self._set(loading=True, error="", error_url="", dispatchables=[], branches=[])
            default = repo.get("default_branch") or "main"
            ok, found = await self._guard(
                "load workflows",
                asyncio.gather(
                    api.dispatchable_workflows(self._auth.api, repo["full_name"], default),
                    api.list_branches(self._auth.api, repo["full_name"]),
                ),
            )
            if not ok:
                return
            workflows, branches = found
            # Default branch first, the rest as GitHub orders them.
            branches = [default] + [b for b in branches if b != default]
            self._set(loading=False, dispatchables=workflows, branches=branches,
                      default_branch=default, loaded_for=node_id)

        self._spawn(go())

    @Slot(str, int, str, "QVariantMap")
    def dispatch(self, node_id: str, workflow_id: int, ref: str, values: dict) -> None:
        repo = self._repo(node_id)
        wf = next((w for w in self._dispatchables if w["id"] == workflow_id), None)
        if not repo or not wf:
            return
        try:
            inputs = api.validate_inputs(wf["inputs"], dict(values or {}))
        except ValueError as exc:
            self._set(error=str(exc))
            return

        async def go():
            self._set(busy="Starting workflow…", error="", error_url="")
            ok, _ = await self._guard(
                "start the workflow", api.dispatch(self._auth.api, repo["full_name"], workflow_id, ref, inputs)
            )
            if ok:
                self._set(busy="")
                self.done.emit(f"Started {wf['name']} on {ref}")
                self._reload.start()

        self._spawn(go())

    @Slot()
    def clearError(self) -> None:
        self._set(error="", error_url="")

    async def settle(self) -> None:
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    busy = Property(bool, lambda self: bool(self._busy), notify=changed)
    busyLabel = Property(str, lambda self: self._busy, notify=changed)
    error = Property(str, lambda self: self._error, notify=changed)
    errorUrl = Property(str, lambda self: self._error_url, notify=changed)
    loading = Property(bool, lambda self: self._loading, notify=changed)
    dispatchables = Property("QVariantList", lambda self: self._dispatchables, notify=changed)
    branches = Property("QVariantList", lambda self: self._branches, notify=changed)
    defaultBranch = Property(str, lambda self: self._default_branch, notify=changed)
    loadedFor = Property(str, lambda self: self._loaded_for, notify=changed)
