# Roadmap: AI-Investment Swarm

**Project:** LockIn
**Version:** v1 (MVP for TFM)
**Timeline:** 18 weeks (~4.5 months)
**Target Completion:** June 2026

---

## Executive Summary

6-phase roadmap to build a **Bayesian multi-agent investment system** with dialectical reasoning (Bull ⇄ Bear), risk veto logic, and glass-box transparency for EU AI Act compliance.

**Architecture:** 7 specialized agents orchestrated via LangGraph StateGraph → Analyze user watchlist → Generate portfolio recommendations with full audit trail → User reviews & executes.

**Key Milestones:**
- **Phase 1 (2w):** LangGraph foundation with checkpointing & HITL
- **Phase 2 (2w):** Data pipeline (yfinance + FRED) with validation
- **Phase 3 (6w):** All 7 agents + RAG implementation (longest phase)
- **Phase 4 (2w):** Risk integration (Guardian veto), consensus (Judge Bayesian), portfolio (Optimizer)
- **Phase 5 (3w):** Backtesting (walk-forward) + paper trading setup
- **Phase 6 (3w):** Streamlit dashboard with explainability UI

---

## Phase 1: Foundation (2 weeks) ✓ COMPLETE

**Goal:** Establish LangGraph infrastructure with auditable state management, checkpointing, and HITL mechanism.

**Completed:** 2026-02-21
**Verification:** 13/13 must-haves passed

**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — InvestmentState schema, config loader, 7 mock agents
- [x] 01-02-PLAN.md — StateGraph builder with conditional edges + audit trail logger
- [x] 01-03-PLAN.md — HITL interrupt in judge + PostgreSQL checkpointing + end-to-end tests

**Success Criteria:**
- [x] LangGraph StateGraph compiles and runs end-to-end with mock agents
- [x] InvestmentState schema defined with all required fields
- [x] PostgreSQL checkpointing functional (can pause/resume)
- [x] Audit trail logs every state transition with timestamps + reasoning
- [x] HITL interrupt mechanism tested (pause → human input → resume)

**Requirements Mapped:**
- CORE-01: LangGraph StateGraph Implementation
- CORE-02: Complete Audit Trail
- CORE-03: PostgreSQL Checkpointing
- CORE-04: HITL Interrupt Mechanism

**Technical Deliverables:**
```python
# InvestmentState TypedDict with all agent fields
# StateGraph with 7 agent nodes + conditional edges
# PostgresSaver configured with Supabase
# audit_logs table schema
# Mock agent functions (return dummy data)
# End-to-end test: watchlist → mock agents → output
```

**Dependencies:**
- Supabase account + PostgreSQL instance (free tier)
- LangGraph installed + dependencies

**Risks:**
- LangGraph API changes (mitigation: pin version)
- Checkpointing complexity (mitigation: start simple, iterate)

---

## Phase 2: Data Layer (2 weeks)

**Goal:** Build reliable financial data pipeline with yfinance + FRED, validation, point-in-time wrapper, and historical storage.

**Success Criteria:**
- [ ] yfinance integration retrieves fundamentals (10-K data: balance, income, cash flow)
- [ ] FRED integration retrieves macro data (yield curve, GDP, inflation, PMI)
- [ ] Point-in-time wrapper prevents look-ahead bias in backtesting
- [ ] Data validation detects outliers (>50% change) and missing fields
- [ ] Historical fundamentals stored in PostgreSQL (assets, prices, fundamentals tables)
- [ ] Data lineage: every data point traceable to source + timestamp

**Requirements Mapped:**
- DATA-01: Financial Data Integration (yfinance)
- DATA-02: Macro Data Integration (FRED)
- DATA-03: Point-in-Time Data Wrapper
- DATA-04: Data Validation & Quality Checks
- DATA-05: Historical Fundamentals Storage

**Technical Deliverables:**
```python
# yfinance wrapper: get_fundamentals(ticker, as_of_date)
# FRED wrapper: get_macro_indicators(as_of_date)
# PointInTimeData class with strict date enforcement
# DataValidator class (outlier detection, missing field checks)
# PostgreSQL schema: assets, prices, fundamentals, macro_data
# Data ingestion scripts with error handling
```

**Dependencies:**
- yfinance API stable
- FRED API key (free)
- PostgreSQL tables created

**Risks:**
- yfinance unreliability (mitigation: cache data, manual fallback for critical tests)
- Data quality issues (mitigation: validation layer catches most, HITL for edge cases)

---

## Phase 3: Agents & RAG (6 weeks)

**Goal:** Implement all 7 agents with dialectical Bull-Bear iteration, simplified VeTO, risk logic, and RAG over financial bibliography.

