from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Status = Literal["success", "error", "partial"]
TaskStatus = Literal["submitted", "working", "completed", "failed", "partial"]
AgentName = Literal["price_agent", "news_agent", "reddit_sentiment_agent"]


def new_id() -> str:
    return str(uuid4())


class ToolStatus(BaseModel):
    status: Status
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentRequest(BaseModel):
    request_id: str = Field(default_factory=new_id)
    trace_id: str
    task_id: str
    conversation_id: str
    agent_name: AgentName
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_s: float = 20.0


class AgentResponse(BaseModel):
    request_id: str
    trace_id: str
    task_id: str
    conversation_id: str
    agent_name: str
    status: Status
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: int | None = None
    token_count: int | None = None
    cost_usd: float | None = None


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=new_id)
    trace_id: str = Field(default_factory=new_id)
    conversation_id: str
    status: TaskStatus = "submitted"
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def normalize_tool_result(result: Any) -> ToolStatus:
    if isinstance(result, ToolStatus):
        return result
    if isinstance(result, dict):
        status = result.get("status")
        if status in {"success", "error", "partial"} and ("data" in result or "error" in result):
            return ToolStatus(
                status=status,
                data=result.get("data") or {},
                error=result.get("error") or result.get("error_message"),
            )
        if status == "success":
            return ToolStatus(status="success", data={k: v for k, v in result.items() if k != "status"})
        if status == "error":
            return ToolStatus(status="error", error=result.get("error_message") or result.get("error"))
        if status == "success_degraded":
            return ToolStatus(status="partial", data={k: v for k, v in result.items() if k != "status"})
    return ToolStatus(status="success", data={"value": result})
