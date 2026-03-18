---
phase: 03-agents-rag
plan: "08"
subsystem: agents
tags: [judge, bayesian, kelly, log-pool, hitl, rag, gemini-pro, confidence-modifier, value-distribution]

# Dependency graph
requires:
  - phase: 03-01
    provides: "ValueDistribution, ConfidenceModifier, JudgeOutput dataclasses; InvestmentState judge_output field; get_llm(), MODEL_PRO"
  - phase: 03-03
    provides: "Value Hunter bull ValueDistribution (EPV/EVA/RIM + log-normal)"
  - phase: 03-05
    provides: "Bear adversarial ValueDistribution (pessimistic EPV, sigma=0.25)"
  - phase: 03-07
    provides: "RAG retrieve_with_citations() function"
  - phase: 03-02
    provides: "Macro Oracle ConfidenceModifier with macro_base_rate signal"
  - phase: 03-04
    provides: "Strategist ConfidenceModifier with VeTO (has_base_rate=False)"
  - phase: 03-06
    provides: "Guardian ConfidenceModifier with circuit_breaker + risk signals"
provides:
  - "judge_math.py: pure 7-step Bayesian Consensus Algorithm (no network, no LLM)"
  - "judge.py: LangGraph agent integrating algorithm with LLM narrative, RAG, HITL"
  - "43 unit tests across both files (35 math + 8 agent)"
affects:
  - "03-09-optimizer (reads judge_output.kelly_fraction, recommendation, circuit_breaker)"
  - "03-12-integration (wires judge into full graph flow)"
  - "01-03-hitl-scaffold (judge replaces mock_judge; HITL threshold changes 0.50->0.40)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Separation of pure math (judge_math.py) from LangGraph integration (judge.py) for testability"
    - "Two-axis consensus: (1) Log Pool for value synthesis, (2) base-rate probability for success likelihood"
    - "Kelly/3 (KELLY_FRACTION=0.33) as conservative position sizing for early-stage system"
    - "HITL at p < 0.40 OR circuit_breaker — NOT conviction < 0.50 (regression guard test added)"
    - "Graceful degradation: yfinance, RAG, LLM each wrapped in try/except with silent fallback"

key-files:
  created:
    - src/lockin/agents/judge_math.py
    - src/lockin/agents/judge.py
    - tests/unit/test_judge_math.py
    - tests/unit/test_judge.py
  modified: []

key-decisions:
  - "judge_math.py is pure (zero imports of yfinance/LLM/RAG) — entire algorithm testable without mocks"
  - "HITL threshold 0.40 (NOT 0.50): p_final < 0.40 = HOLD territory per Notion spec v1.0; regression guard test enforces this"
  - "compute_recommendation checks current_price > precio_target FIRST (PASS), then p_final < 0.40 (HOLD), then BUY — strict order matters"
  - "KELLY_FRACTION = 0.33 (not 0.25): more conservative Kelly/3 for system without Phase 5 backtesting yet"
  - "data_quality_factor returns 0.5 (neutral) when data_coverage.available is empty — avoids collapsing weight to zero"
  - "Missing list sentinel fix: _make_bear_dist uses 'missing is None' check (not 'missing or [...]') to allow explicit empty list"
  - "current_price fallback: geometric mean of bull/bear expected values when yfinance unavailable (not hardcoded 100.0)"

patterns-established:
  - "Algorithm separation: all math in judge_math.py, all I/O in judge.py"
  - "Regression guard test: explicit test_judge_no_hitl_p_045 prevents threshold regression"
  - "Sentinel pattern for mutable default arguments in test fixtures (use None check, not truthiness)"

# Metrics
duration: 35min
completed: 2026-03-18
---

# Phase 3 Plan 08: Judge Agent (7-step Bifásica Algorithm) Summary

**Pure 7-step Bayesian Consensus Algorithm separating log-normal value synthesis (Log Pool) from empirical probability estimation, with Kelly/3 position sizing and HITL at p<0.40 or circuit_breaker**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-03-18T00:00:00Z
- **Completed:** 2026-03-18
- **Tasks:** 2/2
- **Files modified:** 4 (2 source, 2 test)

## Accomplishments

- Implemented `judge_math.py` with 7 pure functions (no side effects): `data_quality_factor`, `log_pool`, `compute_p_success`, `check_circuit_breaker`, `compute_margin_of_safety`, `compute_recommendation`, `compute_map_of_ignorance`, and `run_judge_algorithm` as the full entry point
- Implemented `judge.py` LangGraph agent that reads typed state inputs, calls `run_judge_algorithm()`, determines HITL triggers (p<0.40 or circuit_breaker), retrieves RAG citations, and synthesizes LLM narrative via MODEL_PRO
- 43 total unit tests (35 for pure math, 8 for agent integration), all passing; includes regression guard for HITL threshold

## Task Commits

