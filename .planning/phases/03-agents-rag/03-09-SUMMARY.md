---
phase: "03"
plan: "09"
subsystem: "agents"
tags: ["optimizer", "kelly-criterion", "position-sizing", "portfolio", "circuit-breaker", "yfinance", "gemini-flash"]

dependency-graph:
  requires:
    - "03-01"  # LLM factory (get_llm, MODEL_FLASH), JudgeOutput dataclass, InvestmentState
    - "03-08"  # Judge agent produces JudgeOutput in state (kelly_fraction already Kelly/3)
  provides:
    - "optimizer() LangGraph node with Kelly/3 position sizing"
    - "kelly_criterion() standalone formula (reusable)"
    - "optimizer_portfolio, optimizer_sectors, optimizer_metrics, optimizer_narrative state fields"
  affects:
    - "03-11"  # Phase 3 integration tests (optimizer is final pipeline node)
    - "04-01"  # Phase 4 integration (full graph execution)

tech-stack:
  added: []
  patterns:
    - "Kelly/3 position sizing: KELLY_FRACTION=0.33 applied to JudgeOutput.kelly_fraction"
    - "Hard cap chain: min(kelly, 10%, sector_cap, [2% override cap if CB override])"
    - "JudgeOutput preferred path with fallback to individual state fields"
    - "yfinance sector fetch best-effort (try/except, never crashes pipeline)"
    - "MODEL_FLASH LLM narrative with silent stderr fallback"
    - "Constants at module level for testability (importable by tests)"

key-files:
  created:
    - "src/lockin/agents/optimizer.py"
    - "tests/unit/test_optimizer.py"
  modified: []

decisions:
  - id: "kelly-third-constant"
    choice: "KELLY_FRACTION = 0.33 (Kelly/3)"
    rationale: "Notion spec explicitly specifies Kelly/3, NOT Kelly/4 (0.25). The judge_math module pre-applies the 1/3 fractional Kelly before writing kelly_fraction to JudgeOutput, so optimizer reads the already-fractional value directly."
    alternatives: ["Kelly/4 = 0.25", "Full Kelly"]

  - id: "position-cap-chain"
    choice: "min(kelly_fraction, MAX_POSITION_SIZE, MAX_SECTOR_ALLOCATION, [CB_OVERRIDE_CAP])"
    rationale: "Multiple independent caps applied in sequence: 10% per-position hard cap, 32.5% sector concentration limit, 2% circuit-breaker-override emergency cap. All caps from Notion spec."
    alternatives: ["Single cap only"]

  - id: "cb-override-cap-placement"
    choice: "circuit_breaker_override cap applied AFTER BUY position sizing"
    rationale: "Override path allows a small position (<=2%) even when circuit breaker fires, overriding the hard-zero default. Cap applied last to override any earlier sizing."
    alternatives: ["Block entirely if CB fires"]

  - id: "hold-zero-allocation"
    choice: "HOLD -> position_size = 0.0 (no new capital)"
    rationale: "HOLD means maintain existing position, not add new capital. Optimizer only sizes new allocations. Matches Notion spec decision table."
    alternatives: ["HOLD maintains current sizing"]

  - id: "yfinance-best-effort"
    choice: "yfinance sector fetch wrapped in try/except, defaults to 'Unknown'"
    rationale: "Network calls must not crash the deterministic sizing logic. Sector cap applies regardless (position_size <= MAX_SECTOR_ALLOCATION) so Unknown sector is safe."
    alternatives: ["Fail fast on yfinance error"]

  - id: "llm-flash-narrative"
    choice: "MODEL_FLASH for narrative (not MODEL_PRO)"
    rationale: "Optimizer narrative is a prose summary, not a complex reasoning task. Flash is sufficient and conserves PRO quota for Judge/Value Hunter."
    alternatives: ["MODEL_PRO for narrative"]

metrics:
  duration: "~8 minutes"
  completed: "2026-03-18"
  tasks: 2
  tests_added: 16
  tests_passing: 16
  commits: 2
---

# Phase 3 Plan 9: Optimizer Agent Summary

**One-liner:** Kelly/3 portfolio optimizer (KELLY_FRACTION=0.33) with 10% position cap, 2% circuit-breaker override cap, and sector concentration limit reading from JudgeOutput.

## What Was Built

