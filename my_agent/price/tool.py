from __future__ import annotations

import os
from typing import Any, Dict, Literal

import pandas as pd
import requests
import yfinance as yf
from cachetools import TTLCache, cached

from ..orchestration.contracts import model_to_dict, normalize_tool_result

price_cache = TTLCache(maxsize=100, ttl=300)
AV_BASE = "https://www.alphavantage.co/query"

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

    av_error = None
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if api_key:
        try:
            # Lấy giá hiện tại
            quote_resp = requests.get(AV_BASE, params={
                "function": "GLOBAL_QUOTE",
                "symbol": clean_symbol,
                "apikey": api_key
            }, timeout=10)
            quote_resp.raise_for_status()
            quote = quote_resp.json().get("Global Quote", {})
            if quote:
                # Lấy lịch sử để tính EMA/RSI
                hist_resp = requests.get(AV_BASE, params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": clean_symbol,
                    "outputsize": "compact",
                    "apikey": api_key
                }, timeout=10)
                hist_resp.raise_for_status()
                hist_data = hist_resp.json().get("Time Series (Daily)", {})
                if hist_data:
                    closes = [float(v["4. close"]) for v in list(hist_data.values())[:60]]
                    close = pd.Series(list(reversed(closes)), dtype=float)
                    ema20 = float(ema(close, 20).iloc[-1])
                    ema50 = float(ema(close, 50).iloc[-1])
                    rsi14 = float(rsi(close, 14).iloc[-1])

                    trend = "Uptrend (EMA20 > EMA50)" if ema20 > ema50 else "Downtrend (EMA20 < EMA50)"
                    if rsi14 > 70:
                        trend += " | Overbought RSI>70"
                    elif rsi14 < 30:
                        trend += " | Oversold RSI<30"

                    price = float(quote.get("05. price", 0))
                    prev = float(quote.get("08. previous close", price))
                    change = float(quote.get("09. change", 0))
                    change_pct = float(quote.get("10. change percent", "0%").replace("%", ""))

                    return model_to_dict(normalize_tool_result({
                        "status": "success",
                        "data": {
                            "symbol": clean_symbol,
                            "snapshot": {
                                "symbol": clean_symbol,
                                "price": price,
                                "currency": "USD",
                                "change": change,
                                "change_percent": change_pct,
                                "timestamp": quote.get("07. latest trading day", ""),
                            },
                            "technicals": {
                                "ema20": ema20,
                                "ema50": ema50,
                                "rsi14": rsi14,
                                "trend_hint": trend,
                            },
                            "meta": {"period": period, "interval": interval, "rows": len(closes)},
                        },
                    }))
                else:
                    av_error = f"No historical data for {clean_symbol}."
            else:
                av_error = f"No quote data for {clean_symbol}."
        except requests.exceptions.Timeout:
            av_error = "Timeout fetching Alpha Vantage data."
        except Exception as exc:
            av_error = f"Alpha Vantage error: {exc}"
    else:
        av_error = "ALPHAVANTAGE_API_KEY not set."

    # Fallback to yfinance if Alpha Vantage failed, returned empty, or key was missing
    try:
        ticker = yf.Ticker(clean_symbol)
        hist = ticker.history(period="3mo", interval="1d")
        if hist.empty:
            return model_to_dict(normalize_tool_result({
                "status": "error",
                "error_message": f"No data found for {clean_symbol} via yfinance (Alpha Vantage failed: {av_error})."
            }))

        close_series = hist['Close'].tail(60)
        price = float(close_series.iloc[-1])
        prev = float(close_series.iloc[-2]) if len(close_series) > 1 else price
        change = price - prev
        change_pct = (change / prev) * 100 if prev != 0 else 0.0
        timestamp = close_series.index[-1].strftime("%Y-%m-%d")

        close = pd.Series(close_series.values, dtype=float)
        ema20 = float(ema(close, 20).iloc[-1])
        ema50 = float(ema(close, 50).iloc[-1])
        rsi14 = float(rsi(close, 14).iloc[-1])

        trend = "Uptrend (EMA20 > EMA50)" if ema20 > ema50 else "Downtrend (EMA20 < EMA50)"
        if rsi14 > 70:
            trend += " | Overbought RSI>70"
        elif rsi14 < 30:
            trend += " | Oversold RSI<30"

        return model_to_dict(normalize_tool_result({
            "status": "success",
            "data": {
                "symbol": clean_symbol,
                "snapshot": {
                    "symbol": clean_symbol,
                    "price": price,
                    "currency": "USD",
                    "change": change,
                    "change_percent": change_pct,
                    "timestamp": timestamp,
                },
                "technicals": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "rsi14": rsi14,
                    "trend_hint": trend,
                },
                "meta": {"period": period, "interval": interval, "rows": len(close_series)},
            },
        }))
    except Exception as yf_exc:
        return model_to_dict(normalize_tool_result({
            "status": "error",
            "error_message": f"yfinance error: {yf_exc} (Alpha Vantage failed: {av_error})"
        }))