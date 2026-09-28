"""Repository actions + in-app re-authorization, against mocked GitHub."""

import asyncio
import json

import httpx
import pytest
import respx
from PySide6.QtCore import QCoreApplication

from repokase.api import actions as api
from repokase.api.client import API_URL
from repokase.auth import device_flow
from repokase.auth.device_flow import TokenSet
from repokase.auth.token_store import MemoryTokenStore
from repokase.cache import db, store
from repokase.controllers.actions_controller import ActionsController
from repokase.controllers.auth_controller import AuthController
from repokase.controllers.repo_controller import AccountCache, RepoController

from test_cache import VIEWER, repo

GRAPHQL = f"{API_URL}/graphql"
REPO_URL = f"{API_URL}/repos/octo/alpha"


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
async def env(qapp):
    conn = db.connect(":memory:")
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [
        repo("A", "alpha", viewer_permission="ADMIN", description="old"),
        repo("F", "forky", viewer_permission="ADMIN", is_fork=True),
        repo("R", "readonly", viewer_permission="READ"),
    ])
    store.mark_sync(conn, aid, "repos")
    http = httpx.AsyncClient()
    tokens = MemoryTokenStore()
    auth = AuthController(store=tokens, http=http, accounts=AccountCache(conn))
    auth._token = TokenSet("gho_old", scope="read:user,repo,workflow")
    repos = RepoController(auth, conn)
    actions = ActionsController(auth, repos)
    auth._viewer = dict(VIEWER)
    auth._state = "signedIn"
    auth.signedIn.emit()
    events = {"done": [], "deleted": [], "scope": []}
    actions.done.connect(events["done"].append)
    actions.deleted.connect(events["deleted"].append)
    actions.scopeNeeded.connect(lambda s, n: events["scope"].append((s, n)))
    yield auth, repos, actions, conn, tokens, events
    await actions.settle()
    await http.aclose()
    conn.close()


def patched(**overrides):
    body = {"description": "old", "visibility": "public", "private": False, "archived": False,
            "updated_at": "2026-09-28T00:00:00Z", "stargazers_count": 0, "subscribers_count": 1, "forks_count": 0}
    body.update(overrides)
    return body


# ------------------------------------------------------------------ api layer
@respx.mock
async def test_archive_uses_graphql_mutation(env):
    auth, repos, actions, conn, _, events = env
    route = respx.post(GRAPHQL).respond(json={"data": {"archiveRepository": {"repository": {"isArchived": True, "updatedAt": "x"}}}})
    actions.setArchived("A", True)
    await actions.settle()
    sent = json.loads(route.calls.last.request.content)
    assert "archiveRepository" in sent["query"] and sent["variables"] == {"id": "A"}
    assert repos.source.get_repo("A")["is_archived"] is True
    cached = {r["node_id"]: r for r in store.load_repos(conn, 42)}
    assert cached["A"]["is_archived"] is True
    assert events["done"] == ["Archived octo/alpha"]


@respx.mock
async def test_unarchive_and_mutation_error(env):
    _, repos, actions, _, _, _ = env
    respx.post(GRAPHQL).mock(side_effect=[
        httpx.Response(200, json={"data": {"unarchiveRepository": None},
                                  "errors": [{"type": "FORBIDDEN", "message": "Must have admin rights"}]}),
    ])
    actions.setArchived("A", False)
    await actions.settle()
    assert "admin rights" in actions.property("error")
    assert actions.property("busy") is False


@respx.mock
async def test_visibility_patch_updates_model(env):
    _, repos, actions, _, _, events = env
    route = respx.patch(REPO_URL).respond(json=patched(visibility="private", private=True))
    actions.setVisibility("A", "private")
    await actions.settle()
    assert json.loads(route.calls.last.request.content) == {"visibility": "private"}
    assert repos.source.get_repo("A")["visibility"] == "PRIVATE"
    assert events["done"] == ["octo/alpha is now private"]


@respx.mock
async def test_description_trims_and_saves(env):
    _, repos, actions, conn, _, _ = env
    route = respx.patch(REPO_URL).respond(json=patched(description="New words"))
    actions.setDescription("A", "  New \n words ")
    await actions.settle()
    assert json.loads(route.calls.last.request.content) == {"description": "New words"}
    assert repos.source.get_repo("A")["description"] == "New words"
    assert [r for r in store.load_repos(conn, 42) if r["node_id"] == "A"][0]["description"] == "New words"


async def test_description_too_long_never_sent(env):
    _, _, actions, _, _, _ = env
    with respx.mock(assert_all_called=False) as mock:
        route = mock.patch(REPO_URL)
        actions.setDescription("A", "x" * 351)
        await actions.settle()
        assert not route.called
    assert "350" in actions.property("error")


