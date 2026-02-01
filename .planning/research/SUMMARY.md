# Project Research Summary

**Project:** LockIn - Multi-Agent Value Investing System
**Domain:** AI-powered financial analysis with multi-agent architecture
**Researched:** 2026-02-01
**Confidence:** HIGH

## Executive Summary

LockIn is a multi-agent investment analysis system built on **LangGraph** orchestration, implementing **Value Investing methodology** (Graham/Greenwald principles) through a **dialectical architecture** where Bull agents debate Bear agents to produce auditable recommendations. The system prioritizes **EU AI Act compliance** through transparent reasoning trails and human-in-the-loop oversight at critical decision points.

The recommended approach centers on a **layered StateGraph** (Context → Bulls → Bears → Arbitration → Execution) using **free-tier technologies** (Google AI Gemini, Supabase PostgreSQL+pgvector, yfinance) to minimize MVP costs while enabling future scaling. The architecture treats agents as pure functions operating on shared state, ensuring auditability and reproducibility — critical for financial applications and regulatory compliance.

**Key risks** include look-ahead bias in backtesting (invalidates validation), RAG hallucination (system invents fake financial principles), and HITL fatigue (users rubber-stamp bad decisions). Mitigation requires point-in-time data access wrappers, RAGAs validation with citation enforcement, and risk-based HITL triggering that only interrupts for high-stakes decisions. The build order is critical: state schema first (locks interfaces), then vertical slice (proves architecture), then horizontal scaling (add agents layer-by-layer).

## Key Findings

### Recommended Stack

The standard stack for multi-agent financial investment systems centers on **LangGraph 0.2+** for orchestration (native checkpointing enables HITL interrupts), **Google AI Gemini** for cost-effective LLM access (1500 req/day free tier sufficient for MVP), and **Supabase** for unified PostgreSQL + pgvector storage (audit logs, checkpoints, and RAG vector search in one service).

**Core technologies:**
- **LangGraph 0.2+**: Multi-agent orchestration with state management — chosen for auditable state transitions and HITL checkpoint/resume capability
- **Google AI Gemini 1.5 Pro/Flash**: LLM provider — 1500 free requests/day, 1M token context window, native function calling
- **Supabase (PostgreSQL + pgvector)**: Database — 500MB free tier, handles audit logs, agent checkpoints, and vector similarity search for RAG
- **yfinance + Alpha Vantage + FRED**: Market data — free APIs with fallback strategy (yfinance primary, Alpha Vantage backup, FRED for macro indicators)
- **vectorbt**: Backtesting engine — NumPy-based speed, portfolio-level simulation, transaction cost modeling
- **Streamlit**: MVP dashboard — pure Python, fastest path to HITL approval UI and agent visualization
- **pandas + numpy + scipy**: Financial analysis — EPV calculation, Monte Carlo simulation, statistical analysis

**What to avoid:** Local LLMs (infrastructure cost > API cost for MVP), NoSQL databases (financial data is relational), microservices architecture (over-engineering for single-team MVP), proprietary data terminals (Bloomberg costs $24k/year, overkill for paper trading).

### Expected Features

Multi-agent financial investment systems require a clear feature hierarchy distinguishing **table stakes** (12 features users expect), **differentiators** (17 features providing competitive advantage), and **anti-features** (12 things to deliberately not build).

**Must have (table stakes):**
- **Real-time market data integration** — connection to yfinance/Alpha Vantage/FRED with fallback mechanisms
- **Trade history & audit log** — complete decision trail required for EU AI Act compliance
- **HITL approval workflow** — LangGraph interrupt mechanism for human oversight at critical points
- **Risk guardrails** — hard limits on position sizes, sector concentration, portfolio volatility
- **Fraud detection** — Altman Z-Score (bankruptcy) and Beneish M-Score (earnings manipulation) via Guardian agent
- **Explainability dashboard** — view agent reasoning, data sources, calculations behind every recommendation
- **Data quality validation** — detect stale data, missing fields, anomalies before agent execution
- **Backtesting engine** — simulate strategy on historical data with vectorbt
- **Paper trading mode** — validate in live markets before risking capital

