"""
Pure mathematical functions for the Judge agent's 7-step Bayesian Consensus Algorithm.

This module is intentionally free of all network calls, LLM invocations, and
side effects.  Every function is a pure transformation of its inputs, making the
algorithm fully unit-testable without mocks.

Algorithm overview (Notion Judge spec v1.0):
  Step 1 — Log Pool: combine Bull and Bear ValueDistributions weighted by
            confidence × data_quality_factor into a single log-normal.
  Step 2 — Probability: Oracle base rate adjusted by Guardian/Strategist signals
            that carry empirical base rates (has_base_rate=True).
  Step 3 — Circuit Breaker: read from Guardian ConfidenceModifier.
  Step 4 — Margin of Safety: base 0.30 + all modifier margin_adjustments,
            clamped [0.20, 0.70].
  Step 5 — Recommendation: BUY | HOLD | PASS using Kelly/3 (KELLY_FRACTION=0.33).
            HOLD when p_final < 0.40; PASS when circuit_breaker or overvalued.
  Step 6 — Map of Ignorance: aggregate all data_coverage.missing, compute
            convergence between bull and bear log-normal means.
  Step 7 — Assemble JudgeOutput dataclass.

Design decisions:
  - Kelly/3 (factor=0.33): more conservative than Kelly/4 for early-stage system.
  - HOLD threshold: p_final < 0.40 (spec v1.0; NOT the old 0.50 threshold).
  - VeTO signal (has_base_rate=False) does NOT adjust p_success — informational only.
  - Convergence alert triggers when convergence_score > 0.90 (bull/bear agree closely).
"""

from __future__ import annotations

import math

from lockin.agents.types import ConfidenceModifier, JudgeOutput, ValueDistribution

# Conservative Kelly fraction (Kelly/3, per Notion spec v1.0)
KELLY_FRACTION = 0.33

# Default log-normal sigma when expected_value is zero or missing
_DEFAULT_SIGMA_BULL = 0.20
_DEFAULT_SIGMA_BEAR = 0.25

# p_success bounds (safety caps)
_P_MIN = 0.10
_P_MAX = 0.90

# Margin of safety bounds
_MARGIN_MIN = 0.20
_MARGIN_MAX = 0.70
_MARGIN_BASE = 0.30  # Graham/Buffett baseline

# HOLD threshold (Notion Judge spec v1.0 — do NOT change without spec update)
_HOLD_THRESHOLD = 0.40

# Convergence alert threshold
_CONVERGENCE_ALERT_THRESHOLD = 0.90

# Guardian signal weight for probability adjustment
_GUARDIAN_SIGNAL_WEIGHT = 0.5

# Strategist signal weight for probability adjustment
_STRATEGIST_SIGNAL_WEIGHT = 0.3

# Base probability for signal delta computation (neutral prior)
_BASE_GENERAL = 0.50


# ---------------------------------------------------------------------------
# Step 1 helpers
# ---------------------------------------------------------------------------


def data_quality_factor(data_coverage) -> float:
    """Compute data quality factor from DataCoverage.

    Returns the fraction of data sources that were available.  When no data
    sources are tracked at all, returns 0.5 (neutral weight) rather than 0.0
    to avoid collapsing a distribution to zero weight.

    Args:
        data_coverage: DataCoverage instance with .available and .missing lists.

    Returns:
        Float in [0.0, 1.0].  0.5 when no sources tracked; otherwise
        len(available) / (len(available) + len(missing)).
    """
    if not data_coverage.available:
        return 0.5
    total = len(data_coverage.available) + len(data_coverage.missing)
    return len(data_coverage.available) / total


