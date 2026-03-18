"""
Unit tests for lockin.agents.judge_math — pure 7-step Judge algorithm.

All tests are fully deterministic; no mocks required since judge_math.py
has no network calls or LLM invocations.

Test coverage:
  - log_pool: weight proportionality, mu_combined bounds
  - compute_p_success: Oracle base rate, Guardian adjustment, VeTO exclusion, clamp
  - compute_margin_of_safety: base 0.30, additivity, clamp [0.20, 0.70]
  - compute_recommendation: BUY / HOLD / PASS paths, Kelly/3 math
  - compute_map_of_ignorance: convergence alert threshold
  - run_judge_algorithm: end-to-end integration with known inputs
"""

from __future__ import annotations

import math

import pytest

from lockin.agents.judge_math import (
    KELLY_FRACTION,
    _HOLD_THRESHOLD,
    _CONVERGENCE_ALERT_THRESHOLD,
    compute_map_of_ignorance,
    compute_margin_of_safety,
    compute_p_success,
    compute_recommendation,
    data_quality_factor,
    log_pool,
    run_judge_algorithm,
)
from lockin.agents.types import (
    ConfidenceModifier,
    DataCoverage,
    JudgeOutput,
    Signal,
    ValueDistribution,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_coverage(available: list[str] | None = None, missing: list[str] | None = None) -> DataCoverage:
    return DataCoverage(
        available=available or ["revenue", "earnings", "book_value"],
        missing=missing or [],
    )


def _make_bull_dist(
    expected_value: float = 200.0,
    std_dev: float = 40.0,
    confidence: float = 0.8,
    missing: list[str] | None = None,
) -> ValueDistribution:
    # None means use empty missing list (bull default: all data available).
    effective_missing = [] if missing is None else missing
    return ValueDistribution(
        expected_value=expected_value,
        std_dev=std_dev,
        p10=expected_value * 0.7,
        p50=expected_value,
        p90=expected_value * 1.3,
        confidence=confidence,
        data_coverage=_make_coverage(missing=effective_missing),
    )


def _make_bear_dist(
    expected_value: float = 100.0,
    std_dev: float = 25.0,
    confidence: float = 0.5,
    missing: list[str] | None = None,
) -> ValueDistribution:
    # Use explicit sentinel: None means use default missing list.
    # Passing an empty list [] produces an empty missing list (no default substitution).
    effective_missing = ["competitive_threat"] if missing is None else missing
    return ValueDistribution(
        expected_value=expected_value,
        std_dev=std_dev,
        p10=expected_value * 0.6,
        p50=expected_value,
        p90=expected_value * 1.2,
        confidence=confidence,
        data_coverage=_make_coverage(missing=effective_missing),
    )


def _neutral_modifier(
    margin: float = 0.0,
    variance: float = 0.0,
    circuit_breaker: bool = False,
    signals: list | None = None,
) -> ConfidenceModifier:
    return ConfidenceModifier(
        margin_adjustment=margin,
        variance_adjustment=variance,
        circuit_breaker=circuit_breaker,
        signals=signals or [],
        data_coverage=_make_coverage(),
    )


def _make_oracle_modifier(base_rate: float = 0.55) -> ConfidenceModifier:
    """Oracle with a macro_base_rate signal."""
    signal = Signal(
        name="macro_base_rate",
        value=base_rate,
        category="macro",
        has_base_rate=True,
        base_rate=base_rate,
        base_rate_source="FRED",
    )
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=False,
        signals=[signal],
        data_coverage=_make_coverage(),
    )


def _make_guardian_modifier(signals: list | None = None) -> ConfidenceModifier:
    """Guardian with optional risk signals."""
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=False,
        signals=signals or [],
        data_coverage=_make_coverage(),
    )


def _make_strategist_modifier(signals: list | None = None) -> ConfidenceModifier:
    """Strategist with optional signals."""
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=False,
        signals=signals or [],
        data_coverage=_make_coverage(),
    )


# ---------------------------------------------------------------------------
# Step 1: log_pool tests
# ---------------------------------------------------------------------------


def test_log_pool_weights_proportional_to_confidence():
    """Bull conf=0.8 > Bear conf=0.5 -> w_bull > w_bear (equal data quality)."""
    bull = _make_bull_dist(confidence=0.8)
    bear = _make_bear_dist(confidence=0.5)
    _, _, w_bull, w_bear = log_pool(bull, bear)
    assert w_bull > w_bear, f"Expected w_bull > w_bear, got {w_bull:.4f} vs {w_bear:.4f}"


