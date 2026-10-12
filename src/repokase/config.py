"""Static configuration and XDG paths."""

import os
from pathlib import Path

# Public identifier of the Repokase GitHub OAuth App. Client IDs are not secret;
# no client secret is used anywhere (device flow only).
DEFAULT_GITHUB_CLIENT_ID = "Ov23liXiZkM9OOZhZdBY"

# Minimal scopes requested at first login. delete_repo is only requested,
# via re-authorization, the first time the user deletes a repository.
# read:org is needed to see organization memberships: without it GitHub
# silently returns no ORGANIZATION_MEMBER repositories. Tokens from before
# 0.2.1 lack it; the app offers in-place re-authorization (ORG_SCOPE).
BASE_SCOPES = ("read:org", "read:user", "repo", "workflow")
DELETE_SCOPE = "delete_repo"
ORG_SCOPE = "read:org"


def github_client_id() -> str:
    return os.environ.get("GITHUB_CLIENT_ID") or DEFAULT_GITHUB_CLIENT_ID


def app_access_url() -> str:
    """Where the user grants (or requests) Repokase access to their organizations."""
    return f"https://github.com/settings/connections/applications/{github_client_id()}"


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / default


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "repokase"


def state_home() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")
