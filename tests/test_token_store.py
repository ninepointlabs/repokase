import json

import pytest

from repokase.auth.device_flow import TokenSet
from repokase.auth.token_store import (
    ATTRIBUTES,
    MemoryTokenStore,
    SecretServiceTokenStore,
    TokenStoreError,
)


class FakeItem:
    def __init__(self, coll, attrs, secret):
        self.coll, self.attrs, self.secret = coll, attrs, secret

    def get_secret(self):
        return self.secret

    def delete(self):
        self.coll.items.remove(self)


class FakeCollection:
    def __init__(self):
        self.items: list[FakeItem] = []

    def search_items(self, attrs):
        return [i for i in self.items if all(i.attrs.get(k) == v for k, v in attrs.items())]

    def create_item(self, label, attrs, secret, replace=False, content_type=None):
        if replace:
            for i in self.search_items(attrs):
                i.delete()
        self.items.append(FakeItem(self, dict(attrs), secret))


@pytest.fixture
def store(monkeypatch):
    coll = FakeCollection()
    s = SecretServiceTokenStore()
    monkeypatch.setattr(s, "_collection", lambda: coll)
    s.coll = coll
    return s


def test_save_load_clear_roundtrip(store):
    assert store.load() is None
    token = TokenSet("gho_abc", scope="repo", refresh_token=None)
    store.save(token)
    store.save(TokenSet("gho_new", scope="repo"))
    assert len(store.coll.items) == 1, "save replaces the existing entry"
    assert store.load().access_token == "gho_new"
    assert store.coll.items[0].attrs == ATTRIBUTES
    store.clear()
    assert store.load() is None


def test_unreadable_entry_is_ignored(store):
    store.coll.create_item("x", ATTRIBUTES, b"not json")
    assert store.load() is None


def test_secret_is_json(store):
    store.save(TokenSet("gho_abc", scope="repo"))
    assert json.loads(store.coll.items[0].secret)["access_token"] == "gho_abc"


def test_unavailable_secret_service_raises_clear_error(monkeypatch):
    import secretstorage

    def boom():
        raise secretstorage.exceptions.SecretServiceNotAvailableException("no bus")

    monkeypatch.setattr(secretstorage, "dbus_init", boom)
    with pytest.raises(TokenStoreError, match="Secret Service"):
        SecretServiceTokenStore().load()


def test_memory_store():
    s = MemoryTokenStore()
    s.save(TokenSet("x"))
    assert s.load().access_token == "x"
    s.clear()
    assert s.load() is None
