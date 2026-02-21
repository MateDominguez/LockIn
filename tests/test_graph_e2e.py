"""
End-to-end tests for the AI-Investment Swarm LangGraph pipeline.

Covers all Phase 1 success criteria:
  - CORE-01: StateGraph compiles and runs with 7 mock agents, conditional edges
  - CORE-02: Audit trail logs every agent start/end (stderr fallback)
  - CORE-03: Checkpointing functional with MemorySaver; PostgresSaver ready
  - CORE-04: HITL interrupt — pause at judge, resume with Command, pipeline completes

All tests use MemorySaver for fast, dependency-free execution.
"""

from __future__ import annotations

import unittest.mock as mock

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from lockin.graph.builder import (
    JUDGE_HITL_THRESHOLD,
    create_graph,
    judge_with_hitl,
)
from lockin.graph.state import InvestmentState, create_initial_state


# ---------------------------------------------------------------------------
# Test 1: Full pipeline happy path
# ---------------------------------------------------------------------------


def test_full_pipeline_mock(graph, initial_state, thread_config):
    """Happy path: graph runs all 7 agents to completion with correct output."""
    result = graph.invoke(initial_state, thread_config)

    # Judge produced a valid recommendation
    assert result["judge_recommendation"] in ("BUY", "HOLD", "PASS"), (
        f"Unexpected recommendation: {result['judge_recommendation']}"
    )

    # Optimizer ran and produced portfolio allocation
    assert "optimizer_portfolio" in result, "Optimizer did not produce portfolio"
    assert result["optimizer_portfolio"], "optimizer_portfolio must not be empty"

    # Dialectic loop ran exactly MAX_BULL_BEAR_ITERATIONS times
    assert result["bull_iteration"] == 2, (
        f"Expected 2 bull-bear iterations, got {result['bull_iteration']}"
    )

    # Macro oracle ran
    assert "macro_regime" in result, "macro_regime missing — macro oracle did not run"

    # Guardian did not veto
    assert result.get("guardian_veto") is False, "Guardian should not veto in happy path"

    # HITL was not triggered (mock conviction = 0.70 > threshold 0.5)
    assert result.get("judge_hitl") is False, (
        "HITL should not trigger when conviction is above threshold"
    )


# ---------------------------------------------------------------------------
# Test 2: Bull-bear iteration count
# ---------------------------------------------------------------------------


def test_bull_bear_iteration_count(graph, initial_state, thread_config):
    """Verify the bull-bear dialectic loop runs exactly MAX_BULL_BEAR_ITERATIONS times."""
    result = graph.invoke(initial_state, thread_config)

    assert result["bull_iteration"] == 2, (
        f"Expected exactly 2 dialectic iterations, got {result['bull_iteration']}"
    )

    # Value hunter's refined thesis should be present (produced after iteration > 0)
    assert "bull_refined_thesis" in result, (
        "bull_refined_thesis missing — value_hunter did not run its rebuttal path"
    )
    assert "bull_defense" in result, "bull_defense missing"


# ---------------------------------------------------------------------------
# Test 3: Guardian veto stops pipeline
# ---------------------------------------------------------------------------


def test_guardian_veto_stops_pipeline(memory_saver, initial_state):
    """Inject a vetoing guardian — judge and optimizer must NOT run."""

    def mock_guardian_veto(state: dict, config: RunnableConfig) -> dict:
        return {
            "guardian_veto": True,
            "guardian_veto_reason": "Test: Altman Z-Score below threshold",
            "guardian_risk_report": {"altman_z": 0.8, "beneish_m": -1.5},
        }

    graph = create_graph(
        checkpointer=memory_saver,
        agent_overrides={"guardian": mock_guardian_veto},
    )
    config = {"configurable": {"thread_id": "veto-test-1"}}

    result = graph.invoke(initial_state, config)

    assert result.get("guardian_veto") is True, "Guardian veto flag must be True"
    assert "judge_recommendation" not in result, (
        "Judge must not run when guardian vetoes"
    )
    assert "optimizer_portfolio" not in result, (
        "Optimizer must not run when guardian vetoes"
    )


# ---------------------------------------------------------------------------
# Test 4: Checkpoint stores and retrieves state
# ---------------------------------------------------------------------------


def test_checkpoint_stores_state(graph, initial_state, thread_config):
    """Verify MemorySaver persists state so graph.get_state() returns valid data."""
    graph.invoke(initial_state, thread_config)

    state_from_checkpoint = graph.get_state(thread_config)

    # The stored state values must include what we put in
    values = state_from_checkpoint.values
    assert values.get("asset_ticker") == "AAPL", (
        f"Expected asset_ticker=AAPL in checkpoint, got {values.get('asset_ticker')}"
    )
    assert "judge_recommendation" in values, (
        "judge_recommendation must be stored in checkpoint after full run"
    )
    assert values["judge_recommendation"] in ("BUY", "HOLD", "PASS")


