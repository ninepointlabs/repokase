import json

import httpx
import pytest
import respx

from repokase.api import repos
from repokase.api.client import API_URL, GitHubClient
from repokase.api.errors import GraphQLError


def node(i, **kw):
    n = {
        "id": f"R_{i}",
        "databaseId": i,
        "name": f"repo{i}",
        "nameWithOwner": f"octo/repo{i}",
        "description": "d",
        "url": f"https://github.com/octo/repo{i}",
        "visibility": "PRIVATE",
        "owner": {"login": "octo"},
        "isArchived": False,
        "isFork": True,
        "isTemplate": False,
        "isMirror": False,
        "primaryLanguage": {"name": "Go"},
        "stargazerCount": 5,
        "forkCount": 2,
        "watchers": {"totalCount": 3},
        "issues": {"totalCount": 4},
        "pullRequests": {"totalCount": 1},
        "defaultBranchRef": {"name": "main"},
        "licenseInfo": {"spdxId": "MIT"},
        "diskUsage": 120,
        "viewerPermission": "ADMIN",
        "pushedAt": "2026-09-01T00:00:00Z",
        "createdAt": "2020-01-01T00:00:00Z",
        "updatedAt": "2026-09-01T00:00:00Z",
        "repositoryTopics": {"nodes": [{"topic": {"name": "cli"}}]},
    }
    n.update(kw)
    return n


def page(nodes, has_next, cursor=None, total=None):
    return {
        "data": {
            "rateLimit": {"limit": 5000, "remaining": 4999, "resetAt": "x", "cost": 1},
            "viewer": {
                "repositories": {
                    "totalCount": total if total is not None else len(nodes),
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    "nodes": nodes,
                }
            },
        }
    }


@pytest.fixture
async def api():
    async def token():
        return "t"

    async with httpx.AsyncClient() as http:
        yield GitHubClient(http, token)


def test_normalize_maps_every_field():
    r = repos.normalize(node(1))
    assert r["node_id"] == "R_1" and r["full_name"] == "octo/repo1" and r["owner"] == "octo"
    assert r["visibility"] == "PRIVATE" and r["is_fork"] is True
    assert (r["stargazers"], r["forks"], r["watchers"], r["open_issues"], r["open_prs"]) == (5, 2, 3, 4, 1)
    assert r["primary_language"] == "Go" and r["license_spdx"] == "MIT" and r["default_branch"] == "main"
    assert r["topics"] == ["cli"]


def test_normalize_tolerates_nulls():
    r = repos.normalize(
        node(2, primaryLanguage=None, licenseInfo=None, defaultBranchRef=None, repositoryTopics=None,
             watchers=None, description=None, pushedAt=None)
    )
    assert r["primary_language"] is None and r["license_spdx"] is None and r["topics"] == []
    assert r["watchers"] == 0 and r["pushed_at"] is None


@respx.mock
async def test_fetch_all_paginates(api):
    route = respx.post(f"{API_URL}/graphql").mock(
        side_effect=[
            httpx.Response(200, json=page([node(1), node(2)], True, "c1", total=3)),
            httpx.Response(200, json=page([node(3)], False, None, total=3)),
        ]
    )
    progress = []
    result = await repos.fetch_all_repos(api, on_progress=lambda d, t: progress.append((d, t)))
    assert [r["node_id"] for r in result.repos] == ["R_1", "R_2", "R_3"]
    assert result.total == 3 and progress == [(2, 3), (3, 3)]
    second = json.loads(route.calls[1].request.content)
    assert second["variables"]["after"] == "c1"
    assert second["variables"]["affiliations"] == ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]


@respx.mock
async def test_timeout_halves_page_size_and_retries_same_cursor(api):
    route = respx.post(f"{API_URL}/graphql").mock(
        side_effect=[
            httpx.Response(502, json={"message": "Server Error"}),
            httpx.Response(200, json=page([node(1)], False)),
        ]
    )
    result = await repos.fetch_all_repos(api, page_size=100)
    assert len(result.repos) == 1
    sizes = [json.loads(c.request.content)["variables"]["first"] for c in route.calls]
    assert sizes == [100, 50]


@respx.mock
async def test_partial_sso_errors_become_warnings(api):
    body = page([node(1), None], False)
    body["errors"] = [{"type": "FORBIDDEN", "message": "Resource protected by organization SAML enforcement."}]
    respx.post(f"{API_URL}/graphql").respond(json=body)
    result = await repos.fetch_all_repos(api)
    assert len(result.repos) == 1
    assert "SAML" in result.warnings[0]


@respx.mock
async def test_hard_failure_raises(api):
    respx.post(f"{API_URL}/graphql").respond(json={"data": None, "errors": [{"message": "Bad query"}]})
    with pytest.raises(GraphQLError):
        await repos.fetch_all_repos(api)
