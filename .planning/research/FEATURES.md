# Features Research: Multi-Agent Investment Systems

**Domain:** Auditable Value Investing systems with multi-agent architecture
**Research Date:** 2026-02-01
**Confidence Level:** HIGH

## Executive Summary

Multi-agent financial investment systems require a clear feature hierarchy:
- **Table Stakes (12 features):** Must-haves or users abandon the system (audit trail, risk guardrails, data integrity)
- **Differentiators (17 features):** Competitive advantages unique to this system (transparent agent reasoning, dialectical architecture, Value Investing methodology)
- **Anti-Features (12 features):** Things to deliberately NOT build (guaranteed returns, black boxes, gamification)

---

## Table Stakes Features

### Category: Data & Market Access

#### TS-01: Real-Time Market Data Integration
**Description:** Connection to financial data APIs (prices, fundamentals, macroeconomic indicators)

**Why Table Stakes:**
- Cannot analyze assets without data
- Users expect current information, not stale data

**Complexity:** MEDIUM
- API integration (yfinance, Alpha Vantage, FRED)
- Fallback mechanisms for API failures
- Cache layer for cost optimization

**Dependencies:** None (foundational)

**MVP Priority:** HIGH (Phase 1-2)

---

#### TS-02: Fundamental Data Repository
**Description:** Historical storage of financial statements, ratios, and company metrics

**Why Table Stakes:**
- Value Investing requires analyzing trends over 5-10 year periods
- Cannot calculate EPV, Z-Score, etc. without historical data

**Complexity:** MEDIUM
- Database schema for time-series financial data
- Normalization across different data sources
- Handling corporate actions (splits, dividends)

**Dependencies:** TS-01

**MVP Priority:** HIGH (Phase 2)

---

### Category: Portfolio Management

#### TS-03: Portfolio Tracking
**Description:** View current holdings, positions, cash, total value

**Why Table Stakes:**
- Users must know what they own
- Required for position sizing and rebalancing

**Complexity:** LOW
- Simple CRUD operations on positions table
- Aggregate calculations (total value, allocation %)

**Dependencies:** None

**MVP Priority:** HIGH (Phase 4)

---

#### TS-04: Trade History & Audit Log
**Description:** Complete record of all trades (paper or real) with timestamps, rationale, agent decisions

**Why Table Stakes:**
- **EU AI Act requirement:** Auditability of AI decisions
- Users need to understand past actions
- Required for backtesting validation

**Complexity:** MEDIUM
- LangGraph checkpointing integration
- Structured logging of agent state transitions
- Queryable audit trail (filter by agent, asset, date)

**Dependencies:** LangGraph state persistence

**MVP Priority:** CRITICAL (Phase 1 — architectural decision)

---

### Category: Risk Management

#### TS-05: Risk Guardrails
**Description:** Hard limits on position sizes, sector concentration, portfolio volatility

**Why Table Stakes:**
- Users must be protected from catastrophic losses
- Regulatory requirement for investment advisors
- Builds trust in autonomous system

**Complexity:** MEDIUM
- Configurable risk parameters
- Pre-trade compliance checks (Optimizer agent)
- Alert system when limits approached

**Dependencies:** TS-03

**MVP Priority:** HIGH (Phase 4)

---

#### TS-06: Fraud Detection (Guardian Agent)
**Description:** Altman Z-Score (bankruptcy risk) and Beneish M-Score (earnings manipulation)

**Why Table Stakes:**
- Prevents investing in fraudulent companies
- Core function of Guardian agent
- Loss prevention more important than gain seeking

**Complexity:** HIGH
- Implement scoring algorithms
- Handle missing data gracefully
- Threshold calibration (false positive vs false negative trade-off)

**Dependencies:** TS-02

**MVP Priority:** HIGH (Phase 3 — Bears layer)

---

### Category: Human Interaction

#### TS-07: Human-in-the-Loop (HITL) Approval Workflow
**Description:** System pauses before critical decisions when confidence is low or agents disagree

**Why Table Stakes:**
- Users won't trust fully autonomous financial decisions
- **EU AI Act:** Human oversight required for high-risk AI
- Prevents runaway agent behavior

**Complexity:** HIGH
- LangGraph interrupt mechanism
- UI for presenting agent debate to user
- Resume execution after human input

**Dependencies:** LangGraph checkpointing, frontend