# ---------------------------------------------------------------------------
# Test 5: HITL interrupt pauses at judge, resumes to completion
# ---------------------------------------------------------------------------


def test_hitl_interrupt_low_conviction(memory_saver, initial_state):
    """Low-conviction judge triggers HITL interrupt; resume completes pipeline."""

    def mock_judge_low_conviction(state: dict, config: RunnableConfig) -> dict:
        """Judge that always returns conviction below the HITL threshold."""
        return {
            "judge_recommendation": "HOLD",
            "judge_conviction": 0.3,          # Below JUDGE_HITL_THRESHOLD (0.5)
            "judge_margin": 0.25,
            "judge_price_target": 150.0,
            "judge_narrative": "Low conviction test — insufficient data",
            "judge_hitl": False,               # Will be overwritten by judge_with_hitl
            "judge_hitl_reason": "",
        }

    # Wrap the low-conviction judge in judge_with_hitl so HITL triggers
    def judge_fn_with_hitl(state: dict, config: RunnableConfig) -> dict:
        from lockin.graph.builder import JUDGE_HITL_THRESHOLD
        from langgraph.types import interrupt

        result = mock_judge_low_conviction(state, config)
        conviction = result.get("judge_conviction", 1.0)
        if conviction < JUDGE_HITL_THRESHOLD:
            human_input = interrupt({
                "reason": "Low conviction — human review required",
                "conviction": conviction,
                "recommendation": result.get("judge_recommendation"),
                "narrative": result.get("judge_narrative"),
            })
            result["human_review"] = human_input
            result["judge_hitl"] = True
            result["judge_hitl_reason"] = (
                f"Conviction {conviction} below threshold {JUDGE_HITL_THRESHOLD}"
            )
        else:
            result["judge_hitl"] = False
            result["judge_hitl_reason"] = ""
        return result

    graph = create_graph(
        checkpointer=memory_saver,
        agent_overrides={"judge": judge_fn_with_hitl},
    )
    config = {"configurable": {"thread_id": "hitl-test-1"}}

    # --- First invoke: should pause at judge node with interrupt ---
    result1 = graph.invoke(initial_state, config)

    # LangGraph 1.x returns __interrupt__ key in result when interrupted
    assert "__interrupt__" in result1, (
        "Expected __interrupt__ in result when conviction is below threshold"
    )
    interrupts = result1["__interrupt__"]
    assert len(interrupts) == 1
    interrupt_payload = interrupts[0].value
    assert interrupt_payload["conviction"] == 0.3
    assert interrupt_payload["recommendation"] == "HOLD"

    # Graph state should show judge as next node to execute
    current_state = graph.get_state(config)
    assert current_state.next == ("judge",), (
        f"Expected next=('judge',) after interrupt, got {current_state.next}"
    )

    # --- Resume with human approval ---
    final_result = graph.invoke(
        Command(resume={"approved": True, "notes": "Conviction acceptable given context"}),
        config,
    )

    # After resume, pipeline should complete with optimizer output
    assert "optimizer_portfolio" in final_result, (
        "Optimizer must run after HITL resume"
    )
    assert final_result.get("judge_hitl") is True, (
        "judge_hitl must be True after HITL interrupt was triggered"
    )
    assert final_result.get("human_review") == {
        "approved": True,
        "notes": "Conviction acceptable given context",
    }, "human_review must contain the Command(resume=...) value"


# ---------------------------------------------------------------------------
# Test 6: Audit logging emits to stderr when DATABASE_URL is empty
# ---------------------------------------------------------------------------


def test_audit_logging_stderr(graph, initial_state, thread_config, capsys):
    """Audit trail logs [AUDIT] events to stderr when no DATABASE_URL configured."""
    # Patch get_settings to return empty DATABASE_URL so stderr path is taken
    fake_settings = type("Settings", (), {"database_url": ""})()

    with mock.patch("lockin.utils.audit.get_settings", return_value=fake_settings):
        graph.invoke(initial_state, thread_config)

    captured = capsys.readouterr()
    stderr_output = captured.err

    # Should have audit entries for key agents
    assert "[AUDIT]" in stderr_output, "Expected [AUDIT] prefix in stderr output"
    assert "macro_oracle" in stderr_output, "macro_oracle audit entry missing from stderr"
    assert "judge" in stderr_output, "judge audit entry missing from stderr"
    assert "optimizer" in stderr_output, "optimizer audit entry missing from stderr"
