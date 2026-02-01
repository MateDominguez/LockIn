# Pitfalls Research: Multi-Agent Financial Investment Systems

**Domain:** Multi-agent investment systems with LangGraph, Value Investing, EU AI Act compliance
**Research Date:** 2026-02-01
**Confidence Level:** HIGH

## Executive Summary

19 critical pitfalls identified across multi-agent financial systems, categorized by severity:
- **8 Critical**: Catastrophic failures (look-ahead bias, deadlocks, hallucinations, compliance theater)
- **5 Moderate**: Degraded performance (state explosion, token costs, version hell)
- **3 Minor**: Annoyances (poor errors, no local dev)
- **3 LangGraph-Specific**: Framework misuse patterns

Each pitfall includes:
- **Detection**: Warning signs to catch early
- **Prevention**: Actionable mitigation strategies
- **Phase Mapping**: When to address in roadmap

---

## CRITICAL PITFALLS

### CRIT-01: Look-Ahead Bias in Backtesting
**Severity:** CRITICAL — Invalidates all validation

**What It Is:**
Using information from the future when simulating historical decisions. For example:
- Using end-of-day close price to make "morning" buy decision
- Calculating technical indicators with future data (e.g., 20-day SMA on day 10)
- Survivorship bias (only testing stocks still listed, ignoring delisted bankruptcies)

**Why It Happens:**
- pandas makes it trivial to access any row in a DataFrame (no temporal constraints)
- Financial APIs often return "point-in-time" data incorrectly
- Split/dividend adjustments applied retroactively

**Consequences:**
- Backtest shows 30% annual returns, live trading loses money
- Users trust system, risk real capital, blame you when it fails
- Destroys credibility of entire TFM

**Detection:**
```python
# Red flag: Accessing future data
def backtest_strategy(historical_data):
    for date in historical_data.index:
        # ❌ BAD: Uses close price not known until end of day
        decision_price = historical_data.loc[date, "Close"]

        # ❌ BAD: SMA uses future 19 days
        sma = historical_data.loc[date:date+20, "Close"].mean()

        make_trade_decision(decision_price, sma)
```

**Prevention:**
```python
# ✅ GOOD: Point-in-time data access
class PointInTimeData:
    def __init__(self, historical_data):
        self.data = historical_data

    def get_data_as_of(self, date):
        """Return only data available on or before date"""
        return self.data.loc[:date]

def backtest_strategy(historical_data):
    pit_data = PointInTimeData(historical_data)

    for date in historical_data.index:
        # Only use data known as of this date
        known_data = pit_data.get_data_as_of(date)

        # SMA uses trailing 20 days (not future)
        sma = known_data.tail(20)["Close"].mean()

        make_trade_decision(sma)
```

**Additional Safeguards:**
- Use `as_of_date` parameter in data APIs
- Lag all features by 1 day (assume data available next day)
- Manually check: "Could I have known this on 2020-03-15?"
- Include delisted stocks in backtest universe (survivorship bias)

**Phase to Address:** Phase 2 (Data Layer) — architectural decision

**Validation Checklist:**
- [ ] All data access goes through point-in-time wrapper
- [ ] Backtesting notebook includes manual spot-check of 5 random dates
- [ ] Survivorship bias avoided (universe includes delisted stocks)
- [ ] Technical indicators use trailing windows only

---

### CRIT-02: Agent Coordination Deadlocks
**Severity:** CRITICAL — Infinite loops, system hangs

**What It Is:**
Circular dependencies in LangGraph causing agents to wait on each other forever.

**Example:**
```python
# ❌ BAD: Judge waits for Bear, Bear waits for Judge
workflow.add_conditional_edges(
    "judge",
    lambda state: "bear" if state["conviction"] < 0.8 else "optimizer",
    {"bear": "bear", "optimizer": "optimizer"}
)

workflow.add_conditional_edges(
    "bear",
    lambda state: "judge" if len(state["objections"]) > 5 else "judge",
    {"judge": "judge"}
)
# Result: judge → bear → judge → bear → ...
```

**Why It Happens:**
- Complex conditional routing without cycle detection
- Agents "debating" back and forth without termination condition
- Unclear "who has final say"

**Consequences:**
- System hangs, user waits forever
- Graph compilation fails (LangGraph may catch simple cycles)
- Timeout kills entire analysis