@respx.mock
async def test_sso_error_exposes_authorize_link(env):
    _, _, actions, _, _, _ = env
    respx.patch(REPO_URL).respond(403, json={"message": "SAML"},
                                  headers={"x-github-sso": "required; url=https://github.com/orgs/o/sso?x=1"})
    actions.setDescription("A", "hi")
    await actions.settle()
    assert actions.property("errorUrl") == "https://github.com/orgs/o/sso?x=1"
    actions.clearError()
    assert actions.property("error") == "" and actions.property("errorUrl") == ""


def test_capabilities(env):
    _, _, actions, _, _, _ = env
    a = actions.capabilities("A")
    assert a["archive"] and a["visibility"] and a["delete"] and a["description"]
    assert a["hasDeleteScope"] is False
    f = actions.capabilities("F")
    assert not f["visibility"] and "fork" in f["visibilityWhy"]
    r = actions.capabilities("R")
    assert not (r["archive"] or r["delete"] or r["description"])


# ------------------------------------------------------------------- delete
async def test_delete_mismatch_is_refused_locally(env):
    auth, repos, actions, _, _, events = env
    auth.api.granted_scopes = {"repo", "delete_repo"}
    with respx.mock(assert_all_called=False) as mock:
        route = mock.delete(REPO_URL)
        actions.deleteRepo("A", "octo/alph")
        await actions.settle()
        assert not route.called
    assert "does not match" in actions.property("error")
    assert repos.source.get_repo("A") is not None


async def test_delete_without_scope_asks_for_reauth(env):
    _, repos, actions, _, _, events = env
    with respx.mock(assert_all_called=False) as mock:
        route = mock.delete(REPO_URL)
        actions.deleteRepo("A", "octo/alpha")
        await actions.settle()
        assert not route.called
    assert events["scope"] == [("delete_repo", "A")]


@respx.mock
async def test_delete_success_removes_everywhere(env):
    auth, repos, actions, conn, _, events = env
    auth.api.granted_scopes = {"repo", "delete_repo"}
    store.replace_workflow_runs(conn, 42, "A", [{"id": 1, "created_at": "x"}])
    respx.delete(REPO_URL).respond(204)
    actions.deleteRepo("A", " octo/alpha ")
    await actions.settle()
    assert repos.source.get_repo("A") is None
    assert "A" not in [r["node_id"] for r in store.load_repos(conn, 42)]
    assert conn.execute("SELECT COUNT(*) FROM workflow_run").fetchone()[0] == 0
    assert events["deleted"] == ["A"] and events["done"] == ["Deleted octo/alpha"]


@respx.mock
async def test_delete_scope_rejected_by_github(env):
    auth, repos, actions, _, _, _ = env
    auth.api.granted_scopes = {"repo", "delete_repo"}  # stale belief
    respx.delete(REPO_URL).respond(403, json={"message": "Must have admin rights to Repository."},
                                   headers={"x-accepted-oauth-scopes": "delete_repo", "x-oauth-scopes": "repo"})
    actions.deleteRepo("A", "octo/alpha")
    await actions.settle()
    assert "more GitHub permission" in actions.property("error")
    assert repos.source.get_repo("A") is not None


# ----------------------------------------------------------- re-authorize
def device_routes(token_body):
    respx.post(device_flow.DEVICE_CODE_URL).respond(json={
        "device_code": "d", "user_code": "WXYZ-1234", "verification_uri": "https://github.com/login/device",
        "expires_in": 900, "interval": 1})
    return respx.post(device_flow.TOKEN_URL).respond(json=token_body)


@pytest.fixture
def fast_poll(monkeypatch):
    async def no_wait(_seconds):
        await asyncio.sleep(0)

    monkeypatch.setattr(device_flow, "_sleep", no_wait)


async def reauth(auth):
    auth.requestScope("delete_repo", "why")
    await asyncio.gather(auth._reauth_task, return_exceptions=True)


@respx.mock
async def test_reauth_success_swaps_token_and_keeps_session(env, fast_poll):
    auth, _, _, _, tokens, _ = env
    code_route = device_routes({"access_token": "gho_new", "scope": "delete_repo,read:user,repo,workflow"})
    respx.post(GRAPHQL).respond(json={"data": {"viewer": dict(VIEWER)}},
                                headers={"x-oauth-scopes": "delete_repo, read:user, repo, workflow"})
    fired = []
    auth.reauthorized.connect(lambda: fired.append(1))
    await reauth(auth)
    body = respx.calls[0].request.content.decode()
    assert "scope=delete_repo+read%3Auser+repo+workflow" in body
    assert fired == [1]
    assert auth._token.access_token == "gho_new" and tokens.load().access_token == "gho_new"
    assert auth.hasScope("delete_repo")
    assert auth.property("state") == "signedIn" and auth.property("reauthState") == ""


