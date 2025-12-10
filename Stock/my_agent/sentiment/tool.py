# ============================================================
# FILE 3: my_agent/sentiment/tool.py
# ============================================================
import os, time, math
from typing import Any, Dict, List
import requests
import sys


def _log(msg: str) -> None:
    """Ghi log ra stderr để không làm bẩn STDIO MCP."""
    print(msg, file=sys.stderr, flush=True)


# SỬA: Đổi từ relative sang absolute import
try:
    from cache import get_cache, set_cache
    _log("✅ Sentiment tool đã import cache thành công.")
except ImportError:
    _log("⚠️ Lỗi import cache, sentiment_tool sẽ chạy không có cache.")

    def get_cache(key: str):
        return None

    def set_cache(key: str, value: Any, expiration_sec: int):
        pass


RD_TIMEOUT      = int(os.getenv("RD_TIMEOUT", "10"))
SENTI_TIMEOUT   = int(os.getenv("SENTI_TIMEOUT", "10"))
SENTI_SLEEP_MS  = int(os.getenv("SENTI_SLEEP_MS", "120"))
SENTI_ENDPOINT  = os.getenv("SENTI_ENDPOINT", "http://147.50.231.17:8000/v1/sentiment")
REDDIT_SUBS_CSV = os.getenv("REDDIT_SUBS", "stocks,wallstreetbets,investing")
MIN_SUCCESS     = int(os.getenv("SENTI_MIN_SUCCESS", "5"))
SENTI_RETRY     = int(os.getenv("SENTI_RETRY", "1"))


def _clean_json_nan(data: Any) -> Any:
    if isinstance(data, (float, int)):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    if isinstance(data, dict):
        return {k: _clean_json_nan(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_clean_json_nan(item) for item in data]
    return data


def _safe(v: Any):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, list):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _safe(v) for k, v in v.items()}
    return str(v)


