from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal
from uuid import uuid4

import requests
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl

from ..agent import handle_user_message_v2_async
from ..memory.store import create_task, get_agent_traces, get_task
from ..orchestration.contracts import TaskRecord
from ..security.auth import extract_bearer_token, is_auth_enabled, verify_api_key
from ..security.rate_limit import RateLimitExceeded, check_rate_limit

app = FastAPI(
    title="Stock Advisor A2A Server",
    version="0.1.0",
    description="A2A-compatible HTTP facade for the production-lite stock advisor multi-agent workflow.",
)


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    candidate = x_api_key or extract_bearer_token(authorization)
    if not verify_api_key(candidate):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    identity = candidate or (request.client.host if request.client else "anonymous")
    try:
        check_rate_limit(identity)
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")


class A2AMessage(BaseModel):
    role: Literal["user", "agent"] = "user"
    parts: list[dict[str, Any]]


class PushNotificationConfig(BaseModel):
    url: HttpUrl
    token: str | None = None


class TaskSubmitRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sessionId: str
    message: A2AMessage
    metadata: dict[str, Any] = Field(default_factory=dict)
    pushNotification: PushNotificationConfig | None = None


class A2ATask(BaseModel):
    id: str
    sessionId: str
    message: A2AMessage
    status: Literal["submitted", "working", "completed", "failed", "partial"]
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _message_text(message: A2AMessage) -> str:
    chunks: list[str] = []
    for part in message.parts:
        if "text" in part:
            chunks.append(str(part["text"]))
        elif part.get("type") == "text" and "content" in part:
            chunks.append(str(part["content"]))
    return "\n".join(chunks).strip()


def _task_from_db(row: dict[str, Any], message: A2AMessage | None = None) -> A2ATask:
    output = row.get("output") or {}
    input_payload = row.get("input") or {}
    msg = message or A2AMessage(role="user", parts=[{"type": "text", "text": input_payload.get("text", "")}])
    artifacts = []
    if output:
        artifacts.append({"type": "json", "name": "result", "data": output})
    return A2ATask(
        id=row["task_id"],
        sessionId=row["conversation_id"],
        message=msg,
        status=row["status"],
        artifacts=artifacts,
        metadata={
            "trace_id": row["trace_id"],
            "error": row.get("error"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        },
    )


def _send_push_notification(config: PushNotificationConfig | None, payload: dict[str, Any]) -> None:
    if not config or os.getenv("A2A_ENABLE_PUSH", "0") != "1":
        return
    headers = {"Content-Type": "application/json"}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    try:
        requests.post(str(config.url), json=payload, headers=headers, timeout=10)
    except Exception:
        return


async def _run_task(request: TaskSubmitRequest, trace_id: str) -> None:
    result = await handle_user_message_v2_async(
        conversation_id=request.sessionId,
        text=_message_text(request.message),
        meta=request.metadata,
        task_id=request.id,
        trace_id=trace_id,
    )
    _send_push_notification(request.pushNotification, result)


@app.get("/.well-known/agent.json")
def agent_card() -> dict[str, Any]:
    return {
        "name": "stock-advisor-root-agent",
        "version": "0.1.0",
        "description": "Coordinates price, financial news, and Reddit sentiment subagents for stock analysis.",
        "url": os.getenv("A2A_PUBLIC_URL", "http://localhost:8000"),
        "capabilities": {
            "streaming": True,
            "pushNotifications": os.getenv("A2A_ENABLE_PUSH", "0") == "1",
            "authenticated": is_auth_enabled(),
        },
        "skills": [
            {"id": "price", "name": "Stock price and technical indicators"},
            {"id": "news", "name": "Recent financial news"},
            {"id": "sentiment", "name": "Reddit social sentiment"},
        ],
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks", response_model=A2ATask, dependencies=[Depends(require_api_key)])
async def submit_task(request: TaskSubmitRequest, background_tasks: BackgroundTasks) -> A2ATask:
    text = _message_text(request.message)
    if not text:
        raise HTTPException(status_code=400, detail="Task message must contain text.")
    trace_id = str(uuid4())
    task = TaskRecord(
        task_id=request.id,
        trace_id=trace_id,
        conversation_id=request.sessionId,
        status="submitted",
        input={"text": text, "metadata": request.metadata},
    )
    create_task(task)
    background_tasks.add_task(_run_task, request, trace_id)
    row = get_task(request.id)
    if row is None:
        raise HTTPException(status_code=500, detail="Task was not persisted.")
    return _task_from_db(row, request.message)


@app.get("/tasks/{task_id}", response_model=A2ATask, dependencies=[Depends(require_api_key)])
def read_task(task_id: str) -> A2ATask:
    row = get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return _task_from_db(row)


@app.get("/tasks/{task_id}/traces", dependencies=[Depends(require_api_key)])
def read_task_traces(task_id: str) -> dict[str, Any]:
    if get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task_id": task_id, "traces": get_agent_traces(task_id)}


@app.get("/tasks/{task_id}/events", dependencies=[Depends(require_api_key)])
async def task_events(task_id: str) -> StreamingResponse:
    async def event_stream():
        last_status = None
        while True:
            row = get_task(task_id)
            if row is None:
                yield "event: error\ndata: {\"error\":\"Task not found\"}\n\n"
                return
            if row["status"] != last_status:
                last_status = row["status"]
                yield f"event: status\ndata: {json.dumps(row, default=str)}\n\n"
            if row["status"] in {"completed", "failed", "partial"}:
                return
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
