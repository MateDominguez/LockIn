# Phase 4: Integration & Risk Management - Research

**Researched:** 2026-05-01
**Domain:** LangGraph multi-ticker orchestration, Bayesian synthesis integration, contract testing
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Multi-ticker Orchestration**
- D-01: Shared Macro Oracle — runs once, result shared across all tickers.
- D-02: Parallel fan-out per ticker — each ticker runs Value Hunter → Bear → Strategist → Guardian → Judge concurrently after Macro Oracle.
- D-03: Portfolio-level Optimizer — runs once after all per-ticker Judges complete.
- D-04: Rate limiting via `asyncio.Semaphore` (default: 2 concurrent) + exponential backoff on 429 errors. Gemini Flash only in Phase 4.
- D-05: Multi-provider `get_llm()` factory deferred to Phase 5.

**VeTO Margin Wiring**
- D-06: Symmetric margin adjustment thresholds:
  - VeTO < 0.3 → margin_adjustment = +0.10
  - VeTO < 0.4 → margin_adjustment = +0.05
  - VeTO 0.4–0.7 → margin_adjustment = 0.00
  - VeTO > 0.7 → margin_adjustment = -0.03
  - VeTO > 0.85 → margin_adjustment = -0.05
- D-07: Keep both `variance_adjustment` AND `margin_adjustment` for VeTO.
- D-08: VeTO margin logic lives inline in `strategist.py`.
- D-09: `has_base_rate` stays False for VeTO.
- D-10: VeTO threshold values are provisional; add TODO/future review note.

**Adaptive Margin of Safety**
- D-11: Margin bounds changed from [0.20, 0.70] to [0.15, 0.60].
- D-12: Existing clamp is sufficient — no per-agent caps or weighted sums.
- D-13: Add `margin_breakdown` dict field to `JudgeOutput`.
- D-14: Valuation model accuracy is the long-term fix for margin sizing.

**Integration Test Strategy**
- D-15: Two test layers:
  1. Contract tests (`tests/unit/test_contracts.py`) — zero LLM calls, CI-safe
  2. Live smoke test (`tests/e2e/test_live_smoke.py`) — `@pytest.mark.slow`, excluded from CI
- D-16: Recorded replay E2E deferred to Phase 5+.
- D-17: Smoke test uses structure + golden range assertions (see CONTEXT.md §D-17).
- D-18: If margin/sizing constants change, smoke test golden ranges must be reviewed.

### Claude's Discretion
- Concurrency implementation details for multi-ticker fan-out (asyncio vs threading)
- Exact semaphore limit tuning (start with 2, adjust based on rate limit behavior)
- Contract test fixture generation approach (snapshot from dev runs vs hand-crafted)

### Deferred Ideas (OUT OF SCOPE)
- Multi-provider `get_llm()` factory (DeepSeek R1, Groq, OpenRouter) — Phase 5
- Recorded replay E2E tests — Phase 5+ when prompts stabilize
- VeTO `has_base_rate=True` upgrade — after backtesting
- Insider trading signals and news sentiment for VeTO — v2
- Valuation model accuracy improvement — Phase 5+
- Margin bounds re-calibration based on backtest — Phase 5+
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RISK-01 | Adaptive Margin of Safety (position size limits with configurable 10% cap) | D-11/D-12/D-13: bounds change [0.20,0.70]→[0.15,0.60]; margin_breakdown field; clamp logic in judge_math.py |
| RISK-02 | Guardian Veto Logic (Altman Z<1.8, Beneish M>-1.78, circuit_breaker) | Already implemented in guardian.py; Phase 4 wires it through integration tests |
| RISK-03 | Position Sizing Limits (10% per position, 35% per sector) | MAX_POSITION_SIZE=0.10, MAX_SECTOR_ALLOCATION=0.325 already in optimizer.py |
| RISK-04 | HITL Escalation Triggers (fraud_veto, low conviction, high position size) | judge_with_hitl() in builder.py; p_final<0.40 triggers HITL; circuit_breaker auto-triggers |
| PORTFOLIO-01 | Sector Diversification (max 35% per sector) | MAX_SECTOR_ALLOCATION=0.325 in optimizer.py; multi-ticker Optimizer aggregates across tickers |
| PORTFOLIO-02 | Kelly Criterion Sizing (Kelly/3 = 0.33) | KELLY_FRACTION=0.33 in optimizer.py and judge_math.py |
| PORTFOLIO-03 | Concentration Caps (max 12% per asset per phase description) | Note: CONTEXT.md uses 10% (MAX_POSITION_SIZE=0.10); the phase description says 12% — clarification: spec is 10%, use MAX_POSITION_SIZE from optimizer.py |
</phase_requirements>

---

## Summary

