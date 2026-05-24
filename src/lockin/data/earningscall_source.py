"""
EarningsCallSource — Earnings call transcript fetcher via earningscall.biz.

Live-only: NOT used during backtesting. Activate when the system goes live
with demo users (~5 accounts). The oas_backtest path uses only the quantitative
dimensions (investment_score + consistency_score), not NLP.

Coverage: earningscall.biz has transcripts from 2020 onward — sufficient for
live analysis of current S&P 500 companies.

Cost: ~€20–25/month (paid subscription required for full S&P 500 coverage).

Environment variable required (live only):
    EARNINGSCALL_API_KEY — set in .env when subscribing to earningscall.biz

Graceful degradation: if the library is not installed or the API fails,
get_transcript() returns None. The OAS agent runs without NLP in that case.

## Usage

    from lockin.data.earningscall_source import get_transcript

    text = get_transcript("AAPL", year=2024, quarter=1)
    # → "Good afternoon, and welcome to Apple's first quarter fiscal year 2024..."
    #   Full plain-text transcript, typically 8,000–15,000 words.
    #   Returns None if library not installed, API key not set, or transcript
    #   unavailable — caller must handle None (OAS skips NLP in that case).

    if text is not None:
        word_count = len(text.split())
        # Feed into OAS NLP pipeline (VeTO scoring, sentiment, etc.)
    else:
        # OAS runs on quantitative signals only — no NLP dimension
        pass

    # Results are cached for 30 days (transcripts are immutable after publication),
    # so repeated calls within a session are free.
"""

from __future__ import annotations

import sys

from lockin.data.cache import TTLCache

# 30-day TTL — transcripts are immutable once published
TTL_TRANSCRIPT: int = 30 * 24 * 3600

_TRANSCRIPT_CACHE: TTLCache = TTLCache()

# Tracks whether the earningscall library is importable. Checked once per
# process so we warn only once instead of printing to stderr on every call.
_EARNINGSCALL_AVAILABLE: bool | None = None


def _check_earningscall_available() -> bool:
    """Return True if earningscall library is importable. Warns once if not."""
    global _EARNINGSCALL_AVAILABLE
    if _EARNINGSCALL_AVAILABLE is None:
        try:
            import earningscall  # noqa: F401

            _EARNINGSCALL_AVAILABLE = True
        except ImportError:
            print(
                "[EarningsCallSource] WARNING: 'earningscall' library not installed. "
                "Install with: uv add earningscall\n"
                "Transcripts unavailable — OAS NLP dimension will be skipped.",
                file=sys.stderr,
            )
            _EARNINGSCALL_AVAILABLE = False
    return _EARNINGSCALL_AVAILABLE


def get_transcript(ticker: str, year: int, quarter: int) -> str | None:
    """Fetch an earnings call transcript for the OAS NLP dimension.

    Returns the full transcript text, or None if unavailable for any reason.
    Callers must handle None — the OAS runs without NLP when this returns None.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g. "AAPL").
    year : int
        Fiscal year of the earnings call (e.g. 2024).
    quarter : int
        Fiscal quarter of the earnings call (1–4).

    Returns
    -------
    str | None
        Full transcript text, or None if:
        - earningscall library not installed
        - EARNINGSCALL_API_KEY not configured
        - Transcript not available for the requested period (pre-2020)
        - Any network or API error
    """
    if not _check_earningscall_available():
        return None

    cache_key = f"{ticker}_{year}_Q{quarter}"
    cached = _TRANSCRIPT_CACHE.get(cache_key, TTL_TRANSCRIPT)
    if cached is not None:
        return cached

    try:
        from earningscall import get_company

        company = get_company(ticker)
        transcript = company.get_transcript(year=year, quarter=quarter)
        if transcript and transcript.text:
            _TRANSCRIPT_CACHE.set(cache_key, transcript.text)
            return transcript.text
    except Exception as exc:
        print(
            f"[EarningsCallSource] Could not fetch transcript for "
            f"{ticker} {year} Q{quarter}: {exc}",
            file=sys.stderr,
        )

    return None


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("EarningsCallSource smoke test")
    print("(Requires EARNINGSCALL_API_KEY and 'earningscall' library installed)")

    result = get_transcript("AAPL", year=2024, quarter=1)
    if result:
        preview = result[:300].replace("\n", " ")
        print(f"AAPL Q1 2024: {len(result)} chars")
        print(f"Preview: {preview}...")
    else:
        print(
            "Transcript not available — library not installed or API key not set. "
            "This is expected if earningscall is not yet configured."
        )

    # Confirm cache works: second call must return cached result
    result2 = get_transcript("AAPL", year=2024, quarter=1)
    if result and result2:
        assert result == result2, "Cache mismatch"
        print("Cache: OK (second call returned same result)")

    print("OK")
