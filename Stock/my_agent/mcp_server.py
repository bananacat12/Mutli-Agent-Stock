import json
import sys
import os
from typing import List, Dict, Any
from pathlib import Path
# CẬP NHẬT: Import ConfigDict cho Pydantic V2
from pydantic import BaseModel, Field, ValidationError, ConfigDict

# ---- CRITICAL: Load .env BEFORE any imports ----
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[MCP_SERVER] ✅ Loaded .env from {env_path}", file=sys.stderr, flush=True)
    else:
        print(f"[MCP_SERVER] ⚠️  .env not found at {env_path}", file=sys.stderr, flush=True)
except ImportError:
    print("[MCP_SERVER] ⚠️  python-dotenv not installed", file=sys.stderr, flush=True)
except Exception as e:
    print(f"[MCP_SERVER] ❌ Error loading .env: {e}", file=sys.stderr, flush=True)

# ---- Import all tools ----
print("[MCP_SERVER] Importing tools...", file=sys.stderr, flush=True)

def _import_or_die():
    """Import tất cả các tool và xử lý lỗi"""
    tools = {}
    
    # Price tool
    try:
        from price.tool import get_price
        tools['get_price'] = get_price
        print("[MCP_SERVER] ✅ price.tool imported", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MCP_SERVER] ❌ Cannot import price.tool: {e}", file=sys.stderr, flush=True)
        raise RuntimeError(f"Cannot import price.tool: {e}")

    # News tool
    try:
        from news.tool import get_news
        tools['get_news'] = get_news
        print("[MCP_SERVER] ✅ news.tool imported", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MCP_SERVER] ❌ Cannot import news.tool: {e}", file=sys.stderr, flush=True)
        raise RuntimeError(f"Cannot import news.tool: {e}")

    # Sentiment tool
    try:
        from sentiment.tool import reddit_social_sentiment
        tools['reddit_social_sentiment'] = reddit_social_sentiment
        print("[MCP_SERVER] ✅ sentiment.tool imported", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MCP_SERVER] ❌ Cannot import sentiment.tool: {e}", file=sys.stderr, flush=True)
        raise RuntimeError(f"Cannot import sentiment.tool: {e}")

    # Technical Analysis tool
    try:
        from technical_analysis.tool import get_advanced_ta
        tools['get_advanced_ta'] = get_advanced_ta
        print("[MCP_SERVER] ✅ technical_analysis.tool imported", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MCP_SERVER] ⚠️  Cannot import technical_analysis.tool: {e}", file=sys.stderr, flush=True)
        tools['get_advanced_ta'] = None

    # Financial Analysis tool
    try:
        from financial.tool import analyze_financials
        tools['analyze_financials'] = analyze_financials
        print("[MCP_SERVER] ✅ financial.tool imported", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MCP_SERVER] ⚠️  Cannot import financial.tool: {e}", file=sys.stderr, flush=True)
        tools['analyze_financials'] = None

    return tools

_tools = _import_or_die()

# ---- MCP runtime ----
print("[MCP_SERVER] Initializing FastMCP...", file=sys.stderr, flush=True)
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("my_agent_mcp")
print("[MCP_SERVER] ✅ FastMCP initialized", file=sys.stderr, flush=True)

# ---------- Pydantic Schemas (Updated for V2) ----------
class PriceInput(BaseModel):
    symbol: str = Field(..., description="Mã cổ phiếu, ví dụ: AAPL, TSLA, VNINDEX")
    period: str = Field("1mo", description="1d|5d|1mo|3mo|6mo|1y|2y|5y|10y|ytd|max")
    interval: str = Field("1d", description="1m|2m|5m|15m|30m|60m|90m|1h|1d|5d|1wk|1mo|3mo")


class NewsInput(BaseModel):
    keyword: str = Field(..., description="Từ khóa/mã/công ty: 'AAPL', 'Apple', 'NVDA'")
    days: int = Field(3, ge=1, le=14, description="Số ngày gần nhất để lấy tin")


class RedditSentimentInput(BaseModel):
    query: str = Field(..., description="Ticker hoặc từ khóa: 'TSLA', 'NVDA'")
    max_items: int = Field(60, ge=1, le=60, description="Số lượng bài viết tối đa")
    endpoint: str = Field("", description="Tùy chọn override Sentim endpoint")
    min_success: int = Field(0, description="Tối thiểu sample OK trước khi degrade")
    degraded_mode: bool = Field(True, description="Cho phép fallback rule-based")


class TechnicalAnalysisInput(BaseModel):
    symbol: str = Field(..., description="Mã cổ phiếu cần phân tích kỹ thuật")


