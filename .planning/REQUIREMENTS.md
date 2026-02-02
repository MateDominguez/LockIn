# Requirements: AI-Investment Swarm

**Project:** LockIn
**Version:** v1 (MVP for TFM - June 2026)
**Last Updated:** 2026-02-01

## Overview

Sistema multi-agente de inversión basado en Value Investing con arquitectura dialéctica (Bulls vs Bears) y cumplimiento EU AI Act. v1 incluye 8 agentes, backtesting completo, paper trading por 6 meses, y dashboard de explainabilidad.

---

## v1 Requirements

### CORE: Infrastructure & Orchestration

#### CORE-01: LangGraph StateGraph Implementation
**User Story:** Como sistema, necesito orquestar 8 agentes en 5 capas con estado compartido auditable
**Acceptance Criteria:**
- StateGraph definido con InvestmentState TypedDict
- 8 agentes implementados como pure functions (state, config) → updates
- Conditional edges para routing dialéctico
- Graph compila sin errores, visualizable en Mermaid

**Mapped to Phase:** 1 (Foundation)
**Complexity:** HIGH
**Priority:** CRITICAL

---

#### CORE-02: Complete Audit Trail
**User Story:** Como regulador/usuario, necesito ver el registro completo de todas las decisiones de agentes para cumplir EU AI Act
**Acceptance Criteria:**
- Cada transición de estado logged en PostgreSQL audit_logs table
- Logs incluyen: timestamp, agent_name, input_state, output_updates, reasoning
- Queryable por ticker, fecha, agent, decision
- Retención mínima: 6 meses (paper trading period)

**Mapped to Phase:** 1 (Foundation)
**Complexity:** MEDIUM
**Priority:** CRITICAL

---

#### CORE-03: PostgreSQL Checkpointing
**User Story:** Como sistema HITL, necesito persistir estado para poder resumir después de intervención humana
**Acceptance Criteria:**
- LangGraph compilado con PostgresSaver checkpointer
- Estado completo serializado en cada nodo
- Resume funciona después de interrupción (state restaurado correctamente)
- Checkpoint storage en Supabase PostgreSQL

**Mapped to Phase:** 1 (Foundation)
**Complexity:** MEDIUM
**Priority:** CRITICAL

---

#### CORE-04: HITL Interrupt Mechanism
**User Story:** Como usuario, necesito que el sistema pause antes de decisiones críticas para que yo apruebe/rechace
**Acceptance Criteria:**
- LangGraph interrupt_before configurado en nodos HITL
- Triggers dinámicos basados en: fraud_veto, conviction < threshold, high position size
- Estado persistido durante pausa
- UI permite aprobar/rechazar con comentarios
- Resume execution después de input humano

**Mapped to Phase:** 1 (Foundation), 4 (HITL integration), 6 (UI)
**Complexity:** HIGH
**Priority:** CRITICAL

---

### AGENTS: Multi-Agent Implementation (8 agents)

#### AGENTS-01: Layer 1 - Macro Oracle
**User Story:** Como sistema, necesito detectar el régimen económico (growth/inflation) para ajustar exposición
**Acceptance Criteria:**
- Integración con FRED API (yield curve, inflation expectations)
- Calcula macro_multiplier (0.2-1.0) basado en régimen
- Output: macro_context dict con regime, multiplier, rationale
- Cita fuentes (Dalio "All Weather" via RAG si disponible)

**Mapped to Phase:** 3 (Layer 1 Agents)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### AGENTS-02: Layer 1 - Sentiment Agent
**User Story:** Como sistema, necesito detectar narrative risk mediante análisis de earnings calls, news, forums
**Acceptance Criteria:**
- Web scraping o API de earnings call transcripts
- NLP sentiment analysis (positive/negative ratio)
- Semantic volatility calculation (cambio en tone vs trimestre anterior)
- Output: sentiment_scores dict con narrative_risk, volatility, source_reliability
- Alert si negative sentiment aumenta > 25%

**Mapped to Phase:** 3 (Layer 1 Agents)
**Complexity:** HIGH
**Priority:** HIGH

---

