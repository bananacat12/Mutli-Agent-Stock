from __future__ import annotations

import re
from typing import Any

from .contracts import AgentRequest

COMMON_TICKERS = {
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "TESLA": "TSLA",
    "NVIDIA": "NVDA",
    "META": "META",
    "FACEBOOK": "META",
    "NETFLIX": "NFLX",
}

AGENT_TIMEOUTS = {
    "price_agent": 20.0,
    "news_agent": 20.0,
    "reddit_sentiment_agent": 35.0,
}


def sanitize_user_text(text: str, max_chars: int = 1000) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) > max_chars:
        raise ValueError("Yeu cau qua dai, vui long tom tat duoi 1000 ky tu.")
    return normalized


def extract_ticker(text: str) -> str | None:
    upper = text.upper()
    for name, ticker in COMMON_TICKERS.items():
        if name in upper:
            return ticker
    cashtags = re.findall(r"\$([A-Z]{1,5})(?![A-Z])", upper)
    if cashtags:
        return cashtags[0]
    candidates = re.findall(r"\b[A-Z]{1,5}\b", upper)
    ignored = {
        "BUY",
        "SELL",
        "HOLD",
        "RSI",
        "EMA",
        "TIN",
        "MOI",
        "NEWS",
        "NEN",
        "MUA",
        "BAN",
        "CO",
        "PHIEU",
        "NAO",
        "GIA",
        "VA",
        "Y",
        "KIEN",
    }
    for candidate in candidates:
        if candidate not in ignored:
            return candidate
    return None


def _selected_agents(text: str) -> list[str]:
    lower = text.lower()
    wants_news = any(keyword in lower for keyword in ("news", "tin", "article", "market"))
    wants_sentiment = any(keyword in lower for keyword in ("sentiment", "reddit", "cam xuc", "y kien"))
    wants_price = any(keyword in lower for keyword in ("price", "gia", "rsi", "ema", "technical", "phan tich"))

    if wants_news and not wants_price and not wants_sentiment:
        return ["news_agent"]
    if wants_sentiment and not wants_price and not wants_news:
        return ["reddit_sentiment_agent"]
    if wants_price and not wants_news and not wants_sentiment:
        return ["price_agent"]
    return ["price_agent", "news_agent", "reddit_sentiment_agent"]


def build_plan(
    conversation_id: str,
    task_id: str,
    trace_id: str,
    user_text: str,
    facts: dict[str, str] | None = None,
) -> list[AgentRequest]:
    clean_text = sanitize_user_text(user_text)
    ticker = extract_ticker(clean_text) or (facts or {}).get("ticker")
    if not ticker:
        return []

    agents = _selected_agents(clean_text)
    requests: list[AgentRequest] = []

    for agent_name in agents:
        payload: dict[str, Any] = {"user_text": clean_text, "ticker": ticker}
        if agent_name == "price_agent":
            payload.update({"symbol": ticker, "period": "1mo", "interval": "1d"})
        elif agent_name == "news_agent":
            payload.update({"keyword": ticker if ticker != "UNKNOWN" else clean_text, "days": 3})
        elif agent_name == "reddit_sentiment_agent":
            payload.update({"query": ticker, "max_items": 60})
        requests.append(
            AgentRequest(
                trace_id=trace_id,
                task_id=task_id,
                conversation_id=conversation_id,
                agent_name=agent_name,  # type: ignore[arg-type]
                payload=payload,
                timeout_s=AGENT_TIMEOUTS[agent_name],
            )
        )
    return requests
