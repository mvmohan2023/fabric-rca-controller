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

        event = self._pending_result("event")
        impact = self._pending_result("impact")
        recovery = self._pending_result("recovery")
        traffic = self._pending_result("traffic")
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
                "Engineering validation contract initialized; "
                "domain evaluators are pending."
            ),
        )
