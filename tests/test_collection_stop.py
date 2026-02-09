"""Tests for global collection stop flag logic."""
from __future__ import annotations

import importlib


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)

    def delete(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)

    def ttl(self, key):
        return self.ttls.get(key, -1)


def _reload_module():
    import core.services.collection_stop as cs
    return importlib.reload(cs)


def test_prod_global_stop(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    cs = _reload_module()
    fake = FakeRedis()
    cs._redis_client = fake

    cs.set_global_collection_stop(True)
    assert cs.get_global_collection_stop() is True
    enabled, ttl = cs.get_global_collection_stop_status()
    assert enabled is True
    assert ttl == 3600
    assert fake.store.get("jur:stop:global") == "1"


def test_sandbox_toggle(monkeypatch):
    monkeypatch.setenv("APP_ENV", "sandbox")
    cs = _reload_module()
    fake = FakeRedis()
    cs._redis_client = fake

    cs.set_global_collection_stop(True, ttl_sec=600, reason="test", by="admin")
    assert cs.get_global_collection_stop() is True
    enabled, ttl = cs.get_global_collection_stop_status()
    assert enabled is True
    assert ttl == 600
    assert fake.store.get("jur:stop:global") == "1"

    cs.set_global_collection_stop(False)
    assert cs.get_global_collection_stop() is False
    assert cs.get_global_collection_stop_status() == (False, None)
