# Phase 1: Foundation - Research

**Researched:** 2026-02-20
**Domain:** LangGraph 1.0.9 StateGraph, PostgreSQL checkpointing, HITL patterns
**Confidence:** HIGH (verified against installed source code + official docs)

## Summary

This phase establishes the LangGraph orchestration infrastructure for the LockIn investment swarm. The stack is already installed and the database is already provisioned — the research focus is on exact API usage for LangGraph 1.0.9 to avoid breaking changes from pre-1.0 patterns documented elsewhere.

LangGraph 1.0.9 has breaking changes from the 0.x series: `config_schema` is deprecated in favor of `context_schema`, `input`/`output` parameters renamed to `input_schema`/`output_schema`. The HITL pattern uses `interrupt()` (a function, not a decorator) plus `Command(resume=...)` — the node re-executes from the top on resume, which has critical implications for audit logging. PostgresSaver 3.0.4 with psycopg 3.3.3 uses `from_conn_string()` as a context manager and requires `autocommit=True` + `row_factory=dict_row` on manual connections.

The audit trail must be implemented as a node wrapper (decorator pattern) rather than LangGraph callbacks, since callback hooks require LangSmith integration. Every node write goes through a custom `audit_node()` function that logs before/after to the `audit_logs` table that already exists in Supabase.

**Primary recommendation:** Implement the graph in `src/lockin/graph/investment_graph.py`, wrap every agent node with an `audit_node()` function in `src/lockin/utils/audit.py`, and use `InMemorySaver` for all tests — swapping to `PostgresSaver` only in the `create_graph()` factory function for production runs.

## Standard Stack

### Core (all already installed in .venv)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.0.9 | StateGraph orchestration | Already installed, project decision |
| langgraph-checkpoint-postgres | 3.0.4 | PostgreSQL checkpointing | Already installed, project decision |
| langgraph-checkpoint | 4.0.0 | Base checkpoint interfaces (InMemorySaver) | Transitive dependency, auto-installed |
| psycopg | 3.3.3 | PostgreSQL driver (psycopg3) | Required by PostgresSaver |
| psycopg-pool | 3.3.0 | Connection pooling | Installed, use for production connections |
| pydantic | 2.12.5 | Validation | Already installed |
| langchain-google-genai | 4.2.1 | Gemini LLM calls | Already installed, project decision |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.x | Unit + integration tests | All testing |
| pytest-asyncio | 0.24.x | Async test support | Not needed for Phase 1 (sync graph) |
| python-dotenv | 1.0.x | Load .env credentials | Entry points and tests |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PostgresSaver (sync) | AsyncPostgresSaver | Async is better for FastAPI/web; sync is simpler for scripts and tests. Use sync for Phase 1. |
| Custom audit wrapper | LangSmith callbacks | LangSmith requires API key + external service. Custom wrapper keeps audit in Supabase alongside checkpoints — matches project constraint of staying on free tier. |
| TypedDict for state | Pydantic BaseModel | TypedDict is natively supported with no extra overhead. Pydantic adds validation but requires different graph setup. Use TypedDict. |

**Installation:** Already complete. Stack is installed in `/home/mateo/dev/LockIn/.venv`.

## Architecture Patterns

### Recommended Project Structure

```
src/lockin/
├── graph/
│   ├── __init__.py
│   ├── investment_graph.py    # StateGraph definition, compile(), factory function
│   ├── state.py               # InvestmentState TypedDict
│   └── routing.py             # Conditional edge routing functions
├── agents/
│   ├── __init__.py
│   ├── macro_oracle.py        # Macro regime detection agent
│   ├── value_hunter.py        # Bull valuation agent
│   ├── bear.py                # Bear devil's advocate agent
│   ├── strategist.py          # VeTO qualitative agent
│   ├── guardian.py            # Risk veto agent
│   ├── judge.py               # Bayesian synthesis + HITL trigger
│   └── optimizer.py           # Portfolio construction agent
└── utils/
    ├── __init__.py
    └── audit.py               # audit_node() wrapper, log_to_db()

tests/
├── unit/
│   ├── test_state.py          # InvestmentState construction/validation
│   ├── test_routing.py        # Conditional edge routing functions
│   └── test_agents_mock.py    # Individual mock agent nodes
└── integration/
    └── test_graph_e2e.py      # End-to-end: watchlist → mock agents → output
```

