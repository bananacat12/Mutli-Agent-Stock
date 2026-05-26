from google.adk.agents.llm_agent import Agent

from .tool import get_price


def create_price_agent() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="price_agent",
        description="Handles stock price and technical indicators from Yahoo Finance.",
        instruction=(
            "You are the Price Agent. You receive a JSON string containing symbol, period, and interval. "
            "Call get_price(symbol, period, interval) exactly once. "
            "Return a concise summary under 100 words with current price, change percent, EMA20, EMA50, RSI14, and trend_hint. "
            "Do not provide investment advice beyond the returned technical data."
        ),
        tools=[get_price],
    )