**Should have (competitive differentiators):**
- **Dialectical debate architecture** — forced adversarial process (Bulls vs Bears) prevents confirmation bias
- **Value Investing methodology built-in** — EPV calculation, margin of safety, moat analysis (Graham/Greenwald principles)
- **Knowledge base RAG** — agents cite Graham/Dalio/Greenwald when making decisions, grounded in proven methodology
- **Monte Carlo stress testing** — Bear agent simulates thousands of scenarios to find fragile assumptions
- **Portfolio optimizer with Kelly criterion** — position sizing based on conviction and correlation, not naive equal-weighting
- **Transparent agent reasoning logs** — structured "Log de Explicabilidad" showing WHY each decision was made
- **Multi-regime macro adaptation** — Macro Oracle adjusts strategy based on economic regime (growth/inflation quadrants)

**Defer (v2+):**
- **VeTO/VoMC organizational capability analysis** — management quality scoring (very high complexity, proxy metrics hard to quantify)
- **Fuzzy logic Judge** — weighted evidence arbitration (can use simpler voting for MVP)
- **Execution timing (Trader agent)** — technical entry points to minimize slippage (1-2% improvement, low priority)
- **Live agent activity visualization** — real-time WebSocket updates (static dashboard sufficient for MVP)
- **Walk-forward validation** — rolling window backtesting (high complexity, can defer post-MVP)

**Anti-features (DO NOT BUILD):**
- **Guaranteed returns marketing** — illegal, destroys trust when reality doesn't match
- **Black box predictions** — contradicts core value proposition (transparency)
- **"Set and forget" auto-trading** — too risky for autonomous operation, reduces user engagement
- **Margin/leverage trading** — Graham explicitly warns against leverage, amplifies losses
- **Cryptocurrency trading** — incompatible with fundamental analysis (no cash flows)
- **Options/derivatives** — complex risk profiles, incompatible with Value Investing philosophy

### Architecture Approach

The architecture follows a **layered StateGraph pattern** where agents are pure functions `(state, config) → state_updates` operating on a shared `InvestmentState` TypedDict. No agent-to-agent direct communication — all routing via LangGraph conditional edges to ensure auditability. State-centric design with PostgreSQL checkpointing enables HITL interrupts and EU AI Act compliance.

**Major components:**
1. **StateGraph Orchestrator** — LangGraph workflow managing agent execution order via conditional edges (thesis → antithesis → synthesis flow)
2. **Shared State (InvestmentState TypedDict)** — single source of truth containing all agent inputs/outputs, serialized to PostgreSQL via checkpointer
3. **Agent Layers** — Layer 1 (Context: Macro Oracle + Sentiment), Layer 2 (Bulls: Value Hunter + Strategist), Layer 3 (Bears: Bear + Historian + Guardian), Layer 4 (Orchestration: Judge + Optimizer), Layer 5 (Execution: Trader)
4. **HITL Module** — interrupt node using LangGraph checkpointing, pauses execution for human review when disagreement is high or confidence is low
5. **Knowledge Base RAG** — Supabase pgvector storing embedded chunks from Graham/Dalio/Greenwald books, queried via LangChain retrieval
6. **Audit Logger** — PostgreSQL table recording complete state transitions for EU AI Act compliance and decision reconstruction

**Critical patterns:**
- **Pure function agents** — stateless, testable, reproducible (same state → same output when temperature=0)
- **Conditional routing for dialectical flow** — routing functions check state flags (e.g., `fraud_veto`, `conviction < 0.6`) to decide next node
- **State reducers for conflict resolution** — multiple agents writing to same key use `Annotated[list, lambda old, new: old + new]` for append semantics
- **Point-in-time data access** — wrapper ensures agents only see data available as of decision date (prevents look-ahead bias)

### Critical Pitfalls

Research identified 19 pitfalls across multi-agent financial systems. The top 5 critical failures that destroy credibility:

1. **Look-ahead bias in backtesting (CRIT-01)** — using future data when simulating historical decisions (e.g., end-of-day close price for "morning" buy decision). **Prevention:** Point-in-time data wrapper, lag all features by 1 day, include delisted stocks (survivorship bias). **Impact:** Backtest shows 30% returns, live trading loses money — invalidates entire validation.

2. **Agent coordination deadlocks (CRIT-02)** — circular dependencies causing infinite loops (Judge → Bear → Judge → ...). **Prevention:** Acyclic graph design (layers flow forward only), Judge has final say (no re-routing back to Bulls/Bears), max debate rounds = 1. **Impact:** System hangs, user waits forever, timeout kills analysis.

