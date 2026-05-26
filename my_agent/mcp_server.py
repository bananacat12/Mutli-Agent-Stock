from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from my_agent.agent import handle_user_message_v2
from my_agent.news.tool import get_news
from my_agent.price.tool import get_price
from my_agent.security.auth import is_auth_enabled, verify_api_key
from my_agent.security.rate_limit import check_rate_limit
from my_agent.sentiment.tool import reddit_social_sentiment

mcp = FastMCP(
    name="stock-advisor-multi-agent",
    instructions=(
        "Use these tools to analyze public stocks through a production-lite multi-agent workflow. "
        "The system coordinates price, news, and Reddit sentiment specialists and returns traced JSON results."
    ),
    streamable_http_path="/mcp",
    sse_path="/sse",
    message_path="/messages/",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8001")),
)


def _require_mcp_api_key(api_key: str | None) -> None:
    if not verify_api_key(api_key):
        raise PermissionError("Invalid or missing MCP api_key.")
    check_rate_limit(api_key or "mcp-anonymous")


@mcp.tool(
    name="analyze_stock",
    description="Run the full multi-agent stock analysis workflow for a user request.",
    structured_output=True,
)
def analyze_stock(conversation_id: str, text: str, api_key: str | None = None) -> dict[str, Any]:
    _require_mcp_api_key(api_key)
    return handle_user_message_v2(conversation_id=conversation_id, text=text)


@mcp.tool(
    name="get_stock_price",
    description="Fetch stock price and technical indicators for a ticker.",
    structured_output=True,
)
def get_stock_price(symbol: str, period: str = "1mo", interval: str = "1d", api_key: str | None = None) -> dict[str, Any]:
    _require_mcp_api_key(api_key)
    return get_price(symbol=symbol, period=period, interval=interval)  # type: ignore[arg-type]


@mcp.tool(
    name="get_financial_news",
    description="Fetch recent financial news for a ticker, company, or keyword.",
    structured_output=True,
)
def get_financial_news(keyword: str, days: int = 3, api_key: str | None = None) -> dict[str, Any]:
    _require_mcp_api_key(api_key)
    return get_news(keyword=keyword, days=days)


@mcp.tool(
    name="get_reddit_sentiment",
    description="Collect Reddit posts and score sentiment for a ticker or keyword.",
    structured_output=True,
)
def get_reddit_sentiment(query: str, max_items: int = 60, api_key: str | None = None) -> dict[str, Any]:
    _require_mcp_api_key(api_key)
    return reddit_social_sentiment(query=query, max_items=max_items)


@mcp.resource(
    "agent://card",
    name="Agent Card",
    description="Capability manifest for the stock-advisor multi-agent system.",
    mime_type="application/json",
)
def agent_card_resource() -> str:
    return json.dumps(
        {
            "name": "stock-advisor-root-agent",
            "version": "0.1.0",
            "authenticated": is_auth_enabled(),
            "capabilities": ["price", "news", "sentiment", "parallel_execution", "task_tracing"],
            "tools": ["analyze_stock", "get_stock_price", "get_financial_news", "get_reddit_sentiment"],
        },
        ensure_ascii=True,
    )


@mcp.resource(
    "agent://schemas",
    name="Message Schemas",
    description="Internal request and response schema summary.",
    mime_type="application/json",
)
def schemas_resource() -> str:
    return json.dumps(
        {
            "AgentRequest": {
                "request_id": "uuid",
                "trace_id": "uuid",
                "task_id": "uuid",
                "conversation_id": "string",
                "agent_name": "price_agent | news_agent | reddit_sentiment_agent",
                "payload": "object",
                "timeout_s": "number",
            },
            "AgentResponse": {
                "request_id": "uuid",
                "status": "success | error | partial",
                "data": "object",
                "error": "string | null",
                "latency_ms": "integer | null",
            },
        },
        ensure_ascii=True,
    )


@mcp.prompt(
    name="stock_analysis_prompt",
    description="Prompt template for asking the multi-agent workflow to analyze a stock.",
)
def stock_analysis_prompt(ticker: str) -> str:
    return (
        f"Analyze {ticker} using price action, recent financial news, and Reddit sentiment. "
        "Return a concise HOLD/BUY/SELL-style view with evidence and uncertainty."
    )


@mcp.prompt(
    name="risk_review_prompt",
    description="Prompt template for reviewing risk signals after agent results are available.",
)
def risk_review_prompt(ticker: str) -> str:
    return (
        f"Review the risk signals for {ticker}. Focus on conflicting price, news, and sentiment evidence, "
        "and explain what data is missing before making a decision."
    )


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))  # stdio, sse, or streamable-http
