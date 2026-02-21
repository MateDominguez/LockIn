"""
LangGraph StateGraph factory for the AI-Investment Swarm pipeline.

Builds and compiles a StateGraph with all 7 agent nodes, correct linear edges,
and two conditional routing functions:

  1. Bull-Bear dialectic loop (bear -> value_hunter x2, then -> strategist)
  2. Guardian veto gate (guardian -> END on veto, else -> judge)

Graph flow:
  START
    -> macro_oracle
    -> value_hunter
    -> bear  ---[loop up to MAX_BULL_BEAR_ITERATIONS]---> value_hunter
             ---[iterations reached]------------------> strategist
    -> guardian  ---[veto=True]---> END
                 ---[veto=False]--> judge
    -> optimizer
    -> END

Usage::

    from lockin.graph.builder import create_graph
    from langgraph.checkpoint.memory import MemorySaver

    graph = create_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        create_initial_state("AAPL"),
        config={"configurable": {"thread_id": "my-thread"}},
    )
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from lockin.agents.mock import (
    mock_bear,
    mock_guardian,
    mock_judge,
    mock_macro_oracle,
    mock_optimizer,
    mock_strategist,
    mock_value_hunter,
)
from lockin.graph.state import InvestmentState
from lockin.utils.audit import audit_node

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Number of bear-challenge / value-hunter-rebuttal rounds before moving on.
# With MAX=2 the graph executes:
#   bear(iter=0->1) -> value_hunter -> bear(iter=1->2) -> strategist
MAX_BULL_BEAR_ITERATIONS = 2


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------


def should_continue_dialectic(state: InvestmentState) -> str:
    """Route after bear: loop to value_hunter while iterations remain, else strategist.

    bull_iteration is incremented by mock_bear (and later by real bear agent)
    each time it runs. We route back to value_hunter while that count is still
    below the maximum, giving value_hunter a chance to rebut each challenge.
    """
    if state.get("bull_iteration", 0) < MAX_BULL_BEAR_ITERATIONS:
        return "value_hunter"
    return "strategist"


def should_guardian_veto(state: InvestmentState) -> str:
    """Route after guardian: terminate graph on veto, continue to judge otherwise."""
    if state.get("guardian_veto", False):
        return "__end__"
    return "judge"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def create_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    agent_overrides: dict[str, Any] | None = None,
) -> Any:
    """Build and compile the investment analysis StateGraph.

    Args:
        checkpointer: Optional LangGraph checkpoint saver (e.g. MemorySaver or
            AsyncPostgresSaver). When provided, graph state is persisted between
            invocations, enabling Human-in-the-Loop interrupts (Plan 03).
        agent_overrides: Optional dict mapping agent name -> callable. Used in
            tests to inject custom agents without modifying the graph structure.
            Example: {"guardian": my_strict_guardian}

    Returns:
        Compiled LangGraph CompiledGraph ready for .invoke() / .stream().
    """
    overrides = agent_overrides or {}

    builder = StateGraph(InvestmentState)

    # ------------------------------------------------------------------
    # Nodes — each mock agent wrapped with audit logging
    # ------------------------------------------------------------------
    builder.add_node(
        "macro_oracle",
        audit_node("macro_oracle", overrides.get("macro_oracle", mock_macro_oracle)),
    )
    builder.add_node(
        "value_hunter",
        audit_node("value_hunter", overrides.get("value_hunter", mock_value_hunter)),
    )
    builder.add_node(
        "bear",
        audit_node("bear", overrides.get("bear", mock_bear)),
    )
    builder.add_node(
        "strategist",
        audit_node("strategist", overrides.get("strategist", mock_strategist)),
    )
    builder.add_node(
        "guardian",
        audit_node("guardian", overrides.get("guardian", mock_guardian)),
    )
    builder.add_node(
        "judge",
        audit_node("judge", overrides.get("judge", mock_judge)),
    )
    builder.add_node(
        "optimizer",
        audit_node("optimizer", overrides.get("optimizer", mock_optimizer)),
    )

    # ------------------------------------------------------------------
    # Linear edges
    # ------------------------------------------------------------------
    builder.add_edge(START, "macro_oracle")
    builder.add_edge("macro_oracle", "value_hunter")
    builder.add_edge("value_hunter", "bear")
    builder.add_edge("strategist", "guardian")
    builder.add_edge("optimizer", END)

    # ------------------------------------------------------------------
    # Conditional edges
    # ------------------------------------------------------------------

    # Bull-Bear dialectic loop: bear -> value_hunter (loop) or -> strategist (exit)
    builder.add_conditional_edges(
        "bear",
        should_continue_dialectic,
        {"value_hunter": "value_hunter", "strategist": "strategist"},
    )

    # Guardian veto gate: guardian -> END (veto) or -> judge (pass)
    # END == '__end__' so either the string or the constant works as dict key.
    builder.add_conditional_edges(
        "guardian",
        should_guardian_veto,
        {"__end__": END, "judge": "judge"},
    )

    # Judge -> optimizer (HITL interrupt will be added in Plan 03)
    builder.add_edge("judge", "optimizer")

    # ------------------------------------------------------------------
    # Compile
    # ------------------------------------------------------------------
    graph = builder.compile(checkpointer=checkpointer)
    return graph
