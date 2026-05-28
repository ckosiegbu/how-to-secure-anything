"""Bounded thread-safe LRU cache (for decoder-key derivation memoisation)."""

from __future__ import annotations
import threading
from collections import OrderedDict


class LruCache:
    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self._d = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get_or_compute(self, key, compute):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                self.hits += 1
                return self._d[key]
            self.misses += 1
        value = compute()                     # computed outside the lock
        with self._lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.capacity:
                self._d.popitem(last=False)
        return value

    def clear(self):
        with self._lock:
            self._d.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {"size": len(self._d), "capacity": self.capacity,
                    "hits": self.hits, "misses": self.misses,
                    "hitRate": round(self.hits / total, 4) if total else 0.0}