**Detection:**
- Graph visualization shows cycle (use `workflow.get_graph().draw_mermaid()`)
- Unit test timeout after 10 iterations
- LangGraph compilation error (if cycle is obvious)

**Prevention:**
```python
# ✅ GOOD: Acyclic graph, clear termination
workflow.add_edge("value_hunter", "bear")  # Bull → Bear (one-way)
workflow.add_edge("bear", "judge")         # Bear → Judge (one-way)

workflow.add_conditional_edges(
    "judge",
    lambda state: "hitl_gate" if state["conviction"] < 0.6 else "optimizer",
    {"hitl_gate": "hitl_gate", "optimizer": "optimizer"}
)
# No cycles possible
```

**Architectural Rule:**
- **Layers flow forward only** (Layer 2 → Layer 3 → Layer 4, never backward)
- **Judge has final say** (no re-routing back to Bulls/Bears)
- **Max debate rounds = 1** (Bull makes case, Bear challenges, Judge decides — done)

**Phase to Address:** Phase 1 (Foundation) — graph design

**Validation Checklist:**
- [ ] Graph visualization shows no cycles
- [ ] Max path length < 10 nodes (too long = design smell)
- [ ] Integration test with timeout (fail if > 60 seconds)

---

### CRIT-03: RAG Hallucination Contamination
**Severity:** CRITICAL — System invents fake financial principles

**What It Is:**
LLM hallucinates "facts" about Value Investing instead of citing retrieved sources.

**Example:**
```
User: "What does Graham say about margin of safety?"

❌ BAD (hallucination):
Agent: "Graham recommends a margin of safety of at least 50% for growth stocks and 30% for value stocks."

✅ GOOD (cited retrieval):
Agent: "Graham states: 'A margin of safety is achieved when securities are purchased at prices sufficiently below their indicated value' (The Intelligent Investor, Ch. 20, p. 512). He emphasizes diversification over specific percentage thresholds."
```

**Why It Happens:**
- LLM trained on internet noise (unreliable Graham summaries)
- RAG retrieval fails silently, LLM fills gap with training data
- No citation enforcement in prompt

**Consequences:**
- Agents make decisions based on invented principles
- User trusts "Graham methodology" that's actually fiction
- Destroys credibility when experts notice

**Detection:**
```python
# Red flag: Agent response without citation
response = "Graham recommends X"  # No source reference

# Check: Is this in retrieved chunks?
retrieved_chunks = vector_store.similarity_search("margin of safety")
if "Graham recommends X" not in retrieved_chunks:
    # Hallucination detected
```

**Prevention:**
```python
# ✅ GOOD: Enforce citations in prompt
SYSTEM_PROMPT = """
You are a Value Investing analyst. When answering questions:

1. ONLY cite information from the retrieved context below
2. Every claim must include: (Source, Page, Quote)
3. If context doesn't contain the answer, say "I don't have information on that"
4. NEVER use your training data for financial facts

Retrieved Context:
{retrieved_chunks}
"""

# Validate response has citations
def validate_response(response, retrieved_chunks):
    if not re.search(r'\(.*?, p\. \d+\)', response):
        raise ValueError("Response missing citation")

    # Check quote exists in chunks
    quotes = extract_quotes(response)
    for quote in quotes:
        if not any(quote in chunk for chunk in retrieved_chunks):
            raise ValueError(f"Quote not found in context: {quote}")
```

**Use RAGAs Evaluation:**
```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

# Faithfulness: Does answer align with retrieved context?
results = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy]
)

if results['faithfulness'] < 0.8:
    raise ValueError("High hallucination risk detected")
```

**Phase to Address:** Phase 3 (RAG Layer)

**Validation Checklist:**
- [ ] All agent responses include citations
- [ ] RAGAs faithfulness score > 0.8
- [ ] Manual spot-check of 10 responses for hallucinations
- [ ] Prompt explicitly forbids using training data

---

### CRIT-04: Overfitting to Training Period
**Severity:** CRITICAL — Strategy fails in new market regime

**What It Is:**
Backtest optimized for 2015-2020 bull market, collapses in 2022 bear market.

**Example:**
- System learns "buy tech stocks with high P/S ratios" (worked in ZIRP era)
- 2022: Rising rates kill unprofitable tech (strategy implodes)

**Why It Happens:**
- Backtest period too short (lacks regime diversity)
- Parameters tuned to maximize Sharpe ratio on test set
- No out-of-sample validation