#### AGENTS-03: Layer 2 - Value Hunter (Bull)
**User Story:** Como inversor value, necesito calcular intrinsic value usando EPV (Earnings Power Value) de Greenwald
**Acceptance Criteria:**
- Implementa EPV formula: normalized_earnings / WACC
- Calcula margin of safety: (EPV - price) / EPV
- Moat rating (1-5) basado en ROIC vs WACC persistencia
- Output: intrinsic_value, margin_of_safety, moat_rating
- Cita Graham/Greenwald via RAG cuando explica metodología

**Mapped to Phase:** 3 (Layer 2 Bulls)
**Complexity:** HIGH
**Priority:** CRITICAL

---

#### AGENTS-04: Layer 3 - The Bear (Devil's Advocate)
**User Story:** Como sistema, necesito challengear las tesis optimistas del Value Hunter con análisis de sensibilidad
**Acceptance Criteria:**
- Implementa Monte Carlo simulation (scipy.stats) con 1000+ escenarios
- Prueba sensibilidad de intrinsic_value a cambios en: revenue growth (-3%), margins (-200 bps), WACC (+100 bps)
- Output: objections list, sensitivity_penalty (0.0-1.0), scenario_distribution
- Si intrinsic_value cae > 40% en escenario pesimista → flag high fragility

**Mapped to Phase:** 3 (Layer 3 Bears)
**Complexity:** HIGH
**Priority:** CRITICAL

---

#### AGENTS-05: Layer 3 - The Guardian (Risk Officer)
**User Story:** Como sistema, necesito detectar fraude y riesgo de quiebra antes de recomendar un activo
**Acceptance Criteria:**
- Implementa Altman Z-Score (bankruptcy risk): Z < 1.8 → veto
- Implementa Beneish M-Score (earnings manipulation): M > -1.78 → veto
- Output: fraud_veto bool, z_score, m_score, veto_reason
- Si fraud_veto = True → trigger HITL automáticamente

**Mapped to Phase:** 3 (Layer 3 Bears)
**Complexity:** MEDIUM
**Priority:** CRITICAL

---

#### AGENTS-06: Layer 4 - The Judge (Consensus)
**User Story:** Como sistema, necesito arbitrar el debate Bull vs Bear y decidir BUY/PASS/HITL
**Acceptance Criteria:**
- Input: intrinsic_value, margin_of_safety, objections, fraud_veto
- Lógica simplificada v1 (defer fuzzy logic a v2):
  - Si fraud_veto → HITL
  - Si margin_of_safety < 0 → PASS
  - Si margin_of_safety > 0.25 AND sensitivity_penalty < 0.5 → BUY (conviction based on strength)
  - Else → HITL (low conviction)
- Output: consensus_decision, conviction (0.0-1.0), judge_rationale

**Mapped to Phase:** 4 (Orchestration)
**Complexity:** MEDIUM (v1 simplified, HIGH for v2 fuzzy logic)
**Priority:** CRITICAL

---

#### AGENTS-07: Layer 4 - The Optimizer (Position Sizing)
**User Story:** Como sistema, necesito calcular cuánto asignar a cada posición considerando riesgo y correlación
**Acceptance Criteria:**
- Input: conviction, macro_multiplier, existing portfolio
- Lógica simplificada v1 (defer Kelly criterion a v2):
  - Base size = conviction * 0.05 (5% max per position)
  - Adjust by macro_multiplier
  - Apply risk limits (RISK-01, RISK-02, RISK-03)
- Output: position_size (% of portfolio), rebalance_required bool

**Mapped to Phase:** 4 (Orchestration)
**Complexity:** MEDIUM (v1 simplified, HIGH for v2 Kelly)
**Priority:** HIGH

---

#### AGENTS-08: Layer 5 - The Trader (Execution)
**User Story:** Como sistema, necesito simular órdenes de compra/venta en paper trading
**Acceptance Criteria:**
- Simulated market orders (fill at current price)
- Simulated limit orders (fill if price reaches limit)
- Transaction cost modeling (comisión 0.1%, slippage 0.05%)
- Output: executed_trades list con timestamp, ticker, shares, fill_price, fees
- Track P&L acumulado

**Mapped to Phase:** 5 (Execution)
**Complexity:** MEDIUM
**Priority:** HIGH

---

### DATA: Financial Data Integration

