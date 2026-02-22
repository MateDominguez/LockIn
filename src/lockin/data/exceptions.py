"""
Data layer custom exceptions.

DataUnavailableError — raised when a data source is unreachable AND no cached
    data exists (cold-start + source-down scenario).

LookAheadError — raised when point-in-time enforcement detects that a data
    record's date is newer than the requested as_of_date, which would
    introduce look-ahead bias into backtesting or evaluation.
"""

from __future__ import annotations


class DataUnavailableError(Exception):
    """Raised when a data source cannot be reached and no cache exists.

    Attributes
    ----------
    ticker : str
        The ticker symbol being fetched when the error occurred.
    source : str
        The data source name (e.g. "yfinance", "fred").
    """

    def __init__(self, ticker: str, source: str, message: str = "") -> None:
        self.ticker = ticker
        self.source = source
        default_msg = (
            f"Data unavailable for ticker '{ticker}' from source '{source}'. "
            "Source is unreachable and no cached data exists."
        )
        super().__init__(message or default_msg)


class LookAheadError(Exception):
    """Raised when point-in-time enforcement detects future data leak.

    This prevents look-ahead bias: a data record dated *after* the
    requested as_of_date cannot legally be used in analysis for that date.

    Attributes
    ----------
    as_of_date : str
        The requested analysis date (ISO format).
    data_date : str
        The actual date of the data record that triggered the check.
    """

    def __init__(self, as_of_date: str, data_date: str, message: str = "") -> None:
        self.as_of_date = as_of_date
        self.data_date = data_date
        default_msg = (
            f"Look-ahead bias detected: data dated '{data_date}' "
            f"is newer than the requested as_of_date '{as_of_date}'."
        )
        super().__init__(message or default_msg)
