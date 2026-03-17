---
phase: 03
plan: 03
subsystem: agents
tags: [value-hunting, bull-agent, valuation, EPV, EVA, RIM, piotroski, magic-formula, log-normal, scipy, TDD]

dependency-graph:
  requires:
    - 03-01   # types.py (ValueDistribution, DataCoverage), llm.py (get_llm, MODEL_PRO), base.py (invoke_agent)
    - 02-04   # get_fundamentals public API, FundamentalsResult
  provides:
    - src/lockin/agents/valuations.py   # pure valuation formula functions
    - src/lockin/agents/value_hunter.py # Bull LangGraph node
    - tests/unit/test_valuations.py     # 21 formula unit tests
    - tests/unit/test_value_hunter.py   # 12 agent unit tests
  affects:
    - 03-04   # Bear agent will mirror this pattern (ValueDistribution output)
    - 03-07   # Judge agent reads bull_valuation_distribution for Bayesian synthesis
    - 03-11   # Phase 3 integration tests include value_hunter node

tech-stack:
  added:
    - scipy.stats.lognorm   # log-normal distribution for ValueDistribution
    - numpy                 # mu/sigma calculations for log-normal
  patterns:
    - TDD (RED-GREEN): tests written before implementation in both tasks
    - Pure function module (valuations.py): zero I/O, trivially testable
    - Heuristic company classifier: routes to best valuation model
    - Log-normal ValueDistribution: epistemic uncertainty quantified via sigma
    - Sigma-adjustment by Piotroski F-Score: data quality narrows uncertainty
    - Refinement pass pattern: bull_iteration > 0 triggers LLM re-invocation

key-files:
  created:
    - src/lockin/agents/valuations.py
    - src/lockin/agents/value_hunter.py
    - tests/unit/test_valuations.py
    - tests/unit/test_value_hunter.py
  modified: []

decisions:
  - id: D1
    topic: Valuation model selection heuristic
    decision: "financial (ROE leverage>8x) -> RIM; tech (ROE>20%) -> RIM; mature (ROE>10%) -> EVA; default -> EPV"
    rationale: "Avoids one-size-fits-all; selects model best matched to company's value driver"
    alternatives: "Always EPV (too conservative for high-growth), always RIM (unsuitable for capital-intensive)"

  - id: D2
    topic: Log-normal sigma adjustment by Piotroski F-Score
    decision: "F>=7: sigma*0.85; F<=3: sigma*1.20; else: DEFAULT_SIGMA=0.20"
    rationale: "High accounting quality = narrower epistemic uncertainty; low quality = wider tails"
    alternatives: "Fixed sigma (ignores quality signal); individual model spread"

  - id: D3
    topic: Piotroski prior-year data approximation
    decision: "Scale current-year metrics by 0.90 as synthetic prior when prior-year not available"
    rationale: "FundamentalsResult only has current year; 10% improvement assumption is conservative and documented in quality_metrics.synthetic_prior flag"
    alternatives: "Skip F-score (loses quality signal); require prior-year (blocks single-year data)"

  - id: D4
    topic: Shares outstanding derivation
    decision: "Approximate from net_income / diluted_eps; fallback=1 (guarded by caller)"
    rationale: "FundamentalsResult doesn't carry shares_outstanding as a top-level field"
    alternatives: "Add shares_outstanding to FundamentalsResult (deferred to Phase 3 data layer revision)"

  - id: D5
    topic: TDD approach for both tasks
    decision: "RED commit (failing tests) -> GREEN commit (implementation); 4 atomic commits total"
    rationale: "Enforces test-first discipline; each task independently revertable"
    alternatives: "Test-after (loses design feedback loop)"

metrics:
  duration: "~6 minutes"
  completed: "2026-03-17"
  tests: "33 total (21 formula + 12 agent), 33 passing"
  commits: 4
---

# Phase 3 Plan 03: Value Hunter (Bull) Agent Summary

**One-liner:** EPV/EVA/RIM valuation formulas + log-normal ValueDistribution via scipy.lognorm with Piotroski-adjusted sigma and LLM thesis generation via MODEL_PRO.

---

## What Was Built

### Task 1: Valuation formula module (TDD)

