# Stack Research: Multi-Agent Financial Investment Systems

**Domain:** Multi-agent investment systems with LangGraph
**Research Date:** 2026-02-01
**Confidence Level:** MEDIUM (based on training data, version verification needed)

## Executive Summary

The standard stack for multi-agent financial investment systems in 2025/2026 centers on:
- **LangGraph** for agent orchestration with auditable state graphs
- **Google AI (Gemini)** for cost-effective LLM access
- **Supabase** (PostgreSQL + pgvector) for data persistence and vector search
- **Python ecosystem** for financial analysis and backtesting

All recommendations prioritize **free tiers** and **open-source** options to minimize MVP costs while enabling future scaling.

---

## Core Stack Components

### 1. Agent Orchestration Layer

**Recommended: LangGraph v0.2+ with LangChain**

**Rationale:**
- Native support for complex multi-agent workflows with state management
- Built-in checkpointing for HITL (Human-in-the-Loop) interrupts — critical for EU AI Act compliance
- Auditable state transitions via StateGraph — every decision is traceable
- Conditional edges for dialectical flow (Bulls → Bears → Judge)
- Active development with strong community support

**What NOT to use:**
- ❌ **n8n**: Visual workflow builder, but too limited for complex agent logic (Monte Carlo, fuzzy logic, scoring models)
- ❌ **CrewAI**: Higher-level abstraction, less control over state and flow — problematic for audit requirements
- ❌ **AutoGen**: More research-oriented, less production-ready for financial applications

**Confidence:** HIGH

---

### 2. LLM Provider

**Recommended: Google AI (Gemini 1.5 Pro/Flash) via official SDK**

**Rationale:**
- **Free tier available:** 1,500 requests/day for Gemini 1.5 Flash, 50 requests/day for Pro
- **Long context window:** 1M tokens — enables processing full financial reports in single call
- **Function calling support:** Native tool use for financial calculations
- **Text embeddings:** text-embedding-004 model included free
- **Rate limits sufficient for MVP:** Paper trading doesn't require real-time high-frequency execution

**Alternative (backup):**
- OpenAI GPT-4o-mini for specific tasks if Google AI rate limits hit
- Anthropic Claude (Haiku) for cost-sensitive operations post-MVP

**What NOT to use:**
- ❌ **Local models (Llama, Mistral):** Infrastructure cost and complexity exceed API costs for MVP
- ❌ **GPT-4 Turbo as primary:** 10-15x more expensive than Gemini, unnecessary for most agent tasks

**Confidence:** HIGH

---

### 3. Database & Vector Store

**Recommended: Supabase (Free Tier)**

**Components:**
- **PostgreSQL 15+:** Primary database for structured data (portfolios, trades, audit logs)
- **pgvector extension:** Vector similarity search for RAG on financial bibliography
- **Built-in auth:** User authentication if multi-user features needed
- **Real-time subscriptions:** WebSocket support for live dashboard updates
- **Free tier:** 500MB database, 50MB file storage, unlimited API requests

**Schema Design:**
```sql
-- Core tables
portfolios          -- Portfolio configurations
positions           -- Current holdings
trades              -- Execution history (paper + future real)
agent_states        -- LangGraph checkpoint storage
audit_logs          -- Complete decision trail (EU AI Act)
knowledge_base      -- RAG document chunks with embeddings
```

**Alternative (if Supabase limits hit):**
- Neon (serverless Postgres) — also free tier
- Local PostgreSQL with Docker for development

**What NOT to use:**
- ❌ **MongoDB:** Financial data is inherently relational, SQL is superior for portfolio queries
- ❌ **Pinecone/Weaviate:** Unnecessary cost for vector search when pgvector is free and performant

**Confidence:** HIGH

---

### 4. Financial Data Layer

**Recommended: Multi-source strategy with fallbacks**

**Primary Sources (Free):**

**yfinance (Yahoo Finance)**
```python
import yfinance as yf
# Strengths: Historical OHLCV, fundamentals, free
# Limitations: Rate limits, occasional outages, 15min delay on intraday
```

**Alpha Vantage (Free tier: 25 requests/day)**
- Fundamental data (balance sheets, income statements)
- Economic indicators (GDP, unemployment)

