"""Impact-domain engineering validation."""

from __future__ import annotations

from typing import Any, Dict

from controller.validation.models import ValidationResult


def evaluate_impact(
    *,
    ui_validation: Dict[str, Any],
    evidence_rollup: Dict[str, Any],
) -> ValidationResult:
    """Evaluate whether the expected observable impact was detected.

    This preserves the current production definition used by
    classify_scenario_result():

    impact_ok requires at least one hotspot and a known primary cause.
    """

    total_hotspots = ui_validation.get(
        "total_hotspots",
        0,
    )

    primary_cause = ui_validation.get(
        "primary_cause",
        "unknown",
    )

    hotspot_present = total_hotspots not in (
        None,
        0,
    )

    known_primary_cause = primary_cause not in (
        None,
        "",
        "unknown",
    )

    impact_ok = (
        hotspot_present
        and known_primary_cause
    )

    bug_signals = list(
        evidence_rollup.get(
            "bug_candidate_signals",
            [],
        )
        or []
    )

    telemetry_health = (
        evidence_rollup.get("telemetry_health")
        or {}
    )

    event_congestion = bool(
        telemetry_health.get(
            "event_congestion_detected",
            False,
        )
    )

    evidence = [
        path
        for path in (
            ui_validation.get("path"),
        )
        if path
    ]

    metrics = {
        "total_hotspots": total_hotspots,
        "primary_cause": primary_cause,
        "event_congestion_detected": event_congestion,
        "bug_candidate_signal_count": len(
            bug_signals
        ),
        "bug_candidate_signals": bug_signals,
    }

    if impact_ok:
        reasons = [
            f"Detected {total_hotspots} hotspot(s).",
            f"Primary cause was identified as {primary_cause}.",
        ]

        if event_congestion:
            reasons.append(
                "Event-time congestion was detected."
            )

        return ValidationResult.pass_result(
            summary=(
                "The expected event impact was observed and "
                "correlated to a known primary cause."
            ),
            confidence=1.0,
            reasons=reasons,
            evidence=evidence,
            metrics=metrics,
        )

    missing_evidence = (
        not ui_validation
        or not ui_validation.get("path")
    )

    if missing_evidence:
        return ValidationResult.inconclusive_result(
            summary=(
                "Impact could not be conclusively evaluated "
                "because UI validation evidence is unavailable."
            ),
            confidence=0.0,
            reasons=[
                "UI validation evidence path is unavailable."
            ],
            evidence=evidence,
            metrics=metrics,
        )

    reasons = []

    if not hotspot_present:
        reasons.append(
            "No hotspot was detected in the UI report."
        )

    if not known_primary_cause:
        reasons.append(
            "Primary cause is missing or unknown."
        )

    return ValidationResult.fail_result(
        summary=(
            "The expected observable impact was not completely "
            "confirmed by the RCA/UI evidence."
        ),
        confidence=1.0,
        reasons=reasons,
        evidence=evidence,
        metrics=metrics,
    )
