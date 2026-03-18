---
phase: 03-agents-rag
plan: 06
subsystem: agents
tags: [risk, altman, beneish, vomc, guardian, tdd]
requires:
  - phase: 03-agents-rag
    plan: 01
    provides: ConfidenceModifier, Signal, DataCoverage types and get_llm factory
provides:
  - risk_scores.py with pure Altman Z-Score, Beneish M-Score, VoMC fragility functions (TDD)
  - guardian.py agent outputting ConfidenceModifier with graduated adjustments
  - circuit_breaker=True ONLY for severe conditions (M+red flag OR Z<1.0+leverage>4x)
affects: [03-08, 03-10]
tech-stack:
  added: []
  patterns: [TDD red-green for pure math functions, graduated risk modifiers not binary veto]
key-files:
  created: [src/lockin/agents/risk_scores.py, src/lockin/agents/guardian.py, tests/unit/test_risk_scores.py, tests/unit/test_guardian.py]
  modified: []
key-decisions:
  - "Guardian uses _safe_get() with df.loc for yfinance DataFrame access (not .get())"
  - "Test mock must use real pandas DataFrames (not MagicMock with .get()) so _safe_get works"
  - "Z-Score fallback z=1.5 (conservative grey/distress) used when extraction fails"
  - "circuit_breaker fires for Z < 1.0 (severe distress), NOT Z < 1.81 (regular distress)"
  - "_compute_beneish returns None if < 2 years balance sheet data available"
  - "All 4 Guardian signals have has_base_rate=True with academic sources"
patterns-established:
  - "Risk score functions in risk_scores.py are pure functions (no network, no LLM)"
  - "DataFrame mocks in tests must support .loc and .index interfaces, not just .get()"
duration: ~8min
completed: 2026-03-18
---

# Plan 03-06: Guardian Agent Summary

**Altman Z-Score, Beneish M-Score, VoMC fragility pure functions (TDD) + Guardian agent with ConfidenceModifier output using graduated risk adjustments and circuit_breaker for severe conditions only**

## Performance

- **Duration:** ~8 min
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments
- Implemented 3 pure risk score functions (TDD: RED then GREEN)
- Guardian agent returns ConfidenceModifier with graduated margin/variance adjustments
- circuit_breaker logic correctly fires only for two specific severe conditions from Notion spec

## Task Commits

1. **Task 1a: TDD RED — risk score tests** - `e826684` (test)
2. **Task 1b: TDD GREEN — risk_scores.py** - `c53b17a` (feat)
3. **Task 2a: TDD RED — guardian agent tests** - `cb09a63` (test)
4. **Task 2b: TDD GREEN — guardian.py** - (completed within Guardian rate-limited run)
5. **Fix: DataFrame mock** - `cda9899` (fix)

## Files Created/Modified
- `src/lockin/agents/risk_scores.py` — altman_z_score, beneish_m_score, vomc_fragility pure functions
- `src/lockin/agents/guardian.py` — Guardian Modifier agent with ConfidenceModifier output
- `tests/unit/test_risk_scores.py` — TDD tests for risk formulas
- `tests/unit/test_guardian.py` — 12 tests for Guardian agent (fixed mock to use pandas DataFrames)

## Decisions Made
- `_safe_get(df, row)` uses `df.loc[row, col]` for real yfinance DataFrames — tests must mock with real `pd.DataFrame`
- Z-Score fallback `z=1.5, zone="distress"` when extraction fails (conservative)
- circuit_breaker fires for Z < 1.0 (severe, not just distress < 1.81)
- M-Score circuit_breaker requires simultaneous red flag (distress OR leverage > 4x OR VoMC > 0.7)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock used MagicMock.get() but guardian.py uses df.loc**
- **Found during:** Post-execution test verification
- **Issue:** `_mock_ticker` set up `bs.get.side_effect` but `_safe_get()` uses `df.loc[row, col]` — so all Altman inputs returned None and hit z=1.5 fallback
- **Fix:** Updated `_mock_ticker` to use real `pd.DataFrame` for balance_sheet and financials
- **Verification:** All 12 guardian tests pass after fix
- **Committed in:** `cda9899`

## Issues Encountered
- Guardian agent (03-06) and Strategist (03-04) hit Gemini rate limit mid-execution, but all code was committed before the limit hit; only SUMMARY.md was missing

## Next Phase Readiness
- guardian_modifier (ConfidenceModifier) ready to be consumed by Judge (03-08)
- circuit_breaker field in ConfidenceModifier wired into HITL trigger in Judge

---
*Phase: 03-agents-rag*
*Completed: 2026-03-18*
