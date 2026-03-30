"""
Guardian agent — Phase 3, Plan 06.

The Guardian is a Modifier agent (Family 2 per Notion Judge spec).  It does NOT
opine on price — it computes quantitative risk scores and outputs a ConfidenceModifier
that adjusts the margin of safety and variance the Judge applies.

Risk scores computed (all deterministic, no LLM):
  - Altman Z-Score (1968): bankruptcy risk; zones: safe / grey / distress
  - Beneish M-Score (1999): earnings manipulation probability
  - VoMC Fragility: annualized volatility sigmoid index

Output: ConfidenceModifier with GRADUATED adjustments (NOT binary veto) plus
circuit_breaker=True for SEVERE conditions ONLY.

circuit_breaker=True ONLY for two conditions:
  1. M-Score > -1.78 AND (Z distress OR debt/ebitda > 4x OR VoMC > 0.7)
  2. Z-Score < 1.0 AND debt/ebitda > 4x

All other risk levels use graduated margin/variance adjustments.

Design decisions:
  - Risk scores are deterministic (pure functions from risk_scores.py)
  - LLM (MODEL_FLASH) is used ONLY for narrative text, never for scoring
  - Beneish M-Score requires prior year data; falls back to "not computed"
    when yfinance does not have two years of balance sheet data
  - DataCoverage tracks which data sources contributed to the assessment
  - circuit_breaker=True triggers guardian_veto=True in the state
"""

from __future__ import annotations

import sys

import yfinance as yf
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from lockin.agents.llm import MODEL_FLASH, get_llm
from lockin.agents.risk_scores import altman_z_score, beneish_m_score, vomc_fragility
from lockin.agents.types import ConfidenceModifier, DataCoverage, Signal
from lockin.data import get_fundamentals
from lockin.graph.state import InvestmentState


# ---------------------------------------------------------------------------
# Thresholds (from plan spec)
# ---------------------------------------------------------------------------

_M_MANIPULATOR_THRESHOLD = -1.78    # Beneish (1999)
_M_BORDERLINE_THRESHOLD = -2.22     # Beneish (1999) — between clean and suspicious
_Z_DISTRESS_THRESHOLD = 1.81        # Altman (1968)
_Z_SEVERE_THRESHOLD = 1.0           # Severe distress: triggers CB with high leverage
_VOMC_HIGH_THRESHOLD = 0.7          # High fragility
_VOMC_ELEVATED_THRESHOLD = 0.5      # Elevated fragility
_DEBT_EBITDA_CIRCUIT_BREAKER = 4.0  # x4 leverage triggers CB with Z-Score < 1.0


# ---------------------------------------------------------------------------
# System prompt (narrative only)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a financial risk analyst specializing in bankruptcy prediction and "
    "earnings quality assessment. "
    "You have been given quantitative risk scores (Altman Z-Score, Beneish M-Score, "
    "VoMC Fragility, Debt/EBITDA). Your task is to write a concise risk narrative "
    "(2-3 sentences) summarising what these scores mean for this company. "
    "Do NOT recalculate the scores — they are deterministic. "
    "Focus on: what the combination of scores implies about financial health, "
    "earnings quality, and tail risk. Be direct and data-driven."
)


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------


def _safe_get(df, row: str, col_idx: int = 0):
    """Safely extract a value from a yfinance DataFrame by row name and column index.

    Returns None if the row doesn't exist, the column doesn't exist, or the
    value is NaN/None.
    """
    try:
        if row not in df.index:
            return None
        if col_idx >= len(df.columns):
            return None
        val = df.loc[row, df.columns[col_idx]]
        if val is None:
            return None
        # pandas NaN check
        import math
        if isinstance(val, float) and math.isnan(val):
            return None
        return float(val)
    except Exception:  # noqa: BLE001
        return None


