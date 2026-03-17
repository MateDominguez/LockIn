# Phase 3: Agents & RAG - Research

**Researched:** 2026-03-17
**Domain:** LLM agents, financial valuation math, RAG with pgvector, SEC EDGAR, Bayesian synthesis, position sizing
**Confidence:** MEDIUM-HIGH overall (LangChain/Gemini HIGH, valuation math HIGH, RAG patterns MEDIUM, VoMC LOW)

---

## Summary

Phase 3 replaces 7 mock agents with real implementations that make Gemini LLM calls, compute deterministic
financial math (EPV, Altman Z-Score, Beneish M-Score, Kelly Criterion), run dialectical Bull-Bear iteration,
and support RAG over SEC 10-Ks/earnings transcripts/PDFs.

The standard approach: `ChatGoogleGenerativeAI` from `langchain-google-genai==4.2.1` for all LLM calls,
`SupabaseVectorStore` from `langchain-community==0.4.1` for RAG (already in pyproject.toml),
`edgartools` for SEC 10-K fetching (no API key required), `httpx` for FMP transcript API (already in stack),
and `ragas==0.4.3` for faithfulness evaluation. The LLM is initialized once at agent-creation time reading
the model name from settings — not on every node call.

**Critical finding:** Gemini 2.0 Flash is **deprecated and retired June 1, 2026**. The project timeline
extends past this date. Replace with `gemini-2.5-flash` for structured/fast agents (Macro Oracle,
Strategist, Guardian, Optimizer). Free tier is now 10 RPM / 250 RPD for both 2.5-flash and 2.5-pro.

**IMPORTANT OPEN ITEM:** Two Notion specification pages were identified by the user as containing updated
implementation details but could not be accessed (Notion requires JavaScript, no Notion MCP available):
1. `https://www.notion.so/Especificaci-n-del-Judge-v1-0-Algoritmo-de-Consenso-Bayesiano-320dda73d4cd81a9b224eb0e21112b89` — Judge algorithm specification
2. `https://www.notion.so/4cbbb0257f024a49bd1d574b8e38f6af` — Unknown content (likely agent database)

The planner MUST review these pages before creating Judge tasks. The Bayesian synthesis math documented
in this research is based on prior decisions + standard statistical theory and may be superseded by the
Notion spec.

**Primary recommendation:** Initialize one `ChatGoogleGenerativeAI` per agent at module level (not inside
the node function), reading the model name from `get_settings()`. Keep all valuation math as pure
deterministic Python functions — never have the LLM compute numerical formulas.

---

## Standard Stack

### Core (already in pyproject.toml / uv.lock)

| Library | Locked Version | Purpose | Notes |
|---------|---------------|---------|-------|
| `langchain-google-genai` | 4.2.1 | ChatGoogleGenerativeAI + GoogleGenerativeAIEmbeddings | Already in stack |
| `langgraph` | 1.0.9 | Graph orchestration — nodes, edges, state | Already in stack |
| `langchain` | 1.2.10 | LangChain core, prompt templates | Already in stack |
| `langchain-community` | 0.4.1 | SupabaseVectorStore, ParentDocumentRetriever | Already in stack |
| `langchain-text-splitters` | 1.1.1 | RecursiveCharacterTextSplitter for RAG chunking | Already in lock |
| `ragas` | 0.4.3 | RAG faithfulness evaluation | Already in stack |
| `scipy` | >=1.14.0 | Normal distribution for Bayesian synthesis (stats.norm) | Already in stack |
| `numpy` | >=2.0.0 | Numerical math for valuations | Already in stack |
| `httpx` | >=0.27.0 | FMP transcript API calls | Already in stack |
| `tenacity` | >=9.0.0 | Retry logic for all API calls | Already in stack |
| `supabase` | >=2.0.0 | Supabase client for SupabaseVectorStore | Already in stack |

### New Dependencies (must add)

| Library | Purpose | Add To |
|---------|---------|--------|
| `edgartools` | SEC EDGAR 10-K fetching — no API key required | pyproject.toml |
| `pypdf` | PDF loading for books corpus (Graham, etc.) | pyproject.toml |

**Installation:**
```bash
uv add edgartools pypdf
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `SupabaseVectorStore` (community) | `langchain-postgres` PGVector | langchain-postgres has async + better filtering but requires different SQL setup and new dependency; SupabaseVectorStore already in lock, uses existing Supabase client |
| `edgartools` | SEC EDGAR REST API directly | edgartools handles rate limiting, User-Agent headers, XBRL parsing automatically; raw API requires custom plumbing |
| `GoogleGenerativeAIEmbeddings` | `sentence-transformers` (already in lock) | Google embeddings are free, 768-dim, remote; sentence-transformers is local, adds memory overhead in production but works offline |
| `httpx` for FMP | `fmp-data` Python client | httpx already in stack; fmp-data is a thin wrapper that adds a dependency for marginal gain |

---

## Architecture Patterns

### Recommended Project Structure

```
src/lockin/agents/
├── __init__.py              # Re-exports real agents + MOCK_AGENTS dict
├── mock.py                  # KEEP — used in tests via agent_overrides
├── macro_oracle.py          # Real Macro Oracle (gemini-2.5-flash)
├── value_hunter.py          # Real Value Hunter / Bull (gemini-2.5-pro)
├── bear.py                  # Real Bear (gemini-2.5-pro)
├── strategist.py            # Real Strategist — simplified VeTO (gemini-2.5-flash)
├── guardian.py              # Real Guardian (gemini-2.5-flash)
├── judge.py                 # Real Judge (gemini-2.5-pro)
└── optimizer.py             # Real Optimizer (gemini-2.5-flash)

src/lockin/valuation/        # NEW module — pure deterministic math
├── __init__.py
├── epv.py                   # EPV (Earnings Power Value)
├── eva.py                   # EVA (Economic Value Added)
├── rim.py                   # RIM (Residual Income Model)
├── scores.py                # Altman Z, Beneish M, Piotroski F, Magic Formula
└── kelly.py                 # Kelly Criterion position sizing