def log_pool(
    bull_dist: ValueDistribution,
    bear_dist: ValueDistribution,
) -> tuple[float, float, float, float]:
    """Combine Bull and Bear log-normal distributions via Log Pool.

    The Log Pool is a weighted geometric average of probability distributions.
    For log-normals, this is equivalent to a weighted average of their natural-
    log space parameters (mu, sigma^2).

    Weights are proportional to: confidence × data_quality_factor(data_coverage)

    Args:
        bull_dist: Bull (Value Hunter) ValueDistribution.
        bear_dist: Bear ValueDistribution.

    Returns:
        Tuple (mu_combined, sigma_sq_combined, w_bull, w_bear) where:
          - mu_combined: weighted mean in log space
          - sigma_sq_combined: weighted variance in log space
          - w_bull, w_bear: normalised weights (sum to 1.0)
    """
    w_bull_raw = bull_dist.confidence * data_quality_factor(bull_dist.data_coverage)
    w_bear_raw = bear_dist.confidence * data_quality_factor(bear_dist.data_coverage)

    total = w_bull_raw + w_bear_raw
    if total == 0:
        total = 1.0
    w_bull = w_bull_raw / total
    w_bear = w_bear_raw / total

    # Convert expected values to log-space means
    mu_bull = math.log(bull_dist.expected_value) if bull_dist.expected_value > 0 else 0.0
    mu_bear = math.log(bear_dist.expected_value) if bear_dist.expected_value > 0 else 0.0

    # Approximate log-normal sigma from relative std dev
    sigma_bull = (
        bull_dist.std_dev / bull_dist.expected_value
        if bull_dist.expected_value > 0
        else _DEFAULT_SIGMA_BULL
    )
    sigma_bear = (
        bear_dist.std_dev / bear_dist.expected_value
        if bear_dist.expected_value > 0
        else _DEFAULT_SIGMA_BEAR
    )

    mu_combined = w_bull * mu_bull + w_bear * mu_bear
    sigma_sq_combined = w_bull * sigma_bull ** 2 + w_bear * sigma_bear ** 2

    return mu_combined, sigma_sq_combined, w_bull, w_bear


# ---------------------------------------------------------------------------
# Step 2
# ---------------------------------------------------------------------------


def compute_p_success(
    oracle_modifier: ConfidenceModifier,
    guardian_modifier: ConfidenceModifier,
    strategist_modifier: ConfidenceModifier,
) -> tuple[float, float, dict]:
    """Compute probability of investment thesis success.

    Two-step:
      2A: Oracle base rate — extracted from the "macro_base_rate" signal.
          Defaults to 0.50 when no such signal exists.
      2B: Guardian signals with has_base_rate=True adjust p upward/downward.
      2C: Strategist signals with has_base_rate=True adjust p (lower weight).
          VeTO signals (has_base_rate=False) are IGNORED — they carry no
          empirical base rate and must not influence p_success.

    All adjustments are clamped to [0.10, 0.90].

    Args:
        oracle_modifier:    Macro Oracle ConfidenceModifier.
        guardian_modifier:  Guardian ConfidenceModifier.
        strategist_modifier: Strategist ConfidenceModifier.

    Returns:
        Tuple (p_final, p_base, p_adjustments) where:
          - p_final: clamped probability [0.10, 0.90]
          - p_base:  Oracle base rate before any adjustment
          - p_adjustments: dict mapping signal name -> delta applied
    """
    # 2A: Oracle base rate from macro_base_rate signal
    macro_signal = next(
        (s for s in oracle_modifier.signals if s.name == "macro_base_rate"), None
    )
    p_base = macro_signal.base_rate if (macro_signal and macro_signal.base_rate is not None) else _BASE_GENERAL

    p_adjusted = p_base
    p_adjustments: dict[str, float] = {}

    # 2B: Guardian signals with calibrated base rates
    for signal in guardian_modifier.signals:
        if signal.has_base_rate and signal.base_rate is not None:
            delta = (signal.base_rate - _BASE_GENERAL) * _GUARDIAN_SIGNAL_WEIGHT
            p_adjusted += delta
            p_adjustments[signal.name] = delta

    # 2C: Strategist signals with calibrated base rates (VeTO excluded)
    for signal in strategist_modifier.signals:
        if signal.has_base_rate and signal.base_rate is not None:
            delta = (signal.base_rate - _BASE_GENERAL) * _STRATEGIST_SIGNAL_WEIGHT
            p_adjusted += delta
            p_adjustments[signal.name] = delta

    p_final = max(_P_MIN, min(_P_MAX, p_adjusted))
    return p_final, p_base, p_adjustments


# ---------------------------------------------------------------------------
# Step 3
# ---------------------------------------------------------------------------


def check_circuit_breaker(
    guardian_modifier: ConfidenceModifier,
) -> tuple[bool, str | None]:
    """Extract circuit breaker state from Guardian ConfidenceModifier.

    Args:
        guardian_modifier: Guardian ConfidenceModifier.

    Returns:
        Tuple (circuit_breaker: bool, circuit_breaker_reason: str | None).
    """
    return guardian_modifier.circuit_breaker, guardian_modifier.circuit_breaker_reason


# ---------------------------------------------------------------------------
# Step 4
# ---------------------------------------------------------------------------