3. **RAG hallucination contamination (CRIT-03)** — LLM invents fake financial principles instead of citing retrieved sources. **Prevention:** Enforce citations in prompt, RAGAs faithfulness validation (score > 0.8), manual spot-check of 10 responses. **Impact:** Agents make decisions based on invented methodology, destroys credibility with experts.

4. **Overfitting to training period (CRIT-04)** — backtest optimized for 2015-2020 bull market collapses in 2022 bear market. **Prevention:** Multi-regime testing (include at least one bear market), walk-forward validation, verify strategy logic makes sense (not data-mined parameters). **Impact:** Paper trading shows 40% drawdown in first month.

5. **HITL fatigue (CRIT-08)** — triggers so often users rubber-stamp bad decisions without reading. **Prevention:** Risk-based triggering (high-risk scenarios only: fraud veto, no margin of safety, >10% position size, conviction < 0.5), auto-approve low-risk decisions, summary-first UI. **Impact:** HITL becomes security theater, defeats purpose of human oversight.

**Additional moderate pitfalls:**
- **State explosion** — shared state grows unbounded, checkpointing becomes slow (keep last 50 messages, move large data to DB)
- **Token cost explosion** — unnecessary context in LLM calls (use Haiku for simple tasks, summarize documents before RAG, cache embeddings)
- **Data quality silent failures** — APIs return stale/incorrect data, system doesn't notice (validation layer with staleness checks, fallback strategy, HITL on low quality score)
- **Non-deterministic debugging nightmare** — LLM temperature > 0 + unseeded randomness (use temperature=0 for agent logic, seed all random operations)
- **EU AI Act compliance theater** — logging outputs without explainability of reasoning (structured ExplainableDecision dataclass with bull_case, bear_case, judge_rationale, citations, data provenance)

## Implications for Roadmap

Based on research, suggested 6-phase structure prioritizing architectural decisions first, then vertical slice validation, then horizontal scaling:

### Phase 1: Foundation (Week 1-2)
**Rationale:** State schema locks in all agent interfaces — changing mid-project breaks everything. Checkpointing must be designed upfront (hard to retrofit). Prove LangGraph architecture works before building agents.

**Delivers:**
- `InvestmentState` TypedDict fully defined with all Layer 1-5 output fields
- Basic StateGraph with 1 dummy agent (end-to-end flow working)
- PostgresSaver checkpointing configured and tested
- HITL interrupt mechanism validated (manual trigger → pause → resume)
- Global configuration (temperature=0, random seeds, API keys in .env)

**Addresses:**
- TS-04: Audit Log (state schema includes reasoning fields)
- TS-07: HITL (interrupt architecture)
- CRIT-02: Deadlocks (acyclic graph design)
- CRIT-05: Non-determinism (temperature=0, seeded randomness)
- CRIT-06: Compliance (state schema with explainability fields)
- MOD-05: Over-engineering (monolith decision, defer microservices)

**Avoids:** Building all 10 agents before testing architecture (integration nightmare), changing state schema mid-project (endless refactoring), stateful agents (non-reproducible bugs).

**Research flag:** SKIP — LangGraph patterns well-documented, standard setup.

---

### Phase 2: Data Layer (Week 3-4)
**Rationale:** Data quality issues must be caught before agents execute. Fallback strategy prevents total failure from single API. Point-in-time access prevents look-ahead bias (catches it architecturally, not through discipline).

**Delivers:**
- yfinance integration with Alpha Vantage fallback and FRED for macro indicators
- `fetch_financials_with_validation()` — staleness checks, completeness validation, sanity checks
- Point-in-time data wrapper (`PointInTimeData` class) for backtesting
- Cache layer for API rate limit resilience
- Fundamental data repository (PostgreSQL schema for time-series financial statements)

**Uses:**
- yfinance (primary market data)
- Alpha Vantage (backup fundamentals)
- FRED API (macro indicators for Macro Oracle)
- PostgreSQL (time-series storage)

**Addresses:**
- TS-01: Market Data Integration
- TS-02: Fundamental Data Repository
- TS-09: Data Quality Validation
- TS-10: Error Handling (fallback mechanisms)
- CRIT-01: Look-ahead Bias (point-in-time wrapper)
- CRIT-07: Data Quality Silent Failures (validation layer)