### Pattern 1: InvestmentState TypedDict

**What:** Define the shared state schema as a `TypedDict`. Nodes return partial dicts (only changed fields). LangGraph merges via LastValue (default: overwrite).

**When to use:** For all scalar and dict/list fields that are written by exactly one node. Use `Annotated[list, operator.add]` only for fields accumulated across multiple nodes (e.g., `citations`).

```python
# Source: Verified from langgraph/graph/state.py + langgraph/types.py source
# File: src/lockin/graph/state.py
from typing import Annotated
from typing_extensions import TypedDict
import operator

class InvestmentState(TypedDict):
    # Inputs
    request_id: str
    timestamp: str
    asset_ticker: str

    # Macro Oracle outputs
    macro_regime: dict
    macro_confidence: float
    macro_narrative: str

    # Bull agent outputs
    bull_iteration: int
    bull_valuation_distribution: dict  # {mean, median, std_dev, P10, P90}
    bull_thesis: str
    bull_refined_thesis: str
    bull_defense: str
    bull_confidence: float
    quality_metrics: dict

    # Bear agent outputs
    bear_challenges: list
    bear_valuation_distribution: dict
    bear_thesis: str
    bear_red_flags: list
    bear_conviction: float

    # Strategist outputs
    strategist_veto: float
    strategist_sentiment: float
    strategic_signals: dict
    strategist_narrative: str
    strategist_confidence: float

    # Guardian outputs
    guardian_risk_report: dict
    guardian_veto: bool
    guardian_veto_reason: str
    guardian_sizing: float
    guardian_margin_adjustments: dict

    # Judge outputs
    judge_consensus_distribution: dict
    judge_recommendation: str  # BUY|HOLD|PASS
    judge_conviction: float
    judge_margin: float
    judge_price_target: float
    judge_narrative: str
    judge_hitl: bool
    judge_hitl_reason: str

    # Optimizer outputs
    optimizer_portfolio: dict
    optimizer_sectors: dict
    optimizer_rebalancing: list
    optimizer_metrics: dict
    optimizer_narrative: str

    # Cross-cutting
    citations: Annotated[list, operator.add]  # Accumulated from multiple agents
    human_review: dict
```

**Key insight:** `citations` uses `Annotated[list, operator.add]` because multiple agents append to it. All other fields use default `LastValue` (last write wins). This is correct — do not add `operator.add` to fields written by only one node.

### Pattern 2: StateGraph Construction

**What:** Build the graph as a factory function, not a module-level singleton. This enables testing with different checkpointers.

```python
# Source: Verified from langgraph/graph/__init__.py and langgraph/graph/state.py source
# File: src/lockin/graph/investment_graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import interrupt, Command

from lockin.graph.state import InvestmentState
from lockin.graph.routing import route_bull_bear, route_guardian, route_judge_hitl
from lockin.agents.macro_oracle import macro_oracle_node
from lockin.agents.value_hunter import value_hunter_node
# ... other agents

def build_graph(checkpointer=None):
    """Factory function — pass InMemorySaver for tests, PostgresSaver for production."""
    builder = StateGraph(InvestmentState)

    # Add nodes
    builder.add_node("macro_oracle", macro_oracle_node)
    builder.add_node("value_hunter", value_hunter_node)
    builder.add_node("bear", bear_node)
    builder.add_node("strategist", strategist_node)
    builder.add_node("guardian", guardian_node)
    builder.add_node("judge", judge_node)
    builder.add_node("optimizer", optimizer_node)

    # Linear edges
    builder.add_edge(START, "macro_oracle")
    builder.add_edge("macro_oracle", "value_hunter")
    builder.add_edge("value_hunter", "bear")

    # Conditional: Bull-Bear loop (route back to value_hunter if iteration < max)
    builder.add_conditional_edges("bear", route_bull_bear)

    # After dialectic converges → Strategist → Guardian
    builder.add_edge("strategist", "guardian")

    # Conditional: Guardian veto (route to END if guardian_veto=True)
    builder.add_conditional_edges("guardian", route_guardian)

    # Judge → conditional HITL
    builder.add_edge("judge", "optimizer")  # HITL handled inside judge node with interrupt()
    builder.add_edge("optimizer", END)

    return builder.compile(checkpointer=checkpointer)
```

