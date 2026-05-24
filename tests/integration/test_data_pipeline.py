"""
Integration tests for the data pipeline (mock-based, no internet/API keys).

Tests the full pipeline composition:
  - PointInTimeData wrapper (date enforcement + live bypass)
  - DataValidator (quality score, missing fields)
  - DataUnavailableError propagation

All tests use mock sources injected via PointInTimeData's constructor, so no
FRED API key, yfinance connection, or database is required to run these tests.

Run with:
    python -m pytest tests/integration/test_data_pipeline.py -v
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from lockin.data.exceptions import DataUnavailableError
from lockin.data.point_in_time import PointInTimeData
from lockin.data.data_types import FundamentalsResult, MacroResult
from lockin.data.validator import DataValidator


# ---------------------------------------------------------------------------
# Helpers: minimal mock sources
# ---------------------------------------------------------------------------


def _make_full_fundamentals(ticker: str = "AAPL") -> FundamentalsResult:
    """Return a FundamentalsResult with all required fields populated."""
    return FundamentalsResult(
        ticker=ticker,
        total_revenue=394_328_000_000.0,
        net_income=96_995_000_000.0,
        gross_profit=169_148_000_000.0,
        operating_income=114_301_000_000.0,
        ebitda=130_000_000_000.0,
        diluted_eps=6.13,
        free_cash_flow=99_584_000_000.0,
        total_assets=352_583_000_000.0,
        total_debt=109_280_000_000.0,
        cash_and_equivalents=29_965_000_000.0,
        total_equity=62_146_000_000.0,
        fiscal_year_end=date(2023, 9, 30),
        source="mock",
        fetched_at=datetime.now(timezone.utc),
        as_of_date="live",
        data_freshness="FRESH",
    )


def _make_partial_fundamentals(ticker: str = "AAPL") -> FundamentalsResult:
    """Return a FundamentalsResult with only 4 of 7 required fields present."""
    return FundamentalsResult(
        ticker=ticker,
        total_revenue=394_328_000_000.0,
        net_income=96_995_000_000.0,
        total_assets=352_583_000_000.0,
        total_equity=62_146_000_000.0,
        # Missing: total_debt, cash_and_equivalents, diluted_eps
        source="mock",
        fetched_at=datetime.now(timezone.utc),
        as_of_date="live",
        data_freshness="FRESH",
    )


def _make_macro_result() -> MacroResult:
    """Return a minimal MacroResult."""
    return MacroResult(
        gdp=27_357.7,
        fed_funds=5.33,
        unemployment=3.7,
        source="mock",
        fetched_at=datetime.now(timezone.utc),
        as_of_date="live",
        data_freshness="FRESH",
    )


class MockSource:
    """Minimal DataSourceProtocol implementor returning _make_full_fundamentals."""

    def __init__(self, result: FundamentalsResult | None = None) -> None:
        self._result = result or _make_full_fundamentals()
        self.last_as_of_date: date | None = "NOT_CALLED"  # type: ignore[assignment]

    def get_fundamentals(
        self, ticker: str, as_of_date: date | None = None
    ) -> FundamentalsResult:
        self.last_as_of_date = as_of_date
        return self._result


class FailingSource:
    """DataSourceProtocol implementor that always raises DataUnavailableError."""

    def get_fundamentals(
        self, ticker: str, as_of_date: date | None = None
    ) -> FundamentalsResult:
        raise DataUnavailableError(ticker=ticker, source="mock_failing")


class MockMacro:
    """Minimal MacroSourceProtocol implementor."""

    def get_macro_indicators(self, as_of_date: date | None = None) -> MacroResult:
        return _make_macro_result()


# ---------------------------------------------------------------------------
# Test 1: get_fundamentals via PointInTimeData with mock source
# ---------------------------------------------------------------------------


class TestGetFundamentalsMockNoStorage:
    """Test that PointInTimeData correctly delegates to mock sources."""

    def test_returns_ticker_source_freshness_fields(self) -> None:
        """Result includes ticker, source, data_freshness from mock source."""
        pit = PointInTimeData(MockSource(), MockMacro())
        result = pit.get_fundamentals("AAPL")

        assert result["ticker"] == "AAPL"
        assert result["source"] == "mock"
        assert result["data_freshness"] == "FRESH"

    def test_validator_returns_quality_score_for_full_result(self) -> None:
        """DataValidator returns quality_score=1.0 for fully populated result."""
        full = _make_full_fundamentals()
        validator = DataValidator()
        validation = validator.validate_fundamentals(full)

        assert "quality_score" in validation
        assert validation["quality_score"] == 1.0
        assert validation["missing_fields"] == []

    def test_validator_returns_correct_structure(self) -> None:
        """ValidationResult always has all 5 required keys."""
        full = _make_full_fundamentals()
        validator = DataValidator()
        validation = validator.validate_fundamentals(full)

        assert "quality_score" in validation
        assert "missing_fields" in validation
        assert "outlier_flags" in validation
        assert "hitl_required" in validation
        assert "hitl_reason" in validation


# ---------------------------------------------------------------------------
# Test 2: DataValidator quality_score for partial result
# ---------------------------------------------------------------------------


class TestGetFundamentalsValidatesQualityScore:
    """Validate that quality_score reflects missing required fields."""

    def test_partial_result_has_low_quality_score(self) -> None:
        """4 of 7 required fields present → quality_score = 4/7 ≈ 0.571."""
        partial = _make_partial_fundamentals()
        validator = DataValidator()
        validation = validator.validate_fundamentals(partial)

        expected_score = 4 / 7
        assert abs(validation["quality_score"] - expected_score) < 0.001
        assert validation["quality_score"] < 1.0

    def test_partial_result_lists_missing_fields(self) -> None:
        """Missing required fields are reported in missing_fields list."""
        partial = _make_partial_fundamentals()
        validator = DataValidator()
        validation = validator.validate_fundamentals(partial)

        missing = validation["missing_fields"]
        assert len(missing) == 3, f"Expected 3 missing fields, got: {missing}"
        assert "total_debt" in missing
        assert "cash_and_equivalents" in missing
        assert "diluted_eps" in missing


# ---------------------------------------------------------------------------
# Test 3: Future date raises ValueError
# ---------------------------------------------------------------------------


class TestPointInTimeFutureDateRaises:
    """PointInTimeData must reject future as_of_date with ValueError."""

    def test_future_date_raises_value_error(self) -> None:
        """as_of_date one day in the future raises ValueError."""
        pit = PointInTimeData(MockSource(), MockMacro())
        future = date.today() + timedelta(days=1)

        with pytest.raises(ValueError) as exc_info:
            pit.get_fundamentals("AAPL", as_of_date=future)

        assert "future" in str(exc_info.value).lower()

    def test_future_date_message_includes_date(self) -> None:
        """Error message includes the rejected future date."""
        pit = PointInTimeData(MockSource(), MockMacro())
        future = date.today() + timedelta(days=30)

        with pytest.raises(ValueError) as exc_info:
            pit.get_fundamentals("AAPL", as_of_date=future)

        assert str(future) in str(exc_info.value)

    def test_future_date_macro_raises_value_error(self) -> None:
        """Future date also raises ValueError for macro indicators."""
        pit = PointInTimeData(MockSource(), MockMacro())
        future = date.today() + timedelta(days=1)

        with pytest.raises(ValueError):
            pit.get_macro_indicators(as_of_date=future)


# ---------------------------------------------------------------------------
# Test 4: Live bypass passes as_of_date=None to source
# ---------------------------------------------------------------------------


class TestPointInTimeLiveBypassesEnforcement:
    """Live analysis (today or None) must not raise and must call source with None."""

    def test_today_does_not_raise(self) -> None:
        """as_of_date=date.today() is treated as live and does not raise."""
        mock_source = MockSource()
        pit = PointInTimeData(mock_source, MockMacro())

        # Should not raise ValueError
        result = pit.get_fundamentals("AAPL", as_of_date=date.today())
        assert result["ticker"] == "AAPL"

    def test_today_calls_source_with_none(self) -> None:
        """Live bypass passes as_of_date=None to source (not date.today())."""
        mock_source = MockSource()
        pit = PointInTimeData(mock_source, MockMacro())

        pit.get_fundamentals("AAPL", as_of_date=date.today())

        # Source should have been called with None (live bypass)
        assert mock_source.last_as_of_date is None, (
            f"Expected source called with None, got: {mock_source.last_as_of_date}"
        )

    def test_none_does_not_raise(self) -> None:
        """as_of_date=None (live) does not raise."""
        pit = PointInTimeData(MockSource(), MockMacro())
        result = pit.get_fundamentals("AAPL", as_of_date=None)
        assert result["ticker"] == "AAPL"

    def test_none_calls_source_with_none(self) -> None:
        """as_of_date=None passes None through to source."""
        mock_source = MockSource()
        pit = PointInTimeData(mock_source, MockMacro())

        pit.get_fundamentals("AAPL", as_of_date=None)

        assert mock_source.last_as_of_date is None


# ---------------------------------------------------------------------------
# Test 5: DataUnavailableError propagates from PointInTimeData
# ---------------------------------------------------------------------------


class TestDataUnavailableErrorPropagates:
    """DataUnavailableError from source must propagate through PointInTimeData."""

    def test_failing_source_raises_data_unavailable_error(self) -> None:
        """PointInTimeData propagates DataUnavailableError from source."""
        pit = PointInTimeData(FailingSource(), MockMacro())

        with pytest.raises(DataUnavailableError):
            pit.get_fundamentals("FAIL")

    def test_error_has_ticker_attribute(self) -> None:
        """DataUnavailableError exposes .ticker attribute for diagnostics."""
        pit = PointInTimeData(FailingSource(), MockMacro())

        with pytest.raises(DataUnavailableError) as exc_info:
            pit.get_fundamentals("BADTICKER")

        assert exc_info.value.ticker == "BADTICKER"

    def test_error_has_source_attribute(self) -> None:
        """DataUnavailableError exposes .source attribute for diagnostics."""
        pit = PointInTimeData(FailingSource(), MockMacro())

        with pytest.raises(DataUnavailableError) as exc_info:
            pit.get_fundamentals("BADTICKER")

        assert exc_info.value.source == "mock_failing"
