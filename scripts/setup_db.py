"""
One-time database setup script.

Creates:
- LangGraph checkpoint tables (via PostgresSaver.setup())
- pgvector extension (for Phase 3 RAG)
- audit_logs table (custom, for HITL audit trail)

Run once after setting up Supabase:
    uv run python scripts/setup_db.py
"""

import os
import sys
from pathlib import Path

# Load .env from project root
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"

if not env_file.exists():
    print("ERROR: .env file not found. Copy .env.example to .env and fill in your values.")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(env_file)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

print(f"Connecting to: {database_url[:50]}...")

# 1. LangGraph checkpoint tables
print("\n[1/3] Setting up LangGraph checkpoint tables...")
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string(database_url) as checkpointer:
    checkpointer.setup()
print("      OK — checkpoint_migrations, checkpoints, checkpoint_blobs, checkpoint_writes created")

# 2. pgvector + audit_logs via raw psycopg
print("\n[2/3] Enabling pgvector extension...")
import psycopg

with psycopg.connect(database_url) as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
print("      OK — vector extension enabled")

# 3. Custom tables
print("\n[3/3] Creating custom tables...")
CREATE_AUDIT_LOGS = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id      TEXT NOT NULL,
    asset_ticker    TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    event_type      TEXT NOT NULL,  -- agent_start | agent_end | hitl_trigger | hitl_response | veto
    payload         JSONB,
    thread_id       TEXT,           -- links to LangGraph checkpoint thread
    session_id      TEXT
);

CREATE INDEX IF NOT EXISTS audit_logs_request_id_idx ON audit_logs(request_id);
CREATE INDEX IF NOT EXISTS audit_logs_asset_ticker_idx ON audit_logs(asset_ticker);
CREATE INDEX IF NOT EXISTS audit_logs_created_at_idx ON audit_logs(created_at DESC);
"""

with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_AUDIT_LOGS)
    conn.commit()
print("      OK — audit_logs table created")

print("\nDatabase setup complete. You're ready for Phase 1.")