### Pattern 3: Conditional Edge Routing Functions

**What:** Routing functions receive the full state, return a string (node name or END constant).

```python
# Source: Verified from langgraph/graph/state.py and official docs
# File: src/lockin/graph/routing.py
from langgraph.graph import END
from lockin.graph.state import InvestmentState

MAX_BULL_BEAR_ITERATIONS = 3

def route_bull_bear(state: InvestmentState) -> str:
    """Route back to value_hunter if more dialectic needed, else continue."""
    if state.get("bull_iteration", 0) < MAX_BULL_BEAR_ITERATIONS:
        return "value_hunter"   # Bull refines thesis again
    return "strategist"         # Dialectic complete, move on

def route_guardian(state: InvestmentState) -> str:
    """If Guardian vetoed, terminate. Otherwise continue to Judge."""
    if state.get("guardian_veto", False):
        return END
    return "judge"

# Note: HITL is handled INSIDE judge_node with interrupt(), not as a conditional edge.
# The judge node pauses and resumes in-place.
```

### Pattern 4: HITL with interrupt() Inside a Node

**What:** The `interrupt()` function pauses the graph inside a node. On resume, the entire node re-runs from the top — the `interrupt()` call returns the human's input on the second execution.

**Critical rule:** Do NOT place DB writes, API calls, or side effects before `interrupt()`. The node re-executes on resume and those side effects would run twice.

```python
# Source: Verified from langgraph/types.py source code (interrupt function, lines 420-543)
# File: src/lockin/agents/judge.py
from langgraph.types import interrupt
from lockin.graph.state import InvestmentState
from lockin.utils.audit import audit_node

HITL_CONVICTION_THRESHOLD = 0.5

def judge_node(state: InvestmentState) -> dict:
    """Bayesian synthesis. Triggers HITL if conviction below threshold."""
    # 1. Perform Bayesian synthesis (mock in Phase 1)
    recommendation = "BUY"
    conviction = 0.45  # Mock low conviction → triggers HITL
    judge_hitl = conviction < HITL_CONVICTION_THRESHOLD

    if judge_hitl:
        # HITL: pause and surface to human
        # interrupt() raises GraphInterrupt on first call.
        # On resume, returns whatever value was passed to Command(resume=...)
        human_decision = interrupt({
            "question": "Low conviction recommendation. Approve or override?",
            "recommendation": recommendation,
            "conviction": conviction,
            "asset_ticker": state["asset_ticker"],
        })
        # human_decision is the value passed by Command(resume=human_decision)
        # Update recommendation based on human input
        if isinstance(human_decision, dict):
            recommendation = human_decision.get("override_recommendation", recommendation)

    return {
        "judge_recommendation": recommendation,
        "judge_conviction": conviction,
        "judge_hitl": judge_hitl,
        "judge_hitl_reason": f"Conviction {conviction:.0%} below threshold" if judge_hitl else "",
        # ... other judge fields
    }
```

**How to resume:**
```python
# Client code to resume after interrupt
from langgraph.types import Command

config = {"configurable": {"thread_id": "analysis-AAPL-001"}}

# First invocation: runs until interrupt
result = graph.invoke(initial_state, config=config)
# result["__interrupt__"] contains the interrupt payload

# Human reviews, then resumes:
human_input = {"override_recommendation": "HOLD"}
graph.invoke(Command(resume=human_input), config=config)
```

### Pattern 5: PostgresSaver Setup

**What:** PostgresSaver 3.0.4 is a context manager via `from_conn_string()`. The `setup()` call creates checkpoint tables (already done — tables exist in Supabase). Use `from_conn_string()` for sync, `AsyncPostgresSaver` for async.