**FRED API (Federal Reserve Economic Data)**
- Macro indicators: interest rates, inflation, money supply
- Critical for Macro Oracle agent
- Free, no rate limits

**Fallback Strategy:**
```python
# Pseudocode for resilience
def get_market_data(ticker):
    try:
        return yfinance.get(ticker)
    except RateLimitError:
        return alphavantage.get(ticker)
    except AllAPIsFailed:
        # Load from cache + trigger HITL
        return cache.get_latest(ticker, max_age_hours=24)
        trigger_hitl("Stale data warning")
```

**What NOT to use for MVP:**
- ❌ **Bloomberg Terminal:** $2,000/month, overkill for paper trading
- ❌ **Refinitiv/Reuters:** Enterprise pricing
- ❌ **Scraping:** Legal risks, fragile, unnecessary when free APIs exist

**Confidence:** MEDIUM (API reliability varies, fallback strategy essential)

---

### 5. Backtesting & Simulation

**Recommended: vectorbt + custom logic**

**vectorbt v0.26+**
```python
import vectorbt as vbt
# Strengths:
# - NumPy-based, very fast
# - Supports portfolio-level backtesting
# - Transaction costs, slippage modeling
# - Built-in performance metrics (Sharpe, drawdown)
```

**Custom Monte Carlo Module**
```python
import numpy as np
from scipy import stats

# For Bear agent sensitivity analysis
# Not available in standard backtesting libs
```

**What NOT to use:**
- ❌ **Backtrader:** Slower, less Pythonic API
- ❌ **Zipline:** Unmaintained since 2020
- ❌ **QuantConnect:** Cloud-only, vendor lock-in

**Confidence:** HIGH

---

### 6. RAG (Retrieval-Augmented Generation) Stack

**For knowledge base of financial bibliography (papers, PDFs, books):**

**Document Processing:**
```python
from langchain.document_loaders import PyPDFLoader, UnstructuredMarkdownLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Load Graham, Dalio, Greenwald books
# Chunk with overlap for context preservation
```

**Embedding & Retrieval:**
```python
from langchain.embeddings import GoogleGenerativeAIEmbeddings
from langchain.vectorstores import SupabaseVectorStore

embeddings = GoogleGenerativeAIEmbeddings(model="text-embedding-004")
vectorstore = SupabaseVectorStore(embeddings, client=supabase)
```

**Evaluation:**
```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

# Validate RAG quality before trusting agent decisions
```

**What NOT to use:**
- ❌ **LlamaIndex:** Heavier abstraction, LangChain integrates better with LangGraph
- ❌ **ChromaDB:** Local-only, harder to scale vs Supabase

**Confidence:** HIGH

---

### 7. Financial Analysis Libraries

**Core Python Ecosystem:**

```python
import pandas as pd          # Data manipulation
import numpy as np           # Numerical computation
from scipy import stats      # Statistical analysis (Monte Carlo, distributions)
import plotly.express as px  # Interactive dashboards
```

**Specialized:**
```python
# Altman Z-Score, Beneish M-Score (Guardian agent)
def altman_z_score(financials):
    # Custom implementation - no standard library

# EPV calculation (Value Hunter agent)
def earnings_power_value(income_statement, balance_sheet, wacc):
    # Bruce Greenwald methodology
```

**What NOT to use:**
- ❌ **Excel/VBA:** Not programmable for agent integration
- ❌ **R packages:** Python ecosystem more mature for LLM integration

**Confidence:** HIGH

---

### 8. Web Framework (Dashboard/Interface)

**Recommended: Streamlit (for MVP speed)**

**Rationale:**
- **Fastest development:** Pure Python, no HTML/CSS/JS required
- **Built-in components:** Charts, tables, forms for HITL approval
- **Real-time updates:** WebSocket support for live agent activity
- **Free hosting:** Streamlit Community Cloud (1GB RAM, sufficient for demo)

**Alternative (post-MVP):**
```python
# If more control needed:
# FastAPI (backend) + React (frontend)
# Supabase real-time for state sync
```

**What NOT to use for MVP:**
- ❌ **Django/Flask:** Slower development, unnecessary backend complexity
- ❌ **Next.js/React alone:** Requires separate Python backend, doubles work

**Confidence:** MEDIUM (Streamlit limitations may require migration post-MVP)

---

### 9. Development & Testing

