"""
End-to-end pipeline tests for the real-agent AI-Investment Swarm LangGraph pipeline.

These tests verify the complete graph flow using the real agent_overrides mechanism
to inject lightweight stub agents that mimic the real agents' output contracts without
requiring LLM API keys, FRED access, yfinance network calls, or Supabase RAG.

Test strategy:
  - agent_overrides injects stub functions with the SAME output schema as real agents
  - Stubs return typed dataclasses (ConfidenceModifier, ValueDistribution, JudgeOutput)
    matching what real agents produce — not raw dicts as in mock.py
  - This tests graph routing, state continuity, and HITL mechanics with real structure
  - lockin.utils.audit.get_settings is patched to return empty DATABASE_URL so audit
    writes fall back to stderr (no Supabase connection required in tests)

Tests:
  1. test_full_pipeline_normal_flow — happy path through all 7 agents
  2. test_full_pipeline_guardian_veto — circuit_breaker=True stops at guardian
  3. test_full_pipeline_judge_hitl — p_final < 0.40 triggers HITL, resume completes
  4. test_full_pipeline_state_continuity — no agent overwrites another's fields
  5. test_argument_exhaustion_detection — unit tests for is_argument_exhausted()
"""

from __future__ import annotations

import unittest.mock as mock

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt

from lockin.agents.judge_math import run_judge_algorithm
from lockin.agents.types import (
    ConfidenceModifier,
    DataCoverage,
    JudgeOutput,
    Signal,
    ValueDistribution,
)
from lockin.graph.builder import (
    MAX_BULL_BEAR_ITERATIONS,
    create_graph,
    is_argument_exhausted,
)
from lockin.graph.state import InvestmentState, create_initial_state


# ---------------------------------------------------------------------------
# Shared stub helpers — real output schema, no network calls
# ---------------------------------------------------------------------------

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


def _make_value_distribution(
    expected_value: float = 150.0,
    std_dev: float = 20.0,
    label: str = "stub",
) -> ValueDistribution:
    return ValueDistribution(
        expected_value=expected_value,
        std_dev=std_dev,
        p10=expected_value * 0.75,
        p50=expected_value,
        p90=expected_value * 1.25,
        confidence=0.70,
        methods_used=[label],
        thesis=f"Stub {label} thesis — intrinsic value ${expected_value:.0f}",
        data_coverage=DataCoverage(available=["net_income", "total_assets"], missing=[]),
    )


# ---------------------------------------------------------------------------
# Stub agents with real output schemas
# ---------------------------------------------------------------------------


def stub_macro_oracle(state: dict, config: RunnableConfig) -> dict:
    """Macro Oracle stub — returns typed oracle_modifier (real agent schema)."""
    return {
        "macro_regime": {
            "phase": "expansion",
            "risk_appetite": "risk_on",
            "yield_curve": "normal",
            "fed_stance": "neutral",
        },
        "macro_confidence": 0.75,
        "macro_narrative": "Stub: expansion regime, risk-on, normal yield curve.",
        "oracle_modifier": _make_confidence_modifier(margin=0.05),
    }


def stub_value_hunter(state: dict, config: RunnableConfig) -> dict:
    """Value Hunter stub — returns typed bull_valuation_distribution."""
    iteration = state.get("bull_iteration", 0)
    base_value = 180.0

    result = {
        "bull_valuation_distribution": _make_value_distribution(base_value, label="EPV"),
        "bull_thesis": (
            f"Stub bull thesis (iteration {iteration}): strong EPV, "
            "Piotroski F=7, ROIC=22%, durable competitive moat."
        ),
        "bull_confidence": 0.72,
        "quality_metrics": {
            "piotroski_f": 7,
            "magic_formula": {"earnings_yield": 0.08, "roic": 0.22},
            "synthetic_prior": True,
        },
        # Track previous thesis for argument exhaustion detection
        "_prev_bull_thesis": state.get("bull_thesis", ""),
    }

    if iteration > 0:
        result["bull_refined_thesis"] = (
            f"Stub refined thesis (iteration {iteration}): EPV margin intact "
            "despite bear's revenue concerns. Reaffirm BUY."
        )
        result["bull_defense"] = (
            "Stub defense: services segment ROIC inflecting upward."
        )

    return result


