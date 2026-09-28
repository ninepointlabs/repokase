import asyncio
import base64
import json

import httpx
import pytest
import respx
from PySide6.QtCore import QCoreApplication

from repokase.api import workflows as wf
from repokase.api.client import API_URL, GitHubClient
from repokase.auth.device_flow import TokenSet
from repokase.auth.token_store import MemoryTokenStore
from repokase.cache import db, store
from repokase.controllers.auth_controller import AuthController
from repokase.controllers.detail_controller import DetailController
from repokase.controllers.repo_controller import AccountCache, RepoController
from repokase.controllers.workflows_controller import WorkflowsController

from test_cache import VIEWER, repo

BASE = f"{API_URL}/repos/octo/alpha"

FULL = """
name: Build
on:
  push:
  workflow_dispatch:
    inputs:
      packages:
        description: Space-separated packages
        required: true
      level:
        type: choice
        options: [low, high]
        default: high
      dry_run:
        type: boolean
        default: true
      count:
        type: number
      weird:
        type: mystery
"""


# -------------------------------------------------------------------- parse
def test_parse_full_inputs():
    has, inputs = wf.parse_dispatch(FULL)
    assert has
    by = {i["name"]: i for i in inputs}
    assert by["packages"]["required"] and by["packages"]["type"] == "string"
    assert by["level"]["options"] == ["low", "high"] and by["level"]["default"] == "high"
    assert by["dry_run"]["type"] == "boolean" and by["dry_run"]["default"] == "true"
    assert by["count"]["type"] == "number"
    assert by["weird"]["type"] == "string"  # unknown types degrade to text


@pytest.mark.parametrize(
    "text, has",
    [
        ("on: workflow_dispatch\n", True),
        ("on: [push, workflow_dispatch]\n", True),
        ("on:\n  workflow_dispatch:\n", True),
        ("'on': {workflow_dispatch: {}}\n", True),
        ("on: push\n", False),
        ("on:\n  schedule:\n    - cron: '0 0 * * *'\n", False),
        ("not: [valid", False),
        ("", False),
    ],
)
def test_parse_trigger_forms(text, has):
    assert wf.parse_dispatch(text)[0] is has


def test_choice_without_default_uses_first_option():
    _, inputs = wf.parse_dispatch("on:\n  workflow_dispatch:\n    inputs:\n      env:\n        type: choice\n        options: [staging, prod]\n")
    assert inputs[0]["default"] == "staging"


def test_validate_inputs():
    _, spec = wf.parse_dispatch(FULL)
    ok = wf.validate_inputs(spec, {"packages": "a b", "dry_run": "false", "count": "3"})
    assert ok == {"packages": "a b", "level": "high", "dry_run": "false", "count": "3", "weird": ""}
    with pytest.raises(ValueError, match="packages"):
        wf.validate_inputs(spec, {"packages": "  "})
    with pytest.raises(ValueError, match="one of"):
        wf.validate_inputs(spec, {"packages": "x", "level": "extreme"})
    with pytest.raises(ValueError, match="number"):
        wf.validate_inputs(spec, {"packages": "x", "count": "many"})


# ---------------------------------------------------------------------- api
@pytest.fixture
async def api():
    async def token():
        return "t"

    async with httpx.AsyncClient() as http:
        yield GitHubClient(http, token)


def file_body(text):
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


