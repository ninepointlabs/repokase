import sqlite3

import pytest

from repokase.cache import db, store


def repo(node_id, name, **kw):
    base = {
        "node_id": node_id,
        "database_id": 1,
        "owner": "octo",
        "name": name,
        "full_name": f"octo/{name}",
        "description": None,
        "url": f"https://github.com/octo/{name}",
        "visibility": "PUBLIC",
        "is_archived": False,
        "is_fork": False,
        "is_template": False,
        "is_mirror": False,
        "primary_language": "Python",
        "stargazers": 0,
        "forks": 0,
        "watchers": 1,
        "open_issues": 0,
        "open_prs": 0,
        "pushed_at": "2026-01-01T00:00:00Z",
        "topics": [],
    }
    base.update(kw)
    return base


VIEWER = {"databaseId": 42, "login": "octo", "name": "Octo", "avatarUrl": "a", "url": "u"}


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def test_migrations_apply_and_are_idempotent(tmp_path):
    path = tmp_path / "cache.db"
    c = db.connect(path)
    assert db.schema_version(c) == 1
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"account", "repo", "repo_topic", "category", "repo_category", "workflow_run",
            "sync_state", "setting", "traffic_daily", "traffic_referrer", "workflow", "health"} <= tables
    c.close()
    c = db.connect(path)  # reopen: no re-apply, no error
    assert db.schema_version(c) == 1
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()


def test_account_roundtrip(conn):
    assert store.load_account(conn) is None
    assert store.save_account(conn, VIEWER) == 42
    store.save_account(conn, VIEWER | {"name": "Renamed"})
    loaded = store.load_account(conn)
    assert loaded["login"] == "octo" and loaded["name"] == "Renamed" and loaded["databaseId"] == 42


