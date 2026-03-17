---
phase: 03-agents-rag
plan: 02
subsystem: agents
tags: [macro, fred, llm, confidence-modifier, regime-detection, gemini-flash, ray-dalio]

requires:
  - phase: 03-01
    provides: ConfidenceModifier, Signal, DataCoverage dataclasses; get_llm, invoke_agent, MODEL_FLASH; InvestmentState.oracle_modifier field
  - phase: 02-04
    provides: get_macro_indicators() public API, MacroResult TypedDict, DataUnavailableError

provides:
  - Macro Oracle agent (macro_oracle) that detects economic regime from FRED data
  - ConfidenceModifier output with margin_adjustment, variance_adjustment, circuit_breaker=False
  - Three signals: macro_base_rate (has_base_rate=True, FRED), style_regime, flow_direction
  - FRED data unavailability fallback (macro_confidence=0.3, neutral modifier)
  - 6 unit tests covering all ConfidenceModifier contract assertions

affects:
  - 03-07: Judge agent consumes oracle_modifier to weight macro regime in Bayesian synthesis
  - 03-11: Phase 3 integration tests include macro oracle in full pipeline test

tech-stack:
  added: []
  patterns:
    - "Deterministic + LLM hybrid: rule-based regime (yield_curve, fed_stance) overrides LLM for unambiguous signals; LLM handles subjective classification (phase, risk_appetite)"
    - "Oracle never triggers circuit_breaker (always False) — Oracle adjusts trust, never blocks"
    - "DataUnavailableError fallback returns macro_confidence=0.3 so Judge minimizes macro weight"
    - "Margin adjustment ranges: expansion+risk_on+normal → +0.175, contraction+risk_off+inverted → -0.05"

key-files:
  created:
    - src/lockin/agents/macro_oracle.py
    - tests/unit/test_macro_oracle.py
  modified: []

key-decisions:
  - "MODEL_FLASH chosen for Macro Oracle (not PRO) — structured quantitative task, consistent with Context.md LLM strategy"
  - "Deterministic yield_curve rule: inverted if yield_10y_2y<0 OR yield_10y_3m<0 — not LLM-dependent"
  - "Deterministic fed_stance rule: hawkish if fed_funds>4.0, dovish if <2.0, else neutral"
  - "margin_adjustment=+0.175 for extreme greed (midpoint of [+0.15, +0.20] spec range)"
  - "macro_confidence clamped to [0.3, 0.95] — 0.3 floor prevents zero-weight; 0.95 cap prevents overconfidence"
  - "variance_adjustment=+0.05 only for inverted yield curve + (contraction or hawkish) — high volatility regime signal"

patterns-established:
  - "Modifier agent pattern: returns oracle_modifier (ConfidenceModifier) + macro_regime (dict) + macro_confidence (float) + macro_narrative (str)"
  - "JSON parse fallback: try json.loads() first, then regex extraction of individual fields"
  - "Data coverage tracking: DataCoverage.available/missing lists built from MacroResult field presence"

duration: 5min
completed: 2026-03-17
---

# Phase 3 Plan 02: Macro Oracle Agent Summary

**Macro Oracle Modifier agent that detects economic regime (expansion/contraction via Dalio framework) from FRED indicators, outputs ConfidenceModifier with deterministic yield-curve rules and LLM-classified risk appetite.**

## Performance

- **Duration:** ~5 min (implementation pre-committed by prior session; verification + tests executed this session)
- **Started:** 2026-03-17T11:37:26Z
- **Completed:** 2026-03-17T11:42:41Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- Macro Oracle agent with deterministic + LLM hybrid regime detection
- ConfidenceModifier output: margin_adjustment ranges from -0.05 (extreme fear) to +0.175 (extreme greed); circuit_breaker always False
- Three typed signals: macro_base_rate (has_base_rate=True, base_rate_source=FRED), style_regime, flow_direction
- FRED unavailability fallback: macro_confidence=0.3, neutral ConfidenceModifier with zero adjustments
- 6 unit tests covering all plan must-haves — all pass in 3.42s

## Task Commits

Prior session committed both files before this execution (files were identical to plan spec):

1. **Task 1: Macro Oracle agent** - `0d4ad6b` (feat: macro_oracle.py created alongside strategist)
2. **Task 2: Unit tests** - `3a9524d` (feat: test_macro_oracle.py committed alongside RAG ingestion)

_Note: Both tasks were pre-committed by prior execution sessions. This session verified correctness by running all 6 tests (6/6 pass) and all plan verification criteria._

## Files Created/Modified

- `src/lockin/agents/macro_oracle.py` - Macro Oracle agent: FRED fetch, deterministic rules, LLM classification, ConfidenceModifier builder, FRED fallback
- `tests/unit/test_macro_oracle.py` - 6 unit tests: expansion regime, inverted yield curve, DataUnavailableError fallback, ConfidenceModifier contract, extreme greed margin, extreme fear margin

## Decisions Made

- **MODEL_FLASH** for Macro Oracle — quantitative/structured task; PRO quota reserved for Value Hunter, Bear, Judge (per 03-CONTEXT.md)
- **Deterministic overrides LLM** for yield_curve and fed_stance — these are purely rule-based (spread arithmetic, rate thresholds), no judgment required; LLM handles subjective classification (phase, risk_appetite)
- **margin_adjustment=+0.175** — midpoint of the [+0.15, +0.20] spec range for extreme greed; avoids arbitrary edge selection
- **macro_confidence clamped [0.3, 0.95]** — 0.3 floor ensures minimal weight even without data; 0.95 cap prevents overconfidence regardless of data completeness
- **variance_adjustment=+0.05 only for inverted + (contraction OR hawkish)** — inverted curve alone (in late expansion) doesn't warrant higher variance

## Deviations from Plan

None - plan executed exactly as written. The agent implementation matches the plan specification in all respects.

## Issues Encountered

None. Both files were pre-committed by prior sessions with identical content to what the plan specified. All 6 unit tests pass against the committed implementation.

## User Setup Required

None - no external service configuration required. FRED API key is used at runtime; if absent, the agent gracefully falls back to macro_confidence=0.3.

## Next Phase Readiness

- oracle_modifier (ConfidenceModifier) ready to be consumed by Judge agent (03-07)
- InvestmentState.oracle_modifier field already typed (from 03-01)
- macro_oracle() function importable: `from lockin.agents.macro_oracle import macro_oracle`
- No blockers for 03-03 (Value Hunter) — Macro Oracle is independent

---
*Phase: 03-agents-rag*
*Completed: 2026-03-17*
