import json
import time

import httpx
import pytest
import respx

from repokase.api import health
from repokase.api.client import API_URL, GitHubClient
from repokase.cache import db, store
from repokase.models.repo_model import RepoFilterModel, RepoListModel

from test_cache import VIEWER, repo

NOW = time.time()
DAY = 86400


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def node(**kw):
    n = {
        "id": "A",
        "vulnerabilityAlerts": {"totalCount": 0},
        "pullRequests": {"nodes": []},
        "defaultBranchRef": {"target": {"statusCheckRollup": {"state": "SUCCESS"}}},
        "readme0": {"id": "x"},
    }
    n.update(kw)
    return n


def test_signals_from_node():
    s = health.signals_from_node(node(
        vulnerabilityAlerts={"totalCount": 2},
        pullRequests={"nodes": [{"updatedAt": iso(NOW - 40 * DAY)}, {"updatedAt": iso(NOW - 2 * DAY)}]},
        defaultBranchRef={"target": {"statusCheckRollup": {"state": "FAILURE"}}},
        readme0=None, readme2={"id": "y"},
    ), NOW)
    assert s == {"alerts": 2, "stale_prs": 1, "ci": "FAILURE", "has_readme": True}


def test_missing_access_is_unknown_not_zero():
    s = health.signals_from_node(node(vulnerabilityAlerts=None, defaultBranchRef=None, readme0=None), NOW)
    assert s["alerts"] is None and s["ci"] is None and s["has_readme"] is False


def test_compute_health_orders_by_severity():
    r = repo("A", "alpha", visibility="PUBLIC", license_spdx=None, pushed_at=iso(NOW - 400 * DAY))
    s = {"alerts": 3, "ci": "ERROR", "stale_prs": 2, "has_readme": False}
    h = health.compute_health(r, s, NOW)
    assert h["level"] == "critical"
    assert [f["key"] for f in h["flags"]] == ["security", "ci", "stale_prs", "readme", "license", "inactive"]
    assert h["flags"][0]["link"].endswith("/security/dependabot")
    assert "3 open Dependabot alerts" in h["flags"][0]["detail"]


def test_healthy_private_repo_without_license_is_ok():
    r = repo("A", "alpha", visibility="PRIVATE", license_spdx=None, pushed_at=iso(NOW - DAY))
    h = health.compute_health(r, {"alerts": 0, "ci": "SUCCESS", "stale_prs": 0, "has_readme": True}, NOW)
    assert h == {"level": "ok", "flags": []}


def test_archived_is_not_judged_and_no_signals_skips_readme():
    assert health.compute_health(repo("A", "a", is_archived=True), {"alerts": 9}, NOW)["archived"]
    h = health.compute_health(repo("A", "a", license_spdx="MIT", pushed_at=iso(NOW)), None, NOW)
    assert h["level"] == "ok"  # unknown signals must not claim "no README"


@pytest.fixture
async def api():
    async def token():
        return "t"

    async with httpx.AsyncClient() as http:
        yield GitHubClient(http, token)


@respx.mock
async def test_fetch_signals_batches_and_shrinks_on_502(api):
    ids = [f"R{i}" for i in range(30)]
    calls = []

    def respond(request):
        body = json.loads(request.content)
        batch = body["variables"]["ids"]
        calls.append(len(batch))
        if len(batch) > 20:
            return httpx.Response(502, text="<html>Bad Gateway</html>")
        return httpx.Response(200, json={"data": {"nodes": [node(id=i) for i in batch]}})

    respx.post(f"{API_URL}/graphql").mock(side_effect=respond)
    signals, warnings = await health.fetch_signals(api, ids)
    assert len(signals) == 30 and warnings == []
    assert calls[0] == 25 and calls[1] == 12  # halved after the 502, then continued
    assert "README" in health.HEALTH_QUERY and "statusCheckRollup" in health.HEALTH_QUERY


@respx.mock
async def test_server_error_message_is_plain(api):
    respx.post(f"{API_URL}/graphql").respond(503, text="<html>down</html>")
    with pytest.raises(Exception) as exc:
        await health.fetch_signals(api, ["R1"])
    assert "HTTP 503" in str(exc.value) and "<html>" not in str(exc.value)


def test_health_round_trips_through_cache_and_filters(qapp_core):
    conn = db.connect(":memory:")
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha"), repo("B", "beta"), repo("C", "gamma")])
    store.save_health(conn, aid, {
        "A": {"level": "serious", "flags": [{"key": "ci", "severity": "serious", "label": "CI failing", "detail": "", "link": ""}]},
        "B": {"level": "ok", "flags": []},
    }, {"A": {"ci": "FAILURE"}})
    repos = {r["node_id"]: r for r in store.load_repos(conn, aid)}
    assert repos["A"]["health"]["level"] == "serious"
    assert repos["C"]["health"]["level"] == "unknown"

    src = RepoListModel()
    src.set_repos(list(repos.values()))
    proxy = RepoFilterModel(src)
    proxy.setProperty("health", "attention")
    assert [proxy.get(i)["node_id"] for i in range(proxy.rowCount())] == ["A"]
    proxy.setProperty("health", "healthy")
    assert [proxy.get(i)["node_id"] for i in range(proxy.rowCount())] == ["B"]
    proxy.setProperty("health", "any")
    proxy.setProperty("sortKey", "health")
    assert [proxy.get(i)["node_id"] for i in range(proxy.rowCount())] == ["A", "B", "C"]
    conn.close()


@pytest.fixture(scope="module")
def qapp_core():
    from PySide6.QtCore import QCoreApplication

    return QCoreApplication.instance() or QCoreApplication([])
