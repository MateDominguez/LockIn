"""
PointInTimeData — Thin wrapper that enforces point-in-time date contracts.

This wrapper sits between agents and the concrete data sources (YFinanceSource,
FREDSource). Its sole responsibility is:

  1. **Future date guard:** Reject analysis dates in the future (they don't exist).
  2. **Live analysis bypass:** Skip date enforcement when as_of_date is None or
     today — this is a live (real-time) run, not a backtest.
  3. **Historical delegation:** For past dates, delegate to the source which
     applies its own PIT filter (e.g. ALFRED vintage dates for FRED, income
     statement column filtering for yfinance).

The wrapper does NOT duplicate date-filtering logic already in the sources.
The sources are responsible for the 7-day and 14-day look-ahead tolerances.

Design notes:
- Constructor accepts protocol-typed sources so any implementation (concrete
  or mock) can be injected — enables test isolation without patching.
- LOOKAHEAD_DAYS is informational metadata consumed by orchestration agents
  that need to know the tolerance used per data category.

Usage
-----
from lockin.data.point_in_time import PointInTimeData, LOOKAHEAD_DAYS

pit = PointInTimeData(YFinanceSource(), FREDSource())
result = pit.get_fundamentals("AAPL")
result_pit = pit.get_fundamentals("AAPL", as_of_date=date(2023, 6, 1))
"""

from __future__ import annotations

from datetime import date

from lockin.data.exceptions import DataUnavailableError, LookAheadError  # noqa: F401 (re-export for callers)
from lockin.data.protocols import DataSourceProtocol, MacroSourceProtocol
from lockin.data.data_types import FundamentalsResult, MacroResult


# ---------------------------------------------------------------------------
# Look-ahead tolerance by data category (in calendar days)
# ---------------------------------------------------------------------------

#: Maximum number of days a data record can lag behind the requested as_of_date
#: before it is considered look-ahead-biased for that category.
#: - prices=0: market prices are available daily; no tolerance.
#: - fundamentals=7: annual reports become public ~7 days after filing date.
#: - macro=14: FRED indicators typically publish 1–2 weeks after the period end.
LOOKAHEAD_DAYS: dict[str, int] = {
    "prices": 0,
    "fundamentals": 7,
    "macro": 14,
}


# ---------------------------------------------------------------------------
# PointInTimeData wrapper
# ---------------------------------------------------------------------------


class PointInTimeData:
    """Enforces point-in-time date contract over any DataSourceProtocol pair.

    Parameters
    ----------
    source : DataSourceProtocol
        Concrete fundamental data source (e.g. YFinanceSource).
    macro : MacroSourceProtocol
        Concrete macro data source (e.g. FREDSource).
    """

    def __init__(
        self,
        source: DataSourceProtocol,
        macro: MacroSourceProtocol,
    ) -> None:
        self._source = source
        self._macro = macro

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_fundamentals(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> FundamentalsResult:
        """Fetch fundamental data with point-in-time enforcement.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol (e.g. "AAPL").
        as_of_date : date | None
            Analysis date.
            - None → live (latest available data, no date enforcement).
            - date.today() → same as live (live analysis bypass).
            - Past date → historical delegation to source's PIT filter.
            - Future date → ValueError raised immediately.

        Returns
        -------
        FundamentalsResult
            Validated, point-in-time-correct fundamentals.

        Raises
        ------
        ValueError
            If as_of_date is in the future.
        DataUnavailableError
            If the source cannot return data for the requested ticker.
        """
        self._guard_future_date(as_of_date)

        # Live analysis bypass — skip date enforcement
        if as_of_date is None or as_of_date == date.today():
            return self._source.get_fundamentals(ticker, as_of_date=None)

        # Historical analysis — delegate to source (applies 7-day tolerance)
        return self._source.get_fundamentals(ticker, as_of_date=as_of_date)

    def get_macro_indicators(
        self,
        as_of_date: date | None = None,
    ) -> MacroResult:
        """Fetch macro indicators with point-in-time enforcement.

        Parameters
        ----------
        as_of_date : date | None
            Analysis date.
            - None → live (latest available data, no date enforcement).
            - date.today() → same as live (live analysis bypass).
            - Past date → historical delegation to source's PIT filter.
            - Future date → ValueError raised immediately.

        Returns
        -------
        MacroResult
            Validated, point-in-time-correct macro indicators.

        Raises
        ------
        ValueError
            If as_of_date is in the future.
        DataUnavailableError
            If the FRED source cannot return any data.
        """
        self._guard_future_date(as_of_date)

        # Live analysis bypass — skip date enforcement
        if as_of_date is None or as_of_date == date.today():
            return self._macro.get_macro_indicators(as_of_date=None)

        # Historical analysis — delegate to source (applies 14-day tolerance)
        return self._macro.get_macro_indicators(as_of_date=as_of_date)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guard_future_date(as_of_date: date | None) -> None:
        """Raise ValueError if as_of_date is strictly in the future.

        Parameters
        ----------
        as_of_date : date | None
            The date to check. None is allowed (means live).

        Raises
        ------
        ValueError
            If as_of_date > date.today().
        """
        if as_of_date is not None and as_of_date > date.today():
            raise ValueError(
                f"as_of_date {as_of_date} is in the future "
                f"(today={date.today()})"
            )
