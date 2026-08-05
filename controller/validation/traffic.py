"""Traffic-domain engineering validation."""

from __future__ import annotations

from typing import Any, Dict, List

from controller.validation.models import ValidationResult


_FAILURE_VERDICTS = {
    "fail",
    "failed",
    "error",
    "critical",
}

_WARNING_VERDICTS = {
    "warning",
    "warn",
    "degraded",
    "partial",
}

_PASS_VERDICTS = {
    "pass",
    "passed",
    "ok",
    "healthy",
}


def _normalize_verdict(value: Any) -> str:
    return str(value or "").strip().lower()


def evaluate_traffic(
    *,
    evidence_rollup: Dict[str, Any],
    ui_validation: Dict[str, Any],
    traffic_required: bool | None = None,
) -> ValidationResult:
    """Evaluate traffic health from available traffic evidence.

    Evidence precedence:
    1. Confirmed failure or critical alert -> FAIL
    2. Warning verdict or noncritical alert -> WARN
    3. At least one passing source and no failed source -> PASS
    4. Required traffic with no evidence -> INCONCLUSIVE
    5. Optional traffic with no evidence -> NOT_APPLICABLE
    """

    traffic_verdict = _normalize_verdict(
        evidence_rollup.get("traffic_verdict")
    )
    rocev2_verdict = _normalize_verdict(
        evidence_rollup.get("rocev2_verdict")
    )

    live_alerts = int(
        evidence_rollup.get("live_alerts") or 0
    )
    critical_live_alerts = int(
        evidence_rollup.get("critical_live_alerts") or 0
    )

    traffic_summary = dict(
        evidence_rollup.get("traffic_summary") or {}
    )
    rocev2_summary = dict(
        evidence_rollup.get("rocev2_summary") or {}
    )

    ui_traffic_health = dict(
        ui_validation.get("traffic_health") or {}
    )

    evidence_status = dict(
        evidence_rollup.get("status") or {}
    )

    available_sources: List[str] = []

    if traffic_verdict:
        available_sources.append("traffic_verifier")

    if rocev2_verdict:
        available_sources.append("rocev2_verdict")

    if (
        evidence_status.get("ixia_live_monitor") == "ok"
        or live_alerts > 0
        or critical_live_alerts > 0
    ):
        available_sources.append("ixia_live_monitor")

    evidence = [
        value
        for value in (
            ui_validation.get("path"),
        )
        if value
    ]

    metrics = {
        "traffic_verdict": traffic_verdict or None,
        "rocev2_verdict": rocev2_verdict or None,
        "live_alerts": live_alerts,
        "critical_live_alerts": critical_live_alerts,
        "available_sources": available_sources,
        "traffic_summary": traffic_summary,
        "rocev2_summary": rocev2_summary,
        "ui_traffic_health_available": bool(
            ui_traffic_health
        ),
        "traffic_verifier_status": evidence_status.get(
            "traffic_verifier"
        ),
        "rocev2_evidence_status": evidence_status.get(
            "rocev2_verdict"
        ),
    }

    failure_reasons: List[str] = []

    if traffic_verdict in _FAILURE_VERDICTS:
        failure_reasons.append(
            f"Traffic verifier returned {traffic_verdict}."
        )

    if rocev2_verdict in _FAILURE_VERDICTS:
        failure_reasons.append(
            f"RoCEv2 validation returned {rocev2_verdict}."
        )

    if critical_live_alerts > 0:
        failure_reasons.append(
            (
                f"IXIA live monitoring reported "
                f"{critical_live_alerts} critical alert(s)."
            )
        )

    if failure_reasons:
        return ValidationResult.fail_result(
            summary=(
                "Traffic did not remain healthy or recover "
                "within the validation window."
            ),
            confidence=1.0,
            reasons=failure_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    warning_reasons: List[str] = []

    if traffic_verdict in _WARNING_VERDICTS:
        warning_reasons.append(
            f"Traffic verifier returned {traffic_verdict}."
        )

    if rocev2_verdict in _WARNING_VERDICTS:
        warning_reasons.append(
            f"RoCEv2 validation returned {rocev2_verdict}."
        )

    if live_alerts > 0:
        warning_reasons.append(
            (
                f"IXIA live monitoring reported "
                f"{live_alerts} noncritical alert(s)."
            )
        )

    if warning_reasons:
        return ValidationResult.warn_result(
            summary=(
                "Traffic recovered with warnings or residual "
                "traffic-health signals."
            ),
            ok=True,
            confidence=0.8,
            reasons=warning_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    passing_sources: List[str] = []

    if traffic_verdict in _PASS_VERDICTS:
        passing_sources.append("traffic_verifier")

    if rocev2_verdict in _PASS_VERDICTS:
        passing_sources.append("rocev2_verdict")

    if passing_sources:
        return ValidationResult.pass_result(
            summary=(
                "Available traffic evidence passed during "
                "the recovery window."
            ),
            confidence=1.0,
            reasons=[
                (
                    "Passing traffic evidence source(s): "
                    + ", ".join(passing_sources)
                    + "."
                ),
                "No traffic failure or critical alert was detected.",
            ],
            evidence=evidence,
            metrics=metrics,
        )

    if traffic_required is True:
        return ValidationResult.inconclusive_result(
            summary=(
                "Traffic validation was required, but no usable "
                "traffic verdict was available."
            ),
            confidence=0.0,
            reasons=[
                "Neither generic traffic nor RoCEv2 evidence produced a verdict."
            ],
            evidence=evidence,
            metrics=metrics,
        )

    return ValidationResult.not_applicable_result(
        summary=(
            "No usable traffic evidence was present and traffic "
            "validation was not explicitly required."
        ),
        reasons=[
            "Traffic verifier and RoCEv2 verdicts were unavailable."
        ],
    )
