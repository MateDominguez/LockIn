"""
Data quality validator for the LockIn data layer.

Provides DataValidator, which:
  - Computes a quality_score from missing required fields
  - Detects outliers by comparing current vs previous fundamentals
  - Triggers HITL for changes > 200% (logged to audit_logs via log_audit_event)

Design notes:
  - Threshold 50-200%: warning-level outlier (outlier_flags set, no HITL)
  - Threshold > 200%: HITL trigger (outlier_flags set, hitl_required=True, audit logged)
  - Uses "data_validation" as static sentinel thread_id — the validator has no
    LangGraph thread context.
  - If database_url is empty, log_audit_event falls back to stderr (same as audit.py).
"""

from __future__ import annotations

from lockin.data.data_types import FundamentalsResult, ValidationResult, REQUIRED_FUNDAMENTAL_FIELDS
from lockin.utils.audit import log_audit_event


class DataValidator:
    """Validates FundamentalsResult for quality and outlier detection."""

    def __init__(self, database_url: str = "") -> None:
        self._database_url = database_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_fundamentals(
        self,
        current: FundamentalsResult,
        previous: FundamentalsResult | None = None,
    ) -> ValidationResult:
        """Validate a FundamentalsResult and return a ValidationResult.

        Args:
            current: The current period's fundamentals to validate.
            previous: The previous period's fundamentals for outlier comparison.
                      If None, outlier detection is skipped.

        Returns:
            ValidationResult with quality_score, missing_fields, outlier_flags,
            hitl_required, and hitl_reason.
        """
        # Step 1: missing fields
        missing_fields: list[str] = []
        for field in REQUIRED_FUNDAMENTAL_FIELDS:
            if field not in current or current.get(field) is None:  # type: ignore[literal-required]
                missing_fields.append(field)

        # Step 2: quality score
        total = len(REQUIRED_FUNDAMENTAL_FIELDS)
        quality_score = max(0.0, min(1.0, 1.0 - len(missing_fields) / total))

        # Step 3: outlier detection
        outlier_flags: dict[str, bool] = {}
        hitl_required = False
        hitl_reason = ""

        if previous is not None:
            for field in REQUIRED_FUNDAMENTAL_FIELDS:
                current_val = current.get(field)  # type: ignore[literal-required]
                previous_val = previous.get(field)  # type: ignore[literal-required]

                is_outlier, severity = self.validate_period_change(
                    field,
                    current_val if isinstance(current_val, (int, float)) else None,
                    previous_val if isinstance(previous_val, (int, float)) else None,
                )

                if severity == "hitl":
                    outlier_flags[field] = True
                    hitl_required = True
                    change_pct = abs((current_val - previous_val) / previous_val) * 100
                    hitl_reason = (
                        f"Field '{field}' changed by {change_pct:.1f}% "
                        f"(previous={previous_val}, current={current_val})"
                    )
                    log_audit_event(
                        self._database_url,
                        "data_validation",
                        "data_validator",
                        "hitl_trigger",
                        {
                            "field": field,
                            "change_pct": change_pct,
                            "ticker": current.get("ticker", "unknown"),  # type: ignore[typeddict-item]
                        },
                    )
                elif severity == "warning":
                    outlier_flags[field] = True

        result: ValidationResult = {
            "quality_score": quality_score,
            "missing_fields": missing_fields,
            "outlier_flags": outlier_flags,
            "hitl_required": hitl_required,
            "hitl_reason": hitl_reason,
        }
        return result

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_period_change(
        field: str,
        current_val: float | None,
        previous_val: float | None,
    ) -> tuple[bool, str]:
        """Compute whether a single field change qualifies as an outlier.

        Args:
            field: Field name (used only for context; not evaluated here).
            current_val: Current period value.
            previous_val: Previous period value.

        Returns:
            (is_outlier, severity) where severity is:
              ""        — not an outlier
              "warning" — 50–200% change
              "hitl"    — >200% change
        """
        if current_val is None or previous_val is None:
            return False, ""
        if previous_val == 0:
            return False, ""

        change_pct = abs((current_val - previous_val) / previous_val) * 100

        if change_pct > 200:
            return True, "hitl"
        if change_pct > 50:
            return True, "warning"
        return False, ""