def stub_bear(state: dict, config: RunnableConfig) -> dict:
    """Bear stub — increments bull_iteration, returns typed bear distribution."""
    current_iteration = state.get("bull_iteration", 0)
    return {
        "bear_challenges": [
            "Stub: revenue deceleration in core segment",
            "Stub: competitive moat narrowing",
        ],
        "bear_valuation_distribution": _make_value_distribution(120.0, std_dev=25.0, label="EPV"),
        "bear_thesis": (
            "Stub bear thesis: overvalued given hardware cycle headwinds. "
            "EPV pessimistic scenario implies 30% downside."
        ),
        "bear_red_flags": ["Stub: declining ROIC trend", "Stub: inventory build-up"],
        "bear_conviction": 0.60,
        "bull_iteration": current_iteration + 1,
    }


def stub_strategist(state: dict, config: RunnableConfig) -> dict:
    """Strategist stub — returns typed strategist_modifier."""
    return {
        "strategist_veto": 0.65,
        "strategist_sentiment": 0.62,
        "strategic_signals": {
            "earnings_sentiment": "positive",
            "analyst_revision_trend": "up",
        },
        "strategist_narrative": "Stub: positive VeTO score, no analyst downgrade trend.",
        "strategist_confidence": 0.68,
        "strategist_modifier": _make_confidence_modifier(margin=0.02, variance=0.01),
    }


def stub_guardian_pass(state: dict, config: RunnableConfig) -> dict:
    """Guardian stub — circuit_breaker=False, pipeline continues."""
    modifier = _make_confidence_modifier(
        margin=0.05, variance=0.02, circuit_breaker=False
    )
    return {
        "guardian_modifier": modifier,
        "guardian_risk_report": {
            "z_score": 3.5,
            "z_zone": "safe",
            "m_score": -2.9,
            "vomc_fragility": 0.25,
            "debt_ebitda": 1.2,
            "circuit_breaker": False,
        },
        "guardian_veto": False,
        "guardian_veto_reason": "",
    }


def stub_guardian_veto(state: dict, config: RunnableConfig) -> dict:
    """Guardian stub — circuit_breaker=True (severe risk), pipeline terminates."""
    modifier = _make_confidence_modifier(
        margin=0.40,
        variance=0.15,
        circuit_breaker=True,
        cb_reason="Stub: Z<1.0 AND debt/EBITDA>4x (severe distress)",
    )
    return {
        "guardian_modifier": modifier,
        "guardian_risk_report": {
            "z_score": 0.8,
            "z_zone": "distress",
            "m_score": -1.5,
            "vomc_fragility": 0.75,
            "debt_ebitda": 5.0,
            "circuit_breaker": True,
            "circuit_breaker_reason": modifier.circuit_breaker_reason,
        },
        "guardian_veto": True,
        "guardian_veto_reason": modifier.circuit_breaker_reason or "",
    }


def _run_judge_with_stub_distributions(state: dict) -> JudgeOutput:
    """Run the real judge algorithm with stub distributions (no LLM/yfinance needed)."""
    bull_dist = state.get("bull_valuation_distribution") or _make_value_distribution(180.0)
    bear_dist = state.get("bear_valuation_distribution") or _make_value_distribution(120.0)
    oracle_mod = state.get("oracle_modifier") or _make_confidence_modifier()
    guardian_mod = state.get("guardian_modifier") or _make_confidence_modifier()
    strategist_mod = state.get("strategist_modifier") or _make_confidence_modifier()

    return run_judge_algorithm(
        bull_dist=bull_dist,
        bear_dist=bear_dist,
        oracle_modifier=oracle_mod,
        guardian_modifier=guardian_mod,
        strategist_modifier=strategist_mod,
        current_price=150.0,
    )