def test_replace_repos_upserts_and_prunes(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha", topics=["cli", "rust"]), repo("B", "beta")])
    rows = {r["node_id"]: r for r in store.load_repos(conn, aid)}
    assert set(rows) == {"A", "B"}
    assert rows["A"]["topics"] == ["cli", "rust"]
    assert rows["A"]["is_archived"] is False

    store.replace_repos(conn, aid, [repo("A", "alpha", stargazers=9, is_archived=True, topics=["cli"])])
    rows = store.load_repos(conn, aid)
    assert [r["node_id"] for r in rows] == ["A"]
    assert rows[0]["stargazers"] == 9 and rows[0]["is_archived"] is True
    assert rows[0]["topics"] == ["cli"]
    assert conn.execute("SELECT COUNT(*) FROM repo_topic WHERE repo_id='B'").fetchone()[0] == 0


def test_categories_survive_refresh_and_go_with_their_repo(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha"), repo("B", "beta")])
    conn.execute("INSERT INTO category (id, name) VALUES (1, 'Work')")
    conn.executemany(
        "INSERT INTO repo_category (account_id, repo_id, category_id) VALUES (?, ?, 1)",
        [(aid, "A"), (aid, "B")],
    )
    store.replace_repos(conn, aid, [repo("A", "alpha", stargazers=3)])
    rows = store.load_repos(conn, aid)
    assert rows[0]["category_ids"] == [1]
    assert conn.execute("SELECT COUNT(*) FROM repo_category").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM category").fetchone()[0] == 1


def test_failed_replace_rolls_back(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha")])
    bad = repo("B", "beta")
    del bad["url"]  # NOT NULL violation mid-transaction
    bad["url"] = None
    with pytest.raises(sqlite3.IntegrityError):
        store.replace_repos(conn, aid, [repo("C", "gamma"), bad])
    assert [r["node_id"] for r in store.load_repos(conn, aid)] == ["A"]


def test_accounts_are_isolated(conn):
    a = store.save_account(conn, VIEWER)
    b = store.save_account(conn, VIEWER | {"databaseId": 7, "login": "other"})
    store.replace_repos(conn, a, [repo("A", "alpha")])
    store.replace_repos(conn, b, [repo("Z", "zed")])
    store.replace_repos(conn, a, [])
    assert store.load_repos(conn, a) == []
    assert [r["node_id"] for r in store.load_repos(conn, b)] == ["Z"]


def test_sync_state(conn):
    aid = store.save_account(conn, VIEWER)
    assert store.get_sync(conn, aid, "repos") is None
    store.mark_sync(conn, aid, "repos", error="offline")
    assert store.get_sync(conn, aid, "repos") == {"last_success": None, "last_error": "offline"}
    store.mark_sync(conn, aid, "repos")
    s = store.get_sync(conn, aid, "repos")
    assert s["last_success"] and s["last_error"] is None
    store.mark_sync(conn, aid, "repos", error="again")
    s2 = store.get_sync(conn, aid, "repos")
    assert s2["last_success"] == s["last_success"] and s2["last_error"] == "again"


def test_settings(conn):
    assert store.get_setting(conn, "x", {"d": 1}) == {"d": 1}
    store.set_setting(conn, "x", {"sortKey": "stars"})
    store.set_setting(conn, "x", {"sortKey": "name"})
    assert store.get_setting(conn, "x") == {"sortKey": "name"}


def test_category_crud_order_and_counts(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha"), repo("B", "beta")])
    work = store.create_category(conn, "  Work  ")
    play = store.create_category(conn, "Play")
    with pytest.raises(store.CategoryError, match="already exists"):
        store.create_category(conn, "work")  # case-insensitive unique
    with pytest.raises(store.CategoryError):
        store.create_category(conn, "   ")
    with pytest.raises(store.CategoryError):
        store.create_category(conn, "x" * 41)

    store.set_repo_category(conn, aid, "A", work, True)
    store.set_repo_category(conn, aid, "A", work, True)  # idempotent
    store.set_repo_category(conn, aid, "B", work, True)
    store.set_repo_category(conn, aid, "B", play, True)
    cats = store.list_categories(conn, aid)
    assert [(c["name"], c["count"], c["position"]) for c in cats] == [("Work", 2, 0), ("Play", 1, 1)]

    store.move_category(conn, play, -1)
    assert [c["name"] for c in store.list_categories(conn, aid)] == ["Play", "Work"]
    store.rename_category(conn, work, "Job")
    with pytest.raises(store.CategoryError):
        store.rename_category(conn, work, "play")

    store.set_repo_category(conn, aid, "B", work, False)
    assert store.repo_category_ids(conn, aid, "B") == [play]
    store.delete_category(conn, play)
    assert store.repo_category_ids(conn, aid, "B") == []
    assert [c["name"] for c in store.list_categories(conn, aid)] == ["Job"]


def test_set_repo_topics(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha", topics=["old"])])
    store.set_repo_topics(conn, aid, "A", ["cli", "go"])
    assert store.load_repos(conn, aid)[0]["topics"] == ["cli", "go"]


def test_workflow_runs_replace_and_sync(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha")])
    run = {"id": 1, "name": "CI", "status": "completed", "conclusion": "success", "created_at": "2026-09-01T00:00:00Z"}
    store.replace_workflow_runs(conn, aid, "A", [run, dict(run, id=2, created_at="2026-09-02T00:00:00Z")])
    runs = store.load_workflow_runs(conn, aid, "A")
    assert [r["id"] for r in runs] == [2, 1]  # newest first
    assert store.get_sync(conn, aid, "runs:A")["last_success"]
    store.replace_workflow_runs(conn, aid, "A", [])
    assert store.load_workflow_runs(conn, aid, "A") == []
    # Runs go with their repo.
    store.replace_workflow_runs(conn, aid, "A", [run])
    store.replace_repos(conn, aid, [])
    assert conn.execute("SELECT COUNT(*) FROM workflow_run").fetchone()[0] == 0