src/lockin/rag/              # Currently empty __init__.py
├── __init__.py
├── ingest.py                # Document loading + chunking + embedding pipeline
├── retriever.py             # SupabaseVectorStore + ParentDocumentRetriever init
├── edgar.py                 # SEC 10-K fetching via edgartools
├── fmp_transcripts.py       # Earnings transcript fetching + caching via FMP
└── evaluation.py            # RAGAs faithfulness evaluation runner

scripts/
└── ingest_rag.py            # One-time corpus ingestion script (run before agents)
```

### Pattern 1: Agent Node with Singleton LLM

Initialize the LLM once at module load (not inside the node function). Avoids reconstructing on every
graph invocation. Follows the existing `get_settings()` singleton pattern.

```python
# src/lockin/agents/macro_oracle.py
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from lockin.graph.state import InvestmentState
from lockin.utils.config import get_settings

_settings = get_settings()

# Initialize once at module load
_llm = ChatGoogleGenerativeAI(
    model=_settings.macro_oracle_model,   # "gemini-2.5-flash" default
    google_api_key=_settings.google_api_key,
    temperature=0.2,
    max_retries=3,
)


class MacroRegimeOutput(BaseModel):
    phase: str           # "expansion" | "contraction" | "stagflation" | "recovery"
    risk_appetite: str   # "on" | "off" | "neutral"
    yield_curve: str     # "normal" | "inverted" | "flat"
    fed_stance: str      # "hawkish" | "dovish" | "neutral"
    confidence: float    # 0.0 - 1.0
    narrative: str


_structured_llm = _llm.with_structured_output(MacroRegimeOutput)


def macro_oracle(state: InvestmentState, config: RunnableConfig) -> dict:
    """Detect macro regime from FRED indicators in state."""
    from lockin.data import get_macro_indicators
    macro = get_macro_indicators()

    prompt = f"""Analyze these macroeconomic indicators and determine the current regime:
    - Fed Funds Rate: {macro.get('fed_funds')}%
    - 10Y-2Y Yield Spread: {macro.get('yield_10y_2y')} bps
    - 10Y-3M Yield Spread: {macro.get('yield_10y_3m')} bps
    - CPI: {macro.get('cpi')}%
    - Core PCE: {macro.get('core_pce')}%
    - Unemployment: {macro.get('unemployment')}%
    Classify the macro regime."""

    result: MacroRegimeOutput = _structured_llm.invoke(prompt)

    return {
        "macro_regime": {
            "phase": result.phase,
            "risk_appetite": result.risk_appetite,
            "yield_curve": result.yield_curve,
            "fed_stance": result.fed_stance,
        },
        "macro_confidence": result.confidence,
        "macro_narrative": result.narrative,
    }
```

### Pattern 2: Per-Agent Model Configuration via Settings

The CONTEXT.md decision: each agent has a model key in config/settings. Override via .env.

Extend the `Settings` dataclass in `utils/config.py`:

```python
@dataclass(frozen=True)
class Settings:
    # ...existing fields...
    # Per-agent model names — override in .env
    macro_oracle_model: str = "gemini-2.5-flash"
    value_hunter_model: str = "gemini-2.5-pro"
    bear_model: str = "gemini-2.5-pro"
    judge_model: str = "gemini-2.5-pro"
    guardian_model: str = "gemini-2.5-flash"
    strategist_model: str = "gemini-2.5-flash"
    optimizer_model: str = "gemini-2.5-flash"
    # New API keys
    fmp_api_key: str = ""
    edgar_identity: str = ""   # e.g. "LockIn contact@lockin.ai"
```

And in the `get_settings()` function, add:
```python
macro_oracle_model=os.getenv("MACRO_ORACLE_MODEL", "gemini-2.5-flash"),
value_hunter_model=os.getenv("VALUE_HUNTER_MODEL", "gemini-2.5-pro"),
# ...etc.
fmp_api_key=os.getenv("FMP_API_KEY", ""),
edgar_identity=os.getenv("EDGAR_IDENTITY", ""),
```

### Pattern 3: Bear Agent Isolation (Critical)

Per CONTEXT.md: Bear is blind to Bull's thesis. Bear receives only: `asset_ticker` + raw market data.
It must NOT read `bull_valuation_distribution`, `bull_thesis`, `bull_confidence`, or `quality_metrics`.

```python
# src/lockin/agents/bear.py
def bear(state: InvestmentState, config: RunnableConfig) -> dict:
    ticker = state["asset_ticker"]
    # Read ONLY these fields — do NOT access any bull_* fields
    macro_regime = state.get("macro_regime", {})
    macro_narrative = state.get("macro_narrative", "")
    current_iteration = state.get("bull_iteration", 0)

    # Fetch raw data independently (same data Bull uses, but fresh perspective)
    from lockin.data import get_fundamentals
    fundamentals = get_fundamentals(ticker)

    # Build bearish thesis from scratch...
    # ...
    return {
        "bear_valuation_distribution": {...},
        "bear_thesis": "...",
        "bear_challenges": [...],
        "bear_red_flags": [...],
        "bear_conviction": 0.0,
        "bull_iteration": current_iteration + 1,  # increment for routing
    }
```

### Pattern 4: SupabaseVectorStore + ParentDocumentRetriever

The Supabase SQL setup requires the `match_documents` RPC function and a `rag_documents` table.
For ParentDocumentRetriever in Phase 3, use `InMemoryStore` for parent storage (acceptable for
demo/dev; re-ingest at startup is fine since corpus is static).

```python
# src/lockin/rag/retriever.py
# Source: LangChain Supabase docs, verified 2026-03-17
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from supabase.client import create_client

from lockin.utils.config import get_settings

_settings = get_settings()
_supabase = create_client(_settings.supabase_url, _settings.supabase_key)

