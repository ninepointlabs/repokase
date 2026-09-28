"""Traffic history exposed to QML as the `Traffic` singleton."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .. import jobs
from ..api.errors import ApiError, AuthExpired
from ..cache import store
from .auth_controller import AuthController
from .detail_controller import explain
from .repo_controller import RepoController

log = logging.getLogger(__name__)

# Give the startup repo refresh a head start before snapshotting.
STARTUP_DELAY_MS = 8000


def fill_days(rows: list[dict], until: date | None = None) -> list[dict]:
    """Continuous daily series from the first recorded day to `until`.

    Inside the recorded range a missing day means zero traffic (GitHub omits
    empty days in some responses); before the first snapshot it is unknown,
    so the series starts there.
    """
    if not rows:
        return []
    by_day = {r["day"]: r for r in rows}
    start = date.fromisoformat(rows[0]["day"])
    end = max(until or datetime.now(UTC).date(), date.fromisoformat(rows[-1]["day"]))
    out = []
    d = start
    while d <= end:
        key = d.isoformat()
        r = by_day.get(key)
        out.append({"day": key, "count": r["count"] if r else 0, "uniques": r["uniques"] if r else 0})
        d += timedelta(days=1)
    return out


def summarize(views: list[dict], clones: list[dict]) -> dict:
    def last(series, n=14):
        return series[-n:]

    return {
        "views14": sum(d["count"] for d in last(views)),
        "viewUniques14": sum(d["uniques"] for d in last(views)),
        "clones14": sum(d["count"] for d in last(clones)),
        "cloneUniques14": sum(d["uniques"] for d in last(clones)),
        "viewsAll": sum(d["count"] for d in views),
        "clonesAll": sum(d["count"] for d in clones),
        "since": (views or clones or [{"day": ""}])[0]["day"],
        "days": max(len(views), len(clones)),
    }


class TrafficController(QObject):
    changed = Signal()

    def __init__(self, auth: AuthController, repos: RepoController, parent=None):
        super().__init__(parent)
        self._auth = auth
        self._repos = repos
        self._running = False
        self._progress = ""
        self._error = ""
        self._task: asyncio.Task | None = None
        self._startup = QTimer(self)
        self._startup.setSingleShot(True)
        self._startup.setInterval(STARTUP_DELAY_MS)
        self._startup.timeout.connect(self._snapshot_if_due)
        auth.signedIn.connect(self._startup.start)
        auth.signedOut.connect(self._startup.stop)

    def _set(self, **values) -> None:
        for k, v in values.items():
            setattr(self, f"_{k}", v)
        self.changed.emit()

    def _snapshot_if_due(self) -> None:
        account_id = self._auth.account_id
        if account_id is not None and jobs.traffic_due(self._repos.conn, account_id):
            self.snapshotNow()

    @Slot()
    def snapshotNow(self) -> None:
        if self._running or self._auth.account_id is None:
            return
        self._task = asyncio.ensure_future(self._snapshot())

    async def _snapshot(self) -> None:
        account_id = self._auth.account_id
        self._set(running=True, progress="Recording traffic…", error="")

        def progress(done, total):
            self._set(progress=f"Recording traffic {done}/{total}")

        try:
            result = await jobs.snapshot_traffic(self._auth.api, self._repos.conn, account_id, progress)
        except AuthExpired:
            self._set(running=False, progress="")
            await self._auth.expire_session()
            return
        except ApiError as exc:
            self._set(running=False, progress="", error=explain(exc, "record traffic"))
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("Traffic snapshot failed")
            self._set(running=False, progress="", error=f"Could not record traffic: {exc}")
            return
        msg = f"Traffic recorded for {len(result.traffic)} repos"
        self._set(running=False, progress="", error="" if not result.failed else f"{len(result.failed)} repos failed")
        log.info(msg)

    @Slot(str, result="QVariantMap")
    def forRepo(self, full_name: str) -> dict:
        conn = self._repos.conn
        views = fill_days(store.load_traffic(conn, full_name, "views"))
        clones = fill_days(store.load_traffic(conn, full_name, "clones"))
        return {
            "views": views,
            "clones": clones,
            "referrers": store.latest_referrers(conn, full_name),
            "totals": summarize(views, clones),
        }

    @property
    def last_snapshot(self) -> str:
        account_id = self._auth.account_id
        if account_id is None:
            return ""
        sync = store.get_sync(self._repos.conn, account_id, jobs.TRAFFIC_RESOURCE) or {}
        return sync.get("last_success") or ""

    running = Property(bool, lambda self: self._running, notify=changed)
    progress = Property(str, lambda self: self._progress, notify=changed)
    error = Property(str, lambda self: self._error, notify=changed)
    lastSnapshot = Property(str, lambda self: self.last_snapshot, notify=changed)
