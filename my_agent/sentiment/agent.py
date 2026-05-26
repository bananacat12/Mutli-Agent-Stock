from google.adk.agents.llm_agent import Agent

from .tool import reddit_social_sentiment


def create_sentiment_agent() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="reddit_sentiment_agent",
        description="Collects Reddit posts for a ticker and scores social sentiment.",
        instruction=(
            "You are the Sentiment Agent. You receive a JSON string containing query and max_items. "
            "Call reddit_social_sentiment(query, max_items) exactly once. "
            "Return a concise summary under 150 words with mean score and positive/neutral/negative counts. "
            "If the tool returns partial status, mention that degraded mode was used."
        ),
        tools=[reddit_social_sentiment],
    )
