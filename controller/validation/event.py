"""Event-domain engineering validation."""

from __future__ import annotations

from typing import Any, Dict

from controller.validation.models import ValidationResult


def evaluate_event(
    *,
    stress_validation: Dict[str, Any],
    rca_validation: Dict[str, Any],
    ui_validation: Dict[str, Any],
) -> ValidationResult:
    """Evaluate whether the requested event executed and reached reporting.

    This intentionally preserves the existing production definition used by
    classify_scenario_result():

    event_ok means the event was linked into RCA, rendered in the UI report,
    and represented by at least one event record.

    It is not derived solely from stress_validation["ok"], because some valid
    actions may execute successfully even when the broader stress-report gate
    reports a false negative.
    """

    rca_ok = bool(rca_validation.get("ok", False))
    ui_ok = bool(ui_validation.get("ok", False))
    event_count = int(ui_validation.get("event_count", 0) or 0)

    evidence = [
        path
        for path in (
            stress_validation.get("path"),
            rca_validation.get("path"),
            ui_validation.get("path"),
        )
        if path
    ]

    metrics = {
        "stress_report_ok": bool(
            stress_validation.get("ok", False)
        ),
        "rca_report_ok": rca_ok,
        "ui_report_ok": ui_ok,
        "event_count": event_count,
        "top_event_name": (
            ui_validation.get("top_event_name") or ""
        ),
    }

    event_ok = (
        rca_ok
        and ui_ok
        and event_count > 0
    )

    if event_ok:
        return ValidationResult.pass_result(
            summary=(
                "The requested event executed and was represented "
                "in the RCA/UI report."
            ),
            confidence=1.0,
            reasons=[
                "RCA report is linked to the stress execution.",
                "UI report validation passed.",
                f"UI report contains {event_count} event record(s).",
            ],
            evidence=evidence,
            metrics=metrics,
        )

    missing_evidence = (
        not rca_validation
        or not ui_validation
        or not rca_validation.get("path")
        or not ui_validation.get("path")
    )

    if missing_evidence:
        reasons = []

        if not rca_validation.get("path"):
            reasons.append(
                "RCA validation evidence path is unavailable."
            )

        if not ui_validation.get("path"):
            reasons.append(
                "UI validation evidence path is unavailable."
            )

        if not reasons:
            reasons.append(
                "Required event-validation evidence is incomplete."
            )

        return ValidationResult.inconclusive_result(
            summary=(
                "Event execution could not be conclusively "
                "validated because required report evidence "
                "is missing."
            ),
            confidence=0.0,
            reasons=reasons,
            evidence=evidence,
            metrics=metrics,
        )

    reasons = []

    if not rca_ok:
        reasons.append(
            "RCA report is not correctly linked to the stress report."
        )

    if not ui_ok:
        reasons.append(
            "UI report validation did not pass."
        )

    if event_count <= 0:
        reasons.append(
            "No event records were present in the UI report."
        )

    return ValidationResult.fail_result(
        summary=(
            "The requested event was not successfully represented "
            "through the complete RCA/UI reporting path."
        ),
        confidence=1.0,
        reasons=reasons,
        evidence=evidence,
        metrics=metrics,
    )