**Success Criteria:**
- [ ] **Macro Oracle** detects regime (expansion/contraction, risk-on/off) from FRED
- [ ] **Value Hunter (Bull)** calculates intrinsic value with EPV (mature), EVA (tech), RIM (financials)
- [ ] **Strategist** performs simplified VeTO (keyword extraction + sentiment from earnings calls/news)
- [ ] **Bear** challenges Bull thesis with red flags + pessimistic valuation distribution
- [ ] **Bull-Bear iteration** completes 1+ dialectical cycle (Bull refines thesis after Bear challenge)
- [ ] **Guardian** calculates Altman Z-Score, Beneish M-Score, VoMC fragility + veto logic
- [ ] **Judge** performs Bayesian synthesis of Bull/Bear distributions → final recommendation
- [ ] **Optimizer** applies Kelly Criterion for position sizing + sector diversification
- [ ] **RAG** retrieves citations from 10-Ks, papers, books with Parent Document Retriever
- [ ] **RAGAs evaluation** measures faithfulness >90% (target >95% for production)

**Requirements Mapped:**
- AGENTS-01: Macro Oracle
- AGENTS-02: Sentiment Agent (now part of Strategist)
- AGENTS-03: Value Hunter (Bull)
- AGENTS-04: Strategist (VeTO simplified)
- AGENTS-05: Bear
- AGENTS-06: Guardian (risk + veto)
- AGENTS-07: Judge (Bayesian consensus)
- AGENTS-08: Optimizer (Kelly + diversification)
- RAG-01: Document Ingestion
- RAG-02: Parent Document Retriever
- RAG-03: Citation System
- RAG-04: RAGAs Evaluation

**Technical Deliverables:**

**Week 1-2: Macro + Value Hunter + Strategist**
```python
# Macro Oracle: FRED integration, regime detection (Dalio framework)
# Value Hunter: EPV/EVA/RIM models with SBC adjustments
# Strategist: NLP for keyword extraction, sentiment scoring
# Magic Formula + Piotroski F-Score quality filters
```

**Week 3-4: Bear + Dialectic + RAG**
```python
# Bear: Adversarial analysis, red flag detection, pessimistic distribution
# Bull-Bear iteration logic with state updates
# RAG setup: Pinecone/ChromaDB, document ingestion pipeline
# Parent Document Retriever (retrieve chunk + surrounding context)
# Citation system (source_id, section, timestamp, checksum)
```

**Week 5-6: Guardian + Judge + Optimizer + RAGAs**
```python
# Guardian: Altman Z-Score, Beneish M-Score, VoMC fragility
# Guardian veto logic (thresholds + multi-risk combinations)
# Judge: Bayesian consensus (combine Bull/Bear distributions)
# Judge HITL triggers (conviction<50%, divergence>30%)
# Optimizer: Kelly Criterion, sector limits, concentration caps
# RAGAs evaluation suite (faithfulness, answer relevancy)
```

**Dependencies:**
- OpenAI/Google AI API for LLM calls (Gemini free tier 1500/day)
- Vector DB setup (Pinecone free tier or ChromaDB local)
- Financial bibliography PDFs/papers for RAG

**Risks:**
- LLM rate limits (mitigation: use Gemini free tier, fallback to OpenAI if needed)
- RAG quality issues (mitigation: RAGAs evaluation catches low faithfulness)
- VoMC complexity (mitigation: simplified operational fragility calculation for v1)

---

## Phase 4: Integration & Risk Management (2 weeks)

**Goal:** Integrate all agents into cohesive pipeline, finalize Guardian veto logic, Judge Bayesian synthesis, and Optimizer portfolio construction.

**Success Criteria:**
- [ ] End-to-end flow functional: Macro → Bull ⇄ Bear → Strategist → Guardian → Judge → Optimizer
- [ ] Guardian veto successfully blocks high-risk assets (tested with known distressed companies)
- [ ] Judge Bayesian synthesis produces reasonable consensus (tested with divergent Bull/Bear inputs)
- [ ] Optimizer respects sector limits (max 35% per sector) and concentration caps (max 12% per asset)
- [ ] Adaptive margin of safety calculates correctly (base 25-30% + risk adjustments)
- [ ] HITL triggers activate correctly for low conviction / high divergence cases

**Requirements Mapped:**
- RISK-01: Adaptive Margin of Safety
- RISK-02: Guardian Veto Logic
- RISK-03: Position Sizing Limits
- RISK-04: HITL Escalation Triggers
- PORTFOLIO-01: Sector Diversification
- PORTFOLIO-02: Kelly Criterion Sizing
- PORTFOLIO-03: Concentration Caps

**Technical Deliverables:**
```python
# Integration tests for full pipeline (10 test cases)
# Guardian veto test suite (Z<1.1, M>-2.22, Debt/EBITDA>3x)
# Judge Bayesian math validation (distribution synthesis)
# Optimizer portfolio generation with constraints
# Adaptive margin calculation function
# HITL trigger logic with test cases
```

