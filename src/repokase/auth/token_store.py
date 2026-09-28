"""Token persistence in the desktop Secret Service (gnome-keyring, KWallet).

There is deliberately no file fallback: if no Secret Service is reachable
the app says so and keeps the token in memory for the session only.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from .device_flow import TokenSet

log = logging.getLogger(__name__)

ATTRIBUTES = {"application": "repokase", "type": "github-token"}
LABEL = "Repokase GitHub token"


class TokenStoreError(Exception):
    pass


class TokenStore(Protocol):
    def load(self) -> TokenSet | None: ...
    def save(self, token: TokenSet) -> None: ...
    def clear(self) -> None: ...


class MemoryTokenStore:
    def __init__(self, token: TokenSet | None = None):
        self._token = token

    def load(self) -> TokenSet | None:
        return self._token

    def save(self, token: TokenSet) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None


class SecretServiceTokenStore:
    def __init__(self):
        self._conn = None

    def _collection(self):
        try:
            import secretstorage
            from secretstorage.exceptions import SecretServiceNotAvailableException
        except ImportError as exc:
            raise TokenStoreError("python-secretstorage is not installed.") from exc
        try:
            if self._conn is None:
                self._conn = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(self._conn)
        except (SecretServiceNotAvailableException, Exception) as exc:  # jeepney raises various
            raise TokenStoreError(
                "No Secret Service is available. Install and start gnome-keyring or KWallet "
                "so Repokase can store your GitHub token securely."
            ) from exc
        if collection.is_locked():
            dismissed = collection.unlock()
            if dismissed or collection.is_locked():
                raise TokenStoreError("The keyring is locked. Unlock it to use your saved sign-in.")
        return collection

    def load(self) -> TokenSet | None:
        collection = self._collection()
        for item in collection.search_items(ATTRIBUTES):
            try:
                return TokenSet.from_dict(json.loads(item.get_secret().decode()))
            except (ValueError, TypeError, KeyError):
                log.warning("Ignoring unreadable Repokase keyring entry")
        return None

    def save(self, token: TokenSet) -> None:
        collection = self._collection()
        collection.create_item(
            LABEL,
            ATTRIBUTES,
            json.dumps(token.to_dict()).encode(),
            replace=True,
            content_type="application/json",
        )

    def clear(self) -> None:
        collection = self._collection()
        for item in list(collection.search_items(ATTRIBUTES)):
            item.delete()
