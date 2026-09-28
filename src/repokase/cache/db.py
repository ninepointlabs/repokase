"""SQLite connection and schema migrations (PRAGMA user_version)."""

from __future__ import annotations

import logging
import re
import sqlite3
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


def connect(path: Path | str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)  # explicit transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    migrate(conn)
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
