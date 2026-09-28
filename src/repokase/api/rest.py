"""REST endpoints GraphQL does not cover well: Actions runs, topics."""

from __future__ import annotations

import re
from urllib.parse import quote

from .client import GitHubClient
from .errors import ApiError, NotFound

MAX_TOPICS = 20
_TOPIC = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")


class TopicError(ValueError):
    pass


def _repo_path(full_name: str) -> str:
    owner, _, name = full_name.partition("/")
    if not owner or not name:
        raise ValueError(f"Not an owner/name: {full_name!r}")
    return f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"


def normalize_topic(raw: str) -> str:
    """GitHub's rules: lowercase letters, digits, hyphens; start alphanumeric; <= 50 chars."""
    topic = "-".join((raw or "").strip().lower().split())
    if not _TOPIC.match(topic):
        raise TopicError(
            f'"{raw.strip()}" is not a valid topic. Use lowercase letters, numbers and hyphens '
            "(max 50 characters, starting with a letter or number)."
        )
    return topic


def validate_topics(topics: list[str]) -> list[str]:
    cleaned: list[str] = []
    for t in topics:
        n = normalize_topic(t)
        if n not in cleaned:
            cleaned.append(n)
    if len(cleaned) > MAX_TOPICS:
        raise TopicError(f"GitHub allows at most {MAX_TOPICS} topics per repository.")
    return cleaned


def normalize_run(run: dict) -> dict:
    return {
        "id": run["id"],
        "workflow_id": run.get("workflow_id"),
        "name": run.get("name") or run.get("display_title") or "Workflow",
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "head_branch": run.get("head_branch"),
        "run_number": run.get("run_number"),
        "created_at": run.get("created_at"),
        "html_url": run.get("html_url"),
    }


async def list_workflow_runs(client: GitHubClient, full_name: str, per_page: int = 10) -> list[dict]:
    try:
        body = await client.rest("GET", f"{_repo_path(full_name)}/actions/runs", params={"per_page": per_page})
    except NotFound:
        return []  # Actions disabled, or no workflows ever ran
    except ApiError as exc:
        if exc.status == 403 and "disabled" in str(exc).lower():
            return []
        raise
    return [normalize_run(r) for r in (body or {}).get("workflow_runs", [])]


async def replace_topics(client: GitHubClient, full_name: str, topics: list[str]) -> list[str]:
    names = validate_topics(topics)
    body = await client.rest("PUT", f"{_repo_path(full_name)}/topics", json={"names": names})
    return list((body or {}).get("names", names))
