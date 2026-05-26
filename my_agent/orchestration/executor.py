from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .contracts import AgentRequest, AgentResponse
from ..memory.store import save_agent_trace
from ..observability.tracing import log_agent_event


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_after_s: float = 60.0
    failures: dict[str, int] = field(default_factory=dict)
    opened_at: dict[str, float] = field(default_factory=dict)

    def allow(self, agent_name: str) -> bool:
        opened = self.opened_at.get(agent_name)
        if opened is None:
            return True
        if time.time() - opened >= self.reset_after_s:
            self.failures[agent_name] = 0
            self.opened_at.pop(agent_name, None)
            return True
        return False

    def record_success(self, agent_name: str) -> None:
        self.failures[agent_name] = 0
        self.opened_at.pop(agent_name, None)

    def record_failure(self, agent_name: str) -> None:
        count = self.failures.get(agent_name, 0) + 1
        self.failures[agent_name] = count
        if count >= self.failure_threshold:
            self.opened_at[agent_name] = time.time()


class AgentExecutor:
    def __init__(
        self,
        agents: dict[str, Any],
        max_steps: int = 3,
        max_retries: int = 2,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.agents = agents
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.breaker = breaker or CircuitBreaker()

    async def execute(self, requests: list[AgentRequest]) -> list[AgentResponse]:
        if len(requests) > self.max_steps:
            requests = requests[: self.max_steps]
        return await asyncio.gather(*(self._execute_one(req) for req in requests))

    async def _execute_one(self, request: AgentRequest) -> AgentResponse:
        started = time.perf_counter()
        agent_name = request.agent_name
        if not self.breaker.allow(agent_name):
            response = self._response(request, "error", {}, "Circuit breaker is open.", started)
            self._record_trace(request, response)
            return response

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                agent = self.agents[agent_name]
                result = await asyncio.wait_for(
                    self._run_agent(agent, request),
                    timeout=request.timeout_s,
                )
                data = self._extract_result(result)
                self.breaker.record_success(agent_name)
                response = self._response(request, "success", data, None, started)
                self._record_trace(request, response)
                return response
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2**attempt, 8))

        self.breaker.record_failure(agent_name)
        response = self._response(request, "error", {}, last_error or "Unknown agent failure.", started)
        self._record_trace(request, response)
        return response

    async def _run_agent(self, agent: Any, request: AgentRequest) -> Any:
        message = json.dumps(request.payload, ensure_ascii=False)
        if callable(agent):
            return await asyncio.to_thread(agent, request.payload)
        if hasattr(agent, "run"):
            return await asyncio.to_thread(agent.run, message)
        raise TypeError(
            f"{request.agent_name} does not expose a direct run(payload) interface. "
            "ADK Agent.run_async requires an InvocationContext and must be wrapped before use."
        )

    def _extract_result(self, result: Any) -> dict[str, Any]:
        if hasattr(result, "text"):
            return {"text": result.text}
        if isinstance(result, dict):
            return result
        return {"text": str(result)}

    def _response(
        self,
        request: AgentRequest,
        status: str,
        data: dict[str, Any],
        error: str | None,
        started: float,
    ) -> AgentResponse:
        return AgentResponse(
            request_id=request.request_id,
            trace_id=request.trace_id,
            task_id=request.task_id,
            conversation_id=request.conversation_id,
            agent_name=request.agent_name,
            status=status,  # type: ignore[arg-type]
            data=data,
            error=error,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _record_trace(self, request: AgentRequest, response: AgentResponse) -> None:
        log_agent_event(
            request.trace_id,
            request.task_id,
            request.agent_name,
            response.status,
            response.latency_ms,
        )
        try:
            save_agent_trace(request, response)
        except Exception:
            pass