```python
# Source: Verified from installed source code:
# .venv/lib/python3.12/site-packages/langgraph/checkpoint/postgres/__init__.py lines 54-75
from langgraph.checkpoint.postgres import PostgresSaver

# Connection string format for Supabase (session mode pooler):
# postgres://postgres.PROJECT_ID:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
# Note: Transaction mode (port 6543) does NOT support prepared statements — use session mode (5432)

DB_URI = "postgresql://postgres.YOUR_PROJECT:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

# Context manager pattern (from_conn_string handles autocommit=True and row_factory=dict_row internally):
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    # setup() only needed on FIRST run — tables already exist in Supabase
    # checkpointer.setup()  # Skip if tables already created
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "analysis-AAPL-001"}}
    result = graph.invoke(initial_state, config=config)
```

**For tests — use InMemorySaver:**
```python
# Source: Verified from langgraph/checkpoint/memory/__init__.py
from langgraph.checkpoint.memory import InMemorySaver

def test_graph_e2e():
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-001"}}
    result = graph.invoke(initial_state, config=config)
    assert result["judge_recommendation"] in ["BUY", "HOLD", "PASS"]
```

### Pattern 6: Audit Node Wrapper

**What:** Every agent node is wrapped with an `audit_node()` function that logs pre/post state to the `audit_logs` table. This gives the required audit trail without LangSmith.

```python
# Source: Custom pattern — no LangGraph built-in for custom DB audit logging
# File: src/lockin/utils/audit.py
import datetime
import json
from typing import Callable
from supabase import create_client
from lockin.graph.state import InvestmentState

def audit_node(agent_name: str, node_fn: Callable) -> Callable:
    """Wraps an agent node function to log execution to audit_logs table."""
    def wrapper(state: InvestmentState) -> dict:
        timestamp = datetime.datetime.utcnow().isoformat()

        # Execute the actual agent
        result = node_fn(state)

        # Log post-execution to audit_logs
        _log_audit_event(
            request_id=state.get("request_id", "unknown"),
            asset_ticker=state.get("asset_ticker", "unknown"),
            agent_name=agent_name,
            event_type="node_executed",
            payload={
                "timestamp": timestamp,
                "state_updates": result,  # Only what changed
                "thread_id": state.get("_thread_id"),  # If surfaced
            },
        )
        return result
    wrapper.__name__ = node_fn.__name__
    return wrapper

def _log_audit_event(request_id, asset_ticker, agent_name, event_type, payload):
    """Insert into audit_logs table. Table already exists in Supabase."""
    # Implementation: use psycopg directly or supabase-py client
    # audit_logs schema: id, created_at, request_id, asset_ticker, agent_name,
    #                    event_type, payload JSONB, thread_id, session_id
    pass  # Implement in task
```

**Usage in agent files:**
```python
# File: src/lockin/agents/macro_oracle.py
from lockin.utils.audit import audit_node

def _macro_oracle_impl(state):
    return {"macro_regime": {"type": "bull"}, "macro_confidence": 0.75, "macro_narrative": "Mock"}

macro_oracle_node = audit_node("macro_oracle", _macro_oracle_impl)
```

### Pattern 7: Mock Agent Functions

**What:** Mock agents return valid partial dicts with hard-coded values. Used for Phase 1 end-to-end test before real LLM agents are built.

```python
# File: src/lockin/agents/value_hunter.py (mock implementation for Phase 1)
from lockin.graph.state import InvestmentState

def value_hunter_node(state: InvestmentState) -> dict:
    """Mock Value Hunter — returns dummy valuation data."""
    iteration = state.get("bull_iteration", 0) + 1
    return {
        "bull_iteration": iteration,
        "bull_valuation_distribution": {
            "mean": 150.0,
            "median": 148.0,
            "std_dev": 12.0,
            "P10": 132.0,
            "P90": 170.0,
        },
        "bull_thesis": f"Mock bull thesis (iteration {iteration})",
        "bull_refined_thesis": f"Mock refined thesis (iteration {iteration})",
        "bull_defense": "Mock defense against bear challenges",
        "bull_confidence": 0.72,
        "quality_metrics": {"piotroski_f": 7, "altman_z": 2.8},
        "citations": [{"source": "mock", "claim": "Mock citation"}],
    }
```

### Anti-Patterns to Avoid

