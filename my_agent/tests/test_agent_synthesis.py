import pytest

from my_agent.agent import _summarize_results
from my_agent.orchestration.contracts import AgentResponse


def response(agent_name="price_agent"):
    return AgentResponse(
        request_id="request",
        trace_id="trace",
        task_id="task",
        conversation_id="conv",
        agent_name=agent_name,
        status="success",
        data={"text": "TSLA: price=100 USD, change=1.00%, trend=Uptrend"},
        latency_ms=10,
    )


@pytest.mark.asyncio
async def test_summarize_results_uses_llm_when_api_key_exists(monkeypatch):
    class FakeModels:
        def generate_content(self, model, contents):
            assert model == "test-model"
            assert "Subagent results JSON" in contents

            class Result:
                text = "Verdict: HOLD\nEvidence: price data available"

            return Result()

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.models = FakeModels()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("ROOT_SYNTHESIS_MODEL", "test-model")
    monkeypatch.setattr("my_agent.agent.genai.Client", FakeClient)

    reply = await _summarize_results("analyze TSLA", [response()])

    assert reply.startswith("Verdict: HOLD")


@pytest.mark.asyncio
async def test_summarize_results_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    reply = await _summarize_results("analyze TSLA", [response()])

    assert "Multi-agent result:" in reply
    assert "price_agent" in reply
