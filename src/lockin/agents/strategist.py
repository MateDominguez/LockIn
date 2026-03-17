"""
Strategist agent — Modifier agent producing a ConfidenceModifier.

The Strategist is a Family-2 Modifier agent: it does NOT opine on intrinsic price
(that's Value Hunter and Bear). Instead it adjusts HOW MUCH to trust the Distribution
agents by tuning variance and margin of safety.

Two primary signals:
- VeTO score (0-1): Organizational health indicator from earnings call NLP + analyst
  consensus. Has NO base rate (not empirically validated) — adjusts variance ONLY when
  score is low (<0.4). Does NOT adjust margin (deferred to Phase 4 per CONTEXT.md).
- Analyst momentum: Net analyst upgrades vs downgrades. HAS a calibrated base rate
  from Jegadeesh (2004). Adjusts margin_adjustment (+0.05) for net downgrades only.

circuit_breaker is ALWAYS False for Strategist — Guardian handles circuit-breaker logic.

Data sources:
- FMP API: earnings call transcripts (cached per ticker, graceful fallback without key)
- yfinance: analyst recommendations_summary
- LLM (MODEL_FLASH): sentiment scoring + VeTO extraction

Design references:
- Notion Judge spec (VeTO section): has_base_rate=False, variance only
- CONTEXT.md (Phase 3): VeTO margin-of-safety wiring deferred to Phase 4
- Jegadeesh (2004): analyst upgrade momentum signal with empirical base rate
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx
import yfinance as yf
from langchain_core.runnables import RunnableConfig

from lockin.agents.llm import MODEL_FLASH, get_llm
from lockin.agents.types import ConfidenceModifier, DataCoverage, Signal
from lockin.graph.state import InvestmentState
from lockin.utils.config import get_settings

# ---------------------------------------------------------------------------
# Module-level transcript cache (simple dict, keyed by ticker)
# Avoids repeated FMP API calls within a single process run.
# ---------------------------------------------------------------------------

_TRANSCRIPT_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# FMP transcript fetching
# ---------------------------------------------------------------------------


def _fetch_fmp_transcript(ticker: str, fmp_api_key: str) -> tuple[str, bool]:
    """Fetch the most recent earnings call transcript from FMP API.

    Returns (transcript_text, success). On any failure (missing key, network
    error, bad response) returns ("", False) so callers can degrade gracefully.

    Results are cached in _TRANSCRIPT_CACHE to avoid redundant API calls.
    """
    if not fmp_api_key:
        return "", False

    if ticker in _TRANSCRIPT_CACHE:
        return _TRANSCRIPT_CACHE[ticker], True

    url = (
        f"https://financialmodelingprep.com/api/v3/earning_call_transcript/"
        f"{ticker}?apikey={fmp_api_key}"
    )
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        # FMP returns a list of transcript objects; take the most recent
        if isinstance(data, list) and len(data) > 0:
            transcript_text = data[0].get("content", "")
        elif isinstance(data, dict):
            transcript_text = data.get("content", "")
        else:
            transcript_text = ""

        _TRANSCRIPT_CACHE[ticker] = transcript_text
        return transcript_text, bool(transcript_text)

    except Exception as exc:  # noqa: BLE001
        print(
            f"[Strategist] FMP transcript fetch failed for {ticker}: {exc}",
            file=sys.stderr,
        )
        return "", False


# ---------------------------------------------------------------------------
# yfinance analyst consensus
# ---------------------------------------------------------------------------


def _fetch_analyst_momentum(ticker: str) -> tuple[float, int, int, bool]:
    """Fetch analyst recommendation summary from yfinance.

    Computes analyst_momentum as:
        net = (strongBuy + buy) - (sell + strongSell)
        momentum = net / total_ratings  (normalised -1 to +1)

    Returns (analyst_momentum, buy_count, sell_count, success).
    On failure returns (0.0, 0, 0, False).
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        summary = ticker_obj.recommendations_summary

        if summary is None or summary.empty:
            return 0.0, 0, 0, False

        # Use only the most recent period (row 0 = 0m = current)
        recent = summary.iloc[0]
        strong_buy = int(recent.get("strongBuy", 0))
        buy = int(recent.get("buy", 0))
        hold = int(recent.get("hold", 0))
        sell = int(recent.get("sell", 0))
        strong_sell = int(recent.get("strongSell", 0))

        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return 0.0, 0, 0, False

        net_buy = strong_buy + buy
        net_sell = sell + strong_sell
        net = net_buy - net_sell
        momentum = net / total  # ranges from -1.0 (all sell) to +1.0 (all buy)

        return momentum, net_buy, net_sell, True

    except Exception as exc:  # noqa: BLE001
        print(
            f"[Strategist] yfinance analyst fetch failed for {ticker}: {exc}",
            file=sys.stderr,
        )
        return 0.0, 0, 0, False