Phase 4 is an integration and wiring phase, not a greenfield implementation. All 7 agents are already individually implemented and tested (170 tests passing in Phase 3). The work is: (1) wire VeTO margin logic into strategist.py that currently has a `margin_adjustment=0.0` placeholder, (2) update two margin constants in judge_math.py, (3) surface the already-computed margin_breakdown into the JudgeOutput dataclass, (4) build an async multi-ticker orchestration wrapper above the single-ticker graph, and (5) write contract tests and a live smoke test.

The codebase is well-structured for this work. The `agent_overrides` dict pattern enables contract tests without LLM calls. The `create_graph()` factory is stable. The math in `judge_math.py` is pure and testable. The risk is low because agents are already proven — the main complexity is the async multi-ticker fan-out and ensuring rate limit handling is robust.

**Primary recommendation:** Execute changes in this order: (1) constants + types changes first (no behavior change, easy to verify), (2) VeTO margin logic in strategist.py (isolated, well-understood thresholds), (3) contract tests against changed code, (4) multi-ticker orchestration wrapper, (5) live smoke test.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| VeTO margin adjustment | Agent (strategist.py) | — | D-08: each modifier agent owns its own adjustment logic inline |
| Margin of safety bounds | Math (judge_math.py) | — | _MARGIN_MIN/_MARGIN_MAX constants; pure math module |
| margin_breakdown field | Types (types.py) + Math (judge_math.py) | — | D-13: add field to JudgeOutput dataclass, surface in Step 7 assembly |
| Multi-ticker orchestration | New orchestration layer (orchestrator.py) | Graph (builder.py) | D-01/D-02/D-03: wrapper above single-ticker graph; Macro Oracle runs once |
| Rate limiting | Orchestration layer | — | D-04: asyncio.Semaphore in multi-ticker wrapper, not inside individual agents |
| Contract tests | tests/unit/test_contracts.py | — | D-15: zero LLM calls, CI-safe; verifies typed contracts |
| Live smoke test | tests/e2e/test_live_smoke.py | — | D-15: real APIs, @pytest.mark.slow, excluded from CI |
| HITL triggers | builder.py (judge_with_hitl) | judge.py | Already wired; Phase 4 ensures integration tests cover it |
| Portfolio-level optimization | optimizer.py | Orchestration layer | D-03: Optimizer receives aggregated per-ticker results |

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | >=0.2.0 | Graph orchestration, StateGraph, interrupt | Project foundation; all agents use it |
| asyncio (stdlib) | Python 3.12 | Multi-ticker fan-out via `asyncio.gather` | No new dep; `asyncio.Semaphore` for rate limiting |
| pytest | >=8.0.0 | Contract tests + smoke tests | Already project standard |
| pytest-asyncio | >=0.24.0 | Async test support for multi-ticker tests | Already in dev deps |
| scipy.stats | >=1.14.0 | Bayesian synthesis (lognormal) | Already in judge_math.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | >=9.0.0 | Exponential backoff on 429 errors | D-04: already in deps, use `@retry` on LLM calls or catch at orchestration layer |
| unittest.mock | stdlib | Test injection without LLM calls | Contract tests use agent_overrides; mock.patch for audit settings |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio.gather + Semaphore | ThreadPoolExecutor | asyncio preferred — LangGraph is async-native; threading adds GIL complexity |
| asyncio.gather + Semaphore | LangGraph map-reduce | Map-reduce requires LangGraph 0.3+ Send API; asyncio wrapper is simpler and already understood |

**Installation:** No new packages needed. All dependencies already in `pyproject.toml`.

---

## Architecture Patterns

### System Architecture Diagram

```
MULTI-TICKER PIPELINE (new orchestration layer)
================================================

[tickers: ["AAPL","MSFT","GOOG",...]]
          |
          v
  [Macro Oracle] ──────────────────────── runs ONCE
          |
          | macro_context (shared)
          |
    asyncio.gather(
      ┌─ [single_ticker_pipeline("AAPL", macro_context, semaphore)] ─┐
      ├─ [single_ticker_pipeline("MSFT", macro_context, semaphore)] ─┤  up to N concurrent
      └─ [single_ticker_pipeline("GOOG", macro_context, semaphore)] ─┘  (semaphore=2)
    )
          |
          | [{ticker: InvestmentState}, ...]
          |
  [Portfolio Optimizer] ─── runs ONCE over all per-ticker results
          |
          v
  [PortfolioResult: {positions, sector_allocations, rebalancing}]


SINGLE-TICKER PIPELINE (existing builder.py graph)
===================================================

  create_graph() with injected macro_context
          |
    [Value Hunter] ──┐
          |          │ dialectic loop (up to 2x)
        [Bear] ──────┘
          |
     [Strategist]  ← VeTO margin logic NOW WIRED HERE (D-06)
          |
     [Guardian]   ← circuit_breaker gate
          |          ├── circuit_breaker=True → END (no judge/optimizer)
          |          └── circuit_breaker=False → [Judge]
      [Judge]     ← Bayesian synthesis; p_final<0.40 → HITL interrupt
          |
    [per-ticker result: InvestmentState]
```

