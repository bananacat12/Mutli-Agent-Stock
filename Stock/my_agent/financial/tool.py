# ============================================================
# FILE: my_agent/financial/tool.py (BULLETPROOF VERSION)
# ============================================================
import yfinance as yf
from typing import Dict, Any, List, Optional
import math
import sys
import os
import contextlib
import pandas as pd

# -------------------------------------------------------------------------
# 1. HÀM DỌN DẸP JSON (QUAN TRỌNG: XỬ LÝ NaN)
# -------------------------------------------------------------------------
def clean_nan_safe(data: Any) -> Any:
    """
    Chuyển đổi NaN/Infinity thành None để đảm bảo chuẩn JSON.
    Định nghĩa trực tiếp tại đây để không phụ thuộc vào import.
    """
    if data is None:
        return None
    if isinstance(data, (float, int)):
        try:
            if math.isnan(data) or math.isinf(data):
                return None
        except TypeError:
            # int không có math.isnan
            pass
        return data
    if isinstance(data, dict):
        return {k: clean_nan_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [clean_nan_safe(item) for item in data]
    if isinstance(data, (pd.Timestamp, pd.NaT.__class__)):
        return str(data) if not pd.isna(data) else None
    return data

# -------------------------------------------------------------------------
# 2. CHẶN LOG RÁC (SILENCE CONTEXT)
# -------------------------------------------------------------------------
@contextlib.contextmanager
def silence_yfinance():
    """Chặn stdout/stderr để yfinance không in log làm hỏng luồng MCP"""
    try:
        with open(os.devnull, 'w') as fnull:
            old_stdout, old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout, sys.stderr = fnull, fnull
                yield
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
    except Exception:
        # Nếu không mở được devnull (hiếm), cứ chạy bình thường
        yield

# -------------------------------------------------------------------------
# 3. SETUP CACHE (FALLBACK AN TOÀN)
# -------------------------------------------------------------------------
try:
    from my_agent.cache import get_cache, set_cache
except ImportError:
    def get_cache(key): return None
    def set_cache(key, val, exp): pass

# -------------------------------------------------------------------------
# 4. HÀM MAIN
# -------------------------------------------------------------------------
def analyze_financials(symbol: str) -> Dict[str, Any]:
    """
    Lấy và phân tích dữ liệu tài chính cơ bản cho một mã cổ phiếu.
    Trả về:
      - status: "success" + data (ratios, income, balance, meta)
      - hoặc status: "error" + error_type + error_message (+ available_data nếu có)
    """
    # Key v7 để đảm bảo cache mới hoàn toàn (tránh xung đột version cũ)
    cache_key = f"financial_tool_v7:{symbol}"

    # 1. Check Cache
    try:
        cached = get_cache(cache_key)
        if cached:
            return cached
    except Exception:
        pass

    info: Dict[str, Any] = {}
    fin_df = pd.DataFrame()
    bs_df = pd.DataFrame()

    # 2. Gọi API Yahoo Finance trong im lặng
    try:
        with silence_yfinance():
            tkr = yf.Ticker(symbol)

            # Info cơ bản
            info = tkr.info or {}

            # Income statement (financials)
            if tkr.financials is not None and not tkr.financials.empty:
                fin_df = tkr.financials.iloc[:, :2]

            # Balance sheet
            if tkr.balance_sheet is not None and not tkr.balance_sheet.empty:
                bs_df = tkr.balance_sheet.iloc[:, :2]

    except Exception as e:
        # Lỗi khi gọi API Yahoo Finance → api_error
        base = {
            "status": "error",
            "error_type": "api_error",
            "error_message": str(e),
            "symbol": symbol,
        }

        if info:
            base["available_data"] = {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "marketCap": info.get("marketCap"),
                "shortName": info.get("shortName") or info.get("longName"),
            }

        clean_base = clean_nan_safe(base)
        set_cache(cache_key, clean_base, 600)  # cache ngắn cho lỗi mạng
        return clean_base

    # 3. Các trường hợp thiếu dữ liệu nhưng không raise exception
    if not info and fin_df.empty and bs_df.empty:
        result = {
            "status": "error",
            "error_type": "no_info",
            "error_message": f"Không tìm thấy bất kỳ dữ liệu tài chính nào cho {symbol} từ Yahoo Finance.",
            "symbol": symbol,
        }
        clean_result = clean_nan_safe(result)
        set_cache(cache_key, clean_result, 86400)
        return clean_result

    if info and fin_df.empty and bs_df.empty:
        result = {
            "status": "error",
            "error_type": "no_financials",
            "error_message": f"Không có báo cáo thu nhập hoặc bảng cân đối kế toán cho {symbol}.",
            "symbol": symbol,
            "available_data": {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "marketCap": info.get("marketCap"),
                "shortName": info.get("shortName") or info.get("longName"),
            },
        }
        clean_result = clean_nan_safe(result)
        set_cache(cache_key, clean_result, 86400)
        return clean_result

    if info and (not fin_df.empty) and bs_df.empty:
        result = {
            "status": "error",
            "error_type": "no_balance_sheet",
            "error_message": f"Có báo cáo thu nhập nhưng không có bảng cân đối kế toán cho {symbol}.",
            "symbol": symbol,
            "available_data": {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "marketCap": info.get("marketCap"),
                "shortName": info.get("shortName") or info.get("longName"),
            },
        }
        clean_result = clean_nan_safe(result)
        set_cache(cache_key, clean_result, 86400)
        return clean_result

    # 4. Trường hợp có đủ dữ liệu → tính toán chi tiết
    try:
        def get_val(series: pd.Series, keys: List[str]) -> Optional[float]:
            if series is None or series.empty:
                return None
            for k in keys:
                if k in series.index:
                    val = series.loc[k]
                    if pd.notna(val):
                        try:
                            return float(val)
                        except (TypeError, ValueError):
                            return None
            return None

        # Ratios cơ bản
        ratios = {
            "marketCap": info.get("marketCap"),
            "pe": info.get("forwardPE") or info.get("trailingPE"),
            "roe": info.get("returnOnEquity"),
            "pb": info.get("priceToBook"),
            "profit_margin": info.get("profitMargins"),
        }

        # Income statement (doanh thu, lợi nhuận)
        inc = {"revenue": None, "net_income": None}
        if not fin_df.empty:
            s_inc = fin_df.iloc[:, 0]
            inc["revenue"] = get_val(s_inc, ["Total Revenue", "Operating Revenue"])
            inc["net_income"] = get_val(s_inc, ["Net Income", "Net Income Common Stockholders"])

        # Balance sheet (tài sản, nợ, vốn chủ)
        bal = {"assets": None, "liabilities": None, "equity": None}
        if not bs_df.empty:
            s_bs = bs_df.iloc[:, 0]
            bal["assets"] = get_val(s_bs, ["Total Assets"])
            bal["equity"] = get_val(s_bs, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"])
            bal["liabilities"] = get_val(
                s_bs,
                ["Total Liabilities Net Minority Interest", "Total Liabilities", "Total Liab"],
            )
            if bal["liabilities"] is None and bal["assets"] is not None and bal["equity"] is not None:
                bal["liabilities"] = bal["assets"] - bal["equity"]

        result = {
            "status": "success",
            "symbol": symbol,
            "summary": f"Financials {symbol}: Cap {ratios['marketCap']}, Rev {inc['revenue']}",
            "data": {
                "ratios": ratios,
                "income": inc,
                "balance": bal,
                "meta": {
                    "shortName": info.get("shortName") or info.get("longName"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "currency": info.get("currency"),
                },
            },
        }

        clean_result = clean_nan_safe(result)
        set_cache(cache_key, clean_result, 86400)
        return clean_result

    except Exception as e:
        # Lỗi parsing/tính toán → parsing_error
        base = {
            "status": "error",
            "error_type": "parsing_error",
            "error_message": str(e),
            "symbol": symbol,
        }
        if info:
            base["available_data"] = {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "marketCap": info.get("marketCap"),
                "shortName": info.get("shortName") or info.get("longName"),
            }
        clean_base = clean_nan_safe(base)
        set_cache(cache_key, clean_base, 86400)
        return clean_base

# -------------------------------------------------------------------------
# 5. SELF-TEST (Chạy trực tiếp file này để test)
# -------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    print("--- TEST MODE ---")
    res = analyze_financials("AAPL")
    print(json.dumps(res, indent=2, ensure_ascii=False))
