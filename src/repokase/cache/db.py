"""SQLite connection and schema migrations (PRAGMA user_version)."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

_MIGRATION = re.compile(r"^(\d{3})_[\w-]+\.sql$")


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("repokase.cache") / "migrations"
    found = []
    for entry in folder.iterdir():
        match = _MIGRATION.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.read_text()))
    return sorted(found)


class CacheUnavailable(Exception):
    """The cache can't be opened or written (permissions, read-only disk).

    The message is meant for the user.
    """


# SQLITE_CORRUPT and SQLITE_NOTADB: the file is damaged, not merely unreachable.
_DAMAGED = {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}


def _is_damaged(exc: sqlite3.DatabaseError) -> bool:
    return getattr(exc, "sqlite_errorcode", None) in _DAMAGED


def _move_aside(path: Path) -> Path:
    """Rename a damaged cache (and its WAL/SHM files) out of the way; returns the new path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.broken-{stamp}")
    n = 1
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}.broken-{stamp}-{n}")
    for suffix in ("-wal", "-shm"):
        side = path.with_name(path.name + suffix)
        if side.exists():
            side.rename(target.with_name(target.name + suffix))
    path.rename(target)
    return target


def _unavailable(path: Path, exc: Exception) -> CacheUnavailable:
    reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
    return CacheUnavailable(
        f"Repokase can't write its cache at {path} ({reason}). "
        f"Check that you can write to {path.parent}, then start Repokase again."
    )


def open_cache(path: Path) -> tuple[sqlite3.Connection, str]:
    """Open the on-disk cache, rebuilding it if the file is damaged.

    Returns the connection and a notice for the user ("" when nothing happened).
    Raises CacheUnavailable when the cache can't be created or written.
    """
    try:
        try:
            return connect(path, check=True), ""
        except sqlite3.DatabaseError as exc:
            if not _is_damaged(exc):
                raise
            log.warning("Cache %s is damaged (%s); starting a fresh one", path, exc)
            moved = _move_aside(path)
            conn = connect(path)
    except (OSError, sqlite3.DatabaseError) as exc:
        raise _unavailable(path, exc) from exc
    return conn, (
        f"Repokase's cache was damaged, so it started a fresh one; your repositories reload from GitHub. "
        f"Categories and traffic history from before are in the old file, {moved}."
    )


def connect(path: Path | str, check: bool = False) -> sqlite3.Connection:
    """Open (and migrate) a cache database.

    check=True runs SQLite's quick integrity check first, so a damaged file
    raises sqlite3.DatabaseError here instead of somewhere in the UI later.
    """
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)  # explicit transactions
    try:
        conn.row_factory = sqlite3.Row
        if check:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                exc = sqlite3.DatabaseError(f"integrity check failed: {result}")
                exc.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
                raise exc
        conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        migrate(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> None:
    current = schema_version(conn)
    for version, sql in _migrations():
        if version <= current:
            continue
        log.info("Applying cache migration %03d", version)
        conn.execute("BEGIN")
        try:
            for statement in sql.split(";\n"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