**MVP Priority:** CRITICAL (Phase 1 — architectural decision)

---

#### TS-08: Explainability Dashboard
**Description:** View agent reasoning, data sources, calculations behind every recommendation

**Why Table Stakes:**
- **EU AI Act:** Right to explanation
- Users need transparency to trust system
- Differentiator vs "black box" robo-advisors

**Complexity:** HIGH
- Capture agent thoughts during execution
- Present complex reasoning in digestible format
- Link to source data (which earnings call, which financial ratio)

**Dependencies:** TS-04, frontend

**MVP Priority:** HIGH (Phase 6 — Interface)

---

### Category: System Reliability

#### TS-09: Data Quality Validation
**Description:** Detect stale data, missing fields, anomalies (e.g., negative book value)

**Why Table Stakes:**
- Garbage in, garbage out
- API failures must be caught before agent execution
- Prevents nonsensical recommendations

**Complexity:** MEDIUM
- Schema validation
- Staleness checks (max age thresholds)
- Anomaly detection (statistical outliers)

**Dependencies:** TS-01

**MVP Priority:** HIGH (Phase 2)

---

#### TS-10: Error Handling & Graceful Degradation
**Description:** System continues operating when non-critical components fail

**Why Table Stakes:**
- APIs will fail, LLMs will timeout
- Users expect resilience
- Prevents total system failure from single component

**Complexity:** MEDIUM
- Try-except wrappers with specific error types
- Fallback strategies (cache, alternative data sources)
- HITL escalation when degraded

**Dependencies:** TS-01, TS-07

**MVP Priority:** MEDIUM (Phase 2-3)

---

#### TS-11: Backtesting Engine
**Description:** Simulate strategy on historical data to validate before paper/real trading

**Why Table Stakes:**
- Cannot deploy untested strategy
- Users need confidence in approach
- Regulatory requirement for investment advisors

**Complexity:** HIGH
- Point-in-time data access (avoid look-ahead bias)
- Transaction cost modeling
- Performance metrics (Sharpe, max drawdown, win rate)

**Dependencies:** TS-02, vectorbt integration

**MVP Priority:** HIGH (Phase 5)

---

#### TS-12: Paper Trading Mode
**Description:** Simulate real trades with fake money before risking capital

**Why Table Stakes:**
- Users won't risk real money without proof
- Validate system in live market conditions
- Regulatory requirement for new strategies

**Complexity:** MEDIUM
- Simulated order execution (market orders, limit orders)
- Track simulated P&L
- Compare to real market performance

**Dependencies:** TS-11

**MVP Priority:** HIGH (Phase 5)

---

## Differentiator Features

### Category: Unique Architecture

#### DIFF-01: Transparent Agent Reasoning Logs
**Description:** Every agent publishes structured "Log de Explicabilidad" showing WHY it made a decision

**Competitive Advantage:**
- Most AI investment tools are black boxes
- Builds user trust and understanding
- Enables continuous improvement (user can suggest better logic)

**Complexity:** MEDIUM
- Standardized logging format across agents
- Store in audit_logs table with searchable fields
- UI to surface logs contextually

**Dependencies:** TS-04

**MVP Priority:** HIGH (Phase 3-6)

---

#### DIFF-02: Dialectical Debate Architecture (Bulls vs Bears)
**Description:** Forced adversarial process where Bear agent challenges every Bull recommendation

**Competitive Advantage:**
- Most systems only seek confirming evidence (bias)
- Mimics best human investment processes (red teams)
- Produces higher-quality decisions

**Complexity:** HIGH
- LangGraph conditional routing based on disagreement
- Scoring debate strength
- Judge agent synthesis logic (fuzzy logic)

**Dependencies:** LangGraph, multiple agents implemented

**MVP Priority:** HIGH (Phase 3 — core differentiation)

---

#### DIFF-03: Value Investing Methodology Built-In
**Description:** Agents hardcoded with Graham/Greenwald principles (EPV, margin of safety, moat analysis)

**Competitive Advantage:**
- Most robo-advisors use momentum/growth strategies
- Appeals to value investing community (large, underserved market)
- Timeless principles (less likely to fail in regime changes)

**Complexity:** HIGH
- Implement EPV calculation (Value Hunter agent)
- VeTO/VoMC scoring (Strategist agent)
- Moat rating system