### Recommended Project Structure

```
src/lockin/
├── graph/
│   ├── builder.py          # existing — single-ticker graph (unchanged in Phase 4)
│   ├── state.py            # existing — InvestmentState TypedDict
│   └── orchestrator.py     # NEW — multi-ticker wrapper with Semaphore + fan-out
├── agents/
│   ├── types.py            # MODIFY — add margin_breakdown field to JudgeOutput
│   ├── judge_math.py       # MODIFY — update _MARGIN_MIN/MAX constants, surface margin_breakdown
│   └── strategist.py       # MODIFY — wire VeTO margin_adjustment thresholds (D-06)
tests/
├── unit/
│   └── test_contracts.py   # NEW — contract tests (zero LLM calls)
├── e2e/
│   └── test_live_smoke.py  # NEW — @pytest.mark.slow live smoke test
└── conftest.py             # existing — add slow marker registration
```

### Pattern 1: VeTO Margin Wiring (inline in strategist.py)

**What:** Replace the current `margin_adj = 0.0` no-op with D-06 thresholds.

**When to use:** Whenever veto_score is computed (always in strategist.py).

**Example:**

```python
# Source: CONTEXT.md D-06, D-07, D-08
# VeTO margin adjustment — symmetric, penalty > reward (opacity is a stronger signal)
# TODO: Revisit thresholds after backtest data is available (D-10)
if veto_score < 0.3:
    margin_adj += 0.10   # very opaque
elif veto_score < 0.4:
    margin_adj += 0.05   # poor visibility
elif veto_score > 0.85:
    margin_adj -= 0.05   # very transparent
elif veto_score > 0.7:
    margin_adj -= 0.03   # clear outcomes
# else: 0.40-0.70 range → 0.00 (neutral)

# Variance adjustment stays on its own logic (low VeTO only)
variance_adj = 0.0
if veto_score < 0.4:
    variance_adj += 0.10
```

**Critical ordering note:** The current code sets `margin_adj` from analyst momentum first, then VeTO adjustments ADD to it. Keep additive semantics — both sources accumulate into `margin_adj`.

### Pattern 2: Margin Constants Update (judge_math.py)

**What:** Update `_MARGIN_MIN` and `_MARGIN_MAX` per D-11.

**Example:**

```python
# Source: CONTEXT.md D-11
# Was: _MARGIN_MIN = 0.20, _MARGIN_MAX = 0.70
_MARGIN_MIN = 0.15   # 15% floor — widens lower bound for high-conviction setups
_MARGIN_MAX = 0.60   # 60% ceiling — tightens upper (0.70 was rarely reached)
_MARGIN_BASE = 0.30  # unchanged
```

### Pattern 3: margin_breakdown in JudgeOutput (types.py + judge_math.py)

**What:** Add structured `margin_breakdown` field to JudgeOutput; surface it in Step 7 assembly.

**Example (types.py):**

```python
# Source: CONTEXT.md D-13
@dataclass
class JudgeOutput:
    # ... existing fields ...
    margin_breakdown: dict = field(default_factory=dict)
    # Populated as:
    # {
    #   "base": 0.30,
    #   "oracle": oracle_modifier.margin_adjustment,
    #   "guardian": guardian_modifier.margin_adjustment,
    #   "strategist": strategist_modifier.margin_adjustment,
    #   "raw_total": <sum>,
    #   "clamped": <final clamped value>
    # }
```

**Example (judge_math.py Step 7 — already computed at lines 460-462):**

```python
# Source: CONTEXT.md D-13; existing modifiers_applied dict at lines 460-462
# Surface as structured margin_breakdown field
margin_breakdown = {
    "base": _MARGIN_BASE,
    "oracle": oracle_modifier.margin_adjustment,
    "guardian": guardian_modifier.margin_adjustment,
    "strategist": strategist_modifier.margin_adjustment,
    "raw_total": _MARGIN_BASE + oracle_modifier.margin_adjustment
                 + guardian_modifier.margin_adjustment
                 + strategist_modifier.margin_adjustment,
    "clamped": margin,
}
```

### Pattern 4: Multi-ticker Orchestration (new orchestrator.py)

**What:** Async wrapper that runs Macro Oracle once, fans out per-ticker pipelines with Semaphore, then runs portfolio-level Optimizer.

**Example:**