def stub_judge_normal(state: dict, config: RunnableConfig) -> dict:
    """Judge stub — runs real algorithm, p_final >= 0.40 (no HITL)."""
    result = _run_judge_with_stub_distributions(state)
    return {
        "judge_consensus_distribution": {
            "mu": result.consensus_distribution[0],
            "sigma": result.consensus_distribution[1],
            "valor_mediano": result.valor_mediano,
        },
        "judge_recommendation": result.recommendation,
        "judge_conviction": result.p_success,
        "judge_margin": result.margin_of_safety,
        "judge_price_target": result.precio_target,
        "judge_narrative": (
            f"Stub judge: {result.recommendation}. "
            f"Consensus value ${result.valor_mediano:.2f}, "
            f"p_success={result.p_success:.3f}."
        ),
        "judge_hitl": False,
        "judge_hitl_reason": "",
        "judge_output": result,
        "citations": [],
    }


def stub_judge_hitl(state: dict, config: RunnableConfig) -> dict:
    """Judge stub — p_final < 0.40, triggers HITL interrupt."""
    result = _run_judge_with_stub_distributions(state)

    # Force HITL by using a very low p_success in the returned state dict
    hitl_triggered = True
    hitl_reason = "Stub: p_final=0.25 < 0.40 HITL threshold"

    # Pause execution — interrupt() pauses until Command(resume=...) is sent
    human_input = interrupt({
        "reason": hitl_reason,
        "conviction": 0.25,
        "recommendation": "HOLD",
        "narrative": "Stub: insufficient conviction for autonomous BUY decision.",
    })

    return {
        "judge_consensus_distribution": {
            "mu": result.consensus_distribution[0],
            "sigma": result.consensus_distribution[1],
            "valor_mediano": result.valor_mediano,
        },
        "judge_recommendation": "HOLD",
        "judge_conviction": 0.25,
        "judge_margin": result.margin_of_safety,
        "judge_price_target": result.precio_target,
        "judge_narrative": "Stub: low conviction HOLD.",
        "judge_hitl": True,
        "judge_hitl_reason": hitl_reason,
        "human_review": human_input,
        "judge_output": result,
        "citations": [],
    }


