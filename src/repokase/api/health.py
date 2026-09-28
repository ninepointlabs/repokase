"""Repository health: bulk signals over GraphQL, scored by a pure function."""

from __future__ import annotations

import time
from datetime import datetime

from .client import GitHubClient
from .errors import ApiError

BATCH = 25
STALE_PR_DAYS = 30
INACTIVE_DAYS = 180
README_NAMES = ("README.md", "README", "readme.md", "README.rst")

# Severity ranks: the list and filters sort by the worst flag.
SEVERITY = {"ok": 0, "info": 1, "warning": 2, "serious": 3, "critical": 4}

_readme_fields = "\n".join(
    f'    readme{i}: object(expression: "HEAD:{name}") {{ id }}' for i, name in enumerate(README_NAMES)
)
HEALTH_QUERY = f"""
query Health($ids: [ID!]!) {{
  rateLimit {{ cost remaining resetAt }}
  nodes(ids: $ids) {{
    ... on Repository {{
      id
      vulnerabilityAlerts(states: OPEN, first: 1) {{ totalCount }}
      pullRequests(states: OPEN, first: 50, orderBy: {{field: UPDATED_AT, direction: ASC}}) {{ nodes {{ updatedAt }} }}
      defaultBranchRef {{ target {{ ... on Commit {{ statusCheckRollup {{ state }} }} }} }}
{_readme_fields}
    }}
  }}
}}
"""


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def signals_from_node(node: dict, now: float | None = None) -> dict:
    now = now or time.time()
    alerts = node.get("vulnerabilityAlerts")
    prs = ((node.get("pullRequests") or {}).get("nodes")) or []
    stale_cut = now - STALE_PR_DAYS * 86400
    target = ((node.get("defaultBranchRef") or {}).get("target")) or {}
    rollup = target.get("statusCheckRollup") or {}
    return {
        # None = GitHub didn't tell us (no access), which is not the same as 0.
        "alerts": alerts.get("totalCount") if isinstance(alerts, dict) else None,
        "stale_prs": sum(1 for p in prs if (_ts(p.get("updatedAt")) or now) < stale_cut),
        "ci": rollup.get("state"),
        "has_readme": any(node.get(f"readme{i}") for i in range(len(README_NAMES))),
    }


def compute_health(repo: dict, signals: dict | None, now: float | None = None) -> dict:
    """Flags + overall level for one repo. Archived repos are not judged."""
    now = now or time.time()
    if repo.get("is_archived"):
        return {"level": "ok", "flags": [], "archived": True}
    flags: list[dict] = []

    def flag(key, severity, label, detail, link=""):
        flags.append({"key": key, "severity": severity, "label": label, "detail": detail, "link": link})

    s = signals or {}
    url = repo.get("url", "")
    if s.get("alerts"):
        n = s["alerts"]
        flag("security", "critical", "security", f"{n} open Dependabot alert{'s' if n != 1 else ''}", url + "/security/dependabot")
    if s.get("ci") in ("FAILURE", "ERROR"):
        flag("ci", "serious", "CI failing", "The latest commit on the default branch has failing checks.", url + "/actions")
    if s.get("stale_prs"):
        n = s["stale_prs"]
        flag("stale_prs", "warning", "stale PRs",
             f"{n} open pull request{'s' if n != 1 else ''} untouched for {STALE_PR_DAYS}+ days", url + "/pulls")
    if signals is not None and not s.get("has_readme"):
        flag("readme", "warning", "no README", "No README at the repository root.")
    if repo.get("visibility") == "PUBLIC" and not repo.get("license_spdx"):
        flag("license", "warning", "no license", "Public but unlicensed: others can't legally reuse the code.")
    pushed = _ts(repo.get("pushed_at"))
    if pushed and now - pushed > INACTIVE_DAYS * 86400:
        months = int((now - pushed) / (30 * 86400))
        flag("inactive", "info", "inactive", f"No pushes for {months} months. Archive it if it's done.")
    flags.sort(key=lambda f: -SEVERITY[f["severity"]])
    level = flags[0]["severity"] if flags else "ok"
    return {"level": level, "flags": flags}


async def fetch_signals(client: GitHubClient, node_ids: list[str]) -> tuple[dict[str, dict], list[str]]:
    """node_id -> signals, plus partial-error messages (e.g. SSO orgs)."""
    out: dict[str, dict] = {}
    warnings: list[str] = []
    now = time.time()
    i, size = 0, BATCH
    while i < len(node_ids):
        try:
            result = await client.graphql(HEALTH_QUERY, {"ids": node_ids[i : i + size]})
        except ApiError as exc:
            # GitHub times out heavy queries with 502/504: retry smaller.
            if exc.status in (502, 504) and size > 5:
                size //= 2
                continue
            raise
        i += size
        for node in result.data.get("nodes") or []:
            if node and node.get("id"):
                out[node["id"]] = signals_from_node(node, now)
        warnings.extend(e.get("message", "") for e in result.errors)
    return out, warnings