#### DATA-01: Primary Data Sources
**User Story:** Como sistema, necesito datos financieros actualizados de fuentes confiables
**Acceptance Criteria:**
- yfinance integration (prices, fundamentals, historical data)
- FRED API integration (macro indicators: yield curve, inflation, GDP)
- Alpha Vantage deferred to v2 (fallback not needed for MVP)

**Mapped to Phase:** 2 (Data Layer)
**Complexity:** MEDIUM
**Priority:** CRITICAL

---

#### DATA-02: Data Quality Validation
**User Story:** Como sistema, necesito detectar datos stale, missing, o absurdos antes de usarlos
**Acceptance Criteria:**
- Staleness check: last_updated < 30 days → warning, trigger HITL if critical
- Completeness check: required fields (earnings, revenue, book_value, debt) present
- Sanity checks: earnings < 0 pero PE > 0 → inconsistency error
- Output: quality_score (0.0-1.0) per data fetch

**Mapped to Phase:** 2 (Data Layer)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### DATA-03: Cache with TTL
**User Story:** Como sistema, necesito cachear datos para evitar rate limits y reducir latencia
**Acceptance Criteria:**
- Redis o in-memory cache (decide en Phase 2)
- TTL: fundamentals 1 day, prices 1 hour, macro 1 week
- Cache hit logging (observability)

**Mapped to Phase:** 2 (Data Layer)
**Complexity:** LOW
**Priority:** MEDIUM

---

#### DATA-04: Point-in-Time Data Access Wrapper
**User Story:** Como sistema de backtesting, necesito garantizar que solo uso datos disponibles "en ese momento" para evitar look-ahead bias
**Acceptance Criteria:**
- PointInTimeData class wraps historical DataFrames
- get_data_as_of(date) returns only data known on or before date
- Unit tests: verify cannot access future data
- Backtest validation: manual spot-check of 5 random dates

**Mapped to Phase:** 2 (Data Layer)
**Complexity:** MEDIUM
**Priority:** CRITICAL (invalidates backtesting if missing)

---

#### DATA-05: Historical Fundamentals Storage
**User Story:** Como sistema, necesito almacenar financial statements históricos para análisis de tendencias y evitar re-downloads
**Acceptance Criteria:**
- PostgreSQL schema: companies, financial_statements (quarterly/annual), time-series indexed
- Store 5-10 years of data per company analyzed
- First analysis: download + store. Future: read from DB
- ~200-500 KB per company (fits in Supabase 500MB free tier)

**Mapped to Phase:** 2 (Data Layer)
**Complexity:** MEDIUM
**Priority:** HIGH

---

### RAG: Knowledge Base

#### RAG-01: Document Ingestion Pipeline
**User Story:** Como sistema, necesito cargar bibliografía financiera (Graham, Dalio, Greenwald) para que agentes citen metodologías
**Acceptance Criteria:**
- PyPDFLoader + UnstructuredMarkdownLoader (LangChain)
- Chunk with RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
- Store chunks in Supabase pgvector
- Metadata: source_title, page_number, author

**Mapped to Phase:** 3 (RAG Setup)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### RAG-02: Embedding & Vector Search
**User Story:** Como agente, necesito buscar pasajes relevantes en la bibliografía cuando justifico una decisión
**Acceptance Criteria:**
- Google text-embedding-004 (free)
- Supabase SupabaseVectorStore integration
- Similarity search returns top-k chunks (k=5)
- Includes metadata (source, page) for citation

**Mapped to Phase:** 3 (RAG Setup)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### RAG-03: Citation Enforcement
**User Story:** Como usuario, necesito que agentes citen fuentes reales, no inventen "hechos" de su training data
**Acceptance Criteria:**
- Agent prompts explicitly forbid using training data for financial facts
- All financial principles must include citation: (Author, Book, Page, Quote)
- Validation: response includes regex pattern `\(.*?, p\. \d+\)`
- If no citation found → error, agent retries

**Mapped to Phase:** 3 (RAG Setup)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### RAG-04: RAGAs Evaluation
**User Story:** Como sistema, necesito validar que RAG no está hallucinating (inventando info no presente en chunks)
**Acceptance Criteria:**
- RAGAs library integration (faithfulness, answer_relevancy metrics)
- Faithfulness score > 0.8 required (80%+ of response grounded in context)
- Automated testing: run evaluation on 20 sample queries before deployment
- Alert if faithfulness drops below threshold

