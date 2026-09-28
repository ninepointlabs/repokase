"""Traffic API. GitHub keeps only 14 days, so Repokase snapshots it daily."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from .client import GitHubClient
from .errors import ApiError, AuthExpired, NotFound, RateLimited
from .rest import _repo_path

# Traffic needs push access; GitHub answers 403 otherwise.
PUSH_PERMISSIONS = {"ADMIN", "MAINTAIN", "WRITE"}
CONCURRENCY = 4


@dataclass
class RepoTraffic:
    full_name: str
    views: list[dict] = field(default_factory=list)  # {day, count, uniques}
    clones: list[dict] = field(default_factory=list)
    referrers: list[dict] = field(default_factory=list)  # {referrer, count, uniques}


def _days(items: list[dict]) -> list[dict]:
    return [
        {"day": (i.get("timestamp") or "")[:10], "count": int(i.get("count") or 0), "uniques": int(i.get("uniques") or 0)}
        for i in items or []
        if i.get("timestamp")
    ]


async def fetch_repo_traffic(client: GitHubClient, full_name: str) -> RepoTraffic:
    base = _repo_path(full_name) + "/traffic"
    views, clones, referrers = await asyncio.gather(
        client.rest("GET", f"{base}/views", params={"per": "day"}),
        client.rest("GET", f"{base}/clones", params={"per": "day"}),
        client.rest("GET", f"{base}/popular/referrers"),
    )
    return RepoTraffic(
        full_name=full_name,
        views=_days((views or {}).get("views", [])),
        clones=_days((clones or {}).get("clones", [])),
        referrers=[
            {"referrer": r.get("referrer", ""), "count": int(r.get("count") or 0), "uniques": int(r.get("uniques") or 0)}
            for r in (referrers or [])
        ],
    )


@dataclass
class SnapshotResult:
    traffic: list[RepoTraffic]
    skipped: list[str]  # no push access or not found
    failed: dict[str, str]


async def snapshot(
    client: GitHubClient,
    repos: list[dict],
    on_progress: Callable[[int, int], None] | None = None,
) -> SnapshotResult:
    """Fetch traffic for every repo the viewer can push to, a few at a time."""
    eligible = [r for r in repos if r.get("viewer_permission") in PUSH_PERMISSIONS and not r.get("is_archived")]
    skipped = [r["full_name"] for r in repos if r not in eligible]
    sem = asyncio.Semaphore(CONCURRENCY)
    out: list[RepoTraffic] = []
    failed: dict[str, str] = {}
    done = 0

    async def one(repo: dict) -> None:
        nonlocal done
        async with sem:
            try:
                out.append(await fetch_repo_traffic(client, repo["full_name"]))
            except (AuthExpired, RateLimited):
                raise
            except NotFound:
                skipped.append(repo["full_name"])
            except ApiError as exc:
                if exc.status == 403:
                    skipped.append(repo["full_name"])
                else:
                    failed[repo["full_name"]] = str(exc)
            done += 1
            if on_progress:
                on_progress(done, len(eligible))

    await asyncio.gather(*(one(r) for r in eligible))
    return SnapshotResult(traffic=out, skipped=sorted(skipped), failed=failed)