# ---------------------------------------------------------------------------
# LLM sentiment scoring
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a financial strategist analyzing earnings call transcripts and analyst consensus data.
Your task is to extract structured signals for investment decision support.

Analyze the provided data and respond with ONLY a valid JSON object (no markdown, no code blocks)
containing exactly these fields:
{
  "overall_sentiment": <float 0-1, where 0=very bearish, 0.5=neutral, 1=very bullish>,
  "veto_score": <float 0-1, where 0=very unhealthy organizational tone, 1=very healthy>,
  "sentiment_label": <string: "bearish" | "neutral" | "bullish">,
  "narrative": <string: 1-2 sentence summary of key strategic signals>
}

VeTO score reflects organizational health signals in management language:
- High VeTO (>0.7): Clear, confident, specific guidance; management owns results
- Medium VeTO (0.4-0.7): Mixed signals, some hedging but still constructive
- Low VeTO (<0.4): Excessive hedging, blame-shifting, vague guidance, credibility concerns

Respond with ONLY the JSON object, no other text.
"""


def _llm_sentiment_analysis(
    ticker: str,
    transcript_excerpt: str,
    analyst_summary: str,
    llm: Any,
) -> dict:
    """Invoke LLM for sentiment scoring. Returns parsed dict with defaults on failure."""
    defaults = {
        "overall_sentiment": 0.5,
        "veto_score": 0.5,
        "sentiment_label": "neutral",
        "narrative": f"Insufficient data for {ticker} sentiment analysis.",
    }

    human_content = f"""Ticker: {ticker}

EARNINGS TRANSCRIPT EXCERPT (first 3000 chars):
{transcript_excerpt[:3000] if transcript_excerpt else "(no transcript available)"}

ANALYST CONSENSUS:
{analyst_summary}

