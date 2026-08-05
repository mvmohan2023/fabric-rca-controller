"""Engineering validation result builder.

Commit 1 provides the stable orchestration contract only.
Domain-specific evaluation will be implemented incrementally.
"""

from __future__ import annotations

from typing import Any, Dict

from controller.validation.models import (
    EngineeringValidationResult,
    ValidationResult,
)

from controller.validation.event import evaluate_event
from controller.validation.impact import evaluate_impact
from controller.validation.recovery import evaluate_recovery
from controller.validation.traffic import evaluate_traffic

class EngineeringValidationBuilder:
    """Build a normalized engineering-validation result.

    Validators receive already-loaded evidence. They do not read files
    directly and do not modify existing campaign classification behavior.
    """

    def __init__(
        self,
        *,
        stress_validation: Dict[str, Any],
        rca_validation: Dict[str, Any],
        ui_validation: Dict[str, Any],
        evidence_rollup: Dict[str, Any],
        phase_timeline: Dict[str, Any] | None = None,
        scenario: Dict[str, Any] | None = None,
        post_sample_health: list[Dict[str, Any]] | None = None,
        traffic_required: bool | None = None,
    ) -> None:
        self.stress_validation = dict(
            stress_validation or {}
        )
        self.rca_validation = dict(
            rca_validation or {}
        )
        self.ui_validation = dict(
            ui_validation or {}
        )
        self.evidence_rollup = dict(
            evidence_rollup or {}
        )
        self.phase_timeline = dict(
            phase_timeline or {}
        )
        self.scenario = dict(
            scenario or {}
        )
        self.post_sample_health = list(
            post_sample_health or []
        )
        self.traffic_required = traffic_required

    @staticmethod
    def _pending_result(domain: str) -> ValidationResult:
        return ValidationResult.inconclusive_result(
            summary=(
                f"{domain.capitalize()} validation has not "
                "yet been evaluated."
            ),
            reasons=[
                "Domain evaluator is pending implementation."
            ],
        )

    def build(self) -> EngineeringValidationResult:
        """Return the initial additive EVL contract.

        Commit 1 deliberately reports all domains as INCONCLUSIVE.
        Later commits replace each placeholder with evidence-driven
        evaluators.
        """

        event = evaluate_event(
            stress_validation=self.stress_validation,
            rca_validation=self.rca_validation,
            ui_validation=self.ui_validation,
        )

        impact = evaluate_impact(
            ui_validation=self.ui_validation,
            evidence_rollup=self.evidence_rollup,
        )
        recovery = evaluate_recovery(
            stress_validation=self.stress_validation,
            evidence_rollup=self.evidence_rollup,
            phase_timeline=self.phase_timeline,
            post_sample_health=self.post_sample_health,
        )

        traffic = evaluate_traffic(
            evidence_rollup=self.evidence_rollup,
            ui_validation=self.ui_validation,
            traffic_required=self.traffic_required,
        )
        telemetry = self._pending_result("telemetry")
        platform = self._pending_result("platform")

        return EngineeringValidationResult(
            event=event,
            impact=impact,
            recovery=recovery,
            traffic=traffic,
            telemetry=telemetry,
            platform=platform,
            overall_status="INCONCLUSIVE",
            overall_confidence=0.0,
            summary=(
                "Event, impact, recovery, and traffic validation completed; "
                "telemetry and platform evaluators are pending."
            ),
        )