def stub_optimizer(state: dict, config: RunnableConfig) -> dict:
    """Optimizer stub — deterministic Kelly sizing from judge output."""
    judge_output: JudgeOutput | None = state.get("judge_output")
    recommendation = state.get("judge_recommendation", "HOLD")

    if judge_output is not None:
        kelly = judge_output.kelly_fraction
    else:
        kelly = 0.05  # safe default

    ticker = state.get("asset_ticker", "UNKNOWN")
    position_size = kelly if recommendation == "BUY" else 0.0

    return {
        "optimizer_portfolio": {ticker: position_size},
        "optimizer_sectors": {"technology": position_size},
        "optimizer_rebalancing": [],
        "optimizer_metrics": {
            "kelly_fraction": kelly,
            "position_size": position_size,
            "recommendation": recommendation,
            "position_cap_applied": False,
        },
        "optimizer_narrative": (
            f"Stub optimizer: {recommendation}. "
            f"Kelly fraction={kelly:.3f}, position={position_size:.1%}."
        ),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Fake settings object with empty DATABASE_URL — forces audit logging to stderr
# instead of attempting a real Supabase/PostgreSQL connection in tests.
_FAKE_SETTINGS_NO_DB = type("Settings", (), {"database_url": ""})()


@pytest.fixture(autouse=True)
def patch_audit_settings():
    """Patch audit module to use empty DATABASE_URL for all E2E tests.

    Prevents audit_node from trying to connect to Supabase during tests.
    Audit events fall back to stderr (see audit.py:log_audit_event).
    """
    with mock.patch(
        "lockin.utils.audit.get_settings",
        return_value=_FAKE_SETTINGS_NO_DB,
    ):
        yield


@pytest.fixture
def mem_saver():
    return MemorySaver()


@pytest.fixture
def initial_state_aapl():
    return create_initial_state("AAPL")


@pytest.fixture
def normal_overrides():
    """Agent overrides for normal pipeline flow (no HITL, no veto)."""
    return {
        "macro_oracle": stub_macro_oracle,
        "value_hunter": stub_value_hunter,
        "bear": stub_bear,
        "strategist": stub_strategist,
        "guardian": stub_guardian_pass,
        "judge": stub_judge_normal,
        "optimizer": stub_optimizer,
    }


# ---------------------------------------------------------------------------
# Test 1: Full pipeline normal flow
# ---------------------------------------------------------------------------


def test_full_pipeline_normal_flow(mem_saver, initial_state_aapl, normal_overrides):
    """Happy path: all 7 real-schema agents run to completion.

    Verifies:
    - judge_recommendation is a valid recommendation string
    - optimizer_portfolio is non-empty
    - bull_iteration == MAX_BULL_BEAR_ITERATIONS (dialectic ran fully)
    - macro_regime present
    - guardian did NOT veto
    - HITL was NOT triggered
    """
    graph = create_graph(checkpointer=mem_saver, agent_overrides=normal_overrides)
    config = {"configurable": {"thread_id": "e2e-normal-1"}}

    result = graph.invoke(initial_state_aapl, config)

    # Judge produced a valid recommendation
    assert result["judge_recommendation"] in ("BUY", "HOLD", "PASS"), (
        f"Unexpected recommendation: {result['judge_recommendation']}"
    )

    # Optimizer ran and produced portfolio allocation
    assert "optimizer_portfolio" in result, "Optimizer did not produce portfolio"
    assert result["optimizer_portfolio"], "optimizer_portfolio must not be empty"

    # Dialectic loop ran the expected number of times
    assert result["bull_iteration"] == MAX_BULL_BEAR_ITERATIONS, (
        f"Expected {MAX_BULL_BEAR_ITERATIONS} bull-bear iterations, got {result['bull_iteration']}"
    )

    # Macro oracle ran
    assert "macro_regime" in result, "macro_regime missing — macro oracle did not run"
    assert result["macro_regime"]["phase"] == "expansion"

    # Guardian did not veto
    assert result.get("guardian_veto") is False, "Guardian should not veto in happy path"

    # HITL was not triggered
    assert result.get("judge_hitl") is False, (
        "HITL should not trigger in normal flow"
    )

    # oracle_modifier was populated (typed ConfidenceModifier)
    oracle_mod = result.get("oracle_modifier")
    assert oracle_mod is not None, "oracle_modifier missing from final state"
    assert hasattr(oracle_mod, "circuit_breaker"), "oracle_modifier must be ConfidenceModifier"
    assert oracle_mod.circuit_breaker is False


# ---------------------------------------------------------------------------
# Test 2: Guardian circuit_breaker terminates pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_guardian_veto(mem_saver, initial_state_aapl):
    """Guardian circuit_breaker=True from ConfidenceModifier stops graph at guardian.

    Verifies:
    - graph terminates after guardian node (judge and optimizer do NOT run)
    - guardian_modifier.circuit_breaker is True
    - guardian_veto is True (legacy field also set)
    - should_guardian_veto() reads from guardian_modifier (new path)
    """
    overrides = {
        "macro_oracle": stub_macro_oracle,
        "value_hunter": stub_value_hunter,
        "bear": stub_bear,
        "strategist": stub_strategist,
        "guardian": stub_guardian_veto,  # circuit_breaker=True
        # judge and optimizer NOT in overrides — they should not run
    }
    graph = create_graph(checkpointer=mem_saver, agent_overrides=overrides)
    config = {"configurable": {"thread_id": "e2e-veto-1"}}

    result = graph.invoke(initial_state_aapl, config)

    # guardian_veto was set (legacy boolean)
    assert result.get("guardian_veto") is True, "guardian_veto must be True after circuit breaker"

    # guardian_modifier.circuit_breaker is True (typed field)
    guardian_mod = result.get("guardian_modifier")
    assert guardian_mod is not None, "guardian_modifier missing from state"
    assert hasattr(guardian_mod, "circuit_breaker"), "guardian_modifier must be ConfidenceModifier"
    assert guardian_mod.circuit_breaker is True, (
        "guardian_modifier.circuit_breaker must be True when circuit breaker fires"
    )

    # Judge and optimizer did NOT run (state has no judge or optimizer fields)
    assert "judge_recommendation" not in result, (
        "Judge must not run when guardian circuit breaker fires"
    )
    assert "optimizer_portfolio" not in result, (
        "Optimizer must not run when guardian circuit breaker fires"
    )


# ---------------------------------------------------------------------------
# Test 3: Judge HITL pauses and resumes
# ---------------------------------------------------------------------------


def test_full_pipeline_judge_hitl(mem_saver, initial_state_aapl):
    """Judge HITL interrupt pauses graph; resume with Command completes pipeline.

    Verifies:
    - __interrupt__ in result on first invoke (graph paused at judge)
    - interrupt payload has expected fields
    - graph.get_state shows judge as next node
    - After Command(resume=...), pipeline completes through optimizer
    - judge_hitl=True in final state
    - human_review contains the Command value
    """
    overrides = {
        "macro_oracle": stub_macro_oracle,
        "value_hunter": stub_value_hunter,
        "bear": stub_bear,
        "strategist": stub_strategist,
        "guardian": stub_guardian_pass,
        "judge": stub_judge_hitl,  # triggers HITL interrupt
        "optimizer": stub_optimizer,
    }
    graph = create_graph(checkpointer=mem_saver, agent_overrides=overrides)
    config = {"configurable": {"thread_id": "e2e-hitl-1"}}

    # --- First invoke: should pause at judge ---
    result1 = graph.invoke(initial_state_aapl, config)

    assert "__interrupt__" in result1, (
        "Expected __interrupt__ in result when judge triggers HITL"
    )
    interrupts = result1["__interrupt__"]
    assert len(interrupts) == 1
    interrupt_payload = interrupts[0].value
    assert "conviction" in interrupt_payload, "Interrupt payload must include conviction"
    assert interrupt_payload["conviction"] == 0.25
    assert interrupt_payload["recommendation"] == "HOLD"

    # Graph should show judge as next node to execute
    current_state = graph.get_state(config)
    assert current_state.next == ("judge",), (
        f"Expected next=('judge',) after interrupt, got {current_state.next}"
    )

    # --- Resume with human approval ---
    final_result = graph.invoke(
        Command(resume={"approved": True, "notes": "Accepted low conviction"}),
        config,
    )

    # Pipeline completes through optimizer
    assert "optimizer_portfolio" in final_result, (
        "Optimizer must run after HITL resume"
    )

    # HITL fields are set correctly
    assert final_result.get("judge_hitl") is True, "judge_hitl must be True after HITL"
    assert final_result.get("human_review") == {
        "approved": True,
        "notes": "Accepted low conviction",
    }, "human_review must contain Command(resume=...) value"


# ---------------------------------------------------------------------------
# Test 4: State continuity — no agent overwrites another's fields
# ---------------------------------------------------------------------------


def test_full_pipeline_state_continuity(mem_saver, initial_state_aapl, normal_overrides):
    """Verify each agent's typed output is preserved in the final state.

    Specifically:
    - oracle_modifier set by macro_oracle is NOT overwritten by later agents
    - guardian_modifier set by guardian is NOT overwritten by judge/optimizer
    - strategist_modifier set by strategist is NOT overwritten by guardian
    - All typed ConfidenceModifier fields are intact at the end
    """
    graph = create_graph(checkpointer=mem_saver, agent_overrides=normal_overrides)
    config = {"configurable": {"thread_id": "e2e-continuity-1"}}

    result = graph.invoke(initial_state_aapl, config)

    # oracle_modifier (set by macro_oracle)
    oracle_mod = result.get("oracle_modifier")
    assert oracle_mod is not None, "oracle_modifier missing from final state"
    assert isinstance(oracle_mod, ConfidenceModifier), (
        f"oracle_modifier must be ConfidenceModifier, got {type(oracle_mod)}"
    )
    assert oracle_mod.margin_adjustment == 0.05, (
        "oracle_modifier.margin_adjustment was overwritten"
    )

    # strategist_modifier (set by strategist)
    strategist_mod = result.get("strategist_modifier")
    assert strategist_mod is not None, "strategist_modifier missing from final state"
    assert isinstance(strategist_mod, ConfidenceModifier), (
        f"strategist_modifier must be ConfidenceModifier, got {type(strategist_mod)}"
    )

    # guardian_modifier (set by guardian)
    guardian_mod = result.get("guardian_modifier")
    assert guardian_mod is not None, "guardian_modifier missing from final state"
    assert isinstance(guardian_mod, ConfidenceModifier), (
        f"guardian_modifier must be ConfidenceModifier, got {type(guardian_mod)}"
    )
    assert guardian_mod.circuit_breaker is False, (
        "guardian_modifier.circuit_breaker was corrupted"
    )

    # bull_valuation_distribution (set by value_hunter)
    bull_dist = result.get("bull_valuation_distribution")
    assert bull_dist is not None, "bull_valuation_distribution missing from final state"
    assert isinstance(bull_dist, ValueDistribution), (
        f"bull_valuation_distribution must be ValueDistribution, got {type(bull_dist)}"
    )

    # bear_valuation_distribution (set by bear)
    bear_dist = result.get("bear_valuation_distribution")
    assert bear_dist is not None, "bear_valuation_distribution missing from final state"
    assert isinstance(bear_dist, ValueDistribution), (
        f"bear_valuation_distribution must be ValueDistribution, got {type(bear_dist)}"
    )

    # judge_output (set by judge)
    judge_out = result.get("judge_output")
    assert judge_out is not None, "judge_output missing from final state"
    assert isinstance(judge_out, JudgeOutput), (
        f"judge_output must be JudgeOutput, got {type(judge_out)}"
    )

    # optimizer fields (set by optimizer)
    assert "optimizer_portfolio" in result, "optimizer_portfolio missing"
    assert "optimizer_metrics" in result, "optimizer_metrics missing"
    assert "optimizer_narrative" in result, "optimizer_narrative missing"


# ---------------------------------------------------------------------------
# Test 5: Argument exhaustion detection unit tests
# ---------------------------------------------------------------------------


def test_argument_exhaustion_detection():
    """Unit tests for is_argument_exhausted() function.

    Tests:
    - Identical strings -> True (100% overlap)
    - Very different strings -> False (low overlap)
    - Near-identical (>85% Jaccard overlap) -> True
    - Empty / None inputs -> False
    - Short strings with high overlap -> True
    """
    # Identical strings -> exhausted
    same = "the stock is undervalued based on EPV earnings power value analysis moat"
    assert is_argument_exhausted(same, same) is True, (
        "Identical strings must return True (100% Jaccard overlap)"
    )

    # Very different strings -> not exhausted
    bull_thesis = "stock undervalued EPV moat earnings growth ROIC Piotroski F-Score strong"
    bear_thesis = "bankruptcy risk leverage debt Altman Z-Score distress manipulation Beneish"
    assert is_argument_exhausted(bull_thesis, bear_thesis) is False, (
        "Clearly different theses must return False"
    )

    # Empty string -> False (no basis for comparison)
    assert is_argument_exhausted("", "some thesis content here") is False, (
        "Empty prev_thesis must return False"
    )
    assert is_argument_exhausted("some thesis content here", "") is False, (
        "Empty curr_thesis must return False"
    )

    # Both empty -> False
    assert is_argument_exhausted("", "") is False, (
        "Both empty must return False"
    )

    # Near-identical (only minor change) -> True (>85% overlap)
    base = "AAPL is undervalued based on EPV analysis strong moat services revenue"
    nearly_same = "AAPL is undervalued based on EPV analysis strong moat services revenue growth"
    # The extra word "growth" changes overlap only slightly
    assert is_argument_exhausted(base, nearly_same) is True, (
        "Near-identical theses (single word difference) must return True"
    )

    # Completely different -> False
    assert is_argument_exhausted(
        "bull thesis Apple strong ROIC moat FCF yield Piotroski",
        "completely unrelated content bear recession inflation rates risk leverage debt"
    ) is False

    # None handling: Python None would cause .split() to fail;
    # the function guard is `if not prev_thesis or not curr_thesis`
    assert is_argument_exhausted(None, "something") is False  # type: ignore[arg-type]
    assert is_argument_exhausted("something", None) is False  # type: ignore[arg-type]
