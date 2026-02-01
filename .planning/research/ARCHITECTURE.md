# Architecture Research: Multi-Agent Financial Investment Systems

**Domain:** LangGraph-based multi-agent systems for financial analysis
**Research Date:** 2026-02-01
**Confidence Level:** HIGH (architectural patterns), MEDIUM (LangGraph API specifics)

## Executive Summary

Multi-agent financial investment systems with LangGraph follow a **layered StateGraph architecture** where:
- **Agents are pure functions** `(state, config) → state_updates`
- **Shared state is single source of truth** (no agent-to-agent communication)
- **Dialectical flow** implemented via conditional edges (thesis → antithesis → synthesis)
- **HITL gates** use LangGraph's interrupt mechanism with checkpointing
- **Build order is critical**: State schema → single layer → dialectical core → execution → optimization

---

## 1. Overall Architecture Pattern

### High-Level Structure

```
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph StateGraph                     │
│                                                               │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐  │
│  │   Layer 1    │────▶│   Layer 2    │────▶│   Layer 3   │  │
│  │  (Context)   │     │   (Bulls)    │     │   (Bears)   │  │
│  │  Macro +     │     │ Value Hunter │     │  Bear +     │  │
│  │  Sentiment   │     │ + Strategist │     │  Historian  │  │
│  └──────────────┘     └──────────────┘     │ + Guardian  │  │
│         │                     │             └─────────────┘  │
│         │                     │                     │        │
│         └─────────────────────┴─────────────────────┘        │
│                              │                               │
│                    ┌─────────▼──────────┐                    │
│                    │     Layer 4        │                    │
│                    │  (Orchestration)   │                    │
│                    │  Judge + Optimizer │                    │
│                    └─────────┬──────────┘                    │
│                              │                               │
│                    ┌─────────▼──────────┐                    │
│                    │  HITL Checkpoint?  │◀── Interrupt       │
│                    └─────────┬──────────┘                    │
│                              │                               │
│                    ┌─────────▼──────────┐                    │
│                    │     Layer 5        │                    │
│                    │   (Execution)      │                    │
│                    │      Trader        │                    │
│                    └────────────────────┘                    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Audit Trail      │
                    │ (PostgreSQL)     │
                    └──────────────────┘
```

### Key Architectural Principles

1. **State-Centric Design**: All agents read from and write to a shared `InvestmentState` TypedDict
2. **No Agent-to-Agent Communication**: Violates auditability — all routing via StateGraph conditional edges
3. **Agents as Pure Functions**: Stateless, testable, horizontally scalable
4. **Checkpointing Everything**: EU AI Act compliance requires complete decision trail
5. **Conditional Routing Over Manual Branching**: Let LangGraph handle control flow

---

## 2. Component Boundaries

| Component | Responsibility | Inputs | Outputs | External Dependencies |
|-----------|---------------|--------|---------|----------------------|
| **StateGraph** | Orchestration, flow control, routing | User request, market data | Final recommendation, audit trail | LangGraph framework |
| **Shared State** | Single source of truth | All agent updates | Current system state | PostgreSQL (checkpointing) |
| **Layer 1: Context** | Macro regime, market sentiment | Economic indicators, news, earnings calls | `macro_context`, `sentiment_scores` | FRED API, news APIs |
| **Layer 2: Bulls** | Investment thesis generation | Fundamentals, historical data | `bull_recommendations`, `intrinsic_value` | yfinance, Alpha Vantage |
| **Layer 3: Bears** | Thesis challenge, risk identification | Bull recommendations, fundamentals | `bear_warnings`, `objections`, `veto_flags` | Same as Bulls |
| **Layer 4: Orchestration** | Synthesis, position sizing | Bull + Bear outputs | `final_decision`, `position_size` | None (pure logic) |
| **Layer 5: Execution** | Trade simulation/execution | Final decision, market data | `executed_trades` | Broker API (future), vectorbt (backtesting) |
| **HITL Module** | Human review gates | Disagreement flags, confidence scores | Human approval/rejection | Frontend UI |
| **Knowledge Base** | RAG for financial principles | User query, agent question | Cited passages from Graham, Dalio, etc. | Supabase pgvector |
| **Audit Logger** | EU AI Act compliance | All state transitions | Queryable decision trail | PostgreSQL |

