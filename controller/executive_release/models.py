"""Executive Release Qualification result models.

The architecture defines release-health concepts, risk bands, confidence,
recommendations, and blocking conditions, but does not prescribe one exact
numerical aggregation formula.

The initial evaluator therefore exposes its policy version explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


RELEASE_STATUSES = {
    "READY",
    "READY_WITH_RISK",
    "NOT_READY",
    "BLOCKED",
    "INCONCLUSIVE",
}

RISK_LEVELS = {
    "VERY_LOW",
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
}

RECOMMENDATIONS = {
    "READY FOR PRODUCTION",
    "READY WITH LOW RISK",
    "READY WITH MEDIUM RISK",
    "NOT READY",
    "BLOCK RELEASE",
}


@dataclass
class ExecutiveReleaseResult:
    """Normalized executive release qualification result."""

    release_id: str
    suite_id: str

    release_status: str
    release_health: float

    confidence: float

    risk_score: float
    risk_level: str

    recommendation: str

    blocking_conditions: List[Dict[str, Any]] = field(
        default_factory=list
    )
    warning_conditions: List[Dict[str, Any]] = field(
        default_factory=list
    )
    inconclusive_conditions: List[Dict[str, Any]] = field(
        default_factory=list
    )

    feature_health: Dict[str, Any] = field(
        default_factory=dict
    )
    coverage: Dict[str, Any] = field(
        default_factory=dict
    )
    top_findings: List[str] = field(
        default_factory=list
    )
    traceability: Dict[str, Any] = field(
        default_factory=dict
    )

    missing_inputs: List[str] = field(
        default_factory=list
    )

    policy_version: str = "v1-provisional"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        self.release_id = str(
            self.release_id or ""
        ).strip()

        self.suite_id = str(
            self.suite_id or ""
        ).strip()

        if not self.release_id:
            raise ValueError(
                "release_id must be non-empty"
            )

        if not self.suite_id:
            raise ValueError(
                "suite_id must be non-empty"
            )

        self.release_status = str(
            self.release_status or ""
        ).strip().upper()

        if self.release_status not in RELEASE_STATUSES:
            raise ValueError(
                "Unsupported release_status: "
                f"{self.release_status!r}"
            )

        self.risk_level = str(
            self.risk_level or ""
        ).strip().upper()

        if self.risk_level not in RISK_LEVELS:
            raise ValueError(
                "Unsupported risk_level: "
                f"{self.risk_level!r}"
            )

        self.recommendation = str(
            self.recommendation or ""
        ).strip().upper()

        if self.recommendation not in RECOMMENDATIONS:
            raise ValueError(
                "Unsupported recommendation: "
                f"{self.recommendation!r}"
            )

        for field_name in (
            "release_health",
            "risk_score",
        ):
            value = float(
                getattr(self, field_name)
            )

            if not 0.0 <= value <= 100.0:
                raise ValueError(
                    f"{field_name} must be "
                    "between 0 and 100"
                )

            setattr(
                self,
                field_name,
                round(value, 2),
            )

        self.confidence = float(
            self.confidence
        )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be between "
                "0.0 and 1.0"
            )

        self.confidence = round(
            self.confidence,
            3,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
