import json

import httpx
import pytest
import respx

from repokase.api import rest
from repokase.api.client import API_URL, GitHubClient
from repokase.api.errors import ApiError


@pytest.fixture
async def api():
    async def token():
        return "t"

    async with httpx.AsyncClient() as http:
        yield GitHubClient(http, token)


@pytest.mark.parametrize(
    "raw, expected",
    [("CLI", "cli"), ("  omarchy ", "omarchy"), ("hyprland plugin", "hyprland-plugin"), ("a1-b2", "a1-b2")],
)
def test_normalize_topic(raw, expected):
    assert rest.normalize_topic(raw) == expected


@pytest.mark.parametrize("raw", ["", "-lead", "under_score", "c++", "x" * 51, "émoji"])
def test_invalid_topics(raw):
    with pytest.raises(rest.TopicError):
        rest.normalize_topic(raw)


def test_validate_topics_dedupes_and_caps():
    assert rest.validate_topics(["Go", "go", "cli"]) == ["go", "cli"]
    with pytest.raises(rest.TopicError, match="20"):
        rest.validate_topics([f"t{i}" for i in range(21)])


@respx.mock
async def test_list_runs_normalizes(api):
    route = respx.get(f"{API_URL}/repos/octo/app/actions/runs").respond(
        json={"workflow_runs": [{"id": 9, "name": "CI", "status": "completed", "conclusion": "failure",
                                 "event": "push", "head_branch": "main", "run_number": 12,
                                 "created_at": "2026-09-01T00:00:00Z", "html_url": "https://github.com/octo/app/actions/runs/9",
                                 "workflow_id": 3}]}
    )
    runs = await rest.list_workflow_runs(api, "octo/app")
    assert runs[0]["conclusion"] == "failure" and runs[0]["run_number"] == 12
    assert route.calls.last.request.url.params["per_page"] == "10"


@respx.mock
async def test_list_runs_404_means_none(api):
    respx.get(f"{API_URL}/repos/octo/app/actions/runs").respond(404, json={"message": "Not Found"})
    assert await rest.list_workflow_runs(api, "octo/app") == []


@respx.mock
async def test_replace_topics_puts_full_list(api):
    route = respx.put(f"{API_URL}/repos/octo/app/topics").respond(json={"names": ["cli", "go"]})
    assert await rest.replace_topics(api, "octo/app", ["CLI", "go"]) == ["cli", "go"]
    assert json.loads(route.calls.last.request.content) == {"names": ["cli", "go"]}


@respx.mock
async def test_replace_topics_rejects_invalid_before_network(api):
    route = respx.put(f"{API_URL}/repos/octo/app/topics").respond(json={})
    with pytest.raises(rest.TopicError):
        await rest.replace_topics(api, "octo/app", ["bad topic!"])
    assert not route.called


@respx.mock
async def test_replace_topics_forbidden(api):
    respx.put(f"{API_URL}/repos/octo/app/topics").respond(403, json={"message": "Must have admin rights"})
    with pytest.raises(ApiError) as exc:
        await rest.replace_topics(api, "octo/app", ["cli"])
    assert exc.value.status == 403


def test_repo_path_quotes_and_validates():
    assert rest._repo_path("octo/my.repo") == "/repos/octo/my.repo"
    with pytest.raises(ValueError):
        rest._repo_path("noslash")
