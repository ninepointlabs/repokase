"""GitHub Actions: workflows, workflow_dispatch inputs, re-run and cancel."""

from __future__ import annotations

import base64
import logging
from urllib.parse import quote

import yaml

from .client import GitHubClient
from .errors import ApiError, NotFound
from .rest import _repo_path

log = logging.getLogger(__name__)

INPUT_TYPES = {"string", "boolean", "choice", "number", "environment"}


def _on_block(doc: dict):
    # YAML 1.1 (PyYAML) reads the bare key `on` as boolean True.
    if not isinstance(doc, dict):
        return None
    return doc.get("on", doc.get(True))


def parse_dispatch(text: str) -> tuple[bool, list[dict]]:
    """Does this workflow accept workflow_dispatch, and with which inputs?"""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        log.info("Unparseable workflow file: %s", exc)
        return False, []
    on = _on_block(doc)
    if on == "workflow_dispatch":
        return True, []
    if isinstance(on, list):
        return "workflow_dispatch" in on, []
    if not isinstance(on, dict) or "workflow_dispatch" not in on:
        return False, []
    spec = on.get("workflow_dispatch") or {}
    raw_inputs = spec.get("inputs") if isinstance(spec, dict) else None
    inputs: list[dict] = []
    for name, cfg in (raw_inputs or {}).items():
        cfg = cfg if isinstance(cfg, dict) else {}
        kind = str(cfg.get("type") or "string")
        if kind not in INPUT_TYPES:
            kind = "string"
        default = cfg.get("default")
        options = [str(o) for o in (cfg.get("options") or [])] if kind == "choice" else []
        if kind == "boolean":
            default = "true" if default is True or str(default).lower() == "true" else "false"
        elif default is None:
            default = options[0] if options else ""
        inputs.append({
            "name": str(name),
            "description": str(cfg.get("description") or ""),
            "required": bool(cfg.get("required")),
            "type": kind,
            "default": str(default),
            "options": options,
        })
    return True, inputs


def validate_inputs(spec: list[dict], values: dict) -> dict[str, str]:
    """Returns the payload to send; raises ValueError with a readable message."""
    out: dict[str, str] = {}
    for inp in spec:
        name = inp["name"]
        value = str(values.get(name, inp.get("default", "")))
        if inp["type"] == "boolean":
            value = "true" if value.lower() in ("true", "1", "yes", "on") else "false"
        if inp["required"] and value.strip() == "":
            raise ValueError(f'"{name}" is required.')
        if inp["type"] == "choice" and inp["options"] and value not in inp["options"]:
            raise ValueError(f'"{name}" must be one of: {", ".join(inp["options"])}.')
        if inp["type"] == "number" and value.strip():
            try:
                float(value)
            except ValueError:
                raise ValueError(f'"{name}" must be a number.') from None
        out[name] = value
    return out


async def list_workflows(client: GitHubClient, full_name: str) -> list[dict]:
    try:
        body = await client.rest("GET", f"{_repo_path(full_name)}/actions/workflows", params={"per_page": 100})
    except NotFound:
        return []
    return [
        {"id": w["id"], "name": w.get("name") or w.get("path", ""), "path": w.get("path", ""), "state": w.get("state", "")}
        for w in (body or {}).get("workflows", [])
    ]


async def workflow_file(client: GitHubClient, full_name: str, path: str, ref: str | None) -> str:
    params = {"ref": ref} if ref else None
    body = await client.rest("GET", f"{_repo_path(full_name)}/contents/{quote(path)}", params=params)
    if not isinstance(body, dict) or body.get("encoding") != "base64":
        return ""
    return base64.b64decode(body.get("content", "")).decode("utf-8", errors="replace")


async def dispatchable_workflows(client: GitHubClient, full_name: str, ref: str | None) -> list[dict]:
    """Active workflows with a workflow_dispatch trigger, with their inputs."""
    out = []
    for wf in await list_workflows(client, full_name):
        # Dynamic workflows (Pages, Copilot, Dependabot) have no file to read.
        if wf["state"] != "active" or not wf["path"].startswith(".github/workflows/"):
            continue
        try:
            text = await workflow_file(client, full_name, wf["path"], ref)
        except ApiError as exc:
            log.info("Could not read %s: %s", wf["path"], exc)
            continue
        has, inputs = parse_dispatch(text)
        if has:
            out.append(dict(wf, inputs=inputs))
    return out


async def list_branches(client: GitHubClient, full_name: str) -> list[str]:
    body = await client.rest("GET", f"{_repo_path(full_name)}/branches", params={"per_page": 100})
    return [b["name"] for b in body or []]


async def dispatch(client: GitHubClient, full_name: str, workflow_id: int, ref: str, inputs: dict[str, str]) -> None:
    await client.rest(
        "POST",
        f"{_repo_path(full_name)}/actions/workflows/{int(workflow_id)}/dispatches",
        json={"ref": ref, "inputs": inputs},
    )


async def run_action(client: GitHubClient, full_name: str, run_id: int, action: str) -> None:
    endpoint = {"rerun": "rerun", "rerun-failed": "rerun-failed-jobs", "cancel": "cancel"}[action]
    await client.rest("POST", f"{_repo_path(full_name)}/actions/runs/{int(run_id)}/{endpoint}")