The Optimizer is the final LangGraph node in the investment pipeline. It reads the Judge's structured `JudgeOutput` from state and converts the conviction/recommendation into a concrete portfolio allocation following the Notion spec's Kelly/3 sizing rules.

### Core components

**`src/lockin/agents/optimizer.py`**

- `kelly_criterion(win_prob, win_loss_ratio)` — standalone formula `f* = (p*b - q)/b`, returns `max(0, f*)`. Reusable outside the agent.
- `optimizer(state, config)` — LangGraph node implementing the full decision table:
  - **BUY** → apply `judge_output.kelly_fraction` (already Kelly/3), hard-cap at 10%, sector-cap at 32.5%
  - **HOLD** → 0 new capital (position already held)
  - **PASS** → 0 position
  - **circuit_breaker=True, no override** → hard 0 position
  - **circuit_breaker_override=True** → position capped at <=2% (CIRCUIT_BREAKER_OVERRIDE_CAP)
- Module-level constants importable by tests: `KELLY_FRACTION`, `MAX_POSITION_SIZE`, `MAX_SECTOR_ALLOCATION`, `CIRCUIT_BREAKER_OVERRIDE_CAP`
- Portfolio metrics: `expected_return`, `portfolio_risk`, `sharpe`, `max_drawdown_estimate`
- Best-effort yfinance sector fetch (network failure handled silently)
- MODEL_FLASH LLM narrative with silent fallback to deterministic string

**`tests/unit/test_optimizer.py`** — 16 unit tests across 4 classes:

| Class | Count | Coverage |
|---|---|---|
| TestKellyCriterion | 4 | basic (0.4), negative->0, 50-50->0, zero ratio->0 |
| TestConstants | 3 | KELLY_FRACTION==0.33, MAX_POSITION_SIZE==0.10, CB_OVERRIDE_CAP==0.02 |
| TestOptimizerDecisionTable | 6 | BUY, PASS, HOLD, 10% cap, CB override, CB no override |
| TestOptimizerOutputStructure | 3 | all output keys, metrics sub-keys, LLM fallback |

All 16 tests pass in 3.76s.

## Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| Kelly fraction | KELLY_FRACTION = 0.33 | Notion spec explicitly says Kelly/3, NOT Kelly/4 |
| Position cap | 10% hard cap (MAX_POSITION_SIZE = 0.10) | Notion spec maximum per single position |
| CB override cap | 2% (CIRCUIT_BREAKER_OVERRIDE_CAP = 0.02) | Midpoint of 1-2% spec range |
| HOLD allocation | 0 new capital | HOLD = maintain existing, not add new |
| Sector allocation | 32.5% (midpoint of 30-35%) | Notion spec range midpoint |
| yfinance fetch | Best-effort, defaults to "Unknown" sector | Network failure must not crash deterministic sizing |
| LLM model | MODEL_FLASH for narrative | Prose summary doesn't need MODEL_PRO reasoning quality |

## Deviations from Plan

None — plan executed exactly as written.

The implementation follows the provided spec code structure closely, with these minor enhancements:

1. `position_cap_applied` flag uses a more precise check: `kelly_fraction > MAX_POSITION_SIZE and position_size <= MAX_POSITION_SIZE` (correctly identifies when cap was actually binding), vs the plan's `round(position_size, 4) == round(MAX_POSITION_SIZE, 4)` which was imprecise for floating-point comparisons. This produces the same result but is more readable.
2. Added 7 additional tests beyond the required 9 (16 total vs 9 minimum) to improve coverage of output structure, metrics keys, and LLM failure fallback.

## Next Phase Readiness

**Optimizer is ready for integration when:**
- Judge agent (03-08) is complete and writes `JudgeOutput` to `state["judge_output"]`
- LangGraph graph builder wires `optimizer` as the final node after `judge`

**State fields produced by optimizer:**
```python
optimizer_portfolio: {ticker: position_size}   # e.g. {"AAPL": 0.08}
optimizer_sectors:   {sector: position_size}   # e.g. {"Technology": 0.08}
optimizer_rebalancing: []                       # v1: always empty
optimizer_metrics: {
    kelly_fraction, position_size, position_cap_applied,
    circuit_breaker_override_applied, expected_return,
    portfolio_risk, sharpe, max_drawdown_estimate
}
optimizer_narrative: str                        # LLM prose or fallback string
```