# === FIX QUAN TRỌNG: Sử dụng ConfigDict thay vì class Config ===
class FinancialAnalysisInput(BaseModel):
    symbol: str = Field(..., description="Mã cổ phiếu cần phân tích tài chính")

    # Cấu hình cho Pydantic V2: Cho phép Gemini gửi thêm tham số thừa mà không lỗi
    model_config = ConfigDict(extra="allow")
# ===============================================================


class SnapshotInput(BaseModel):
    symbols: List[str] = Field(..., description="Danh sách mã cần snapshot")
    period: str = Field("1mo", description="Period cho price data")
    interval: str = Field("1d", description="Interval cho price data")
    news_days: int = Field(2, ge=1, le=14, description="Số ngày tin tức")
    senti_items: int = Field(20, ge=1, le=60, description="Số lượng sentiment items")
    include_ta: bool = Field(False, description="Bao gồm technical analysis")
    include_financials: bool = Field(False, description="Bao gồm financial analysis")

# ---------- Helper Functions ----------
def _json(data: Any) -> str:
    """Convert data to JSON string"""
    return json.dumps(data, ensure_ascii=False, default=str)

def _ok(obj: Any) -> str:
    """Return success response"""
    return _json({"status": "success", "data": obj})

def _err(msg: str) -> str:
    """Return error response"""
    return _json({"status": "error", "error_message": msg})

# ---------- Register MCP Tools ----------
print("[MCP_SERVER] Registering tools...", file=sys.stderr, flush=True)

# 1. PRICE TOOL
@mcp.tool(name="price_get")
def price_get(args: PriceInput) -> str:
    try:
        data = _tools['get_price'](args.symbol, args.period, args.interval)
        return _json(data)
    except Exception as e:
        return _err(f"price_get lỗi: {e}")

@mcp.tool(name="get")
def get_alias(args: PriceInput) -> str:
    try:
        return price_get(args)
    except ValidationError as ve:
        return _err(f"validate lỗi: {ve}")
    except Exception as e:
        return _err(f"get lỗi: {e}")

# 2. NEWS TOOL
@mcp.tool(name="news_search")
def news_search(args: NewsInput) -> str:
    try:
        data = _tools['get_news'](args.keyword, args.days)
        return _json(data)
    except Exception as e:
        return _err(f"news_search lỗi: {e}")

# 3. SENTIMENT TOOL
@mcp.tool(name="sentiment_reddit")
def sentiment_reddit(args: RedditSentimentInput) -> str:
    try:
        data = _tools['reddit_social_sentiment'](
            query=args.query,
            max_items=args.max_items,
            endpoint=args.endpoint,
            min_success=args.min_success,
            degraded_mode=args.degraded_mode,
        )
        return _json(data)
    except Exception as e:
        return _err(f"sentiment_reddit lỗi: {e}")

# 4. TECHNICAL ANALYSIS TOOL
if _tools['get_advanced_ta']:
    @mcp.tool(name="technical_analysis")
    def technical_analysis(args: TechnicalAnalysisInput) -> str:
        try:
            data = _tools['get_advanced_ta'](args.symbol)
            return _json(data)
        except Exception as e:
            return _err(f"technical_analysis lỗi: {e}")

# 5. FINANCIAL ANALYSIS TOOL
if _tools['analyze_financials']:
    @mcp.tool(name="financial_analysis")
    def financial_analysis(args: FinancialAnalysisInput) -> str:
        """Phân tích tài chính cơ bản (P/E, P/B, ROE, Income Statement, Balance Sheet)."""
        try:
            # Chỉ truyền symbol, bỏ qua các tham số thừa (period, interval, days, years...)
            data = _tools['analyze_financials'](args.symbol)
            return _json(data)
        except Exception as e:
            return _err(f"financial_analysis lỗi: {e}")

# 7. SNAPSHOT TOOL
@mcp.tool(name="advisor.snapshot")
def advisor_snapshot(args: SnapshotInput) -> str:
    out: Dict[str, Any] = {
        "asof": None,
        "symbols": args.symbols,
        "items": []
    }
    
    try:
        for sym in args.symbols:
            item = {"symbol": sym}
            try:
                price = _tools['get_price'](sym, args.period, args.interval)
                item["price"] = price
                if not out["asof"]:
                    try:
                        out["asof"] = price.get("snapshot", {}).get("timestamp")
                    except Exception:
                        pass
            except Exception as e:
                item["price"] = {"status": "error", "error_message": str(e)}
            
            try:
                news = _tools['get_news'](sym, args.news_days)
                item["news"] = news
            except Exception as e:
                item["news"] = {"status": "error", "error_message": str(e)}
            
            try:
                senti = _tools['reddit_social_sentiment'](sym, max_items=args.senti_items, degraded_mode=True)
                item["sentiment"] = senti
            except Exception as e:
                item["sentiment"] = {"status": "error", "error_message": str(e)}
            
            if args.include_ta and _tools['get_advanced_ta']:
                try:
                    ta = _tools['get_advanced_ta'](sym)
                    item["technical_analysis"] = ta
                except Exception as e:
                    item["technical_analysis"] = {"status": "error", "error_message": str(e)}
            
            if args.include_financials and _tools['analyze_financials']:
                try:
                    fin = _tools['analyze_financials'](sym)
                    item["financial_analysis"] = fin
                except Exception as e:
                    item["financial_analysis"] = {"status": "error", "error_message": str(e)}
            
            out["items"].append(item)
        
        return _json(out)
    
    except Exception as e:
        return _err(f"advisor.snapshot lỗi: {e}")