---

## 3. Core Interaction Patterns

### Pattern 1: Agent Execution (Pure Function)

```python
from typing import TypedDict
from langchain_core.messages import BaseMessage

class InvestmentState(TypedDict):
    """Shared state across all agents"""
    # Input
    ticker: str
    messages: list[BaseMessage]

    # Layer 1 outputs
    macro_context: dict  # {"regime": "growth", "multiplier": 0.85}
    sentiment_scores: dict  # {"narrative_risk": 0.3, "volatility": 0.15}

    # Layer 2 outputs (Bulls)
    intrinsic_value: float
    margin_of_safety: float
    moat_rating: int  # 1-5
    veto_score: int  # VeTO model score

    # Layer 3 outputs (Bears)
    objections: list[str]
    sensitivity_penalty: float
    historical_percentile: int
    fraud_veto: bool  # Guardian veto

    # Layer 4 outputs (Orchestration)
    consensus_decision: str  # "BUY", "PASS", "HITL_REQUIRED"
    conviction: float  # 0.0-1.0
    position_size: float  # % of portfolio

    # Layer 5 outputs (Execution)
    executed_trades: list[dict]

    # HITL
    hitl_triggered: bool
    hitl_reason: str

# Agent as pure function
def value_hunter_agent(state: InvestmentState, config: dict) -> dict:
    """
    Layer 2 Bull: Calculate intrinsic value via EPV

    Returns: Dict with keys to update in state
    """
    ticker = state["ticker"]

    # Fetch fundamentals
    fundamentals = get_fundamentals(ticker)  # External API call

    # Calculate EPV (Earnings Power Value)
    normalized_earnings = fundamentals["net_income"] / (1 + fundamentals["cyclical_adjustment"])
    wacc = calculate_wacc(fundamentals)
    epv = normalized_earnings / wacc

    # Calculate margin of safety
    current_price = get_current_price(ticker)
    margin_of_safety = (epv - current_price) / epv

    # Assess moat (competitive advantage)
    roic = fundamentals["roic"]
    moat_rating = 5 if roic > 0.20 else 3 if roic > 0.15 else 1

    # Return state updates
    return {
        "intrinsic_value": epv,
        "margin_of_safety": margin_of_safety,
        "moat_rating": moat_rating,
        "messages": state["messages"] + [
            f"Value Hunter: EPV=${epv:.2f}, Margin of Safety={margin_of_safety:.1%}, Moat={moat_rating}/5"
        ]
    }
```

**Why This Pattern:**
- Testable: Can unit test agent with mock state
- Reproducible: Same state → same output (if LLM temperature=0)
- Auditable: Input state + output updates logged
- Composable: Drop in/out agents without affecting others

---

### Pattern 2: Conditional Routing (Dialectical Flow)