**Mapped to Phase:** 3 (RAG Setup)
**Complexity:** MEDIUM
**Priority:** HIGH

---

### BACKTEST: Validation

#### BACKTEST-01: vectorbt Integration
**User Story:** Como validador, necesito simular la estrategia en datos históricos para verificar que funciona
**Acceptance Criteria:**
- vectorbt.Portfolio backtest engine
- Feed historical decisions from LangGraph
- Model transaction costs: 0.1% commission, 0.05% slippage
- Output: portfolio value over time, trades executed

**Mapped to Phase:** 5 (Validation)
**Complexity:** HIGH
**Priority:** CRITICAL

---

#### BACKTEST-02: Performance Metrics
**User Story:** Como validador, necesito métricas estándar para evaluar la estrategia
**Acceptance Criteria:**
- Sharpe Ratio (risk-adjusted return)
- Maximum Drawdown (worst peak-to-trough decline)
- Win Rate (% of profitable trades)
- Total Return, Annualized Return
- Comparison vs benchmark (S&P 500 buy-and-hold)

**Mapped to Phase:** 5 (Validation)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### BACKTEST-03: Multi-Regime Testing
**User Story:** Como validador, necesito probar que la estrategia no está overfitted a un solo régimen de mercado
**Acceptance Criteria:**
- Test periods include:
  - 2008-2009 (Financial Crisis - bear market)
  - 2010-2015 (Recovery - slow growth)
  - 2016-2019 (Bull Market - low rates)
  - 2020 (COVID - extreme volatility)
  - 2021-2022 (Inflation - rising rates)
- Strategy must have Sharpe > 0.5 in ALL periods (minimum viability)
- Report performance per regime

**Mapped to Phase:** 5 (Validation)
**Complexity:** HIGH
**Priority:** HIGH

---

#### BACKTEST-04: Walk-Forward Validation
**User Story:** Como validador, necesito simular cómo la estrategia hubiera funcionado "out-of-sample" para evitar overfitting
**Acceptance Criteria:**
- Rolling windows: train on 3 years, test on 1 year
- Example: train 2015-2017 → test 2018, train 2016-2018 → test 2019, etc.
- Average out-of-sample performance within 20% of in-sample (otherwise overfitted)
- Document methodology in TFM

**Mapped to Phase:** 5 (Validation)
**Complexity:** HIGH
**Priority:** HIGH

---

### PAPER: Paper Trading

#### PAPER-01: Simulated Order Execution
**User Story:** Como trader simulado, necesito ejecutar órdenes con pricing realista
**Acceptance Criteria:**
- Market orders: fill at current bid/ask (simulate slippage)
- Limit orders: fill only if price reaches limit within session
- Order types: BUY, SELL (long-only, no shorting for v1)
- Execution log: timestamp, type, limit_price, fill_price, shares

**Mapped to Phase:** 5 (Execution)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### PAPER-02: P&L Tracking
**User Story:** Como usuario, necesito ver cuánto dinero virtual gané/perdí en paper trading
**Acceptance Criteria:**
- Track cash balance, position values, total portfolio value
- Calculate realized P&L (on sells) and unrealized P&L (mark-to-market)
- Daily P&L snapshots for charting
- Display in dashboard: today's P&L, cumulative P&L, % return

**Mapped to Phase:** 5 (Execution)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### PAPER-03: Portfolio State Management
**User Story:** Como sistema, necesito mantener el estado actual del portfolio (holdings, cash)
**Acceptance Criteria:**
- PostgreSQL schema: portfolios, positions (ticker, shares, avg_cost, current_value)
- Update on each trade execution
- Portfolio summary: total value, cash %, equity %, sector allocation

**Mapped to Phase:** 5 (Execution)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### PAPER-04: Benchmark Comparison
**User Story:** Como usuario, necesito saber si el sistema está beating the market o no
**Acceptance Criteria:**
- Fetch S&P 500 (SPY) prices for same period
- Calculate buy-and-hold benchmark return
- Display: AI strategy return vs benchmark return, alpha (excess return)
- Chart: portfolio value vs benchmark over time

