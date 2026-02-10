from core.services.collection_stop import get_global_collection_stop_state


class FakeRedis:
    def __init__(self):
        self.k = {}
        self._ttl = {}

    def get(self, key):
        return self.k.get(key)

    def setex(self, key, ttl, val):
        self.k[key] = val
        self._ttl[key] = ttl

    def set(self, key, val, ex=None):
        self.k[key] = val
        if ex is not None:
            self._ttl[key] = ex

    def delete(self, key):
        self.k.pop(key, None)
        self._ttl.pop(key, None)

    def ttl(self, key):
        v = self._ttl.get(key)
        return -1 if v is None else v


def test_global_stop_works_in_prod():
    r = FakeRedis()
    r.set("jur:stop:global", "1", ex=3600)
    st = get_global_collection_stop_state(r, "prod")
    assert st.enabled is True
    assert st.key == "jur:stop:global"


def test_legacy_sandbox_stop_only_affects_sandbox():
    r = FakeRedis()
    r.set("jur:stop:global:sandbox", "1", ex=3600)
    assert get_global_collection_stop_state(r, "prod").enabled is False
    assert get_global_collection_stop_state(r, "sandbox").enabled is True

