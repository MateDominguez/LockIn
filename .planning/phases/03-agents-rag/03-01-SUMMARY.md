---
phase: 03-agents-rag
plan: 01
subsystem: agents
tags: [llm, gemini, dataclasses, langchain, settings, edgar, pypdf, langchain-text-splitters]
requires:
  - phase: 02-data-layer
    provides: data layer public API
provides:
  - LLM factory (get_llm) with model selection and temperature
  - Agent types (ValueDistribution, ConfidenceModifier, Signal, DataCoverage, JudgeOutput)
  - Updated Settings with fmp_api_key and 7 per-agent model fields
  - Updated InvestmentState with typed agent output fields
  - invoke_agent() utility with tenacity retry for rate-limit handling
  - BASE_RATE_TABLE with 10 academic base-rate entries
affects: [03-02, 03-03, 03-04, 03-05, 03-06, 03-07, 03-08, 03-09, 03-10, 03-11]
tech-stack:
  added: [edgar, pypdf>=4.0.0, langchain-text-splitters>=0.3.0]
  patterns: [LLM factory pattern, typed agent output contracts, lazy __getattr__ for circular import resolution]
key-files:
  created:
    - src/lockin/agents/llm.py
    - src/lockin/agents/base.py
    - src/lockin/agents/types.py
  modified:
    - pyproject.toml
    - src/lockin/utils/config.py
    - src/lockin/agents/__init__.py
    - src/lockin/graph/state.py
    - src/lockin/graph/__init__.py
key-decisions:
  - lazy-getattr-for-circular-imports
  - runtime-type-imports-for-langgraph-compatibility
  - types-module-eagerly-imported-in-agents-init
patterns-established:
  - LLM factory: get_llm(model, temperature) abstracts API key validation and construction
  - Two-axis architecture: Distribution agents -> ValueDistribution, Modifier agents -> ConfidenceModifier
  - BASE_RATE_TABLE: placeholder academic priors, None for TBD values, source citations included
duration: 6min
completed: 2026-03-17
---

# Phase 3 Plan 1: Shared Agent Infrastructure Summary

**One-liner:** Typed agent output contracts (ValueDistribution/ConfidenceModifier), Gemini LLM factory, tenacity-retried invoke_agent(), and BASE_RATE_TABLE priors — the shared foundation for all Wave 2 agents.

---

## What Was Built

Set up the complete shared infrastructure layer that every real agent in Wave 2 will import:

1. **`src/lockin/agents/types.py`** — Five typed dataclasses enforcing the Notion Judge spec two-axis architecture: `DataCoverage`, `Signal`, `ConfidenceModifier` (modifier agents), `ValueDistribution` (distribution agents), `JudgeOutput` (final synthesis).

2. **`src/lockin/agents/llm.py`** — `get_llm(model, temperature)` factory returning `ChatGoogleGenerativeAI`. Validates `GOOGLE_API_KEY` at call-time (not import-time). Exports `MODEL_PRO = "gemini-2.5-pro"` and `MODEL_FLASH = "gemini-2.5-flash"` constants.

3. **`src/lockin/agents/base.py`** — `invoke_agent(llm, system_prompt, human_prompt, agent_name)` builds `[SystemMessage, HumanMessage]` and calls `llm.invoke()` with a 3-attempt tenacity retry (30s wait, rate-limit pattern match). Also exports `BASE_RATE_TABLE` with 10 academic base-rate entries (Piotroski, Altman Z, Beneish M-Score, VIX, GDP regime, analyst upgrades).

4. **`src/lockin/utils/config.py`** — Added `fmp_api_key: str = ""` and 7 per-agent model fields (`macro_oracle_model`, `value_hunter_model`, `strategist_model`, `bear_model`, `guardian_model`, `judge_model`, `optimizer_model`) with Gemini defaults and env var overrides.

5. **`src/lockin/graph/state.py`** — Added typed fields to `InvestmentState`: `oracle_modifier`, `guardian_modifier`, `strategist_modifier` (`Optional[ConfidenceModifier]`), `judge_output` (`Optional[JudgeOutput]`), changed `bull/bear_valuation_distribution` from `dict` to `Optional[ValueDistribution]`.

6. **`pyproject.toml`** — Added `edgar`, `pypdf>=4.0.0`, `langchain-text-splitters>=0.3.0` for RAG document ingestion.

---

## Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| Circular import resolution | Lazy `__getattr__` in both `lockin.agents.__init__` and `lockin.graph.__init__` | `mock.py` imports `graph.state`; `graph.state` imports `agents.types`; eager init created circular dependency. Lazy loading defers resolution until first attribute access. |
| Runtime vs TYPE_CHECKING imports in state.py | Runtime imports (not guarded by `TYPE_CHECKING`) | LangGraph calls `get_type_hints(InvestmentState)` at `StateGraph(InvestmentState)` construction time. Forward references under `TYPE_CHECKING` are strings at runtime and can't be resolved by `typing.get_type_hints()` — causes `NameError`. |
| Types eagerly imported in `agents/__init__` | `lockin.agents.types` imports are eager in `__init__` | Types have no graph/mock dependencies — safe to import immediately. Mock/llm/base are deferred. This allows `state.py` to `from lockin.agents.types import ...` which triggers `lockin.agents.__init__` but only hits the eager type imports, not the circular mock imports. |
| BASE_RATE_TABLE values | All `success_rate: None`, academic defaults where published papers exist | Phase 5 (Validation) will backfill empirical rates from live data. Academic defaults (Piotroski 0.62, Beneish 0.55, expansion regime 0.55) used as Bayesian priors until then. |
| tenacity retry pattern | `retry_if_exception_message(match=r"(?i)(rate.?limit|quota|429)")` | Only retry rate-limit errors; propagate all other exceptions immediately to avoid masking real bugs. |

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing circular import in `lockin.graph.__init__`**

- **Found during:** Task 1 verification (`from lockin.agents.types import ...`)
- **Issue:** `lockin.graph.__init__` eagerly imported `create_graph, postgres_checkpointer` from `builder.py`, which in turn imports `lockin.agents.mock`. When `lockin.agents.__init__` triggered `lockin.graph.__init__` via `mock.py -> graph.state -> graph.__init__`, Python hit a partially initialised `mock.py` module.
- **Fix:** Replaced eager imports in `lockin.graph.__init__` with `__getattr__` lazy loading for `create_graph` and `postgres_checkpointer`.
- **Files modified:** `src/lockin/graph/__init__.py`
- **Commit:** 5f9357b (included in Task 1 commit)

**2. [Rule 1 - Bug] Extended lazy loading to `lockin.agents.__init__` for mock/llm/base**

- **Found during:** Task 3 verification (LangGraph `get_type_hints` call at StateGraph construction)
- **Issue:** After fixing graph's `__init__`, importing types at runtime in `state.py` triggered `lockin.agents.__init__` which eagerly imported `mock.py`. Mock imports `graph.state` (still initialising), recreating the circular dependency from the other direction.
- **Fix:** Moved mock/llm/base imports in `lockin.agents.__init__` to `__getattr__` lazy loading. Only `lockin.agents.types` is eagerly imported (no graph dependency). This allows `state.py` to import from `lockin.agents.types` safely.
- **Files modified:** `src/lockin/agents/__init__.py`
- **Commit:** d31d84e (included in Task 3 commit)

---

## Verification Results

All Task verification checks passed:

```
uv sync                                                  ✓ (edgar, pypdf, langchain-text-splitters installed)
get_settings().fmp_api_key                               ✓ (returns '')
get_settings().judge_model == 'gemini-2.5-pro'           ✓
import edgar                                             ✓
import pypdf                                             ✓
from lockin.agents.types import ... (all 5 types)        ✓
from lockin.agents import get_llm, MODEL_PRO, MODEL_FLASH, invoke_agent, BASE_RATE_TABLE  ✓
from lockin.agents import ValueDistribution, ...         ✓
len(BASE_RATE_TABLE) == 10                               ✓
InvestmentState.__annotations__ has all typed fields     ✓
pytest tests/ (15 pass, 1 pre-existing Supabase fail)    ✓
```

---

## Test Suite Status

- **15 tests pass** — same as before plan execution
- **1 pre-existing failure** — `test_full_pipeline_mock` requires live Supabase PostgreSQL connection (`audit_node` writes to DB). Not related to this plan. Pre-existed before Phase 3.

---

## Next Phase Readiness

**Phase 3 Plan 02 (Macro Oracle agent):** Ready to proceed.
- `get_llm(settings.macro_oracle_model)` returns configured LLM
- `invoke_agent(llm, system_prompt, human_prompt)` handles invocation + retry
- `ConfidenceModifier` dataclass is the output contract
- `oracle_modifier: Optional[ConfidenceModifier]` field exists in `InvestmentState`
- `BASE_RATE_TABLE` provides `expansion_regime`, `vix_extreme_fear`, `vix_extreme_greed` priors