def test_log_pool_weights_sum_to_one():
    """w_bull + w_bear must equal 1.0."""
    bull = _make_bull_dist()
    bear = _make_bear_dist()
    _, _, w_bull, w_bear = log_pool(bull, bear)
    assert abs(w_bull + w_bear - 1.0) < 1e-10


def test_log_pool_combined_mu_between_bull_and_bear():
    """mu_combined must lie strictly between mu_bull and mu_bear."""
    bull = _make_bull_dist(expected_value=200.0, confidence=0.8)
    bear = _make_bear_dist(expected_value=100.0, confidence=0.5)
    mu_combined, _, _, _ = log_pool(bull, bear)
    mu_bull = math.log(200.0)
    mu_bear = math.log(100.0)
    assert mu_bear < mu_combined < mu_bull, (
        f"Expected {mu_bear:.4f} < {mu_combined:.4f} < {mu_bull:.4f}"
    )


def test_log_pool_equal_confidence_midpoint():
    """Equal confidence + equal data quality -> w_bull == w_bear and mu_combined is midpoint."""
    # Use identical missing lists so data_quality_factor is the same for both
    bull = _make_bull_dist(expected_value=math.e ** 2, confidence=0.7, missing=[])
    bear = _make_bear_dist(expected_value=math.e ** 1, confidence=0.7, missing=[])
    mu_combined, _, w_bull, w_bear = log_pool(bull, bear)
    # Equal confidence + equal data quality -> equal weights
    assert abs(w_bull - w_bear) < 0.01
    expected_mu = (2 + 1) / 2  # midpoint = 1.5
    assert abs(mu_combined - expected_mu) < 0.05


def test_log_pool_data_quality_affects_weights():
    """A distribution with more missing data has lower effective weight."""
    bull = _make_bull_dist(confidence=0.7, missing=[])            # quality=1.0
    bear = _make_bear_dist(confidence=0.7, missing=["a", "b", "c"])  # quality lower
    _, _, w_bull, w_bear = log_pool(bull, bear)
    assert w_bull > w_bear


# ---------------------------------------------------------------------------
# Step 2: compute_p_success tests
# ---------------------------------------------------------------------------


def test_p_success_base_from_oracle():
    """p_base must come from Oracle macro_base_rate signal."""
    oracle = _make_oracle_modifier(base_rate=0.60)
    guardian = _make_guardian_modifier()
    strategist = _make_strategist_modifier()
    p_final, p_base, _ = compute_p_success(oracle, guardian, strategist)
    assert p_base == 0.60


def test_p_success_default_base_when_no_signal():
    """Missing macro_base_rate signal -> p_base defaults to 0.50."""
    oracle = _neutral_modifier()  # no signals
    guardian = _make_guardian_modifier()
    strategist = _make_strategist_modifier()
    p_final, p_base, _ = compute_p_success(oracle, guardian, strategist)
    assert p_base == 0.50


def test_p_success_guardian_adjusts_upward():
    """Guardian signal with base_rate=0.70 should push p_final above p_base."""
    oracle = _make_oracle_modifier(base_rate=0.55)
    g_signal = Signal(
        name="piotroski_high",
        value=8.0,
        category="quality",
        has_base_rate=True,
        base_rate=0.70,
    )
    guardian = _make_guardian_modifier(signals=[g_signal])
    strategist = _make_strategist_modifier()
    p_final, p_base, adjustments = compute_p_success(oracle, guardian, strategist)
    assert p_final > p_base
    assert "piotroski_high" in adjustments
    # delta = (0.70 - 0.50) * 0.5 = 0.10
    assert abs(adjustments["piotroski_high"] - 0.10) < 1e-10


def test_p_success_guardian_adjusts_downward():
    """Guardian signal with base_rate=0.30 should push p_final below p_base."""
    oracle = _make_oracle_modifier(base_rate=0.55)
    g_signal = Signal(
        name="z_score",
        value=1.2,
        category="bankruptcy_risk",
        has_base_rate=True,
        base_rate=0.30,
    )
    guardian = _make_guardian_modifier(signals=[g_signal])
    strategist = _make_strategist_modifier()
    p_final, p_base, _ = compute_p_success(oracle, guardian, strategist)
    assert p_final < p_base