```python
from langgraph.graph import StateGraph, END

def should_trigger_hitl(state: InvestmentState) -> str:
    """
    Routing function: Decide next node based on state

    Returns: Node name ("hitl_gate", "optimizer", or END)
    """
    # Trigger HITL if Guardian vetoes
    if state.get("fraud_veto"):
        return "hitl_gate"

    # Trigger HITL if Bull/Bear disagreement is large
    margin = state.get("margin_of_safety", 0)
    penalty = state.get("sensitivity_penalty", 0)

    if margin > 0.3 and penalty > 0.5:  # Bull says BUY, Bear says FRAGILE
        return "hitl_gate"

    # Trigger HITL if conviction is low
    if state.get("conviction", 1.0) < 0.6:
        return "hitl_gate"

    # Otherwise, proceed to Optimizer
    return "optimizer"

# Build graph
workflow = StateGraph(InvestmentState)

# Add nodes
workflow.add_node("macro_oracle", macro_oracle_agent)
workflow.add_node("value_hunter", value_hunter_agent)
workflow.add_node("bear", bear_agent)
workflow.add_node("judge", judge_agent)
workflow.add_node("hitl_gate", hitl_handler)  # Interrupt node
workflow.add_node("optimizer", optimizer_agent)
workflow.add_node("trader", trader_agent)

# Add edges
workflow.add_edge("macro_oracle", "value_hunter")
workflow.add_edge("value_hunter", "bear")
workflow.add_edge("bear", "judge")

# Conditional edge: Judge decides HITL or Optimizer
workflow.add_conditional_edges(
    "judge",
    should_trigger_hitl,
    {
        "hitl_gate": "hitl_gate",
        "optimizer": "optimizer"
    }
)

workflow.add_edge("hitl_gate", "optimizer")  # After HITL, continue
workflow.add_edge("optimizer", "trader")
workflow.add_edge("trader", END)

# Set entry point
workflow.set_entry_point("macro_oracle")

# Compile
app = workflow.compile(checkpointer=PostgresSaver(...))
```

**Why This Pattern:**
- Declarative control flow (vs imperative if/else spaghetti)
- Auditable: Graph structure visible, routing logic in one place
- Interruptible: `hitl_gate` can pause execution, persist state, resume later

---

### Pattern 3: HITL Interrupt & Resume

```python
from langgraph.checkpoint import PostgresSaver

# PostgreSQL checkpointer for state persistence
checkpointer = PostgresSaver.from_conn_string("postgresql://...")

app = workflow.compile(checkpointer=checkpointer, interrupt_before=["hitl_gate"])

# Initial invocation
config = {"configurable": {"thread_id": "investment-123"}}
result = app.invoke({"ticker": "AAPL", "messages": []}, config)

# If HITL triggered, execution stops before hitl_gate
# State is persisted in PostgreSQL with thread_id="investment-123"

# User reviews recommendation in UI, approves/rejects
# Resume execution
human_decision = {"hitl_approval": True, "hitl_comment": "Agree with Bear's concern, reduce position size"}

# Update state and resume
app.update_state(config, human_decision)
final_result = app.invoke(None, config)  # None = resume from checkpoint
```

**Why This Pattern:**
- EU AI Act compliance: Human oversight at critical points
- State survives process crashes (persisted in DB)
- User can review at own pace (async workflow)

---

### Pattern 4: Parallel Agent Execution

```python
# Layer 2 (Bulls) has 2 independent agents: Value Hunter + Strategist
# Run them in parallel

def layer2_parallel_node(state: InvestmentState, config: dict) -> dict:
    """
    Execute Value Hunter and Strategist in parallel, merge results
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both agents
        future_hunter = executor.submit(value_hunter_agent, state, config)
        future_strategist = executor.submit(strategist_agent, state, config)

        # Wait for results
        hunter_updates = future_hunter.result()
        strategist_updates = future_strategist.result()

    # Merge updates (no key collisions expected)
    merged = {**hunter_updates, **strategist_updates}

    return merged

# Use in graph
workflow.add_node("layer2_bulls", layer2_parallel_node)
```

**Why This Pattern:**
- Faster execution (2 agents in parallel vs sequential)
- Agents are independent (no inter-agent dependencies within layer)
- Results merged into shared state

**Warning:** Only parallelize within a layer if agents don't depend on each other's outputs.

---

### Pattern 5: State Reducers for Conflict Resolution

```python
from typing import Annotated
from langgraph.graph import add_messages  # Built-in reducer

class InvestmentState(TypedDict):
    # Messages list: Multiple agents append, use reducer to merge
    messages: Annotated[list[BaseMessage], add_messages]

    # Objections: Bear agent appends, Historian appends → list grows
    objections: Annotated[list[str], lambda existing, new: existing + new]

    # Conviction: Judge overwrites (no reducer needed)
    conviction: float
```

