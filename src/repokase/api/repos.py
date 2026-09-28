"""Bulk repository fetch over GraphQL."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .client import GitHubClient
from .errors import ApiError, GraphQLError

log = logging.getLogger(__name__)

AFFILIATIONS = ("OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER")

REPOS_QUERY = """
query Repos($first: Int!, $after: String, $affiliations: [RepositoryAffiliation]) {
  rateLimit { limit remaining resetAt cost }
  viewer {
    repositories(first: $first, after: $after, ownerAffiliations: $affiliations,
                 orderBy: {field: NAME, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id databaseId name nameWithOwner description url visibility
        owner { login }
        isArchived isFork isTemplate isMirror
        primaryLanguage { name }
        stargazerCount forkCount
        watchers { totalCount }
        issues(states: OPEN) { totalCount }
        pullRequests(states: OPEN) { totalCount }
        defaultBranchRef { name }
        licenseInfo { spdxId }
        diskUsage viewerPermission
        pushedAt createdAt updatedAt
        repositoryTopics(first: 20) { nodes { topic { name } } }
      }
    }
  }
}
"""

VIEWER_QUERY = "query { viewer { databaseId login name avatarUrl url } }"


@dataclass
class FetchResult:
    repos: list[dict]
    total: int
    # Partial GraphQL errors, e.g. organizations that need SSO for this token.
    warnings: list[str] = field(default_factory=list)


def _count(node: dict | None, key: str) -> int:
    value = (node or {}).get(key) or {}
    return int(value.get("totalCount") or 0)


def normalize(node: dict) -> dict:
    """GraphQL repository node -> cache row dict (see store.REPO_COLUMNS)."""
    topics = [
        t["topic"]["name"]
        for t in ((node.get("repositoryTopics") or {}).get("nodes") or [])
        if t and t.get("topic")
    ]
    return {
        "node_id": node["id"],
        "database_id": node.get("databaseId"),
        "owner": (node.get("owner") or {}).get("login") or node["nameWithOwner"].split("/")[0],
        "name": node["name"],
        "full_name": node["nameWithOwner"],
        "description": node.get("description"),
        "url": node["url"],
        "visibility": node.get("visibility") or "PUBLIC",
        "is_archived": bool(node.get("isArchived")),
        "is_fork": bool(node.get("isFork")),
        "is_template": bool(node.get("isTemplate")),
        "is_mirror": bool(node.get("isMirror")),
        "primary_language": (node.get("primaryLanguage") or {}).get("name"),
        "stargazers": int(node.get("stargazerCount") or 0),
        "forks": int(node.get("forkCount") or 0),
        "watchers": _count(node, "watchers"),
        "open_issues": _count(node, "issues"),
        "open_prs": _count(node, "pullRequests"),
        "default_branch": (node.get("defaultBranchRef") or {}).get("name"),
        "license_spdx": (node.get("licenseInfo") or {}).get("spdxId"),
        "disk_kb": node.get("diskUsage"),
        "viewer_permission": node.get("viewerPermission"),
        "pushed_at": node.get("pushedAt"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "topics": topics,
    }


def _warning(err: dict) -> str:
    msg = err.get("message", "")
    if "SAML" in msg or "SSO" in msg:
        return msg or "An organization requires SSO authorization for this token."
    return msg or err.get("type", "Unknown GraphQL error")


async def fetch_viewer(client: GitHubClient) -> dict:
    return (await client.graphql(VIEWER_QUERY)).data["viewer"]


async def fetch_all_repos(
    client: GitHubClient,
    page_size: int = 100,
    on_progress: Callable[[int, int], None] | None = None,
) -> FetchResult:
    """Fetch every repo the viewer owns, collaborates on, or sees via orgs.

    GitHub can time out on large pages (502/504 or a "timedout" GraphQL
    error); the page size then halves and the same cursor is retried.
    """
    repos: list[dict] = []
    warnings: list[str] = []
    after: str | None = None
    total = 0
    size = page_size
    while True:
        variables = {"first": size, "after": after, "affiliations": list(AFFILIATIONS)}
        try:
            result = await client.graphql(REPOS_QUERY, variables)
        except (GraphQLError, ApiError) as exc:
            timed_out = getattr(exc, "status", None) in (502, 504) or "timeout" in str(exc).lower() or "timedout" in str(exc).lower()
            if timed_out and size > 10:
                size //= 2
                log.info("Repo page timed out; retrying with page size %d", size)
                continue
            raise
        conn = result.data["viewer"]["repositories"]
        total = conn["totalCount"]
        repos.extend(normalize(n) for n in conn["nodes"] if n)
        warnings.extend(_warning(e) for e in result.errors)
        if on_progress:
            on_progress(len(repos), total)
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]
    # Name order is stable across pages, but dedupe defensively (renames mid-fetch).
    unique = {r["node_id"]: r for r in repos}
    return FetchResult(repos=list(unique.values()), total=total, warnings=sorted(set(warnings)))
