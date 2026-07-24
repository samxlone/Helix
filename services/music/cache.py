"""Simple in-memory cache for metadata.
Not persistent; suitable for small-scale caching in Phase 1.
"""
import time
from typing import Any, Optional


class SimpleCache:
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self.data = {}

    def set(self, key: str, value: Any) -> None:
        self.data[key] = (time.time() + self.ttl, value)

    def get(self, key: str) -> Optional[Any]:
        item = self.data.get(key)
        if not item:
            return None
        expires, value = item
        if time.time() > expires:
            del self.data[key]
            return None
        return value

    def clear(self):
        self.data.clear()
