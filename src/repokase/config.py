"""Static configuration and XDG paths."""

import os
from pathlib import Path

# Public identifier of the Repokase GitHub OAuth App. Client IDs are not secret;
# no client secret is used anywhere (device flow only).
DEFAULT_GITHUB_CLIENT_ID = "Ov23liXiZkM9OOZhZdBY"

# Minimal scopes requested at first login. delete_repo is only requested,
# via re-authorization, the first time the user deletes a repository.
BASE_SCOPES = ("read:user", "repo", "workflow")
DELETE_SCOPE = "delete_repo"


def github_client_id() -> str:
    return os.environ.get("GITHUB_CLIENT_ID") or DEFAULT_GITHUB_CLIENT_ID


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / default


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "repokase"


def state_home() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")