```python
# Source: CONTEXT.md D-01/D-02/D-03/D-04
import asyncio
from langgraph.checkpoint.memory import MemorySaver
from lockin.graph.builder import create_graph
from lockin.graph.state import create_initial_state

async def analyze_portfolio(
    tickers: list[str],
    max_concurrent: int = 2,
) -> dict:
    """Run multi-ticker pipeline: Macro Oracle once, then parallel per-ticker."""
    semaphore = asyncio.Semaphore(max_concurrent)

    # Step 1: Run Macro Oracle once (shared context)
    macro_graph = create_graph(checkpointer=MemorySaver(),
                               agent_overrides={"value_hunter": ...,  # macro-only run
                                                ...})
    # OR: extract macro_oracle as a standalone call (simpler)
    macro_context = await _run_macro_oracle_standalone(tickers[0])

    # Step 2: Fan-out per ticker
    async def run_ticker(ticker: str) -> dict:
        async with semaphore:
            graph = create_graph(checkpointer=MemorySaver())
            state = create_initial_state(ticker)
            # Inject pre-computed macro context
            state.update(macro_context)
            return await asyncio.to_thread(
                graph.invoke,
                state,
                {"configurable": {"thread_id": f"portfolio-{ticker}"}},
            )

    ticker_results = await asyncio.gather(
        *[run_ticker(t) for t in tickers],
        return_exceptions=True,
    )

    # Step 3: Portfolio-level optimization
    return _run_portfolio_optimizer(ticker_results)
```

**Implementation note on asyncio.to_thread:** LangGraph `graph.invoke()` is synchronous. Use `asyncio.to_thread()` to run it in a thread pool executor without blocking the event loop, while still controlling concurrency via the Semaphore.

**Rate limit handling (tenacity):**

```python
# Source: CONTEXT.md D-04; tenacity already in pyproject.toml
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def _is_rate_limit_error(exc: Exception) -> bool:
    return "429" in str(exc) or "quota" in str(exc).lower()

@retry(
    retry=retry_if_exception(_is_rate_limit_error),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
)
def _invoke_graph_with_retry(graph, state, config):
    return graph.invoke(state, config)
```

### Pattern 5: Contract Tests (tests/unit/test_contracts.py)

**What:** Verify real agent output contracts match typed dataclasses; zero LLM calls.

**When to use:** CI — runs on every commit.

**Example:**

```python
# Source: CONTEXT.md D-15; existing test_full_pipeline.py pattern
import pytest
from lockin.agents.types import ConfidenceModifier, JudgeOutput, ValueDistribution
from lockin.agents.judge_math import (
    run_judge_algorithm, _MARGIN_MIN, _MARGIN_MAX, _MARGIN_BASE
)

def test_margin_bounds_updated():
    """D-11: Verify bounds are [0.15, 0.60] (not old [0.20, 0.70])."""
    assert _MARGIN_MIN == 0.15
    assert _MARGIN_MAX == 0.60

def test_veto_margin_low():
    """D-06: VeTO < 0.3 adds +0.10 to margin_adjustment."""
    mod = _make_strategist_modifier_with_veto(veto_score=0.25)
    assert mod.margin_adjustment >= 0.10  # analyst could add too

def test_judge_output_has_margin_breakdown():
    """D-13: JudgeOutput must include margin_breakdown dict with all 3 agent keys."""
    output = run_judge_algorithm(...)
    assert "oracle" in output.margin_breakdown
    assert "guardian" in output.margin_breakdown
    assert "strategist" in output.margin_breakdown
    assert "clamped" in output.margin_breakdown

def test_margin_clamp_respects_new_bounds():
    """D-11/D-12: Stacked adjustments clamp to [0.15, 0.60]."""
    # All agents signaling caution: oracle+0.10, guardian+0.30, strategist+0.10+0.05
    output = run_judge_algorithm(... extreme_modifiers ...)
    assert 0.15 <= output.margin_of_safety <= 0.60
```

### Pattern 6: Live Smoke Test (tests/e2e/test_live_smoke.py)

**What:** Single-ticker full pipeline run with real APIs; structure + golden range assertions.

**Example:**