- **Side effects before interrupt():** Any code before `interrupt()` re-runs on resume. Don't write to DB, call APIs, or send emails before `interrupt()`. Move all side effects to after the interrupt value is received.
- **Missing thread_id in config:** Every `invoke()` call must include `{"configurable": {"thread_id": "..."}}` when using a checkpointer. Without it, checkpointing silently fails.
- **Using recursion_limit as control flow:** Don't rely on the default recursion limit (25) to stop the Bull-Bear loop. Use explicit routing logic in `route_bull_bear()` that returns "strategist" after max iterations.
- **Parallel branches without reducers:** If two nodes run in parallel (same superstep) and both write to the same state field, LangGraph raises `InvalidUpdateError`. In this graph, nodes run sequentially — not an issue unless you add parallel execution.
- **Calling setup() every time:** `PostgresSaver.setup()` runs migrations. Tables already exist in Supabase. Only call once on first deployment. Subsequent calls are safe (idempotent) but add startup latency.
- **Transaction mode pooler connection:** Supabase's transaction mode (port 6543) does not support prepared statements. Use session mode (port 5432) for LangGraph checkpointing.
- **Using config_schema in LangGraph 1.0.9:** This parameter is deprecated. Use `context_schema` for run-scoped immutable context. Using the old param emits `LangGraphDeprecatedSinceV10` warning.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph state persistence | Custom pickle/JSON to DB | PostgresSaver | Handles concurrent writes, migrations, checkpoint history, time-travel |
| HITL pause/resume | Custom flag polling with sleep() | interrupt() + Command | LangGraph's mechanism handles state serialization, resume value matching by index, and node re-execution semantics |
| Graph execution engine | Custom executor loop | graph.invoke() / graph.stream() | Pregel execution model handles supersteps, error recovery, streaming output |
| Test checkpointing | SQLite or custom dict | InMemorySaver | Already available, zero setup, perfect for tests |
| Connection pooling | Custom pool manager | psycopg_pool.ConnectionPool | Thread-safe, already installed |
| Checkpoint table schema | Custom migration script | checkpointer.setup() | LangGraph manages its own schema (checkpoint_migrations, checkpoints, checkpoint_blobs, checkpoint_writes tables already exist) |

**Key insight:** LangGraph's checkpoint protocol is the core infrastructure. Bypassing it with custom solutions loses time-travel debugging, interrupt persistence across restarts, and checkpoint history browsing.

## Common Pitfalls

### Pitfall 1: Node Re-execution on Resume is Surprising

**What goes wrong:** Developer places an audit log write before `interrupt()`. On resume, the node re-executes from the top — the audit write fires a second time, creating duplicate entries.

**Why it happens:** LangGraph's resume mechanism re-runs the entire node function. The `interrupt()` call detects "we're resuming" and returns the stored resume value instead of raising `GraphInterrupt`. Everything before `interrupt()` runs again.

**How to avoid:** Structure `judge_node` so ALL side effects (DB writes, audit logs) happen AFTER the interrupt value is received:
```python
def judge_node(state):
    # SAFE: pure computation only before interrupt
    conviction = compute_conviction(state)
    should_hitl = conviction < THRESHOLD

    if should_hitl:
        human_decision = interrupt({"conviction": conviction})  # May run twice
        # Side effects AFTER interrupt (only runs once — on second execution when returning)
        result = apply_human_decision(human_decision)
    else:
        result = default_decision(state)

    audit_log(result)  # Safe: only runs after interrupt resolves
    return result
```

**Warning signs:** Duplicate audit log entries for the judge node; DB write errors on resume.

### Pitfall 2: Missing thread_id Silently Skips Checkpointing

**What goes wrong:** Graph runs without errors but HITL doesn't work — interrupts don't persist, can't be resumed.

**Why it happens:** When `thread_id` is missing from the config, LangGraph creates a new thread for each invocation. The interrupted state is not findable when `Command(resume=...)` is called.

**How to avoid:** Always pass thread_id:
```python
config = {"configurable": {"thread_id": f"analysis-{ticker}-{request_id}"}}
result = graph.invoke(state, config=config)
```

**Warning signs:** `interrupt()` fires but `Command(resume=...)` starts a fresh run instead of resuming; graph output has no `__interrupt__` key.

