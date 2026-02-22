"""
TTLCache — In-memory TTL (time-to-live) cache with stale fallback.

Design decisions:
- Instance-based (not a singleton): callers inject a fresh TTLCache so tests
  remain isolated and state doesn't bleed across runs.
- Stale fallback: get_stale() returns expired data rather than None when a
  re-fetch fails (graceful degradation for production use).
- Pure Python + stdlib: no external dependencies.

TTL constants are defined at module level so every caller uses the same
value without hardcoding numbers throughout the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# TTL constants (seconds)
# ---------------------------------------------------------------------------

TTL_FUNDAMENTALS: int = 86_400      # 24 hours — fundamentals change once a year
TTL_MACRO: int = 604_800            # 7 days  — macro indicators change monthly


# ---------------------------------------------------------------------------
# Internal storage entry
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    """A single cached item with its fetch timestamp."""

    data: Any
    fetched_at: datetime


# ---------------------------------------------------------------------------
# TTLCache
# ---------------------------------------------------------------------------

class TTLCache:
    """In-memory TTL cache with stale-data fallback.

    Usage
    -----
    cache = TTLCache()

    cache.set("AAPL", fundamentals_result)

    fresh = cache.get("AAPL", ttl_seconds=TTL_FUNDAMENTALS)
    # Returns data if within TTL, else None.

    stale = cache.get_stale("AAPL")
    # Returns data regardless of TTL (for fallback when re-fetch fails).
    """

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        """Return cached data if within TTL, else None.

        Parameters
        ----------
        key : str
            Cache key (e.g. ticker symbol or "macro").
        ttl_seconds : int
            Maximum age in seconds before the entry is considered expired.

        Returns
        -------
        Any | None
            Cached data, or None if missing or expired.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        age = (datetime.now(timezone.utc) - entry.fetched_at).total_seconds()
        if age > ttl_seconds:
            return None
        return entry.data

    def get_stale(self, key: str) -> Any | None:
        """Return cached data regardless of TTL.

        Use this as a fallback when a re-fetch fails and stale data is
        preferable to raising an error (graceful degradation).

        Parameters
        ----------
        key : str
            Cache key.

        Returns
        -------
        Any | None
            Cached data regardless of age, or None if key was never set.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        return entry.data

    def set(self, key: str, data: Any) -> None:
        """Store data with the current UTC timestamp.

        Parameters
        ----------
        key : str
            Cache key.
        data : Any
            Data to cache (typically a FundamentalsResult or MacroResult).
        """
        self._store[key] = CacheEntry(
            data=data,
            fetched_at=datetime.now(timezone.utc),
        )

    def clear(self) -> None:
        """Empty the entire store.

        Primarily for test isolation — call in setUp/tearDown to ensure
        no cross-test state contamination.
        """
        self._store.clear()
