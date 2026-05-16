# 🤖 Multi-Agent AI Stock Advisory System

An intelligent, multi-agent AI system for stock investment advisory, powered by **Google Agent Development Kit (ADK)**, **Gemini 2.5**, and a hybrid memory architecture using **PostgreSQL** and **Redis**.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Agents](#agents)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Usage Examples](#usage-examples)
- [Memory System](#memory-system)
- [Future Work](#future-work)

---

## 🌟 Overview

This system acts as a virtual financial advisor capable of:

- 📈 Fetching **real-time stock prices** and technical indicators (EMA, RSI)
- 📰 Retrieving and summarizing **latest financial news**
- 💬 Analyzing **Reddit sentiment** from r/wallstreetbets, r/stocks, r/investing
- 📊 Performing **fundamental analysis** (P/E, ROE, Debt/Equity)
- 🔍 Running **advanced technical analysis** (MACD, Bollinger Bands, ATR-based stop-loss)
- 🧠 Maintaining **conversational context** across multiple turns
- 🏁 Generating **BUY / HOLD / SELL** recommendations with reasoning

---

## 🏗️ Architecture

The system follows an **Orchestrator-Tool (Hub-and-Spoke)** multi-agent pattern:

```
                        ┌─────────────┐    ┌──────────────┐
                        │    Redis    │    │  PostgreSQL  │
                        │ (Cache +    │    │  + pgvector  │
                        │  Session)   │    │  (RAG/LTM)   │
                        └──────┬──────┘    └──────┬───────┘
                               │                  │
                        ┌──────▼──────────────────▼───────┐
                        │         ROOT ORCHESTRATOR        │
                        │        (Gemini 2.5 Pro / ADK)   │
                        └──────┬──────┬──────┬──────┬─────┘
                               │      │      │      │
               ┌───────────────┘      │      │      └──────────────────┐
               ▼                      ▼      ▼                         ▼
     ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
     │   price_agent    │  │  news_agent  │  │  sentiment   │  │  [financial &    │
     │  (Yahoo Finance) │  │  (NewsAPI)   │  │    agent     │  │   ta_agent]      │
     │  EMA/RSI/Trend   │  │  Top Stories │  │  (Reddit)    │  │  (fundamentals + │
     └──────────────────┘  └──────────────┘  └──────────────┘  │   MACD/BB/ATR)  │
                                                                └──────────────────┘
```

All intelligence is centralized in the **Orchestrator**. Sub-agents are stateless tools that fetch and return structured JSON — no reasoning of their own.

---

## 🤖 Agents

### 1. Root Orchestrator (`my_agent/agent.py`)
- Model: `gemini-2.5-pro`
- Routes user queries to the appropriate sub-agents via `transfer_to_agent`
- Synthesizes all data into a final **BUY / HOLD / SELL** recommendation
- Manages PostgreSQL logging and Redis session state

### 2. Price Agent (`my_agent/price/`)
- Model: `gemini-2.5-flash`
- Tool: `get_price(symbol, period, interval)`
- Data source: **Yahoo Finance** via `yfinance`
- Returns: current price, % change, EMA20, EMA50, RSI(14), trend hint

### 3. News Agent (`my_agent/news/`)
- Model: `gemini-2.5-flash`
- Tool: `get_news(keyword, days=3)`
- Data source: **NewsAPI** (`/v2/everything`)
- Returns: top 5 articles with title, source, URL, publishedAt, description

### 4. Reddit Sentiment Agent (`my_agent/reddit_sentiment/`)
- Model: `gemini-2.5-flash`
- Tool: `reddit_social_sentiment(query, max_items=60)`
- Data source: **Reddit public JSON API** (no key required)
- Scoring: **Sentim API** (primary) → **Rule-based lexicon** (fallback/degraded mode)
- Returns: mean_score, pos/neu/neg counts, top posts, sentiment label

### 5. Memory Store (`my_agent/memory/store.py`)
- PostgreSQL-backed functions: `save_message`, `get_history`, `upsert_fact`, `get_facts`, `clear_session`
- Used by the orchestrator to persist conversation history per `session_id`

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | Google Agent Development Kit (ADK) |
| LLM | Gemini 2.5 Pro / Flash |
| Stock Data | `yfinance` (Yahoo Finance) |
| News Data | NewsAPI (`newsapi.org`) |
| Sentiment Source | Reddit Public JSON API |
| Sentiment Scoring | Sentim API + Rule-based fallback |
| Long-term Memory | PostgreSQL + `pgvector` |
| Short-term Cache | Redis |
| Technical Indicators | `pandas`, `numpy` |
| Infrastructure | Docker (PostgreSQL & Redis containers) |
| Language | Python 3.10+ |

---

## 📁 Project Structure

```
my_agent/
├── agent.py                    # Root Orchestrator (entry point for ADK)
├── __init__.py
│
├── price/
│   ├── agent.py                # Price Agent definition
│   └── tool.py                 # get_price() – Yahoo Finance + EMA/RSI
│
├── news/
│   ├── agent.py                # News Agent definition
│   └── tool.py                 # get_news() – NewsAPI
│
├── reddit_sentiment/
│   ├── agent.py                # Sentiment Agent definition
│   └── tool.py                 # reddit_social_sentiment() – Reddit + Sentim
│
├── memory/
│   └── store.py                # PostgreSQL CRUD (messages, facts)
│
└── db/
    └── core.py                 # SQLAlchemy engine + init_db()
```

---

## ✅ Prerequisites

- Python **3.10+**
- Docker & Docker Compose
- A Google Cloud project with **Gemini API** enabled
- A **NewsAPI** key (free tier at newsapi.org)

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/bananacat12/Mutli-Agent-Stock.git
cd Mutli-Agent-Stock/Stock
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start infrastructure with Docker

```bash
# Spin up PostgreSQL (with pgvector) and Redis
docker compose up -d
```

> **docker-compose.yml** (example):
> ```yaml
> services:
>   postgres:
>     image: pgvector/pgvector:pg16
>     environment:
>       POSTGRES_DB: stockdb
>       POSTGRES_USER: postgres
>       POSTGRES_PASSWORD: postgres
>     ports:
>       - "5432:5432"
>
>   redis:
>     image: redis:7-alpine
>     ports:
>       - "6379:6379"
> ```

---

## 🔧 Configuration

Create a `.env` file in the project root:

```env
# ── Google / Gemini ──────────────────────────────────────
GOOGLE_API_KEY=your_gemini_api_key_here

# ── NewsAPI ──────────────────────────────────────────────
NEWS_API_KEY=your_newsapi_key_here

# ── PostgreSQL ───────────────────────────────────────────
DB_URL=postgresql://postgres:postgres@localhost:5432/stockdb

# ── Redis ────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Session ──────────────────────────────────────────────
SESSION_ID=local_demo

# ── Sentiment (optional tuning) ──────────────────────────
SENTI_ENDPOINT=https://sentim-api.herokuapp.com/api/v1/
SENTI_TIMEOUT=10
SENTI_SLEEP_MS=120
SENTI_MIN_SUCCESS=5
SENTI_RETRY=1
REDDIT_SUBS=stocks,wallstreetbets,investing
RD_TIMEOUT=10
```

---

## 🚀 Running the System

### Option A – ADK Web UI (recommended)

```bash
adk web
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.  
Select `my_agent` from the left panel and start chatting.

### Option B – ADK CLI

```bash
adk run my_agent
```

### Option C – Programmatic (Python)

```python
from my_agent.agent import handle_user_message

reply = handle_user_message("Should I buy AAPL right now?")
print(reply)
```

---

## 💬 Usage Examples

| Query | Agents Triggered |
|---|---|
| `"Giá TSLA hiện tại?"` | price_agent |
| `"Tin tức mới nhất về NVDA?"` | news_agent |
| `"Sentiment Reddit về AAPL?"` | reddit_sentiment_agent |
| `"Có nên mua MSFT không?"` | price_agent → news_agent → reddit_sentiment_agent → Orchestrator synthesizes |
| `"So sánh AAPL và GOOGL"` | All agents × 2 symbols |

### Sample recommendation output

```
== Khuyến nghị ==
• Action        : BUY
• Lý do chính  : EMA20 > EMA50 (uptrend), RSI = 58 (neutral), 3 tin tích cực, sentiment score +0.31
• Rủi ro        : Earnings report sắp tới; RSI tiệm cận vùng overbought nếu tăng thêm
• Khung thời gian: Ngắn hạn 1–4 tuần
• Độ tự tin     : Vừa
```

---

## 🧠 Memory System

The system uses a **3-layer hybrid memory** architecture:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 – Long-Term (PostgreSQL + pgvector)                │
│  • Full chat history stored as vector embeddings            │
│  • Semantic KNN search for relevant past conversations      │
│  • Tables: messages, facts                                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 – Performance Cache (Redis, TTL varies)            │
│  • Price data      → TTL 5 min                              │
│  • News data       → TTL 60 min                             │
│  • Sentiment data  → TTL 30 min                             │
│  • Technical data  → TTL 15 min                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 – Session State (Redis, TTL 1 hour)                │
│  • current_symbol  (e.g., "AAPL")                           │
│  • conversation summary (auto-generated every 10 messages)  │
└─────────────────────────────────────────────────────────────┘
```

This allows the agent to correctly answer follow-up questions like *"Giá của nó thế nào?"* without the user having to repeat the ticker.

---

## 🔮 Future Work

- [ ] **SSE Transport**: Migrate MCP server to Server-Sent Events over HTTP for persistent, long-lived connections
- [ ] **Async tools**: Refactor all tools to `async/await` for fully parallel data fetching
- [ ] **Vietnamese data**: Integrate WiGroup or SSI API for HOSE/HNX/UPCoM stocks
- [ ] **Chain-of-Thought logging**: Surface the orchestrator's step-by-step reasoning for greater transparency
- [ ] **Cloud deployment**: Migrate to Google Cloud Run + Cloud SQL + Memorystore for production-grade scalability
- [ ] **Crypto & Forex**: Expand the data universe to include crypto assets and foreign exchange pairs
- [ ] **Macroeconomic indicators**: Incorporate GDP, interest rates, and CPI to enrich advisory context

---

## 📚 References

- [Google Agent Development Kit (ADK) Docs](https://google.github.io/adk-docs/)
- [NewsAPI Documentation](https://newsapi.org/docs)
- [yfinance Library](https://github.com/ranaroussi/yfinance)
- [pgvector Extension](https://github.com/pgvector/pgvector)
- [Sentim API](https://sentim-api.herokuapp.com)

---
