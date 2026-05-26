# ============================================================
# FILE 1: my_agent/price/tool.py
# ============================================================
from typing import Dict, Any, Literal, List
import math
import numpy as np
import pandas as pd
import yfinance as yf
import sys


def _log(msg: str) -> None:
    """Ghi log ra stderr để không làm bẩn STDIO MCP."""
    print(msg, file=sys.stderr, flush=True)


# SỬA: Đổi từ relative sang absolute import
try:
    from cache import get_cache, set_cache
    _log("✅ Price tool đã import cache thành công.")
except ImportError:
    _log("⚠️ Lỗi import cache, price_tool sẽ chạy không có cache.")

    def get_cache(key: str):
        return None

    def set_cache(key: str, value: Any, expiration_sec: int):
        pass


Interval = Literal[
    "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h",
    "1d", "5d", "1wk", "1mo", "3mo"
]
Period = Literal[
    "1d", "5d", "1mo", "3mo", "6mo", "1y",
    "2y", "5y", "10y", "ytd", "max"
]


def _clean_json_nan(data: Any) -> Any:
    """Dọn dẹp NaN/Infinity trong dict/list."""
    if isinstance(data, (float, int)):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    if isinstance(data, dict):
        return {k: _clean_json_nan(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_clean_json_nan(item) for item in data]
    return data


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = -d.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def get_price(symbol: str, period: Period = "1mo", interval: Interval = "1d") -> Dict[str, Any]:
    """Trả về JSON giá thật từ Yahoo Finance + EMA/RSI + trend_hint."""
    cache_key = f"price_tool:{symbol}:{period}:{interval}"
    cached_result = get_cache(cache_key)
    if cached_result:
        return cached_result

    _log(f"CACHE MISS: Đang gọi API YFinance cho {symbol}...")

    try:
        tkr = yf.Ticker(symbol)
        hist = tkr.history(period=period, interval=interval, auto_adjust=False)
    except Exception as e:
        result = {"status": "error", "error_message": f"Lỗi truy vấn Yahoo: {e}"}
        set_cache(cache_key, _clean_json_nan(result), expiration_sec=10)
        return _clean_json_nan(result)

    if hist is None or hist.empty:
        result = {
            "status": "error",
            "error_message": f"Không có dữ liệu cho {symbol} ({period}, {interval}).",
        }
        set_cache(cache_key, result, expiration_sec=60)
        return result

    close = hist["Close"].astype(float)
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else None
    change = (price - prev) if prev is not None else 0.0
    change_pct = ((price / prev - 1.0) * 100.0) if prev is not None else 0.0

    ema20 = float(ema(close, 20).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1])
    rsi14 = float(rsi(close, 14).iloc[-1])

    trend = "Uptrend (EMA20 > EMA50)" if ema20 > ema50 else "Downtrend (EMA20 < EMA50)"

    if not math.isnan(rsi14):
        if rsi14 > 70:
            trend += " | Overbought RSI>70"
        elif rsi14 < 30:
            trend += " | Oversold RSI<30"
    else:
        trend += " | RSI(14) N/A"

    try:
        info = tkr.fast_info
        if isinstance(info, dict):
            currency = info.get("currency")
        else:
            currency = getattr(info, "currency", None)
    except Exception:
        currency = None

    result: Dict[str, Any] = {
        "status": "success",
        "symbol": symbol,
        "snapshot": {
            "symbol": symbol,
            "price": price,
            "currency": currency,
            "change": change,
            "change_percent": change_pct,
            "timestamp": hist.index[-1].to_pydatetime().isoformat(),
        },
        "technicals": {
            "ema20": ema20,
            "ema50": ema50,
            "rsi14": rsi14,
            "trend_hint": trend,
        },
        "meta": {"period": period, "interval": interval, "rows": len(hist)},
    }

    clean_result = _clean_json_nan(result)
    set_cache(cache_key, clean_result, expiration_sec=300)
    return clean_result