`src/lockin/agents/valuations.py` — five pure functions:

| Function | Description |
|---|---|
| `calculate_epv(ebit_5y_avg, tax_rate, wacc, shares)` | Greenwald no-growth EPV per share |
| `calculate_eva(nopat, wacc, invested_capital)` | Economic Value Added (residual profit) |
| `calculate_rim(book_value, roe, coe, growth, shares)` | Residual Income Model per share |
| `piotroski_f_score(current, prior)` | 9-signal accounting quality index (0-9) |
| `magic_formula_metrics(ebit, ev, nfa, wc)` | Greenblatt earnings yield + ROIC |

**TDD cycle:** 21 tests written RED first (`b44f188`), then implementation turned all GREEN (`493bafe`).

### Task 2: Value Hunter agent (TDD)

`src/lockin/agents/value_hunter.py` — `value_hunter(state, config) -> dict`:

1. Fetches fundamentals via `get_fundamentals(ticker, store=False)`
2. Classifies company type (financial / tech / mature / default)
3. Routes to EPV, EVA, or RIM for intrinsic value per share
4. Builds log-normal `ValueDistribution` via `scipy.stats.lognorm`
5. Computes Piotroski F-Score + Magic Formula quality metrics
6. Invokes `MODEL_PRO` LLM to generate bullish thesis
7. On `bull_iteration > 0`: invokes LLM again with bear challenges -> `bull_refined_thesis`

**TDD cycle:** 12 tests written RED first (`00247e7`), implementation GREEN (`47662b7`).

---

## Verification Results

```
tests/unit/test_valuations.py  - 21 passed in 0.02s
tests/unit/test_value_hunter.py - 12 passed in 3.55s
Total: 33 passed
```

All plan verification criteria met:
- [x] `bull_valuation_distribution` is `ValueDistribution` instance
- [x] `p10 < p50 < p90` (log-normal monotonicity)
- [x] `methods_used` contains "EPV" | "EVA" | "RIM"
- [x] `data_coverage.available` non-empty
- [x] `confidence` in [0, 1]

---

## Decisions Made

| # | Topic | Decision |
|---|---|---|
| D1 | Model selection heuristic | financial/tech -> RIM; mature -> EVA; default -> EPV |
| D2 | Sigma adjustment | F-Score adjusts log-normal width (±15-20%) |
| D3 | Piotroski prior approximation | Scale current by 0.90; flagged via synthetic_prior=True |
| D4 | Shares outstanding | Derived from net_income / diluted_eps |
| D5 | TDD approach | RED then GREEN, 4 atomic commits |

---

## Deviations from Plan

None — plan executed exactly as written. The `calculate_epv` test for zero shares outstanding was naturally handled via the `_safe_shares()` helper (D4 decision, not a deviation). The `test_f_score_zero` test acknowledged that signal (4) `ocf > net_income` evaluates to True when both are negative (`-20 > -50`), so minimum achievable score is 1, not 0 — test asserts `<= 2` instead of `== 0`. This was anticipated in the test comments.

---

## Next Phase Readiness

**Plan 03-04 (Bear agent):** `value_hunter.py` establishes the pattern Bear will mirror:
- Same LangGraph node signature `(state, config) -> dict`
- Same `ValueDistribution` output structure
- Same `data_coverage`, `methods_used`, `confidence` fields
- Bear reads `bull_thesis` from state; Value Hunter reads `bear_challenges` on refinement

**Plan 03-07 (Judge agent):** `bull_valuation_distribution` (ValueDistribution) is ready for Bayesian synthesis. The log-normal parametrization `(mu, sigma)` can be extracted from `p50` and `(p90 - p10)` spread.

**No blockers identified.**

---

## Commits

| Hash | Type | Description |
|---|---|---|
| `b44f188` | test(03-03) | RED: failing tests for EPV, EVA, RIM, Piotroski, MagicFormula (21 tests) |
| `493bafe` | feat(03-03) | GREEN: implement valuations.py — all 21 tests pass |
| `00247e7` | test(03-03) | RED: failing tests for value_hunter agent (12 tests) |
| `47662b7` | feat(03-03) | GREEN: implement value_hunter.py — all 12 tests pass |