def test_p_success_veto_does_not_adjust():
    """VeTO signal with has_base_rate=False must NOT change p_final."""
    oracle = _make_oracle_modifier(base_rate=0.55)
    guardian = _make_guardian_modifier()
    veto_signal = Signal(
        name="veto_score",
        value=0.3,
        category="narrative",
        has_base_rate=False,  # VeTO — no base rate
        base_rate=None,
    )
    strategist = _make_strategist_modifier(signals=[veto_signal])
    p_final, p_base, adjustments = compute_p_success(oracle, guardian, strategist)
    # VeTO should not appear in adjustments
    assert "veto_score" not in adjustments
    # p_final should equal p_base (no other signals)
    assert abs(p_final - p_base) < 1e-10


def test_p_success_clamped_at_maximum():
    """Very high base rate + positive signals should be clamped at 0.90."""
    oracle = _make_oracle_modifier(base_rate=0.90)
    g_signal = Signal(
        name="piotroski_high",
        value=9.0,
        category="quality",
        has_base_rate=True,
        base_rate=0.90,
    )
    guardian = _make_guardian_modifier(signals=[g_signal])
    strategist = _make_strategist_modifier()
    p_final, _, _ = compute_p_success(oracle, guardian, strategist)
    assert p_final <= 0.90


def test_p_success_clamped_at_minimum():
    """Very low base rate + negative signals should be clamped at 0.10."""
    oracle = _make_oracle_modifier(base_rate=0.10)
    g_signal = Signal(
        name="z_score_distress",
        value=0.5,
        category="bankruptcy_risk",
        has_base_rate=True,
        base_rate=0.10,
    )
    guardian = _make_guardian_modifier(signals=[g_signal])
    strategist = _make_strategist_modifier()
    p_final, _, _ = compute_p_success(oracle, guardian, strategist)
    assert p_final >= 0.10


# ---------------------------------------------------------------------------
# Step 4: compute_margin_of_safety tests
# ---------------------------------------------------------------------------


def test_margin_base_030_when_no_adjustments():
    """No modifier adjustments -> margin == 0.30 exactly."""
    oracle = _neutral_modifier(margin=0.0)
    guardian = _neutral_modifier(margin=0.0)
    strategist = _neutral_modifier(margin=0.0)
    margin = compute_margin_of_safety(oracle, guardian, strategist)
    assert abs(margin - 0.30) < 1e-10


def test_margin_additive():
    """Margin = 0.30 + sum of all modifier margin_adjustments."""
    oracle = _neutral_modifier(margin=0.05)
    guardian = _neutral_modifier(margin=0.10)
    strategist = _neutral_modifier(margin=0.02)
    margin = compute_margin_of_safety(oracle, guardian, strategist)
    assert abs(margin - 0.47) < 1e-10


def test_margin_clamped_at_maximum():
    """Large adjustments should be clamped at 0.70."""
    oracle = _neutral_modifier(margin=0.20)
    guardian = _neutral_modifier(margin=0.25)
    strategist = _neutral_modifier(margin=0.15)
    margin = compute_margin_of_safety(oracle, guardian, strategist)
    assert margin == 0.70


def test_margin_clamped_at_minimum():
    """Negative adjustments should be clamped at 0.20."""
    oracle = _neutral_modifier(margin=-0.10)
    guardian = _neutral_modifier(margin=-0.05)
    strategist = _neutral_modifier(margin=-0.10)
    margin = compute_margin_of_safety(oracle, guardian, strategist)
    assert margin == 0.20


# ---------------------------------------------------------------------------
# Step 5: compute_recommendation tests
# ---------------------------------------------------------------------------


def test_recommendation_buy():
    """current_price < precio_target AND p_final >= 0.40 -> BUY."""
    # valor_mediano=200, margin=0.30, target=140, current=100, p=0.60
    rec, kelly, hold = compute_recommendation(
        current_price=100.0,
        valor_mediano=200.0,
        precio_target=140.0,
        p_final=0.60,
    )
    assert rec == "BUY"
    assert kelly > 0.0
    assert hold == 0.0


def test_recommendation_hold_low_probability():
    """p_final < 0.40 -> HOLD with non-zero hold_conviction."""
    rec, kelly, hold = compute_recommendation(
        current_price=100.0,
        valor_mediano=200.0,
        precio_target=140.0,
        p_final=0.35,
    )
    assert rec == "HOLD"
    assert kelly == 0.0
    assert hold > 0.0
    assert abs(hold - (1.0 - 0.35)) < 1e-10


def test_recommendation_hold_conviction_formula():
    """hold_conviction == 1.0 - p_final exactly."""
    p = 0.32
    _, _, hold = compute_recommendation(
        current_price=50.0,
        valor_mediano=150.0,
        precio_target=105.0,
        p_final=p,
    )
    assert abs(hold - (1.0 - p)) < 1e-10


