# Phase 4: Integration & Risk Management - Pattern Map

**Mapped:** 2026-05-01
**Files analyzed:** 7 (3 modified, 2 new source, 2 new test)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/lockin/agents/strategist.py` | agent/modifier | request-response | self (lines 381–465) | exact — inline edit |
| `src/lockin/agents/judge_math.py` | math/pure | transform | self (lines 46–49, 440–467) | exact — inline edit |
| `src/lockin/agents/types.py` | model/dataclass | — | self (lines 77–98) | exact — inline edit |
| `src/lockin/graph/orchestrator.py` | orchestrator | event-driven + request-response | `src/lockin/graph/builder.py` | role-match (graph orchestration) |
| `tests/unit/test_contracts.py` | test/unit | — | `tests/unit/test_judge_math.py` | exact — pure unit test pattern |
| `tests/e2e/test_live_smoke.py` | test/e2e | — | `tests/e2e/test_full_pipeline.py` | exact — E2E structure pattern |
| `pyproject.toml` | config | — | self (`[tool.pytest.ini_options]`) | exact — inline edit |

---

## Pattern Assignments

### `src/lockin/agents/strategist.py` (modifier agent, inline edit)

**Analog:** Self — lines 377–392 (the adjustment computation block)

**Exact target block** (`strategist.py` lines 381–391):
```python
# Current (Phase 3 placeholder — VeTO margin deferred):
margin_adj = 0.0
if analyst_momentum < 0:  # net analyst downgrades
    margin_adj += 0.05

variance_adj = 0.0
if veto_score < 0.4:  # low VeTO → unreliable organizational health signal
    variance_adj += 0.10
```

**Replacement pattern** (D-06/D-07/D-08/D-10):
```python
# Margin adjustment: analyst momentum signal (has_base_rate=True, Jegadeesh 2004)
margin_adj = 0.0
if analyst_momentum < 0:  # net analyst downgrades
    margin_adj += 0.05

# VeTO margin adjustment — symmetric, penalty (opacity) > reward (clarity)
# TODO: Revisit thresholds after backtest data is available (D-10)
if veto_score < 0.3:
    margin_adj += 0.10   # very opaque: strong penalty
elif veto_score < 0.4:
    margin_adj += 0.05   # poor visibility: moderate penalty
elif veto_score > 0.85:
    margin_adj -= 0.05   # very transparent: modest reward
elif veto_score > 0.7:
    margin_adj -= 0.03   # clear outcomes: small reward
# else: veto_score 0.40–0.70 → neutral, no adjustment

# Variance adjustment: VeTO only, conditional on low score (no base rate).
# VeTO has no base rate → only increases uncertainty band, never lowers it.
variance_adj = 0.0
if veto_score < 0.4:  # low VeTO → unreliable organizational health signal
    variance_adj += 0.10
```

**Critical:** Always use `+=` for VeTO contributions — they accumulate on top of analyst momentum. Setting `=` instead of `+=` silently drops the analyst momentum contribution (Pitfall 1 in RESEARCH.md).

**Doc-string update** (line 10–11, `strategist.py`): Remove the `Does NOT adjust margin (deferred to Phase 4)` clause and replace with the new VeTO margin semantics.

**Docstring for `strategist()` function** (line 300): Update `# Adjusts variance_adjustment += 0.10 ONLY when veto_score < 0.4` to add `# Adjusts margin_adjustment per D-06 thresholds (see inline block below)`.

---

### `src/lockin/agents/judge_math.py` (pure math, inline edit)

**Analog:** Self — lines 46–49 (constants block) and lines 440–467 (Step 7 assembly)

**Constants change** (lines 47–48, D-11):
```python
# Was:
_MARGIN_MIN = 0.20
_MARGIN_MAX = 0.70
_MARGIN_BASE = 0.30  # Graham/Buffett baseline  ← UNCHANGED

# Replace with:
_MARGIN_MIN = 0.15   # 15% floor — widens lower bound for high-conviction setups
_MARGIN_MAX = 0.60   # 60% ceiling — tightens upper (0.70 was rarely reached)
_MARGIN_BASE = 0.30  # unchanged
```

**margin_breakdown surface — Step 7 assembly** (lines 443–467, D-13):

The existing `modifiers_applied` dict already computes the individual agent contributions (lines 459–464). Extend the `JudgeOutput(...)` constructor call to also pass `margin_breakdown`:

```python
# After computing margin (line ~253: max(_MARGIN_MIN, min(_MARGIN_MAX, margin))):
raw_total = (
    _MARGIN_BASE
    + oracle_modifier.margin_adjustment
    + guardian_modifier.margin_adjustment
    + strategist_modifier.margin_adjustment
)
margin_breakdown = {
    "base": _MARGIN_BASE,
    "oracle": oracle_modifier.margin_adjustment,
    "guardian": guardian_modifier.margin_adjustment,
    "strategist": strategist_modifier.margin_adjustment,
    "raw_total": raw_total,
    "clamped": margin,   # margin = max(_MARGIN_MIN, min(_MARGIN_MAX, raw_total + _MARGIN_BASE))
}

# In JudgeOutput(...) constructor, add:
margin_breakdown=margin_breakdown,
```

**Module docstring update** (line 16): Change `clamped [0.20, 0.70]` to `clamped [0.15, 0.60]`.

**After constants change — existing tests at risk:** Any test in `tests/unit/test_judge_math.py` asserting `margin >= 0.20` must be updated to `>= 0.15`. Grep for `0.20` and `0.70` in that file before running the suite (Pitfall 3 in RESEARCH.md).

---

### `src/lockin/agents/types.py` (model/dataclass, inline edit)

**Analog:** Self — `JudgeOutput` dataclass (lines 77–98)

**Existing JudgeOutput** (lines 77–98):
```python
@dataclass
class JudgeOutput:
    recommendation: str
    consensus_distribution: tuple
    valor_mediano: float
    precio_target: float
    margin_of_safety: float
    p_success: float
    p_base: float
    p_adjustments: dict = field(default_factory=dict)
    kelly_fraction: float = 0.0
    hold_conviction: float = 0.0
    known_unknowns: list[str] = field(default_factory=list)
    convergence_score: float = 0.0
    convergence_alert: bool = False
    bull_weight: float = 0.5
    bear_weight: float = 0.5
    modifiers_applied: dict = field(default_factory=dict)
    circuit_breaker: bool = False
    circuit_breaker_override: bool = False
```

**Add after `circuit_breaker_override`** (D-13, Pitfall 2):
```python
    margin_breakdown: dict = field(default_factory=dict)
    # Populated by judge_math.py Step 7:
    # {
    #   "base": _MARGIN_BASE,
    #   "oracle": oracle_modifier.margin_adjustment,
    #   "guardian": guardian_modifier.margin_adjustment,
    #   "strategist": strategist_modifier.margin_adjustment,
    #   "raw_total": <sum before clamp>,
    #   "clamped": <final margin_of_safety>,
    # }
```

**Critical:** Must use `field(default_factory=dict)` (not `= {}`) so existing code that constructs `JudgeOutput(...)` without naming `margin_breakdown` continues to work (Pitfall 2 in RESEARCH.md).

---

### `src/lockin/graph/orchestrator.py` (new orchestrator, request-response + event-driven)

**Analog:** `src/lockin/graph/builder.py` — module structure, imports, graph invocation pattern

**Imports pattern** (copy from `builder.py` lines 39–72, adapt):
```python
"""
Multi-ticker orchestration wrapper.

Runs Macro Oracle once (shared market context), fans out per-ticker pipelines
concurrently via asyncio.Semaphore, then aggregates via a portfolio-level optimizer.

Architecture (D-01/D-02/D-03):
  1. Macro Oracle — runs ONCE, result injected into all per-ticker initial states
  2. asyncio.gather fan-out — each ticker runs the full 7-agent pipeline concurrently
     with Semaphore(max_concurrent) controlling API rate limits (D-04)
  3. Portfolio Optimizer — runs ONCE over all valid per-ticker results

Rate limiting (D-04):
  - asyncio.Semaphore(max_concurrent=2) — controls concurrent LLM calls
  - tenacity @retry on 429 errors with exponential backoff
  - asyncio.to_thread() — graph.invoke() is sync; run in thread pool (A1)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from langgraph.checkpoint.memory import MemorySaver

from lockin.graph.builder import create_graph
from lockin.graph.state import InvestmentState, create_initial_state

logger = logging.getLogger(__name__)
```

**Macro Oracle isolation pattern** — run only macro_oracle via agent_overrides stubs for all other agents, OR extract the macro context from the state after a single-ticker partial run. Recommended approach (simpler, no partial run gymnastics):

