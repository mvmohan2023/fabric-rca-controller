"""Normalized engineering-validation result models.

These models are additive and do not replace existing campaign,
stress, RCA, UI, or validation result fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


VALIDATION_STATUSES = {
    "PASS",
    "FAIL",
    "WARN",
    "INCONCLUSIVE",
    "NOT_APPLICABLE",
}


@dataclass
class ValidationResult:
    """Result produced by one engineering validation domain."""

    status: str
    ok: Optional[bool]
    confidence: float
    summary: str
    reasons: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_status = str(self.status or "").strip().upper()

        if normalized_status not in VALIDATION_STATUSES:
            raise ValueError(
                f"Unsupported validation status: {self.status!r}. "
                f"Expected one of {sorted(VALIDATION_STATUSES)}"
            )

        self.status = normalized_status

        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Validation confidence must be numeric: "
                f"{self.confidence!r}"
            ) from exc

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Validation confidence must be between 0.0 and 1.0"
            )

        if self.status == "PASS" and self.ok is not True:
            raise ValueError(
                "PASS validation result must have ok=True"
            )

        if self.status == "FAIL" and self.ok is not False:
            raise ValueError(
                "FAIL validation result must have ok=False"
            )

        if self.status in {"INCONCLUSIVE", "NOT_APPLICABLE"}:
            if self.ok is not None:
                raise ValueError(
                    f"{self.status} validation result must have ok=None"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)

    @classmethod
    def pass_result(
        cls,
        *,
        summary: str,
        confidence: float = 1.0,
        reasons: Optional[List[str]] = None,
        evidence: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> "ValidationResult":
        return cls(
            status="PASS",
            ok=True,
            confidence=confidence,
            summary=summary,
            reasons=list(reasons or []),
            evidence=list(evidence or []),
            metrics=dict(metrics or {}),
        )

    @classmethod
    def fail_result(
        cls,
        *,
        summary: str,
        confidence: float = 1.0,
        reasons: Optional[List[str]] = None,
        evidence: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> "ValidationResult":
        return cls(
            status="FAIL",
            ok=False,
            confidence=confidence,
            summary=summary,
            reasons=list(reasons or []),
            evidence=list(evidence or []),
            metrics=dict(metrics or {}),
        )

    @classmethod
    def warn_result(
        cls,
        *,
        summary: str,
        ok: Optional[bool] = True,
        confidence: float = 0.75,
        reasons: Optional[List[str]] = None,
        evidence: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> "ValidationResult":
        return cls(
            status="WARN",
            ok=ok,
            confidence=confidence,
            summary=summary,
            reasons=list(reasons or []),
            evidence=list(evidence or []),
            metrics=dict(metrics or {}),
        )

    @classmethod
    def inconclusive_result(
        cls,
        *,
        summary: str,
        confidence: float = 0.0,
        reasons: Optional[List[str]] = None,
        evidence: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> "ValidationResult":
        return cls(
            status="INCONCLUSIVE",
            ok=None,
            confidence=confidence,
            summary=summary,
            reasons=list(reasons or []),
            evidence=list(evidence or []),
            metrics=dict(metrics or {}),
        )

    @classmethod
    def not_applicable_result(
        cls,
        *,
        summary: str,
        reasons: Optional[List[str]] = None,
    ) -> "ValidationResult":
        return cls(
            status="NOT_APPLICABLE",
            ok=None,
            confidence=1.0,
            summary=summary,
            reasons=list(reasons or []),
        )


@dataclass
class EngineeringValidationResult:
    """Normalized validation result for one complete scenario."""

    event: ValidationResult
    impact: ValidationResult
    recovery: ValidationResult
    traffic: ValidationResult
    telemetry: ValidationResult
    platform: ValidationResult
    overall_status: str
    overall_confidence: float
    summary: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        normalized_status = str(
            self.overall_status or ""
        ).strip().upper()

        if normalized_status not in VALIDATION_STATUSES:
            raise ValueError(
                f"Unsupported overall validation status: "
                f"{self.overall_status!r}"
            )

        self.overall_status = normalized_status

        try:
            self.overall_confidence = float(
                self.overall_confidence
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Overall validation confidence must be numeric"
            ) from exc

        if not 0.0 <= self.overall_confidence <= 1.0:
            raise ValueError(
                "Overall validation confidence must be "
                "between 0.0 and 1.0"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Return a stable JSON-compatible schema."""

        return {
            "schema_version": self.schema_version,
            "overall_status": self.overall_status,
            "overall_confidence": self.overall_confidence,
            "summary": self.summary,
            "event": self.event.to_dict(),
            "impact": self.impact.to_dict(),
            "recovery": self.recovery.to_dict(),
            "traffic": self.traffic.to_dict(),
            "telemetry": self.telemetry.to_dict(),
            "platform": self.platform.to_dict(),
        }