**Mapped to Phase:** 5 (Execution)
**Complexity:** MEDIUM
**Priority:** HIGH

---

### RISK: Risk Management

#### RISK-01: Position Size Limits
**User Story:** Como gestor de riesgo, necesito limitar la exposición máxima a un solo activo
**Acceptance Criteria:**
- Configurable limit (default: 10% of portfolio per position)
- Optimizer respects limit (caps position_size)
- Alert if limit approached
- Override requires manual approval (HITL)

**Mapped to Phase:** 4 (Orchestration)
**Complexity:** LOW
**Priority:** CRITICAL

---

#### RISK-02: Sector Concentration Limits
**User Story:** Como gestor de riesgo, necesito evitar concentración excesiva en un sector (ej: todo tech)
**Acceptance Criteria:**
- Sector classification per ticker (from yfinance or manual mapping)
- Configurable limit (default: 30% of portfolio per sector)
- Optimizer checks sector exposure before sizing position
- Alert if limit would be breached

**Mapped to Phase:** 4 (Orchestration)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### RISK-03: Portfolio Volatility Cap
**User Story:** Como gestor de riesgo, necesito limitar la volatilidad total del portfolio
**Acceptance Criteria:**
- Calculate portfolio volatility using covariance matrix (60-day rolling)
- Configurable limit (default: annualized volatility < 20%)
- Optimizer reduces position sizes if portfolio vol exceeds limit
- Alert in dashboard if vol is high

**Mapped to Phase:** 4 (Orchestration)
**Complexity:** HIGH
**Priority:** MEDIUM

---

#### RISK-04: Guardian Veto Enforcement
**User Story:** Como usuario, necesito que el sistema no me recomiende empresas fraudulentas o en quiebra
**Acceptance Criteria:**
- If Guardian sets fraud_veto = True → decision = PASS (no BUY)
- No override allowed (hard veto)
- Log veto reason in audit trail
- Alert user with explanation (Z-Score, M-Score values)

**Mapped to Phase:** 3 (Layer 3 Bears)
**Complexity:** LOW
**Priority:** CRITICAL

---

### UI: Interface & Explainability

#### UI-01: Dashboard Principal
**User Story:** Como usuario, necesito un overview del sistema: portfolio, recomendaciones activas, performance
**Acceptance Criteria:**
- Streamlit dashboard
- Sections: Portfolio Summary, Recent Recommendations, P&L Chart, Pending HITL Reviews
- Responsive (works on desktop + tablet)

**Mapped to Phase:** 6 (Interface)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### UI-02: Agent Reasoning Viewer
**User Story:** Como usuario, necesito ver el debate completo entre agentes para entender la recomendación
**Acceptance Criteria:**
- Display agent outputs structured:
  - **Macro Oracle:** "Regime: Growth, Multiplier: 0.9"
  - **Value Hunter:** "EPV: $150, Margin: 25%, Moat: 4/5"
  - **Bear:** "Objection: High valuation at 82nd percentile"
  - **Guardian:** "Z-Score: 3.2 (safe), M-Score: -2.1 (safe)"
  - **Judge:** "BUY with conviction 0.75 — Bull case stronger despite valuation concern"
- Expandable sections (summary → full reasoning)
- Link to citations (Graham quote from RAG)

**Mapped to Phase:** 6 (Interface)
**Complexity:** HIGH
**Priority:** CRITICAL (core value prop: transparency)

---

#### UI-03: HITL Approval Interface
**User Story:** Como usuario, necesito revisar y aprobar/rechazar decisiones cuando el sistema me lo pide
**Acceptance Criteria:**
- Modal o dedicated page cuando HITL triggered
- Show: recommendation, ticker, agent debate summary, reason for HITL
- Actions: Approve, Reject, Modify (adjust position size)
- Comment field (user can explain decision)
- Resume execution después de approval

**Mapped to Phase:** 6 (Interface)
**Complexity:** MEDIUM
**Priority:** CRITICAL

---