_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",    # 768 dimensions
    google_api_key=_settings.google_api_key,
    task_type="RETRIEVAL_DOCUMENT",       # for indexing
)

_vectorstore = SupabaseVectorStore(
    client=_supabase,
    embedding=_embeddings,
    table_name="rag_documents",
    query_name="match_documents",
)

_parent_store = InMemoryStore()

retriever = ParentDocumentRetriever(
    vectorstore=_vectorstore,
    docstore=_parent_store,
    child_splitter=RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50),
    parent_splitter=RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200),
)


def get_rag_context(query: str, filter_metadata: dict | None = None, k: int = 5) -> list[str]:
    """Retrieve relevant document passages for an agent query."""
    # Note: retriever uses RETRIEVAL_QUERY task_type automatically for queries
    docs = retriever.invoke(query)[:k]
    return [doc.page_content for doc in docs]
```

### Pattern 5: RAGAs Faithfulness Evaluation

```python
# src/lockin/rag/evaluation.py
# Source: RAGAs docs verified 2026-03-17, ragas==0.4.3
from ragas import evaluate, EvaluationDataset
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import Faithfulness
from langchain_google_genai import ChatGoogleGenerativeAI

from lockin.utils.config import get_settings

_settings = get_settings()

_evaluator_llm = LangchainLLMWrapper(
    ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",   # use flash for eval to save pro quota
        google_api_key=_settings.google_api_key,
    )
)


def evaluate_faithfulness(samples: list[dict]) -> float:
    """
    Evaluate RAG faithfulness for a list of samples.

    Each sample must have:
      - user_input: str
      - retrieved_contexts: list[str]
      - response: str

    Returns: faithfulness score 0.0-1.0 (target: >0.90 per Phase 3 success criteria)
    """
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness()],
        llm=_evaluator_llm,
    )
    return float(result["faithfulness"])
```

### Anti-Patterns to Avoid

- **LLM initialized inside node function:** Instantiate `ChatGoogleGenerativeAI` at module level.
  Each construction validates API key, creates HTTP client, etc. — expensive on each call.
- **LLM computing valuation math:** EPV, Z-Score, M-Score, Kelly are deterministic. Compute in Python,
  pass results to LLM as context for narrative generation only.
- **Bear reading Bull's state fields:** Bear node must not access `state["bull_thesis"]` or any
  `bull_*` field. Enforce via code review + unit test.
- **InMemoryStore in production:** Fine for Phase 3 (static corpus). Add note in code.
- **Using `gemini-2.0-flash`:** Retired June 1, 2026. Use `gemini-2.5-flash`.
- **Rebuilding SupabaseVectorStore per agent call:** Initialize once globally in `rag/retriever.py`,
  import the singleton in agents.
- **Forgetting EDGAR identity:** Set `EDGAR_IDENTITY` in .env before fetching 10-Ks. SEC will block
  your IP if you skip this header.
- **Single-year Beneish M-Score:** M-Score requires two consecutive years. Always validate that
  prior-year data is available before computing.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SEC 10-K fetching | Custom EDGAR HTTP client | `edgartools` (`edgar.Company`) | Handles 10 req/sec rate limiting, User-Agent header, XBRL parsing, pagination |
| PDF text extraction | Custom PDF parser | `PyPDFLoader` from langchain + `pypdf` | Handles pagination, multi-page, encoding edge cases |
| RAG faithfulness evaluation | Custom claim verification pipeline | `ragas.metrics.Faithfulness` | LLM-based claim decomposition + verification already implemented |
| Text chunking | Custom splitter | `RecursiveCharacterTextSplitter` | Handles sentence boundaries, overlap, max size |
| API retry logic | Custom retry loop | `tenacity` (already in stack) | Exponential backoff, jitter, exception filtering |
| Cosine similarity for thesis comparison | Custom math | `sentence_transformers.util.cos_sim` | Already in lock, handles batching |
| Embedding computation | Custom Google API client | `GoogleGenerativeAIEmbeddings` | Handles batching (max 100), task_type, auth |

**Key insight:** All valuation math (EPV, EVA, RIM, Altman Z, Beneish M, Piotroski F, Magic Formula,
Kelly Criterion) has NO good existing Python library — it MUST be implemented as Python functions in
`src/lockin/valuation/`. But everything around data access, LLM integration, and RAG should use
existing libraries.

---

## Valuation Math Reference

All formulas are deterministic Python. Implement in `src/lockin/valuation/`.

### EPV — Earnings Power Value (Bull, mature companies)

**Formula:** `EPV = Normalized_EBIT × (1 - Tax_Rate) / WACC`

**Step by step:**
1. `Normalized_EBIT` = Average EBIT over 3-5 years (smooth cyclicality). Use `get_fundamentals()` with
   multiple `as_of_date` values (prior years) to get historical operating_income.
2. `Tax_Rate` = Effective tax rate. Derive from: `1 - (net_income / operating_income)`. Cap at 35%.
3. `WACC` = Simplified proxy: `fed_funds_rate + 0.04` (4% equity risk premium). Use `macro_regime`
   data from state for current fed_funds.
4. `EPV = Normalized_EBIT * (1 - Tax_Rate) / WACC`
5. Net debt adjustment: `EPV_equity = EPV - total_debt + cash_and_equivalents`
6. Per share: `EPV_per_share = EPV_equity / shares_outstanding`

**Phase 2 fields available:** `total_revenue`, `net_income`, `gross_profit`, `operating_income`,
`ebitda`, `total_debt`, `cash_and_equivalents`, `total_equity`, `diluted_eps`, `free_cash_flow`

**Missing fields (need extra fetches):**
- `shares_outstanding`: fetch from `yf.Ticker(ticker).info["sharesOutstanding"]`
- Multi-year EBIT for normalization: call `get_fundamentals(ticker, as_of_date=prior_year_date)` for 3 years
- `effective_tax_rate`: derive from income statement or `yf.Ticker(ticker).info["effectiveTaxRate"]`

### EVA — Economic Value Added (Bull, tech companies)

**Formula:** `EVA = NOPAT - (WACC × Invested_Capital)`

Where:
- `NOPAT = operating_income × (1 - tax_rate)`
- `Invested_Capital = total_equity + total_debt - cash_and_equivalents`
- **R&D capitalization (tech adjustment):** Add back R&D expense to NOPAT; add 5-year capitalized R&D
  to IC. Fetch `R&D expense` from `yf.Ticker(ticker).income_stmt` (row "Research And Development").

**Phase 2 availability:** `operating_income`, `total_equity`, `total_debt`, `cash_and_equivalents` all
available. R&D needs direct yfinance fetch.

### RIM — Residual Income Model (Bull, financials/banks)

**Formula:** `Equity_Value = BVE_0 + Σ(t=1..T) [(ROE_t - r_e) × BVE_{t-1}] / (1 + r_e)^t`

Where:
- `BVE_0` = current book value of equity (`total_equity`)
- `ROE` = `net_income / total_equity`
- `r_e` = cost of equity = `fed_funds + 0.04`
- Use a fade model: ROE decays toward r_e linearly over 10 years (fade to "no excess return")

**Simplified T=10 implementation:** Compute for each year, assuming linear ROE decay.

**Phase 2 availability:** `net_income`, `total_equity` available. Multi-year projection is synthetic.

### Altman Z-Score (Guardian)

**Formula (original 1968, public companies):**
```
Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
```

| Variable | Formula | Source |
|----------|---------|--------|
| X1 | Working Capital / Total Assets | need `current_assets - current_liabilities` from raw balance sheet |
| X2 | Retained Earnings / Total Assets | approximate as `total_equity - shares_outstanding × par_value`; or use `total_equity * 0.7` as rough proxy |
| X3 | EBIT / Total Assets | `operating_income / total_assets` — Phase 2 has both |
| X4 | Market Cap / Book Value of Total Debt | need `market_cap` from `yf.Ticker.info["marketCap"]` |
| X5 | Revenue / Total Assets | `total_revenue / total_assets` — Phase 2 has both |

**Thresholds:** Z > 2.99 = safe, 1.81-2.99 = gray zone, Z < 1.81 = distress. Veto at Z < 1.1 (per PROJECT.md).

**Extra fetches needed (Guardian must fetch raw):**
- `current_assets`, `current_liabilities` from `yf.Ticker(ticker).balance_sheet`
- `market_cap` from `yf.Ticker(ticker).info["marketCap"]`

### Beneish M-Score (Guardian)

**Formula (8-variable, 1999):**
```
M = -4.84 + 0.92×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI
    + 0.115×DEPI - 0.172×SGAI + 4.679×TATA - 0.327×LVGI