### Pitfall 3: Bull-Bear Routing Creates Infinite Loop

**What goes wrong:** `route_bull_bear` always returns "value_hunter", graph hits `recursion_limit=25` and raises `GraphRecursionError`.

**Why it happens:** The routing function condition is wrong or `bull_iteration` is never incremented.

**How to avoid:**
1. `value_hunter_node` must always increment `bull_iteration` by 1.
2. `route_bull_bear` must return "strategist" when `bull_iteration >= MAX_BULL_BEAR_ITERATIONS`.
3. Test this explicitly: invoke with a state where `bull_iteration=3`, confirm routing returns "strategist".

**Warning signs:** `GraphRecursionError: Recursion limit of 25 reached`.

### Pitfall 4: PostgresSaver Supabase Transaction Mode Connection Fails

**What goes wrong:** Connection string uses port 6543 (transaction mode pooler). LangGraph's PostgresSaver uses prepared statements internally, which are not supported in transaction mode.

**Why it happens:** Supabase's transaction pooler doesn't support `PREPARE` statements.

**How to avoid:** Use session mode pooler (port 5432) or direct connection:
```
# WRONG (transaction mode):
postgresql://postgres.PROJECT:PASS@aws-0-eu-central-1.pooler.supabase.com:6543/postgres

# CORRECT (session mode pooler or direct):
postgresql://postgres.PROJECT:PASS@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
```

**Warning signs:** `psycopg.errors.FeatureNotSupported: prepared statements are not supported`.

### Pitfall 5: InvestmentState Fields Without Defaults Cause Invoke Errors

**What goes wrong:** `graph.invoke({"request_id": "abc", "asset_ticker": "AAPL"}, ...)` crashes because TypedDict fields without defaults must be provided.

**Why it happens:** LangGraph initializes state from the input dict. Missing required TypedDict fields aren't auto-initialized — they simply don't exist in the state dict. Nodes that `state.get("guardian_veto")` return `None` instead of `False`, breaking boolean checks.

**How to avoid:**
- Use `state.get("guardian_veto", False)` with defaults in all agent reads.
- Or provide a complete initial state in `invoke()` with all fields defaulted.
- Or use `TypedDict` with `total=False` (all fields optional) and rely on `.get()` with defaults.

**Warning signs:** `KeyError` in agent nodes; routing functions behaving incorrectly because a field is `None` instead of `False`.

### Pitfall 6: Audit Logging Blocks the Agent (Sync DB Call in Critical Path)

**What goes wrong:** Each agent waits for the audit DB insert to complete before returning. For 7 agents × multiple tickers, this adds significant latency.

**Why it happens:** Synchronous Supabase insert in the audit wrapper.

**How to avoid for Phase 1:** Log to a list in memory during graph execution, flush to DB after graph completes. Or use fire-and-forget with a background thread. For Phase 1 (mock agents with no real latency), sync logging is acceptable.

**Warning signs:** Graph execution time dominated by DB inserts rather than agent logic.

## Code Examples

### Complete End-to-End Test Structure

```python
# Source: Pattern from LangGraph official testing docs + verified API
# File: tests/integration/test_graph_e2e.py
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from lockin.graph.investment_graph import build_graph

MOCK_INITIAL_STATE = {
    "request_id": "test-req-001",
    "timestamp": "2026-02-20T10:00:00Z",
    "asset_ticker": "AAPL",
    # All other fields absent — agents will populate them
}

def test_graph_e2e_no_veto_no_hitl():
    """Full graph run with mock agents, no veto, no HITL."""
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-001"}}

    result = graph.invoke(MOCK_INITIAL_STATE, config=config)

    assert result["judge_recommendation"] in ["BUY", "HOLD", "PASS"]
    assert "optimizer_portfolio" in result
    assert result["guardian_veto"] is False

def test_graph_guardian_veto_terminates():
    """When guardian vetoes, graph terminates before judge."""
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-002"}}

    # Use a state/mock that triggers guardian veto
    result = graph.invoke({**MOCK_INITIAL_STATE, "asset_ticker": "VETO_TRIGGER"}, config=config)

    assert result["guardian_veto"] is True
    assert "judge_recommendation" not in result or result.get("judge_recommendation") is None

def test_hitl_interrupt_and_resume():
    """HITL: graph pauses at judge, resumes with human input."""
    from langgraph.types import Command
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-003"}}

    # First invoke: should hit interrupt in judge
    first_result = graph.invoke({**MOCK_INITIAL_STATE, "asset_ticker": "LOW_CONVICTION"}, config=config)
    assert "__interrupt__" in first_result

    # Resume with human decision
    human_input = {"override_recommendation": "HOLD"}
    final_result = graph.invoke(Command(resume=human_input), config=config)
    assert final_result["judge_recommendation"] == "HOLD"

def test_individual_node_in_isolation():
    """Test a single node without running the full graph."""
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)

    # Access node directly via graph.nodes dict
    node_result = graph.nodes["macro_oracle"].invoke({
        "request_id": "test-001",
        "asset_ticker": "AAPL",
    })
    assert "macro_regime" in node_result
```