#### UI-04: Live Agent Activity Visualization
**User Story:** Como usuario, quiero ver qué agentes están pensando en tiempo real
**Acceptance Criteria:**
- Real-time updates via WebSocket (LangGraph streaming)
- Visual state machine: nodes light up when active
- Status indicators: idle, working, completed, blocked (HITL)

**Mapped to Phase:** v2 (optional for v1)
**Complexity:** MEDIUM
**Priority:** LOW (nice-to-have)

---

#### UI-05: Audit Trail Browser
**User Story:** Como usuario, necesito buscar decisiones pasadas y ver el estado completo del análisis
**Acceptance Criteria:**
- Search by: ticker, date range, agent, decision (BUY/PASS)
- Display: full InvestmentState at time of decision
- Download as JSON or PDF for auditing

**Mapped to Phase:** 6 (Interface)
**Complexity:** MEDIUM
**Priority:** HIGH

---

#### UI-06: Data Source Viewer
**User Story:** Como usuario, necesito ver los datos raw que los agentes usaron para verificar calidad
**Acceptance Criteria:**
- Click on any metric (P/E ratio, earnings, etc.) → modal shows raw API response
- Display: source (yfinance), timestamp, full JSON payload
- Helps debug data quality issues

**Mapped to Phase:** 6 (Interface)
**Complexity:** MEDIUM
**Priority:** MEDIUM

---

## v2 Requirements (Post-TFM)

### Deferred to v2

**Agents:**
- AGENTS-09: Strategist (VeTO/VoMC) — organizational capability analysis (very complex)
- AGENTS-10: Historian — historical valuation percentiles (nice-to-have)

**Features:**
- FEAT-01: Multi-source data fallback (Alpha Vantage backup)
- FEAT-02: Kelly Criterion position sizing (replace simplified optimizer)
- FEAT-03: Fuzzy Logic Judge (replace simplified voting)
- FEAT-04: Live Agent Activity Visualization (UI-04)
- FEAT-05: Multi-language support (Spanish UI)

**Optimizations:**
- OPT-01: Async agent execution (performance)
- OPT-02: Distributed graph execution (scale)
- OPT-03: Streaming state updates (UX)

---

## Out of Scope

**Never Build:**
- Guaranteed returns marketing (illegal)
- Black box predictions (contradicts transparency)
- Set-and-forget auto-trading (too risky)
- Social/viral features (gamification)
- High-frequency trading (incompatible with Value Investing)
- Cryptocurrency trading (no fundamentals)
- Margin/leverage trading (against Graham principles)
- Penny stocks / microcaps (unreliable data)
- Options/derivatives (too complex for v1)
- Mobile native app (webapp is sufficient)

---

## Requirements Traceability

| Phase | Requirements Covered | Total Count |
|-------|---------------------|-------------|
| **Phase 1: Foundation** | CORE-01, CORE-02, CORE-03, CORE-04 | 4 |
| **Phase 2: Data Layer** | DATA-01, DATA-02, DATA-03, DATA-04, DATA-05 | 5 |
| **Phase 3: Agents & RAG** | AGENTS-01 through AGENTS-05, RAG-01 through RAG-04 | 9 |
| **Phase 4: Orchestration** | AGENTS-06, AGENTS-07, RISK-01, RISK-02, RISK-03 | 5 |
| **Phase 5: Validation & Execution** | AGENTS-08, BACKTEST-01 through BACKTEST-04, PAPER-01 through PAPER-04, RISK-04 | 10 |
| **Phase 6: Interface** | UI-01, UI-02, UI-03, UI-05, UI-06 | 5 |

**Total v1 Requirements:** 38

---

## Success Criteria

**MVP is successful if:**
- [ ] All 8 agents implemented and functional
- [ ] Backtesting shows Sharpe > 0.5 in all 5 market regimes (multi-regime test passes)
- [ ] Paper trading runs for 6 months without critical failures
- [ ] HITL triggers < 20% of decisions (not fatiguing users)
- [ ] RAGAs faithfulness score > 0.8 (low hallucination risk)
- [ ] Dashboard allows non-technical user to understand agent reasoning (user testing validates)
- [ ] EU AI Act compliance: audit trail complete, explanations human-readable
- [ ] TFM submitted by June 2026

---

*Last updated: 2026-02-01 after user confirmation of all feature scopes*
