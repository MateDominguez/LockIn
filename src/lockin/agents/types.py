"""
Typed dataclasses for agent output contracts.

These types enforce the Notion Judge spec's two-axis architecture:
  - Distribution agents (Value Hunter, Bear) produce ValueDistribution
  - Modifier agents (Macro Oracle, Guardian, Strategist) produce ConfidenceModifier
  - Judge synthesises into JudgeOutput

All agents exchange structured dataclasses rather than raw dicts so that
type errors are caught early and the schema is self-documenting.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DataCoverage:
    """Tracks which data sources were available vs missing for an agent run."""

    available: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    confidence_impact: float = 0.0


@dataclass
class Signal:
    """A single quantitative or qualitative signal used by an agent."""

    name: str
    value: float
    category: str
    has_base_rate: bool
    base_rate: float | None = None
    base_rate_source: str | None = None


@dataclass
class ConfidenceModifier:
    """Output of a Modifier agent (Macro Oracle, Guardian, Strategist).

    Modifier agents do not produce valuations — they adjust the margin of safety
    and variance that the Judge applies when synthesising distributions.
    """

    margin_adjustment: float
    variance_adjustment: float
    circuit_breaker: bool
    circuit_breaker_reason: str | None = None
    signals: list[Signal] = field(default_factory=list)
    data_coverage: DataCoverage = field(default_factory=DataCoverage)
    reasoning: str = ""


@dataclass
class ValueDistribution:
    """Output of a Distribution agent (Value Hunter, Bear).

    Captures the full probability distribution over intrinsic value so the
    Judge can perform Bayesian synthesis across bull and bear views.
    """

    expected_value: float
    std_dev: float
    p10: float
    p50: float
    p90: float
    confidence: float
    methods_used: list[str] = field(default_factory=list)
    data_coverage: DataCoverage = field(default_factory=DataCoverage)
    thesis: str = ""
    key_assumptions: list[str] = field(default_factory=list)


@dataclass
class JudgeOutput:
    """Final output of the Judge agent — the Bayesian consensus decision."""

    recommendation: str           # BUY | HOLD | PASS
    consensus_distribution: tuple  # (mu, sigma) of LogNormal
    valor_mediano: float
    precio_target: float
    margin_of_safety: float
    p_success: float
    p_base: float
    p_adjustments: dict = field(default_factory=dict)
    kelly_fraction: float = 0.0
    hold_conviction: float = 0.0
    known_unknowns: list[str] = field(default_factory=list)
    convergence_score: float = 0.0
    convergence_alert: bool = False
    bull_weight: float = 0.5
    bear_weight: float = 0.5
    modifiers_applied: dict = field(default_factory=dict)
    circuit_breaker: bool = False
    circuit_breaker_override: bool = False