1. **Task 1: judge_math.py — pure 7-step algorithm** - `96f3afe` (feat)
2. **Task 2: judge.py agent + tests** - `3c3e3d5` (feat)

## Files Created/Modified

- `src/lockin/agents/judge_math.py` — Pure 7-step Bayesian Consensus Algorithm: Log Pool, p_success, circuit breaker, margin of safety, recommendation (BUY/HOLD/PASS), Map of Ignorance, JudgeOutput assembly
- `src/lockin/agents/judge.py` — LangGraph agent integrating judge_math with yfinance price fetching, RAG citations, MODEL_PRO LLM narrative, and HITL trigger logic
- `tests/unit/test_judge_math.py` — 35 unit tests for pure math: all steps individually (weights, mu bounds, VeTO exclusion, margin clamp, Kelly/3, convergence) + end-to-end `run_judge_algorithm`
- `tests/unit/test_judge.py` — 8 unit tests for agent: HITL triggers, regression guard (p=0.45 must NOT trigger HITL), recommendation alignment, state compatibility, default modifiers, RAG citations

## Decisions Made

- **judge_math.py pure (no side effects):** Entire algorithm testable without mocks — all 35 tests run in 0.05s with no network access. This separation is a hard architectural constraint, not optional.
- **HITL threshold 0.40 (NOT 0.50):** Notion spec v1.0 defines p_final < 0.40 as HOLD territory requiring human review. The old Foundation scaffold (plan 01-03) used conviction < 0.50; an explicit regression guard test `test_judge_no_hitl_p_045` ensures this threshold is never reverted.
- **compute_recommendation decision order matters:** `current_price > precio_target` (PASS for overvaluation) is checked BEFORE `p_final < 0.40` (HOLD for low probability). This order is correct: even low-probability cases that are overvalued should PASS, not HOLD.
- **KELLY_FRACTION = 0.33 (Kelly/3):** More conservative than Kelly/4 (0.25) since the system has no Phase 5 empirical base rates yet; the fraction can increase after backtesting.
- **data_quality_factor returns 0.5 when no sources tracked:** Prevents dividing by zero and avoids collapsing a distribution to weight=0 when DataCoverage.available is empty (e.g., state fallback distributions).
- **current_price fallback = geometric mean of bull/bear:** Better estimate than hardcoded 100.0 when yfinance is unavailable; uses the same log-space math as the algorithm itself.
- **Test fixture sentinel pattern:** `_make_bear_dist(missing=[])` must use `missing is None` (not `missing or ['competitive_threat']`) because empty list `[]` is falsy in Python and would incorrectly substitute the default missing items.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture `_make_bear_dist` used `or []` pattern causing empty list to be replaced by default**
- **Found during:** Task 1 (test_judge_math.py) during test run
- **Issue:** `_make_bear_dist(missing=[])` with `missing or ['competitive_threat']` treated empty list as falsy, substituting the default list, causing test_log_pool_equal_confidence_midpoint to fail because data quality factors were unequal
- **Fix:** Changed to explicit sentinel check `missing is None` in both `_make_bull_dist` and `_make_bear_dist` so `missing=[]` correctly produces an empty missing list
- **Files modified:** tests/unit/test_judge_math.py
- **Verification:** All 35 judge_math tests pass including the midpoint test
- **Committed in:** 96f3afe (part of Task 1 commit)

**2. [Rule 1 - Bug] test_judge_hitl_low_probability had incorrect HOLD assertion when overvaluation PASS fires first**
- **Found during:** Task 2 (test_judge.py) during test run
- **Issue:** Test used current_price=80, guardian margin_adjustment=0.25 which raised margin to 0.55, making precio_target = valor_mediano*(1-0.55) ≈ 72 < 80 = current_price, causing PASS (overvaluation) not HOLD (low probability) — PASS fires before HOLD in the decision tree
- **Fix:** Changed to current_price=10 (well below any reasonable target) and guardian margin_adjustment=0.0 so the overvaluation check does not fire and the HOLD path is reached
- **Files modified:** tests/unit/test_judge.py
- **Verification:** All 8 judge agent tests pass
- **Committed in:** 3c3e3d5 (part of Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — test bugs)
**Impact on plan:** Both auto-fixes were test correctness issues, not algorithm bugs. Implementation is exactly per spec. No scope creep.

## Issues Encountered

None beyond the two test fixture bugs documented above.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- `judge_math.run_judge_algorithm()` is ready for Optimizer consumption: `JudgeOutput.kelly_fraction`, `.recommendation`, `.circuit_breaker` all populated
- `judge()` LangGraph agent can be wired into `builder.py` to replace `mock_judge`
- HITL threshold now 0.40 (not 0.50 from Foundation scaffold) — integration tests in plan 03-12 should verify the new threshold
- Plan 03-09 (Optimizer) can proceed: it reads `judge_output` from state

---
*Phase: 03-agents-rag*
*Completed: 2026-03-18*
