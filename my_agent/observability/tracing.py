from __future__ import annotations

import json
import logging
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in ("trace_id", "task_id", "agent", "status", "latency_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def get_logger(name: str = "my_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_agent_event(
    trace_id: str,
    task_id: str,
    agent: str,
    status: str,
    latency_ms: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    logger = get_logger()
    logger.info(
        "agent_call",
        extra={
            "trace_id": trace_id,
            "task_id": task_id,
            "agent": agent,
            "status": status,
            "latency_ms": latency_ms,
            **(extra or {}),
        },
    )
