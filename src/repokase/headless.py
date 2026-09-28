"""`repokase --snapshot-traffic`: record traffic without the GUI.

Meant for the optional systemd user timer, so history keeps growing even on
days the app is not opened. Uses the same keyring token and cache as the app.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from . import config
from .api.client import GitHubClient
from .api.errors import ApiError, AuthExpired
from .api.repos import fetch_all_repos, fetch_viewer
from .auth import device_flow
from .auth.token_store import SecretServiceTokenStore, TokenStoreError
from .cache import db, store
from .jobs import snapshot_traffic, traffic_due

log = logging.getLogger(__name__)


async def _run(if_due: bool) -> int:
    tokens = SecretServiceTokenStore()
    try:
        token = tokens.load()
    except TokenStoreError as exc:
        print(f"repokase: {exc}", file=sys.stderr)
        return 2
    if token is None:
        print("repokase: not signed in. Open Repokase and sign in first.", file=sys.stderr)
        return 2

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as http:
        state = {"token": token}

        async def access_token() -> str:
            t = state["token"]
            if t.needs_refresh():
                # Another process (the GUI) may have refreshed already.
                fresh = tokens.load()
                if fresh and not fresh.needs_refresh():
                    state["token"] = fresh
                elif t.refresh_token:
                    state["token"] = await device_flow.refresh_token(http, config.github_client_id(), t.refresh_token)
                    tokens.save(state["token"])
                else:
                    raise AuthExpired()
            return state["token"].access_token

        client = GitHubClient(http, access_token)
        conn = db.connect(config.data_dir() / "repokase.db")
        try:
            viewer = await fetch_viewer(client)
            account_id = store.save_account(conn, viewer)
            if if_due and not traffic_due(conn, account_id):
                log.info("Traffic snapshot not due yet; nothing to do.")
                return 0
            if not store.load_repos(conn, account_id):
                result = await fetch_all_repos(client)
                store.replace_repos(conn, account_id, result.repos)
                store.mark_sync(conn, account_id, "repos")
            result = await snapshot_traffic(client, conn, account_id)
        except AuthExpired:
            print("repokase: GitHub sign-in expired. Open Repokase and sign in again.", file=sys.stderr)
            return 3
        except (ApiError, device_flow.DeviceFlowError) as exc:
            print(f"repokase: {exc}", file=sys.stderr)
            return 1
        finally:
            conn.close()
    print(
        f"Recorded traffic for {len(result.traffic)} repositories"
        f" ({len(result.skipped)} skipped: archived or no push access; {len(result.failed)} failed)."
    )
    return 1 if result.failed and not result.traffic else 0


def snapshot_traffic_cli(if_due: bool) -> int:
    return asyncio.run(_run(if_due))