```python
# Source: CONTEXT.md D-17
import os
import pytest
from lockin.graph.builder import create_graph
from lockin.graph.state import create_initial_state
from langgraph.checkpoint.memory import MemorySaver

SMOKE_TICKER = os.getenv("SMOKE_TICKER", "AAPL")

@pytest.mark.slow
def test_live_single_ticker_smoke():
    """Full pipeline run with real APIs. Excluded from CI (pytest.mark.slow)."""
    graph = create_graph(checkpointer=MemorySaver())
    state = create_initial_state(SMOKE_TICKER)
    result = graph.invoke(state, {"configurable": {"thread_id": f"smoke-{SMOKE_TICKER}"}})

    # Structure assertions
    assert result.get("judge_recommendation") in ("BUY", "HOLD", "PASS")
    assert result.get("judge_conviction") is not None
    assert result.get("optimizer_portfolio")  # non-empty
    assert result.get("bull_thesis")  # non-empty string
    assert result.get("bear_thesis")  # non-empty string

    # Golden range assertions
    # NOTE: If margin/sizing constants change (D-18), review these ranges
    # Source constants: _MARGIN_MIN=0.15, _MARGIN_MAX=0.60 in judge_math.py
    assert 0.0 <= result["judge_conviction"] <= 1.0
    assert 0.15 <= result["judge_margin"] <= 0.60
    assert 0.0 <= result.get("optimizer_metrics", {}).get("position_size", 0) <= 0.10

    # Typed output is present
    judge_out = result.get("judge_output")
    assert judge_out is not None
    assert hasattr(judge_out, "margin_breakdown")
    assert "oracle" in judge_out.margin_breakdown

    # VeTO wired: strategist_modifier must have margin_adjustment != None
    strat_mod = result.get("strategist_modifier")
    assert strat_mod is not None
    assert 0.0 <= result.get("strategist_veto", 0.5) <= 1.0
```

### Anti-Patterns to Avoid

- **Separate Macro Oracle call per ticker:** D-01 explicitly requires a single shared macro context. Running macro_oracle N times wastes API quota and produces inconsistent regime signals across tickers.
- **Blocking the event loop with graph.invoke():** Use `asyncio.to_thread()` — `graph.invoke()` is synchronous. Calling it directly in an async context blocks the event loop and defeats the concurrency design.
- **Adding margin_adjustment in Judge instead of Strategist:** D-08 locks VeTO margin logic to strategist.py. Judge must not compute VeTO adjustments — it only accumulates what modifier agents produce.
- **Changing the margin clamp to per-agent caps:** D-12 explicitly rejects this. The global clamp `[0.15, 0.60]` is the correct behavior when all agents signal caution simultaneously.
- **Using asyncio.gather return_exceptions=False:** A single ticker failure would cancel all others. Always use `return_exceptions=True` and handle per-ticker errors gracefully.
- **Hardcoding macro context injection by overwriting state fields directly:** Prefer creating initial state with pre-populated macro fields, or run a graph with only macro_oracle active. Avoid mutating state dicts directly after creation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exponential backoff on 429 | Custom sleep/retry loop | `tenacity` (already in deps) | Handles jitter, max retries, exception filtering |
| Async concurrency control | Custom semaphore logic | `asyncio.Semaphore` (stdlib) | Battle-tested, composable with asyncio.gather |
| Bayesian log-normal pooling | Custom math | `judge_math.py:run_judge_algorithm()` | Pure, 35 tests, Phase 3 complete |
| Kelly Criterion | Custom formula | `optimizer.py:kelly_criterion()` | Correct Kelly/3 with edge cases handled |
| Altman Z / Beneish M scoring | Custom formulas | `risk_scores.py` + `guardian.py` | Phase 3 complete; 12 guardian tests |
| LangGraph HITL | Custom interrupt logic | `builder.py:judge_with_hitl()` + `interrupt()` | Already wired with checkpoint resume |

**Key insight:** Phase 4 is wiring, not building. The mathematical and agent logic is complete. Resist the urge to "improve" agent internals during integration — surface bugs via contract tests, fix them atomically.

---

## Common Pitfalls

### Pitfall 1: VeTO margin_adj Overwrite Instead of Accumulate

**What goes wrong:** Setting `margin_adj = 0.10` (for VeTO < 0.3) instead of `margin_adj += 0.10`, which silently drops the analyst momentum contribution.

**Why it happens:** Copy-paste from the variance section which starts from 0.0.

**How to avoid:** Always use `+=` for both VeTO and analyst momentum contributions. Write a contract test that verifies `margin_adjustment > 0.10` when both VeTO < 0.3 AND analyst downgrades are present.

**Warning signs:** Test `test_veto_margin_low` passes but a combined test fails.

### Pitfall 2: JudgeOutput margin_breakdown Not Backward Compatible

**What goes wrong:** Adding `margin_breakdown` as a required field (no default) breaks existing tests that construct JudgeOutput with positional args.

**Why it happens:** `@dataclass` with no default for the new field breaks any code that constructs JudgeOutput without naming it.

**How to avoid:** Add `margin_breakdown: dict = field(default_factory=dict)` with a default. Verify existing unit tests still pass after types.py change.

**Warning signs:** `TypeError: __init__() missing 1 required positional argument` in any of the 35 judge_math tests.

### Pitfall 3: Margin Bounds Update Breaks Existing Tests

**What goes wrong:** Changing `_MARGIN_MIN = 0.15` causes existing judge_math tests that assert `margin >= 0.20` to fail.

**Why it happens:** Tests were written against the old bounds.

**How to avoid:** When updating constants, grep for hardcoded `0.20` or `0.70` in test files and update them. Run `uv run pytest tests/unit/test_judge_math.py` immediately after the constant change.

