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
    -> bear  ---[loop up to MAX_BULL_BEAR_ITERATIONS OR argument exhaustion]---> value_hunter
             ---[iterations reached or exhausted]------------------------------> strategist
    -> guardian  ---[veto=True]---> END
                 ---[veto=False]--> judge  (HITL interrupt if p_final < 0.40 or circuit_breaker)
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

from collections import Counter
from contextlib import contextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

# ---------------------------------------------------------------------------
# Real agent imports (Phase 3 implementations)
# ---------------------------------------------------------------------------
from lockin.agents.macro_oracle import macro_oracle
from lockin.agents.value_hunter import value_hunter
from lockin.agents.bear import bear
from lockin.agents.strategist import strategist
from lockin.agents.guardian import guardian
from lockin.agents.judge import judge
from lockin.agents.optimizer import optimizer

# Mock agents kept for backward compatibility (Phase 1 E2E tests, agent_overrides)
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
# NOTE: The real judge agent uses p_final < 0.40 per Notion spec v1.0.
# This constant (0.5) is kept for backward compatibility with Phase 1 mock tests.
# The real HITL threshold is defined in lockin.agents.judge (_HITL_PROBABILITY_THRESHOLD).
JUDGE_HITL_THRESHOLD = 0.5

# Jaccard similarity threshold above which the bull-bear debate is considered exhausted.
# If the current bull thesis overlaps with the previous by more than 85%, no new
# arguments are being made and the debate should terminate early.
_ARGUMENT_EXHAUSTION_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Argument exhaustion detection
# ---------------------------------------------------------------------------


def is_argument_exhausted(prev_thesis: str, curr_thesis: str) -> bool:
    """Detect whether the Bull-Bear dialectic has stopped producing new arguments.

    Uses Jaccard similarity over the top-20 most frequent words in each thesis.
    If similarity > 0.85, the theses are converging and the debate should terminate.

    Args:
        prev_thesis: Bull thesis from the previous round (or empty string if first round).
        curr_thesis:  Bull thesis from the current round.

    Returns:
        True if the argument is considered exhausted (similarity > threshold).
        False if theses are different enough to continue, or if either is empty.
    """
    if not prev_thesis or not curr_thesis:
        return False

    def top_words(text: str, n: int = 20) -> set[str]:
        words = text.lower().split()
        return set(w for w, _ in Counter(words).most_common(n))

    prev_set = top_words(prev_thesis)
    curr_set = top_words(curr_thesis)

    if not prev_set or not curr_set:
        return False

    jaccard = len(prev_set & curr_set) / len(prev_set | curr_set)
    return jaccard > _ARGUMENT_EXHAUSTION_THRESHOLD


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------


def should_continue_dialectic(state: InvestmentState) -> str:
    """Route after bear: loop to value_hunter while iterations remain, else strategist.

    Termination conditions (either stops the dialectic):
      1. bull_iteration >= MAX_BULL_BEAR_ITERATIONS (hard iteration cap)
      2. is_argument_exhausted() returns True (Jaccard similarity > 0.85)

    bull_iteration is incremented by the bear agent each time it runs.
    We route back to value_hunter while that count is still below the maximum,
    giving value_hunter a chance to rebut each challenge.

    _prev_bull_thesis is updated by the value_hunter after each rebuttal.
    """
    if state.get("bull_iteration", 0) >= MAX_BULL_BEAR_ITERATIONS:
        return "strategist"

    prev_thesis = state.get("_prev_bull_thesis", "")
    curr_thesis = state.get("bull_thesis", "")
    if is_argument_exhausted(prev_thesis, curr_thesis):
        return "strategist"

    return "value_hunter"  # continue dialectic (route back to bull for rebuttal)


