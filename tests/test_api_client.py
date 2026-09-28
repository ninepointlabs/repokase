import httpx
import pytest
import respx

from repokase.api.client import API_URL, GitHubClient
from repokase.api.repos import fetch_viewer
from repokase.api.errors import (
    ApiError,
    AuthExpired,
    GraphQLError,
    NetworkError,
    NotFound,
    RateLimited,
    ScopeMissing,
    SsoRequired,
)


@pytest.fixture
async def api():
    async def token():
        return "gho_secret"

    seen = []
    async with httpx.AsyncClient() as http:
        client = GitHubClient(http, token, on_rate_limit=seen.append)
        client.seen = seen
        yield client


@respx.mock
async def test_viewer_sends_auth_and_tracks_rate_limit_and_scopes(api):
    route = respx.post(f"{API_URL}/graphql").respond(
        json={"data": {"viewer": {"login": "octo", "name": "Octo", "avatarUrl": "a", "url": "u"}}},
        headers={
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4990",
            "x-ratelimit-reset": "1700000000",
            "x-ratelimit-resource": "graphql",
            "x-oauth-scopes": "repo, read:user, workflow",
        },
    )
    viewer = await fetch_viewer(api)
    assert viewer["login"] == "octo"
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer gho_secret"
    assert req.headers["x-github-api-version"] == "2022-11-28"
    assert api.rate_limits["graphql"].remaining == 4990
    assert api.seen[-1].limit == 5000
    assert api.granted_scopes == {"repo", "read:user", "workflow"}


@respx.mock
async def test_401_is_auth_expired(api):
    respx.get(f"{API_URL}/user").respond(401, json={"message": "Bad credentials"})
    with pytest.raises(AuthExpired):
        await api.rest("GET", "/user")


@respx.mock
async def test_sso_header_is_surfaced_with_url(api):
    respx.get(f"{API_URL}/orgs/acme/repos").respond(
        403,
        json={"message": "Resource protected by organization SAML enforcement."},
        headers={"x-github-sso": "required; url=https://github.com/orgs/acme/sso?authorization_request=abc"},
    )
    with pytest.raises(SsoRequired) as exc:
        await api.rest("GET", "/orgs/acme/repos")
    assert exc.value.url == "https://github.com/orgs/acme/sso?authorization_request=abc"


@respx.mock
async def test_primary_rate_limit(api):
    respx.get(f"{API_URL}/user").respond(
        403,
        json={"message": "API rate limit exceeded"},
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000123"},
    )
    with pytest.raises(RateLimited) as exc:
        await api.rest("GET", "/user")
    assert exc.value.reset_at == 1700000123


@respx.mock
async def test_secondary_rate_limit_retry_after(api):
    respx.get(f"{API_URL}/user").respond(429, headers={"retry-after": "30"}, json={})
    with pytest.raises(RateLimited) as exc:
        await api.rest("GET", "/user")
    assert exc.value.reset_at is not None


@respx.mock
async def test_missing_scope_detected(api):
    respx.delete(f"{API_URL}/repos/o/r").respond(
        403,
        json={"message": "Must have admin rights to Repository."},
        headers={"x-accepted-oauth-scopes": "delete_repo", "x-oauth-scopes": "repo, workflow"},
    )
    with pytest.raises(ScopeMissing) as exc:
        await api.rest("DELETE", "/repos/o/r")
    assert exc.value.needed == {"delete_repo"}


@respx.mock
async def test_plain_403_and_404(api):
    respx.get(f"{API_URL}/a").respond(403, json={"message": "Forbidden thing"})
    respx.get(f"{API_URL}/b").respond(404, json={"message": "Not Found"})
    with pytest.raises(ApiError, match="Forbidden thing"):
        await api.rest("GET", "/a")
    with pytest.raises(NotFound):
        await api.rest("GET", "/b")


@respx.mock
async def test_network_error(api):
    respx.get(f"{API_URL}/user").mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(NetworkError):
        await api.rest("GET", "/user")


@respx.mock
async def test_graphql_partial_errors_are_returned_not_raised(api):
    respx.post(f"{API_URL}/graphql").respond(
        json={"data": {"viewer": {"login": "o"}}, "errors": [{"type": "FORBIDDEN", "message": "SAML"}]}
    )
    result = await api.graphql("query { viewer { login } }")
    assert result.data["viewer"]["login"] == "o"
    assert result.errors[0]["type"] == "FORBIDDEN"


@respx.mock
async def test_graphql_total_failure_and_rate_limit(api):
    respx.post(f"{API_URL}/graphql").mock(
        side_effect=[
            httpx.Response(200, json={"data": None, "errors": [{"message": "Something went wrong"}]}),
            httpx.Response(200, json={"errors": [{"type": "RATE_LIMITED", "message": "limit"}]}),
        ]
    )
    with pytest.raises(GraphQLError):
        await api.graphql("query { x }")
    with pytest.raises(RateLimited):
        await api.graphql("query { x }")


@respx.mock
async def test_204_returns_none(api):
    respx.put(f"{API_URL}/repos/o/r/topics").respond(204)
    assert await api.rest("PUT", "/repos/o/r/topics", json={"names": []}) is None
