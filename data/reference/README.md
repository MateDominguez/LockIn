# data/reference/

Static reference data used by the backtest. These files are committed to the
repository — they are not market data, change infrequently, and do not contain
any secrets.

---

## sp500_historical_components.csv

**Required by:** `src/lockin/data/sp500_universe.py`  
**Used for:** Point-in-time S&P 500 composition lookup during backtesting.
Prevents survivorship bias by ensuring each quarterly window only screens
companies that were actually in the index on that date.

**Source:** [github.com/fja05680/sp500](https://github.com/fja05680/sp500)  
Maintained from Wikipedia's historical S&P 500 composition pages. Coverage
starts in 1996 and is updated periodically.

**Format:** CSV with two columns:

| Column    | Format                              | Example                        |
|-----------|-------------------------------------|--------------------------------|
| `date`    | `YYYY-MM-DD` (change effective date)| `2008-09-22`                   |
| `tickers` | Comma-separated ticker symbols      | `MMM,AOS,ABT,ABBV,...`         |

Each row represents the full index composition as of a change date. The lookup
in `sp500_universe.py` returns the most recent row with `date <= as_of`, so
any intermediate date is automatically covered.

### Download (run once before the backtest)

```bash
mkdir -p data/reference
curl -L "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes.csv" \
     -o data/reference/sp500_historical_components.csv
```

Or with PowerShell:

```powershell
New-Item -ItemType Directory -Force data\reference
Invoke-WebRequest `
    -Uri "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes.csv" `
    -OutFile "data\reference\sp500_historical_components.csv"
```

### Verify the download

```python
from datetime import date
from lockin.data.sp500_universe import get_sp500_tickers_at_date

print(len(get_sp500_tickers_at_date(date(2014, 1, 1))))   # expect ~503
print("LEH" in get_sp500_tickers_at_date(date(2008, 1, 1)))  # True  (pre-bankruptcy)
print("LEH" in get_sp500_tickers_at_date(date(2009, 1, 1)))  # False (post-bankruptcy)
```

### Updating the file

If you need a more recent snapshot (e.g. current 2025 composition), re-run the
`curl` command above. The file is safe to overwrite — `sp500_universe.py` clears
its `lru_cache` on the next process start, so no restart is needed between a
download and a backtest run.
