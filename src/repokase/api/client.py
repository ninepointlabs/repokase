"""Async GitHub client: one httpx session, rate-limit tracking, error mapping."""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from .. import __version__
from .errors import (
    ApiError,
    AuthExpired,
    GraphQLError,
    NetworkError,
    NotFound,
    RateLimited,
    ScopeMissing,
    SsoRequired,
)

API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"

_SSO_URL = re.compile(r"url=(\S+)")


@dataclass
class RateLimit:
    limit: int | None = None
    remaining: int | None = None
    reset_at: float | None = None
    resource: str = "core"


@dataclass
class GraphQLResult:
    data: dict
    # Partial errors (e.g. one SSO-protected org) that did not void the query.
    errors: list[dict] = field(default_factory=list)


def _scopes(header: str | None) -> set[str] | None:
    if header is None:
        return None
    return {s.strip() for s in header.split(",") if s.strip()}


class GitHubClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        token: Callable[[], Awaitable[str]],
        on_rate_limit: Callable[[RateLimit], None] | None = None,
    ):
        self._http = http
        self._token = token
        self._on_rate_limit = on_rate_limit
        self.rate_limits: dict[str, RateLimit] = {}
        self.granted_scopes: set[str] | None = None

    async def _headers(self, accept: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._token()}",
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": f"Repokase/{__version__}",
        }

    def _track(self, resp: httpx.Response) -> None:
        h = resp.headers
        scopes = _scopes(h.get("x-oauth-scopes"))
        if scopes is not None:
            self.granted_scopes = scopes
        if "x-ratelimit-remaining" not in h:
            return
        rl = RateLimit(
            limit=int(h.get("x-ratelimit-limit", 0)) or None,
            remaining=int(h["x-ratelimit-remaining"]),
            reset_at=float(h["x-ratelimit-reset"]) if "x-ratelimit-reset" in h else None,
            resource=h.get("x-ratelimit-resource", "core"),
        )
        self.rate_limits[rl.resource] = rl
        if self._on_rate_limit:
            self._on_rate_limit(rl)

    def _raise_for(self, resp: httpx.Response) -> None:
        status = resp.status_code
        if status < 400:
            return
        h = resp.headers
        try:
            message = resp.json().get("message", "")
        except (ValueError, AttributeError):
            message = ""
        if status >= 500:
            raise ApiError(f"GitHub is having trouble right now (HTTP {status}). Try again shortly.", status)
        if status == 401:
            raise AuthExpired()
        sso = h.get("x-github-sso")
        if status == 403 and sso:
            match = _SSO_URL.search(sso)
            raise SsoRequired(match.group(1) if match else None)
        if status in (403, 429) and (h.get("x-ratelimit-remaining") == "0" or "retry-after" in h):
            if "retry-after" in h:
                reset = time.time() + float(h["retry-after"])
            else:
                reset = float(h.get("x-ratelimit-reset", 0)) or None
            raise RateLimited(reset)
        if status in (403, 404):
            accepted = _scopes(h.get("x-accepted-oauth-scopes"))
            granted = _scopes(h.get("x-oauth-scopes"))
            # Accepted scopes are alternatives; missing means none was granted.
            if accepted and granted is not None and not (accepted & granted):
                raise ScopeMissing(accepted)
        if status == 404:
            raise NotFound()
        raise ApiError(message or f"GitHub returned HTTP {status}.", status)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        accept: str = "application/vnd.github+json",
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{API_URL}{path}"
        try:
            resp = await self._http.request(
                method, url, json=json, params=params, headers=await self._headers(accept)
            )
        except httpx.TransportError as exc:
            raise NetworkError(str(exc)) from exc
        self._track(resp)
        self._raise_for(resp)
        return resp

    async def rest(self, method: str, path: str, **kw) -> Any:
        resp = await self.request(method, path, **kw)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def graphql(self, query: str, variables: dict | None = None) -> GraphQLResult:
        resp = await self.request("POST", "/graphql", json={"query": query, "variables": variables or {}})
        body = resp.json()
        errors = body.get("errors") or []
        for err in errors:
            if err.get("type") == "RATE_LIMITED":
                rl = self.rate_limits.get("graphql")
                raise RateLimited(rl.reset_at if rl else None)
        data = body.get("data")
        if data is None:
            raise GraphQLError(errors)
        return GraphQLResult(data=data, errors=errors)
