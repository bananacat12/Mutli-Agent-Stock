# Hệ thống Tư vấn Chứng khoán - Điều phối Định sẵn (Deterministic Orchestration) & Tổng hợp LLM (LLM Synthesis)

Live Demo: https://bananacat12.github.io/Mutli-Agent-Stock

## Preview
![Stock Analysis Desk](./assets/screenshot.jpeg)

![Python](https://img.shields.io/badge/python-3.11-blue)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)

Hệ thống tư vấn chứng khoán dựa trên kiến trúc **Điều phối Định sẵn (Deterministic Orchestration)** và **Tổng hợp bằng LLM (LLM Synthesis)**. Thay vì sử dụng mô hình Multi-Agent tự do thuần túy (vốn dễ gặp lỗi và tốn chi phí), hệ thống áp dụng mô hình thiết kế tối ưu "Sweet Spot" kết hợp sự chính xác tuyệt đối của code định sẵn với khả năng lập luận của LLM.

Demo URL: https://mutli-agent-stock.onrender.com

## Web Interface

1. Open the live demo: https://bananacat12.github.io/Mutli-Agent-Stock
2. Enter a stock ticker, for example `TSLA` or `AAPL`.
3. Enter your API key.
4. Click `Analyze` and wait for the multi-agent result.

## Architecture

```text
Client / A2A / MCP
        |
        v
FastAPI A2A Server ---- MCP FastMCP Server
        |
        v
Root Workflow
        |
        v
Planner -> AgentRequest contracts -> Parallel Executor
        |                         |          |
        v                         v          v
  Price Tool                 News Tool   Reddit Sentiment Tool
        \______________________|__________/
                               v
                      Task + Trace Store
                         PostgreSQL
```

### Chi tiết Kiến trúc Hệ thống

Hệ thống được thiết kế theo các nguyên tắc kiến trúc hiện đại nhằm đảm bảo độ tin cậy và hiệu năng cao nhất:

1. **Mô hình "Sweet Spot" (Tools-as-Agents với Centralized Orchestrator)**:
   - Thay vì xây dựng các Agent tự do giao tiếp và tự đưa ra quyết định luồng (dễ dẫn đến lặp vô hạn hoặc sai lệch luồng), hệ thống sử dụng một **Centralized Orchestrator** (Bộ điều phối trung tâm) để quản lý luồng chạy xác định (Deterministic Workflow).
   - Các Agent đóng vai trò là các "Tool-based Agents" được kích hoạt và kiểm soát rõ ràng bởi Orchestrator.

2. **Vai trò của các Sub-agents (Price, News, Sentiment) - Tool Wrappers bằng Code thuần**:
   - Các Sub-agents thực chất là các hàm bọc code thuần (Tool Wrappers) thực hiện các tác vụ chuyên biệt (truy vấn giá Alpha Vantage/yfinance, thu thập tin tức từ NewsAPI, phân tích Sentiment từ Reddit).
   - Chúng được thực thi hoàn toàn **song song** thông qua cơ chế bất đồng bộ `asyncio.gather()` của Python để tối ưu hóa hiệu năng.
   - Việc sử dụng code thuần (thay vì LLM Agent tự tương tác với tool) giúp dữ liệu tài chính đầu ra chính xác 100% (tránh hoàn toàn hiện tượng **hallucination** - ảo giác của LLM), đồng thời giảm thiểu tối đa chi phí API và độ trễ (latency).

3. **Tầng Tổng hợp (Synthesis Layer - LLM Synthesis)**:
   - Chỉ có **duy nhất 1 cuộc gọi LLM** (sử dụng mô hình `gemini-2.5-flash` làm mặc định) ở bước cuối cùng của quy trình.
   - LLM đóng vai trò như một **Portfolio Manager (Giám đốc Danh mục Đầu tư)**. Nhiệm vụ duy nhất của nó là nhận dữ liệu cấu trúc (JSON) đã được tổng hợp chính xác từ các sub-agent, phân tích tổng hợp thông tin và đưa ra khuyến nghị đầu tư cuối cùng (**BUY/HOLD/SELL**) kèm theo luận điểm phân tích chi tiết. Điều này giúp kiểm soát tốt chi phí và nâng cao chất lượng lập luận.


## Tech Stack

- Python 3.11
- FastAPI + Uvicorn
- Google ADK agent definitions
- MCP FastMCP
- PostgreSQL + SQLAlchemy
- Pydantic contracts
- Alpha Vantage (fallback yfinance), NewsAPI, Reddit/Sentim
- Pytest

## Local Development

Copy environment placeholders:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```env
AGENT_API_KEY=<liên hệ để lấy API key>
NEWS_API_KEY=<liên hệ để lấy API key>
GOOGLE_API_KEY=<liên hệ để lấy API key>
ALPHAVANTAGE_API_KEY=<liên hệ để lấy API key>
```

The Compose file treats `.env` as optional so configuration can be parsed before secrets are created, but real runs should set the values above.

Run with Docker Compose from this repository root:

```powershell
docker compose up --build
```

Check health:

```powershell
curl http://localhost:8000/health
```

Call A2A:

```powershell
curl -X POST http://localhost:8000/tasks `
  -H "Content-Type: application/json" `
  -H "X-API-Key: <liên hệ để lấy API key>" `
  -d "{\"sessionId\":\"demo\",\"message\":{\"role\":\"user\",\"parts\":[{\"type\":\"text\",\"text\":\"Analyze TSLA\"}]}}"
```

## MCP

MCP is included as a separate entrypoint. Run stdio locally:

```powershell
python -m my_agent.mcp_server
```

Run MCP streamable HTTP as a separate service:

```powershell
$env:MCP_TRANSPORT="streamable-http"
$env:MCP_PORT="8001"
python -m my_agent.mcp_server
```

MCP tools require the `api_key` argument when `AGENT_API_KEY` is set.

## Render Deploy

1. Push this repository to GitHub.
2. Go to Render -> New -> Web Service -> Deploy from GitHub.
3. Select the repository.
4. Add a Render PostgreSQL service.
5. Set environment variables on the app service:

```env
DB_URL=<Render Postgres SQLAlchemy URL>
AGENT_API_KEY=<liên hệ để lấy API key>
NEWS_API_KEY=<liên hệ để lấy API key>
GOOGLE_API_KEY=<liên hệ để lấy API key>
ALPHAVANTAGE_API_KEY=<liên hệ để lấy API key>
GOOGLE_GENAI_USE_VERTEXAI=0
ROOT_SYNTHESIS_MODEL=gemini-2.5-flash
A2A_ENABLE_PUSH=0
A2A_PUBLIC_URL=https://mutli-agent-stock.onrender.com
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

6. Deploy and check `/health`.

If Render gives a PostgreSQL URL in `postgresql://...` format, use SQLAlchemy's PostgreSQL driver format if needed:

```text
postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE
```

## Tests

From the `my_agent` package directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