def should_guardian_veto(state: InvestmentState) -> str:
    """Route after guardian: terminate graph on veto, continue to judge otherwise.

    Reads circuit_breaker from guardian_modifier (typed ConfidenceModifier) as
    the primary source of truth, with guardian_veto boolean as legacy fallback.
    The real guardian agent sets both fields, so this handles both real and mock.
    """
    # Primary: read from typed ConfidenceModifier (real guardian agent output)
    guardian_mod = state.get("guardian_modifier")
    if guardian_mod is not None and hasattr(guardian_mod, "circuit_breaker"):
        circuit_breaker = guardian_mod.circuit_breaker
    else:
        # Legacy fallback for mock guardian (which sets guardian_veto boolean only)
        circuit_breaker = state.get("guardian_veto", False)

    if circuit_breaker:
        return "__end__"
    return "judge"


# ---------------------------------------------------------------------------
# HITL-enabled judge node (wraps real judge with legacy HITL mechanism)
# ---------------------------------------------------------------------------


def judge_with_hitl(state: dict, config: RunnableConfig) -> dict:
    """Judge node with HITL interrupt for low-conviction / circuit-breaker decisions.

    Delegates to the real judge agent which implements the full 7-step Bayesian
    Consensus Algorithm. The real judge detects HITL internally (p_final < 0.40
    OR circuit_breaker), setting judge_hitl=True in its return dict.

    This wrapper reads judge_hitl from the agent result and calls interrupt()
    when triggered, pausing execution for human review.

    CRITICAL: Do NOT place irreversible side effects before interrupt().
    This entire node re-executes from the top when resumed; side effects
    before interrupt() will execute twice.

    TODO (audit_node duplicate): When judge calls interrupt(), audit_node logs
    agent_start BEFORE this function runs. On HITL resume, LangGraph re-executes
    the whole node (including audit_node wrapper), causing a duplicate agent_start
    in the audit trail. Fix deferred — proper distinction between "first execution"
    vs "resumed execution" requires non-trivial audit_node changes.
    """
    # Run real judge logic first (safe to re-run on resume — pure math + LLM)
    result = judge(state, config)

    # judge.py sets judge_hitl=True when p_final < 0.40 OR circuit_breaker is True
    hitl_triggered = result.get("judge_hitl", False)

    if hitl_triggered:
        conviction = result.get("judge_conviction", 0.0)
        # Pause execution — returns to caller with __interrupt__ in result.
        # On resume, interrupt() returns the Command(resume=...) value.
        human_input = interrupt({
            "reason": result.get("judge_hitl_reason", "Human review required"),
            "conviction": conviction,
            "recommendation": result.get("judge_recommendation"),
            "narrative": result.get("judge_narrative"),
        })
        result["human_review"] = human_input

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

    Uses real agent implementations by default. Tests inject lightweight
    substitutes via agent_overrides to avoid network calls.

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
    # Nodes — each real agent wrapped with audit logging.
    # agent_overrides allows test injection of lightweight substitutes.
    # ------------------------------------------------------------------
    builder.add_node(
        "macro_oracle",
        audit_node("macro_oracle", overrides.get("macro_oracle", macro_oracle)),
    )
    builder.add_node(
        "value_hunter",
        audit_node("value_hunter", overrides.get("value_hunter", value_hunter)),
    )
    builder.add_node(
        "bear",
        audit_node("bear", overrides.get("bear", bear)),
    )
    builder.add_node(
        "strategist",
        audit_node("strategist", overrides.get("strategist", strategist)),
    )
    builder.add_node(
        "guardian",
        audit_node("guardian", overrides.get("guardian", guardian)),
    )
    # Judge uses judge_with_hitl by default (wraps real judge with HITL interrupt).
    # Can be overridden in tests via agent_overrides["judge"].
    judge_fn = overrides.get("judge", judge_with_hitl)
    builder.add_node(
        "judge",
        audit_node("judge", judge_fn),
    )
    builder.add_node(
        "optimizer",
        audit_node("optimizer", overrides.get("optimizer", optimizer)),
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
    # Stops on: max iterations reached OR argument exhaustion (Jaccard > 0.85)
    builder.add_conditional_edges(
        "bear",
        should_continue_dialectic,
        {"value_hunter": "value_hunter", "strategist": "strategist"},
    )

    # Guardian veto gate: guardian -> END (veto) or -> judge (pass)
    # Reads from guardian_modifier.circuit_breaker (primary) or guardian_veto (legacy).
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
