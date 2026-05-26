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
    price_tool.price_cache.clear()

    class FakeTicker:
        fast_info = {"currency": "USD"}

        def history(self, **kwargs):
            return pd.DataFrame(
                {"Close": [100.0, 101.0, 102.0, 103.0]},
                index=pd.to_datetime(
                    [
                        datetime(2026, 1, 1),
                        datetime(2026, 1, 2),
                        datetime(2026, 1, 3),
                        datetime(2026, 1, 4),
                    ]
                ),
            )

    monkeypatch.setattr(price_tool.yf, "Ticker", lambda symbol: FakeTicker())

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