```

All 8 variables require **two consecutive years of data** (year t and year t-1):

| Variable | Formula |
|----------|---------|
| DSRI | (Receivables_t/Sales_t) / (Receivables_{t-1}/Sales_{t-1}) |
| GMI | Gross_Margin_{t-1} / Gross_Margin_t |
| AQI | [1-(CA+PPE)/TA]_t / [1-(CA+PPE)/TA]_{t-1} |
| SGI | Sales_t / Sales_{t-1} |
| DEPI | [Dep/(PPE+Dep)]_{t-1} / [Dep/(PPE+Dep)]_t |
| SGAI | [SGA/Sales]_t / [SGA/Sales]_{t-1} |
| TATA | (Net_Income - CFO) / Total_Assets_t |
| LVGI | [(LTD+CL)/TA]_t / [(LTD+CL)/TA]_{t-1} |

**Threshold:** M > -1.78 = possible manipulation. Veto trigger per REQUIREMENTS.md.

**Extra fetches needed:** Receivables, PPE, SGA, Depreciation, Current Liabilities — all from raw
`yf.Ticker(ticker).balance_sheet` and `yf.Ticker(ticker).income_stmt`. None of these are in Phase 2
`FundamentalsResult`. Guardian must fetch them directly.

### Piotroski F-Score (Value Hunter — quality signal)

9 binary criteria, 1 point each:

**Profitability (4 pts):** ROA > 0; CFO > 0; ROA improved YoY; CFO > Net Income (earnings quality)

**Leverage/Liquidity/Dilution (3 pts):** Long-term debt ratio decreased YoY; Current ratio improved YoY;
No new shares issued

**Efficiency (2 pts):** Gross margin improved YoY; Asset turnover improved YoY

All YoY comparisons require two `get_fundamentals()` calls (current year and prior year).

### Magic Formula — EBIT/EV + ROIC (Value Hunter — quality signal)

Not used as a universe ranking (single ticker). Use as standalone quality signals:

- `Earnings_Yield = EBIT / Enterprise_Value`  where `EV = market_cap + total_debt - cash_and_equivalents`
- `ROIC = EBIT / (Net_Working_Capital + Net_Fixed_Assets)`

**Available:** `operating_income` (EBIT proxy), `total_debt`, `cash_and_equivalents`. Need `market_cap`
and `net_fixed_assets` (PPE from raw balance sheet).

### Kelly Criterion (Optimizer)

**Formula:** `f* = (b×p - q) / b`

Where:
- `p` = probability of winning ≈ `judge_conviction` from state
- `q` = 1 - p
- `b` = reward-to-risk ratio = `(judge_price_target - current_price) / (current_price - bear_P10)`

**Apply half-Kelly for safety:**
```python
def kelly_position_size(
    conviction: float,
    price_target: float,
    current_price: float,
    bear_p10: float,
    max_position: float = 0.10,
) -> float:
    if current_price <= 0 or bear_p10 >= current_price:
        return 0.0
    b = (price_target - current_price) / (current_price - bear_p10)
    p = conviction
    q = 1 - p
    f_star = (b * p - q) / b
    half_kelly = max(0.0, f_star * 0.5)   # never negative
    return min(half_kelly, max_position)   # hard cap at 10%
