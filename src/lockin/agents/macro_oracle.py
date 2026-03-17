"""
Macro Oracle agent — Phase 3, Plan 02.

The Macro Oracle is a Modifier agent (Family 2 per Notion Judge spec).  It does NOT
opine on price — it opines on how much to trust the Distribution agents (Value Hunter
and Bear) by detecting the current economic regime and risk appetite from FRED data.

Output: ConfidenceModifier with calibrated base rates from FRED historical data.
These feed the Judge's probability calculation (margin_adjustment + variance_adjustment).

Design decisions:
  - Uses MODEL_FLASH (gemini-2.0-flash): structured quantitative task, no deep reasoning.
  - Deterministic fallback: if LLM JSON parse fails, rule-based regime classification
    guarantees a valid ConfidenceModifier is always returned.
  - circuit_breaker is ALWAYS False for Oracle — Oracle adjusts trust, never blocks.
  - DataUnavailableError: if FRED is down, returns a conservative fallback with
    macro_confidence=0.3 so the Judge applies minimal macro weight.
"""

from __future__ import annotations

import json
import re
import sys

from langchain_core.runnables import RunnableConfig

from lockin.agents.base import invoke_agent
from lockin.agents.llm import MODEL_FLASH, get_llm
from lockin.agents.types import ConfidenceModifier, DataCoverage, Signal
from lockin.data import DataUnavailableError, MacroResult, get_macro_indicators
from lockin.graph.state import InvestmentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a macroeconomic analyst using Ray Dalio's economic machine framework. "
    "Analyze the provided FRED macroeconomic indicators to determine:\n"
    "  1) Economic phase: expansion | late_expansion | contraction | recovery\n"
    "  2) Risk appetite: risk_on | risk_off | neutral\n"
    "  3) Yield curve signal: normal | flat | inverted\n"
    "  4) Fed stance: hawkish | neutral | dovish\n\n"
    "Respond ONLY with a JSON object — no prose, no markdown fences. Format:\n"
    '{"phase": "...", "risk_appetite": "...", "yield_curve": "...", "fed_stance": "...", '
    '"reasoning": "..."}'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_macro_prompt(macro: MacroResult) -> str:
    """Format MacroResult fields into a structured human prompt for the LLM."""
    lines = ["FRED Macroeconomic Indicators (latest available):"]

    def _fmt(label: str, val, unit: str = "") -> str:
        if val is None:
            return f"  {label}: N/A"
        return f"  {label}: {val}{unit}"

    lines.append(_fmt("Real GDP growth (annualised, %)", macro.get("gdp"), "%"))
    lines.append(_fmt("CPI (YoY %)", macro.get("cpi"), "%"))
    lines.append(_fmt("Core PCE (YoY %)", macro.get("core_pce"), "%"))
    lines.append(_fmt("Fed Funds Rate (%)", macro.get("fed_funds"), "%"))
    lines.append(_fmt("Yield Curve 10Y-2Y (bps)", macro.get("yield_10y_2y")))
    lines.append(_fmt("Yield Curve 10Y-3M (bps)", macro.get("yield_10y_3m")))
    lines.append(_fmt("Unemployment Rate (%)", macro.get("unemployment"), "%"))

    lines.append(
        "\nAnalyse these indicators and classify the economic regime. "
        "Respond ONLY with the JSON object specified."
    )
    return "\n".join(lines)


