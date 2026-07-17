"""In-memory session store (stand-in for Redis + PostgreSQL)."""

from __future__ import annotations
import time
from collections import OrderedDict


class MemoryStore:
    """Simple TTL-based in-memory key-value store."""

    def __init__(self):
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def set(self, key: str, value: object, ttl: int = 1800):
        self._data[key] = (time.time() + ttl, value)
        self._evict()

    def get(self, key: str) -> object | None:
        self._evict()
        entry = self._data.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.time() > expires:
            del self._data[key]
            return None
        return value

    def delete(self, key: str):
        self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def _evict(self):
        now = time.time()
        expired = [k for k, (exp, _) in self._data.items() if now > exp]
        for k in expired:
            del self._data[k]


# Global singleton
store = MemoryStore()


def get_store() -> MemoryStore:
    return store