**Consequences:**
- Paper trading shows 40% drawdown in first month
- User abandons system, TFM fails validation

**Detection:**
- Backtest performance too good (Sharpe > 2.5 = suspicious)
- Performance collapses on out-of-sample period
- Strategy changes dramatically with small parameter tweaks (fragile)

**Prevention:**
```python
# ✅ GOOD: Multi-regime backtesting
test_periods = [
    ("2008-2009", "Financial Crisis"),     # Bear market, credit crunch
    ("2010-2015", "Recovery"),             # Slow growth
    ("2016-2019", "Bull Market"),          # Low rates, growth
    ("2020", "COVID Crash + Recovery"),    # Extreme volatility
    ("2021-2022", "Inflation Regime"),     # Rising rates, value rotation
]

for period, label in test_periods:
    results = backtest(strategy, period)
    print(f"{label}: Sharpe={results.sharpe}, Max DD={results.max_drawdown}")

# Fail if strategy breaks in any regime
assert all(results.sharpe > 0.5 for results in all_results)
```

**Walk-Forward Validation:**
```python
# Train on 2015-2017, test on 2018
# Train on 2016-2018, test on 2019
# Train on 2017-2019, test on 2020
# Average out-of-sample performance = true expectation
```

**Phase to Address:** Phase 5 (Backtesting)

**Validation Checklist:**
- [ ] Backtest includes at least one bear market
- [ ] Out-of-sample performance within 20% of in-sample
- [ ] Walk-forward validation implemented
- [ ] Strategy logic makes sense (not data-mined parameters)

---

### CRIT-05: Non-Deterministic Debugging Nightmare
**Severity:** CRITICAL — Cannot reproduce bugs

**What It Is:**
LLM temperature > 0 + unseeded randomness = different output every run.

**Example:**
```python
# ❌ BAD: Non-deterministic
llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.7)

# Run 1: Agent recommends BUY
# Run 2: Agent recommends PASS (same inputs!)
# Run 3: Agent recommends BUY again
# How do you debug this?
```

**Why It Happens:**
- Default LLM temperature = 1.0 (maximum randomness)
- Monte Carlo simulations without seed
- Parallel agents with race conditions

**Consequences:**
- User reports bug, you cannot reproduce
- Backtest results change every run (no validation possible)
- EU AI Act compliance impossible (cannot explain decision)

**Detection:**
- Run same analysis twice, get different results
- Unit tests flaky (pass sometimes, fail others)

**Prevention:**
```python
# ✅ GOOD: Deterministic execution
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    temperature=0,  # Deterministic
)

# Seed all randomness
import numpy as np
import random

def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    # If using PyTorch: torch.manual_seed(seed)

set_seed(42)

# Monte Carlo simulations
np.random.seed(42)
simulations = np.random.normal(loc=0.05, scale=0.15, size=10000)
```

**Exception: When to use temperature > 0:**
- Generating creative explanations for dashboard (non-critical)
- User-facing chatbot (not agent logic)

**Phase to Address:** Phase 1 (Foundation) — global config

**Validation Checklist:**
- [ ] All LLM calls use temperature=0
- [ ] All random operations seeded
- [ ] Integration test: Run twice, assert identical outputs
- [ ] Document where non-determinism is allowed (and why)

---

### CRIT-06: EU AI Act Compliance Theater
**Severity:** CRITICAL — Legal liability without substance

**What It Is:**
Logging agent outputs without actual explainability of reasoning process.

**Example:**
```python
# ❌ BAD: Logs conclusion, not reasoning
log_decision("BUY", "AAPL", conviction=0.85)

# User asks: "Why BUY?"
# System shows: "Conviction: 0.85" (useless)
```