**Dependencies:** TS-02

**MVP Priority:** HIGH (Phase 3 — Layers 2-3)

---

#### DIFF-04: EU AI Act Compliance Dashboard
**Description:** Pre-built reporting for transparency, human oversight, auditability requirements

**Competitive Advantage:**
- Most competitors will scramble to comply in 2026
- Reduces regulatory risk for users
- Appeals to European market

**Complexity:** MEDIUM
- Map features to AI Act requirements
- Generate compliance reports
- Document risk classification (system is "support tool", not "high-risk AI")

**Dependencies:** TS-04, TS-08

**MVP Priority:** MEDIUM (Phase 6)

---

#### DIFF-05: Multi-Regime Macro Adaptation (Macro Oracle)
**Description:** System adjusts strategy based on economic regime (growth/inflation quadrants)

**Competitive Advantage:**
- Most systems fail during regime changes (e.g., 2022 inflation surprise)
- Implements Ray Dalio "All Weather" thinking
- Protects capital in downturns

**Complexity:** HIGH
- Economic indicator integration (yield curve, inflation expectations)
- Regime classification logic
- Dynamic position sizing (macro_multiplier)

**Dependencies:** TS-01 (FRED API for macro data)

**MVP Priority:** MEDIUM (Phase 3 — Layer 1)

---

#### DIFF-06: Alternative Data Sentiment Analysis
**Description:** Sentiment Agent analyzes earnings calls, news, forums for narrative risk

**Competitive Advantage:**
- Detects problems before they appear in financial statements
- Uses NLP/LLM capabilities most competitors ignore
- Early warning system for reputation crises

**Complexity:** HIGH
- Earnings call transcript scraping/API
- NLP sentiment extraction
- Semantic volatility calculation

**Dependencies:** LLM integration, alternative data sources

**MVP Priority:** LOW (Phase 3 — nice-to-have)

---

#### DIFF-07: Knowledge Base RAG (Financial Bibliography)
**Description:** Agents cite Graham, Dalio, Greenwald when making decisions

**Competitive Advantage:**
- Most AI systems hallucinate financial principles
- Grounds recommendations in proven methodology
- Educational value for users (learn while investing)

**Complexity:** HIGH
- PDF/book ingestion pipeline
- Chunk and embed (text-embedding-004)
- Citation mechanism (link recommendation to source passage)
- RAGAs validation (prevent hallucinations)

**Dependencies:** Supabase pgvector, LangChain

**MVP Priority:** MEDIUM (Phase 3)

---

#### DIFF-08: Monte Carlo Stress Testing (Bear Agent)
**Description:** Simulate thousands of scenarios to find fragile assumptions

**Competitive Advantage:**
- Most systems use point estimates (single future)
- Quantifies uncertainty rigorously
- Prevents overconfidence in projections

**Complexity:** HIGH
- Implement Monte Carlo simulation (scipy.stats)
- Define probability distributions for inputs (revenue growth, margins)
- Aggregate results into risk score

**Dependencies:** TS-02

**MVP Priority:** MEDIUM (Phase 3 — Bear agent)

---

#### DIFF-09: Historical Valuation Context (Historian Agent)
**Description:** Compare current valuation to 10-year history to detect overpricing

**Competitive Advantage:**
- Prevents buying at tops (mean reversion)
- Most retail investors ignore historical context
- Implements Shiller CAPE methodology

**Complexity:** MEDIUM
- Calculate historical percentiles
- Adjust for structural changes (e.g., higher margins in SaaS era)
- Generate alerts for extreme valuations

**Dependencies:** TS-02

**MVP Priority:** MEDIUM (Phase 3 — Bears layer)

---

#### DIFF-10: Portfolio Optimizer with Kelly Criterion
**Description:** Position sizing based on conviction and correlation, not equal-weight

**Competitive Advantage:**
- Most robo-advisors use naive equal-weighting
- Maximizes long-term growth rate mathematically
- Accounts for hidden correlations (e.g., tech stocks moving together)

**Complexity:** HIGH
- Covariance matrix calculation
- Modified Kelly formula (fractional Kelly to reduce risk)
- Rebalancing logic

**Dependencies:** TS-03, TS-05

**MVP Priority:** MEDIUM (Phase 4)

---