**Why Reducers:**
- Multiple agents write to same key (e.g., `messages`)
- Reducer defines merge strategy (append, max, average, overwrite)
- Prevents conflicts and race conditions

---

## 4. Data Flow Sequence

```
User: "Analyze ticker AAPL"
│
▼
[StateGraph Initialize]
state = {
    "ticker": "AAPL",
    "messages": [],
    ...all fields None/empty
}
│
▼
[Layer 1: Macro Oracle]
Inputs: FRED API (yield curve, inflation)
Outputs: state.macro_context = {"regime": "growth", "multiplier": 0.9}
│
▼
[Layer 1: Sentiment Agent (parallel with Macro)]
Inputs: Earnings call transcripts, news
Outputs: state.sentiment_scores = {"narrative_risk": 0.2}
│
▼
[Layer 2: Value Hunter]
Inputs: state.ticker, yfinance fundamentals
Outputs: state.intrinsic_value = 150, state.margin_of_safety = 0.25
│
▼
[Layer 2: Strategist (parallel with Value Hunter)]
Inputs: state.ticker, VeTO model inputs
Outputs: state.veto_score = 78
│
▼
[Layer 3: Bear]
Inputs: state.intrinsic_value, state.margin_of_safety
Action: Run Monte Carlo sensitivity test
Outputs: state.objections = ["Growth assumptions fragile"], state.sensitivity_penalty = 0.4
│
▼
[Layer 3: Historian (parallel)]
Inputs: state.ticker, 10-year P/E history
Outputs: state.historical_percentile = 82, state.objections += ["Trading at 82nd percentile valuation"]
│
▼
[Layer 3: Guardian (parallel)]
Inputs: state.ticker, financial statements
Action: Calculate Z-Score, M-Score
Outputs: state.fraud_veto = False (scores OK)
│
▼
[Layer 4: Judge]
Inputs: All Layer 2 + 3 outputs
Action: Fuzzy logic arbitration (simplified for MVP: if objections > 2 → low conviction)
Outputs: state.consensus_decision = "BUY", state.conviction = 0.65
│
▼
[Conditional Edge: should_trigger_hitl(state)]
Conviction = 0.65 (> 0.6 threshold) → Route to "optimizer"
(If conviction < 0.6 → Route to "hitl_gate" → INTERRUPT)
│
▼
[Layer 4: Optimizer]
Inputs: state.conviction, state.macro_multiplier, existing portfolio
Action: Kelly criterion calculation
Outputs: state.position_size = 0.04  # 4% of portfolio
│
▼
[Layer 5: Trader]
Inputs: state.ticker, state.position_size
Action: Simulate limit order at VWAP
Outputs: state.executed_trades = [{"ticker": "AAPL", "shares": 10, "price": 148.50}]
│
▼
[Audit Logger]
Write complete state to PostgreSQL audit_logs table
│
▼
[Return to User]
Display: Recommendation + Agent reasoning + Audit trail link
```

---

## 5. Build Order Recommendations

### Phase 1: Foundation (Week 1-2)
**Goal:** Prove LangGraph architecture works

**Deliverables:**
1. `InvestmentState` TypedDict fully defined
2. Basic StateGraph with 1 dummy agent
3. PostgresSaver checkpointing configured
4. HITL interrupt mechanism tested (manual trigger)

**Why First:**
- State schema locks in agent interfaces
- Changing state schema mid-project breaks all agents
- Checkpointing is hard to retrofit (design choice affects DB schema)

**Anti-Pattern:** Starting with agent logic before state schema → endless refactoring

---

### Phase 2: Single Layer Prototype (Week 3-4)
**Goal:** Validate end-to-end flow with minimal complexity

**Deliverables:**
1. Layer 1 (Macro Oracle + Sentiment Agent) implemented
2. Data integration (FRED API, yfinance)
3. Audit logging working
4. Streamlit UI displays agent outputs

**Why Second:**
- Proves architecture before horizontal scaling
- Catches integration issues early (API failures, data quality)
- Demonstrates value to stakeholders (working demo)

