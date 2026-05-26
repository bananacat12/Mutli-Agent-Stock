from __future__ import annotations

from urllib.parse import urlparse

import requests

ALLOWED_HOSTS = {
    "newsapi.org",
    "www.reddit.com",
    "sentim-api.herokuapp.com",
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
}


def _validate_url(url: str) -> None:
    host = urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        raise PermissionError(f"Blocked outbound host: {host}")


def safe_get(url: str, **kwargs):
    _validate_url(url)
    kwargs.setdefault("timeout", 10)
    return requests.get(url, **kwargs)


def safe_post(url: str, **kwargs):
    _validate_url(url)
    kwargs.setdefault("timeout", 10)
    return requests.post(url, **kwargs)