**Avoids:** Garbage in, garbage out (stale/incorrect data making bad recommendations), API failures killing entire analysis, survivorship bias in backtesting.

**Research flag:** SKIP — yfinance/Alpha Vantage/FRED well-documented, standard patterns.

---

### Phase 3: Agent Intelligence (Week 5-10)
**Rationale:** Core differentiation is dialectical debate (Bulls vs Bears). Must work before execution layer. Most complex logic (EPV, Monte Carlo, Z-Score). Highest risk of rework. RAG grounds decisions in proven methodology (prevents hallucinations).

**Delivers:**
- Layer 1: Macro Oracle (regime classification via FRED data) + Sentiment Agent (earnings call analysis)
- Layer 2: Value Hunter (EPV calculation, margin of safety, moat rating) + Strategist (simplified VeTO scoring, defer full organizational capability analysis)
- Layer 3: Bear (Monte Carlo sensitivity testing), Historian (historical valuation percentiles), Guardian (Altman Z-Score, Beneish M-Score)
- Layer 4: Judge (simplified voting, defer fuzzy logic to post-MVP)
- Knowledge Base RAG: Ingest Graham/Dalio/Greenwald excerpts, embed with text-embedding-004, store in Supabase pgvector, LangChain retrieval with citation enforcement
- RAGAs validation pipeline (faithfulness > 0.8)

**Implements:**
- Dialectical debate architecture (conditional routing based on disagreement)
- Value Investing methodology (DIFF-03)
- Transparent reasoning logs (DIFF-01)
- Fraud detection (TS-06)
- RAG knowledge base (DIFF-07)

**Addresses:**
- DIFF-02: Dialectical Debate (core differentiation)
- DIFF-03: Value Investing Methodology
- TS-06: Fraud Detection
- DIFF-07: Knowledge Base RAG
- DIFF-08: Monte Carlo Stress Testing (simplified)
- DIFF-09: Historical Valuation Context
- CRIT-03: RAG Hallucination (citation enforcement, RAGAs validation)
- MOD-02: Token Cost Explosion (use Haiku for Guardian, summarize documents)

**Avoids:** Black box predictions, confirmation bias (only Bull agents), hallucinated financial principles, value traps (declining businesses that deserve to be cheap).

**Research flag:** Phase 3.1 (RAG setup) — NEEDS RESEARCH on RAGAs configuration, chunking strategies for financial texts. Phase 3.2 (Bulls/Bears) — SKIP, calculation formulas well-documented.

---

### Phase 4: Orchestration & Execution (Week 11-12)
**Rationale:** Downstream of decision-making (depends on Layer 2-4 outputs). Simpler logic than dialectical core. Portfolio management can use simplified approaches for MVP (equal-weight fallback if Kelly criterion too complex).

**Delivers:**
- Optimizer agent: Kelly criterion position sizing with risk guardrails (max 10% single position, max 30% sector concentration)
- Risk-based HITL triggering (only interrupt for: fraud veto, no margin of safety, >10% position, conviction < 0.5, data quality < 0.7)
- Portfolio state tracking (positions table, aggregate calculations)
- Trade simulation (market orders, limit orders)
- Integration: LangGraph conditional edge routing (Judge → HITL gate or Optimizer, based on risk flags)

**Uses:**
- LangGraph conditional edges for HITL routing
- PostgreSQL for portfolio state
- Kelly criterion math (can simplify to equal-weight if time constrained)

**Addresses:**
- TS-03: Portfolio Tracking
- TS-05: Risk Guardrails
- DIFF-10: Portfolio Optimizer (simplified Kelly)
- TS-12: Paper Trading Mode
- CRIT-08: HITL Fatigue (risk-based triggering)

**Avoids:** HITL triggering on every decision (fatigue), naive equal-weighting when conviction varies, concentration risk (no diversification).

**Research flag:** SKIP — Kelly criterion well-documented, standard portfolio management patterns.

---

### Phase 5: Validation (Week 13-15)
**Rationale:** Requires all agents functional. Validates architecture decisions. Builds credibility for TFM. Cannot deploy untested strategy (regulatory requirement for investment advisors).

