"""
Environment configuration loader.

Reads variables from the .env file at project root via python-dotenv and
exposes them through a cached Settings dataclass.  Callers should import
get_settings() rather than reading os.environ directly so that:
  - All config is centralised and documented in one place.
  - lru_cache() ensures .env is only read once per process.
  - Missing keys are silently defaulted to "" (agents should validate
    at call-time, not at import-time).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Load .env from project root (the directory that contains this package).
# safe to call multiple times — subsequent calls are no-ops.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime environment variables."""

    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    google_api_key: str = ""
    fred_api_key: str = ""
    env: str = "development"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings loaded from environment / .env file."""
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY", "")),
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        fred_api_key=os.getenv("FRED_API_KEY", ""),
        env=os.getenv("ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