**Anti-Pattern:** Building all 10 agents before testing any → integration nightmare

---

### Phase 3: Dialectical Core (Week 5-10)
**Goal:** Implement unique value proposition (Bulls vs Bears)

**Deliverables:**
1. Layer 2 (Value Hunter + Strategist)
2. Layer 3 (Bear + Historian + Guardian)
3. Layer 4 (Judge with simplified voting)
4. Conditional routing (disagreement → HITL)
5. RAG knowledge base (Graham, Dalio excerpts)

**Why Third:**
- Core differentiation must work before execution
- Most complex logic (EPV, Monte Carlo, Z-Score)
- Highest risk of rework

**Anti-Pattern:** Building execution layer first → can execute bad decisions efficiently

---

### Phase 4: Execution (Week 11-12)
**Goal:** Portfolio management and trade simulation

**Deliverables:**
1. Layer 4 (Optimizer with Kelly criterion)
2. Layer 5 (Trader with paper trading)
3. Portfolio state tracking
4. Risk guardrails

**Why Fourth:**
- Downstream of decision-making (depends on Layer 2-4 outputs)
- Simpler logic than dialectical core
- Can defer to post-MVP without breaking core value

---

### Phase 5: Validation (Week 13-15)
**Goal:** Prove system works on historical data

**Deliverables:**
1. Backtesting engine (vectorbt)
2. Walk-forward validation
3. Performance metrics dashboard

**Why Fifth:**
- Requires all agents functional
- Validates architecture decisions
- Builds credibility for TFM

---

### Phase 6: Polish (Week 16-18)
**Goal:** Production-ready UI and explainability

**Deliverables:**
1. Explainability dashboard (reasoning logs)
2. HITL UI (approve/reject with comments)
3. Live agent activity visualization
4. EU AI Act compliance report

**Why Last:**
- Depends on all agents producing outputs
- UI is easier to iterate than backend
- Can simplify for MVP without losing functionality

---

## 6. Scalability Implications

### MVP (1-10 users, local/demo)

**Architecture:**
- Single-threaded Python process
- In-memory state (with checkpoint fallback to Postgres)
- Synchronous agent execution
- Streamlit for UI (single-threaded)

**Limitations:**
- 1 analysis at a time
- No concurrency
- State in RAM (loss on crash, but checkpoints persist)

**Good Enough For:** TFM demo, initial validation

---

### Growth (100-1K users, production)

**Architecture:**
- Multi-process workers (Gunicorn/Uvicorn)
- PostgreSQL for all state (no in-memory)
- Async agent execution (asyncio)
- Separate frontend (React) + backend (FastAPI)
- LangSmith for observability

**Changes Required:**
- Async rewrites for I/O-bound agents (API calls)
- Horizontal scaling via load balancer
- Rate limiting per user
- Queue for long-running analyses (Celery/BullMQ)

---

### Scale (10K+ users, enterprise)

**Architecture:**
- Distributed graph execution (LangGraph Cloud or custom)
- Event-driven agents (Kafka/RabbitMQ)
- Streaming state updates (WebSockets)
- Separate hot (recent) vs cold (historical) storage
- Multi-region deployment

**Changes Required:**
- Major refactor to event-driven
- Sharding strategy for state
- GraphQL for flexible frontend queries

---

## 7. Critical Anti-Patterns to Avoid

### Anti-Pattern 1: Agent-to-Agent Direct Communication

**Bad:**
```python
class BearAgent:
    def __init__(self):
        self.bull_agent = ValueHunterAgent()

    def analyze(self, ticker):
        bull_thesis = self.bull_agent.get_thesis(ticker)  # ❌ Direct call
        return self.challenge(bull_thesis)
```

**Why Bad:**
- Breaks auditability (who called whom?)
- Creates hidden dependencies
- Impossible to interrupt/resume

**Good:**
```python
def bear_agent(state: InvestmentState, config: dict) -> dict:
    bull_thesis = state["intrinsic_value"]  # ✅ Read from state
    return {"objections": challenge(bull_thesis)}
```