**Warning signs:** Red tests in test_judge_math.py after constants change.

### Pitfall 4: Multi-ticker Fan-out Returns Exception Objects Instead of States

**What goes wrong:** `asyncio.gather(return_exceptions=True)` returns `Exception` objects in the results list for failed tickers. The portfolio optimizer receives them and crashes when trying to read `result["judge_output"]`.

**Why it happens:** `return_exceptions=True` is correct, but the caller must filter before passing to optimizer.

**How to avoid:** In the orchestrator, filter: `valid_results = [r for r in ticker_results if not isinstance(r, Exception)]`. Log failures separately.

**Warning signs:** `TypeError: 'RateLimitError' object is not subscriptable` in optimizer.

### Pitfall 5: asyncio.to_thread Without Semaphore Inside Thread

**What goes wrong:** The Semaphore is acquired in the async context before `asyncio.to_thread()`, but if the thread itself calls async code, the Semaphore is in the wrong event loop.

**Why it happens:** Mixing async and sync contexts incorrectly.

**How to avoid:** The Semaphore must be acquired as an async context manager BEFORE calling `asyncio.to_thread()`. The thread itself is fully synchronous (graph.invoke is sync). This is the correct pattern:
```python
async with semaphore:
    result = await asyncio.to_thread(graph.invoke, state, config)
```

**Warning signs:** All tickers run simultaneously despite `max_concurrent=2`.

### Pitfall 6: Smoke Test Slow Marker Not Registered

**What goes wrong:** `pytest.mark.slow` is unknown to pytest, producing a `PytestUnknownMarkWarning` and potentially running slow tests in CI if `-m "not slow"` is not in the CI command.

**Why it happens:** Custom marks must be registered in `pytest.ini_options`.

**How to avoid:** Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["slow: marks tests as slow (deselect with '-m not slow')"]
```

**Warning signs:** `PytestUnknownMarkWarning: Unknown pytest.mark.slow`.

---

## Code Examples

### Verified: Existing VeTO Section in strategist.py (lines ~380-390)

```python
# Source: src/lockin/agents/strategist.py lines ~380-390 [VERIFIED: codebase read]
# Current state — margin_adjustment=0.0 is a placeholder:
margin_adj = 0.0
if analyst_momentum < 0:  # net analyst downgrades
    margin_adj += 0.05

variance_adj = 0.0
if veto_score < 0.4:
    variance_adj += 0.10

# Phase 4 change: add VeTO margin thresholds between these two blocks
```

### Verified: Current Margin Constants (judge_math.py lines 46-49)

```python
# Source: src/lockin/agents/judge_math.py lines 46-49 [VERIFIED: codebase read + runtime check]
# Current values (verified runtime: min=0.2, max=0.7, base=0.3):
_MARGIN_MIN = 0.20   # → change to 0.15 (D-11)
_MARGIN_MAX = 0.70   # → change to 0.60 (D-11)
_MARGIN_BASE = 0.30  # unchanged
```

### Verified: modifiers_applied Already Computed in Judge Step 7 (lines 459-464)

```python
# Source: src/lockin/agents/judge_math.py lines 459-464 [VERIFIED: codebase read]
# Already computed — just needs to be exposed as margin_breakdown:
modifiers_applied={
    "oracle_margin": oracle_modifier.margin_adjustment,
    "guardian_margin": guardian_modifier.margin_adjustment,
    "strategist_margin": strategist_modifier.margin_adjustment,
    "total_variance_adj": total_variance_adj,
},
# Phase 4: add margin_breakdown to JudgeOutput with base + raw_total + clamped
```

### Verified: agent_overrides Pattern (builder.py)

```python
# Source: src/lockin/graph/builder.py create_graph() [VERIFIED: codebase read]
graph = create_graph(
    checkpointer=MemorySaver(),
    agent_overrides={
        "guardian": my_strict_guardian,
        "judge": my_judge,
    }
)
# Any agent not in overrides uses the real implementation.
# Contract tests use this to inject lightweight stubs.
```

### Verified: Semaphore Pattern (asyncio stdlib)

```python
# Source: Python 3.12 asyncio documentation [ASSUMED based on stdlib knowledge]
semaphore = asyncio.Semaphore(2)  # max 2 concurrent

async def run_with_limit(ticker: str) -> dict:
    async with semaphore:
        return await asyncio.to_thread(graph.invoke, state, config)

