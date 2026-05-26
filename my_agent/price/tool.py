from __future__ import annotations

import os
from typing import Any, Dict, Literal

import pandas as pd
import requests
from cachetools import TTLCache, cached

from ..orchestration.contracts import model_to_dict, normalize_tool_result

price_cache = TTLCache(maxsize=100, ttl=300)

FMP_BASE = "https://financialmodelingprep.com/api/v3"

Interval = Literal["1d"]
Period = Literal["1mo", "3mo"]


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
    clean_symbol = (symbol or "").strip().upper()
    if not clean_symbol or clean_symbol == "UNKNOWN":
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": "Missing stock symbol."}))

    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": "FMP_API_KEY not set."}))

    try:
        quote_resp = requests.get(f"{FMP_BASE}/quote/{clean_symbol}", params={"apikey": api_key}, timeout=10)
        quote_resp.raise_for_status()
        quote_data = quote_resp.json()
        if not quote_data:
            return model_to_dict(normalize_tool_result({"status": "error", "error_message": f"No data for {clean_symbol}."}))
        quote = quote_data[0]

        hist_resp = requests.get(f"{FMP_BASE}/historical-price-full/{clean_symbol}", params={"timeseries": 60, "apikey": api_key}, timeout=10)
        hist_resp.raise_for_status()
        hist_data = hist_resp.json().get("historical", [])
        if not hist_data:
            return model_to_dict(normalize_tool_result({"status": "error", "error_message": f"No historical data for {clean_symbol}."}))

        close = pd.Series([h["close"] for h in reversed(hist_data)], dtype=float)
        ema20 = float(ema(close, 20).iloc[-1])
        ema50 = float(ema(close, 50).iloc[-1])
        rsi14 = float(rsi(close, 14).iloc[-1])

        trend = "Uptrend (EMA20 > EMA50)" if ema20 > ema50 else "Downtrend (EMA20 < EMA50)"
        if rsi14 > 70:
            trend += " | Overbought RSI>70"
        elif rsi14 < 30:
            trend += " | Oversold RSI<30"

        price = float(quote.get("price", 0))
        prev = float(quote.get("previousClose", price))
        change = float(quote.get("change", 0))
        change_pct = float(quote.get("changesPercentage", 0))
        currency = quote.get("currency", "USD")

        return model_to_dict(normalize_tool_result({
            "status": "success",
            "data": {
                "symbol": clean_symbol,
                "snapshot": {
                    "symbol": clean_symbol,
                    "price": price,
                    "currency": currency,
                    "change": change,
                    "change_percent": change_pct,
                    "timestamp": quote.get("timestamp", ""),
                },
                "technicals": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "rsi14": rsi14,
                    "trend_hint": trend,
                },
                "meta": {"period": period, "interval": interval, "rows": len(hist_data)},
            },
        }))

    except requests.exceptions.Timeout:
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": "Timeout fetching FMP data."}))
    except Exception as exc:
        return model_to_dict(normalize_tool_result({"status": "error", "error_message": f"FMP error: {exc}"}))