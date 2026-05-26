from my_agent.orchestration.planner import build_plan, extract_ticker


def test_extract_ticker_from_company_name():
    assert extract_ticker("phan tich Tesla") == "TSLA"


def test_news_only_plan():
    plan = build_plan("conv", "task", "trace", "tin moi Apple")

    assert [request.agent_name for request in plan] == ["news_agent"]
    assert plan[0].payload["keyword"] == "AAPL"


def test_sentiment_only_plan():
    plan = build_plan("conv", "task", "trace", "sentiment NVDA tren Reddit")

    assert [request.agent_name for request in plan] == ["reddit_sentiment_agent"]
    assert plan[0].payload["query"] == "NVDA"


def test_default_stock_question_uses_all_agents():
    plan = build_plan("conv", "task", "trace", "nen mua TSLA khong")

    assert [request.agent_name for request in plan] == [
        "price_agent",
        "news_agent",
        "reddit_sentiment_agent",
    ]


def test_missing_ticker_does_not_plan_unknown_tool_calls():
    plan = build_plan("conv", "task", "trace", "nen mua co phieu nao")

    assert plan == []