def _extract_altman_inputs(
    bs,       # balance sheet DataFrame
    fin,      # financials DataFrame
    info: dict,
) -> dict:
    """Extract inputs needed for Altman Z-Score from yfinance DataFrames."""
    return {
        "working_capital": _safe_get(bs, "Working Capital"),
        "retained_earnings": _safe_get(bs, "Retained Earnings"),
        "ebit": _safe_get(fin, "EBIT"),
        "market_cap": info.get("marketCap"),
        "total_liabilities": _safe_get(bs, "Total Liabilities Net Minority Interest"),
        "revenue": _safe_get(fin, "Total Revenue"),
        "total_assets": _safe_get(bs, "Total Assets"),
    }


def _compute_beneish(bs, fin) -> dict | None:
    """Compute Beneish M-Score from yfinance DataFrames.

    Requires two years of data (current and prior year). Returns None if
    prior year data is not available.

    The Beneish indices are year-over-year ratios. For a clean firm, all
    indices are approximately 1.0.
    """
    if len(bs.columns) < 2 or len(fin.columns) < 2:
        return None  # prior year data unavailable

    def _ratio(cur, pri):
        """Safe ratio — returns 1.0 if either is None/zero (neutral index)."""
        if cur is None or pri is None or pri == 0:
            return 1.0
        return cur / pri

    # --- Current year ---
    recv_cur = _safe_get(bs, "Receivables", 0) or _safe_get(bs, "Accounts Receivable", 0)
    rev_cur = _safe_get(fin, "Total Revenue", 0)
    gp_cur = _safe_get(fin, "Gross Profit", 0)
    ta_cur = _safe_get(bs, "Total Assets", 0)
    # PPE proxied by Net PPE (Property Plant Equipment)
    ppe_cur = _safe_get(bs, "Net PPE", 0)
    depr_cur = _safe_get(fin, "Reconciled Depreciation", 0)
    sga_cur = _safe_get(fin, "Selling General And Administration", 0)
    ltd_cur = _safe_get(bs, "Long Term Debt", 0)
    cl_cur = _safe_get(bs, "Current Liabilities", 0)
    ni_cur = _safe_get(fin, "Net Income", 0) or _safe_get(fin, "Net Income Common Stockholders", 0)
    cfo_cur = None  # yfinance financials don't directly expose CFO in income stmt

    # --- Prior year ---
    recv_pri = _safe_get(bs, "Receivables", 1) or _safe_get(bs, "Accounts Receivable", 1)
    rev_pri = _safe_get(fin, "Total Revenue", 1)
    gp_pri = _safe_get(fin, "Gross Profit", 1)
    ta_pri = _safe_get(bs, "Total Assets", 1)
    ppe_pri = _safe_get(bs, "Net PPE", 1)
    depr_pri = _safe_get(fin, "Reconciled Depreciation", 1)
    sga_pri = _safe_get(fin, "Selling General And Administration", 1)
    ltd_pri = _safe_get(bs, "Long Term Debt", 1)
    cl_pri = _safe_get(bs, "Current Liabilities", 1)

    # --- Compute indices ---
    # DSRI: (Receivables/Revenue)_cur / (Receivables/Revenue)_pri
    dsri_cur = _ratio(recv_cur, rev_cur)
    dsri_pri = _ratio(recv_pri, rev_pri)
    dsri = _ratio(dsri_cur, dsri_pri)

    # GMI: Gross Margin pri / Gross Margin cur
    gm_cur = _ratio(gp_cur, rev_cur)
    gm_pri = _ratio(gp_pri, rev_pri)
    gmi = _ratio(gm_pri, gm_cur)  # Note: GMI > 1 means margin deteriorating

    # AQI: (1 - (CurrentAssets + PPE) / TotalAssets)_cur / same_pri
    # Simplified: use (non-current non-PPE) / total_assets ratio
    # We proxy: AQI = (TA - recv - ppe) / ta_cur / prior
    def _aqi_ratio(recv, ppe, ta):
        if ta is None or ta == 0:
            return 0.0
        recv = recv or 0.0
        ppe = ppe or 0.0
        return (ta - recv - ppe) / ta

    aqi_cur_val = _aqi_ratio(recv_cur, ppe_cur, ta_cur)
    aqi_pri_val = _aqi_ratio(recv_pri, ppe_pri, ta_pri)
    aqi = _ratio(aqi_cur_val, aqi_pri_val)
    if aqi < 0 or aqi > 10:
        aqi = 1.0  # clamp pathological values

    # SGI: Revenue_cur / Revenue_pri
    sgi = _ratio(rev_cur, rev_pri)

    # DEPI: (Depr / (Depr + PPE))_pri / (Depr / (Depr + PPE))_cur
    def _depr_rate(depr, ppe):
        base = (depr or 0.0) + (ppe or 0.0)
        if base == 0:
            return 0.0
        return (depr or 0.0) / base

    depi_cur = _depr_rate(depr_cur, ppe_cur)
    depi_pri = _depr_rate(depr_pri, ppe_pri)
    depi = _ratio(depi_pri, depi_cur)  # pri/cur: >1 means slowing depreciation
    if depi < 0 or depi > 10:
        depi = 1.0

    # SGAI: (SGA/Rev)_cur / (SGA/Rev)_pri
    sgai_cur_val = _ratio(sga_cur, rev_cur)
    sgai_pri_val = _ratio(sga_pri, rev_pri)
    sgai = _ratio(sgai_cur_val, sgai_pri_val)
    if sgai < 0 or sgai > 10:
        sgai = 1.0

    # TATA: Total Accruals to Total Assets
    # Total accruals = net income - CFO
    # When CFO is unavailable, proxy TATA using net_income / total_assets
    # (conservative: assumes CFO ≈ 0)
    if ni_cur is not None and ta_cur is not None and ta_cur != 0:
        tata = ni_cur / ta_cur
    else:
        tata = 0.05  # neutral default

    # LVGI: (Total Debt/Total Assets)_cur / (Total Debt/Total Assets)_pri
    ltd_cur = ltd_cur or 0.0
    cl_cur = cl_cur or 0.0
    ltd_pri = ltd_pri or 0.0
    cl_pri = cl_pri or 0.0
    total_debt_cur = ltd_cur + cl_cur
    total_debt_pri = ltd_pri + cl_pri

    lev_cur = _ratio(total_debt_cur, ta_cur)
    lev_pri = _ratio(total_debt_pri, ta_pri)
    lvgi = _ratio(lev_cur, lev_pri)
    if lvgi < 0 or lvgi > 10:
        lvgi = 1.0

    return beneish_m_score(dsri=dsri, gmi=gmi, aqi=aqi, sgi=sgi,
                           depi=depi, sgai=sgai, tata=tata, lvgi=lvgi)