def compute_margin_of_safety(
    oracle_modifier: ConfidenceModifier,
    guardian_modifier: ConfidenceModifier,
    strategist_modifier: ConfidenceModifier,
) -> float:
    """Compute margin of safety as base 0.30 + all modifier adjustments.

    Each modifier agent (Macro Oracle, Guardian, Strategist) contributes an
    additive margin_adjustment.  The sum is clamped to [0.20, 0.70].

    Args:
        oracle_modifier:    Macro Oracle ConfidenceModifier.
        guardian_modifier:  Guardian ConfidenceModifier.
        strategist_modifier: Strategist ConfidenceModifier.

    Returns:
        Margin of safety as a float in [0.20, 0.70].
    """
    margin = (
        _MARGIN_BASE
        + oracle_modifier.margin_adjustment
        + guardian_modifier.margin_adjustment
        + strategist_modifier.margin_adjustment
    )
    return max(_MARGIN_MIN, min(_MARGIN_MAX, margin))


# ---------------------------------------------------------------------------
# Step 5
# ---------------------------------------------------------------------------


def compute_recommendation(
    current_price: float,
    valor_mediano: float,
    precio_target: float,
    p_final: float,
) -> tuple[str, float, float]:
    """Compute BUY / HOLD / PASS recommendation using Kelly/3.

    Decision tree (strict order — checked top to bottom):
      1. current_price > precio_target  -> PASS (overvalued relative to target)
      2. p_final < HOLD_THRESHOLD (0.40) -> HOLD (thesis probability too low)
      3. b = (valor_mediano - current_price) / current_price <= 0 -> PASS
      4. Otherwise: BUY with kelly_fraction = max(0, full_kelly * KELLY_FRACTION)

    Kelly formula:
      full_kelly = (p * b - (1 - p)) / b
      conservative_kelly = max(0, full_kelly * 0.33)

    Args:
        current_price: Current market price.
        valor_mediano:  Consensus intrinsic value (median = exp(mu_combined)).
        precio_target:  Buy price target = valor_mediano * (1 - margin_of_safety).
        p_final:       Probability of investment success.

    Returns:
        Tuple (recommendation, kelly_fraction, hold_conviction) where:
          - recommendation: "BUY" | "HOLD" | "PASS"
          - kelly_fraction: Conservative Kelly fraction (0.0 for non-BUY)
          - hold_conviction: 1.0 - p_final for HOLD; 0.0 otherwise
    """
    # Overvalued: current price exceeds the required margin of safety target
    if current_price > precio_target:
        return "PASS", 0.0, 0.0

    # HOLD: p_final too low to justify a position (p < 0.40)
    if p_final < _HOLD_THRESHOLD:
        hold_conviction = 1.0 - p_final
        return "HOLD", 0.0, hold_conviction

    # BUY: compute Kelly fraction
    b = (valor_mediano - current_price) / current_price
    if b <= 0:
        return "PASS", 0.0, 0.0

    full_kelly = (p_final * b - (1 - p_final)) / b
    kelly_conservative = max(0.0, full_kelly * KELLY_FRACTION)
    return "BUY", kelly_conservative, 0.0


# ---------------------------------------------------------------------------
# Step 6
# ---------------------------------------------------------------------------


def compute_map_of_ignorance(
    bull_dist: ValueDistribution,
    bear_dist: ValueDistribution,
    guardian_modifier: ConfidenceModifier,
    strategist_modifier: ConfidenceModifier,
    mu_bull: float,
    mu_bear: float,
) -> tuple[list[str], float, bool]:
    """Aggregate known unknowns and compute bull/bear convergence.

    Known unknowns: union of all data_coverage.missing lists from all agents.
    Convergence: measures how closely bull and bear agree on intrinsic value
    in log space.  High convergence (>0.90) suggests the two views are
    nearly identical, which may indicate groupthink or thin analytical margin.

    Args:
        bull_dist:          Bull ValueDistribution.
        bear_dist:          Bear ValueDistribution.
        guardian_modifier:  Guardian ConfidenceModifier.
        strategist_modifier: Strategist ConfidenceModifier.
        mu_bull:            Bull log-space mean (math.log(bull expected value)).
        mu_bear:            Bear log-space mean (math.log(bear expected value)).

    Returns:
        Tuple (known_unknowns, convergence_score, convergence_alert) where:
          - known_unknowns: deduplicated list of missing data items
          - convergence_score: float in [0, 1]; 1 = perfect agreement
          - convergence_alert: True when convergence_score > 0.90
    """
    known_unknowns = list(set(
        bull_dist.data_coverage.missing
        + bear_dist.data_coverage.missing
        + guardian_modifier.data_coverage.missing
        + strategist_modifier.data_coverage.missing
    ))

    max_mu = max(abs(mu_bull), abs(mu_bear), 0.01)
    convergence = 1.0 - abs(mu_bull - mu_bear) / max_mu
    convergence_alert = convergence > _CONVERGENCE_ALERT_THRESHOLD

    return known_unknowns, convergence, convergence_alert