---

### Anti-Pattern 2: Stateful Agents

**Bad:**
```python
class MacroOracle:
    def __init__(self):
        self.cached_macro_data = None  # ❌ Mutable state

    def analyze(self, ticker):
        if not self.cached_macro_data:
            self.cached_macro_data = fetch_fred_data()
        return self.cached_macro_data
```

**Why Bad:**
- Cannot resume from checkpoint (agent state not in StateGraph)
- Non-deterministic (cache hit vs miss)
- Concurrency bugs (race conditions)

**Good:**
```python
def macro_oracle_agent(state: InvestmentState, config: dict) -> dict:
    # Fetch fresh data every time (or rely on external cache layer)
    macro_data = fetch_fred_data()
    return {"macro_context": macro_data}
```

---

### Anti-Pattern 3: Untyped State

**Bad:**
```python
state = {}  # ❌ Dict with unknown keys
state["intrinic_value"] = 150  # Typo!
```

**Why Bad:**
- Runtime errors (KeyError, None checks everywhere)
- No IDE autocomplete
- Hard to onboard new developers

**Good:**
```python
from typing import TypedDict

class InvestmentState(TypedDict):
    intrinsic_value: float  # ✅ Typed, IDE catches typos
```

---

### Anti-Pattern 4: Business Logic in Routing Functions

**Bad:**
```python
def should_trigger_hitl(state: InvestmentState) -> str:
    # ❌ Complex EPV calculation in routing function
    normalized_earnings = state["net_income"] / (1 + state["cyclical_adj"])
    epv = normalized_earnings / state["wacc"]
    margin = (epv - state["price"]) / epv

    if margin > 0.3:
        return "optimizer"
    else:
        return "hitl_gate"
```

**Why Bad:**
- Calculation not logged (routing functions not audited)
- Cannot unit test business logic separately
- Duplicates logic from Value Hunter agent

**Good:**
```python
def should_trigger_hitl(state: InvestmentState) -> str:
    # ✅ Simple boolean check on state field
    margin = state["margin_of_safety"]  # Already calculated by agent
    return "hitl_gate" if margin < 0.3 else "optimizer"
```

---

### Anti-Pattern 5: Synchronous External API Calls in Graph

**Bad:**
```python
def value_hunter_agent(state, config):
    data = requests.get("https://api.example.com/fundamentals")  # ❌ Blocks graph
    return {"fundamentals": data.json()}
```

**Why Bad:**
- Blocks entire graph during API call
- Cannot parallelize agents if they're waiting on I/O
- Timeout kills entire analysis

**Good (Option 1: Async):**
```python
async def value_hunter_agent(state, config):
    async with httpx.AsyncClient() as client:
        data = await client.get("https://api.example.com/fundamentals")
    return {"fundamentals": data.json()}
```

**Good (Option 2: Pre-fetch):**
```python
# Fetch all data upfront in a single node, then route to agents
def data_fetcher_node(state, config):
    ticker = state["ticker"]
    fundamentals = fetch_fundamentals(ticker)
    macro = fetch_macro_data()
    return {"fundamentals": fundamentals, "macro_data": macro}

# Agents read from state (no external calls)
def value_hunter_agent(state, config):
    fundamentals = state["fundamentals"]
    return {"intrinsic_value": calculate_epv(fundamentals)}
```

---

## 8. Open Questions & Validation Needed

1. **LangGraph API specifics:**
   - Confirm current syntax for `add_conditional_edges` (may have changed post-training cutoff)
   - Verify `PostgresSaver` configuration (connection pooling, performance)
   - Test async agent support (is `async def agent(state, config)` supported?)

2. **Checkpointing performance:**
   - Benchmark state serialization time (large state with 10+ agents)
   - Determine if state size limits exist (10KB? 100KB?)

3. **HITL interrupt mechanism:**
   - Confirm `interrupt_before=["node_name"]` syntax
   - Test state updates during pause (`app.update_state()`)

