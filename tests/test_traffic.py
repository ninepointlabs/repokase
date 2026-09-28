from datetime import date

import httpx
import pytest
import respx

from repokase import jobs
from repokase.api import traffic
from repokase.api.client import API_URL, GitHubClient
from repokase.cache import db, store
from repokase.controllers.traffic_controller import fill_days, summarize

from test_cache import VIEWER, repo


def views_body(days):
    return {"count": sum(c for _, c, _ in days), "uniques": 1,
            "views": [{"timestamp": f"{d}T00:00:00Z", "count": c, "uniques": u} for d, c, u in days]}


def clones_body(days):
    return {"count": 0, "uniques": 0,
            "clones": [{"timestamp": f"{d}T00:00:00Z", "count": c, "uniques": u} for d, c, u in days]}


@pytest.fixture
async def api():
    async def token():
        return "t"

    async with httpx.AsyncClient() as http:
        yield GitHubClient(http, token)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def mock_repo(name, views, clones, referrers=()):
    base = f"{API_URL}/repos/octo/{name}/traffic"
    respx.get(f"{base}/views").respond(json=views_body(views))
    respx.get(f"{base}/clones").respond(json=clones_body(clones))
    respx.get(f"{base}/popular/referrers").respond(json=[{"referrer": r, "count": 3, "uniques": 2} for r in referrers])


@respx.mock
async def test_fetch_repo_traffic_parses_days(api):
    mock_repo("alpha", [("2026-09-01", 5, 2)], [("2026-09-01", 1, 1)], ["github.com"])
    t = await traffic.fetch_repo_traffic(api, "octo/alpha")
    assert t.views == [{"day": "2026-09-01", "count": 5, "uniques": 2}]
    assert t.clones[0]["count"] == 1 and t.referrers[0]["referrer"] == "github.com"
    assert respx.calls[0].request.url.params["per"] == "day"


@respx.mock
async def test_snapshot_eligibility_and_forbidden(api):
    mock_repo("alpha", [("2026-09-01", 5, 2)], [])
    respx.get(f"{API_URL}/repos/octo/denied/traffic/views").respond(403, json={"message": "Must have push access"})
    respx.get(f"{API_URL}/repos/octo/denied/traffic/clones").respond(403, json={"message": "Must have push access"})
    respx.get(f"{API_URL}/repos/octo/denied/traffic/popular/referrers").respond(403, json={"message": "x"})
    repos = [
        repo("A", "alpha", viewer_permission="WRITE"),
        repo("D", "denied", viewer_permission="ADMIN"),  # GitHub still refuses: skipped, not failed
        repo("R", "reader", viewer_permission="READ"),  # never requested
        repo("Z", "zipped", viewer_permission="ADMIN", is_archived=True),  # never requested
    ]
    progress = []
    result = await traffic.snapshot(api, repos, lambda d, t: progress.append((d, t)))
    assert [t.full_name for t in result.traffic] == ["octo/alpha"]
    assert set(result.skipped) == {"octo/denied", "octo/reader", "octo/zipped"}
    assert result.failed == {}
    assert progress[-1] == (2, 2)
    assert not any("reader" in str(c.request.url) or "zipped" in str(c.request.url) for c in respx.calls)


@respx.mock
async def test_snapshot_job_persists_and_marks_due(api, conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha", viewer_permission="ADMIN")])
    assert jobs.traffic_due(conn, aid)
    mock_repo("alpha", [("2026-09-01", 5, 2), ("2026-09-02", 7, 3)], [("2026-09-02", 1, 1)], ["github.com"])
    await jobs.snapshot_traffic(api, conn, aid)
    assert [d["count"] for d in store.load_traffic(conn, "octo/alpha", "views")] == [5, 7]
    assert store.latest_referrers(conn, "octo/alpha")[0]["referrer"] == "github.com"
    assert not jobs.traffic_due(conn, aid)


def test_history_accumulates_beyond_14_days(conn):
    # Two snapshots with overlapping windows: history keeps the union and the
    # later value wins for the overlapping (revised) day.
    store.save_traffic(conn, "octo/a", "views", [{"day": "2026-08-01", "count": 1, "uniques": 1},
                                                 {"day": "2026-08-14", "count": 2, "uniques": 1}])
    store.save_traffic(conn, "octo/a", "views", [{"day": "2026-08-14", "count": 9, "uniques": 4},
                                                 {"day": "2026-08-28", "count": 3, "uniques": 1}])
    rows = store.load_traffic(conn, "octo/a", "views")
    assert [(r["day"], r["count"]) for r in rows] == [("2026-08-01", 1), ("2026-08-14", 9), ("2026-08-28", 3)]


def test_history_survives_repo_leaving_cache(conn):
    aid = store.save_account(conn, VIEWER)
    store.replace_repos(conn, aid, [repo("A", "alpha")])
    store.save_traffic(conn, "octo/alpha", "views", [{"day": "2026-08-01", "count": 1, "uniques": 1}])
    store.replace_repos(conn, aid, [])
    assert len(store.load_traffic(conn, "octo/alpha", "views")) == 1


def test_fill_days_and_summarize():
    rows = [{"day": "2026-09-01", "count": 2, "uniques": 1}, {"day": "2026-09-04", "count": 5, "uniques": 2}]
    filled = fill_days(rows, until=date(2026, 9, 5))
    assert [d["day"][-2:] for d in filled] == ["01", "02", "03", "04", "05"]
    assert [d["count"] for d in filled] == [2, 0, 0, 5, 0]
    assert fill_days([]) == []
    s = summarize(filled, filled)
    assert s["views14"] == 7 and s["viewsAll"] == 7 and s["since"] == "2026-09-01" and s["days"] == 5