results = await asyncio.gather(
    *[run_with_limit(t) for t in tickers],
    return_exceptions=True,
)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Mock agents (Phase 1) | Real agents with typed contracts | Phase 3 complete | Contract tests now test real behavior, not mocks |
| `_MARGIN_MIN=0.20, _MARGIN_MAX=0.70` | `_MARGIN_MIN=0.15, _MARGIN_MAX=0.60` | Phase 4 (D-11) | More headroom for high-conviction setups |
| VeTO variance-only | VeTO variance + margin (symmetric) | Phase 4 (D-06/D-07) | Low VeTO now compounds: wider band + higher safety hurdle |
| margin_breakdown not in output | Structured margin_breakdown in JudgeOutput | Phase 4 (D-13) | Full explainability for EU AI Act compliance |
| Single-ticker pipeline | Multi-ticker async fan-out | Phase 4 (D-01/D-02/D-03) | Portfolio-level analysis enabled |

**Deprecated/outdated:**
- `margin_adjustment=0.0` placeholder in strategist.py: replaced by D-06 thresholds in Phase 4.
- `_MARGIN_MIN=0.20, _MARGIN_MAX=0.70` in judge_math.py: replaced by [0.15, 0.60] in Phase 4.
- Any test asserting `margin >= 0.20`: must be updated to `>= 0.15`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncio.to_thread()` correctly isolates sync `graph.invoke()` calls | Architecture Patterns / Multi-ticker | LangGraph graph.invoke may not be thread-safe if it uses mutable shared state — if so, create separate graph instance per ticker |
| A2 | Python asyncio.Semaphore stdlib behavior in 3.12 | Code Examples | Very low risk; stdlib API is stable |
| A3 | `tenacity` retry works by catching exceptions that contain "429" string | Code Examples | If Gemini SDK uses a different exception type, the retry predicate needs adjustment |
| A4 | `PORTFOLIO-03` concentration cap is 10% (from optimizer.py MAX_POSITION_SIZE) not 12% as in phase description | Phase Requirements | If 12% is correct, MAX_POSITION_SIZE in optimizer.py needs to change |

---

## Open Questions

1. **Thread safety of create_graph() / graph.invoke()**
   - What we know: LangGraph docs indicate that each `invoke()` call is scoped to a thread_id via the checkpointer; MemorySaver is in-process.
   - What's unclear: Whether creating multiple graph instances in threads with separate MemorySaver instances is safe or whether there's global mutable state in LangGraph internals.
   - Recommendation: Create one graph instance per ticker run (inside the thread), not a shared graph instance. This is safe regardless of LangGraph thread-safety guarantees.

2. **Portfolio-level Optimizer: new function or extend existing optimizer.py?**
   - What we know: D-03 says "Optimizer runs once after all per-ticker Judges complete." The existing `optimizer.py` operates per-ticker on a single InvestmentState.
   - What's unclear: Whether Phase 4 needs a new portfolio-level function that receives all ticker states and enforces cross-ticker sector limits.
   - Recommendation: Add a `portfolio_optimize(ticker_states: list[InvestmentState]) -> dict` function in orchestrator.py that enforces sector concentration limits (PORTFOLIO-01) across tickers. The per-ticker optimizer.py remains unchanged.

3. **PORTFOLIO-03 concentration cap: 10% or 12%?**
   - What we know: `optimizer.py` has `MAX_POSITION_SIZE = 0.10` (10%). The phase description success criteria says "max 12% per asset."
   - What's unclear: Which is the authoritative number.
   - Recommendation: Use 10% (MAX_POSITION_SIZE from optimizer.py / Notion spec). The 12% in the phase description appears to be a drafting artifact.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All | ✓ | 3.14.4 (CPython) | — |
| uv | Package management | ✓ | (installed) | pip |
| asyncio | Multi-ticker orchestration | ✓ | stdlib | — |
| pytest | Contract tests | ✓ | >=8.0.0 in dev deps | — |
| pytest-asyncio | Async test support | ✓ | >=0.24.0 in dev deps | — |
| tenacity | Exponential backoff | ✓ | >=9.0.0 in deps | Manual retry |
| Gemini Flash API key | Live smoke test | [ASSUMED] requires env var | — | Skip smoke test |
| Supabase / PostgreSQL | Audit logs (test bypass) | optional | — | stderr fallback (existing pattern) |

**Missing dependencies with no fallback:** None — all Phase 4 work can proceed with existing dependencies.

**Missing dependencies with fallback:**
- Gemini API key: Smoke test requires it; contract tests do not. CI runs only contract tests.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8.0.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/test_contracts.py -x -q` |
| Full suite command | `uv run pytest tests/ -m "not slow" -q` |
| Slow/live tests | `uv run pytest tests/e2e/test_live_smoke.py -m slow -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RISK-01 | Margin bounds [0.15, 0.60] enforced | unit | `uv run pytest tests/unit/test_contracts.py::test_margin_bounds_updated -x` | Wave 0 |
| RISK-01 | margin_breakdown in JudgeOutput | unit | `uv run pytest tests/unit/test_contracts.py::test_judge_output_has_margin_breakdown -x` | Wave 0 |
| RISK-02 | Guardian circuit_breaker propagates to END | unit (existing) | `uv run pytest tests/unit/test_guardian.py -x` | ✓ existing |
| RISK-03 | Position size capped at 10% | unit (existing) | `uv run pytest tests/unit/test_optimizer.py -x` | ✓ existing |
| RISK-04 | HITL triggers on p_final < 0.40 | unit (existing) | `uv run pytest tests/unit/test_judge.py -x` | ✓ existing |
| PORTFOLIO-01 | Sector concentration < 32.5% | unit | `uv run pytest tests/unit/test_contracts.py::test_sector_limits -x` | Wave 0 |
| PORTFOLIO-02 | Kelly/3 = 0.33 | unit (existing) | `uv run pytest tests/unit/test_optimizer.py -x` | ✓ existing |
| PORTFOLIO-03 | Concentration cap per position | unit (existing) | `uv run pytest tests/unit/test_optimizer.py -x` | ✓ existing |
| VeTO wiring | VeTO < 0.3 → margin += 0.10 | unit | `uv run pytest tests/unit/test_contracts.py::test_veto_margin_thresholds -x` | Wave 0 |
| Multi-ticker | Fan-out produces per-ticker results | unit | `uv run pytest tests/unit/test_contracts.py::test_multi_ticker_orchestrator -x` | Wave 0 |
| Integration | Full pipeline smoke (real APIs) | e2e/slow | `uv run pytest tests/e2e/test_live_smoke.py -m slow -v` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/test_contracts.py tests/unit/test_judge_math.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -m "not slow" -q`
- **Phase gate:** Full suite green + smoke test passes before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_contracts.py` — covers RISK-01, PORTFOLIO-01, VeTO wiring, multi-ticker
- [ ] `tests/e2e/test_live_smoke.py` — covers full integration, all golden range assertions
- [ ] `pyproject.toml` markers update — register `slow` mark to avoid PytestUnknownMarkWarning
- [ ] `src/lockin/graph/orchestrator.py` — new module (does not exist yet)

*(All other test infrastructure already exists and covers RISK-02, RISK-03, RISK-04, PORTFOLIO-02, PORTFOLIO-03)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Clamp functions in judge_math.py for all numeric outputs; VeTO score validated [0,1] |
| V6 Cryptography | no | — |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invalid ticker input (injection via ticker name) | Tampering | yfinance handles invalid tickers gracefully (returns None/empty DataFrame); agents have DataUnavailableError fallbacks |
| LLM prompt injection via earnings transcript | Tampering | Strategist LLM prompt is structured; transcript is passed as user message content, not system prompt |
| Rate limit exhaustion (DoS of Gemini free tier) | Denial of Service | D-04: asyncio.Semaphore(2) + exponential backoff limits concurrent calls |
| Numeric overflow in Bayesian math | Tampering | All probabilities clamped `[_P_MIN=0.10, _P_MAX=0.90]`; margins clamped `[0.15, 0.60]` |

---

## Sources

### Primary (HIGH confidence)
- `src/lockin/agents/strategist.py` — VeTO current state, existing VeTO logic, line numbers
- `src/lockin/agents/judge_math.py` — margin constants (runtime verified: min=0.2, max=0.7, base=0.3), Step 7 assembly
- `src/lockin/agents/types.py` — JudgeOutput dataclass (no margin_breakdown field confirmed)
- `src/lockin/agents/optimizer.py` — MAX_POSITION_SIZE=0.10, MAX_SECTOR_ALLOCATION=0.325, KELLY_FRACTION=0.33
- `src/lockin/graph/builder.py` — create_graph(), agent_overrides pattern, judge_with_hitl
- `tests/e2e/test_full_pipeline.py` — existing E2E test patterns, stub conventions
- `.planning/phases/04-integration-risk/04-CONTEXT.md` — all locked decisions D-01 through D-18

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` — Phase 3 completion status, known decisions per plan
- `.planning/REQUIREMENTS.md` — RISK-01..04, PORTFOLIO-01..03 acceptance criteria

### Tertiary (LOW confidence)
- asyncio.Semaphore + asyncio.to_thread concurrency pattern — based on training knowledge, not verified in this session [A1, A2]
- tenacity exception predicate pattern — based on training knowledge [A3]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified in pyproject.toml and codebase
- Architecture: HIGH — integration points precisely located via codebase reads (line numbers)
- Pitfalls: HIGH for codebase-specific ones (backward compat, overwrite vs accumulate); MEDIUM for async patterns
- Multi-ticker concurrency: MEDIUM — asyncio pattern assumed from training; LangGraph thread-safety not explicitly verified

**Research date:** 2026-05-01
**Valid until:** 2026-06-01 (stable stack; Gemini API may change rate limit behavior)
