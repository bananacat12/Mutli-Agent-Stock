import pytest

from my_agent.security.rate_limit import RateLimitExceeded, check_rate_limit, get_rate_limiter


def test_rate_limiter_allows_until_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    get_rate_limiter().reset()

    check_rate_limit("key")
    check_rate_limit("key")

    with pytest.raises(RateLimitExceeded):
        check_rate_limit("key")


def test_rate_limiter_has_separate_buckets(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    get_rate_limiter().reset()

    check_rate_limit("key-a")
    check_rate_limit("key-b")

    with pytest.raises(RateLimitExceeded):
        check_rate_limit("key-a")