def _dedup_keep_order(texts: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for t in texts:
        s = (t or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _fetch_reddit(query: str, limit: int) -> List[str]:
    subs = [s.strip() for s in (REDDIT_SUBS_CSV or "").split(",") if s.strip()] or \
           ["stocks", "wallstreetbets", "investing"]
    per_sub = max(1, min(max(1, limit) // max(1, len(subs)), 25))
    headers = {"User-Agent": "adk-reddit-sentiment/1.0"}
    texts: List[str] = []

    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=1&sort=new&limit={per_sub}"
        try:
            r = requests.get(url, headers=headers, timeout=RD_TIMEOUT)
            if r.status_code == 429:
                time.sleep(1.0)
                continue
            r.raise_for_status()
            js = r.json()
            children = (js.get("data", {}) or {}).get("children", []) or []
            for c in children:
                d = c.get("data", {}) or {}
                title = (d.get("title") or "").strip()
                selftext = (d.get("selftext") or "").strip()
                t = title if title else selftext
                if t:
                    texts.append(t)
        except Exception:
            continue

    return _dedup_keep_order(texts)


def _sentim_once(text: str, endpoint: str) -> Dict[str, Any]:
    url = endpoint.rstrip("/") + "/"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    r = requests.post(url, json={"text": text}, headers=headers, timeout=SENTI_TIMEOUT)
    r.raise_for_status()
    js: Dict[str, Any] = {}
    try:
        js = r.json()
    except Exception:
        pass
    res = js.get("result", {}) or {}
    return {"label": str(res.get("type", "neutral")), "score": float(res.get("polarity", 0.0))}


def _sentim(text: str, endpoint: str) -> Dict[str, Any]:
    last: Exception | None = None
    for _ in range(max(1, SENTI_RETRY)):
        try:
            return _sentim_once(text, endpoint)
        except Exception as e:
            last = e
            time.sleep(0.2)
    raise last or RuntimeError("Sentim failed")


_POS = {
    "bull", "bullish", "buy", "bought", "call", "calls", "upgrade", "rally",
    "beat", "breakout", "support", "ath", "moon", "strong", "surge", "green"
}
_NEG = {
    "bear", "bearish", "sell", "sold", "put", "puts", "downgrade", "dump",
    "miss", "breakdown", "resistance", "crash", "tank", "weak", "red", "fud"
}


def _rule_score(text: str) -> float:
    t = text.lower()
    score = 0
    for w in _POS:
        if w in t:
            score += 1
    for w in _NEG:
        if w in t:
            score -= 1
    if score > 0:
        return min(1.0, 0.2 * score)
    if score < 0:
        return max(-1.0, 0.2 * score)
    return 0.0


def reddit_social_sentiment(
    query: str,
    max_items: int = 60,
    endpoint: str = "",
    min_success: int = 0,
    degraded_mode: bool = True
) -> Dict[str, Any]:
    """Lấy bài viết Reddit rồi chấm sentiment (Sentim). Đã bọc cache."""
    q_norm = (query or "").strip().upper()
    mi_norm = max(1, min(int(max_items or 60), 60))
    ep_norm = (endpoint or SENTI_ENDPOINT).strip()
    ms_norm = int(min_success or 0) or MIN_SUCCESS
    dm_norm = bool(degraded_mode)

    cache_key = f"sentiment_tool:{q_norm}:{mi_norm}:{ep_norm}:{ms_norm}:{dm_norm}"
    cached_result = get_cache(cache_key)
    if cached_result:
        return cached_result

    _log(f"CACHE MISS: Đang gọi Reddit/Sentim API cho '{q_norm}'...")

    if not q_norm:
        result = {"status": "error", "error_message": "Thiếu 'query'."}
        set_cache(cache_key, result, expiration_sec=3600)
        return result

    texts = _fetch_reddit(q_norm, mi_norm)

    if not texts:
        result = {
            "status": "error",
            "error_message": "Không lấy được bài Reddit phù hợp.",
            "source": "reddit",
            "total": 0,
            "data": [],
        }
        set_cache(cache_key, result, expiration_sec=300)
        return result

    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i, t in enumerate(texts[:mi_norm]):
        try:
            res = _sentim(t, ep_norm)
            results.append({"text": t, "label": res["label"], "score": res["score"]})
        except Exception as e:
            errors.append(str(e))
            results.append({"text": t, "label": "neutral", "score": 0.0, "error": str(e)})
        if i + 1 < len(texts) and SENTI_SLEEP_MS > 0:
            time.sleep(SENTI_SLEEP_MS / 1000.0)

    ok = [r for r in results if "error" not in r]

    if len(ok) < ms_norm:
        if not dm_norm:
            result = {
                "status": "error",
                "error_message": f"Không đủ mẫu hợp lệ (ok={len(ok)} < min={ms_norm}).",
                "source": "reddit",
                "total": len(results),
                "success_count": len(ok),
                "failed_count": len(results) - len(ok),
                "data": [],
            }
            set_cache(cache_key, _clean_json_nan(result), expiration_sec=1800)
            return _clean_json_nan(result)

        rb: List[Dict[str, Any]] = []
        for t in texts[:mi_norm]:
            s = _rule_score(t)
            label = "positive" if s > 0.05 else ("negative" if s < -0.05 else "neutral")
            rb.append({"text": t, "label": label, "score": s})
        pos = sum(1 for d in rb if d["label"] == "positive")
        neg = sum(1 for d in rb if d["label"] == "negative")
        neu = sum(1 for d in rb if d["label"] == "neutral")
        mean = sum(d["score"] for d in rb) / max(1, len(rb))
        top_pos = sorted(rb, key=lambda d: d["score"], reverse=True)[:3]
        top_neg = sorted(rb, key=lambda d: d["score"])[:3]

        result = {
            "status": "success_degraded",
            "source": "reddit",
            "query": q_norm,
            "total": len(rb),
            "success_count": 0,
            "failed_count": len(results),
            "mean_score": round(mean, 3),
            "pos": int(pos),
            "neu": int(neu),
            "neg": int(neg),
            "top_pos": _safe(top_pos),
            "top_neg": _safe(top_neg),
            "samples": _safe(rb[:10]),
            "note": f"Sentim không đủ mẫu (ok={len(ok)} < min={ms_norm}), dùng rule-based.",
        }
        set_cache(cache_key, _clean_json_nan(result), expiration_sec=1800)
        return _clean_json_nan(result)

    pos = sum(1 for d in ok if d["label"] == "positive")
    neg = sum(1 for d in ok if d["label"] == "negative")
    neu = sum(1 for d in ok if d["label"] == "neutral")
    mean = sum(float(d["score"]) for d in ok) / max(1, len(ok))
    top_pos = sorted(ok, key=lambda d: d["score"], reverse=True)[:3]
    top_neg = sorted(ok, key=lambda d: d["score"])[:3]

    result = {
        "status": "success",
        "source": "reddit",
        "query": q_norm,
        "total": len(results),
        "success_count": len(ok),
        "failed_count": len(results) - len(ok),
        "mean_score": round(mean, 3),
        "pos": int(pos),
        "neu": int(neu),
        "neg": int(neg),
        "top_pos": _safe(top_pos),
        "top_neg": _safe(top_neg),
        "samples": _safe(results[:10]),
        "errors": _safe(errors),
    }

    clean_result = _clean_json_nan(result)
    set_cache(cache_key, clean_result, expiration_sec=1800)
    return clean_result