**Delivers:**
- vectorbt backtesting integration (point-in-time data access via wrapper from Phase 2)
- Multi-regime testing (2008-2009 crisis, 2010-2015 recovery, 2016-2019 bull, 2020 COVID, 2021-2022 inflation)
- Transaction cost modeling (slippage, commissions)
- Performance metrics dashboard (Sharpe ratio, max drawdown, win rate)
- Walk-forward validation (optional if time permits, can defer to post-MVP)
- Backtest validation checklist (out-of-sample performance within 20% of in-sample, strategy logic makes sense)

**Uses:**
- vectorbt (NumPy-based speed)
- PointInTimeData wrapper from Phase 2
- pandas/numpy for metrics

**Addresses:**
- TS-11: Backtesting Engine
- TS-12: Paper Trading Mode
- DIFF-16: Walk-Forward Validation (optional)
- CRIT-04: Overfitting (multi-regime testing)
- CRIT-01: Look-ahead Bias (validation via point-in-time wrapper)

**Avoids:** Deploying untested strategy, overfitting to single market regime, look-ahead bias invalidating results.

**Research flag:** Phase 5.1 (vectorbt setup) — NEEDS RESEARCH on portfolio-level backtesting API, transaction cost configuration. Phase 5.2 (walk-forward) — SKIP if deferred.

---

### Phase 6: Interface & Polish (Week 16-18)
**Rationale:** Depends on all agents producing outputs. UI easier to iterate than backend. Explainability dashboard makes system usable and compliant. User testing validates HITL UX is meaningful, not tedious.

**Delivers:**
- Streamlit dashboard with components:
  - Explainability viewer (show bull_case, bear_case, judge_rationale, citations, data provenance)
  - HITL approval UI (summary-first, expand for details, pre-filled recommendation, approve/reject buttons)
  - Agent activity visualization (which agents ran, what they produced, state transitions)
  - Performance metrics (portfolio value over time, Sharpe, drawdown)
- EU AI Act compliance report (map features to transparency/oversight/auditability requirements)
- User testing with non-technical users (can they understand agent reasoning? is HITL review meaningful?)
- Documentation (README, architecture diagram, deployment guide)

**Uses:**
- Streamlit (pure Python, WebSocket support for real-time updates)
- Plotly for charts
- PostgreSQL audit_logs table for decision reconstruction

**Addresses:**
- TS-08: Explainability Dashboard
- DIFF-01: Transparent Reasoning Logs UI
- DIFF-04: EU AI Act Compliance Dashboard
- DIFF-14: Live Activity Visualization (static version, defer WebSocket updates)
- CRIT-06: Compliance Theater (user testing validates explainability is meaningful)

**Avoids:** Black box UI (just showing "BUY" without reasoning), HITL as rubber-stamping (UI makes review fast but meaningful), non-technical users unable to understand system.

**Research flag:** SKIP — Streamlit well-documented, standard dashboard patterns.

---

### Phase Ordering Rationale

**Why this sequence:**
1. **State schema first** — changing it mid-project breaks all agents (learned from ARCHITECTURE.md anti-patterns)
2. **Data layer before agents** — prevents garbage in, garbage out (agents depend on clean data)
3. **Dialectical core before execution** — core differentiation must work before optimizing position sizing
4. **Validation before interface** — can't polish a UI for broken agents, need working system to demo
5. **Layer-by-layer agent building** — proves architecture at each step, catches integration issues early

**Dependency flow:**
- Phase 2 depends on Phase 1 (state schema defines data fields)
- Phase 3 depends on Phase 2 (agents need validated data)
- Phase 4 depends on Phase 3 (orchestration needs agent outputs)
- Phase 5 depends on Phase 4 (backtesting needs full decision flow)
- Phase 6 depends on Phase 5 (UI displays validated results)

**Pitfall avoidance:**
- Phase 1 prevents CRIT-02 (deadlocks via acyclic graph), CRIT-05 (non-determinism via temperature=0), CRIT-06 (compliance via state schema)
- Phase 2 prevents CRIT-01 (look-ahead bias via point-in-time wrapper), CRIT-07 (data quality via validation layer)
- Phase 3 prevents CRIT-03 (RAG hallucination via citation enforcement)
- Phase 4 prevents CRIT-08 (HITL fatigue via risk-based triggering)
- Phase 5 prevents CRIT-04 (overfitting via multi-regime testing)
- Phase 6 prevents CRIT-06 (compliance theater via user testing)