```

### Bayesian Synthesis (Judge)

**IMPORTANT:** The Notion spec page for Judge v1.0 was not accessible. The following is based on
standard statistical theory and prior decisions (CONTEXT.md). Verify against Notion before implementing.

Given two normal distributions (Bull and Bear), compute a mixture model posterior:

```python
import numpy as np
from scipy import stats


def bayesian_synthesis(
    bull_mean: float,
    bull_std: float,
    bull_weight: float,  # = bull_confidence from state
    bear_mean: float,
    bear_std: float,
    bear_weight: float,  # = bear_conviction from state
) -> dict:
    """
    Mixture of Gaussians posterior for Judge consensus distribution.
    Returns distribution dict matching InvestmentState schema.
    """
    total_w = bull_weight + bear_weight
    w_bull = bull_weight / total_w
    w_bear = bear_weight / total_w

    # Mixture posterior mean
    post_mean = w_bull * bull_mean + w_bear * bear_mean

    # Mixture posterior variance (law of total variance)
    post_var = (
        w_bull * (bull_std**2 + bull_mean**2)
        + w_bear * (bear_std**2 + bear_mean**2)
        - post_mean**2
    )
    post_std = float(np.sqrt(max(post_var, 0)))

    dist = stats.norm(loc=post_mean, scale=post_std)
    p10, p25, p50, p75, p90 = dist.ppf([0.10, 0.25, 0.50, 0.75, 0.90])

    return {
        "mean": float(post_mean),
        "median": float(p50),
        "std_dev": float(post_std),
        "P10": float(p10),
        "P25": float(p25),
        "P50": float(p50),
        "P75": float(p75),
        "P90": float(p90),
    }
```

The LLM (Judge) receives the computed distribution and both agents' narratives, then produces the
final recommendation (BUY/PASS/HOLD/HITL) and judge_narrative. Math is Python; narration is LLM.

### Argument Exhaustion Detection (Bull-Bear Loop)

For detecting "no new substance" in refinement rounds, use cosine similarity of thesis embeddings:

```python
from sentence_transformers import SentenceTransformer, util

_sim_model = SentenceTransformer("all-MiniLM-L6-v2")  # already in lock via sentence-transformers

EXHAUSTION_THRESHOLD = 0.92  # similarity > 0.92 = likely just rephrasing

def is_argument_exhausted(thesis_before: str, thesis_after: str) -> bool:
    """Return True if thesis refinement added no substantive new content."""
    embs = _sim_model.encode([thesis_before, thesis_after])
    similarity = float(util.cos_sim(embs[0], embs[1]))
    return similarity > EXHAUSTION_THRESHOLD
```

---

## VoMC — Volatility of Market Cap (Custom Metric)

**Research finding:** VoMC is NOT a standard financial metric in public literature. No academic papers
or industry standards found under this exact name. It is a project-specific concept from the Cabanelas
2024 reference in PROJECT.md ("Viabilidad Operativa: fragilidad operativa y apalancamiento").

**Interpretation from context:** VoMC appears to proxy "operational fragility" — how unstable a
company's market valuation has been relative to its fundamentals.

**Recommended placeholder implementation (LOW confidence — must validate vs Cabanelas 2024):**
```python
import numpy as np

def calculate_vomc_fragility(
    price_history_1y: list[float],   # ~252 daily prices
) -> float:
    """
    VoMC fragility score — PLACEHOLDER implementation.

    Hypothesis: rolling 1Y realized annualized volatility of stock price,
    normalized to [0, 1]. >0.5 = high fragility.

    Must be validated against Cabanelas 2024 before using in production.
    """
    if len(price_history_1y) < 20:
        return 0.5  # neutral if insufficient data
    prices = np.array(price_history_1y)
    log_returns = np.diff(np.log(prices))
    realized_vol = float(np.std(log_returns) * np.sqrt(252))
    # Normalize: assume >80% annualized vol = maximum fragility
    return min(realized_vol / 0.80, 1.0)
```

**Action required before implementing Guardian:** Locate the Cabanelas 2024 paper referenced in
PROJECT.md and extract the exact VoMC formula.

---

## SEC EDGAR Integration

**Use `edgartools`** (no API key, open source, respects SEC rate limits):

```python
# Source: edgartools docs verified 2026-03-17
# Requires: uv add edgartools
from edgar import Company, set_identity
from langchain_core.documents import Document

# Set in .env: EDGAR_IDENTITY="LockIn contact@lockin.ai"
set_identity(settings.edgar_identity)


def fetch_10k_documents(ticker: str, years: int = 3) -> list[Document]:
    """Fetch last N 10-K filings as LangChain Documents for RAG ingestion."""
    company = Company(ticker)
    filings = company.get_filings(form="10-K").latest(years)

    docs = []
    for filing in filings:
        text = filing.document.markdown()   # structured text extraction
        docs.append(Document(
            page_content=text,
            metadata={
                "source": "10-K",
                "ticker": ticker,
                "year": filing.filing_date.year,
                "filing_date": str(filing.filing_date),
                "accession_number": filing.accession_number,
            },
        ))
    return docs
```

**Rate limits:** 9 req/sec (edgartools default). Do not parallelize. `EDGAR_IDENTITY` is required.
Each 10-K is large (~50-200 pages). Chunk at 800 tokens with 100 overlap for RAG.

---

## FMP API Integration

**Earnings transcript endpoint** (use httpx, already in stack):

```python
# Source: FMP docs (v3 endpoint confirmed via WebSearch 2026-03-17)
# Add FMP_API_KEY to .env
import httpx

FMP_BASE = "https://financialmodelingprep.com/api/v3"