def _deterministic_regime(macro: MacroResult) -> dict:
    """Rule-based regime classification as a fallback or LLM complement.

    These rules are independent of LLM output and always produce a valid result.
    They are used to override LLM classifications for deterministic fields
    (yield_curve, fed_stance) where the logic is unambiguous.
    """
    yield_10y_2y = macro.get("yield_10y_2y")
    yield_10y_3m = macro.get("yield_10y_3m")
    fed_funds = macro.get("fed_funds")

    # Yield curve: inverted if either spread is negative
    if (yield_10y_2y is not None and yield_10y_2y < 0) or (
        yield_10y_3m is not None and yield_10y_3m < 0
    ):
        yield_curve = "inverted"
    elif (yield_10y_2y is not None and abs(yield_10y_2y) < 0.5) or (
        yield_10y_3m is not None and abs(yield_10y_3m) < 0.5
    ):
        yield_curve = "flat"
    else:
        yield_curve = "normal"

    # Fed stance: hawkish if funds > 4%, dovish if < 2%
    if fed_funds is not None:
        if fed_funds > 4.0:
            fed_stance = "hawkish"
        elif fed_funds < 2.0:
            fed_stance = "dovish"
        else:
            fed_stance = "neutral"
    else:
        fed_stance = "neutral"

    return {"yield_curve": yield_curve, "fed_stance": fed_stance}


def _parse_llm_json(raw: str) -> dict:
    """Parse LLM JSON response with regex fallback if json.loads fails."""
    raw = raw.strip()

    # Remove markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```\s*$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    # Regex fallback: extract key fields individually
    result = {}
    for field in ("phase", "risk_appetite", "yield_curve", "fed_stance", "reasoning"):
        match = re.search(rf'"{field}"\s*:\s*"([^"]+)"', raw)
        if match:
            result[field] = match.group(1)

    return result


def _build_confidence_modifier(
    llm_regime: dict,
    det_regime: dict,
    macro: MacroResult,
) -> ConfidenceModifier:
    """Build ConfidenceModifier from detected regime.

    Margin and variance adjustments per Notion spec:
      - expansion + low VIX (extreme_greed): +0.15 to +0.20
      - contraction + extreme_fear: -0.05
      - high volatility: +0.05 variance
      - circuit_breaker: ALWAYS False for Oracle
    """
    # Merge: deterministic overrides LLM for rule-based fields
    phase = llm_regime.get("phase", "expansion")
    risk_appetite = llm_regime.get("risk_appetite", "neutral")
    yield_curve = det_regime.get("yield_curve", llm_regime.get("yield_curve", "normal"))
    fed_stance = det_regime.get("fed_stance", llm_regime.get("fed_stance", "neutral"))
    reasoning = llm_regime.get("reasoning", "Deterministic regime classification applied.")

    # Determine regime sentiment
    is_expansion = phase in ("expansion", "late_expansion")
    is_contraction = phase in ("contraction",)
    is_risk_on = risk_appetite == "risk_on"
    is_risk_off = risk_appetite == "risk_off"
    is_inverted = yield_curve == "inverted"
    is_hawkish = fed_stance == "hawkish"

    # --- Margin adjustment ---
    # Extreme greed: expansion + risk_on + normal yield curve
    if is_expansion and is_risk_on and not is_inverted:
        margin_adjustment = 0.175  # midpoint of [+0.15, +0.20]
    # Extreme fear: contraction + risk_off + inverted
    elif is_contraction and is_risk_off and is_inverted:
        margin_adjustment = -0.05
    # Contraction or risk_off alone: moderate negative
    elif is_contraction or (is_risk_off and is_inverted):
        margin_adjustment = -0.03
    # Late expansion or hawkish: slight positive
    elif phase == "late_expansion" or (is_hawkish and not is_inverted):
        margin_adjustment = 0.05
    else:
        margin_adjustment = 0.0

    # --- Variance adjustment ---
    # High volatility = inverted yield curve (recession signal) + contraction
    if is_inverted and (is_contraction or is_hawkish):
        variance_adjustment = 0.05
    else:
        variance_adjustment = 0.0

    # --- Signals ---
    # macro_base_rate: from FRED historical data — expansion regime hit rate
    # Source: expansion_regime entry in BASE_RATE_TABLE (Dalio framework, FRED)
    macro_base_rate_value = 0.55 if is_expansion else 0.40
    macro_base_rate = Signal(
        name="macro_base_rate",
        value=macro_base_rate_value,
        category="macro",
        has_base_rate=True,
        base_rate=0.55,  # academic_default from BASE_RATE_TABLE["expansion_regime"]
        base_rate_source="FRED",
    )

    # style_regime: qualitative signal — expansion vs contraction
    style_value = 1.0 if is_expansion else -1.0
    style_regime = Signal(
        name="style_regime",
        value=style_value,
        category="regime",
        has_base_rate=False,
    )

    # flow_direction: directional risk appetite signal
    flow_value = 1.0 if is_risk_on else (-1.0 if is_risk_off else 0.0)
    flow_direction = Signal(
        name="flow_direction",
        value=flow_value,
        category="sentiment",
        has_base_rate=False,
    )

    # --- Data coverage ---
    available = []
    missing = []
    for field_name, field_key in [
        ("GDP", "gdp"),
        ("CPI", "cpi"),
        ("Core PCE", "core_pce"),
        ("Fed Funds", "fed_funds"),
        ("Yield 10Y-2Y", "yield_10y_2y"),
        ("Yield 10Y-3M", "yield_10y_3m"),
        ("Unemployment", "unemployment"),
    ]:
        if macro.get(field_key) is not None:
            available.append(field_name)
        else:
            missing.append(field_name)

    coverage_impact = -0.1 * len(missing) / max(len(available) + len(missing), 1)
    data_coverage = DataCoverage(
        available=available,
        missing=missing,
        confidence_impact=coverage_impact,
    )

    return ConfidenceModifier(
        margin_adjustment=margin_adjustment,
        variance_adjustment=variance_adjustment,
        circuit_breaker=False,  # ALWAYS False for Oracle
        circuit_breaker_reason=None,
        signals=[macro_base_rate, style_regime, flow_direction],
        data_coverage=data_coverage,
        reasoning=reasoning,
    )