def _extract_daily_returns(ticker_obj) -> list[float]:
    """Extract daily price returns from yfinance 1y history."""
    try:
        hist = ticker_obj.history(period="1y")
        closes = hist["Close"].pct_change().dropna().tolist()
        return closes
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# ConfidenceModifier builder
# ---------------------------------------------------------------------------


def _build_modifier(
    z_result: dict,
    m_result: dict | None,
    vomc: float,
    debt_ebitda: float | None,
    narrative: str,
) -> ConfidenceModifier:
    """Build ConfidenceModifier from risk scores with GRADUATED adjustments.

    Graduated margin adjustment (additive):
      Altman Z-Score:
        grey zone (1.81 < Z <= 2.99): +0.10
        distress zone (Z <= 1.81):    +0.25
      Beneish M-Score:
        borderline (-2.22 < M <= -1.78): +0.10
        manipulator (M > -1.78):         +0.20
      VoMC Fragility:
        elevated (0.5 < fragility <= 0.7): +0.10
        high (fragility > 0.7):            +0.15

    Graduated variance adjustment:
      grey zone: +0.05
      distress:  +0.10

    circuit_breaker=True ONLY for:
      Condition 1: M > -1.78 AND (Z distress OR debt/ebitda > 4x OR VoMC > 0.7)
      Condition 2: Z < 1.0 AND debt/ebitda > 4x
    """
    z_score = z_result["z_score"]
    z_zone = z_result["zone"]

    m_score = m_result["m_score"] if m_result else None
    m_manipulator = m_result["likely_manipulator"] if m_result else False

    # --- Margin adjustment (additive) ---
    margin = 0.0

    # Z-Score contribution
    if z_zone == "distress":
        margin += 0.25
    elif z_zone == "grey":
        margin += 0.10

    # M-Score contribution
    if m_score is not None:
        if m_manipulator:  # M > -1.78
            margin += 0.20
        elif m_score > _M_BORDERLINE_THRESHOLD:  # -2.22 < M <= -1.78
            margin += 0.10

    # VoMC contribution
    if vomc > _VOMC_HIGH_THRESHOLD:
        margin += 0.15
    elif vomc > _VOMC_ELEVATED_THRESHOLD:
        margin += 0.10

    # --- Variance adjustment ---
    variance = 0.0
    if z_zone == "distress":
        variance += 0.10
    elif z_zone == "grey":
        variance += 0.05

    # --- Circuit breaker logic ---
    # Condition 1: M manipulator AND (Z distress OR high leverage OR high VoMC)
    z_distress = z_zone == "distress"
    high_leverage = (debt_ebitda is not None and debt_ebitda > _DEBT_EBITDA_CIRCUIT_BREAKER)
    high_vomc = vomc > _VOMC_HIGH_THRESHOLD

    cb_condition_1 = (
        m_manipulator
        and (z_distress or high_leverage or high_vomc)
    )

    # Condition 2: Severe Z (< 1.0) AND high leverage
    z_severe = z_score < _Z_SEVERE_THRESHOLD
    cb_condition_2 = z_severe and high_leverage

    circuit_breaker = cb_condition_1 or cb_condition_2

    # Build CB reason string
    cb_reason = None
    if circuit_breaker:
        reasons = []
        if cb_condition_1:
            reasons.append(
                f"M-Score {m_score:.2f} > {_M_MANIPULATOR_THRESHOLD} "
                f"(manipulation flagged) combined with: "
                + (f"Z distress ({z_score:.2f})" if z_distress else "")
                + (f" high leverage ({debt_ebitda:.1f}x)" if high_leverage else "")
                + (f" high VoMC ({vomc:.2f})" if high_vomc else "")
            )
        if cb_condition_2:
            reasons.append(
                f"Z-Score {z_score:.2f} < 1.0 (severe distress) "
                f"with Debt/EBITDA {debt_ebitda:.1f}x > 4x"
            )
        cb_reason = "; ".join(reasons)

    # --- Signals ---
    # z_score signal
    z_value_norm = max(0.0, min(1.0, z_score / 8.0))  # normalise to [0,1] range
    z_signal = Signal(
        name="z_score",
        value=z_score,
        category="bankruptcy_risk",
        has_base_rate=True,
        base_rate=None,  # populated in Phase 5 Validation
        base_rate_source="backtest",
    )

    # m_score signal
    m_value = m_score if m_score is not None else _M_MANIPULATOR_THRESHOLD
    m_signal = Signal(
        name="m_score",
        value=m_value,
        category="earnings_manipulation",
        has_base_rate=True,
        base_rate=0.55,  # Beneish (1999): 55% of manipulators detected above threshold
        base_rate_source="Beneish (1999)",
    )

    # piotroski_score — Guardian computes Piotroski quality score if data available
    # Note: Guardian uses a simplified Piotroski proxy (cash flow quality vs net income)
    # Full Piotroski F-Score computation requires both current and prior year data
    # which guardian accesses via yfinance balance_sheet. Placeholder = 0 when unavailable.
    piotroski_signal = Signal(
        name="piotroski_score",
        value=0.0,  # placeholder — Guardian does not compute full Piotroski (Value Hunter owns it)
        category="quality",
        has_base_rate=True,
        base_rate=0.62,  # Piotroski (2000): high-score firms outperform
        base_rate_source="Piotroski (2000)",
    )

    # vomc_fragility signal
    vomc_signal = Signal(
        name="vomc_fragility",
        value=vomc,
        category="volatility_risk",
        has_base_rate=True,
        base_rate=None,  # populated in Phase 5 Validation
        base_rate_source="backtest",
    )

    # --- Data coverage ---
    available = []
    missing = []
    for label, val in [
        ("Altman Z-Score", z_score),
        ("Beneish M-Score", m_score),
        ("VoMC Fragility", vomc),
        ("Debt/EBITDA", debt_ebitda),
    ]:
        if val is not None:
            available.append(label)
        else:
            missing.append(label)

    coverage_impact = -0.05 * len(missing) / max(len(available) + len(missing), 1)
    data_coverage = DataCoverage(
        available=available,
        missing=missing,
        confidence_impact=coverage_impact,
    )

    return ConfidenceModifier(
        margin_adjustment=margin,
        variance_adjustment=variance,
        circuit_breaker=circuit_breaker,
        circuit_breaker_reason=cb_reason,
        signals=[z_signal, m_signal, piotroski_signal, vomc_signal],
        data_coverage=data_coverage,
        reasoning=narrative,
    )


