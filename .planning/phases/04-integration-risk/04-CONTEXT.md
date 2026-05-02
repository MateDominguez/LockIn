# Phase 4: Integration & Risk Management - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrate all 7 agents into a cohesive multi-ticker pipeline, wire the VeTO margin of safety
adjustment, finalize adaptive margin bounds, and establish integration test coverage. Agents are
already individually implemented (Phase 3) — this phase is about making them work together
correctly at the pipeline level.

Backtesting, paper trading, and the Streamlit dashboard are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Multi-ticker Orchestration
- **D-01:** Shared Macro Oracle — runs once, result shared across all tickers. Macro regime
  (expansion/contraction, yield curve, fed stance) is market-wide, not per-ticker.
- **D-02:** Parallel fan-out per ticker — after Macro Oracle, each ticker runs its own
  Value Hunter → Bear → Strategist → Guardian → Judge pipeline concurrently.
- **D-03:** Portfolio-level Optimizer — runs once after all per-ticker Judges complete,
  aggregates across tickers for portfolio construction with sector limits and concentration caps.
- **D-04:** Rate limiting via semaphore + exponential backoff — `asyncio.Semaphore` controls
  concurrent LLM calls (default: 2 concurrent). Exponential backoff on 429 errors.
  Keep Gemini Flash for dev (500 RPD free tier). ~41 LLM calls for a 5-ticker portfolio.
- **D-05:** Multi-provider `get_llm()` factory deferred to Phase 5 — architecture should allow
  it, but Phase 4 stays on Gemini Flash only. DeepSeek R1 ($0.07/run) identified as top paid
  reasoning candidate for future upgrade.

### VeTO Margin Wiring
- **D-06:** Symmetric margin adjustment — low VeTO penalizes (increases margin), high VeTO
  modestly rewards (decreases margin). Reward magnitude is half the penalty magnitude.
  Thresholds:
  - VeTO < 0.3 → margin_adjustment = +0.10 (very opaque)
  - VeTO < 0.4 → margin_adjustment = +0.05 (poor visibility)
  - VeTO 0.4–0.7 → margin_adjustment = 0.00 (neutral)
  - VeTO > 0.7 → margin_adjustment = -0.03 (clear outcomes)
  - VeTO > 0.85 → margin_adjustment = -0.05 (very transparent)
- **D-07:** Keep both variance_adjustment AND margin_adjustment for VeTO — they affect
  different Judge algorithm steps (Step 1 Log Pool vs Step 4 Margin) and are complementary,
  not redundant. Low VeTO compounds: wider uncertainty band + higher safety hurdle.
- **D-08:** VeTO margin logic lives inline in `strategist.py` — matches existing pattern
  where each modifier agent owns its own adjustment logic.
- **D-09:** `has_base_rate` stays False for VeTO — no empirical validation yet. VeTO does
  NOT adjust p_success (Step 2). Upgrade to True when backtesting validates predictive power.
- **D-10:** Hardcoded VeTO threshold values (0.3, 0.4, 0.7, 0.85) are provisional — add a
  TODO/future review note. Revisit after backtest data is available.

### Adaptive Margin of Safety
- **D-11:** Margin bounds changed from [0.20, 0.70] to [0.15, 0.60] — widens the lower bound
  modestly (15% minimum discount vs 20%) to give high-conviction setups room, tightens the
  upper bound from 0.70 (rarely reached) to 0.60.
- **D-12:** Existing clamp is sufficient — no per-agent caps or weighted sums needed. If all
  three agents independently signal caution, stacking to 0.60 IS the correct behavior.
- **D-13:** Margin breakdown dict added to JudgeOutput — structured `margin_breakdown` field
  with each agent's contribution (base, oracle, guardian, strategist, raw_total, clamped).
  Already computed in `judge_math.py` lines 460-462 — surface in typed output.
- **D-14:** Valuation model accuracy is the long-term fix for margin sizing — tracked as a
  future improvement. Better Value Hunter estimates reduce the need for large margins.
  Revisit bounds after backtesting reveals actual prediction accuracy.

### Integration Test Strategy
- **D-15:** Two test layers for Phase 4:
  1. **Contract tests** (`tests/unit/test_contracts.py`) — verify each real agent's output
     matches typed contracts (ConfidenceModifier, ValueDistribution, JudgeOutput). Test margin
     math with real modifier combinations, VeTO wiring thresholds, bounds [0.15, 0.60].
     Zero LLM calls, runs in CI.
  2. **Live smoke test** (`tests/e2e/test_live_smoke.py`) — `@pytest.mark.slow`, excluded
     from CI. Full single-ticker run with real APIs. Default ticker AAPL, configurable via
     `SMOKE_TICKER` env var.
- **D-16:** Recorded replay E2E deferred to Phase 5+ — agent prompts still changing too
  rapidly, fixture maintenance cost not justified until prompts stabilize.
