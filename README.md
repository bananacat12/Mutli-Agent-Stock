# Stock Advisor Multi-Agent

![Python](https://img.shields.io/badge/python-3.11-blue)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)

Production-lite multi-agent stock advisor built with Google ADK-style agent definitions, deterministic orchestration, A2A HTTP endpoints, and MCP tools. The system coordinates price, financial news, and Reddit sentiment specialists, then stores task and trace data in PostgreSQL.

Demo URL: https://mutli-agent-stock.onrender.com

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

## Tech Stack

- Python 3.11
- FastAPI + Uvicorn
- Google ADK agent definitions
- MCP FastMCP
- PostgreSQL + SQLAlchemy
- Pydantic contracts
- Yahoo Finance, NewsAPI, Reddit/Sentim
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

Current expected result: `25 passed`.