def test_recommendation_pass_overvalued():
    """current_price > precio_target -> PASS regardless of p_final."""
    rec, kelly, hold = compute_recommendation(
        current_price=160.0,  # above target 140
        valor_mediano=200.0,
        precio_target=140.0,
        p_final=0.70,
    )
    assert rec == "PASS"
    assert kelly == 0.0
    assert hold == 0.0


def test_recommendation_pass_negative_upside():
    """b <= 0 (current >= valor_mediano) -> PASS."""
    rec, kelly, hold = compute_recommendation(
        current_price=200.0,  # equal to valor_mediano
        valor_mediano=200.0,
        precio_target=140.0,
        p_final=0.60,
    )
    assert rec == "PASS"


def test_kelly_third_fraction():
    """Kelly fraction = max(0, full_kelly * 0.33)."""
    p = 0.60
    valor_mediano = 200.0
    current_price = 100.0
    precio_target = 140.0   # target below current is not the case here

    rec, kelly_conservative, _ = compute_recommendation(
        current_price=current_price,
        valor_mediano=valor_mediano,
        precio_target=precio_target,
        p_final=p,
    )
    assert rec == "BUY"

    # Manual Kelly calculation
    b = (valor_mediano - current_price) / current_price  # = 1.0
    full_kelly = (p * b - (1 - p)) / b
    expected = max(0.0, full_kelly * KELLY_FRACTION)
    assert abs(kelly_conservative - expected) < 1e-10


def test_kelly_fraction_constant_is_033():
    """KELLY_FRACTION module constant must be 0.33 (not 0.25)."""
    assert KELLY_FRACTION == 0.33


# ---------------------------------------------------------------------------
# Step 6: compute_map_of_ignorance tests
# ---------------------------------------------------------------------------


def test_convergence_alert_when_similar_values():
    """Bull and bear with similar expected values -> convergence > 0.90 -> alert."""
    bull = _make_bull_dist(expected_value=100.0)
    bear = _make_bear_dist(expected_value=99.0)  # very close
    guardian = _make_guardian_modifier()
    strategist = _make_strategist_modifier()
    mu_bull = math.log(100.0)
    mu_bear = math.log(99.0)
    _, convergence, alert = compute_map_of_ignorance(bull, bear, guardian, strategist, mu_bull, mu_bear)
    assert convergence > _CONVERGENCE_ALERT_THRESHOLD
    assert alert is True


def test_no_convergence_alert_when_values_diverge():
    """Bull and bear with very different expected values -> no alert."""
    bull = _make_bull_dist(expected_value=300.0)
    bear = _make_bear_dist(expected_value=80.0)
    guardian = _make_guardian_modifier()
    strategist = _make_strategist_modifier()
    mu_bull = math.log(300.0)
    mu_bear = math.log(80.0)
    _, convergence, alert = compute_map_of_ignorance(bull, bear, guardian, strategist, mu_bull, mu_bear)
    assert not alert


def test_known_unknowns_deduplicated():
    """Items appearing in multiple missing lists should appear once."""
    bull = _make_bull_dist(missing=["insider_sentiment", "regulatory_risk"])
    bear = _make_bear_dist(missing=["insider_sentiment", "competitive_threat"])
    guardian = _make_guardian_modifier()
    strategist = _make_strategist_modifier()
    mu_bull = math.log(200.0)
    mu_bear = math.log(100.0)
    unknowns, _, _ = compute_map_of_ignorance(bull, bear, guardian, strategist, mu_bull, mu_bear)
    # insider_sentiment should appear only once
    assert unknowns.count("insider_sentiment") == 1
    assert "regulatory_risk" in unknowns
    assert "competitive_threat" in unknowns


# ---------------------------------------------------------------------------
# Full algorithm: run_judge_algorithm
# ---------------------------------------------------------------------------


def test_full_algorithm_returns_judge_output():
    """run_judge_algorithm returns a JudgeOutput instance."""
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(expected_value=200.0, confidence=0.8),
        bear_dist=_make_bear_dist(expected_value=100.0, confidence=0.5),
        oracle_modifier=_make_oracle_modifier(base_rate=0.55),
        guardian_modifier=_make_guardian_modifier(),
        strategist_modifier=_make_strategist_modifier(),
        current_price=80.0,
    )
    assert isinstance(result, JudgeOutput)