- **D-17:** Smoke test uses structure + golden range assertions:
  - `judge_recommendation in (BUY, HOLD, PASS)`
  - `judge_conviction in [0.0, 1.0]`
  - `margin_of_safety in [0.15, 0.60]`
  - `position_size in [0.0, 0.10]`
  - `veto_score in [0.0, 1.0]`
  - `margin_breakdown` dict has all 3 agent keys
  - `optimizer_portfolio` is non-empty
  - `bull_thesis` and `bear_thesis` are non-empty strings
  - No unhandled exceptions
- **D-18:** If margin/sizing constants change, smoke test golden ranges must be reviewed.
  Add a comment in the test file pointing to the source constants.

### Claude's Discretion
- Concurrency implementation details for multi-ticker fan-out (asyncio vs threading)
- Exact semaphore limit tuning (start with 2, adjust based on rate limit behavior)
- Contract test fixture generation approach (snapshot from dev runs vs hand-crafted)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Graph
- `.planning/PROJECT.md` — 7-agent architecture, constitution, key design decisions
- `src/lockin/graph/builder.py` — Graph factory, conditional edges, Bull-Bear dialectic loop, HITL
- `src/lockin/graph/state.py` — InvestmentState TypedDict definition

### Agent Implementations (Phase 3)
- `src/lockin/agents/strategist.py` §290-306 — Current VeTO logic (margin_adjustment=0.0 deferred comment)
- `src/lockin/agents/judge_math.py` — 7-step Bayesian algorithm, margin constants, Kelly/3
- `src/lockin/agents/guardian.py` — Circuit breaker logic, graduated adjustments
- `src/lockin/agents/optimizer.py` — Kelly sizing, position limits, sector allocation
- `src/lockin/agents/types.py` — ConfidenceModifier, ValueDistribution, JudgeOutput contracts
- `src/lockin/agents/llm.py` — LLM factory, MODEL_PRO/FLASH, GEMINI_FORCE_FLASH fallback

### Prior Context
- `.planning/phases/03-agents-rag/03-CONTEXT.md` — VeTO informational-only decision, Bear blind to Bull
- `.planning/phases/02-data-layer/02-CONTEXT.md` — Protocol abstraction, TTL caching, PIT enforcement

### Requirements
- `.planning/REQUIREMENTS.md` — AGENTS-06 (Judge), AGENTS-07 (Optimizer), RISK-01 through RISK-04

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `create_graph()` in `builder.py`: already supports `agent_overrides` dict for test injection
- `audit_node()` wrapper: all agents already wrapped with audit logging
- `ConfidenceModifier` dataclass: typed contract used by all modifier agents (Oracle, Guardian, Strategist)
- `compute_margin_of_safety()` in `judge_math.py`: simple additive function, easy to modify bounds
- `get_llm()` factory in `llm.py`: single point of control for model selection

### Established Patterns
- Each modifier agent owns its adjustment logic inline (thresholds, magnitude)
- Judge accumulates all `margin_adjustment` values additively with global clamp
- `agent_overrides` dict pattern for test injection without modifying graph structure
- `@pytest.mark.slow` convention already exists in test suite

### Integration Points
- `strategist.py` line 300: deferred comment to replace with VeTO margin logic
- `judge_math.py` lines 46-49: `_MARGIN_MIN` and `_MARGIN_MAX` constants to update
- `judge_math.py` lines 460-462: margin breakdown already computed, needs surfacing in JudgeOutput
- `builder.py`: graph needs multi-ticker fan-out wrapper (new orchestration layer above single-ticker graph)
- `types.py` JudgeOutput: add `margin_breakdown` field

</code_context>

<specifics>
## Specific Ideas

- **VeTO asymmetry is intentional:** penalty magnitude (+0.10 max) is 2x the reward magnitude
  (-0.05 max). Opacity is a stronger signal than clarity — absence of risk isn't confirmation of safety.
- **Margin bounds rationale:** 15% floor means even the best setup requires meaningful discount.
  The long-term path to lower margins is improving the valuation model accuracy, not loosening bounds.
- **Provider analysis on Notion:** LLM cost analysis was captured as a Notion page in Joaquin's
  workspace. DeepSeek R1 at $0.07/run for reasoning tasks is the leading candidate when free
  tier limits are hit.
- **Constants review discipline:** VeTO thresholds and margin bounds are starting points.
  Both carry a "revisit after backtest" note. Don't over-tune before empirical data exists.

</specifics>

<deferred>
## Deferred Ideas

- Multi-provider `get_llm()` factory (DeepSeek R1, Groq, OpenRouter) — Phase 5 or when rate limits are hit
- Recorded replay E2E tests — Phase 5+ when agent prompts stabilize
- VeTO `has_base_rate=True` upgrade — after backtesting validates predictive power
- Insider trading signals and news sentiment for VeTO — v2
- Valuation model accuracy improvement (Value Hunter) — Phase 5+
- Margin bounds re-calibration based on backtest prediction accuracy — Phase 5+

</deferred>

---

*Phase: 04-integration-risk*
*Context gathered: 2026-05-01*
