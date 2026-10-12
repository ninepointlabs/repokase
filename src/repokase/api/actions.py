"""Repository mutations: archive, visibility, description, transfer, delete."""

from __future__ import annotations

import re

from .client import GitHubClient
from .errors import GraphQLError, ScopeMissing
from .rest import _repo_path

DESCRIPTION_MAX = 350  # GitHub's limit for repository descriptions
VISIBILITIES = ("public", "private", "internal")
# GitHub logins: alphanumerics and single inner hyphens, at most 39 characters.
_LOGIN = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9]){0,38}")

_ARCHIVE = """
mutation Archive($id: ID!) {
  archiveRepository(input: {repositoryId: $id}) { repository { isArchived updatedAt } }
}
"""
_UNARCHIVE = """
mutation Unarchive($id: ID!) {
  unarchiveRepository(input: {repositoryId: $id}) { repository { isArchived updatedAt } }
}
"""


def _raise_mutation_errors(errors: list[dict], payload) -> None:
    if payload is not None and not errors:
        return
    for err in errors:
        if err.get("type") == "INSUFFICIENT_SCOPES":
            raise ScopeMissing({"repo"})
    raise GraphQLError(errors or [{"message": "GitHub did not apply the change."}])


async def set_archived(client: GitHubClient, node_id: str, archived: bool) -> dict:
    """GraphQL, because REST cannot unarchive. Returns changed cache fields."""
    field = "archiveRepository" if archived else "unarchiveRepository"
    result = await client.graphql(_ARCHIVE if archived else _UNARCHIVE, {"id": node_id})
    payload = result.data.get(field)
    _raise_mutation_errors(result.errors, payload)
    repo = payload["repository"]
    return {"is_archived": bool(repo["isArchived"]), "updated_at": repo.get("updatedAt")}


def _fields_from_rest(body: dict) -> dict:
    return {
        "description": body.get("description"),
        "visibility": (body.get("visibility") or ("private" if body.get("private") else "public")).upper(),
        "is_archived": bool(body.get("archived")),
        "updated_at": body.get("updated_at"),
        "pushed_at": body.get("pushed_at"),
        "stargazers": body.get("stargazers_count"),
        "watchers": body.get("subscribers_count"),
        "forks": body.get("forks_count"),
    }


async def update_repo(client: GitHubClient, full_name: str, **changes) -> dict:
    body = await client.rest("PATCH", _repo_path(full_name), json=changes)
    return {k: v for k, v in _fields_from_rest(body or {}).items() if v is not None or k == "description"}


async def set_visibility(client: GitHubClient, full_name: str, visibility: str) -> dict:
    visibility = visibility.lower()
    if visibility not in VISIBILITIES:
        raise ValueError(f"Unknown visibility {visibility!r}")
    return await update_repo(client, full_name, visibility=visibility)


async def set_description(client: GitHubClient, full_name: str, description: str) -> dict:
    text = " ".join((description or "").split())
    if len(text) > DESCRIPTION_MAX:
        raise ValueError(f"Descriptions are limited to {DESCRIPTION_MAX} characters.")
    return await update_repo(client, full_name, description=text)


async def delete_repo(client: GitHubClient, full_name: str) -> None:
    """Needs the delete_repo scope; GitHub answers 403 with X-Accepted-OAuth-Scopes otherwise."""
    await client.rest("DELETE", _repo_path(full_name))


async def transfer_repo(client: GitHubClient, full_name: str, new_owner: str) -> dict:
    """Ask GitHub to move the repo to `new_owner` (an organization or a user).

    Transfers to an organization the viewer can create repositories in happen
    right away; transfers to a user wait until that user accepts by email.
    Returns {"owner", "name", "full_name", "url"} as GitHub reports them, so the
    caller can tell which of the two happened.
    """
    new_owner = new_owner.strip()
    if not _LOGIN.fullmatch(new_owner):
        raise ValueError(f"{new_owner!r} is not a valid GitHub account or organization name.")
    if new_owner.lower() == full_name.partition("/")[0].lower():
        raise ValueError(f"{full_name} already belongs to {new_owner}.")
    body = await client.rest("POST", f"{_repo_path(full_name)}/transfer", json={"new_owner": new_owner}) or {}
    owner = (body.get("owner") or {}).get("login") or full_name.partition("/")[0]
    name = body.get("name") or full_name.partition("/")[2]
    return {
        "owner": owner,
        "name": name,
        "full_name": body.get("full_name") or f"{owner}/{name}",
        "url": body.get("html_url") or f"https://github.com/{owner}/{name}",
    }
