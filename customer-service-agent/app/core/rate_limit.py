"""Token bucket rate limiter."""

from __future__ import annotations
import time
from collections import defaultdict


class RateLimiter:
    """Simple token bucket rate limiter, per-user."""

    def __init__(self, rate: int = 30, per_seconds: int = 60):
        self.rate = rate          # tokens per window
        self.window = per_seconds # window in seconds
        self._buckets: dict[str, dict] = defaultdict(lambda: {"tokens": rate, "last": time.time()})

    def allow(self, key: str) -> bool:
        """Check if request is allowed. Returns True if within limit."""
        now = time.time()
        bucket = self._buckets[key]
        elapsed = now - bucket["last"]

        # Refill tokens
        bucket["tokens"] = min(self.rate, bucket["tokens"] + elapsed * self.rate / self.window)
        bucket["last"] = now

        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        return False

    def remaining(self, key: str) -> int:
        bucket = self._buckets[key]
        return max(0, int(bucket["tokens"]))

    def cleanup(self, max_age: int = 3600):
        """Remove stale buckets."""
        now = time.time()
        stale = [k for k, v in self._buckets.items() if now - v["last"] > max_age]
        for k in stale:
            del self._buckets[k]


# Global singleton
limiter = RateLimiter(rate=30, per_seconds=60)


def get_limiter() -> RateLimiter:
    limiter.cleanup()
    return limiter