### Conditional Routing with Path Map (Alternative Style)

```python
# Source: Verified from official docs on add_conditional_edges
from langgraph.graph import END

# Style 1: Return string directly (preferred for clarity)
def route_guardian(state) -> str:
    return END if state.get("guardian_veto") else "judge"

# Style 2: Return bool, use path_map (equivalent)
def guardian_vetoed(state) -> bool:
    return state.get("guardian_veto", False)

builder.add_conditional_edges(
    "guardian",
    guardian_vetoed,
    {True: END, False: "judge"}
)
```

### PostgresSaver in Production Entry Point

```python
# Source: Verified from PostgresSaver source + Supabase connection docs
# File: src/lockin/graph/investment_graph.py
import os
from dotenv import load_dotenv

def run_analysis(ticker: str, request_id: str) -> dict:
    """Production entry point — uses PostgresSaver."""
    load_dotenv()
    db_uri = os.environ["DATABASE_URL"]

    with PostgresSaver.from_conn_string(db_uri) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": f"analysis-{ticker}-{request_id}"}}
        initial_state = {
            "request_id": request_id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "asset_ticker": ticker,
        }
        return graph.invoke(initial_state, config=config)
```

### Streaming for Progress Monitoring

```python
# Source: Verified from langgraph/types.py StreamMode enum
# stream_mode="updates" emits node name + partial state after each node
for event in graph.stream(initial_state, config=config, stream_mode="updates"):
    node_name, updates = next(iter(event.items()))
    print(f"[{node_name}] completed")
    # Useful for Streamlit progress indicators in later phases
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `StateGraph(state_schema, config_schema=...)` | `StateGraph(state_schema, context_schema=...)` | LangGraph 1.0 | `config_schema` raises deprecation warning |
| `interrupt_before=["node"]` at compile (breakpoints) | `interrupt()` inside node body | LangGraph 0.2.x | More flexible — interrupt at any point in node logic, not just at node boundary |
| `graph.invoke(input, input_schema=...)` | `input_schema` param at `StateGraph()` constructor | LangGraph 1.0 | Define input/output narrowing at graph definition time |
| `langchain_postgres.PostgresSaver` | `langgraph.checkpoint.postgres.PostgresSaver` | v2.0 of checkpoint | Two separate packages — make sure to import from `langgraph.checkpoint.postgres`, NOT `langchain_postgres` |

**Deprecated/outdated:**
- `MessageGraph`: Use `StateGraph` with custom state. `MessageGraph` only handles message-list state.
- `GraphInterrupt` as user-catchable exception: Do NOT wrap `interrupt()` in try/except — it relies on raising `GraphInterrupt` internally.
- `interrupt_before` / `interrupt_after` at compile for HITL: These are debugging breakpoints, not the production HITL pattern. Use `interrupt()` inside node body for real HITL.
- `langgraph_checkpoint_postgres` old import path (`langchain_postgres.checkpoint`): Wrong package. Use `langgraph.checkpoint.postgres`.

## Open Questions

1. **Audit log thread_id access inside nodes**
   - What we know: LangGraph passes config via `RunnableConfig`. The `thread_id` lives in `config["configurable"]["thread_id"]`, not in the state dict.
   - What's unclear: The cleanest way to access `config` inside a node. LangGraph 1.0.9 may support passing config as a second argument to node functions (need to verify exact signature).
   - Recommendation: For Phase 1, generate `thread_id` externally before invoking and include it in the initial state dict as a convenience field. This avoids needing config injection in the audit wrapper.

2. **Supabase audit_logs insert reliability**
   - What we know: The `audit_logs` table exists with correct schema. Supabase free tier has rate limits.
   - What's unclear: Whether direct psycopg inserts or supabase-py client inserts are more reliable for audit logging given the connection already used by PostgresSaver.
   - Recommendation: Use a separate psycopg connection for audit logs (not the same connection as PostgresSaver) to avoid transaction conflicts. Or batch-write audit events after graph completion.

3. **Bull-Bear loop: minimum 1 iteration guarantee**
   - What we know: The routing function returns "value_hunter" if `bull_iteration < MAX`. The flow is value_hunter → bear → route_bull_bear.
   - What's unclear: How to guarantee minimum 1 iteration when bear runs first. If `bull_iteration=0` after first bear run, route sends back to value_hunter for a second pass.
   - Recommendation: Initialize `bull_iteration=0` in initial state. After first value_hunter runs, it becomes 1. After first bear runs, route checks `bull_iteration < MAX_BULL_BEAR_ITERATIONS` (e.g., 2 total iterations). With MAX=2: iteration 1 routes to strategist after bear's first challenge. This gives exactly 1 bull-bear exchange (minimum 1 back-and-forth as required).

## Sources

### Primary (HIGH confidence)

- Installed source code: `/home/mateo/dev/LockIn/.venv/lib/python3.12/site-packages/langgraph/types.py` — `interrupt()` function, `Command` class, `Interrupt` class verified line-by-line
- Installed source code: `/home/mateo/dev/LockIn/.venv/lib/python3.12/site-packages/langgraph/graph/state.py` — `StateGraph.__init__()`, `add_node()` signatures
- Installed source code: `/home/mateo/dev/LockIn/.venv/lib/python3.12/site-packages/langgraph/checkpoint/postgres/__init__.py` — `PostgresSaver.from_conn_string()`, `setup()`, connection requirements (autocommit=True, row_factory=dict_row)
- Installed source code: `/home/mateo/dev/LockIn/.venv/lib/python3.12/site-packages/langgraph/graph/__init__.py` — confirmed exports: `StateGraph`, `START`, `END`, `add_messages`, `MessagesState`
- PyPI page: https://pypi.org/project/langgraph-checkpoint-postgres/ — version 3.0.4, released 2026-01-31

### Secondary (MEDIUM confidence)

- Official LangGraph interrupts docs (https://docs.langchain.com/oss/python/langgraph/interrupts) — interrupt pattern, Command(resume=...), verified against source code
- Official LangGraph testing docs (https://docs.langchain.com/oss/python/langgraph/test) — InMemorySaver for tests, graph.nodes["node"].invoke() for isolation tests
- Official add_conditional_edges docs — routing function pattern, path_map, END routing

### Tertiary (LOW confidence)

- WebSearch: Supabase session mode vs transaction mode pooler — port 5432 vs 6543 behavior re: prepared statements. Verified via Supabase docs that transaction mode (6543) doesn't support prepared statements, but not explicitly verified that PostgresSaver uses prepared statements. Use session mode (5432) to be safe.
- WebSearch: Audit trail callback approach — multiple sources confirm LangSmith is the standard observability integration; custom DB audit requires wrapper pattern.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All versions verified from installed .venv site-packages dist-info
- StateGraph API: HIGH — Verified from installed source code, not just documentation
- HITL pattern: HIGH — interrupt() function source code read directly, behavior documented inline
- PostgresSaver setup: HIGH — Source code read directly, autocommit/row_factory requirements confirmed
- Audit trail pattern: MEDIUM — Custom wrapper is the right approach but specific implementation choices (sync vs async, which psycopg connection) need validation during implementation
- Supabase connection mode: MEDIUM — Session mode (5432) is safe choice; transaction mode risk is well-documented

**Research date:** 2026-02-20
**Valid until:** 2026-04-01 (LangGraph moves fast; re-verify before any major version upgrade)