```python
def _run_macro_oracle_standalone(reference_ticker: str) -> dict:
    """Run a graph with all agents stubbed except macro_oracle.

    Returns the macro-relevant keys from InvestmentState:
      macro_regime, macro_confidence, macro_narrative, oracle_modifier
    """
    from lockin.agents.mock import (
        mock_bear, mock_guardian, mock_judge,
        mock_optimizer, mock_strategist, mock_value_hunter,
    )
    graph = create_graph(
        checkpointer=MemorySaver(),
        agent_overrides={
            "value_hunter": mock_value_hunter,
            "bear": mock_bear,
            "strategist": mock_strategist,
            "guardian": mock_guardian,
            "judge": mock_judge,
            "optimizer": mock_optimizer,
        },
    )
    state = create_initial_state(reference_ticker)
    result = graph.invoke(state, {"configurable": {"thread_id": f"macro-only-{reference_ticker}"}})
    return {
        "macro_regime": result.get("macro_regime"),
        "macro_confidence": result.get("macro_confidence"),
        "macro_narrative": result.get("macro_narrative"),
        "oracle_modifier": result.get("oracle_modifier"),
    }
```

**Retry pattern** (tenacity, D-04):
```python
def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate" in msg

@retry(
    retry=retry_if_exception(_is_rate_limit_error),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
)
def _invoke_graph_with_retry(graph: Any, state: dict, config: dict) -> dict:
    return graph.invoke(state, config)
```

**Core fan-out pattern** (D-01/D-02/D-03/D-04):
```python
async def analyze_portfolio(
    tickers: list[str],
    max_concurrent: int = 2,
) -> dict[str, Any]:
    """Run multi-ticker pipeline: Macro Oracle once, then parallel per-ticker."""
    semaphore = asyncio.Semaphore(max_concurrent)

    # Step 1: Macro Oracle runs once — shared across all tickers (D-01)
    macro_context = _run_macro_oracle_standalone(tickers[0])

    # Step 2: Fan-out — each ticker gets its own graph instance (A1: thread safety)
    async def run_ticker(ticker: str) -> dict | Exception:
        async with semaphore:   # acquire BEFORE asyncio.to_thread (Pitfall 5)
            state = create_initial_state(ticker)
            state.update(macro_context)   # inject shared macro context
            graph = create_graph(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": f"portfolio-{ticker}"}}
            try:
                return await asyncio.to_thread(
                    _invoke_graph_with_retry, graph, state, config
                )
            except Exception as exc:
                logger.error("Ticker %s failed: %s", ticker, exc)
                return exc  # return_exceptions=True semantics (Pitfall 4)

    ticker_results = await asyncio.gather(
        *[run_ticker(t) for t in tickers],
        return_exceptions=True,
    )

    # Step 3: Filter failed tickers before passing to portfolio optimizer (Pitfall 4)
    valid_results = [r for r in ticker_results if not isinstance(r, Exception)]
    failed = [r for r in ticker_results if isinstance(r, Exception)]
    if failed:
        logger.warning("%d tickers failed: %s", len(failed), failed)

    # Step 4: Portfolio-level optimization (D-03)
    return portfolio_optimize(valid_results, tickers)
```

**Portfolio optimizer function** (cross-ticker, D-03; Research Q2):
```python
def portfolio_optimize(
    ticker_states: list[dict],
    all_tickers: list[str],
) -> dict[str, Any]:
    """Aggregate per-ticker Judge outputs into a portfolio allocation.

    Enforces cross-ticker sector concentration (PORTFOLIO-01: MAX_SECTOR_ALLOCATION).
    Per-ticker position caps are already enforced by optimizer.py (RISK-03).
    """
    from lockin.agents.optimizer import MAX_POSITION_SIZE, MAX_SECTOR_ALLOCATION

    positions: dict[str, float] = {}
    sector_allocations: dict[str, float] = {}

    for state in ticker_states:
        ticker = state.get("asset_ticker", "UNKNOWN")
        portfolio = state.get("optimizer_portfolio", {})
        sectors = state.get("optimizer_sectors", {})
        for asset, size in portfolio.items():
            positions[asset] = min(size, MAX_POSITION_SIZE)
        for sector, alloc in sectors.items():
            sector_allocations[sector] = sector_allocations.get(sector, 0.0) + alloc

    # Enforce cross-ticker sector cap
    for sector, total in sector_allocations.items():
        if total > MAX_SECTOR_ALLOCATION:
            # Scale down all positions in this sector proportionally
            scale = MAX_SECTOR_ALLOCATION / total
            for asset, size in positions.items():
                positions[asset] = size * scale   # simplified; real logic iterates by sector

    return {
        "positions": positions,
        "sector_allocations": sector_allocations,
        "ticker_count": len(ticker_states),
        "failed_tickers": [t for t in all_tickers if t not in positions],
    }
```

