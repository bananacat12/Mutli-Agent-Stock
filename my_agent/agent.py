from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from google import genai
from google.adk.agents.llm_agent import Agent

from .memory.store import build_context, create_task, save_message, update_task
from .news.agent import create_news_agent
from .news.tool import get_news
from .orchestration.contracts import AgentResponse, TaskRecord, model_to_dict
from .orchestration.executor import AgentExecutor
from .orchestration.planner import build_plan, sanitize_user_text
from .price.agent import create_price_agent
from .price.tool import get_price
from .sentiment.agent import create_sentiment_agent
from .sentiment.tool import reddit_social_sentiment


def create_agent() -> Agent:
    price_agent = create_price_agent()
    news_agent = create_news_agent()
    sentiment_agent = create_sentiment_agent()

    return Agent(
        model="gemini-2.5-pro",
        name="root_agent",
        description="Orchestrator and advisor that coordinates price, news, and sentiment agents.",
        instruction=(
            "You are the root stock-advisor orchestrator. The application layer performs deterministic planning, "
            "parallel subagent execution, tracing, and schema validation before you receive data. "
            "Use only the provided subagent results. Return a concise BUY/HOLD/SELL-style view when enough evidence "
            "exists, otherwise ask for the missing ticker or clarification. This is not financial advice."
        ),
        sub_agents=[price_agent, news_agent, sentiment_agent],
    )


def _summarize_tool_data(agent_name: str, result: dict[str, Any]) -> str:
    status = result.get("status")
    data = result.get("data") or {}
    if status == "error":
        return f"ERROR - {result.get('error')}"
    if agent_name == "price_agent":
        snapshot = data.get("snapshot", {})
        technicals = data.get("technicals", {})
        change_percent = snapshot.get("change_percent")
        change_text = f"{change_percent:.2f}%" if isinstance(change_percent, (int, float)) else "n/a"
        return (
            f"{data.get('symbol')}: price={snapshot.get('price')} {snapshot.get('currency')}, "
            f"change={change_text}, "
            f"EMA20={technicals.get('ema20')}, EMA50={technicals.get('ema50')}, "
            f"RSI14={technicals.get('rsi14')}, trend={technicals.get('trend_hint')}"
        )
    if agent_name == "news_agent":
        articles = data.get("articles", [])[:3]
        titles = "; ".join(filter(None, [article.get("title") for article in articles]))
        return f"{data.get('keyword')}: {data.get('count', 0)} recent articles. {titles}"
    if agent_name == "reddit_sentiment_agent":
        return (
            f"{data.get('query')}: mean_score={data.get('mean_score')}, "
            f"pos={data.get('pos')}, neu={data.get('neu')}, neg={data.get('neg')}. {data.get('note') or ''}"
        ).strip()
    return str(result)


def _price_runner(payload: dict[str, Any]) -> dict[str, Any]:
    result = get_price(
        payload.get("symbol") or payload.get("ticker"),
        payload.get("period", "1mo"),
        payload.get("interval", "1d"),
    )
    return {"tool_result": result, "text": _summarize_tool_data("price_agent", result)}


def _news_runner(payload: dict[str, Any]) -> dict[str, Any]:
    result = get_news(payload.get("keyword") or payload.get("ticker"), int(payload.get("days", 3)))
    return {"tool_result": result, "text": _summarize_tool_data("news_agent", result)}


def _sentiment_runner(payload: dict[str, Any]) -> dict[str, Any]:
    result = reddit_social_sentiment(payload.get("query") or payload.get("ticker"), int(payload.get("max_items", 60)))
    return {"tool_result": result, "text": _summarize_tool_data("reddit_sentiment_agent", result)}


def _create_agent_map() -> dict[str, Any]:
    return {
        "price_agent": _price_runner,
        "news_agent": _news_runner,
        "reddit_sentiment_agent": _sentiment_runner,
    }


def _run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("handle_user_message_v2 cannot be called synchronously from a running event loop.")


def _status_from_results(results: list[AgentResponse]) -> str:
    if all(result.status == "success" for result in results):
        return "completed"
    if any(result.status == "success" for result in results):
        return "partial"
    return "failed"


def _fallback_summarize_results(user_text: str, results: list[AgentResponse]) -> str:
    if not results:
        return "I could not create an agent plan. Please provide a stock ticker or company name."

    lines = ["Multi-agent result:"]
    for result in results:
        if result.status == "success":
            text = result.data.get("text") if isinstance(result.data, dict) else None
            lines.append(f"- {result.agent_name}: {text or result.data}")
        else:
            lines.append(f"- {result.agent_name}: ERROR - {result.error}")

    if any(result.status == "success" for result in results):
        lines.append("Recommendation: HOLD unless price, news, and sentiment evidence clearly align.")
    else:
        lines.append("Recommendation: unable to evaluate because all subagents failed.")
    return "\n".join(lines)


