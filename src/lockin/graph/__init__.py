"""lockin.graph — LangGraph StateGraph and supporting types."""

from lockin.graph.state import InvestmentState, create_initial_state

__all__ = [
    "InvestmentState",
    "create_initial_state",
    "create_graph",
    "postgres_checkpointer",
]


def __getattr__(name: str):
    """Lazy-import graph builder symbols to avoid circular import at module init time.

    lockin.graph.builder imports lockin.agents.mock, which in turn imports
    lockin.graph.state. If we eagerly imported builder here, Python would try to
    initialise lockin.graph (this module) before it is ready, causing an
    ImportError on 'mock_bear' from the partially initialised agents.mock module.

    By deferring builder imports until first access, the module graph is fully
    initialised before the cross-package reference is resolved.
    """
    if name in ("create_graph", "postgres_checkpointer"):
        from lockin.graph import builder as _builder
        return getattr(_builder, name)
    raise AttributeError(f"module 'lockin.graph' has no attribute {name!r}")