**Total timeline:** 18 weeks (~4.5 months) fits June 2026 deadline with buffer.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 3.1 (RAG setup):** RAGAs configuration, chunking strategies for financial texts, citation extraction from PDFs
- **Phase 5.1 (vectorbt integration):** Portfolio-level backtesting API, transaction cost configuration, point-in-time data integration

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Foundation):** LangGraph setup well-documented in official docs
- **Phase 2 (Data Layer):** yfinance/Alpha Vantage/FRED standard integrations
- **Phase 3.2 (Bulls/Bears):** EPV, Z-Score, M-Score calculation formulas well-documented
- **Phase 4 (Orchestration):** Kelly criterion, portfolio management standard patterns
- **Phase 6 (Interface):** Streamlit dashboard standard patterns

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | LangGraph, Google AI, Supabase all have active development, strong docs, free tiers verified |
| Features | HIGH | Table stakes validated via competitive analysis of robo-advisors, differentiators align with Value Investing principles |
| Architecture | HIGH | StateGraph patterns proven in production multi-agent systems, pure function agents testable |
| Pitfalls | HIGH | Look-ahead bias, RAG hallucination, HITL fatigue documented in financial ML literature and LangGraph community |

**Overall confidence:** HIGH

Research based on:
- Official LangGraph documentation (state management, checkpointing, conditional routing)
- Financial ML best practices (quantitative backtesting, point-in-time data access)
- Value Investing canonical texts (Graham Intelligent Investor, Greenwald Value Investing, Dalio Principles)
- EU AI Act regulatory requirements (transparency, human oversight, auditability)
- Multi-agent system architectural patterns (state-centric design, pure function agents)

### Gaps to Address

Research was comprehensive, but the following areas need validation during implementation:

- **LangGraph API stability:** Training data from early 2025, verify 0.2.x API is stable or if 0.3+ introduces breaking changes — CHECK OFFICIAL DOCS during Phase 1 setup
- **Google AI rate limits:** Confirm 1500 req/day sufficient for 10-agent system with complex workflows — MONITOR during Phase 3, have OpenAI backup ready
- **yfinance reliability:** Test fallback strategy under real rate limit conditions — VALIDATE in Phase 2 with stress testing
- **Supabase vector search performance:** Benchmark pgvector with 10k+ document chunks — VALIDATE in Phase 3.1 RAG setup
- **Streamlit scalability:** Determine at what point migration to FastAPI+React becomes necessary — MONITOR during Phase 6, defer migration to post-MVP

**Handling during planning:**
- Include LangGraph version verification in Phase 1 kickoff
- Add API rate limit monitoring to Phase 3 (log requests, alert if approaching limits)
- Include fallback testing in Phase 2 acceptance criteria
- Add pgvector performance benchmarking to Phase 3.1 RAG setup
- Document Streamlit limitations in Phase 6 (inform post-MVP migration planning)

## Sources

### Primary (HIGH confidence)
- LangGraph Official Documentation — StateGraph architecture, checkpointing, interrupt mechanism
- Google AI Documentation — Gemini API, rate limits, function calling, text-embedding-004
- Supabase Documentation — PostgreSQL setup, pgvector extension, free tier limits
- yfinance GitHub Repository — API capabilities, rate limits, known issues
- vectorbt Documentation — Portfolio backtesting, transaction costs, performance metrics
- Graham "The Intelligent Investor" — Margin of safety, Value Investing principles, EPV methodology
- Greenwald "Value Investing: From Graham to Buffett and Beyond" — EPV calculation, moat analysis
- EU AI Act Official Text — Transparency requirements, human oversight, auditability

### Secondary (MEDIUM confidence)
- LangGraph Community Examples — Multi-agent financial systems (GitHub search)
- QuantStack Blog — Financial backtesting best practices, look-ahead bias prevention
- RAGAs Documentation — Faithfulness metric, citation validation
- Streamlit Community Forum — Dashboard patterns, WebSocket limitations

### Tertiary (LOW confidence)
- Altman Z-Score academic papers — Threshold calibration (needs validation with recent data)
- Beneish M-Score research — False positive rates (needs testing on dataset)
- VeTO organizational capability model — Proxy metrics for management quality (complex to implement, simplified for MVP)

---
*Research completed: 2026-02-01*
*Ready for roadmap: yes*
