from datetime import datetime

import pandas as pd

from my_agent.news import tool as news_tool
from my_agent.price import tool as price_tool
from my_agent.sentiment import tool as sentiment_tool


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_news_tool_success_shape(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "test")
    news_tool.news_cache.clear()
    monkeypatch.setattr(
        news_tool,
        "safe_get",
        lambda *_, **__: FakeResponse(
            {
                "status": "ok",
                "articles": [
                    {
                        "title": "Title",
                        "source": {"name": "Source"},
                        "url": "https://example.com",
                        "publishedAt": "2026-01-01T00:00:00Z",
                        "description": "Desc",
                    }
                ],
            }
        ),
    )

    result = news_tool.get_news("AAPL")

    assert result["status"] == "success"
    assert result["data"]["count"] == 1


def test_price_tool_success_shape(monkeypatch):
    from datetime import timedelta
    price_tool.price_cache.clear()
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test")

    def mock_get(url, params=None, **kwargs):
        params = params or {}
        func = params.get("function")
        if func == "GLOBAL_QUOTE":
            return FakeResponse({
                "Global Quote": {
                    "05. price": "180.0",
                    "08. previous close": "175.0",
                    "09. change": "5.0",
                    "10. change percent": "2.86%",
                    "07. latest trading day": "2026-05-26"
                }
            })
        elif func == "TIME_SERIES_DAILY":
            time_series = {}
            for i in range(65):
                date_str = (datetime(2026, 5, 26) - timedelta(days=i)).strftime("%Y-%m-%d")
                time_series[date_str] = {"4. close": str(180.0 - i * 0.1)}
            return FakeResponse({
                "Time Series (Daily)": time_series
            })
        return FakeResponse({})

    monkeypatch.setattr(price_tool.requests, "get", mock_get)

    result = price_tool.get_price("TSLA")

    assert result["status"] == "success"
    assert result["data"]["symbol"] == "TSLA"
    assert "rsi14" in result["data"]["technicals"]


def test_sentiment_tool_partial_rule_based(monkeypatch):
    sentiment_tool.sentiment_cache.clear()
    monkeypatch.setattr(sentiment_tool, "_fetch_reddit", lambda *_: ["bullish breakout", "bearish dump"])
    monkeypatch.setattr(sentiment_tool, "_sentim", lambda *_: (_ for _ in ()).throw(RuntimeError("down")))

    result = sentiment_tool.reddit_social_sentiment("TSLA", max_items=2, min_success=2)

    assert result["status"] == "partial"
    assert result["data"]["query"] == "TSLA"
