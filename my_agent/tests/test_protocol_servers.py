import pytest
from fastapi.testclient import TestClient

from my_agent.api.a2a import app
from my_agent.mcp_server import mcp


def test_a2a_agent_card():
    client = TestClient(app)

    response = client.get("/.well-known/agent.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "stock-advisor-root-agent"
    assert payload["capabilities"]["streaming"] is True
    assert {skill["id"] for skill in payload["skills"]} == {"price", "news", "sentiment"}


def test_a2a_task_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "60")
    from my_agent.security.rate_limit import get_rate_limiter

    get_rate_limiter().reset()
    client = TestClient(app)
    payload = {
        "id": "task-auth-test",
        "sessionId": "session",
        "message": {"role": "user", "parts": [{"type": "text", "text": "analyze TSLA"}]},
    }

    missing = client.post("/tasks", json=payload)
    invalid = client.post("/tasks", json=payload, headers={"X-API-Key": "bad"})

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_a2a_task_accepts_api_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "60")
    from my_agent.security.rate_limit import get_rate_limiter

    get_rate_limiter().reset()
    client = TestClient(app)
    payload = {
        "id": "task-auth-test-ok",
        "sessionId": "session",
        "message": {"role": "user", "parts": [{"type": "text", "text": "analyze TSLA"}]},
    }
    monkeypatch.setattr("my_agent.api.a2a.create_task", lambda *_: None)
    async def noop_run_task(*_):
        return None

    monkeypatch.setattr("my_agent.api.a2a._run_task", noop_run_task)
    monkeypatch.setattr(
        "my_agent.api.a2a.get_task",
        lambda *_: {
            "task_id": "task-auth-test-ok",
            "conversation_id": "session",
            "trace_id": "trace",
            "status": "submitted",
            "input": {"text": "analyze TSLA"},
            "output": None,
            "error": None,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        },
    )

    response = client.post("/tasks", json=payload, headers={"X-API-Key": "secret"})

    assert response.status_code == 200


def test_a2a_rate_limit_blocks_after_quota(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    from my_agent.security.rate_limit import get_rate_limiter

    get_rate_limiter().reset()
    client = TestClient(app)
    payload = {
        "id": "task-rate-limit",
        "sessionId": "session",
        "message": {"role": "user", "parts": [{"type": "text", "text": "analyze TSLA"}]},
    }
    monkeypatch.setattr("my_agent.api.a2a.create_task", lambda *_: None)

    async def noop_run_task(*_):
        return None

    monkeypatch.setattr("my_agent.api.a2a._run_task", noop_run_task)
    monkeypatch.setattr(
        "my_agent.api.a2a.get_task",
        lambda *_: {
            "task_id": "task-rate-limit",
            "conversation_id": "session",
            "trace_id": "trace",
            "status": "submitted",
            "input": {"text": "analyze TSLA"},
            "output": None,
            "error": None,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        },
    )

    first = client.post("/tasks", json=payload, headers={"X-API-Key": "secret"})
    second = client.post("/tasks", json={**payload, "id": "task-rate-limit-2"}, headers={"X-API-Key": "secret"})

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_mcp_exposes_tools_resources_and_prompts():
    tools = await mcp.list_tools()
    resources = await mcp.list_resources()
    prompts = await mcp.list_prompts()

    assert {"analyze_stock", "get_stock_price", "get_financial_news", "get_reddit_sentiment"}.issubset(
        {tool.name for tool in tools}
    )
    assert {"agent://card", "agent://schemas"}.issubset({str(resource.uri) for resource in resources})
    assert {"stock_analysis_prompt", "risk_review_prompt"}.issubset({prompt.name for prompt in prompts})


def test_mcp_tool_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "60")
    from my_agent.security.rate_limit import get_rate_limiter

    get_rate_limiter().reset()
    from my_agent import mcp_server

    with pytest.raises(PermissionError):
        mcp_server.get_stock_price("TSLA")


def test_mcp_tool_rate_limit(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "secret")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    from my_agent.security.rate_limit import RateLimitExceeded, get_rate_limiter

    get_rate_limiter().reset()
    from my_agent import mcp_server

    monkeypatch.setattr(mcp_server, "get_price", lambda **_: {"status": "success", "data": {}})

    mcp_server.get_stock_price("TSLA", api_key="secret")
    with pytest.raises(RateLimitExceeded):
        mcp_server.get_stock_price("TSLA", api_key="secret")