print("[MCP_SERVER] ✅ All tools registered", file=sys.stderr, flush=True)

# ---------- Tool List Summary ----------
def print_tool_summary():
    """In ra danh sách các tool đã đăng ký"""
    tools_registered = [
        "price_get",
        "get (alias)",
        "news_search",
        "sentiment_reddit",
        "advisor.snapshot"
    ]
    
    if _tools['get_advanced_ta']:
        tools_registered.append("technical_analysis")
    if _tools['analyze_financials']:
        tools_registered.append("financial_analysis")
    
    print(f"[MCP_SERVER] Registered tools: {', '.join(tools_registered)}", 
          file=sys.stderr, flush=True)

# ---------- Main ----------
if __name__ == "__main__":
    print(f"[MCP_SERVER] __main__ started, args: {sys.argv}", file=sys.stderr, flush=True)
    
    if "--selftest" in sys.argv:
        print("[MCP_SERVER] Running selftest...", file=sys.stderr, flush=True)

        try:
            # 1. PRICE_GET
            print("\n== 1. PRICE_GET ==")
            res_price = price_get(PriceInput(symbol="AAPL", period="1mo", interval="1d"))
            print(res_price)

            # 2. GET (alias)
            print("\n== 2. GET (alias of price_get) ==")
            res_get_alias = get_alias(PriceInput(symbol="MSFT", period="5d", interval="1d"))
            print(res_get_alias)

            # 3. NEWS_SEARCH
            print("\n== 3. NEWS_SEARCH ==")
            res_news = news_search(NewsInput(keyword="AAPL", days=3))
            print(res_news)

            # 4. SENTIMENT_REDDIT
            print("\n== 4. SENTIMENT_REDDIT ==")
            res_senti = sentiment_reddit(
                RedditSentimentInput(
                    query="TSLA",
                    max_items=20,
                    endpoint="",
                    min_success=0,
                    degraded_mode=True,
                )
            )
            print(res_senti)

            # 5. TECHNICAL_ANALYSIS (nếu tool có)
            if _tools.get("get_advanced_ta"):
                print("\n== 5. TECHNICAL_ANALYSIS ==")
                # Gọi trực tiếp tool MCP đã đăng ký
                res_ta = technical_analysis(TechnicalAnalysisInput(symbol="AAPL"))
                print(res_ta)
            else:
                print("\n== 5. TECHNICAL_ANALYSIS BỎ QUA (tool không được import) ==")

            # 6. FINANCIAL_ANALYSIS (nếu tool có)
            if _tools.get("analyze_financials"):
                print("\n== 6. FINANCIAL_ANALYSIS ==")
                res_fin = financial_analysis(FinancialAnalysisInput(symbol="AAPL"))
                print(res_fin)
            else:
                print("\n== 6. FINANCIAL_ANALYSIS BỎ QUA (tool không được import) ==")

            # 7. ADVISOR.SNAPSHOT
            print("\n== 7. ADVISOR.SNAPSHOT ==")
            res_snapshot = advisor_snapshot(
                SnapshotInput(
                    symbols=["AAPL", "MSFT", "TSLA"],
                    period="1mo",
                    interval="1d",
                    news_days=3,
                    senti_items=20,
                    include_ta=True,
                    include_financials=True,
                )
            )
            print(res_snapshot)

            print("\n[MCP_SERVER] ✅ Selftest completed successfully", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"\n[MCP_SERVER] ❌ SELFTEST ERROR: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            sys.exit(1)

        sys.exit(0)

    print("[MCP_SERVER] Starting STDIO server...", file=sys.stderr, flush=True)
    print_tool_summary()
    print("[MCP_SERVER] Ready to accept MCP requests", file=sys.stderr, flush=True)
    
    try:
        mcp.run()
    except KeyboardInterrupt:
        print("[MCP_SERVER] Shutting down gracefully...", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[MCP_SERVER] ❌ Fatal Error: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc()
        raise