def test_full_algorithm_recommendation_buy():
    """With favourable inputs: price below target, p > 0.40 -> BUY."""
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(expected_value=200.0, confidence=0.8),
        bear_dist=_make_bear_dist(expected_value=100.0, confidence=0.5),
        oracle_modifier=_make_oracle_modifier(base_rate=0.60),
        guardian_modifier=_neutral_modifier(margin=0.0, circuit_breaker=False),
        strategist_modifier=_neutral_modifier(margin=0.0),
        current_price=80.0,
    )
    assert result.recommendation == "BUY"
    assert result.kelly_fraction > 0.0


def test_full_algorithm_circuit_breaker_forces_pass():
    """circuit_breaker=True in guardian -> recommendation='PASS'."""
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(expected_value=200.0, confidence=0.8),
        bear_dist=_make_bear_dist(expected_value=100.0, confidence=0.5),
        oracle_modifier=_make_oracle_modifier(base_rate=0.60),
        guardian_modifier=ConfidenceModifier(
            margin_adjustment=0.25,
            variance_adjustment=0.10,
            circuit_breaker=True,
            circuit_breaker_reason="Z-Score severe + high leverage",
            signals=[],
            data_coverage=_make_coverage(),
        ),
        strategist_modifier=_neutral_modifier(),
        current_price=80.0,
    )
    assert result.recommendation == "PASS"
    assert result.circuit_breaker is True
    assert result.kelly_fraction == 0.0


def test_full_algorithm_p_below_040_gives_hold():
    """p_final < 0.40 -> recommendation='HOLD'."""
    # Force low p_base
    oracle = _make_oracle_modifier(base_rate=0.30)
    # Guardian signal that pushes p_final even lower
    g_signal = Signal(
        name="distress",
        value=1.0,
        category="bankruptcy_risk",
        has_base_rate=True,
        base_rate=0.25,
    )
    guardian = _make_guardian_modifier(signals=[g_signal])
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(expected_value=200.0, confidence=0.8),
        bear_dist=_make_bear_dist(expected_value=100.0, confidence=0.5),
        oracle_modifier=oracle,
        guardian_modifier=guardian,
        strategist_modifier=_neutral_modifier(),
        current_price=80.0,
    )
    assert result.recommendation == "HOLD"
    assert result.p_success < _HOLD_THRESHOLD
    assert result.hold_conviction > 0.0
    assert result.kelly_fraction == 0.0


def test_full_algorithm_valor_mediano_positive():
    """valor_mediano = exp(mu_combined) must be positive."""
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(),
        bear_dist=_make_bear_dist(),
        oracle_modifier=_make_oracle_modifier(),
        guardian_modifier=_make_guardian_modifier(),
        strategist_modifier=_make_strategist_modifier(),
        current_price=100.0,
    )
    assert result.valor_mediano > 0.0


def test_full_algorithm_modifiers_applied_dict():
    """modifiers_applied dict contains expected keys."""
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(),
        bear_dist=_make_bear_dist(),
        oracle_modifier=_neutral_modifier(margin=0.05),
        guardian_modifier=_neutral_modifier(margin=0.10, variance=0.05),
        strategist_modifier=_neutral_modifier(margin=0.02, variance=0.02),
        current_price=100.0,
    )
    assert "oracle_margin" in result.modifiers_applied
    assert "guardian_margin" in result.modifiers_applied
    assert "strategist_margin" in result.modifiers_applied
    assert "total_variance_adj" in result.modifiers_applied
    assert abs(result.modifiers_applied["oracle_margin"] - 0.05) < 1e-10
    assert abs(result.modifiers_applied["guardian_margin"] - 0.10) < 1e-10


def test_full_algorithm_bull_bear_weights_sum_to_one():
    """bull_weight + bear_weight must equal 1.0."""
    result = run_judge_algorithm(
        bull_dist=_make_bull_dist(),
        bear_dist=_make_bear_dist(),
        oracle_modifier=_make_oracle_modifier(),
        guardian_modifier=_make_guardian_modifier(),
        strategist_modifier=_make_strategist_modifier(),
        current_price=100.0,
    )
    assert abs(result.bull_weight + result.bear_weight - 1.0) < 1e-10


def test_hold_threshold_constant_is_040():
    """_HOLD_THRESHOLD must be 0.40 (NOT 0.50 — guards against regression)."""
    assert _HOLD_THRESHOLD == 0.40


def test_convergence_alert_threshold_is_090():
    """_CONVERGENCE_ALERT_THRESHOLD must be 0.90."""
    assert _CONVERGENCE_ALERT_THRESHOLD == 0.90