#### DIFF-11: Execution Timing (Trader Agent)
**Description:** Wait for technical entry points (RSI, VWAP) to minimize slippage

**Competitive Advantage:**
- Most fundamental systems ignore entry timing (leave 1-2% on table)
- Improves realized returns without changing strategy
- Especially valuable for less liquid stocks

**Complexity:** MEDIUM
- Technical indicator calculation (TA-Lib or custom)
- Limit order logic
- Track execution quality (realized price vs decision price)

**Dependencies:** TS-01 (intraday data)

**MVP Priority:** LOW (Phase 5 — optimization)

---

#### DIFF-12: Organizational Capability Analysis (VeTO/VoMC)
**Description:** Strategist agent evaluates management quality, innovation capacity, talent retention

**Competitive Advantage:**
- Most quant systems ignore qualitative factors
- Implements novel academic framework (Cabanelas 2015)
- Predicts execution risk (can management deliver on vision?)

**Complexity:** VERY HIGH
- Proxy metrics for VeTO dimensions (hard to quantify)
- Data sources: LinkedIn (employee turnover), patent filings, earnings call tone
- Scoring calibration

**Dependencies:** Alternative data sources

**MVP Priority:** LOW (Phase 3 — Strategist agent, can simplify for MVP)

---

#### DIFF-13: Consensus Mechanism with Fuzzy Logic (Judge Agent)
**Description:** Arbitrate Bull vs Bear using weighted evidence, not binary vote

**Competitive Advantage:**
- Most multi-agent systems use simple voting (ignores argument strength)
- Implements advanced AI technique (fuzzy logic)
- Produces nuanced decisions (partial positions based on confidence)

**Complexity:** VERY HIGH
- Fuzzy logic implementation (membership functions)
- Weight calibration (how much to trust each agent)
- Explanation generation (why Judge sided with Bull/Bear)

**Dependencies:** All agents in Layers 2-3

**MVP Priority:** MEDIUM (Phase 4 — can use simpler voting for MVP)

---

#### DIFF-14: Live Agent Activity Visualization
**Description:** Real-time dashboard showing which agents are thinking, debating, waiting for HITL

**Competitive Advantage:**
- Users see system "thinking" (builds trust)
- Transparency of process, not just outputs
- Educational/entertaining (users learn how analysis works)

**Complexity:** MEDIUM
- WebSocket updates from LangGraph state changes
- Visual state machine display
- Agent status indicators (idle, working, blocked)

**Dependencies:** Frontend, LangGraph streaming

**MVP Priority:** MEDIUM (Phase 6 — UI polish)

---

#### DIFF-15: Configurable Risk Profiles
**Description:** User adjusts aggressiveness (conservative, balanced, growth) with transparent trade-offs

**Competitive Advantage:**
- Most systems one-size-fits-all
- Users feel in control
- Expands addressable market (risk-averse and risk-seeking)

**Complexity:** LOW
- Slider maps to parameters (position size limits, conviction thresholds)
- Pre-configured profiles
- Show expected volatility/return for each profile

**Dependencies:** TS-05

**MVP Priority:** LOW (post-MVP feature)

---

#### DIFF-16: Walk-Forward Validation
**Description:** Backtest uses rolling windows (train on 2015-2020, test on 2021) to prevent overfitting

**Competitive Advantage:**
- Most backtests overfit to history (look good on paper, fail live)
- Industry best practice (but rarely implemented)
- Builds credibility with sophisticated users

**Complexity:** HIGH
- Partition historical data into train/test windows
- Re-run backtest multiple times
- Aggregate out-of-sample performance

**Dependencies:** TS-11

**MVP Priority:** MEDIUM (Phase 5)

---

#### DIFF-17: Multi-Language Support (Spanish MVP)
**Description:** UI and agent reasoning in Spanish (given TFM is Spanish context)

**Competitive Advantage:**
- Most AI investment tools English-only
- Untapped Spanish-speaking market (LatAm, Spain)
- Differentiation in academic context (shows localization thinking)

**Complexity:** LOW
- LLM prompts in Spanish (Gemini supports it)
- Streamlit UI text in Spanish
- Financial term translations

**Dependencies:** None

**MVP Priority:** LOW (nice-to-have, not critical)

---

## Anti-Features (DO NOT BUILD)

