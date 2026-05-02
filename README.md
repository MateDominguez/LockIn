# LockIn — AI Investment Decision Swarm

A multi-agent system that performs fundamental equity analysis using a **Bayesian Investment Decision Swarm**. Seven specialized LLM agents collaborate through structured debate, quantitative modeling, and RAG-enhanced reasoning to produce investment recommendations with full audit transparency.

## Why This Exists

Traditional stock screeners give you numbers. Sell-side research gives you narratives. Neither forces bull and bear cases to directly confront each other with math.

LockIn treats investment analysis as a **multi-agent adversarial process**: a bull analyst builds a valuation thesis, a bear analyst tears it apart, they iterate until arguments converge, and then a Bayesian judge synthesizes everything — macro regime, management quality, financial risk scores — into a single probability-weighted recommendation with position sizing.

Every step is auditable. Every number is traceable. The human stays in the loop when confidence is low.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                      │
│              Orchestrates 7 agents via shared state          │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Layer                             │
├───────────────┬──────────────────┬──────────────────────────┤
│  Distribution │    Modifier       │    Orchestration         │
│               │                  │                          │
│  Value Hunter │  Macro Oracle    │  Judge (Bayesian)        │
│  Bear         │  Strategist      │  Optimizer (Kelly/3)     │
│               │  Guardian        │                          │
└───────────────┴──────────────────┴──────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│  Yahoo Finance │ FRED (macro) │ SEC EDGAR │ Earnings Calls   │
├─────────────────────────────────────────────────────────────┤
│  RAG Pipeline (pgvector) │ PostgreSQL │ Audit Logs           │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Macro Regime Detection
The **Macro Oracle** pulls real-time Federal Reserve data (GDP, CPI, yield curves, unemployment) and classifies the current economic regime. This feeds a confidence modifier into the final decision.

### 2. Bull-Bear Dialectic
The **Value Hunter** builds a bullish valuation using EPV, EVA, and Residual Income models, producing a log-normal probability distribution over intrinsic value. The **Bear** agent independently builds an adversarial case with pessimistic assumptions.

They iterate — the bull rebuts the bear's points, the bear challenges the rebuttal — until argument exhaustion is detected via Jaccard similarity (or a max iteration cap). This forces genuine thesis refinement, not just confirmation bias.

### 3. Signal Modifiers
- **Strategist**: Analyzes full earnings call transcripts via NLP to extract a Voice-Tone (VeTO) score and analyst momentum signals
- **Guardian**: Computes Altman Z-Score (bankruptcy risk), Beneish M-Score (earnings manipulation detection), and VoMC Fragility — the only agent that can trigger a **circuit breaker** to halt the entire analysis

### 4. Bayesian Consensus
The **Judge** runs a 7-step Bayesian Consensus Algorithm (pure math, no LLM) that:
- Pools bull and bear distributions
- Applies macro, strategist, and guardian modifiers
- Weighs signals by base rates from academic literature
- Retrieves RAG citations from 10-K filings and earnings transcripts for evidence grounding
- Produces a final `p_success` probability

If confidence is below 40%, a **Human-in-the-Loop interrupt** fires — the system pauses and waits for human review before proceeding.

### 5. Position Sizing
The **Optimizer** applies Kelly Criterion (divided by 3 for conservatism) with hard caps: max 10% per position, max 32.5% per sector.

### 6. Full Audit Trail
Every agent execution is wrapped with `audit_node()`, which logs structured `agent_start` / `agent_end` events to PostgreSQL. Every decision is traceable back to the data and reasoning that produced it.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | **LangGraph** (StateGraph with conditional routing) |
| LLM | **Google Gemini 2.5 Pro / Flash** via LangChain |
| Embeddings | **Gemini Embedding 001** (768-dim) |
| Vector Store | **Supabase pgvector** |
| Database | **PostgreSQL** (Supabase) — state checkpointing, audit logs, financial data |
| Financial Data | **yfinance**, **FRED API**, **SEC EDGAR**, **EarningsCall API** |
| RAG | Parent/child chunking → pgvector with citation-tracked retrieval |
| Eval | **RAGAS** for RAG quality evaluation |
| Language | **Python 3.12+** |

## Key Technical Decisions

- **Agents communicate only through shared state** — no direct inter-agent calls, making the system modular and testable
- **Distribution vs. Modifier pattern** — Distribution agents produce probability distributions; Modifier agents adjust confidence. The Judge combines both families
- **Deterministic math separated from LLM reasoning** — `judge_math.py` is pure computation (the 7-step Bayesian algorithm); `judge.py` adds LLM narrative and RAG citations on top
- **Point-in-time data guards** — the data layer prevents look-ahead bias for backtesting by enforcing temporal boundaries on all data fetches
- **Circuit breaker pattern** — Guardian can veto the entire pipeline if financial risk scores exceed thresholds (Z-Score < 1.8, M-Score > -1.78)

## Project Structure

```
src/lockin/
├── agents/         # 7 LangGraph agent nodes + shared utilities
│   ├── types.py    # ValueDistribution, ConfidenceModifier, JudgeOutput
│   ├── judge_math.py   # Pure 7-step Bayesian Consensus Algorithm
│   ├── valuations.py   # EPV, EVA, RIM, Piotroski F-Score
│   └── risk_scores.py  # Altman Z-Score, Beneish M-Score, VoMC
├── graph/          # LangGraph topology + state schema
│   ├── builder.py  # Graph wiring, routing, HITL
│   └── state.py    # InvestmentState TypedDict
├── data/           # Financial data layer (yfinance, FRED)
│   ├── point_in_time.py  # Future-date guard for backtesting
│   └── validator.py      # Data quality scoring
├── rag/            # Document ingestion + retrieval
│   ├── ingestion.py  # PDF/10-K/transcript → pgvector
│   └── retriever.py  # Citation-tracked vector search
└── utils/          # Config + audit trail
```

## Agent Pipeline Flow

```
macro_oracle ──→ value_hunter ←──→ bear (dialectic loop)
                                      │
                                      ▼
                               strategist ──→ guardian
                                                │
                                          circuit_breaker?
                                         /              \
                                       YES               NO
                                        │                 │
                                       END          judge (Bayesian)
                                                         │
                                                   p_final < 0.40?
                                                    /          \
                                                  YES           NO
                                                   │             │
                                              HITL pause    optimizer
                                                             (Kelly/3)
```

## Status

This is an active project built iteratively with a phase-based development approach. Current state:
- All 7 agents implemented and tested
- Full LangGraph pipeline with conditional routing
- RAG pipeline operational with pgvector
- RAGAS evaluation framework integrated
- Audit trail logging to PostgreSQL
- HITL interrupt mechanism functional

---

Built by [Mateo](https://github.com/mateonoel2)