def _fallback_modifier() -> ConfidenceModifier:
    """Conservative ConfidenceModifier when FRED data is unavailable."""
    macro_base_rate = Signal(
        name="macro_base_rate",
        value=0.55,  # academic_default (expansion regime) — no live data
        category="macro",
        has_base_rate=True,
        base_rate=0.55,
        base_rate_source="FRED",
    )
    style_regime = Signal(
        name="style_regime",
        value=0.0,  # unknown — neutral
        category="regime",
        has_base_rate=False,
    )
    flow_direction = Signal(
        name="flow_direction",
        value=0.0,  # unknown — neutral
        category="sentiment",
        has_base_rate=False,
    )
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=False,
        circuit_breaker_reason=None,
        signals=[macro_base_rate, style_regime, flow_direction],
        data_coverage=DataCoverage(
            available=[],
            missing=["GDP", "CPI", "Core PCE", "Fed Funds", "Yield 10Y-2Y", "Yield 10Y-3M", "Unemployment"],
            confidence_impact=-0.7,
        ),
        reasoning="FRED data unavailable — conservative neutral stance applied.",
    )


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def macro_oracle(state: InvestmentState, config: RunnableConfig) -> dict:
    """Macro Oracle agent — detect economic regime and return ConfidenceModifier.

    Steps:
      1. Fetch macro data from FRED via the public data API.
      2. Build deterministic regime (yield curve, Fed stance) — always valid.
      3. Call LLM (MODEL_FLASH) for phase + risk appetite classification.
      4. Parse LLM JSON; merge with deterministic rules.
      5. Build ConfidenceModifier per Notion spec.
      6. Return dict with macro_regime, macro_confidence, macro_narrative, oracle_modifier.

    Fallback: if FRED is unavailable, returns conservative defaults with
    macro_confidence=0.3 so the Judge applies minimal macro weight.
    """
    # ------------------------------------------------------------------
    # Step 1: Fetch FRED macro data
    # ------------------------------------------------------------------
    try:
        macro: MacroResult = get_macro_indicators(as_of_date=None, store=False)
    except DataUnavailableError as exc:
        print(
            f"macro_oracle: FRED data unavailable — {exc}. Returning fallback.",
            file=sys.stderr,
        )
        return {
            "macro_regime": {
                "phase": "unknown",
                "risk_appetite": "neutral",
                "yield_curve": "unknown",
                "fed_stance": "neutral",
            },
            "macro_confidence": 0.3,
            "macro_narrative": (
                "FRED data unavailable. Macro Oracle operating in fallback mode — "
                "applying conservative neutral regime with reduced confidence."
            ),
            "oracle_modifier": _fallback_modifier(),
        }

    # ------------------------------------------------------------------
    # Step 2: Deterministic regime (yield curve, Fed stance)
    # ------------------------------------------------------------------
    det_regime = _deterministic_regime(macro)

    # ------------------------------------------------------------------
    # Step 3: LLM regime classification
    # ------------------------------------------------------------------
    llm_regime: dict = {}
    try:
        llm = get_llm(model=MODEL_FLASH, temperature=0.1)
        human_prompt = _build_macro_prompt(macro)
        raw_response = invoke_agent(
            llm,
            system_prompt=_SYSTEM_PROMPT,
            human_prompt=human_prompt,
            agent_name="macro_oracle",
        )
        llm_regime = _parse_llm_json(raw_response)
    except Exception as exc:  # noqa: BLE001
        print(
            f"macro_oracle: LLM call failed — {exc}. Using deterministic fallback.",
            file=sys.stderr,
        )
        # Deterministic fallback for LLM fields
        gdp = macro.get("gdp")
        llm_regime = {
            "phase": "expansion" if (gdp is not None and gdp > 0) else "contraction",
            "risk_appetite": "neutral",
            "yield_curve": det_regime.get("yield_curve", "normal"),
            "fed_stance": det_regime.get("fed_stance", "neutral"),
            "reasoning": "LLM unavailable — deterministic regime classification applied.",
        }

    # ------------------------------------------------------------------
    # Step 4: Build ConfidenceModifier
    # ------------------------------------------------------------------
    modifier = _build_confidence_modifier(llm_regime, det_regime, macro)

    # ------------------------------------------------------------------
    # Step 5: Build macro_regime dict and confidence score
    # ------------------------------------------------------------------
    phase = llm_regime.get("phase", "expansion")
    risk_appetite = llm_regime.get("risk_appetite", "neutral")

    # Confidence: penalise for missing fields; boost for strong expansion signal
    available_count = len(modifier.data_coverage.available)
    total_fields = 7
    data_completeness = available_count / total_fields

    if phase in ("expansion",) and risk_appetite == "risk_on":
        base_confidence = 0.80
    elif phase in ("contraction",) and risk_appetite == "risk_off":
        base_confidence = 0.75  # contraction is clearer to detect
    elif phase in ("late_expansion", "recovery"):
        base_confidence = 0.65
    else:
        base_confidence = 0.60

    macro_confidence = round(base_confidence * data_completeness, 3)
    macro_confidence = max(0.3, min(0.95, macro_confidence))  # clamp [0.3, 0.95]

    # Build macro_regime dict (matches mock_macro_oracle's schema)
    macro_regime = {
        "phase": phase,
        "risk_appetite": risk_appetite,
        "yield_curve": det_regime.get("yield_curve", "normal"),
        "fed_stance": det_regime.get("fed_stance", "neutral"),
    }

    macro_narrative = (
        f"Economic phase: {phase} | Risk appetite: {risk_appetite} | "
        f"Yield curve: {macro_regime['yield_curve']} | "
        f"Fed stance: {macro_regime['fed_stance']}. "
        f"Data coverage: {available_count}/{total_fields} FRED indicators available. "
        f"{modifier.reasoning}"
    )

    return {
        "macro_regime": macro_regime,
        "macro_confidence": macro_confidence,
        "macro_narrative": macro_narrative,
        "oracle_modifier": modifier,
    }