Analyze the above and return the JSON object as specified."""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown code blocks if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        parsed = json.loads(raw)
        # Validate required fields are present, fill defaults otherwise
        result = {**defaults, **parsed}
        # Clamp float values to [0, 1]
        result["overall_sentiment"] = max(0.0, min(1.0, float(result["overall_sentiment"])))
        result["veto_score"] = max(0.0, min(1.0, float(result["veto_score"])))
        return result

    except Exception as exc:  # noqa: BLE001
        print(
            f"[Strategist] LLM sentiment parsing failed for {ticker}: {exc}",
            file=sys.stderr,
        )
        return defaults


# ---------------------------------------------------------------------------
# Main Strategist agent
# ---------------------------------------------------------------------------


def strategist(state: InvestmentState, config: RunnableConfig) -> dict:
    """Modifier agent: analyse strategic signals and output a ConfidenceModifier.

    Outputs:
    - strategist_modifier: ConfidenceModifier — typed contract for the Judge
    - strategist_veto: float (0-1) — VeTO score (backward compat scalar)
    - strategist_sentiment: float (0-1) — overall sentiment score
    - strategic_signals: dict — legacy flat dict of signal values
    - strategist_narrative: str — 1-2 sentence strategic narrative
    - strategist_confidence: float (0-1) — data coverage confidence

    VeTO design (per Notion Judge spec + CONTEXT.md):
    - has_base_rate=False: not empirically validated → does NOT adjust probability
    - Adjusts variance_adjustment += 0.10 ONLY when veto_score < 0.4
    - Does NOT adjust margin_adjustment (deferred to Phase 4)

    Analyst momentum design:
    - has_base_rate=True, base_rate_source="Jegadeesh (2004)"
    - Adjusts margin_adjustment += 0.05 ONLY for net analyst downgrades (momentum < 0)

    circuit_breaker: ALWAYS False (Guardian is responsible for circuit breakers)
    """
    ticker = state.get("asset_ticker", "UNKNOWN")
    settings = get_settings()

    available_sources: list[str] = []
    missing_sources: list[str] = []

    # ------------------------------------------------------------------
    # 1. Fetch FMP earnings transcript
    # ------------------------------------------------------------------
    transcript, fmp_ok = _fetch_fmp_transcript(ticker, settings.fmp_api_key)
    if fmp_ok:
        available_sources.append("fmp_transcript")
    else:
        missing_sources.append("fmp_transcript")

    # ------------------------------------------------------------------
    # 2. Fetch analyst consensus from yfinance
    # ------------------------------------------------------------------
    analyst_momentum, buy_count, sell_count, yf_ok = _fetch_analyst_momentum(ticker)
    if yf_ok:
        available_sources.append("yf_analyst_consensus")
    else:
        missing_sources.append("yf_analyst_consensus")

    # Build human-readable analyst summary for LLM context
    if yf_ok:
        analyst_summary = (
            f"Analyst ratings — Buy: {buy_count}, Sell: {sell_count}, "
            f"Net momentum: {analyst_momentum:+.2f} "
            f"({'upgrades' if analyst_momentum > 0 else 'downgrades' if analyst_momentum < 0 else 'neutral'})"
        )
    else:
        analyst_summary = "Analyst data unavailable."

    # ------------------------------------------------------------------
    # 3. LLM sentiment + VeTO scoring
    # ------------------------------------------------------------------
    llm_ok = False
    llm_result = {
        "overall_sentiment": 0.5,
        "veto_score": 0.5,
        "sentiment_label": "neutral",
        "narrative": f"No LLM analysis available for {ticker}.",
    }

    try:
        llm = get_llm(model=MODEL_FLASH, temperature=0.1)
        llm_result = _llm_sentiment_analysis(ticker, transcript, analyst_summary, llm)
        available_sources.append("llm_sentiment")
        llm_ok = True
    except Exception as exc:  # noqa: BLE001
        print(
            f"[Strategist] LLM invocation failed for {ticker}: {exc}",
            file=sys.stderr,
        )
        missing_sources.append("llm_sentiment")

    veto_score: float = llm_result["veto_score"]
    sentiment_score: float = llm_result["overall_sentiment"]
    sentiment_label: str = llm_result["sentiment_label"]
    narrative: str = llm_result["narrative"]

    # ------------------------------------------------------------------
    # 4. Compute adjustments per Notion Judge spec + CONTEXT.md
    # ------------------------------------------------------------------

    # Margin adjustment: VeTO does NOT contribute (deferred to Phase 4).
    # Only analyst momentum (net downgrades) adjusts margin.
    margin_adj = 0.0
    if analyst_momentum < 0:  # net analyst downgrades
        margin_adj += 0.05

    # Variance adjustment: VeTO only, conditional on low score.
    # VeTO has no base rate → only increases uncertainty, never lowers it.
    variance_adj = 0.0
    if veto_score < 0.4:  # low VeTO → unreliable organizational health signal
        variance_adj += 0.10

    # ------------------------------------------------------------------
    # 5. Build Signal list
    # ------------------------------------------------------------------

    # VeTO category: thresholds match the LLM scoring rubric
    veto_category = (
        "low" if veto_score < 0.4
        else "medium" if veto_score < 0.7
        else "high"
    )

    analyst_category = (
        "upgrade" if analyst_momentum > 0
        else "downgrade" if analyst_momentum < 0
        else "neutral"
    )

    signals = [
        Signal(
            name="veto_score",
            value=veto_score,
            category=veto_category,
            has_base_rate=False,    # CRITICAL: VeTO has no empirical base rate
            base_rate=None,
            base_rate_source=None,
        ),
        Signal(
            name="analyst_momentum",
            value=analyst_momentum,
            category=analyst_category,
            has_base_rate=True,     # Calibrated base rate from academic literature
            base_rate=None,         # Phase 5 will fill from backtesting
            base_rate_source="Jegadeesh (2004)",
        ),
        Signal(
            name="sentiment_price_impact",
            value=sentiment_score,
            category=sentiment_label,
            has_base_rate=False,    # No empirical validation for LLM sentiment
            base_rate=None,
            base_rate_source=None,
        ),
    ]

    # ------------------------------------------------------------------
    # 6. Data coverage confidence
    # ------------------------------------------------------------------

    # Each source contributes equally to confidence estimate
    source_count = len(available_sources)
    max_sources = 3  # fmp_transcript, yf_analyst_consensus, llm_sentiment
    confidence_impact = source_count / max_sources  # 0.0, 0.33, 0.67, or 1.0

    # Overall strategist confidence: data coverage weighted average
    # When all sources available: 1.0 impact; when none: 0.0
    data_coverage = DataCoverage(
        available=available_sources,
        missing=missing_sources,
        confidence_impact=confidence_impact,
    )

    # ------------------------------------------------------------------
    # 7. Assemble ConfidenceModifier
    # ------------------------------------------------------------------

    strategist_modifier = ConfidenceModifier(
        margin_adjustment=margin_adj,
        variance_adjustment=variance_adj,
        circuit_breaker=False,          # Strategist NEVER triggers circuit breaker
        circuit_breaker_reason=None,
        signals=signals,
        data_coverage=data_coverage,
        reasoning=narrative,
    )

    # Strategist confidence: blend of data coverage and LLM availability
    strategist_confidence = confidence_impact

    # ------------------------------------------------------------------
    # 8. Return InvestmentState-compatible dict
    # ------------------------------------------------------------------

    return {
        "strategist_modifier": strategist_modifier,
        "strategist_veto": veto_score,         # scalar for backward compat
        "strategist_sentiment": sentiment_score,
        "strategic_signals": {
            "veto_score": veto_score,
            "veto_category": veto_category,
            "analyst_momentum": analyst_momentum,
            "analyst_buy_count": buy_count,
            "analyst_sell_count": sell_count,
            "overall_sentiment": sentiment_score,
            "sentiment_label": sentiment_label,
            "margin_adjustment": margin_adj,
            "variance_adjustment": variance_adj,
        },
        "strategist_narrative": narrative,
        "strategist_confidence": strategist_confidence,
    }
