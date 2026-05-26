from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

load_dotenv()

DB_URL = os.getenv("DB_URL")
_engine: Engine | None = None


def get_engine() -> Engine:
    """Create the database engine lazily so imports do not require DB_URL."""
    global _engine
    if _engine is None:
        db_url = os.getenv("DB_URL") or DB_URL
        if not db_url:
            raise RuntimeError("Missing DB_URL in .env")
        _engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


SQL_INIT = """
CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT CHECK(role IN ('user','assistant','tool')) NOT NULL,
  content TEXT NOT NULL,
  meta JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);

CREATE TABLE IF NOT EXISTS facts (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  k TEXT NOT NULL,
  v TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(session_id, k)
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  status TEXT CHECK(status IN ('submitted','working','completed','failed','partial')) NOT NULL,
  input JSONB NOT NULL,
  output JSONB,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id ON tasks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_trace_id ON tasks(trace_id);

CREATE TABLE IF NOT EXISTS agent_traces (
  id BIGSERIAL PRIMARY KEY,
  trace_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  input JSONB,
  output JSONB,
  status TEXT CHECK(status IN ('success','error','partial','skipped')) NOT NULL,
  latency_ms INTEGER,
  token_count INTEGER,
  cost_usd NUMERIC,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_traces_trace_id ON agent_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_task_id ON agent_traces(task_id);
"""


def init_db() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(SQL_INIT))


def ping() -> str:
    with get_engine().begin() as conn:
        return conn.execute(text("SELECT version()")).scalar()
