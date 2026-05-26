# ============================================================
# FILE 2: my_agent/news/tool.py
# ============================================================
import requests
import os
from datetime import datetime, timedelta
from typing import Dict, Any
import sys


def _log(msg: str) -> None:
    """Ghi log ra stderr để không làm bẩn STDIO MCP."""
    print(msg, file=sys.stderr, flush=True)


# SỬA: Đổi từ relative sang absolute import
try:
    from cache import get_cache, set_cache
    _log("✅ News tool đã import cache thành công.")
except ImportError:
    _log("⚠️ Lỗi import cache, news_tool sẽ chạy không có cache.")

    def get_cache(key: str):
        return None

    def set_cache(key: str, value: Any, expiration_sec: int):
        pass


def get_news(keyword: str, days: int = 3) -> Dict[str, Any]:
    """Trả về danh sách tin tức tài chính mới nhất."""
    cache_key = f"news_tool:{keyword}:{days}"
    cached_result = get_cache(cache_key)
    if cached_result:
        return cached_result

    _log(f"CACHE MISS: Đang gọi API NewsAPI cho '{keyword}'...")

    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"status": "error", "error_message": "Thiếu NEWS_API_KEY trong .env"}

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": keyword,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "from": (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d"),
        "apiKey": api_key,
    }

    try:
        res = requests.get(url, params=params)
        data = res.json()
    except Exception as e:
        result = {"status": "error", "error_message": f"Lỗi gọi API: {e}"}
        set_cache(cache_key, result, expiration_sec=60)
        return result

    if data.get("status") != "ok":
        result = {"status": "error", "error_message": data.get("message", "Unknown error")}
        set_cache(cache_key, result, expiration_sec=60)
        return result

    articles = []
    for a in data.get("articles", []):
        articles.append({
            "title": a.get("title"),
            "source": a.get("source", {}).get("name"),
            "url": a.get("url"),
            "publishedAt": a.get("publishedAt"),
            "description": a.get("description"),
        })

    result = {
        "status": "success",
        "keyword": keyword,
        "count": len(articles),
        "articles": articles,
    }

    set_cache(cache_key, result, expiration_sec=3600)
    return result