4. **Parallel execution:**
   - Verify thread safety of shared state
   - Test race conditions with parallel agents writing to same key

5. **Streaming updates:**
   - Can LangGraph stream intermediate state to frontend (WebSockets)?
   - Syntax for `app.stream()` vs `app.invoke()`

---

## 9. Recommended File Structure

```
lockin/
├── .planning/                      # Project planning docs (already exists)
├── src/
│   ├── agents/                     # Agent implementations
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseAgent interface
│   │   ├── layer1/
│   │   │   ├── macro_oracle.py
│   │   │   └── sentiment.py
│   │   ├── layer2/
│   │   │   ├── value_hunter.py
│   │   │   └── strategist.py
│   │   ├── layer3/
│   │   │   ├── bear.py
│   │   │   ├── historian.py
│   │   │   └── guardian.py
│   │   ├── layer4/
│   │   │   ├── judge.py
│   │   │   └── optimizer.py
│   │   └── layer5/
│   │       └── trader.py
│   ├── graph/                      # LangGraph orchestration
│   │   ├── __init__.py
│   │   ├── state.py                # InvestmentState TypedDict
│   │   ├── workflow.py             # StateGraph definition
│   │   └── routing.py              # Conditional edge functions
│   ├── data/                       # Data layer
│   │   ├── __init__.py
│   │   ├── market_data.py          # yfinance, Alpha Vantage
│   │   ├── macro_data.py           # FRED API
│   │   ├── cache.py                # Fallback cache
│   │   └── validators.py           # Data quality checks
│   ├── rag/                        # Knowledge base RAG
│   │   ├── __init__.py
│   │   ├── ingest.py               # Load PDFs, chunk, embed
│   │   ├── retrieval.py            # Query vector store
│   │   └── evaluation.py           # RAGAs validation
│   ├── backtesting/                # Simulation
│   │   ├── __init__.py
│   │   ├── engine.py               # vectorbt integration
│   │   └── metrics.py              # Sharpe, drawdown, etc.
│   ├── db/                         # Database layer
│   │   ├── __init__.py
│   │   ├── models.py               # SQLAlchemy models
│   │   └── checkpointer.py         # PostgresSaver config
│   ├── ui/                         # Streamlit dashboard
│   │   ├── __init__.py
│   │   ├── app.py                  # Main Streamlit app
│   │   ├── components/
│   │   │   ├── reasoning_viewer.py
│   │   │   ├── hitl_approval.py
│   │   │   └── agent_activity.py
│   │   └── utils.py
│   └── config.py                   # Settings (API keys, thresholds)
├── tests/
│   ├── agents/                     # Unit tests per agent
│   ├── graph/                      # Integration tests for workflow
│   ├── data/                       # Data layer tests
│   └── conftest.py                 # Pytest fixtures
├── knowledge_base/                 # PDFs, books (not in git)
│   ├── graham_intelligent_investor.pdf
│   ├── dalio_principles.pdf
│   └── ...
├── pyproject.toml                  # Dependencies
├── README.md
└── .env                            # API keys (not in git)
```

---

## 10. Summary: What Roadmap Should Prioritize

### Critical Architectural Decisions (Phase 1)

1. **State Schema Design** — locks in all agent interfaces
2. **Checkpointing Strategy** — enables HITL and auditability
3. **Error Handling Philosophy** — fallback vs fail-fast

### Build Order (Phases 2-6)

1. **Foundation** → State + basic graph + checkpointing
2. **Vertical Slice** → Layer 1 end-to-end (proves architecture)
3. **Core Differentiation** → Dialectical debate (Layers 2-4)
4. **Execution** → Portfolio management (Layers 4-5)
5. **Validation** → Backtesting (proves it works)
6. **Interface** → Explainability UI (makes it usable)

### Performance Optimization (Defer to Post-MVP)

- Async agents
- Parallel layer execution
- Caching strategies
- Streaming updates

---

**Last Updated:** 2026-02-01
**Researcher Confidence:** HIGH (patterns), MEDIUM (LangGraph API specifics)
