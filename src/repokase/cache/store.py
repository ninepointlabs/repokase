"""Typed reads and writes over the cache database."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime

REPO_COLUMNS = (
    "node_id",
    "database_id",
    "owner",
    "name",
    "full_name",
    "description",
    "url",
    "visibility",
    "is_archived",
    "is_fork",
    "is_template",
    "is_mirror",
    "primary_language",
    "stargazers",
    "forks",
    "watchers",
    "open_issues",
    "open_prs",
    "default_branch",
    "license_spdx",
    "disk_kb",
    "viewer_permission",
    "pushed_at",
    "created_at",
    "updated_at",
)

BOOL_COLUMNS = {"is_archived", "is_fork", "is_template", "is_mirror"}


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# ------------------------------------------------------------------ account
def save_account(conn: sqlite3.Connection, viewer: dict) -> int:
    account_id = int(viewer["databaseId"])
    conn.execute(
        """INSERT INTO account (id, login, name, avatar_url, profile_url, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET login=excluded.login, name=excluded.name,
             avatar_url=excluded.avatar_url, profile_url=excluded.profile_url,
             updated_at=excluded.updated_at""",
        (account_id, viewer["login"], viewer.get("name"), viewer.get("avatarUrl"), viewer.get("url"), utcnow()),
    )
    return account_id


def load_account(conn: sqlite3.Connection) -> dict | None:
    """Most recently seen account, in the same shape as the GraphQL viewer."""
    row = conn.execute("SELECT * FROM account ORDER BY updated_at DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return {
        "databaseId": row["id"],
        "login": row["login"],
        "name": row["name"],
        "avatarUrl": row["avatar_url"],
        "url": row["profile_url"],
    }


# -------------------------------------------------------------------- repos
def replace_repos(conn: sqlite3.Connection, account_id: int, repos: Iterable[dict]) -> int:
    """Make the cache match a complete fetch: upsert all, drop the rest."""
    fetched_at = utcnow()
    cols = ", ".join(REPO_COLUMNS)
    marks = ", ".join("?" for _ in REPO_COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in REPO_COLUMNS if c != "node_id")
    seen: list[str] = []
    with transaction(conn):
        for repo in repos:
            values = [int(bool(repo.get(c))) if c in BOOL_COLUMNS else repo.get(c) for c in REPO_COLUMNS]
            conn.execute(
                f"""INSERT INTO repo (account_id, {cols}, fetched_at) VALUES (?, {marks}, ?)
                    ON CONFLICT(account_id, node_id) DO UPDATE SET {updates}, fetched_at=excluded.fetched_at""",
                (account_id, *values, fetched_at),
            )
            conn.execute("DELETE FROM repo_topic WHERE account_id=? AND repo_id=?", (account_id, repo["node_id"]))
            conn.executemany(
                "INSERT OR IGNORE INTO repo_topic (account_id, repo_id, topic) VALUES (?, ?, ?)",
                [(account_id, repo["node_id"], t) for t in repo.get("topics", [])],
            )
            seen.append(repo["node_id"])
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _seen (node_id TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM _seen")
        conn.executemany("INSERT OR IGNORE INTO _seen VALUES (?)", [(n,) for n in seen])
        conn.execute(
            "DELETE FROM repo WHERE account_id=? AND node_id NOT IN (SELECT node_id FROM _seen)",
            (account_id,),
        )
    return len(seen)


def load_repos(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    rows = conn.execute(
        f"SELECT {', '.join(REPO_COLUMNS)}, fetched_at FROM repo WHERE account_id=?", (account_id,)
    ).fetchall()
    topics: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT repo_id, topic FROM repo_topic WHERE account_id=? ORDER BY topic", (account_id,)
    ):
        topics.setdefault(r["repo_id"], []).append(r["topic"])
    categories: dict[str, list[int]] = {}
    for r in conn.execute("SELECT repo_id, category_id FROM repo_category WHERE account_id=?", (account_id,)):
        categories.setdefault(r["repo_id"], []).append(r["category_id"])
    health: dict[str, dict] = {}
    for r in conn.execute("SELECT repo_id, flags_json FROM health WHERE account_id=?", (account_id,)):
        try:
            health[r["repo_id"]] = json.loads(r["flags_json"])
        except ValueError:
            pass
    out = []
    for row in rows:
        repo = dict(row)
        for c in BOOL_COLUMNS:
            repo[c] = bool(repo[c])
        repo["topics"] = topics.get(repo["node_id"], [])
        repo["category_ids"] = categories.get(repo["node_id"], [])
        repo["health"] = health.get(repo["node_id"], {"level": "unknown", "flags": []})
        out.append(repo)
    return out


# --------------------------------------------------------------- sync state
def mark_sync(conn: sqlite3.Connection, account_id: int, resource: str, error: str | None = None) -> None:
    now = utcnow()
    if error is None:
        conn.execute(
            """INSERT INTO sync_state (account_id, resource, last_success, last_error) VALUES (?, ?, ?, NULL)
               ON CONFLICT(account_id, resource) DO UPDATE SET last_success=excluded.last_success, last_error=NULL""",
            (account_id, resource, now),
        )
    else:
        conn.execute(
            """INSERT INTO sync_state (account_id, resource, last_error) VALUES (?, ?, ?)
               ON CONFLICT(account_id, resource) DO UPDATE SET last_error=excluded.last_error""",
            (account_id, resource, error),
        )


def get_sync(conn: sqlite3.Connection, account_id: int, resource: str) -> dict | None:
    row = conn.execute(
        "SELECT last_success, last_error FROM sync_state WHERE account_id=? AND resource=?",
        (account_id, resource),
    ).fetchone()
    return dict(row) if row else None


# ----------------------------------------------------------------- settings
def get_setting(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:
        return default


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


# --------------------------------------------------------------- categories
class CategoryError(ValueError):
    pass


def _clean_category_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise CategoryError("Category name can't be empty.")
    if len(name) > 40:
        raise CategoryError("Category names are limited to 40 characters.")
    return name


def list_categories(conn: sqlite3.Connection, account_id: int | None) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.name, c.sort_order,
                  (SELECT COUNT(*) FROM repo_category rc
                    WHERE rc.category_id = c.id AND rc.account_id = ?) AS count
             FROM category c ORDER BY c.sort_order, c.name COLLATE NOCASE""",
        (account_id if account_id is not None else -1,),
    ).fetchall()
    # `position` drives the 1-9 shortcut and the theme color.
    return [dict(r, position=i) for i, r in enumerate(rows)]


