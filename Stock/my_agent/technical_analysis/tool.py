# my_agent/technical_analysis/tool.py
import yfinance as yf
import pandas_ta as ta
import pandas as pd
from typing import Dict, Any, List
import math
import sys


def _log(msg: str) -> None:
    """Ghi log ra stderr để không làm bẩn STDIO MCP."""
    print(msg, file=sys.stderr, flush=True)


try:
    from ..cache import get_cache, set_cache

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

    _log("✅ TA tool đã import cache thành công.")
except ImportError:
    def get_cache(key: str):
        return None

    def set_cache(key: str, value: Any, expiration_sec: int):
        pass

    def _clean_json_nan(data: Any):
        return data


def get_advanced_ta(symbol: str) -> Dict[str, Any]:
    """
    Phân tích kỹ thuật nâng cao (MACD, BBands, RSI, Stochastic, MA, ATR).
    """
    cache_key = f"ta_tool_v2:{symbol}"
    cached_result = get_cache(cache_key)
    if cached_result:
        return cached_result

    _log(f"CACHE MISS: Đang gọi API YFinance (TA) cho {symbol}...")

    try:
        # Lấy 1 năm dữ liệu để tính đường MA200 chính xác
        tkr = yf.Ticker(symbol)
        df = tkr.history(period="1y", interval="1d")

        if df.empty or len(df) < 50:
            result = {"status": "error", "message": f"Không đủ dữ liệu giá cho {symbol}."}
            set_cache(cache_key, result, expiration_sec=60)
            return result

    except Exception as e:
        result = {"status": "error", "message": f"Lỗi truy vấn YFinance: {e}"}
        set_cache(cache_key, result, expiration_sec=60)
        return result

    # --- TÍNH TOÁN CHỈ BÁO ---
    analysis: Dict[str, Any] = {}
    signals: List[str] = []

    close = df["Close"]
    current_price = float(close.iloc[-1])
    analysis["current_price"] = current_price

    # 1. Xu hướng (Moving Averages)
    try:
        ma50 = df.ta.sma(length=50).iloc[-1]
        ma200 = df.ta.sma(length=200).iloc[-1]
        analysis["ma50"] = float(ma50) if ma50 is not None else None
        analysis["ma200"] = float(ma200) if ma200 is not None else None

        if analysis["ma50"] and analysis["ma200"]:
            if current_price > analysis["ma50"] > analysis["ma200"]:
                signals.append("Xu hướng: TĂNG MẠNH (Giá > MA50 > MA200)")
            elif current_price < analysis["ma50"] < analysis["ma200"]:
                signals.append("Xu hướng: GIẢM (Giá < MA50 < MA200)")
            elif analysis["ma50"] < analysis["ma200"]:
                signals.append("Cảnh báo: Giao cắt tử thần (Death Cross) - MA50 nằm dưới MA200")
            elif analysis["ma50"] > analysis["ma200"]:
                signals.append("Tích cực: Giao cắt vàng (Golden Cross) - MA50 nằm trên MA200")
    except Exception:
        pass

    # 2. Động lượng (RSI)
    try:
        rsi_val = float(df.ta.rsi(length=14).iloc[-1])
        analysis["rsi"] = rsi_val
        if rsi_val > 70:
            signals.append(f"RSI ({rsi_val:.1f}): Vùng QUÁ MUA")
        elif rsi_val < 30:
            signals.append(f"RSI ({rsi_val:.1f}): Vùng QUÁ BÁN")
        else:
            signals.append(f"RSI ({rsi_val:.1f}): Trung tính")
    except Exception:
        pass

    # 3. MACD
    try:
        macd_df = df.ta.macd(fast=12, slow=26, signal=9)
        last_row = macd_df.iloc[-1]
        analysis["macd"] = {
            "line": float(last_row.iloc[0]),
            "signal": float(last_row.iloc[2]),
            "hist": float(last_row.iloc[1]),
        }
        if analysis["macd"]["line"] > analysis["macd"]["signal"]:
            signals.append("MACD: Tín hiệu MUA (Cắt lên)")
        else:
            signals.append("MACD: Tín hiệu BÁN (Cắt xuống)")
    except Exception:
        pass

    # 4. Bollinger Bands
    try:
        bb_df = df.ta.bbands(length=20, std=2)
        last_row = bb_df.iloc[-1]
        upper = float(last_row.iloc[2])
        lower = float(last_row.iloc[0])
        analysis["bbands"] = {"upper": upper, "lower": lower}

        if current_price > upper:
            signals.append("Bollinger: Giá vượt dải trên (Căng cứng)")
        elif current_price < lower:
            signals.append("Bollinger: Giá thủng dải dưới (Quá bán)")
    except Exception:
        pass

    # 5. ATR (Biến động)
    try:
        atr = float(df.ta.atr(length=14).iloc[-1])
        analysis["atr"] = atr
        analysis["stop_loss_suggest"] = current_price - (2 * atr)
    except Exception:
        pass

    result: Dict[str, Any] = {
        "status": "success",
        "symbol": symbol,
        "data": analysis,
        "summary_signals": signals,
    }

    clean_result = _clean_json_nan(result)
    set_cache(cache_key, clean_result, expiration_sec=900)

    return clean_result