**Dependencies:**
- Phase 3 agents complete and tested individually
- Test data: 10-20 tickers covering range of quality/risk profiles

**Risks:**
- Integration bugs between agents (mitigation: extensive integration tests)
- Bayesian math complexity (mitigation: use existing scipy.stats libraries)

---

## Phase 5: Validation (3 weeks)

**Goal:** Validate system logic via backtesting (walk-forward, multi-regime) and setup paper trading simulation for 6-month validation period.

**Success Criteria:**
- [ ] Backtesting engine functional with walk-forward analysis (6-month train, 3-month test windows)
- [ ] Multi-regime backtesting covers bull market (2019), crash (2020), recovery (2021), bear (2022)
- [ ] Case studies completed: Coca-Cola (defensive) vs Alphabet (growth) with full agent reasoning
- [ ] Backtesting metrics calculated: CAGR, max drawdown, Sharpe ratio, win rate, turnover
- [ ] Paper trading simulation setup (tracks portfolio state, P&L, benchmark comparison)
- [ ] Point-in-time enforcement verified (no look-ahead bias in backtests)

**Requirements Mapped:**
- BACKTEST-01: Walk-Forward Backtesting
- BACKTEST-02: Multi-Regime Testing
- BACKTEST-03: Point-in-Time Enforcement
- BACKTEST-04: Performance Metrics
- PAPER-01: Paper Trading Simulation
- PAPER-02: Portfolio State Tracking
- PAPER-03: P&L Calculation
- PAPER-04: Benchmark Comparison

**Technical Deliverables:**
```python
# Backtesting engine with vectorbt or custom implementation
# Walk-forward test runner (rolling windows)
# Multi-regime test suite (2019-2023 data)
# Case study generator (full agent reasoning per asset)
# Paper trading simulator (tracks positions, cash, P&L)
# Performance metrics dashboard (returns, risk, efficiency)
```

**Dependencies:**
- Historical data for 2019-2023 (yfinance)
- Backtesting frameworks (vectorbt or backtrader)

**Risks:**
- Look-ahead bias (mitigation: strict point-in-time enforcement)
- Overfitting (mitigation: walk-forward prevents training on test data)
- Historical data quality (mitigation: validate critical periods manually)

---

## Phase 6: Interface & Compliance (3 weeks)

**Goal:** Build Streamlit dashboard with glass-box transparency, explainability UI, audit trail browser, and HITL approval interface.

**Success Criteria:**
- [ ] Dashboard shows multi-agent consensus visualization (Bull vs Bear distributions)
- [ ] Agent reasoning viewer displays each agent's thesis + evidence + citations
- [ ] Audit trail browser allows filtering by ticker, date, agent, decision
- [ ] HITL approval interface allows user to review flagged decisions (approve/reject/modify)
- [ ] Data viewer shows financial data with links to SEC filings (data lineage)
- [ ] EU AI Act compliance: disclaimers, transparency documentation, risk management log
- [ ] Portfolio view shows recommended allocation with sizing rationale

**Requirements Mapped:**
- UI-01: Dashboard Multi-Agent Consensus
- UI-02: Agent Reasoning Viewer
- UI-03: Audit Trail Browser
- UI-04: HITL Approval Interface
- UI-05: Data Viewer with SEC Links
- COMPLIANCE-01: EU AI Act Documentation
- COMPLIANCE-02: Disclaimers (B2B decision support, not financial advice)
- COMPLIANCE-03: Glass Box Transparency

**Technical Deliverables:**
```python
# Streamlit app structure:
#   - Home: Portfolio overview + allocation
#   - Consensus: Bull vs Bear synthesis per asset
#   - Agent Details: Reasoning + evidence + citations per agent
#   - Audit Trail: Searchable log of all decisions
#   - HITL Queue: Flagged decisions awaiting approval
#   - Data Explorer: Financial data with SEC filing links
#   - Compliance: Disclaimers, risk disclosures, methodology
# Plotly visualizations (distributions, sector exposure, time series)
# SEC filing deep-link generator
```

**Dependencies:**
- Streamlit framework
- Plotly for visualizations
- Audit logs from Phase 1 available in DB

**Risks:**
- UI/UX complexity (mitigation: MVP UI first, polish later)
- Streamlit performance with large data (mitigation: pagination, caching)

---

## Milestone Summary

| Phase | Duration | Completion | Key Deliverable |
|-------|----------|------------|-----------------|
| **1 - Foundation** | 2 weeks | Week 2 | LangGraph pipeline with checkpointing + HITL |
| **2 - Data Layer** | 2 weeks | Week 4 | Financial data pipeline with validation |
| **3 - Agents & RAG** | 6 weeks | Week 10 | 7 agents + dialectic + RAG + RAGAs |
| **4 - Integration** | 2 weeks | Week 12 | End-to-end integration + risk logic |
| **5 - Validation** | 3 weeks | Week 15 | Backtesting + paper trading setup |
| **6 - Interface** | 3 weeks | Week 18 | Dashboard + compliance documentation |

