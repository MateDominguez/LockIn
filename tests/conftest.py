"""
Shared pytest fixtures for the LockIn test suite.

Provides graph, initial state, and config fixtures used across e2e tests.
All fixtures use MemorySaver for fast, in-process checkpointing (no DB required).
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from lockin.graph.builder import create_graph
from lockin.graph.state import create_initial_state


@pytest.fixture
def memory_saver():
    """Return a fresh MemorySaver instance for each test."""
    return MemorySaver()


@pytest.fixture
def graph_with_memory(memory_saver):
    """Return a compiled graph with MemorySaver checkpointing."""
    return create_graph(checkpointer=memory_saver)


# Keep 'graph' as an alias so plan tests that use 'graph' fixture work too.
@pytest.fixture
def graph(memory_saver):
    """Return a compiled graph with MemorySaver checkpointing."""
    return create_graph(checkpointer=memory_saver)


@pytest.fixture
def initial_state():
    """Return a minimal initial InvestmentState for AAPL."""
    return create_initial_state("AAPL")


@pytest.fixture
def thread_config():
    """Return a LangGraph config dict with a stable thread_id."""
    return {"configurable": {"thread_id": "test-run-1"}}
