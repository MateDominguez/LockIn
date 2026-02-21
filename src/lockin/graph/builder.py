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
                 ---[veto=False]--> judge  (HITL interrupt if conviction < threshold)
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

    # PostgreSQL checkpointing (production):
    from lockin.graph.builder import postgres_checkpointer
    with postgres_checkpointer("postgresql://...") as cp:
        graph = create_graph(checkpointer=cp)
        result = graph.invoke(...)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

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

# Conviction below this threshold triggers a HITL interrupt at the judge node.
# The human reviewer can approve or override the recommendation.
JUDGE_HITL_THRESHOLD = 0.5


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
# HITL-enabled judge node
# ---------------------------------------------------------------------------


def judge_with_hitl(state: dict, config: RunnableConfig) -> dict:
    """Judge node with HITL interrupt for low-conviction decisions.

    When judge_conviction falls below JUDGE_HITL_THRESHOLD, the node calls
    interrupt() which causes LangGraph to pause execution and surface the
    interrupt payload to the caller. The graph is resumed by invoking with
    Command(resume=value), at which point this entire function re-executes
    and interrupt() returns the human-provided value instead of pausing.

    CRITICAL: Do NOT place irreversible side effects before interrupt().
    This entire node re-executes from the top when resumed; side effects
    before interrupt() will execute twice.
    """
    # Run judge logic first (safe to re-run on resume)
    result = mock_judge(state, config)

    conviction = result.get("judge_conviction", 1.0)
    if conviction < JUDGE_HITL_THRESHOLD:
        # Pause execution — returns to caller with __interrupt__ in result.
        # On resume, interrupt() returns the Command(resume=...) value.
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


# ---------------------------------------------------------------------------
# PostgreSQL checkpointer context manager
# ---------------------------------------------------------------------------


@contextmanager
def postgres_checkpointer(database_url: str):
    """Context manager yielding a configured PostgresSaver.

    Creates the checkpoint tables if they do not already exist (saver.setup()).
    Use this for production deployments where state persistence across
    invocations and HITL resume is required.

    Example::

        from lockin.graph.builder import create_graph, postgres_checkpointer
        from lockin.utils.config import get_settings

        settings = get_settings()
        with postgres_checkpointer(settings.database_url) as cp:
            graph = create_graph(checkpointer=cp)
            result = graph.invoke(
                create_initial_state("AAPL"),
                {"configurable": {"thread_id": "prod-run-1"}},
            )

    Args:
        database_url: PostgreSQL connection string (psycopg-compatible DSN or URL).

    Yields:
        A ready-to-use PostgresSaver instance.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.setup()  # Creates checkpoint tables if they don't exist
        yield saver


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
            PostgresSaver). When provided, graph state is persisted between
            invocations, enabling Human-in-the-Loop interrupts and resume.
        agent_overrides: Optional dict mapping agent name -> callable. Used in
            tests to inject custom agents without modifying the graph structure.
            Example: {"guardian": my_strict_guardian, "judge": my_judge}

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
    # Judge uses judge_with_hitl by default (HITL interrupt when conviction < threshold)
    # Can be overridden in tests via agent_overrides["judge"]
    judge_fn = overrides.get("judge", judge_with_hitl)
    builder.add_node(
        "judge",
        audit_node("judge", judge_fn),
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

    # Judge -> optimizer
    builder.add_edge("judge", "optimizer")

    # ------------------------------------------------------------------
    # Compile
    # ------------------------------------------------------------------
    graph = builder.compile(checkpointer=checkpointer)
    return graph