**Total Timeline:** 18 weeks (~4.5 months)
**Buffer:** 2-3 weeks before June 2026 deadline for polish & TFM writeup

---

## Dependencies & Critical Path

```
Phase 1 (Foundation) → BLOCKS → All other phases
Phase 2 (Data Layer) → BLOCKS → Phase 3, 4, 5
Phase 3 (Agents) → BLOCKS → Phase 4, 5, 6
Phase 4 (Integration) → BLOCKS → Phase 5
Phase 5 (Validation) → Can run in parallel with Phase 6 (different focus)
```

**Critical Path:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
**Parallelizable:** Phase 5 (Validation) and Phase 6 (Interface) last 1 week can overlap

---

## Risk Management

### High-Risk Items

1. **Phase 3 duration (6 weeks):** Longest phase, most complexity
   - **Mitigation:** Break into sub-phases, prioritize Value Hunter + Guardian first (minimum viable agents)

2. **LLM rate limits (Google AI 1500 req/day)**
   - **Mitigation:** Monitor usage, use caching aggressively, fallback to OpenAI if needed

3. **RAG quality (faithfulness <90%)**
   - **Mitigation:** RAGAs evaluation in Phase 3, iterate on prompts + retrieval strategy

4. **Backtesting look-ahead bias**
   - **Mitigation:** Strict point-in-time enforcement from Phase 2, validation in Phase 5

### Medium-Risk Items

1. **yfinance reliability**
   - **Mitigation:** Cache all data, have manual data fallback for critical test cases

2. **VoMC complexity (operational fragility calculation)**
   - **Mitigation:** Simplified calculation in v1 (stress test revenue -10% → measure EBIT impact)

3. **Bayesian synthesis implementation**
   - **Mitigation:** Use scipy.stats for distribution operations, validate with toy examples first

---

## Deferred to v2

**Features explicitly out of scope for v1:**
- Chartist (technical timing analysis)
- Historian (historical valuation context)
- Full VeTO NLP model (clustering, absorption capacity)
- Active stock screening (v1 analyzes user watchlist only)
- Multi-source data fallback (Alpha Vantage, FMP)
- Trader agent (execution simulation - user executes in v1)
- Advanced portfolio rebalancing strategies
- Real-money execution
- Mobile app

**v2 Roadmap (Post-TFM, if converting to SaaS):**
- Add deferred agents (Chartist, Historian)
- Full VeTO NLP model with organizational analysis
- Active screening across SP500
- Professional dashboard (React/Next.js)
- Multi-user support + authentication
- Subscription billing (base + compute credits)
- Real-time data streams
- Advanced risk models (VaR, CVaR, stress testing)

---

## Success Metrics (v1 MVP)

**Technical Validation:**
- [ ] All 38 v1 requirements met
- [ ] Backtesting CAGR > SP500 benchmark (not guaranteed, but target)
- [ ] Max drawdown < SP500 benchmark
- [ ] RAGAs faithfulness score >90%
- [ ] Zero critical bugs in paper trading (6-month period)

**Academic Validation (TFM):**
- [ ] System demonstrates Bayesian reasoning with probabilistic distributions
- [ ] Dialectical process (Bull ⇄ Bear) produces refined theses
- [ ] EU AI Act compliance documented (glass box, auditability)
- [ ] Bibliography citations functional (RAG with source attribution)
- [ ] Case studies show qualitative improvement over simple valuation models

**User Experience:**
- [ ] Dashboard clearly explains agent reasoning (non-expert can understand)
- [ ] Audit trail allows full traceability (regulator could verify decisions)
- [ ] HITL approval workflow intuitive (user can intervene without breaking system)

---

## Phase Planning Protocol

**Before each phase:**
1. Read this ROADMAP.md + REQUIREMENTS.md
2. Review which requirements map to this phase
3. Create phase PLAN.md with:
   - Detailed task breakdown (sub-tasks, dependencies)
   - Implementation approach
   - Testing strategy
   - Success criteria verification plan
4. Get user approval on PLAN.md
5. Execute phase
6. Verify success criteria before moving to next phase

**Phase completion checklist:**
- [ ] All requirements for phase met
- [ ] Tests passing
- [ ] Success criteria verified
- [ ] Documentation updated
- [ ] Code committed with descriptive message
- [ ] Phase SUMMARY.md created (what was done, decisions made, blockers resolved)

---

*Roadmap created: 2026-02-08*
*Based on: Agent architecture finalization, REQUIREMENTS.md (38 v1 requirements), research findings*