### AF-01: Guaranteed Returns Marketing
**Why NOT:**
- Illegal in most jurisdictions
- Destroys trust when reality doesn't match
- Attracts wrong users (get-rich-quick crowd)

**Instead:** Emphasize risk management and transparency

---

### AF-02: Black Box Predictions
**Why NOT:**
- Contradicts core value proposition (transparency)
- Violates EU AI Act
- Users won't trust unexplained recommendations

**Instead:** Always show agent reasoning

---

### AF-03: "Set and Forget" Auto-Trading
**Why NOT:**
- Too risky for autonomous operation (bugs can lose real money)
- Reduces user engagement (learning opportunity lost)
- Regulatory liability

**Instead:** HITL approval for all trades, even in "auto" mode

---

### AF-04: Social/Viral Features (Leaderboards, Sharing P&L)
**Why NOT:**
- Encourages unhealthy competition
- Gamifies serious financial decisions
- Attracts speculators over investors

**Instead:** Focus on individual learning and long-term wealth building

---

### AF-05: High-Frequency Trading
**Why NOT:**
- Contradicts Value Investing philosophy (multi-year holding periods)
- Requires microsecond latency (infrastructure cost explosion)
- Regulatory complexity

**Instead:** Daily rebalancing at most

---

### AF-06: Cryptocurrency Trading
**Why NOT:**
- Crypto incompatible with fundamental analysis (no cash flows)
- Regulatory uncertainty
- Distracts from core value proposition

**Instead:** Stick to equities/bonds with auditable financials

---

### AF-07: Margin/Leverage Trading
**Why NOT:**
- Amplifies losses (destroys capital)
- Graham explicitly warns against leverage
- Adds regulatory complexity

