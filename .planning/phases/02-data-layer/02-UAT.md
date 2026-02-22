---
status: complete
phase: 02-data-layer
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md
started: 2026-02-22T00:00:00Z
updated: 2026-02-22T00:00:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. YFinance live fundamentals fetch (AAPL)
expected: |
  uv run python -c "from lockin.data.yfinance_source import YFinanceSource; r = YFinanceSource().get_fundamentals('AAPL'); print('revenue:', r.get('total_revenue')); print('source:', r.get('source')); print('freshness:', r.get('data_freshness'))"
  Should print revenue ~390B, source=yfinance, freshness=FRESH
result: pass

### 2. YFinance returns all required fields
expected: |
  uv run python -c "from lockin.data.yfinance_source import YFinanceSource; from lockin.data.types import REQUIRED_FUNDAMENTAL_FIELDS; r = YFinanceSource().get_fundamentals('AAPL'); missing = [f for f in REQUIRED_FUNDAMENTAL_FIELDS if not r.get(f)]; print('missing fields:', missing)"
  Should print: missing fields: []  (all 7 required fields present)
result: pass

### 3. FRED live macro indicators fetch
expected: |
  uv run python -c "from lockin.data.fred_source import FREDSource; m = FREDSource().get_macro_indicators(); print('gdp:', m.get('gdp')); print('fed_funds:', m.get('fed_funds')); print('unemployment:', m.get('unemployment')); print('source:', m.get('source'))"
  Should print GDP ~25000+, fed_funds some positive number, unemployment ~4.0, source=fred
result: pass

### 4. FRED manufacturing_pmi is None (NAPM series unavailable)
expected: |
  uv run python -c "from lockin.data.fred_source import FREDSource; m = FREDSource().get_macro_indicators(); print('manufacturing_pmi:', m.get('manufacturing_pmi')); print('gdp still present:', m.get('gdp') is not None)"
  Should print: manufacturing_pmi: None, gdp still present: True
  (NAPM series was removed from public FRED — graceful None, no crash)
result: issue
reported: "manufacturing_pmi is None but NAPM should be deleted from the code or noted as unsupported — it's misleading to have a field that silently always returns None"
severity: minor

### 5. Historical point-in-time query (pre-2023 AAPL)
expected: |
  uv run python -c "from lockin.data.yfinance_source import YFinanceSource; from datetime import date; r = YFinanceSource().get_fundamentals('AAPL', as_of_date=date(2022, 12, 31)); print('fiscal_year_end:', r.get('fiscal_year_end')); print('revenue:', r.get('total_revenue'))"
  Should print fiscal_year_end of 2022-09-24 (or similar pre-2023 date), revenue from that year (Apple FY2022 ~$394B)
result: pass

### 6. TTL cache: second call returns same fetched_at
expected: |
  uv run python -c "from lockin.data.yfinance_source import YFinanceSource; from lockin.data.cache import TTLCache; cache = TTLCache(); src = YFinanceSource(cache=cache); r1 = src.get_fundamentals('MSFT'); r2 = src.get_fundamentals('MSFT'); print('fetched_at same:', r1['fetched_at'] == r2['fetched_at']); print('data_freshness:', r2.get('data_freshness'))"
  Should print: fetched_at same: True, data_freshness: FRESH
result: pass

### 7. DataUnavailableError on invalid ticker
expected: |
  heredoc: uv run python << 'EOF' ... DataUnavailableError raised, ticker: INVALIDTICKER_XYZ_999 EOF
  Should print: DataUnavailableError raised, ticker: INVALIDTICKER_XYZ_999
result: pass
      print('DataUnavailableError raised for ticker:', e.ticker)"
  Should print: DataUnavailableError raised for ticker: INVALIDTICKER_XYZ_999
  (Note: yfinance returns empty DataFrames for bad tickers — may be slow due to retry logic)
result: [pending]

### 8. Public API get_fundamentals with validation metadata
expected: |
  uv run python -c "from lockin.data import get_fundamentals; r = get_fundamentals('AAPL'); print('quality_score:', r.get('quality_score')); print('missing_fields:', r.get('missing_fields')); print('ticker:', r.get('ticker'))"
  Should print: quality_score: 1.0, missing_fields: [], ticker: AAPL
result: issue
reported: "quality_score is None instead of 1.0 — DB storage errors (tables not created yet, non-fatal as designed) but quality_score should be 1.0 from validation merge"
severity: major

### 9. Public API get_macro_indicators
expected: |
  uv run python -c "from lockin.data import get_macro_indicators; m = get_macro_indicators(); print('gdp:', m.get('gdp')); print('data_freshness:', m.get('data_freshness')); print('manufacturing_pmi:', m.get('manufacturing_pmi'))"
  Should print GDP value, data_freshness=FRESH, manufacturing_pmi=None
result: pass

## Summary

total: 9
passed: 7
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "NAPM/manufacturing_pmi series is known-unavailable on public FRED — should be removed from FRED_SERIES dict or clearly annotated as deprecated/dead so it doesn't silently return None"
  status: failed
  reason: "User reported: if NAPM is not supported anymore it should be deleted or at least note that is not supported"
  severity: minor
  test: 4
  artifacts: []
  missing: []

- truth: "get_fundamentals() public API should return quality_score: 1.0 for AAPL (all required fields present)"
  status: failed
  reason: "User reported: quality_score is None instead of 1.0 — validation metadata not merged into result from public API"
  severity: major
  test: 8
  artifacts: []
  missing: []
