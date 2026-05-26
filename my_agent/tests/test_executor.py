import pytest

from my_agent.orchestration.contracts import AgentRequest
from my_agent.orchestration.executor import AgentExecutor, CircuitBreaker


class Result:
    def __init__(self, text):
        self.text = text


class OkAgent:
    def run(self, message):
        return Result(f"ok:{message}")


class FailingAgent:
    def run(self, message):
        raise RuntimeError("boom")


class SlowAgent:
    def run(self, message):
        import time

        time.sleep(0.2)
        return Result("slow")


def request(agent_name, timeout_s=1.0):
    return AgentRequest(
        trace_id="trace",
        task_id="task",
        conversation_id="conv",
        agent_name=agent_name,
        payload={"symbol": "TSLA"},
        timeout_s=timeout_s,
    )


@pytest.mark.asyncio
async def test_executor_success_and_error(monkeypatch):
    monkeypatch.setattr("my_agent.orchestration.executor.save_agent_trace", lambda *_: None)
    executor = AgentExecutor(
        {
            "price_agent": OkAgent(),
            "news_agent": FailingAgent(),
        },
        max_retries=0,
    )

    results = await executor.execute([request("price_agent"), request("news_agent")])

    assert [result.status for result in results] == ["success", "error"]


@pytest.mark.asyncio
async def test_executor_timeout(monkeypatch):
    monkeypatch.setattr("my_agent.orchestration.executor.save_agent_trace", lambda *_: None)
    executor = AgentExecutor({"price_agent": SlowAgent()}, max_retries=0)

    results = await executor.execute([request("price_agent", timeout_s=0.01)])

    assert results[0].status == "error"


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_open_agent(monkeypatch):
    monkeypatch.setattr("my_agent.orchestration.executor.save_agent_trace", lambda *_: None)
    breaker = CircuitBreaker(failure_threshold=1, reset_after_s=60)
    executor = AgentExecutor({"price_agent": FailingAgent()}, max_retries=0, breaker=breaker)

    first = await executor.execute([request("price_agent")])
    second = await executor.execute([request("price_agent")])

    assert first[0].status == "error"
    assert second[0].error == "Circuit breaker is open."
