---
phase: 03-agents-rag
plan: 05
subsystem: agents
tags: [bear, valuation, lognormal, epv, scipy, red-flags, adversarial]

# Dependency graph
requires:
  - phase: 03-01
    provides: "LLM factory (get_llm, MODEL_PRO), ValueDistribution + DataCoverage dataclasses, InvestmentState typed fields"
  - phase: 02-04
    provides: "get_fundamentals() public API — agents call this, never submodules directly"
provides:
  - "src/lockin/agents/bear.py: Bear adversarial agent — independent pessimistic investigation"
  - "tests/unit/test_bear.py: 10 unit tests verifying Bear independence, distribution shape, and state compatibility"
affects:
  - "03-07 (Judge): reads bear_valuation_distribution for Bayesian synthesis"
  - "03-11 (integration tests): bear must be wired into the graph replacing mock_bear"
  - "01-02 (builder): MAX_BULL_BEAR_ITERATIONS routing depends on bull_iteration increment from Bear"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Adversarial independence: Bear NEVER reads Bull output — structural guarantee enforced by docstring + tests"
    - "EPV pessimistic parametrization: WACC=12%, 20% EBIT haircut, tax=25%"
    - "Log-normal ValueDistribution: scipy.stats.lognorm with mu=log(max(value,1.0)), sigma=0.25"
    - "guard against log(0): max(pessimistic_value, 1.0) before np.log()"
    - "Deterministic red flags before LLM invocation — five signal checks on raw fundamentals"
    - "LLM fallback: try/except around get_llm and invoke_agent, safe defaults if LLM fails"

key-files:
  created:
    - "src/lockin/agents/bear.py"
    - "tests/unit/test_bear.py"
  modified: []

key-decisions:
  - "Bear sigma=0.25 (fixed constant) — wider than Bull's ~0.20 to express greater uncertainty in bearish case"
  - "EPV pessimistic uses operating_income as EBIT proxy; fallback: gross-up net_income by (1-tax_rate)"
  - "DataCoverage.available fixed to ['income_statement','balance_sheet','cash_flow']; missing=['competitive_threat_detail','regulatory_risk','insider_sentiment'] — three structural unknowns Bear cannot resolve from fundamentals alone"
  - "LLM red_flags merged with deterministic flags via dict.fromkeys (preserves order, de-duplicates)"
  - "store=False in get_fundamentals call — Bear is read-only; no DB writes during adversarial pass"

patterns-established:
  - "ValueDistribution.thesis updated after LLM call to incorporate LLM-generated text"
  - "All five deterministic red-flag signals guard against None / zero denominators via _safe() helper"
  - "Test mock pattern: @patch bear.get_llm + @patch bear.get_fundamentals — no live network"

# Metrics
duration: 3min
completed: 2026-03-17
---

# Phase 3 Plan 05: Bear Adversarial Agent Summary

**Pessimistic EPV-based Bear agent with log-normal ValueDistribution (sigma=0.25), 5 deterministic red-flag signals, full independence from Bull output, and 10 passing unit tests.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-17T11:38:41Z
- **Completed:** 2026-03-17T11:41:53Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Bear agent independently fetches fundamentals via `get_fundamentals(ticker, store=False)` — never reads Bull output
- Computes 5 deterministic red-flag signals: FCF < 0, margin compression < 5%, debt/equity > 2.0, accrual gap > 50%, revenue < 0
- Builds pessimistic EPV with WACC=12%, 20% EBIT haircut, tax=25%, net-cash adjusted
- Parametrizes log-normal ValueDistribution with sigma=0.25 (wider than Bull) ensuring p10 < p50 < p90
- Invokes MODEL_PRO for bearish thesis + structured challenges; graceful fallback if LLM unavailable
- 10 unit tests: all pass, including structural independence proof and distribution shape assertions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Bear adversarial agent outputting ValueDistribution** - `67bc3dc` (feat)
2. **Task 2: Unit tests verifying ValueDistribution output and independence** - `d92e63d` (feat)

**Plan metadata:** see final commit below

## Files Created/Modified

- `/home/mateo/dev/LockIn/src/lockin/agents/bear.py` — Bear agent: red-flag detection, pessimistic EPV, log-normal distribution, LLM thesis
- `/home/mateo/dev/LockIn/tests/unit/test_bear.py` — 10 unit tests (all 9 required + 1 bonus iteration edge case)

## Decisions Made

**Bear sigma = 0.25 (fixed constant):**
Wider than Bull's ~0.20 to reflect bear's higher uncertainty. Simple constant avoids data-derived sigma instability on sparse fundamentals.

**EPV uses operating_income as EBIT proxy:**
operating_income is directly available in FundamentalsResult. Fallback to net_income gross-up ensures EPV is always computable even with sparse data.

**DataCoverage.missing hardcoded to 3 structural unknowns:**
competitive_threat_detail, regulatory_risk, and insider_sentiment cannot be derived from fundamentals alone. Always missing for Bear = always honest about information gaps.

**store=False in get_fundamentals:**
Bear is a read-only agent. Skipping DB writes on the adversarial pass avoids redundant storage since Bull (Value Hunter) already wrote the same fundamentals in its pass.

**LLM fallback: silent stderr + safe defaults:**
A LLM failure should not crash the dialectic loop. Deterministic red flags (computed before LLM) provide a minimal but valid bear output even with no LLM.

## Deviations from Plan

None — plan executed exactly as written.

The `_compute_pessimistic_epv` function subtracts net debt (cash - debt) from the NOPAT-based EPV to produce an equity value, which is the standard EPV formula. The plan specified the formula components but left equity-value adjustment implicit; this was implemented as the correct financial interpretation.

## Verification Results

```
============================= test session starts ==============================
collected 10 items

tests/unit/test_bear.py::TestBearAgent::test_bear_independent_of_bull PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_increments_iteration PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_increments_iteration_from_nonzero PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_red_flags_detected PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_returns_value_distribution PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_distribution_pessimistic PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_distribution_wider_sigma PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_distribution_log_normal PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_data_coverage PASSED
tests/unit/test_bear.py::TestBearAgent::test_bear_state_compatible PASSED

============================== 10 passed in 3.74s ==============================
```

All 5 success criteria met:
- Bear builds thesis independently (blind to Bull) -- verified by `mock_gf.assert_called_once_with`
- Output is ValueDistribution (not dict) with log-normal parametrization -- isinstance check
- Bear distribution centered on pessimistic case (lower mu, wider sigma) -- < $200M bull estimate, sigma=0.25
- Red flags computed from deterministic signals before LLM call
- data_coverage.available and .missing both non-empty
- bull_iteration incremented (drives graph routing)

## Next Phase Readiness

**Blockers for 03-07 (Judge):** None. `bear_valuation_distribution` is a fully typed `ValueDistribution` instance ready for Bayesian synthesis.

**Graph wiring:** `mock_bear` in the LangGraph builder (plan 01-02) must be replaced by the real `bear` function from `lockin.agents.bear` in plan 03-11 integration tests.
