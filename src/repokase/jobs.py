"""Background jobs shared by the GUI and the headless CLI (no Qt here)."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime

from .api import traffic as traffic_api
from .api.client import GitHubClient
from .cache import store

log = logging.getLogger(__name__)

TRAFFIC_RESOURCE = "traffic"
# Run at most about once a day; a little under 24h so a daily timer never skips.
TRAFFIC_DUE_AFTER_S = 20 * 3600


def _age_s(iso: str | None) -> float:
    if not iso:
        return float("inf")
    try:
        return time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("inf")


def traffic_due(conn: sqlite3.Connection, account_id: int) -> bool:
    sync = store.get_sync(conn, account_id, TRAFFIC_RESOURCE) or {}
    return _age_s(sync.get("last_success")) >= TRAFFIC_DUE_AFTER_S


async def snapshot_traffic(
    client: GitHubClient,
    conn: sqlite3.Connection,
    account_id: int,
    on_progress: Callable[[int, int], None] | None = None,
) -> traffic_api.SnapshotResult:
    repos = store.load_repos(conn, account_id)
    result = await traffic_api.snapshot(client, repos, on_progress)
    today = datetime.now(UTC).date().isoformat()
    with store.transaction(conn):
        for t in result.traffic:
            store.save_traffic(conn, t.full_name, "views", t.views)
            store.save_traffic(conn, t.full_name, "clones", t.clones)
            store.save_referrers(conn, t.full_name, today, t.referrers)
        store.mark_sync(conn, account_id, TRAFFIC_RESOURCE)
    log.info(
        "Traffic snapshot: %d repos saved, %d skipped (archived or no push access), %d failed",
        len(result.traffic), len(result.skipped), len(result.failed),
    )
    return result
