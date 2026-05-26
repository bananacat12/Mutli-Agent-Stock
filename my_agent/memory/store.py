from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from ..db.core import get_engine, init_db
from ..orchestration.contracts import AgentRequest, AgentResponse, TaskRecord, model_to_dict

_db_initialized = False


def ensure_db_init() -> None:
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=True, default=str)


def _truncate(content: str, limit: int = 1000) -> str:
    if len(content) <= limit:
        return content
    return content[:limit] + "... [TRUNCATED]"


def save_message(session_id: str, role: str, content: str, meta: dict[str, Any] | None = None) -> None:
    ensure_db_init()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """INSERT INTO messages(session_id, role, content, meta)
                   VALUES (:s, :r, :c, CAST(:m AS JSONB))"""
            ),
            {"s": session_id, "r": role, "c": content, "m": _json(meta)},
        )


def get_history(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_db_init()
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """SELECT role, content, meta, created_at
                   FROM messages
                   WHERE session_id = :s
                   ORDER BY id DESC
                   LIMIT :lim"""
            ),
            {"s": session_id, "lim": limit},
        ).all()
    formatted: list[dict[str, Any]] = []
    for row in reversed(rows):
        formatted.append(
            {
                "role": row[0],
                "content": _truncate(row[1]),
                "meta": row[2],
                "created_at": row[3].isoformat(),
            }
        )
    return formatted


def build_context(conversation_id: str, limit: int = 5) -> dict[str, Any]:
    return {
        "history": get_history(conversation_id, limit=limit),
        "facts": get_facts(conversation_id),
    }


def clear_session(session_id: str) -> None:
    ensure_db_init()
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM messages WHERE session_id=:s"), {"s": session_id})
        conn.execute(text("DELETE FROM facts WHERE session_id=:s"), {"s": session_id})
        conn.execute(text("DELETE FROM tasks WHERE conversation_id=:s"), {"s": session_id})


def upsert_fact(session_id: str, k: str, v: str) -> None:
    ensure_db_init()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """INSERT INTO facts(session_id,k,v)
                   VALUES (:s,:k,:v)
                   ON CONFLICT (session_id,k)
                   DO UPDATE SET v=EXCLUDED.v, updated_at=NOW()"""
            ),
            {"s": session_id, "k": k, "v": v},
        )


def get_facts(session_id: str) -> dict[str, str]:
    ensure_db_init()
    with get_engine().begin() as conn:
        rows = conn.execute(text("SELECT k,v FROM facts WHERE session_id=:s"), {"s": session_id}).all()
    return {k: v for k, v in rows}


def create_task(task: TaskRecord) -> None:
    ensure_db_init()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """INSERT INTO tasks(task_id, conversation_id, trace_id, status, input, output, error)
                   VALUES (:task_id, :conversation_id, :trace_id, :status, CAST(:input AS JSONB),
                           CAST(:output AS JSONB), :error)
                   ON CONFLICT (task_id) DO UPDATE
                   SET status=EXCLUDED.status, input=EXCLUDED.input, output=EXCLUDED.output,
                       error=EXCLUDED.error, updated_at=NOW()"""
            ),
            {
                "task_id": task.task_id,
                "conversation_id": task.conversation_id,
                "trace_id": task.trace_id,
                "status": task.status,
                "input": _json(task.input),
                "output": _json(task.output),
                "error": task.error,
            },
        )


def update_task(task_id: str, status: str, output: dict[str, Any] | None = None, error: str | None = None) -> None:
    ensure_db_init()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """UPDATE tasks
                   SET status=:status, output=CAST(:output AS JSONB), error=:error, updated_at=NOW()
                   WHERE task_id=:task_id"""
            ),
            {"task_id": task_id, "status": status, "output": _json(output), "error": error},
        )


def get_task(task_id: str) -> dict[str, Any] | None:
    ensure_db_init()
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                """SELECT task_id, conversation_id, trace_id, status, input, output, error, created_at, updated_at
                   FROM tasks
                   WHERE task_id=:task_id"""
            ),
            {"task_id": task_id},
        ).first()
    if row is None:
        return None
    return {
        "task_id": row[0],
        "conversation_id": row[1],
        "trace_id": row[2],
        "status": row[3],
        "input": row[4],
        "output": row[5],
        "error": row[6],
        "created_at": row[7].isoformat(),
        "updated_at": row[8].isoformat(),
    }


def get_agent_traces(task_id: str) -> list[dict[str, Any]]:
    ensure_db_init()
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """SELECT trace_id, task_id, agent_name, input, output, status, latency_ms, token_count, cost_usd, error, created_at
                   FROM agent_traces
                   WHERE task_id=:task_id
                   ORDER BY id ASC"""
            ),
            {"task_id": task_id},
        ).all()
    return [
        {
            "trace_id": row[0],
            "task_id": row[1],
            "agent_name": row[2],
            "input": row[3],
            "output": row[4],
            "status": row[5],
            "latency_ms": row[6],
            "token_count": row[7],
            "cost_usd": float(row[8]) if row[8] is not None else None,
            "error": row[9],
            "created_at": row[10].isoformat(),
        }
        for row in rows
    ]


def save_agent_trace(request: AgentRequest, response: AgentResponse) -> None:
    ensure_db_init()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """INSERT INTO agent_traces(
                     trace_id, task_id, agent_name, input, output, status,
                     latency_ms, token_count, cost_usd, error
                   )
                   VALUES (
                     :trace_id, :task_id, :agent_name, CAST(:input AS JSONB),
                     CAST(:output AS JSONB), :status, :latency_ms,
                     :token_count, :cost_usd, :error
                   )"""
            ),
            {
                "trace_id": response.trace_id,
                "task_id": response.task_id,
                "agent_name": response.agent_name,
                "input": _json(model_to_dict(request)),
                "output": _json(model_to_dict(response)),
                "status": response.status,
                "latency_ms": response.latency_ms,
                "token_count": response.token_count,
                "cost_usd": response.cost_usd,
                "error": response.error,
            },
        )
