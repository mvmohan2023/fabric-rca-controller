"""Engineering validation result builder."""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, Iterable, Set

from controller.validation.event import evaluate_event
from controller.validation.impact import evaluate_impact
from controller.validation.models import (
    EngineeringValidationResult,
    ValidationResult,
)
from controller.validation.platform import evaluate_platform
from controller.validation.recovery import evaluate_recovery
from controller.validation.telemetry import evaluate_telemetry
from controller.validation.traffic import evaluate_traffic


class EngineeringValidationBuilder:
    """Build one normalized engineering-validation result.

    Validators receive already-loaded evidence and do not read artifacts
    directly. Existing campaign classification remains unchanged.
    """

    _DOMAIN_ORDER = (
        "event",
        "impact",
        "recovery",
        "traffic",
        "telemetry",
        "platform",
    )

    _DEFAULT_REQUIRED_DOMAINS = {
        "event",
        "impact",
        "recovery",
        "telemetry",
    }

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
        platform_health: Dict[str, Any] | None = None,
        required_domains: Iterable[str] | None = None,
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
        self.platform_health = dict(
            platform_health or {}
        )

        if required_domains is None:
            resolved_required_domains = set(
                self._DEFAULT_REQUIRED_DOMAINS
            )
        else:
            resolved_required_domains = {
                str(domain).strip().lower()
                for domain in required_domains
                if str(domain).strip()
            }

        if traffic_required is True:
            resolved_required_domains.add("traffic")

        if self.platform_health:
            resolved_required_domains.add("platform")

        unknown_domains = (
            resolved_required_domains
            - set(self._DOMAIN_ORDER)
        )

        if unknown_domains:
            raise ValueError(
                "Unsupported required validation domain(s): "
                + ", ".join(sorted(unknown_domains))
            )

        self.required_domains: Set[str] = (
            resolved_required_domains
        )

    @staticmethod
    def _domain_map(
        *,
        event: ValidationResult,
        impact: ValidationResult,
        recovery: ValidationResult,
        traffic: ValidationResult,
        telemetry: ValidationResult,
        platform: ValidationResult,
    ) -> Dict[str, ValidationResult]:
        return {
            "event": event,
            "impact": impact,
            "recovery": recovery,
            "traffic": traffic,
            "telemetry": telemetry,
            "platform": platform,
        }

    def _derive_overall(
        self,
        domains: Dict[str, ValidationResult],
    ) -> tuple[str, float, str]:
        """Derive the additive EVL overall verdict.

        Explicit domain failures always fail the overall verdict, even if the
        domain is optional. Optional inconclusive results do not block PASS,
        but reduce confidence.
        """

        failed_domains = [
            name
            for name in self._DOMAIN_ORDER
            if domains[name].status == "FAIL"
        ]

        warning_domains = [
            name
            for name in self._DOMAIN_ORDER
            if domains[name].status == "WARN"
        ]

        required_inconclusive = [
            name
            for name in self._DOMAIN_ORDER
            if (
                name in self.required_domains
                and domains[name].status
                in {
                    "INCONCLUSIVE",
                    "NOT_APPLICABLE",
                }
            )
        ]

        optional_inconclusive = [
            name
            for name in self._DOMAIN_ORDER
            if (
                name not in self.required_domains
                and domains[name].status
                == "INCONCLUSIVE"
            )
        ]

        decisive_results = [
            result
            for result in domains.values()
            if result.status
            in {
                "PASS",
                "WARN",
                "FAIL",
            }
        ]

        if decisive_results:
            base_confidence = mean(
                result.confidence
                for result in decisive_results
            )
        else:
            base_confidence = 0.0

        # Optional missing evidence lowers confidence but does not block PASS.
        confidence_penalty = (
            0.05 * len(optional_inconclusive)
        )

        overall_confidence = round(
            max(
                0.0,
                min(
                    1.0,
                    base_confidence
                    - confidence_penalty,
                ),
            ),
            3,
        )

        if failed_domains:
            return (
                "FAIL",
                overall_confidence,
                (
                    "Engineering validation failed in: "
                    + ", ".join(failed_domains)
                    + "."
                ),
            )

        if required_inconclusive:
            return (
                "INCONCLUSIVE",
                overall_confidence,
                (
                    "Engineering validation is inconclusive because "
                    "required evidence is incomplete for: "
                    + ", ".join(required_inconclusive)
                    + "."
                ),
            )

        if warning_domains:
            summary = (
                "Engineering validation completed with warnings in: "
                + ", ".join(warning_domains)
                + "."
            )

            if optional_inconclusive:
                summary += (
                    " Optional evidence is incomplete for: "
                    + ", ".join(optional_inconclusive)
                    + "."
                )

            return (
                "WARN",
                overall_confidence,
                summary,
            )

        required_not_passed = [
            name
            for name in self.required_domains
            if domains[name].status != "PASS"
        ]

        if required_not_passed:
            return (
                "INCONCLUSIVE",
                overall_confidence,
                (
                    "Not all required engineering validation "
                    "domains produced PASS."
                ),
            )

        summary = (
            "All required engineering validation domains passed."
        )

        if optional_inconclusive:
            summary += (
                " Optional evidence is incomplete for: "
                + ", ".join(optional_inconclusive)
                + "."
            )

        return (
            "PASS",
            overall_confidence,
            summary,
        )

    def build(self) -> EngineeringValidationResult:
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

        telemetry = evaluate_telemetry(
            evidence_rollup=self.evidence_rollup,
            phase_timeline=self.phase_timeline,
            post_sample_health=self.post_sample_health,
        )

        platform = evaluate_platform(
            evidence_rollup=self.evidence_rollup,
            platform_health=self.platform_health,
        )

        domains = self._domain_map(
            event=event,
            impact=impact,
            recovery=recovery,
            traffic=traffic,
            telemetry=telemetry,
            platform=platform,
        )

        (
            overall_status,
            overall_confidence,
            summary,
        ) = self._derive_overall(domains)

        return EngineeringValidationResult(
            event=event,
            impact=impact,
            recovery=recovery,
            traffic=traffic,
            telemetry=telemetry,
            platform=platform,
            overall_status=overall_status,
            overall_confidence=overall_confidence,
            summary=summary,
        )