def create_category(conn: sqlite3.Connection, name: str) -> int:
    name = _clean_category_name(name)
    next_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM category").fetchone()[0]
    try:
        cur = conn.execute("INSERT INTO category (name, sort_order) VALUES (?, ?)", (name, next_order))
    except sqlite3.IntegrityError as exc:
        raise CategoryError(f'A category named "{name}" already exists.') from exc
    return int(cur.lastrowid)


def rename_category(conn: sqlite3.Connection, category_id: int, name: str) -> None:
    name = _clean_category_name(name)
    try:
        conn.execute("UPDATE category SET name=? WHERE id=?", (name, category_id))
    except sqlite3.IntegrityError as exc:
        raise CategoryError(f'A category named "{name}" already exists.') from exc


def delete_category(conn: sqlite3.Connection, category_id: int) -> None:
    conn.execute("DELETE FROM category WHERE id=?", (category_id,))  # assignments cascade


def move_category(conn: sqlite3.Connection, category_id: int, delta: int) -> None:
    ids = [r[0] for r in conn.execute("SELECT id FROM category ORDER BY sort_order, name COLLATE NOCASE")]
    if category_id not in ids:
        return
    i = ids.index(category_id)
    j = max(0, min(len(ids) - 1, i + delta))
    ids.insert(j, ids.pop(i))
    with transaction(conn):
        conn.executemany("UPDATE category SET sort_order=? WHERE id=?", [(n, cid) for n, cid in enumerate(ids)])


def set_repo_category(conn: sqlite3.Connection, account_id: int, repo_id: str, category_id: int, on: bool) -> None:
    if on:
        conn.execute(
            "INSERT OR IGNORE INTO repo_category (account_id, repo_id, category_id) VALUES (?, ?, ?)",
            (account_id, repo_id, category_id),
        )
    else:
        conn.execute(
            "DELETE FROM repo_category WHERE account_id=? AND repo_id=? AND category_id=?",
            (account_id, repo_id, category_id),
        )


def repo_category_ids(conn: sqlite3.Connection, account_id: int, repo_id: str) -> list[int]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT category_id FROM repo_category WHERE account_id=? AND repo_id=? ORDER BY category_id",
            (account_id, repo_id),
        )
    ]


# ------------------------------------------------------------------- topics
def set_repo_topics(conn: sqlite3.Connection, account_id: int, repo_id: str, topics: list[str]) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM repo_topic WHERE account_id=? AND repo_id=?", (account_id, repo_id))
        conn.executemany(
            "INSERT OR IGNORE INTO repo_topic (account_id, repo_id, topic) VALUES (?, ?, ?)",
            [(account_id, repo_id, t) for t in topics],
        )


# ------------------------------------------------------------ workflow runs
RUN_COLUMNS = (
    "id",
    "workflow_id",
    "name",
    "status",
    "conclusion",
    "event",
    "head_branch",
    "run_number",
    "created_at",
    "html_url",
)