---

### `tests/unit/test_contracts.py` (new, unit test, zero LLM calls)

**Analog:** `tests/unit/test_judge_math.py` — fixture helpers, import pattern, pure assertion style

**Imports pattern** (copy from `test_judge_math.py` lines 1–41, adapt):
```python
"""
Contract tests for Phase 4 integration wiring.

Verifies:
  - VeTO margin thresholds (D-06)
  - Margin bounds [0.15, 0.60] (D-11)
  - margin_breakdown in JudgeOutput (D-13)
  - Multi-ticker orchestrator (D-01/D-02/D-03)

Zero LLM calls — CI-safe. All inputs are hand-crafted stubs.
NOTE: If margin/sizing constants change (D-18), review golden ranges here.
Source constants: _MARGIN_MIN=0.15, _MARGIN_MAX=0.60 in judge_math.py
"""
from __future__ import annotations

import pytest
from lockin.agents.judge_math import (
    _MARGIN_MIN,
    _MARGIN_MAX,
    _MARGIN_BASE,
    compute_margin_of_safety,
    run_judge_algorithm,
)
from lockin.agents.types import ConfidenceModifier, DataCoverage, JudgeOutput, ValueDistribution
```

**Fixture helpers** (copy `_make_coverage`, `_make_bull_dist`, `_make_bear_dist` from `test_judge_math.py` lines 48–95 verbatim):
```python
def _make_modifier(margin: float = 0.0, variance: float = 0.0) -> ConfidenceModifier:
    return ConfidenceModifier(
        margin_adjustment=margin,
        variance_adjustment=variance,
        circuit_breaker=False,
        signals=[],
        data_coverage=DataCoverage(available=["test_field"], missing=[]),
        reasoning="contract test stub",
    )
```

**Strategist stub for VeTO threshold tests** (needed to invoke the real strategist adjustment logic without LLM calls):
```python
# Rather than calling the real strategist (which calls LLM + yfinance),
# replicate the adjustment block inline in the test, or extract it to a
# pure helper function. Pattern from test_full_pipeline.py lines 53–67.

def _make_strategist_modifier_with_veto(
    veto_score: float,
    analyst_momentum: float = 0.0,
) -> ConfidenceModifier:
    """Compute strategist adjustments inline (same logic as strategist.py block)."""
    margin_adj = 0.0
    if analyst_momentum < 0:
        margin_adj += 0.05
    if veto_score < 0.3:
        margin_adj += 0.10
    elif veto_score < 0.4:
        margin_adj += 0.05
    elif veto_score > 0.85:
        margin_adj -= 0.05
    elif veto_score > 0.7:
        margin_adj -= 0.03

    variance_adj = 0.0
    if veto_score < 0.4:
        variance_adj += 0.10

    return _make_modifier(margin=margin_adj, variance=variance_adj)
```