# ---------------------------------------------------------------------------
# Step 7 — Full algorithm entry point
# ---------------------------------------------------------------------------


def run_judge_algorithm(
    bull_dist: ValueDistribution,
    bear_dist: ValueDistribution,
    oracle_modifier: ConfidenceModifier,
    guardian_modifier: ConfidenceModifier,
    strategist_modifier: ConfidenceModifier,
    current_price: float,
) -> JudgeOutput:
    """Run the complete 7-step Bayesian Consensus Algorithm.

    This is the single entry point that orchestrates all steps and assembles
    a JudgeOutput.  Pure function — no side effects.

    Args:
        bull_dist:           Bull (Value Hunter) ValueDistribution.
        bear_dist:           Bear ValueDistribution.
        oracle_modifier:     Macro Oracle ConfidenceModifier.
        guardian_modifier:   Guardian ConfidenceModifier.
        strategist_modifier: Strategist ConfidenceModifier.
        current_price:       Current market price of the asset.

    Returns:
        JudgeOutput with all fields populated.
    """
    # ------------------------------------------------------------------
    # Step 1: Log Pool — combine distributions
    # ------------------------------------------------------------------
    mu_combined, sigma_sq_combined, w_bull, w_bear = log_pool(bull_dist, bear_dist)

    total_variance_adj = (
        oracle_modifier.variance_adjustment
        + guardian_modifier.variance_adjustment
        + strategist_modifier.variance_adjustment
    )
    sigma_final_sq = sigma_sq_combined * (1 + total_variance_adj)
    valor_mediano = math.exp(mu_combined)

    # ------------------------------------------------------------------
    # Step 2: Probability of success
    # ------------------------------------------------------------------
    p_final, p_base, p_adjustments = compute_p_success(
        oracle_modifier, guardian_modifier, strategist_modifier
    )

    # ------------------------------------------------------------------
    # Step 3: Circuit breaker
    # ------------------------------------------------------------------
    circuit_breaker, cb_reason = check_circuit_breaker(guardian_modifier)

    # ------------------------------------------------------------------
    # Step 4: Margin of safety and price target
    # ------------------------------------------------------------------
    margin = compute_margin_of_safety(oracle_modifier, guardian_modifier, strategist_modifier)
    precio_target = valor_mediano * (1 - margin)

    # ------------------------------------------------------------------
    # Step 5: Recommendation
    # ------------------------------------------------------------------
    if circuit_breaker:
        recommendation = "PASS"
        kelly_fraction = 0.0
        hold_conviction = 0.0
    else:
        recommendation, kelly_fraction, hold_conviction = compute_recommendation(
            current_price, valor_mediano, precio_target, p_final
        )

    # ------------------------------------------------------------------
    # Step 6: Map of Ignorance
    # ------------------------------------------------------------------
    mu_bull = math.log(bull_dist.expected_value) if bull_dist.expected_value > 0 else 0.0
    mu_bear = math.log(bear_dist.expected_value) if bear_dist.expected_value > 0 else 0.0

    known_unknowns, convergence, convergence_alert = compute_map_of_ignorance(
        bull_dist, bear_dist, guardian_modifier, strategist_modifier, mu_bull, mu_bear
    )

    # ------------------------------------------------------------------
    # Step 7: Assemble JudgeOutput
    # ------------------------------------------------------------------
    return JudgeOutput(
        recommendation=recommendation,
        consensus_distribution=(mu_combined, sigma_final_sq ** 0.5),
        valor_mediano=valor_mediano,
        precio_target=precio_target,
        margin_of_safety=margin,
        p_success=p_final,
        p_base=p_base,
        p_adjustments=p_adjustments,
        kelly_fraction=kelly_fraction,
        hold_conviction=hold_conviction,
        known_unknowns=known_unknowns,
        convergence_score=convergence,
        convergence_alert=convergence_alert,
        bull_weight=w_bull,
        bear_weight=w_bear,
        modifiers_applied={
            "oracle_margin": oracle_modifier.margin_adjustment,
            "guardian_margin": guardian_modifier.margin_adjustment,
            "strategist_margin": strategist_modifier.margin_adjustment,
            "total_variance_adj": total_variance_adj,
        },
        circuit_breaker=circuit_breaker,
        circuit_breaker_override=False,
    )
