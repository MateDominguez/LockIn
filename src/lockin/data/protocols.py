"""
Data source protocols — structural type contracts for all data sources.

Using typing.Protocol with @runtime_checkable so:
  1. Type checkers (mypy/pyright) validate structural compatibility.
  2. isinstance(source, DataSourceProtocol) works at runtime in tests,
     making substitutability explicit and verifiable.

Any class that implements the required methods satisfies the protocol
without inheriting from it — enabling YFinanceSource, MockSource, and
any future source to be used interchangeably in agent code.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from lockin.data.types import FundamentalsResult, MacroResult


@runtime_checkable
class DataSourceProtocol(Protocol):
    """Protocol for fundamental financial data sources.

    Implementors: YFinanceSource (Phase 2), MockSource (tests).
    Consumers: Value Hunter agent, Bear agent (Phase 3).
    """

    def get_fundamentals(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> FundamentalsResult:
        """Fetch fundamental financial data for a given ticker.

        Parameters
        ----------
        ticker : str
            The stock ticker symbol (e.g. "AAPL").
        as_of_date : date | None
            Point-in-time date for look-ahead-safe fetching.
            None means "live" (latest available data).

        Returns
        -------
        FundamentalsResult
            TypedDict with financial fields, fiscal_year_end, and metadata.
        """
        ...


@runtime_checkable
class MacroSourceProtocol(Protocol):
    """Protocol for macroeconomic indicator sources.

    Implementors: FREDSource (Phase 2), MockMacroSource (tests).
    Consumers: Macro Oracle agent (Phase 3).
    """

    def get_macro_indicators(
        self,
        as_of_date: date | None = None,
    ) -> MacroResult:
        """Fetch macroeconomic indicators.

        Parameters
        ----------
        as_of_date : date | None
            Point-in-time date for look-ahead-safe fetching.
            None means "live" (latest available data).

        Returns
        -------
        MacroResult
            TypedDict with 8 FRED indicators and metadata.
        """
        ...