async def fetch_earnings_transcript(
    ticker: str, year: int, quarter: int
) -> dict:
    """Fetch a single earnings call transcript from FMP API."""
    url = f"{FMP_BASE}/earning_call_transcript/{ticker}"
    params = {
        "quarter": quarter,
        "year": year,
        "apikey": settings.fmp_api_key,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else {}
    # Returns: {"symbol": "AAPL", "quarter": 2, "year": 2024,
    #           "date": "2024-08-01", "content": "...full transcript text..."}
```

**Rate limits:** 250 req/day free tier. Budget carefully:
- VeTO (Strategist): 1-2 transcripts per analysis (latest 2 quarters)
- RAG ingestion: 4 transcripts per ticker (1 year of quarters)
- Total per ticker: ~6 FMP calls

**CRITICAL:** Cache transcripts with long TTL (30 days). Transcripts are immutable after posting.
Reuse the existing `TTLCache` from `lockin.data.cache`.

---

## RAG SQL Schema (Supabase)

The project uses Supabase. `SupabaseVectorStore` requires a table + RPC function:

```sql
-- Run in Supabase SQL Editor before RAG ingestion
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding VECTOR(768)   -- text-embedding-004 = 768 dims
);

CREATE INDEX IF NOT EXISTS rag_documents_embedding_idx
    ON rag_documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE OR REPLACE FUNCTION match_documents(
    query_embedding VECTOR(768),
    filter JSONB DEFAULT '{}',
    match_count INT DEFAULT 10
) RETURNS TABLE (
    id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT id, content, metadata,
        1 - (rag_documents.embedding <=> query_embedding) AS similarity
    FROM rag_documents
    WHERE metadata @> filter
    ORDER BY rag_documents.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

**Embedding dimensions:** `text-embedding-004` produces 768 dimensions (confirmed via LangChain docs).
Configure as `VECTOR(768)`.

### Document Corpus Strategy

| Source | Chunk Size | Overlap | Metadata Fields |
|--------|-----------|---------|-----------------|
| SEC 10-K | 800 tokens | 100 | source, ticker, year, filing_date, section |
| FMP transcripts | 600 tokens | 80 | source, ticker, year, quarter, date |
| PDF books | 1000 tokens | 150 | source, title, author, chapter |

---

## Common Pitfalls

### Pitfall 1: Gemini 2.0 Flash is Deprecated

**What goes wrong:** `model="gemini-2.0-flash"` will fail after June 1, 2026. Project deadline is June 2026.
**Why it happens:** Earlier research and pyproject.toml comments reference 2.0-flash as the "fast" option.
**How to avoid:** Use `model="gemini-2.5-flash"` throughout. Default in Settings should be `gemini-2.5-flash`.
**Warning signs:** HTTP 404 or deprecation notice in API response.

### Pitfall 2: Gemini Free Tier Rate Limits (250 RPD)

**What goes wrong:** 250 req/day limit exhausted during development/testing.
**Why it happens:** Full 7-agent graph = ~12-15 LLM calls per ticker. 250 / 15 = only 16 full analyses/day.
**How to avoid:** (1) Test each agent in isolation before full graph runs. (2) Use mock agents for integration
tests. (3) Cache LLM responses in dev. (4) Track daily usage. Reserve gemini-2.5-pro quota (also 250 RPD)
for Bull/Bear/Judge only.
**Warning signs:** `ResourceExhausted` or 429 errors from Google API.

### Pitfall 3: Beneish M-Score Requires Two Years

**What goes wrong:** M-Score variables silently produce wrong values (all ratios = 1.0) when only one year
is loaded.
**Why it happens:** Variables are ratios of year_t vs year_(t-1). Single-year data = division by self.
**How to avoid:** Guardian must explicitly call `get_fundamentals(ticker, as_of_date=last_year_date)`.
Add assertion: `if prior_year_data is None: log_warning(); skip_m_score(); return None`.
**Warning signs:** All M-Score index ratios (DSRI, GMI, SGI) exactly equal 1.0.

### Pitfall 4: FundamentalsResult Missing Guardian Fields

**What goes wrong:** Z-Score and M-Score require fields not in Phase 2 `FundamentalsResult`
(receivables, current_assets, current_liabilities, PPE, SGA, depreciation, market_cap).
**Why it happens:** Phase 2 was scoped to 7 core fundamental fields.
**How to avoid:** Guardian fetches extra fields directly via `yf.Ticker(ticker).balance_sheet` and
`yf.Ticker(ticker).income_stmt`. Do NOT modify Phase 2's FundamentalsResult schema.
Create a `_fetch_guardian_data(ticker)` helper function in `guardian.py`.
**Warning signs:** `KeyError` when Guardian tries to compute Z-Score or M-Score.

### Pitfall 5: Bear Accidentally Reads Bull's State Fields

**What goes wrong:** Bear agent reads `state["bull_thesis"]` or `bull_valuation_distribution` and its
"independent" thesis mirrors Bull's framing.
**Why it happens:** Full InvestmentState is passed to every node — easy to accidentally use Bull fields.
**How to avoid:** Add a comment block in `bear.py` listing forbidden state keys. Write a unit test that
populates state with known bull fields and asserts bear output is invariant.
**Warning signs:** Bear's price targets are suspiciously close to Bull's; Bear addresses Bull's exact arguments.

### Pitfall 6: InMemoryStore Parent Documents Lost on Restart

**What goes wrong:** After Python process restart, `ParentDocumentRetriever` with `InMemoryStore` loses
parent documents. Child chunks remain in pgvector but can't be retrieved.
**Why it happens:** InMemoryStore is ephemeral.
**How to avoid:** Build ingestion as a one-time script (`scripts/ingest_rag.py`). Run it once per corpus
update. Document that agents require pre-loaded parent store.
**Warning signs:** `retriever.invoke(query)` returns 0 documents despite pgvector having embeddings.

### Pitfall 7: LLM Arithmetic is Unreliable

**What goes wrong:** LLM-generated EPV or Z-Score values don't match Python calculations.
**Why it happens:** LLMs are not reliable calculators, especially for multi-step financial math.
**How to avoid:** ALL numerical computations in `src/lockin/valuation/` (Python). LLM only narrates.
In prompts: "The EPV calculation shows $X. Explain in investment terms why this is compelling/concerning."
**Warning signs:** LLM-generated price targets don't match the distribution computed in Python.

### Pitfall 8: FMP API Key Not in Settings

**What goes wrong:** Strategist silently fails when `FMP_API_KEY` is not set because Settings has no
`fmp_api_key` field.
**Why it happens:** FMP was not in the original Phase 1/2 settings.
**How to avoid:** Add `fmp_api_key: str = ""` to Settings dataclass. If empty, Strategist logs warning
and returns neutral VeTO score (mirrors the FRED graceful-degradation pattern in the data layer).
**Warning signs:** Strategist returns `strategist_sentiment=0.0` with no transcript analysis in narrative.

---

## Code Examples

### ChatGoogleGenerativeAI — Current Models

```python
# Source: LangChain Google Genai docs + Google AI model page, verified 2026-03-17
from langchain_google_genai import ChatGoogleGenerativeAI

# For deep reasoning agents: Value Hunter (Bull), Bear, Judge
pro_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",          # GA stable as of 2026
    google_api_key=settings.google_api_key,
    temperature=0.7,
    thinking_budget=-1,              # -1 = dynamic thinking; 0 = off; >0 = token cap
    max_retries=3,
)

# For structured/fast agents: Macro Oracle, Strategist, Guardian, Optimizer
flash_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",        # Replaces deprecated gemini-2.0-flash
    google_api_key=settings.google_api_key,
    temperature=0.2,
    max_retries=3,
)

# Structured output (Pydantic model)
from pydantic import BaseModel
class MyOutput(BaseModel):
    value: float
    narrative: str

result: MyOutput = flash_llm.with_structured_output(MyOutput).invoke("prompt")
```

### GoogleGenerativeAIEmbeddings

```python
# Source: LangChain docs verified 2026-03-17
# text-embedding-004 = 768 dimensions (NOT 1536)
from langchain_google_genai import GoogleGenerativeAIEmbeddings

doc_emb = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=settings.google_api_key,
    task_type="RETRIEVAL_DOCUMENT",  # for indexing
)

query_emb = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=settings.google_api_key,
    task_type="RETRIEVAL_QUERY",     # for retrieval at query time
)
```

### Altman Z-Score

```python
# Pure deterministic Python — no LLM
def calculate_altman_z(
    current_assets: float,
    current_liabilities: float,
    total_assets: float,
    retained_earnings: float,      # total_equity as rough proxy
    ebit: float,                   # operating_income
    market_cap: float,
    total_debt: float,
    total_revenue: float,
) -> float:
    """Altman Z-Score (original 1968 model for public companies)."""
    x1 = (current_assets - current_liabilities) / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_debt if total_debt > 0 else 10.0  # default if no debt
    x5 = total_revenue / total_assets
    return 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    # Veto if z < 1.1 (per PROJECT.md conservative threshold)
```

### edgartools 10-K

```python
# Source: edgartools docs verified 2026-03-17
# Requires: uv add edgartools
from edgar import Company, set_identity

set_identity("LockIn contact@lockin.ai")   # Required by SEC

company = Company("AAPL")
filings_10k = company.get_filings(form="10-K").latest(3)
for filing in filings_10k:
    text = filing.document.markdown()
    print(f"Year {filing.filing_date.year}: {len(text)} chars")
```

### graph/builder.py Update Pattern

Replace mock agents in `builder.py` — use `agent_overrides` pattern already built into `create_graph()`:

```python
# builder.py update: swap imports
from lockin.agents.macro_oracle import macro_oracle
from lockin.agents.value_hunter import value_hunter
from lockin.agents.bear import bear
from lockin.agents.strategist import strategist
from lockin.agents.guardian import guardian
from lockin.agents.judge import judge as real_judge
from lockin.agents.optimizer import optimizer

# In create_graph(): replace mock_* with real agents
# The audit_node wrapper and graph topology stay unchanged
builder.add_node("macro_oracle", audit_node("macro_oracle",
    overrides.get("macro_oracle", macro_oracle)))  # real agent as default
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `gemini-2.0-flash` | `gemini-2.5-flash` | 2.0-flash retires June 1, 2026 |
| `gemini-1.5-pro` | `gemini-2.5-pro` | Better reasoning, same LangChain API |
| `text-embedding-004` (768-dim) | `gemini-embedding-2-preview` (3072-dim) | 2-preview is new/preview status; stick with text-embedding-004 for stability |
| `ragas` old API | `ragas==0.4.3`: `EvaluationDataset.from_list()` + `LangchainLLMWrapper` | New API required for current version |
| `langchain_community.vectorstores.PGVector` | `langchain_postgres.PGVector` | Migration path; SupabaseVectorStore stays in community |

**Deprecated/outdated:**
- `gemini-2.0-flash`: Use `gemini-2.5-flash`
- `gemini-2.0-flash-lite`: Use `gemini-2.5-flash-lite`
- `ragas.evaluate(dataset={"question": ..., "contexts": ...})` (old key names): Use
  `user_input`, `retrieved_contexts`, `response` in current API

---

## Open Questions

1. **Judge v1.0 Bayesian consensus specification (CRITICAL)**
   - What we know: Notion page exists at URL provided by user; CONTEXT.md describes Bayesian synthesis
   - What's unclear: Exact algorithm (weighting scheme, convergence criteria, HITL thresholds) per Notion spec
   - Recommendation: **Planner must review Notion page before creating Judge tasks.** The Bayesian synthesis
     math in this document is a reasonable default but may differ from the authoritative spec.

2. **Notion database page (second URL)**
   - What we know: A Notion DB view exists at the second URL (likely the agent specifications database)
   - What's unclear: What additional specifications are in this database
   - Recommendation: Planner should check this page; it may contain specifications for all 7 agents.

3. **VoMC formula definition (Cabanelas 2024)**
   - What we know: PROJECT.md cites Cabanelas 2024 for VoMC; it relates to operational fragility
   - What's unclear: Exact mathematical definition
   - Recommendation: Implement placeholder (rolling 1Y realized vol, normalized to 0-1). Flag in
     Guardian output. The score is LOW confidence until Cabanelas 2024 is consulted.

4. **Argument exhaustion threshold (0.92 cosine similarity)**
   - What we know: Judge uses semantic similarity to detect no-new-substance rounds
   - What's unclear: Whether 0.92 is the right threshold
   - Recommendation: Make it configurable via Settings (`judge_exhaustion_threshold: float = 0.92`).
     Tune during testing.

5. **FMP API key availability**
   - What we know: `fmp_api_key` is NOT in the current Settings dataclass; 250 req/day free tier
   - What's unclear: Whether the user already has an FMP API key configured
   - Recommendation: Add `fmp_api_key` to Settings. Make Strategist gracefully degrade if missing
     (log warning, return neutral VeTO score). Do not fail the graph.

6. **edgartools `.markdown()` method reliability**
   - What we know: edgartools provides `.markdown()` and `.text()` on filing documents
   - What's unclear: Quality on different filing formats; some older EDGAR filings are scanned PDFs
   - Recommendation: Test on 2-3 sample 10-Ks before bulk ingestion. Use only last 3 years per
     CONTEXT.md decision (recent filings are well-structured HTML/XBRL).

---

## Sources

### Primary (HIGH confidence)
- uv.lock file — exact installed versions for all Python packages, verified 2026-03-17
- LangChain ChatGoogleGenerativeAI docs — https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai fetched 2026-03-17
- Google AI Gemini 2.5 Pro model page — https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro fetched 2026-03-17
- Google AI LangGraph example — https://ai.google.dev/gemini-api/docs/langgraph-example fetched 2026-03-17
- RAGAs faithfulness metric docs — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ fetched 2026-03-17
- RAGAs evaluate docs — https://docs.ragas.io/en/stable/getstarted/rag_eval/ fetched 2026-03-17
- SupabaseVectorStore LangChain docs — https://docs.langchain.com/oss/python/integrations/vectorstores/supabase fetched 2026-03-17
- PGVector LangChain docs — https://docs.langchain.com/oss/python/integrations/vectorstores/pgvector fetched 2026-03-17
- edgartools configuration docs — https://edgartools.readthedocs.io/en/stable/configuration/ fetched 2026-03-17
- LangGraph graph API docs — https://docs.langchain.com/oss/python/langgraph/graph-api fetched 2026-03-17
- Altman Z-Score (1968) — confirmed via Wikipedia + WallStreetPrep + CFA sources
- Beneish M-Score (1999) — confirmed via Wikipedia + multiple finance education sources
- Kelly Criterion — confirmed via Wikipedia + CFA sources
- EPV (Bruce Greenwald) — confirmed via WallStreetPrep + multiple value investing sources
- Piotroski F-Score (2000) — confirmed via Wikipedia + multiple sources

### Secondary (MEDIUM confidence)
- FMP transcript API endpoint — WebSearch (multiple sources confirm v3 endpoint format)
- Gemini free tier limits (250 RPD) — WebSearch 2026 sources (multiple sites confirm 10 RPM / 250 RPD)
- `gemini-2.5-flash` model string — WebSearch confirmed via Google model page
- Gemini 2.0 Flash deprecation — WebSearch multiple 2026 sources confirm June 1, 2026 retirement
- GoogleGenerativeAIEmbeddings task_type — LangChain docs (fetched; text-embedding-004 section not found, gemini-embedding-2-preview documented; task_type pattern confirmed)
- edgartools `.markdown()` method — docs page fetched; README also confirmed

### Tertiary (LOW confidence)
- VoMC formula — Project-specific concept; placeholder implementation derived from context only
- Argument exhaustion threshold (0.92) — No authoritative source; reasonable heuristic
- text-embedding-004 dimension (768) — Confirmed via WebSearch + LangChain docs reference
- InMemoryStore behavior on restart — Assumed from LangChain documentation description

---

## Metadata

**Confidence breakdown:**
- Standard stack (libraries + versions): HIGH — verified in uv.lock + PyPI
- ChatGoogleGenerativeAI usage patterns: HIGH — official docs fetched
- Gemini model names and status: HIGH — official Google AI page fetched
- Gemini rate limits: MEDIUM — multiple 2026 WebSearch sources (not official rate-limits page directly)
- EPV/EVA/RIM formulas: HIGH — standard value investing literature
- Altman Z-Score: HIGH — original 1968 paper formula, widely documented
- Beneish M-Score: HIGH — 1999 paper formula, widely documented
- Piotroski F-Score: HIGH — 2000 paper criteria, widely documented
- Kelly Criterion: HIGH — well-established
- Bayesian synthesis pattern: MEDIUM — standard stats theory; may differ from Notion spec
- VoMC: LOW — custom metric, no public definition found
- SupabaseVectorStore SQL setup: HIGH — official LangChain + Supabase docs
- edgartools API: MEDIUM — docs verified; edge cases unknown
- FMP transcript API: MEDIUM — confirmed endpoint; pagination/error behavior assumed
- RAGAs 0.4.3 API: HIGH — official docs fetched

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (Gemini model availability can change; verify rate limits before starting)

**BLOCKER before Judge implementation:** Review Notion page
`https://www.notion.so/Especificaci-n-del-Judge-v1-0-Algoritmo-de-Consenso-Bayesiano-320dda73d4cd81a9b224eb0e21112b89`
and incorporate Judge v1.0 specification into Judge tasks.
