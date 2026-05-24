"""
SP500Universe — Historical S&P 500 composition lookup.

Data source: github.com/fja05680/sp500
CSV format: 'date' column (YYYY-MM-DD) and 'tickers' column (comma-separated).
Each row represents a composition change on that date. The lookup returns the
most recent row with date <= as_of, so intermediate dates are automatically
covered by the last published change.

Download the CSV once before using this module:
    mkdir -p data/reference
    curl -L "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes.csv" \\
         -o data/reference/sp500_historical_components.csv

Commit the CSV to the repository — it is static reference data, not market
data, and changes infrequently.

## Usage

    from datetime import date
    from lockin.data.sp500_universe import get_sp500_tickers_at_date

    # Who was in the index on a given date?
    tickers = get_sp500_tickers_at_date(date(2014, 1, 1))
    # → ['A', 'AAL', 'AAP', ...] — ~503 tickers, sorted alphabetically

    # Survivorship-bias check: the CSV uses LEHMQ (Lehman's post-bankruptcy OTC
    # ticker). LEHMQ dropped off the composition on 2008-09-17 (after bankruptcy).
    assert "LEHMQ" in get_sp500_tickers_at_date(date(2008, 1, 1))   # True
    assert "LEHMQ" not in get_sp500_tickers_at_date(date(2009, 1, 1))  # True

    # Typical backtest loop: fetch the real universe for each quarter
    for year in range(2014, 2025):
        universe = get_sp500_tickers_at_date(date(year, 1, 1))
        # run screening on `universe` — no look-ahead, no survivorship bias
"""

from __future__ import annotations

import csv
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

# Matches the -YYYYMM removal-date suffix backfilled by the dataset maintainer.
# e.g. "LEHMQ-201203" → "LEHMQ", "AAL-199702" → "AAL"
# Active (currently listed) tickers have no suffix and are returned as-is.
_SUFFIX_RE = re.compile(r"-\d{6}$")

# ---------------------------------------------------------------------------
# CSV path — resolved relative to this file (4 parents up = project root)
# src/lockin/data/sp500_universe.py → src/lockin/data → src/lockin → src → root
# ---------------------------------------------------------------------------

SP500_CSV: Path = (
    Path(__file__).parent.parent.parent.parent
    / "data"
    / "reference"
    / "sp500_historical_components.csv"
)

_DOWNLOAD_INSTRUCTIONS = (
    "Download it with:\n"
    "  mkdir -p data/reference\n"
    '  curl -L "https://raw.githubusercontent.com/fja05680/sp500/master/'
    'S%26P%20500%20Historical%20Components%20%26%20Changes.csv" \\\n'
    "       -o data/reference/sp500_historical_components.csv"
)


@lru_cache(maxsize=1)
def _load_sp500_history() -> tuple[tuple[date, tuple[str, ...]], ...]:
    """Load full composition history from CSV. Cached — loads once per process.

    Uses tuples (not lists) to satisfy lru_cache hashability requirement.

    Returns
    -------
    tuple of (date, tuple[str, ...]) sorted ascending by date.

    Raises
    ------
    FileNotFoundError
        If the CSV file has not been downloaded yet.
    KeyError
        If the CSV column names differ from the expected 'date' and 'tickers'.
    """
    if not SP500_CSV.exists():
        raise FileNotFoundError(
            f"S&P 500 historical composition CSV not found at:\n  {SP500_CSV}\n\n"
            f"{_DOWNLOAD_INSTRUCTIONS}"
        )

    rows: list[tuple[date, tuple[str, ...]]] = []
    with open(SP500_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "date" not in reader.fieldnames or "tickers" not in reader.fieldnames:
            actual = list(reader.fieldnames or [])
            raise KeyError(
                f"Expected columns 'date' and 'tickers' in {SP500_CSV}. "
                f"Got: {actual}. "
                "Check the CSV header and update _load_sp500_history() if needed."
            )
        for row in reader:
            d = date.fromisoformat(row["date"])
            tickers = tuple(
                _SUFFIX_RE.sub("", t.strip())
                for t in row["tickers"].split(",")
                if t.strip()
            )
            rows.append((d, tickers))

    rows.sort(key=lambda x: x[0])
    return tuple(rows)


def get_sp500_tickers_at_date(as_of: date) -> list[str]:
    """Return the S&P 500 composition on a given date.

    Uses the most recent composition row with date <= as_of. This matches how
    index changes are published: a change on date D is valid from D onward.

    Parameters
    ----------
    as_of : date
        The date for which to retrieve the index composition.

    Returns
    -------
    list[str]
        Ticker symbols in the S&P 500 on the given date (~500 tickers).

    Raises
    ------
    ValueError
        If as_of predates the first available composition row.
    FileNotFoundError
        If the composition CSV has not been downloaded.
    """
    history = _load_sp500_history()
    result: tuple[str, ...] | None = None
    for row_date, tickers in history:
        if row_date <= as_of:
            result = tickers
        else:
            break
    if result is None:
        first_date = history[0][0] if history else "unknown"
        raise ValueError(
            f"No S&P 500 composition data available for {as_of}. "
            f"Earliest available date in CSV: {first_date}."
        )
    return list(result)


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import date as _date

    print("SP500Universe smoke test")

    jan_2014 = get_sp500_tickers_at_date(_date(2014, 1, 1))
    print(f"2014-01-01: {len(jan_2014)} tickers")
    assert len(jan_2014) > 400, f"Expected ~500, got {len(jan_2014)}"

    jan_2008 = get_sp500_tickers_at_date(_date(2008, 1, 1))
    jan_2009 = get_sp500_tickers_at_date(_date(2009, 1, 1))
    # The CSV uses LEHMQ (Lehman's post-bankruptcy OTC ticker), not LEH.
    # LEHMQ dropped off the composition list on 2008-09-17 (after the bankruptcy).
    print(f"LEHMQ in 2008-01-01: {'LEHMQ' in jan_2008}")   # True — Lehman Brothers
    print(f"LEHMQ in 2009-01-01: {'LEHMQ' in jan_2009}")   # False — removed Sep 2008
    assert "LEHMQ" in jan_2008, "Expected LEHMQ in 2008 composition"
    assert "LEHMQ" not in jan_2009, "Expected LEHMQ absent from 2009 composition"

    # lru_cache: second call must be instant (no re-read)
    jan_2023 = get_sp500_tickers_at_date(_date(2023, 1, 1))
    print(f"2023-01-01: {len(jan_2023)} tickers")
    assert len(jan_2023) > 400, f"Expected ~500, got {len(jan_2023)}"

    print("OK")