**Core test cases** (D-15):
```python
# --- Margin bounds (D-11) ---
def test_margin_bounds_updated():
    assert _MARGIN_MIN == 0.15
    assert _MARGIN_MAX == 0.60

def test_margin_clamp_lower_bound():
    margin = compute_margin_of_safety(
        _make_modifier(-0.50), _make_modifier(-0.50), _make_modifier(-0.50)
    )
    assert margin == 0.15

def test_margin_clamp_upper_bound():
    margin = compute_margin_of_safety(
        _make_modifier(0.20), _make_modifier(0.30), _make_modifier(0.15)
    )
    assert margin == 0.60

# --- VeTO margin wiring (D-06) ---
def test_veto_very_opaque_adds_010():
    mod = _make_strategist_modifier_with_veto(veto_score=0.25)
    assert mod.margin_adjustment == pytest.approx(0.10)

def test_veto_poor_visibility_adds_005():
    mod = _make_strategist_modifier_with_veto(veto_score=0.35)
    assert mod.margin_adjustment == pytest.approx(0.05)

def test_veto_neutral_range_no_adjustment():
    mod = _make_strategist_modifier_with_veto(veto_score=0.55)
    assert mod.margin_adjustment == pytest.approx(0.00)

def test_veto_clear_outcomes_subtracts_003():
    mod = _make_strategist_modifier_with_veto(veto_score=0.75)
    assert mod.margin_adjustment == pytest.approx(-0.03)

def test_veto_very_transparent_subtracts_005():
    mod = _make_strategist_modifier_with_veto(veto_score=0.90)
    assert mod.margin_adjustment == pytest.approx(-0.05)

def test_veto_accumulates_with_analyst_momentum():
    """Pitfall 1: += semantics — both sources must accumulate."""
    mod = _make_strategist_modifier_with_veto(veto_score=0.25, analyst_momentum=-1)
    assert mod.margin_adjustment == pytest.approx(0.15)  # 0.05 (analyst) + 0.10 (VeTO)

# --- margin_breakdown in JudgeOutput (D-13) ---
def test_judge_output_has_margin_breakdown_field():
    output = JudgeOutput(
        recommendation="HOLD",
        consensus_distribution=(5.0, 0.2),
        valor_mediano=150.0,
        precio_target=135.0,
        margin_of_safety=0.30,
        p_success=0.55,
        p_base=0.50,
    )
    assert hasattr(output, "margin_breakdown")
    assert isinstance(output.margin_breakdown, dict)

def test_judge_algorithm_populates_margin_breakdown():
    output = run_judge_algorithm(
        bull_dist=_make_bull_dist(),
        bear_dist=_make_bear_dist(),
        oracle_modifier=_make_modifier(margin=0.05),
        guardian_modifier=_make_modifier(margin=0.05),
        strategist_modifier=_make_modifier(margin=0.05),
        current_price=150.0,
    )
    assert "oracle" in output.margin_breakdown
    assert "guardian" in output.margin_breakdown
    assert "strategist" in output.margin_breakdown
    assert "base" in output.margin_breakdown
    assert "raw_total" in output.margin_breakdown
    assert "clamped" in output.margin_breakdown
    assert output.margin_breakdown["clamped"] == output.margin_of_safety
```

---

### `tests/e2e/test_live_smoke.py` (new, E2E, real APIs)

**Analog:** `tests/e2e/test_full_pipeline.py` — module structure, fixture pattern, `patch_audit_settings`, `mem_saver`

**Imports and setup** (lines 24–46 of `test_full_pipeline.py` as template):
```python
"""
Live smoke test — single-ticker full pipeline with real APIs.

Excluded from CI. Run manually:
  uv run pytest tests/e2e/test_live_smoke.py -m slow -v

Requires: GEMINI_API_KEY (or GOOGLE_API_KEY) in environment.
Default ticker: AAPL. Override with SMOKE_TICKER env var.

NOTE (D-18): If margin/sizing constants change, review the golden range
assertions below. Source constants:
  _MARGIN_MIN=0.15, _MARGIN_MAX=0.60   in src/lockin/agents/judge_math.py
  MAX_POSITION_SIZE=0.10               in src/lockin/agents/optimizer.py
"""
from __future__ import annotations

import os
import unittest.mock as mock

import pytest
from langgraph.checkpoint.memory import MemorySaver

from lockin.graph.builder import create_graph
from lockin.graph.state import create_initial_state

SMOKE_TICKER = os.getenv("SMOKE_TICKER", "AAPL")

_FAKE_SETTINGS_NO_DB = type("Settings", (), {"database_url": ""})()

@pytest.fixture(autouse=True)
def patch_audit_settings():
    """Prevent audit_node from attempting Supabase connection during smoke test."""
    with mock.patch(
        "lockin.utils.audit.get_settings",
        return_value=_FAKE_SETTINGS_NO_DB,
    ):
        yield
```

