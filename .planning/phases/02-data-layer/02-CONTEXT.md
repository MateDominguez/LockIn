# Phase 2: Data Layer - Context

**Gathered:** 2026-02-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a financial data pipeline that agents can call at analysis time. Covers:
- yfinance wrapper: `get_fundamentals(ticker, as_of_date)`
- FRED wrapper: `get_macro_indicators(as_of_date)`
- Point-in-time enforcement (no look-ahead bias for backtesting)
- Data validation (outlier detection, missing field flags)
- PostgreSQL storage for fundamentals and macro snapshots

**Out of scope for this phase:** actual agent logic, backtesting engine, real-time streaming, multi-source fallback (e.g., Alpha Vantage). Those belong in later phases.

</domain>

<decisions>
## Implementation Decisions

### Abstraction principle
- Design wrappers behind a clear interface (abstract class or protocol) so the data source (yfinance, Alpha Vantage, etc.) can be swapped without touching agent code
- Phase 2 implements yfinance + FRED concretely, but the wrapper API is the contract agents depend on
- Keep it simple — this is a 2-week phase; avoid over-engineering the DB schema

### Data freshness & caching
- **TTL-based caching:**
  - Prices: fetched live each time, no caching (yfinance price data is fast enough)
  - Fundamentals: 24-hour TTL
  - Macro (FRED): 7-day TTL (macro indicators change slowly)
- **On TTL expiry + re-fetch failure:** use stale cached data with a `data_freshness=STALE` warning flag — never block analysis due to source unavailability
- **Cold start + source down (no cache at all):** raise `DataUnavailableError`, skip that ticker, log the failure — analysis continues for other tickers
- **Cache invalidation:** TTL only. Add internal `force_refresh=True` flag on wrappers for debugging purposes — not exposed to users

### Error handling & fallbacks
- **Partial data (some fields None):** accept and return partial data; include `missing_fields: list[str]` in the response so agents know what's absent
- **Outlier detection thresholds:**
  - 50–200% period-over-period change: log warning, set `outlier_flag=True` on the field
  - >200% change: escalate to HITL for human review before passing to agents
- **FRED errors:** same stale-with-warning fallback policy as yfinance, but 7-day TTL before considering data stale
- **Validation error logging:** Claude's discretion — significant validation events (HITL triggers, DataUnavailableError) go to `audit_logs`; field-level warnings stay as metadata on returned data objects

### Point-in-time enforcement
- **Default behavior:** return latest data available strictly BEFORE `as_of_date`
- **Filing delay window (lookahead tolerance):**
  - Prices: 0 days (exact date required — price data exists for every trading day)
  - Fundamentals: 7-day lookahead (10-K/10-Q filings have publication delays)
  - Macro (FRED): 14-day lookahead (FRED revisions and releases lag the reporting period)
- **Live analysis (`as_of_date = today`):** bypass point-in-time logic entirely — fetch latest data without date enforcement
- **Future date guard:** `PointInTimeData` raises `ValueError` immediately if `as_of_date > today` — hard fail to prevent programming mistakes

### Storage policy
- **Prices:** fetch live, no DB storage — agents get what they need without accumulating a price history table in Phase 2
- **Fundamentals:** lazy storage — persist to `fundamentals` table only for tickers that have been analyzed (store exactly what was fetched, not field-filtered)
- **Macro data:** store to `macro_data` table in PostgreSQL — FRED has rate limits and macro data is slow-moving; current snapshot per indicator (not a full historical time series in Phase 2); TTL enforced at query time
- **Data lineage:** metadata columns on each table — `source` (e.g., `'yfinance'`), `fetched_at` (datetime), `as_of_date` (date used for point-in-time lookup). No separate lineage table — keeps schema simple and each row self-documenting

### Claude's Discretion
- Exact lookahead window values per data type (defined above as best-practice defaults)
- Whether validation warnings go to `audit_logs` or stay as metadata on returned data
- Macro storage decision (DB vs in-memory) — chose DB to avoid FRED rate limit pressure and provide session-independent caching
- Data lineage implementation (metadata columns vs separate table) — chose columns for simplicity

</decisions>

<specifics>
## Specific Ideas

- "Keep it simple — this is a 2-week phase, don't over-engineer"
- The data source could change from yfinance to a more reliable provider in the future → wrapper design must make this swap easy without touching agent code
- Wrappers should have clean, consistent return types (TypedDict or dataclass) so agents don't need to handle source-specific quirks

</specifics>

<deferred>
## Deferred Ideas

- Multi-source fallback (Alpha Vantage, FMP, Polygon.io) when yfinance fails — noted for v2 or a future phase
- Full historical macro time series (not just current snapshots) — deferred to Phase 5 if backtesting requires it
- Active data quality dashboard / monitoring UI — deferred to Phase 6
- Real-time streaming prices — out of scope for v1 entirely

</deferred>

---

*Phase: 02-data-layer*
*Context gathered: 2026-02-22*
