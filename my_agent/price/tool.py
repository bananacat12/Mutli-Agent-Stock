from __future__ import annotations

from typing import Any, Dict, Literal

import pandas as pd
import yfinance as yf
from cachetools import TTLCache, cached

from ..orchestration.contracts import model_to_dict, normalize_tool_result

price_cache = TTLCache(maxsize=100, ttl=300)

Interval = Literal["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"]
Period = Literal["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=1).mean()
    loss = -delta.clip(upper=0).rolling(period, min_periods=1).mean()
    rs = gain / loss
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.where(loss != 0, 100.0)
    rsi_series = rsi_series.where((gain != 0) | (loss != 0), 50.0)
    return rsi_series


@cached(cache=price_cache)
def get_price(symbol: str, period: Period = "1mo", interval: Interval = "1d") -> Dict[str, Any]:
    """Return stock price, EMA, RSI, and a simple trend hint from Yahoo Finance."""
    clean_symbol = (symbol or "").strip().upper()
    if not clean_symbol or clean_symbol == "UNKNOWN":
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": "Missing stock symbol."}))

    try:
        ticker = yf.Ticker(clean_symbol)
        hist = ticker.history(period=period, interval=interval, auto_adjust=False)
    except Exception as exc:
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": f"Yahoo Finance error: {exc}"}))

    if hist is None or hist.empty:
        return model_to_dict(
            normalize_tool_result(
                {"status": "error", "error_message": f"No price data for {clean_symbol} ({period}, {interval})."}
            )
        )

    close = hist["Close"].astype(float)
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else None
    change = (price - prev) if prev else 0.0
    change_pct = ((price / prev - 1.0) * 100.0) if prev else 0.0
    ema20 = float(ema(close, 20).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1])
    rsi14 = float(rsi(close, 14).iloc[-1])

    trend = "Uptrend (EMA20 > EMA50)" if ema20 > ema50 else "Downtrend (EMA20 < EMA50)"
    if rsi14 > 70:
        trend += " | Overbought RSI>70"
    elif rsi14 < 30:
        trend += " | Oversold RSI<30"

    try:
        info = ticker.fast_info
        currency = getattr(info, "currency", None) if not isinstance(info, dict) else info.get("currency")
    except Exception:
        currency = None

    return model_to_dict(
        normalize_tool_result(
            {
                "status": "success",
                "data": {
                    "symbol": clean_symbol,
                    "snapshot": {
                        "symbol": clean_symbol,
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
                },
            }
        )
    )