# ---------------------------------------------------------------------------
# LLM narrative helper
# ---------------------------------------------------------------------------


def _generate_narrative(
    ticker: str,
    z_result: dict,
    m_result: dict | None,
    vomc: float,
    debt_ebitda: float | None,
) -> str:
    """Call LLM (MODEL_FLASH) to produce a risk narrative. Graceful fallback."""
    m_str = (
        f"{m_result['m_score']:.2f} ({'manipulator' if m_result['likely_manipulator'] else 'clean'})"
        if m_result else "not computed (insufficient history)"
    )
    de_str = f"{debt_ebitda:.1f}x" if debt_ebitda is not None else "unknown"

    human_prompt = (
        f"Risk scores for {ticker}:\n"
        f"  Altman Z-Score: {z_result['z_score']:.2f} (zone: {z_result['zone']})\n"
        f"  Beneish M-Score: {m_str}\n"
        f"  VoMC Fragility: {vomc:.3f}\n"
        f"  Debt/EBITDA: {de_str}\n\n"
        "Write a 2-3 sentence risk narrative. Be concise and direct."
    )

    try:
        llm = get_llm(model=MODEL_FLASH, temperature=0.1)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]
        response = llm.invoke(messages)
        return response.content
    except Exception as exc:  # noqa: BLE001
        print(
            f"guardian: LLM narrative failed — {exc}. Using deterministic fallback.",
            file=sys.stderr,
        )
        return (
            f"{ticker} risk assessment: Z={z_result['z_score']:.2f} ({z_result['zone']}), "
            f"M={m_str}, VoMC={vomc:.3f}, Debt/EBITDA={de_str}. "
            "LLM narrative unavailable — deterministic scores used."
        )


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def guardian(state: InvestmentState, config: RunnableConfig) -> dict:
    """Guardian agent — compute risk scores and return ConfidenceModifier.

    Steps:
      1. Get ticker from state["asset_ticker"]
      2. Fetch balance sheet + price history via yf.Ticker
      3. Get fundamentals from state or get_fundamentals()
      4. Compute: Altman Z-Score, Beneish M-Score (if prior year available),
         VoMC fragility, Debt/EBITDA ratio
      5. Build ConfidenceModifier with GRADUATED adjustments
      6. Call LLM (MODEL_FLASH) for narrative only
      7. Return guardian state dict

    Fallback: if yfinance data is unavailable, uses fundamentals from state
    and returns a conservative modifier with missing data flagged.
    """
    ticker = state.get("asset_ticker", "UNKNOWN")

    # ------------------------------------------------------------------
    # Step 1: Fetch market data via yfinance
    # ------------------------------------------------------------------
    try:
        yf_ticker = yf.Ticker(ticker)
        bs = yf_ticker.balance_sheet
        fin = yf_ticker.financials
        info = yf_ticker.info or {}
        daily_returns = _extract_daily_returns(yf_ticker)
    except Exception as exc:  # noqa: BLE001
        print(
            f"guardian: yfinance fetch failed for {ticker} — {exc}",
            file=sys.stderr,
        )
        bs = None
        fin = None
        info = {}
        daily_returns = []

    # ------------------------------------------------------------------
    # Step 2: Get fundamentals (from state or fresh fetch)
    # ------------------------------------------------------------------
    try:
        fundamentals = get_fundamentals(ticker, as_of_date=None, store=False)
    except Exception as exc:  # noqa: BLE001
        print(
            f"guardian: get_fundamentals failed for {ticker} — {exc}",
            file=sys.stderr,
        )
        fundamentals = {}

    # ------------------------------------------------------------------
    # Step 3: Compute Altman Z-Score
    # ------------------------------------------------------------------
    altman_inputs = {}
    if bs is not None and fin is not None:
        altman_inputs = _extract_altman_inputs(bs, fin, info)

    # Fill missing Altman inputs from fundamentals dict
    mapping = {
        "total_assets": "total_assets",
        "revenue": "total_revenue",
        "ebit": "operating_income",
    }
    for z_key, fund_key in mapping.items():
        if altman_inputs.get(z_key) is None and fund_key in fundamentals:
            altman_inputs[z_key] = fundamentals.get(fund_key)

    # Check if we have the minimum inputs for Z-Score
    z_result = {"z_score": None, "zone": "unknown"}
    required_z = ["working_capital", "retained_earnings", "ebit",
                  "market_cap", "total_liabilities", "revenue", "total_assets"]
    z_available = all(
        altman_inputs.get(k) is not None for k in required_z
    )

    if z_available and altman_inputs["total_assets"] != 0:
        try:
            z_result = altman_z_score(
                working_capital=altman_inputs["working_capital"],
                retained_earnings=altman_inputs["retained_earnings"],
                ebit=altman_inputs["ebit"],
                market_cap=altman_inputs["market_cap"],
                total_liabilities=altman_inputs["total_liabilities"],
                revenue=altman_inputs["revenue"],
                total_assets=altman_inputs["total_assets"],
            )
        except ValueError:
            z_result = {"z_score": 0.0, "zone": "distress"}  # treat as worst case

    # If Z-Score computation failed, use conservative defaults
    if z_result["z_score"] is None:
        z_result = {"z_score": 1.5, "zone": "distress"}  # conservative fallback

    # ------------------------------------------------------------------
    # Step 4: Compute Beneish M-Score (requires prior year data)
    # ------------------------------------------------------------------
    m_result = None
    if bs is not None and fin is not None:
        try:
            m_result = _compute_beneish(bs, fin)
        except Exception as exc:  # noqa: BLE001
            print(
                f"guardian: Beneish M-Score computation failed — {exc}",
                file=sys.stderr,
            )
            m_result = None

    # ------------------------------------------------------------------
    # Step 5: Compute VoMC Fragility
    # ------------------------------------------------------------------
    vomc = vomc_fragility(daily_returns)

    # ------------------------------------------------------------------
    # Step 6: Compute Debt/EBITDA
    # ------------------------------------------------------------------
    debt_ebitda = None
    total_debt = fundamentals.get("total_debt")
    ebitda = fundamentals.get("ebitda")
    if total_debt is not None and ebitda is not None and ebitda != 0:
        debt_ebitda = abs(total_debt) / abs(ebitda)

    # ------------------------------------------------------------------
    # Step 7: Generate narrative (LLM)
    # ------------------------------------------------------------------
    narrative = _generate_narrative(ticker, z_result, m_result, vomc, debt_ebitda)

    # ------------------------------------------------------------------
    # Step 8: Build ConfidenceModifier
    # ------------------------------------------------------------------
    modifier = _build_modifier(z_result, m_result, vomc, debt_ebitda, narrative)

    # ------------------------------------------------------------------
    # Step 9: Build risk report dict
    # ------------------------------------------------------------------
    risk_report = {
        "ticker": ticker,
        "z_score": z_result.get("z_score"),
        "z_zone": z_result.get("zone"),
        "m_score": m_result.get("m_score") if m_result else None,
        "m_likely_manipulator": m_result.get("likely_manipulator") if m_result else None,
        "vomc_fragility": vomc,
        "debt_ebitda": debt_ebitda,
        "circuit_breaker": modifier.circuit_breaker,
        "circuit_breaker_reason": modifier.circuit_breaker_reason,
        "margin_adjustment": modifier.margin_adjustment,
        "variance_adjustment": modifier.variance_adjustment,
    }

    return {
        "guardian_modifier": modifier,
        "guardian_risk_report": risk_report,
        "guardian_veto": modifier.circuit_breaker,
        "guardian_veto_reason": modifier.circuit_breaker_reason or "",
    }