**Testing:**
```python
pytest                    # Unit tests for agent logic
pytest-asyncio           # Async test support
hypothesis               # Property-based testing (find edge cases)
```

**Linting & Formatting:**
```python
ruff                     # Fast linter (replaces flake8, black, isort)
mypy                     # Type checking
```

**Environment Management:**
```bash
uv                       # Fast package manager (replaces pip)
pyproject.toml          # Dependency specification
```

**What NOT to use:**
- ❌ **Poetry:** Slower than uv, more complex
- ❌ **Conda:** Overkill for pure Python project

**Confidence:** HIGH

---

### 10. Deployment (Post-MVP)

**Phase 1 (Local/Demo):**
- Docker Compose: Supabase + Streamlit + Python backend
- Git for version control

**Phase 2 (Production):**
- **Backend:** Railway / Render (free tiers available)
- **Database:** Supabase (upgrade to paid as needed)
- **Frontend:** Streamlit Cloud or Vercel
- **Monitoring:** Sentry (error tracking), LangSmith (LLM tracing)

**What NOT to use for MVP:**
- ❌ **AWS/GCP/Azure:** Over-engineered, cost tracking complexity
- ❌ **Kubernetes:** Unnecessary for single-service app

**Confidence:** MEDIUM

---

## Critical Dependencies Summary

| Component | Technology | Free Tier | Confidence |
|-----------|-----------|-----------|------------|
| **Agent Orchestration** | LangGraph 0.2+ | Yes (OSS) | HIGH |
| **LLM** | Google AI (Gemini) | 1500 req/day | HIGH |
| **Database** | Supabase (Postgres + pgvector) | 500MB | HIGH |
| **Financial Data** | yfinance + Alpha Vantage | Yes (rate limited) | MEDIUM |
| **Backtesting** | vectorbt | Yes (OSS) | HIGH |
| **RAG** | LangChain + pgvector | Yes | HIGH |
| **Analysis** | pandas + numpy + scipy | Yes (OSS) | HIGH |
| **Dashboard** | Streamlit | Yes (1GB hosting) | MEDIUM |
| **Testing** | pytest + hypothesis | Yes (OSS) | HIGH |

---

## Open Questions & Validation Needed

1. **LangGraph version stability:** Verify 0.2.x API is stable or if 0.3+ introduces breaking changes
2. **Google AI rate limits:** Confirm 1500 req/day sufficient for 10-agent system with complex workflows
3. **yfinance reliability:** Test fallback strategy under real rate limit conditions
4. **Supabase vector search performance:** Benchmark pgvector with 10k+ document chunks
5. **Streamlit scalability:** Determine at what point migration to FastAPI+React becomes necessary

---

## What We're NOT Using (And Why)

| Technology | Why Excluded |
|------------|--------------|
| **Proprietary data terminals** (Bloomberg, Refinitiv) | $20k+/year, overkill for paper trading MVP |
| **High-frequency trading infrastructure** | Microsecond latency unnecessary for Value Investing (multi-day holding periods) |
| **Blockchain/Web3** | No value add, regulatory complexity |
| **Local LLMs** | Infrastructure cost > API cost for MVP scale |
| **NoSQL databases** | SQL superior for financial relational data |
| **Microservices architecture** | Over-engineering for single-team MVP |

---

## Recommendations for Roadmap

**Phase 1 (Foundation):**
- Set up Supabase instance
- Configure LangGraph + Google AI
- Implement basic StateGraph with 1 agent

**Phase 2 (Data):**
- Integrate yfinance + Alpha Vantage + FRED
- Build fallback and cache layer
- Data quality validation

**Phase 3 (RAG):**
- Load bibliography into Supabase pgvector
- Implement LangChain retrieval
- RAGAs evaluation pipeline

**Phase 4 (Agents):**
- Implement 10 agents layer-by-layer
- LangGraph state schema design
- HITL interrupt mechanisms

**Phase 5 (Backtesting):**
- vectorbt integration
- Monte Carlo modules
- Walk-forward validation

**Phase 6 (Interface):**
- Streamlit dashboard
- Agent reasoning visualization
- HITL approval flows

---

**Last Updated:** 2026-02-01
**Researcher Confidence:** MEDIUM (versions unverified, architectural patterns HIGH confidence)