**Why It Happens:**
- Misunderstanding EU AI Act requirements (it's not just logging)
- Focusing on outputs, not reasoning process
- No testing with actual non-technical users

**Consequences:**
- Regulatory audit reveals system is "black box"
- Classified as "High-Risk AI" (heavy regulation)
- Users don't trust recommendations (adoption fails)

**What EU AI Act Actually Requires:**
1. **Transparency**: User understands how decision was made
2. **Human oversight**: Meaningful intervention points (not rubber-stamping)
3. **Auditability**: Can reconstruct decision 6 months later
4. **Risk management**: Identified risks and mitigations documented

**Prevention:**
```python
# ✅ GOOD: Structured explainability
@dataclass
class ExplainableDecision:
    recommendation: str  # "BUY", "PASS", "SELL"
    ticker: str
    conviction: float

    # Reasoning chain
    bull_case: str  # "EPV of $150 vs price of $120 = 25% margin of safety"
    bear_case: str  # "High valuation at 82nd percentile of 10-year range"
    judge_rationale: str  # "Bull case stronger: margin of safety exceeds threshold despite high valuation"

    # Data provenance
    data_sources: list[str]  # ["yfinance AAPL 2024-01-31", "FRED FEDFUNDS 2024-01-31"]
    citations: list[str]  # ["Graham, Intelligent Investor, p. 512"]

    # Agent state trail
    agent_states: dict  # Full LangGraph state at each step

    # Human oversight
    hitl_triggered: bool
    hitl_reason: Optional[str]

    # Timestamp
    timestamp: datetime

def log_explainable_decision(decision: ExplainableDecision):
    # Store in audit_logs table
    db.save(decision)

    # Test: Can non-technical user understand?
    assert len(decision.judge_rationale) > 0
    assert decision.judge_rationale != "High conviction"  # Too vague
```

**Dashboard Requirements:**
- Show agent debate (Bull said X, Bear said Y, Judge chose Z because...)
- Link to source data (click "P/E ratio" → see yfinance API response)
- Explain thresholds (why is 25% margin of safety "good"? Graham says...)

**Phase to Address:** Phase 1 (Foundation) — state schema design

**Validation Checklist:**
- [ ] Every decision has structured reasoning (not just conclusion)
- [ ] Non-technical user can understand explanation (user testing)
- [ ] Can reconstruct decision from logs (test with 1-month-old decision)
- [ ] HITL triggers are meaningful (not "click OK to continue")

---

### CRIT-07: Data Quality Silent Failures
**Severity:** CRITICAL — Garbage in, garbage out

**What It Is:**
APIs return stale/incorrect data, system doesn't notice, makes bad recommendations.

**Example:**
```python
# API returns earnings from 2 quarters ago (stale)
earnings = get_earnings("AAPL")  # Should be Q4 2024, actually Q2 2024

# Agent calculates P/E using stale earnings
pe_ratio = price / earnings  # Wrong!

# User buys overvalued stock, loses money
```

**Why It Happens:**
- Free APIs are unreliable (yfinance, Alpha Vantage outages common)
- No validation of data freshness or completeness
- Fail-silent errors (API returns 200 OK with incomplete data)

**Consequences:**
- Agent recommends buying a company that just reported terrible earnings
- User loses trust and money
- System credibility destroyed

**Detection:**
```python
# Red flags
assert data["last_updated"] > datetime.now() - timedelta(days=30)  # Stale?
assert data["earnings"] is not None  # Missing?
assert data["pe_ratio"] > 0  # Nonsensical (negative P/E)?
assert data["market_cap"] > 1_000_000_000  # Below minimum threshold?
```

**Prevention:**
```python
from typing import Optional
from datetime import datetime, timedelta

@dataclass
class ValidatedFinancials:
    ticker: str
    earnings: float
    last_updated: datetime
    source: str  # "yfinance", "alphavantage"
    quality_score: float  # 0.0-1.0

def fetch_financials_with_validation(ticker: str) -> ValidatedFinancials:
    # Try primary source
    try:
        data = yfinance.get_fundamentals(ticker)
    except Exception as e:
        logger.warning(f"yfinance failed for {ticker}: {e}")
        data = None

    # Fallback to secondary source
    if data is None:
        try:
            data = alphavantage.get_fundamentals(ticker)
        except Exception as e:
            logger.error(f"All data sources failed for {ticker}")
            raise DataUnavailableError(ticker)

    # Validate freshness
    if data["last_updated"] < datetime.now() - timedelta(days=30):
        logger.warning(f"Stale data for {ticker}: {data['last_updated']}")
        quality_score = 0.6
        # Option: Trigger HITL
        trigger_hitl(f"Data for {ticker} is stale (30+ days old)")
    else:
        quality_score = 1.0

    # Validate completeness
    required_fields = ["earnings", "revenue", "book_value", "debt"]
    missing = [f for f in required_fields if data.get(f) is None]
    if missing:
        logger.error(f"Missing fields for {ticker}: {missing}")
        raise DataIncompleteError(ticker, missing)

    # Validate sanity
    if data["earnings"] < 0 and data["pe_ratio"] > 0:
        logger.error(f"Inconsistent data for {ticker}: negative earnings but positive P/E")
        raise DataInconsistentError(ticker)

    return ValidatedFinancials(
        ticker=ticker,
        earnings=data["earnings"],
        last_updated=data["last_updated"],
        source=data["source"],
        quality_score=quality_score
    )

# Agent uses validated data
def value_hunter_agent(state, config):
    financials = fetch_financials_with_validation(state["ticker"])

    if financials.quality_score < 0.8:
        # Low confidence due to stale data → trigger HITL
        return {
            "hitl_triggered": True,
            "hitl_reason": f"Data quality low ({financials.quality_score}) for {state['ticker']}"
        }

    epv = calculate_epv(financials)
    return {"intrinsic_value": epv}
```

**Phase to Address:** Phase 2 (Data Layer)

**Validation Checklist:**
- [ ] All data fetching goes through validation layer
- [ ] Fallback strategy tested (disconnect primary API, verify fallback works)
- [ ] Staleness triggers warning or HITL
- [ ] Sanity checks for nonsensical values (negative book value, etc.)

---

### CRIT-08: Human-in-the-Loop Fatigue
**Severity:** CRITICAL — Users rubber-stamp bad decisions

**What It Is:**
HITL triggers so often that users stop reading and just click "Approve" reflexively.

**Example:**
```python
# ❌ BAD: Triggers HITL for every decision
if conviction < 1.0:  # Always true
    trigger_hitl()

# User approves 20 decisions in a row, stops reading
# Decision #21 is terrible, user approves anyway
```

**Why It Happens:**
- Overly conservative HITL thresholds (trigger on every minor uncertainty)
- No risk-based prioritization (treat all decisions equally)
- Poor UI (hard to review, takes too long)

**Consequences:**
- HITL becomes security theater (doesn't actually add oversight)
- Users frustrated, abandon system
- Defeats purpose of human oversight

**Detection:**
- HITL approval rate > 95% (users aren't thinking)
- Average review time < 10 seconds (too fast to read)
- User complaints about "too many interruptions"

**Prevention:**
```python
# ✅ GOOD: Risk-based HITL triggering
def should_trigger_hitl(state: InvestmentState) -> bool:
    # High-risk scenarios only
    high_risk_conditions = [
        state["fraud_veto"],  # Guardian detected fraud risk
        state["margin_of_safety"] < 0,  # No margin of safety
        state["position_size"] > 0.10,  # >10% of portfolio (concentration risk)
        state["conviction"] < 0.5,  # Very low confidence
        state["data_quality_score"] < 0.7,  # Stale/incomplete data
    ]

    return any(high_risk_conditions)

# Additional: Auto-approve low-risk decisions
def auto_approve_if_safe(state: InvestmentState) -> bool:
    safe_conditions = [
        state["conviction"] > 0.8,
        state["margin_of_safety"] > 0.3,
        state["position_size"] < 0.05,
        not state["fraud_veto"],
        state["data_quality_score"] > 0.9,
    ]

    return all(safe_conditions)
```

**UI Improvements:**
- **Summary first**: "BUY 3% position in AAPL (conviction: 85%)" — approve/reject buttons
- **Details on demand**: Expand to see full agent debate
- **Pre-filled recommendation**: Default action is what Judge recommends (user can override)
- **Batch review**: Show 5 decisions at once (approve all, or expand to review)

**Phase to Address:** Phase 4 (Orchestration) + Phase 6 (UI)

**Validation Checklist:**
- [ ] HITL triggers < 20% of decisions (80% auto-approved or rejected)
- [ ] Average review time > 30 seconds (users actually reading)
- [ ] User testing confirms reviews are meaningful, not tedious

---

## MODERATE PITFALLS

### MOD-01: State Explosion in LangGraph
**Severity:** MODERATE — Performance degradation

**What It Is:**
Shared state grows unbounded, checkpointing becomes slow.

**Example:**
```python
# ❌ BAD: Appending to state without limit
class InvestmentState(TypedDict):
    messages: list[BaseMessage]  # Grows forever
    historical_prices: list[float]  # 10 years of daily data

# After 10 analyses: messages list has 1000+ entries
# Checkpoint serialization takes 5 seconds
```

**Prevention:**
```python
# ✅ GOOD: Bounded state, move large data to DB
class InvestmentState(TypedDict):
    messages: Annotated[list[BaseMessage], lambda old, new: (old + new)[-50:]]  # Keep last 50
    analysis_id: str  # Reference to DB row with full data

# Store large data externally
db.save_historical_prices(analysis_id, prices)
```

**Phase to Address:** Phase 1 (State Schema)

---

### MOD-02: Token Cost Explosion
**Severity:** MODERATE — Budget overrun

**What It Is:**
LLM calls include unnecessary context, 10x token usage.

**Prevention:**
- Use Haiku for simple tasks (Guardian fraud detection doesn't need Opus)
- Summarize long documents before RAG (don't embed entire 300-page book)
- Cache embeddings (don't re-embed same document)

**Phase to Address:** Phase 3 (Agent Implementation)

---

### MOD-03: Dependency Version Hell
**Severity:** MODERATE — Breaks on deployment

**What It Is:**
Works on dev machine, breaks in production due to library version mismatch.

**Prevention:**
```bash
# ✅ Lock versions
uv pip compile pyproject.toml > requirements.lock
uv pip install -r requirements.lock
```

**Phase to Address:** Phase 1 (Setup)

---

### MOD-04: Ignoring Value Investing Realities (Value Traps)
**Severity:** MODERATE — Strategy underperforms

**What It Is:**
Buying "cheap" stocks that deserve to be cheap (declining businesses).

**Prevention:**
- Strategist agent checks for declining margins, revenue, market share
- Moat analysis (is competitive advantage durable?)
- Avoid "cigar butt" investing (Graham's early mistake)

**Phase to Address:** Phase 3 (Layer 2-3 Agents)

---

### MOD-05: Over-Engineering Phase 1
**Severity:** MODERATE — Never ships

**What It Is:**
Building microservices, Kubernetes, GraphQL for MVP.

**Prevention:**
- Monolith is fine for MVP
- Streamlit over React
- PostgreSQL over distributed database

**Phase to Address:** Phase 1 (Architecture Decisions)

---

## MINOR PITFALLS

### MIN-01: Poor Error Messages
**What It Is:** `KeyError: 'intrinsic_value'` instead of "Value Hunter agent failed to calculate intrinsic value for AAPL"

**Prevention:** Wrap exceptions with context

---

### MIN-02: No Local Development Story
**What It Is:** Must deploy to cloud to test changes (slow iteration)

**Prevention:** Docker Compose for local Supabase + app

---

### MIN-03: Hardcoded Configuration
**What It Is:** Thresholds (conviction > 0.6) hardcoded in agent logic

**Prevention:** Move to config.py or .env

---

## LANGGRAPH-SPECIFIC PITFALLS

### LG-01: Misusing State Reducers
**What It Is:** Multiple agents overwrite same state key, last one wins

**Prevention:** Use `Annotated[list, lambda old, new: old + new]` for append semantics

---

### LG-02: Forgetting Checkpointing
**What It Is:** HITL interrupt without checkpointer → state lost on resume

**Prevention:** Always compile with `checkpointer=PostgresSaver(...)`

---

### LG-03: Ignoring Graph Compilation Errors
**What It Is:** Graph compiles with warnings, breaks at runtime

**Prevention:** Treat compilation warnings as errors, visualize graph

---

## Phase-Specific Prevention Roadmap

| Phase | Critical Pitfalls to Address | How |
|-------|------------------------------|-----|
| **Phase 1 (Foundation)** | CRIT-02 (Deadlocks), CRIT-05 (Non-determinism), CRIT-06 (Compliance), MOD-05 (Over-engineering) | Acyclic graph design, temperature=0, state schema with reasoning fields, monolith architecture |
| **Phase 2 (Data)** | CRIT-01 (Look-ahead bias), CRIT-07 (Data quality) | Point-in-time data access, validation layer, fallback strategy |
| **Phase 3 (Agents)** | CRIT-03 (RAG hallucination), MOD-02 (Token costs), MOD-04 (Value traps) | Citation enforcement, RAGAs, model selection (Haiku vs Sonnet), moat analysis |
| **Phase 4 (Orchestration)** | CRIT-08 (HITL fatigue) | Risk-based triggering, auto-approve low-risk |
| **Phase 5 (Backtesting)** | CRIT-04 (Overfitting) | Multi-regime testing, walk-forward validation |
| **Phase 6 (UI)** | CRIT-06 (Compliance theater) | Explainability dashboard, user testing with non-technical users |

---

**Last Updated:** 2026-02-01
**Researcher Confidence:** HIGH
