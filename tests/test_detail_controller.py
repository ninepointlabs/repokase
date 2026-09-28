"""Detail + categories controllers against an in-memory cache and mocked GitHub."""

import asyncio

import httpx
import pytest
import respx
from PySide6.QtCore import QCoreApplication

from repokase.api.client import API_URL
from repokase.auth.device_flow import TokenSet
from repokase.auth.token_store import MemoryTokenStore
from repokase.cache import db, store
from repokase.controllers.auth_controller import AuthController
from repokase.controllers.detail_controller import DetailController
from repokase.controllers.repo_controller import AccountCache, RepoController

from test_cache import VIEWER, repo


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
async def env(qapp):
    conn = db.connect(":memory:")
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [
        repo("A", "alpha", viewer_permission="ADMIN", topics=["old"]),
        repo("B", "beta", viewer_permission="READ"),
    ])
    store.mark_sync(conn, aid, "repos")  # fresh: no startup refresh
    http = httpx.AsyncClient()
    auth = AuthController(store=MemoryTokenStore(), http=http, accounts=AccountCache(conn))
    auth._token = TokenSet("t")
    repos = RepoController(auth, conn)
    detail = DetailController(auth, repos)
    auth._viewer = dict(VIEWER)
    auth._state = "signedIn"
    auth.signedIn.emit()
    yield auth, repos, detail, conn
    detail._debounce.stop()
    await settle(detail)
    await http.aclose()
    conn.close()


async def settle(detail):
    for task in (detail._runs_task, detail._topics_task):
        if task:
            await asyncio.gather(task, return_exceptions=True)


@respx.mock
async def test_select_loads_repo_and_fetches_runs_into_cache(env):
    auth, repos, detail, conn = env
    respx.get(f"{API_URL}/repos/octo/alpha/actions/runs").respond(
        json={"workflow_runs": [{"id": 5, "name": "CI", "status": "completed", "conclusion": "success",
                                 "created_at": "2026-09-01T00:00:00Z", "html_url": "https://github.com/x"}]}
    )
    detail.select("A")
    assert detail.property("repo")["full_name"] == "octo/alpha"
    assert detail.property("canAdmin") is True
    detail.refreshRuns()
    await settle(detail)
    assert [r["id"] for r in detail.property("runs")] == [5]
    assert store.load_workflow_runs(conn, 42, "A")[0]["conclusion"] == "success"
    detail.select("B")
    assert detail.property("canAdmin") is False and detail.property("runs") == []


@respx.mock
async def test_runs_error_is_explained_not_raised(env):
    _, _, detail, _ = env
    respx.get(f"{API_URL}/repos/octo/alpha/actions/runs").mock(side_effect=httpx.ConnectError("x"))
    detail.select("A")
    detail.refreshRuns()
    await settle(detail)
    assert "Offline" in detail.property("runsError")
    assert detail.property("runsLoading") is False


@respx.mock
async def test_save_topics_updates_github_cache_and_model(env):
    _, repos, detail, conn = env
    route = respx.put(f"{API_URL}/repos/octo/alpha/topics").respond(json={"names": ["cli", "rust"]})
    detail.select("A")
    detail.saveTopics(["CLI", "rust"])
    await settle(detail)
    assert route.called
    assert detail.property("repo")["topics"] == ["cli", "rust"]
    assert repos.source.get_repo("A")["topics"] == ["cli", "rust"]
    assert store.load_repos(conn, 42)[0]["topics"] == ["cli", "rust"]
    assert detail.property("topicsError") == "" and detail.property("topicsBusy") is False


@respx.mock
async def test_save_topics_forbidden_keeps_old_topics(env):
    _, repos, detail, _ = env
    respx.put(f"{API_URL}/repos/octo/alpha/topics").respond(403, json={"message": "Must have admin rights"})
    detail.select("A")
    detail.saveTopics(["cli"])
    await settle(detail)
    assert "admin or maintain" in detail.property("topicsError")
    assert repos.source.get_repo("A")["topics"] == ["old"]


async def test_invalid_topic_never_hits_network(env):
    _, _, detail, _ = env
    detail.select("A")
    with respx.mock(assert_all_called=False) as mock:
        route = mock.put(f"{API_URL}/repos/octo/alpha/topics")
        detail.saveTopics(["not valid!"])
        await settle(detail)
        assert not route.called
    assert "not a valid topic" in detail.property("topicsError")
    assert detail.checkTopic("Hyprland Plugin") == {"ok": True, "topic": "hyprland-plugin", "error": ""}


async def test_categories_toggle_filter_and_delete(env):
    _, repos, detail, _ = env
    L = repos.property("list")
    assert repos.createCategory("Work") == ""
    assert "already exists" in repos.createCategory("work")
    cid = repos.categoryIdAt(1)
    assert cid > 0 and repos.categoryIdAt(2) == -1
    detail.select("A")
    repos.toggleCategory("A", cid)
    assert detail.property("repo")["category_ids"] == [cid]
    assert repos.property("categories")[0]["count"] == 1
    assert repos.property("uncategorized") == 1
    L.setProperty("category", cid)
    assert L.property("count") == 1
    L.setProperty("category", 0)
    assert L.property("count") == 1 and L.get(0)["node_id"] == "B"
    L.setProperty("category", cid)
    repos.deleteCategory(cid)
    assert L.property("category") == -1  # filter cleared with the category
    assert repos.source.get_repo("A")["category_ids"] == []
    assert repos.property("categories") == []