@respx.mock
async def test_reauth_as_other_account_is_rejected(env, fast_poll):
    auth, _, _, _, tokens, _ = env
    device_routes({"access_token": "gho_other", "scope": "delete_repo,repo"})
    respx.post(GRAPHQL).respond(json={"data": {"viewer": {"databaseId": 7, "login": "someone"}}})
    await reauth(auth)
    assert auth.property("reauthState") == "error"
    assert "@someone" in auth.property("reauthError")
    assert auth._token.access_token == "gho_old" and tokens.load() is None


@respx.mock
async def test_reauth_scope_not_granted(env, fast_poll):
    auth, _, _, _, _, _ = env
    device_routes({"access_token": "gho_x", "scope": "repo"})
    respx.post(GRAPHQL).respond(json={"data": {"viewer": dict(VIEWER)}}, headers={"x-oauth-scopes": "repo"})
    await reauth(auth)
    assert "did not grant" in auth.property("reauthError")
    assert auth._token.access_token == "gho_old"


@respx.mock
async def test_reauth_denied_then_cancel(env, fast_poll):
    auth, _, _, _, _, _ = env
    device_routes({"error": "access_denied"})
    await reauth(auth)
    assert auth.property("reauthState") == "error" and "cancelled" in auth.property("reauthError")
    auth.cancelReauth()
    assert auth.property("reauthState") == "" and auth.property("state") == "signedIn"


def test_api_rejects_unknown_visibility():
    with pytest.raises(ValueError):
        asyncio.run(api.set_visibility(None, "o/r", "secret"))


# ------------------------------------------------------------------- bulk
def test_marks_range_hidden_and_clear(env):
    _, repos, _, _, _, _ = env
    L = repos.property("list")
    L.setProperty("sortKey", "name")
    repos.markRange(0, 1)
    assert repos.property("markedCount") == 2
    assert repos.source.get_repo(repos.property("markedIds")[0])["marked"] is True
    L.setProperty("search", "readonly")
    assert repos.property("hiddenMarked") == 2
    L.setProperty("search", "")
    repos.toggleMark("R")
    assert repos.property("markedCount") == 3
    repos.clearMarks()
    assert repos.property("markedCount") == 0
    assert not any(r.get("marked") for r in repos.source.repos())


def test_marks_survive_reload_and_prune_deleted(env):
    auth, repos, _, conn, _, _ = env
    repos.setMarked("A", True)
    repos.setMarked("R", True)
    store.replace_repos(conn, 42, [r for r in store.load_repos(conn, 42) if r["node_id"] != "R"])
    repos._load_cache(42)
    assert repos.property("markedIds") == ["A"]
    assert repos.source.get_repo("A")["marked"] is True


def test_bulk_category(env):
    _, repos, _, _, _, _ = env
    repos.createCategory("Work")
    cid = repos.categoryIdAt(1)
    for n in ("A", "F"):
        repos.setMarked(n, True)
    repos.setCategoryForMarked(cid, True)
    assert repos.property("categories")[0]["count"] == 2
    assert repos.source.get_repo("F")["category_ids"] == [cid]
    repos.setCategoryForMarked(cid, False)
    assert repos.property("categories")[0]["count"] == 0


@respx.mock
async def test_bulk_archive_skips_and_reports_failures(env):
    _, repos, actions, _, _, events = env
    store_repo = repos.source.get_repo
    repos.source.update_repo("F", is_archived=True)  # already archived: skipped
    calls = []

    def respond(request):
        rid = json.loads(request.content)["variables"]["id"]
        calls.append(rid)
        if rid == "A":
            return httpx.Response(200, json={"data": {"archiveRepository": {"repository": {"isArchived": True, "updatedAt": "x"}}}})
        return httpx.Response(200, json={"data": {"archiveRepository": None}, "errors": [{"message": "boom"}]})

    respx.post(GRAPHQL).mock(side_effect=respond)
    repos.source._repos.append(dict(store_repo("A"), node_id="B", full_name="octo/bravo", name="bravo", is_archived=False))
    repos.source._row_of["B"] = len(repos.source._repos) - 1
    for n in ("A", "B", "F", "R"):
        repos.setMarked(n, True)
    actions.bulkArchive(["A", "B", "F", "R"], True)
    await actions.settle()
    assert calls == ["A", "B"]  # F already archived, R not admin: never sent
    assert store_repo("A")["is_archived"] is True
    assert events["done"][-1] == "Archived 1 of 4 · 2 skipped (already archived or no admin access)"
    assert "octo/bravo: boom" in actions.property("error")
    assert repos.property("markedCount") == 0  # marks cleared after a bulk run
