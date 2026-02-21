"""
Audit trail logger for the LangGraph investment analysis pipeline.

Provides two public functions:
  - log_audit_event: writes a single audit record to the audit_logs table
  - audit_node: wraps any agent function to emit agent_start / agent_end events

Design notes:
  - audit_node uses a *separate* short-lived psycopg connection, distinct from
    the LangGraph PostgreSQL checkpointer connection, to avoid transaction
    conflicts (checkpointer holds open transactions; inserting inside that same
    connection can deadlock or corrupt checkpoint state).
  - When DATABASE_URL is not set (e.g. local dev / CI), log_audit_event falls
    back to stderr so the pipeline still runs without a real DB connection.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Callable

import psycopg
from langchain_core.runnables import RunnableConfig

from lockin.utils.config import get_settings


# ---------------------------------------------------------------------------
# Core persistence helper
# ---------------------------------------------------------------------------


def log_audit_event(
    database_url: str,
    thread_id: str,
    agent_name: str,
    event_type: str,
    state_snapshot: dict,
    asset_ticker: str | None = None,
    request_id: str | None = None,
) -> None:
    """Log an audit event to the audit_logs table.

    Uses a separate short-lived connection to avoid conflicts with the
    LangGraph checkpointer's connection/transactions.

    Actual table schema (Supabase):
        id BIGSERIAL, created_at TIMESTAMPTZ, request_id TEXT,
        asset_ticker TEXT, agent_name TEXT, event_type TEXT,
        payload JSONB, thread_id TEXT, session_id TEXT

    Args:
        database_url: PostgreSQL connection string. If empty, falls back to
            stderr logging so the pipeline works without a DB.
        thread_id: LangGraph thread_id from config.configurable.
        agent_name: Name of the agent being logged (e.g. "macro_oracle").
        event_type: "agent_start" | "agent_end".
        state_snapshot: A (possibly partial) dict of state fields to record
            (stored in the payload JSONB column).
        asset_ticker: Optional ticker symbol extracted from state.
        request_id: Optional request ID extracted from state.
    """
    if not database_url:
        print(
            f"[AUDIT] {event_type}: {agent_name} (thread={thread_id})",
            file=sys.stderr,
        )
        return

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audit_logs
                       (thread_id, agent_name, event_type, payload,
                        asset_ticker, request_id, session_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    thread_id,
                    agent_name,
                    event_type,
                    json.dumps(state_snapshot, default=str),
                    asset_ticker,
                    request_id,
                    thread_id,  # session_id mirrors thread_id for now
                ),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Agent wrapper
# ---------------------------------------------------------------------------


def audit_node(agent_name: str, fn: Callable) -> Callable:
    """Wrap an agent function with audit logging (start + end events).

    The wrapper emits two audit events per agent execution:
      1. agent_start — before the agent runs (logs asset_ticker, bull_iteration)
      2. agent_end   — after the agent runs (logs the agent's output dict)

    This provides a complete, ordered audit trail of every state transition
    through the graph, satisfying CORE-02 (glass-box transparency).

    Args:
        agent_name: Identifier used in audit records (e.g. "macro_oracle").
        fn: The agent callable with signature (state, config) -> dict.

    Returns:
        A new callable with the same signature, augmented with audit logging.
        The wrapper's __name__ is set to "audit_{agent_name}" for debuggability.
    """

    def wrapper(state: dict, config: RunnableConfig) -> dict:
        settings = get_settings()
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        asset_ticker = state.get("asset_ticker")
        request_id = state.get("request_id")

        # Log start — only a minimal subset of state to keep payloads small
        log_audit_event(
            settings.database_url,
            thread_id,
            agent_name,
            "agent_start",
            {
                "asset_ticker": asset_ticker,
                "bull_iteration": state.get("bull_iteration"),
            },
            asset_ticker=asset_ticker,
            request_id=request_id,
        )

        # Execute the underlying agent
        result = fn(state, config)

        # Log end — record the agent's full output dict
        log_audit_event(
            settings.database_url,
            thread_id,
            agent_name,
            "agent_end",
            result,
            asset_ticker=asset_ticker,
            request_id=request_id,
        )

        return result

    wrapper.__name__ = f"audit_{agent_name}"
    return wrapper
