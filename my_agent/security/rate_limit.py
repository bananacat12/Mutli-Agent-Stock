from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field


class RateLimitExceeded(Exception):
    pass


def rate_limit_requests() -> int:
    return int(os.getenv("RATE_LIMIT_REQUESTS", "60"))


def rate_limit_window_seconds() -> int:
    return int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


@dataclass
class InMemoryRateLimiter:
    requests: int
    window_seconds: int
    buckets: dict[str, list[float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, identity: str) -> None:
        now = time.time()
        window_start = now - self.window_seconds
        with self.lock:
            timestamps = [ts for ts in self.buckets.get(identity, []) if ts > window_start]
            if len(timestamps) >= self.requests:
                self.buckets[identity] = timestamps
                raise RateLimitExceeded("Rate limit exceeded.")
            timestamps.append(now)
            self.buckets[identity] = timestamps

    def reset(self) -> None:
        with self.lock:
            self.buckets.clear()


_limiter = InMemoryRateLimiter(
    requests=rate_limit_requests(),
    window_seconds=rate_limit_window_seconds(),
)


def get_rate_limiter() -> InMemoryRateLimiter:
    global _limiter
    requests = rate_limit_requests()
    window_seconds = rate_limit_window_seconds()
    if _limiter.requests != requests or _limiter.window_seconds != window_seconds:
        _limiter = InMemoryRateLimiter(requests=requests, window_seconds=window_seconds)
    return _limiter


def check_rate_limit(identity: str | None) -> None:
    get_rate_limiter().check(identity or "anonymous")