**Instead:** Cash-only positions (Graham's rule: never borrow to invest)

---

### AF-08: Penny Stocks / Microcaps
**Why NOT:**
- Lack reliable financial data
- Manipulation risk high
- Illiquidity (can't exit positions)

**Instead:** Minimum market cap filter (e.g., $1B+)

---

### AF-09: Options/Derivatives
**Why NOT:**
- Complex risk profiles (Greeks, time decay)
- Incompatible with Value Investing (speculation, not ownership)
- Requires different agent logic

**Instead:** Long-only equity positions

---

### AF-10: Proprietary Data Moats
**Why NOT:**
- Lock users into platform (reduces trust)
- Expensive to acquire/maintain for MVP
- Contradicts transparency principle

**Instead:** Use public data sources, let users verify

---

### AF-11: Freemium Conversion Pressure
**Why NOT:**
- Adds dark patterns (artificial limits)
- Distracts from core product development
- Degrades user experience

**Instead:** Focus on building great product, monetize later

---

### AF-12: Mobile App (MVP)
**Why NOT:**
- Doubles development effort (iOS + Android)
- Financial analysis better suited to desktop (charts, tables)
- Webapp is mobile-responsive (good enough for MVP)

**Instead:** Responsive webapp, defer native apps to post-MVP

---

## Feature Dependencies Graph

```
Foundation Layer:
├─ TS-01: Market Data
├─ TS-04: Audit Log (LangGraph checkpointing)
└─ TS-07: HITL (LangGraph interrupts)

Data Layer (depends on Foundation):
├─ TS-02: Fundamental Data Repository
├─ TS-09: Data Quality Validation
└─ TS-10: Error Handling

Agent Intelligence Layer (depends on Data):
├─ TS-06: Fraud Detection (Guardian)
├─ DIFF-03: Value Investing (Value Hunter, Strategist)
├─ DIFF-05: Macro Oracle
├─ DIFF-06: Sentiment Agent
├─ DIFF-07: Knowledge Base RAG
├─ DIFF-08: Monte Carlo (Bear)
├─ DIFF-09: Historical Context (Historian)
└─ DIFF-12: VeTO/VoMC (Strategist)

Orchestration Layer (depends on Agents):
├─ DIFF-02: Dialectical Debate
├─ DIFF-13: Judge (Fuzzy Logic)
└─ DIFF-10: Portfolio Optimizer

Execution Layer (depends on Orchestration):
├─ TS-03: Portfolio Tracking
├─ TS-05: Risk Guardrails
├─ TS-11: Backtesting
├─ TS-12: Paper Trading
├─ DIFF-11: Trader (Timing)
└─ DIFF-16: Walk-Forward Validation

Transparency Layer (depends on all above):
├─ TS-08: Explainability Dashboard
├─ DIFF-01: Reasoning Logs
├─ DIFF-04: EU AI Act Dashboard
└─ DIFF-14: Live Activity Visualization
```

---

## MVP Feature Prioritization

### Phase 1 (Foundation - Week 1-2):
- TS-04: Audit Log
- TS-07: HITL
- LangGraph basic setup

### Phase 2 (Data - Week 3-4):
- TS-01: Market Data (yfinance + fallback)
- TS-02: Fundamental Repository
- TS-09: Data Quality

### Phase 3 (Agents - Week 5-10):
- TS-06: Guardian (Z-Score, M-Score)
- DIFF-03: Value Hunter (EPV)
- DIFF-02: Bear + Historian (simplified)
- DIFF-07: RAG (bibliography)
- Dialectical debate (simplified)

### Phase 4 (Orchestration - Week 11-12):
- Judge (simple voting, defer fuzzy logic)
- DIFF-10: Optimizer (simplified)
- TS-05: Risk Guardrails

### Phase 5 (Simulation - Week 13-15):
- TS-11: Backtesting (vectorbt)
- TS-12: Paper Trading
- DIFF-16: Walk-Forward (if time)

### Phase 6 (Interface - Week 16-18):
- TS-08: Explainability Dashboard (Streamlit)
- DIFF-01: Reasoning Logs UI
- DIFF-14: Activity Visualization (if time)

**Total MVP Timeline:** 18 weeks (~4.5 months) — fits June 2026 deadline

---

## Complexity Assessment Summary

| Feature | Complexity | MVP Priority | Can Defer? |
|---------|-----------|--------------|------------|
| TS-01: Market Data | MEDIUM | HIGH | No |
| TS-02: Fundamentals | MEDIUM | HIGH | No |
| TS-03: Portfolio Tracking | LOW | HIGH | No |
| TS-04: Audit Log | MEDIUM | CRITICAL | No |
| TS-05: Risk Guardrails | MEDIUM | HIGH | Partially |
| TS-06: Fraud Detection | HIGH | HIGH | Partially (M-Score optional) |
| TS-07: HITL | HIGH | CRITICAL | No |
| TS-08: Explainability | HIGH | HIGH | Partially (basic version OK) |
| TS-09: Data Quality | MEDIUM | HIGH | Partially |
| TS-10: Error Handling | MEDIUM | MEDIUM | Partially |
| TS-11: Backtesting | HIGH | HIGH | No (core validation) |
| TS-12: Paper Trading | MEDIUM | HIGH | No (core validation) |
| DIFF-01: Reasoning Logs | MEDIUM | HIGH | Partially |
| DIFF-02: Dialectical Debate | HIGH | HIGH | No (core differentiation) |
| DIFF-03: Value Investing | HIGH | HIGH | Partially (simplify VeTO) |
| DIFF-04: EU AI Act | MEDIUM | MEDIUM | Yes (post-MVP) |
| DIFF-05: Macro Oracle | HIGH | MEDIUM | Yes (use static regime for MVP) |
| DIFF-06: Sentiment | HIGH | LOW | Yes (defer) |
| DIFF-07: RAG | HIGH | MEDIUM | Partially (small knowledge base OK) |
| DIFF-08: Monte Carlo | HIGH | MEDIUM | Partially (simple sensitivity) |
| DIFF-09: Historian | MEDIUM | MEDIUM | Partially |
| DIFF-10: Optimizer | HIGH | MEDIUM | Partially (equal-weight fallback) |
| DIFF-11: Trader Timing | MEDIUM | LOW | Yes (defer) |
| DIFF-12: VeTO/VoMC | VERY HIGH | LOW | Yes (simplify or defer) |
| DIFF-13: Fuzzy Logic Judge | VERY HIGH | MEDIUM | Yes (use voting for MVP) |
| DIFF-14: Live Visualization | MEDIUM | MEDIUM | Yes (static dashboard OK for MVP) |
| DIFF-15: Risk Profiles | LOW | LOW | Yes (defer) |
| DIFF-16: Walk-Forward | HIGH | MEDIUM | Yes (defer) |
| DIFF-17: Multi-Language | LOW | LOW | Yes (defer) |

---

**Last Updated:** 2026-02-01
**Researcher Confidence:** HIGH
