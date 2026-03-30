---
phase: 03-agents-rag
plan: 04
subsystem: agents
tags: [strategist, veto, analyst-momentum, confidence-modifier, fmp, yfinance, gemini, jegadeesh]

requires:
  - phase: 03-agents-rag
    plan: 01
    provides: ConfidenceModifier, Signal, DataCoverage dataclasses; get_llm factory; MODEL_FLASH constant

provides:
  - Strategist agent (strategist.py) outputting ConfidenceModifier per Notion Judge spec
  - FMP earnings transcript fetching with module-level dict cache and graceful fallback
  - yfinance analyst recommendations_summary processing for net upgrade/downgrade momentum
  - LLM (MODEL_FLASH) JSON sentiment + VeTO scoring with error handling
  - 8 unit tests verifying all design constraints (VeTO no-base-rate, variance-only, no-margin, etc.)

affects: [03-07, 03-11]

tech-stack:
  added: []
  patterns:
    - VeTO design pattern: has_base_rate=False, adjusts variance only (not probability or margin)
    - Modifier agent contract: ConfidenceModifier with typed Signal list, DataCoverage, reasoning
    - Graceful degradation: each data source independently fallible, agent always returns valid output
    - Module-level dict cache for external API calls (FMP transcript cache)
    - LLM JSON parsing with markdown code block stripping and field defaults on failure

key-files:
  created:
    - src/lockin/agents/strategist.py
    - tests/unit/test_strategist.py

key-decisions:
  - veto-no-base-rate-variance-only
  - veto-margin-deferred-to-phase-4
  - analyst-momentum-jegadeesh-2004-source
  - circuit-breaker-always-false-for-strategist
  - module-level-transcript-cache

patterns-established:
  - "VeTO design: has_base_rate=False, adjusts variance_adjustment only (+0.10 if score < 0.4); no margin contribution"
  - "Analyst momentum: has_base_rate=True, base_rate_source='Jegadeesh (2004)'; adjusts margin (+0.05 for downgrades)"
  - "Modifier agent: always returns ConfidenceModifier with circuit_breaker=False; Guardian owns circuit breaking"
  - "Graceful degradation: each source has try/except, missing sources tracked in DataCoverage.missing"

duration: 8min
completed: 2026-03-17
---

# Phase 3 Plan 4: Strategist Agent Summary

**One-liner:** Strategist Modifier agent with VeTO (has_base_rate=False, variance-only, no margin) and Jegadeesh (2004) analyst momentum signal — implemented per Notion Judge spec with FMP + yfinance + MODEL_FLASH LLM, 8/8 unit tests passing.

---

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-17T11:38:40Z
- **Completed:** 2026-03-17T11:47:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

---

## Accomplishments

- Implemented `strategist()` as a LangGraph-compatible Modifier agent (state, config) -> dict outputting a typed `ConfidenceModifier` — not scalar scores.
- Enforced the two critical VeTO constraints from the Notion Judge spec: `has_base_rate=False` (no probability adjustment) and variance-only adjustment (`+0.10` when `veto_score < 0.4`; VeTO does NOT touch `margin_adjustment` per CONTEXT.md Phase 4 deferral).
- Analyst momentum signal (`analyst_momentum`) has `has_base_rate=True`, `base_rate_source="Jegadeesh (2004)"` — the only signal that adjusts `margin_adjustment` (+0.05 for net analyst downgrades).
- 8 unit tests pass, each targeting a specific design constraint from the Notion Judge spec.

---

## Task Commits

1. **Task 1: Strategist agent** — `0d4ad6b` (feat)
2. **Task 2: Unit tests** — `d858e03` (feat)

---

## Files Created/Modified

- `/home/mateo/dev/LockIn/src/lockin/agents/strategist.py` — Strategist agent with FMP fetch, yfinance analyst consensus, LLM sentiment/VeTO scoring, ConfidenceModifier assembly
- `/home/mateo/dev/LockIn/tests/unit/test_strategist.py` — 8 unit tests covering all design constraints

---

## Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| VeTO has_base_rate | False | VeTO is informational only in Phase 3 — no empirical validation, so it cannot adjust probability. Only adjusts variance to signal increased uncertainty. |
| VeTO variance threshold | `veto_score < 0.4` adds `+0.10` | Consistent with plan spec. Low VeTO means unhealthy org signal → widen uncertainty. High VeTO (healthy) → no change. |
| VeTO margin deferred | margin_adjustment unchanged by VeTO | CONTEXT.md explicitly defers VeTO margin-of-safety wiring to Phase 4. Strategist.py documents this clearly in code comments. |
| analyst_momentum base rate | has_base_rate=True, source "Jegadeesh (2004)" | Analyst revision momentum has academic support (Jegadeesh 2004 momentum paper). Phase 5 will backfill empirical win rate. |
| margin_adjustment trigger | `analyst_momentum < 0` only | Net analyst downgrades (sell > buy) signal deteriorating consensus → add 0.05 to margin for safety. No adjustment for neutral or upgrades. |
| circuit_breaker | Always False | Guardian is the circuit-breaker agent. Strategist never has veto power over the investment decision. |
| Module-level transcript cache | `_TRANSCRIPT_CACHE: dict[str, str]` | FMP free tier is 250 req/day — caching per ticker within a process avoids redundant calls during pipeline re-runs. |
| LLM JSON parsing | Strip markdown code blocks + fill defaults on failure | Gemini sometimes wraps JSON in ```json blocks. Stripping ensures clean parse. Defaults on parse failure ensure agent never crashes. |

---

## Deviations from Plan

None — plan executed exactly as specified.

---

## Verification Results

```
python -m pytest tests/unit/test_strategist.py -v    8/8 passed (3.84s)
import lockin.agents.strategist                       OK
ConfidenceModifier construction                       OK
VeTO has_base_rate=False                              OK (verified in test 2 + programmatically)
VeTO variance conditional (only when score < 0.4)    OK (verified in test 3)
VeTO NO margin contribution                           OK (verified in test 4)
analyst_momentum has_base_rate=True, Jegadeesh        OK (verified in test 5)
margin_adjustment: +0.05 for downgrades only          OK (verified in test 6)
Graceful fallback without FMP key                     OK (verified in test 7)
circuit_breaker always False                          OK (verified in test 8)
```

---

## Next Phase Readiness

**Phase 3 Plan 07 (Judge agent):** Strategist output is ready.
- `strategist_modifier: Optional[ConfidenceModifier]` exists in `InvestmentState`
- Judge can read `strategist_modifier.variance_adjustment` and `strategist_modifier.margin_adjustment`
- Judge can read `strategist_modifier.signals` to find VeTO and analyst_momentum signals
- VeTO variance wiring: Judge applies `strategist_modifier.variance_adjustment` to widen posterior
- VeTO margin wiring: deferred to Phase 4 (Judge should NOT use VeTO for margin in Phase 3)