def _synthesis_api_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def _compact_result(result: AgentResponse) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_name": result.agent_name,
        "status": result.status,
        "error": result.error,
        "latency_ms": result.latency_ms,
    }
    if isinstance(result.data, dict):
        payload["summary"] = result.data.get("text")
        tool_result = result.data.get("tool_result")
        if isinstance(tool_result, dict):
            payload["tool_status"] = tool_result.get("status")
            payload["tool_data"] = tool_result.get("data")
            payload["tool_error"] = tool_result.get("error")
        else:
            payload["data"] = result.data
    else:
        payload["data"] = result.data
    return payload


def _build_synthesis_prompt(user_text: str, results: list[AgentResponse]) -> str:
    evidence = json.dumps([_compact_result(result) for result in results], ensure_ascii=False, default=str)
    if len(evidence) > 12000:
        evidence = evidence[:12000] + "... [TRUNCATED]"
    return (
        "You are the root stock-advisor orchestrator in a multi-agent system. "
        "Synthesize only the provided subagent evidence. Do not invent prices, news, sentiment, sources, or dates. "
        "If evidence is missing or conflicting, say so clearly. This is not financial advice.\n\n"
        "Return a concise answer with these sections:\n"
        "1. Verdict: BUY, HOLD, SELL, or INSUFFICIENT DATA\n"
        "2. Evidence: price, news, and sentiment bullets when available\n"
        "3. Risks / missing data\n\n"
        f"User request: {user_text}\n\n"
        f"Subagent results JSON:\n{evidence}"
    )


def _call_synthesis_llm(user_text: str, results: list[AgentResponse]) -> str | None:
    api_key = _synthesis_api_key()
    if not api_key or not results:
        return None

    model = os.getenv("ROOT_SYNTHESIS_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=_build_synthesis_prompt(user_text, results),
    )
    text = getattr(response, "text", None)
    return text.strip() if isinstance(text, str) and text.strip() else None


async def _summarize_results(user_text: str, results: list[AgentResponse]) -> str:
    if not results:
        return _fallback_summarize_results(user_text, results)
    try:
        llm_reply = await asyncio.to_thread(_call_synthesis_llm, user_text, results)
    except Exception:
        llm_reply = None
    return llm_reply or _fallback_summarize_results(user_text, results)


async def handle_user_message_v2_async(
    conversation_id: str,
    text: str,
    meta: dict[str, Any] | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    clean_text = sanitize_user_text(text)
    task_kwargs: dict[str, Any] = {
        "conversation_id": conversation_id,
        "input": {"text": clean_text, "meta": meta or {}},
    }
    if task_id:
        task_kwargs["task_id"] = task_id
    if trace_id:
        task_kwargs["trace_id"] = trace_id
    task = TaskRecord(**task_kwargs)
    create_task(task)
    save_message(conversation_id, "user", clean_text, {**(meta or {}), "task_id": task.task_id, "trace_id": task.trace_id})

    try:
        context = build_context(conversation_id, limit=5)
        requests = build_plan(
            conversation_id=conversation_id,
            task_id=task.task_id,
            trace_id=task.trace_id,
            user_text=clean_text,
            facts=context.get("facts", {}),
        )
        update_task(task.task_id, "working", {"planned_agents": [request.agent_name for request in requests]})
        executor = AgentExecutor(_create_agent_map(), max_steps=3, max_retries=2)
        results = await executor.execute(requests)
        status = _status_from_results(results)
        reply = await _summarize_results(clean_text, results)
        output = {
            "trace_id": task.trace_id,
            "task_id": task.task_id,
            "status": status,
            "reply": reply,
            "agent_results": [model_to_dict(result) for result in results],
        }
        update_task(task.task_id, status, output)
        save_message(conversation_id, "assistant", reply, {**(meta or {}), "task_id": task.task_id, "trace_id": task.trace_id})
        return output
    except Exception as exc:
        error = str(exc)
        reply = f"System Error: agent workflow failed - {error}"
        output = {
            "trace_id": task.trace_id,
            "task_id": task.task_id,
            "status": "failed",
            "reply": reply,
            "agent_results": [],
            "error": error,
        }
        update_task(task.task_id, "failed", output, error)
        save_message(conversation_id, "assistant", reply, {**(meta or {}), "task_id": task.task_id, "trace_id": task.trace_id})
        return output


def handle_user_message_v2(
    conversation_id: str,
    text: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _run_sync(handle_user_message_v2_async(conversation_id, text, meta))


def handle_user_message(session_id: str, text: str, meta: dict[str, Any] | None = None) -> str:
    """Backward-compatible string API for CLI/Web/Telegram integrations."""
    try:
        return str(handle_user_message_v2(session_id, text, meta).get("reply", ""))
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"System Error: agent workflow failed - {exc}"


root_agent = create_agent()