def replace_workflow_runs(conn: sqlite3.Connection, account_id: int, repo_id: str, runs: list[dict]) -> None:
    now = utcnow()
    with transaction(conn):
        conn.execute("DELETE FROM workflow_run WHERE account_id=? AND repo_id=?", (account_id, repo_id))
        conn.executemany(
            f"""INSERT OR REPLACE INTO workflow_run (account_id, repo_id, {', '.join(RUN_COLUMNS)}, fetched_at)
                VALUES (?, ?, {', '.join('?' for _ in RUN_COLUMNS)}, ?)""",
            [(account_id, repo_id, *(r.get(c) for c in RUN_COLUMNS), now) for r in runs],
        )
        mark_sync(conn, account_id, f"runs:{repo_id}")


def load_workflow_runs(conn: sqlite3.Connection, account_id: int, repo_id: str, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        f"""SELECT {', '.join(RUN_COLUMNS)} FROM workflow_run
             WHERE account_id=? AND repo_id=? ORDER BY created_at DESC LIMIT ?""",
        (account_id, repo_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------ repo mutations
MUTABLE_REPO_FIELDS = {
    "description", "visibility", "is_archived", "updated_at", "pushed_at", "stargazers", "watchers", "forks",
}


def update_repo_fields(conn: sqlite3.Connection, account_id: int, node_id: str, fields: dict) -> None:
    fields = {k: v for k, v in fields.items() if k in MUTABLE_REPO_FIELDS}
    if not fields:
        return
    values = [int(bool(v)) if k in BOOL_COLUMNS else v for k, v in fields.items()]
    assignments = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE repo SET {assignments} WHERE account_id=? AND node_id=?", (*values, account_id, node_id)
    )


def delete_repo(conn: sqlite3.Connection, account_id: int, node_id: str) -> None:
    # Topics, categories, runs and health cascade. Traffic history is kept
    # (keyed by full_name) in case the repo is restored.
    conn.execute("DELETE FROM repo WHERE account_id=? AND node_id=?", (account_id, node_id))


# ------------------------------------------------------------------ traffic
def save_traffic(conn: sqlite3.Connection, full_name: str, kind: str, days: list[dict]) -> None:
    """Upsert daily counts. GitHub revises the current day, so later wins."""
    conn.executemany(
        """INSERT INTO traffic_daily (full_name, day, kind, count, uniques) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(full_name, day, kind) DO UPDATE SET count=excluded.count, uniques=excluded.uniques""",
        [(full_name, d["day"], kind, d["count"], d["uniques"]) for d in days],
    )


def save_referrers(conn: sqlite3.Connection, full_name: str, day: str, referrers: list[dict]) -> None:
    conn.execute("DELETE FROM traffic_referrer WHERE full_name=? AND snapshot_day=?", (full_name, day))
    conn.executemany(
        "INSERT INTO traffic_referrer (full_name, snapshot_day, referrer, count, uniques) VALUES (?, ?, ?, ?, ?)",
        [(full_name, day, r["referrer"], r["count"], r["uniques"]) for r in referrers],
    )


def load_traffic(conn: sqlite3.Connection, full_name: str, kind: str) -> list[dict]:
    rows = conn.execute(
        "SELECT day, count, uniques FROM traffic_daily WHERE full_name=? AND kind=? ORDER BY day",
        (full_name, kind),
    ).fetchall()
    return [dict(r) for r in rows]


def latest_referrers(conn: sqlite3.Connection, full_name: str) -> list[dict]:
    row = conn.execute(
        "SELECT MAX(snapshot_day) FROM traffic_referrer WHERE full_name=?", (full_name,)
    ).fetchone()
    if not row or not row[0]:
        return []
    return [
        dict(r)
        for r in conn.execute(
            """SELECT referrer, count, uniques FROM traffic_referrer
                WHERE full_name=? AND snapshot_day=? ORDER BY count DESC LIMIT 10""",
            (full_name, row[0]),
        )
    ]


def traffic_totals(conn: sqlite3.Connection, account_id: int) -> dict[str, dict]:
    """Per repo: views/clones over the last 14 recorded days (for list sorting)."""
    rows = conn.execute(
        """SELECT t.full_name, t.kind, SUM(t.count) AS total
             FROM traffic_daily t JOIN repo r ON r.full_name = t.full_name AND r.account_id = ?
            WHERE t.day >= date('now', '-13 days') GROUP BY t.full_name, t.kind""",
        (account_id,),
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["full_name"], {})[r["kind"]] = r["total"]
    return out


# ------------------------------------------------------------------- health
def save_health(conn: sqlite3.Connection, account_id: int, results: dict[str, dict], signals: dict[str, dict]) -> None:
    now = utcnow()
    with transaction(conn):
        conn.executemany(
            """INSERT INTO health (account_id, repo_id, computed_at, flags_json, alert_counts_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(account_id, repo_id) DO UPDATE SET computed_at=excluded.computed_at,
                 flags_json=excluded.flags_json, alert_counts_json=excluded.alert_counts_json""",
            [
                (account_id, node_id, now, json.dumps(h), json.dumps(signals.get(node_id)))
                for node_id, h in results.items()
            ],
        )
