from google.adk.agents.llm_agent import Agent

from .tool import get_news


def create_news_agent() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="news_agent",
        description="Fetches and summarizes recent financial news for companies, tickers, or keywords.",
        instruction=(
            "You are the News Agent. You receive a JSON string containing keyword and days. "
            "Call get_news(keyword, days) exactly once. "
            "Return a concise summary under 150 words covering the 2-3 most important articles, sources, and timestamps. "
            "If the tool returns an error, report the error briefly."
        ),
        tools=[get_news],
    )


if __name__ == "__main__":
    print("Create this agent through my_agent.agent.create_agent() or run the deterministic workflow via handle_user_message_v2().")
