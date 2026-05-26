from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from cachetools import TTLCache, cached

from ..orchestration.contracts import model_to_dict, normalize_tool_result
from ..security.http_client import safe_get, safe_post

sentiment_cache = TTLCache(maxsize=100, ttl=300)

RD_TIMEOUT = int(os.getenv("RD_TIMEOUT", "10"))
SENTI_TIMEOUT = int(os.getenv("SENTI_TIMEOUT", "10"))
SENTI_SLEEP_MS = int(os.getenv("SENTI_SLEEP_MS", "120"))
SENTI_ENDPOINT = os.getenv("SENTI_ENDPOINT", "https://sentim-api.herokuapp.com/api/v1/")
REDDIT_SUBS_CSV = os.getenv("REDDIT_SUBS", "stocks,wallstreetbets,investing")
MIN_SUCCESS = int(os.getenv("SENTI_MIN_SUCCESS", "5"))
SENTI_RETRY = int(os.getenv("SENTI_RETRY", "1"))


def _safe(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    return str(value)


def _dedup_keep_order(texts: List[str]) -> List[str]:
    seen = set()
    output = []
    for text in texts:
        cleaned = (text or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


def _fetch_reddit(query: str, limit: int) -> List[str]:
    subs = [sub.strip() for sub in (REDDIT_SUBS_CSV or "").split(",") if sub.strip()]
    subs = subs or ["stocks", "wallstreetbets", "investing"]
    per_sub = max(1, min(max(1, limit) // max(1, len(subs)), 25))
    headers = {"User-Agent": "adk-reddit-sentiment/1.0"}
    texts: List[str] = []

    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=1&sort=new&limit={per_sub}"
        try:
            response = safe_get(url, headers=headers, timeout=RD_TIMEOUT)
            if response.status_code == 429:
                time.sleep(1.0)
                continue
            response.raise_for_status()
            children = (response.json().get("data", {}) or {}).get("children", []) or []
            for child in children:
                data = child.get("data", {}) or {}
                title = (data.get("title") or "").strip()
                selftext = (data.get("selftext") or "").strip()
                text = title if title else selftext
                if text:
                    texts.append(text)
        except Exception:
            continue

    return _dedup_keep_order(texts)


def _sentim_once(text: str, endpoint: str) -> Dict[str, Any]:
    url = endpoint.rstrip("/") + "/"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    response = safe_post(url, json={"text": text}, headers=headers, timeout=SENTI_TIMEOUT)
    response.raise_for_status()
    try:
        payload = response.json()
    except Exception:
        payload = {}
    result = payload.get("result", {}) or {}
    return {"label": str(result.get("type", "neutral")), "score": float(result.get("polarity", 0.0))}


def _sentim(text: str, endpoint: str) -> Dict[str, Any]:
    last_error = None
    for attempt in range(max(1, SENTI_RETRY)):
        try:
            return _sentim_once(text, endpoint)
        except Exception as exc:
            last_error = exc
            time.sleep(min(0.2 * (2**attempt), 2.0))
    raise last_error or RuntimeError("Sentim failed")


_POS = {
    "bull",
    "bullish",
    "buy",
    "bought",
    "call",
    "calls",
    "upgrade",
    "rally",
    "beat",
    "breakout",
    "support",
    "ath",
    "moon",
    "strong",
    "surge",
    "green",
}
_NEG = {
    "bear",
    "bearish",
    "sell",
    "sold",
    "put",
    "puts",
    "downgrade",
    "dump",
    "miss",
    "breakdown",
    "resistance",
    "crash",
    "tank",
    "weak",
    "red",
    "fud",
}


def _rule_score(text: str) -> float:
    lowered = text.lower()
    score = 0
    for word in _POS:
        if word in lowered:
            score += 1
    for word in _NEG:
        if word in lowered:
            score -= 1
    if score > 0:
        return min(1.0, 0.2 * score)
    if score < 0:
        return max(-1.0, 0.2 * score)
    return 0.0


@cached(cache=sentiment_cache)
def reddit_social_sentiment(
    query: str,
    max_items: int = 60,
    endpoint: str = "",
    min_success: int = 0,
    degraded_mode: bool = True,
) -> Dict[str, Any]:
    """Collect Reddit posts and score sentiment through Sentim with a rule-based fallback."""
    clean_query = (query or "").strip().upper()
    if not clean_query or clean_query == "UNKNOWN":
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": "Missing query."}))

    item_count = max(1, min(int(max_items or 60), 60))
    texts = _fetch_reddit(clean_query, item_count)

    if not texts:
        return model_to_dict(
            normalize_tool_result(
                {
                    "status": "error",
                    "error_message": "No matching Reddit posts were found.",
                    "data": {"source": "reddit", "total": 0},
                }
            )
        )

    sentim_endpoint = (endpoint or SENTI_ENDPOINT).strip()
    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    consecutive_errors = 0

    for index, text in enumerate(texts[:item_count]):
        try:
            result = _sentim(text, sentim_endpoint)
            results.append({"text": text, "label": result["label"], "score": result["score"]})
            consecutive_errors = 0
        except Exception as exc:
            errors.append(str(exc))
            results.append({"text": text, "label": "neutral", "score": 0.0, "error": str(exc)})
            consecutive_errors += 1
            if degraded_mode and consecutive_errors >= 3:
                break
        if index + 1 < len(texts) and SENTI_SLEEP_MS > 0:
            time.sleep(SENTI_SLEEP_MS / 1000.0)

    valid = [result for result in results if "error" not in result]
    minimum_success = int(min_success or 0) or MIN_SUCCESS

    if len(valid) < minimum_success:
        if not degraded_mode:
            return model_to_dict(
                normalize_tool_result(
                    {
                        "status": "error",
                        "error_message": f"Not enough valid sentiment samples (ok={len(valid)} < min={minimum_success}).",
                        "data": {
                            "source": "reddit",
                            "total": len(results),
                            "success_count": len(valid),
                            "failed_count": len(results) - len(valid),
                        },
                    }
                )
            )
        fallback = []
        for text in texts[:item_count]:
            score = _rule_score(text)
            label = "positive" if score > 0.05 else ("negative" if score < -0.05 else "neutral")
            fallback.append({"text": text, "label": label, "score": score})
        return _summary_payload("partial", clean_query, fallback, 0, len(results), errors, "Used rule-based fallback.")

    return _summary_payload("success", clean_query, valid, len(valid), len(results) - len(valid), errors, None)


def _summary_payload(
    status: str,
    query: str,
    rows: list[dict[str, Any]],
    success_count: int,
    failed_count: int,
    errors: list[str],
    note: str | None,
) -> Dict[str, Any]:
    pos = sum(1 for row in rows if row["label"] == "positive")
    neg = sum(1 for row in rows if row["label"] == "negative")
    neu = sum(1 for row in rows if row["label"] == "neutral")
    mean = sum(float(row["score"]) for row in rows) / max(1, len(rows))
    top_pos = sorted(rows, key=lambda row: row["score"], reverse=True)[:3]
    top_neg = sorted(rows, key=lambda row: row["score"])[:3]
    return model_to_dict(
        normalize_tool_result(
            {
                "status": status,
                "data": {
                    "source": "reddit",
                    "query": query,
                    "total": len(rows),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "mean_score": round(mean, 3),
                    "pos": int(pos),
                    "neu": int(neu),
                    "neg": int(neg),
                    "top_pos": _safe(top_pos),
                    "top_neg": _safe(top_neg),
                    "samples": _safe(rows[:10]),
                    "errors": _safe(errors),
                    "note": note,
                },
            }
        )
    )
