from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache, cached

from ..orchestration.contracts import normalize_tool_result, model_to_dict
from ..security.http_client import safe_get

news_cache = TTLCache(maxsize=100, ttl=300)


@cached(cache=news_cache)
def get_news(keyword: str, days: int = 3) -> dict:
    """Return recent financial news for a keyword using NewsAPI."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": "Missing NEWS_API_KEY."}))

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": keyword,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "from": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),
        "apiKey": api_key,
    }

    try:
        res = safe_get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as exc:
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": f"News API error: {exc}"}))

    if data.get("status") != "ok":
        return model_to_dict(
            normalize_tool_result({"status": "error", "error_message": data.get("message", "Unknown NewsAPI error")})
        )

    articles = [
        {
            "title": article.get("title"),
            "source": article.get("source", {}).get("name"),
            "url": article.get("url"),
            "publishedAt": article.get("publishedAt"),
            "description": article.get("description"),
        }
        for article in data.get("articles", [])
    ]

    return model_to_dict(
        normalize_tool_result(
            {
                "status": "success",
                "data": {
                    "keyword": keyword,
                    "count": len(articles),
                    "articles": articles,
                },
            }
        )
    )