@respx.mock
async def test_dispatchable_skips_dynamic_disabled_and_non_dispatch(api):
    respx.get(f"{BASE}/actions/workflows").respond(json={"workflows": [
        {"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active"},
        {"id": 2, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
        {"id": 3, "name": "Old", "path": ".github/workflows/old.yml", "state": "disabled_manually"},
        {"id": 4, "name": "Pages", "path": "dynamic/pages/pages-build-deployment", "state": "active"},
    ]})
    respx.get(f"{BASE}/contents/.github/workflows/build.yml").respond(json=file_body(FULL))
    respx.get(f"{BASE}/contents/.github/workflows/ci.yml").respond(json=file_body("on: push\n"))
    found = await wf.dispatchable_workflows(api, "octo/alpha", "main")
    assert [w["id"] for w in found] == [1]
    assert len(found[0]["inputs"]) == 5
    requested = [str(c.request.url) for c in respx.calls]
    assert not any("old.yml" in u or "dynamic" in u for u in requested)
    assert "ref=main" in requested[1]


# --------------------------------------------------------------- controller
@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
async def env(qapp):
    conn = db.connect(":memory:")
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [
        repo("A", "alpha", viewer_permission="WRITE", default_branch="main"),
        repo("R", "reader", viewer_permission="READ"),
    ])
    store.mark_sync(conn, aid, "repos")
    http = httpx.AsyncClient()
    auth = AuthController(store=MemoryTokenStore(), http=http, accounts=AccountCache(conn))
    auth._token = TokenSet("t")
    repos = RepoController(auth, conn)
    detail = DetailController(auth, repos)
    flows = WorkflowsController(auth, repos, detail)
    auth._viewer = dict(VIEWER)
    auth._state = "signedIn"
    auth.signedIn.emit()
    done = []
    flows.done.connect(done.append)
    yield flows, done
    flows._reload.stop()
    detail._debounce.stop()
    await flows.settle()
    await http.aclose()
    conn.close()


def test_can_run_requires_write(env):
    flows, _ = env
    assert flows.canRun("A") and not flows.canRun("R")


@pytest.mark.parametrize("action, endpoint", [("rerun", "rerun"), ("rerun-failed", "rerun-failed-jobs"), ("cancel", "cancel")])
@respx.mock
async def test_run_actions(env, action, endpoint):
    flows, done = env
    route = respx.post(f"{BASE}/actions/runs/77/{endpoint}").respond(201, json={})
    flows.runAction("A", 77, action)
    await flows.settle()
    assert route.called and done and flows.property("busy") is False
    assert flows._reload.isActive()  # runs list refreshes shortly after


@respx.mock
async def test_load_and_dispatch(env):
    flows, done = env
    respx.get(f"{BASE}/actions/workflows").respond(json={"workflows": [
        {"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active"}]})
    respx.get(f"{BASE}/contents/.github/workflows/build.yml").respond(json=file_body(FULL))
    respx.get(f"{BASE}/branches").respond(json=[{"name": "dev"}, {"name": "main"}])
    flows.loadDispatch("A")
    await flows.settle()
    assert flows.property("branches") == ["main", "dev"]  # default branch first
    assert flows.property("loadedFor") == "A"

    # Missing required input: refused locally.
    flows.dispatch("A", 1, "main", {})
    assert "required" in flows.property("error")

    route = respx.post(f"{BASE}/actions/workflows/1/dispatches").respond(204)
    flows.dispatch("A", 1, "dev", {"packages": "foo", "dry_run": "true"})
    await flows.settle()
    body = json.loads(route.calls.last.request.content)
    assert body["ref"] == "dev" and body["inputs"]["packages"] == "foo" and body["inputs"]["dry_run"] == "true"
    assert done == ["Started Build on dev"]


@respx.mock
async def test_dispatch_forbidden_is_explained(env):
    flows, _ = env
    respx.get(f"{BASE}/actions/workflows").respond(json={"workflows": [
        {"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active"}]})
    respx.get(f"{BASE}/contents/.github/workflows/build.yml").respond(json=file_body("on: workflow_dispatch\n"))
    respx.get(f"{BASE}/branches").respond(json=[{"name": "main"}])
    flows.loadDispatch("A")
    await flows.settle()
    respx.post(f"{BASE}/actions/workflows/1/dispatches").respond(403, json={"message": "Resource not accessible"})
    flows.dispatch("A", 1, "main", {})
    await flows.settle()
    assert flows.property("error") == "GitHub refused: you need write access to start the workflow."