**Core smoke test** (D-17):
```python
@pytest.mark.slow
def test_live_single_ticker_smoke():
    """Full pipeline with real LLM + real data APIs. Structure + golden range assertions."""
    graph = create_graph(checkpointer=MemorySaver())
    state = create_initial_state(SMOKE_TICKER)
    result = graph.invoke(
        state,
        {"configurable": {"thread_id": f"smoke-{SMOKE_TICKER}"}},
    )

    # Structure assertions — must be present
    assert result.get("judge_recommendation") in ("BUY", "HOLD", "PASS")
    assert result.get("optimizer_portfolio")           # non-empty dict
    assert result.get("bull_thesis")                   # non-empty string
    assert result.get("bear_thesis")                   # non-empty string
    assert result.get("macro_regime") is not None

    judge_out = result.get("judge_output")
    assert judge_out is not None
    assert hasattr(judge_out, "margin_breakdown")
    assert "oracle" in judge_out.margin_breakdown
    assert "guardian" in judge_out.margin_breakdown
    assert "strategist" in judge_out.margin_breakdown
    assert "clamped" in judge_out.margin_breakdown

    # Golden range assertions (D-17)
    # NOTE (D-18): review if _MARGIN_MIN/_MARGIN_MAX or MAX_POSITION_SIZE change
    conviction = result.get("judge_conviction")
    assert conviction is not None
    assert 0.0 <= conviction <= 1.0

    margin = result.get("judge_margin")
    assert margin is not None
    assert 0.15 <= margin <= 0.60   # bounds per D-11

    position_size = result.get("optimizer_metrics", {}).get("position_size", 0.0)
    assert 0.0 <= position_size <= 0.10   # MAX_POSITION_SIZE per RISK-03

    veto_score = result.get("strategist_veto")
    assert veto_score is not None
    assert 0.0 <= veto_score <= 1.0

    strat_mod = result.get("strategist_modifier")
    assert strat_mod is not None
    assert hasattr(strat_mod, "margin_adjustment")
```

---

### `pyproject.toml` (config, inline edit)

**Analog:** Self — `[tool.pytest.ini_options]` block (lines 73–75)

**Current state** (lines 73–76):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Add `markers`** (Pitfall 6 in RESEARCH.md):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow — real API calls, excluded from CI (deselect with '-m not slow')",
]
```

---

## Shared Patterns

### audit_node patch (tests only)
**Source:** `tests/e2e/test_full_pipeline.py` lines 331–347
**Apply to:** `tests/e2e/test_live_smoke.py` and `tests/unit/test_contracts.py` (if any agent is called)
```python
_FAKE_SETTINGS_NO_DB = type("Settings", (), {"database_url": ""})()

@pytest.fixture(autouse=True)
def patch_audit_settings():
    with mock.patch(
        "lockin.utils.audit.get_settings",
        return_value=_FAKE_SETTINGS_NO_DB,
    ):
        yield
```

### ConfidenceModifier stub constructor
**Source:** `tests/e2e/test_full_pipeline.py` lines 53–67
**Apply to:** `tests/unit/test_contracts.py` (used extensively for VeTO threshold tests)
```python
def _make_confidence_modifier(
    margin: float = 0.0,
    variance: float = 0.0,
    circuit_breaker: bool = False,
    cb_reason: str | None = None,
) -> ConfidenceModifier:
    return ConfidenceModifier(
        margin_adjustment=margin,
        variance_adjustment=variance,
        circuit_breaker=circuit_breaker,
        circuit_breaker_reason=cb_reason,
        signals=[],
        data_coverage=DataCoverage(available=["test_field"], missing=[]),
        reasoning="stub modifier",
    )
```

### agent_overrides injection pattern
**Source:** `src/lockin/graph/builder.py` lines 270–290 (`create_graph()` signature)
**Apply to:** `orchestrator.py` (macro-only run stubs), `tests/unit/test_contracts.py` (multi-ticker test with stubs)
```python
graph = create_graph(
    checkpointer=MemorySaver(),
    agent_overrides={
        "value_hunter": mock_value_hunter,
        "bear": mock_bear,
        # ... stubs for everything except the agent under test
    },
)
```

### asyncio.to_thread + Semaphore concurrency
**Source:** RESEARCH.md Pattern 4 (Pitfall 5 documents the critical ordering rule)
**Apply to:** `orchestrator.py`
```python
async with semaphore:              # acquire FIRST (outside to_thread)
    result = await asyncio.to_thread(graph.invoke, state, config)
```

---

## No Analog Found

All 7 files have analogs. The only conceptually new pattern is `asyncio.to_thread` + `Semaphore` for the multi-ticker fan-out — this has no existing codebase analog, but is a standard asyncio stdlib pattern documented in RESEARCH.md Patterns 4/5.

---

## Metadata

**Analog search scope:** `src/lockin/`, `tests/`
**Files scanned:** 12 (strategist.py, judge_math.py, types.py, builder.py, state.py, optimizer.py, test_full_pipeline.py, test_judge_math.py, conftest.py, pyproject.toml + CONTEXT.md + RESEARCH.md)
**Pattern extraction date:** 2026-05-01
