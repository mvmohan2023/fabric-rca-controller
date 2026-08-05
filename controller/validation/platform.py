"""Platform-domain engineering validation."""

from __future__ import annotations

from typing import Any, Dict, List

from controller.validation.models import ValidationResult


_HARD_PLATFORM_SIGNALS = {
    "interface_in_errors_detected",
    "interface_out_errors_detected",
    "hotspot_transport_instability",
    "hotspot_port_health_signal",
    "platform_core_detected",
    "daemon_crash_detected",
    "hardware_alarm_detected",
    "memory_health_failed",
    "cpu_health_failed",
    "optics_health_failed",
}

_WARNING_PLATFORM_SIGNALS = {
    "interface_ingress_discards_detected",
    "interface_egress_discards_detected",
    "cos_queue_without_explicit_scheduler",
    "cos_needs_manual_review",
}

_INFORMATIONAL_SIGNALS = {
    "cos_expected_ecn_pressure",
}


def evaluate_platform(
    *,
    evidence_rollup: Dict[str, Any],
    platform_health: Dict[str, Any] | None = None,
) -> ValidationResult:
    """Evaluate platform health from explicit platform evidence.

    Current campaign artifacts do not yet provide a complete platform
    health object. Therefore absence of platform evidence produces
    INCONCLUSIVE rather than a false PASS.

    Explicit hard signals always produce FAIL.
    Explicit warning signals produce WARN.
    Expected ECN pressure remains informational.
    """

    platform_health = dict(platform_health or {})

    bug_signals = set(
        evidence_rollup.get(
            "bug_candidate_signals",
            [],
        )
        or []
    )

    cos_health = dict(
        evidence_rollup.get("cos_health") or {}
    )
    cos_counts = dict(
        cos_health.get("counts") or {}
    )
    cos_summary = dict(
        cos_health.get("summary") or {}
    )

    hard_signals = sorted(
        bug_signals & _HARD_PLATFORM_SIGNALS
    )
    warning_signals = sorted(
        bug_signals & _WARNING_PLATFORM_SIGNALS
    )
    informational_signals = sorted(
        bug_signals & _INFORMATIONAL_SIGNALS
    )

    explicit_platform_status = str(
        platform_health.get("status") or ""
    ).strip().lower()

    core_count = int(
        platform_health.get("core_count")
        or platform_health.get("cores")
        or 0
    )
    daemon_crash_count = int(
        platform_health.get("daemon_crash_count")
        or platform_health.get("daemon_crashes")
        or 0
    )
    alarm_count = int(
        platform_health.get("unexpected_alarm_count")
        or platform_health.get("alarms")
        or 0
    )

    evidence = list(
        platform_health.get("evidence") or []
    )

    metrics = {
        "explicit_platform_status": (
            explicit_platform_status or None
        ),
        "core_count": core_count,
        "daemon_crash_count": daemon_crash_count,
        "unexpected_alarm_count": alarm_count,
        "hard_platform_signals": hard_signals,
        "warning_platform_signals": warning_signals,
        "informational_signals": informational_signals,
        "cos_counts": cos_counts,
        "cos_summary": cos_summary,
        "platform_health_available": bool(
            platform_health
        ),
    }

    failure_reasons: List[str] = []

    if explicit_platform_status in {
        "fail",
        "failed",
        "critical",
        "error",
    }:
        failure_reasons.append(
            f"Explicit platform health status was "
            f"{explicit_platform_status}."
        )

    if core_count > 0:
        failure_reasons.append(
            f"{core_count} unexpected core file(s) were detected."
        )

    if daemon_crash_count > 0:
        failure_reasons.append(
            f"{daemon_crash_count} daemon crash(es) were detected."
        )

    if alarm_count > 0:
        failure_reasons.append(
            f"{alarm_count} unexpected platform alarm(s) were detected."
        )

    if hard_signals:
        failure_reasons.append(
            "Hard platform-health signal(s) detected: "
            + ", ".join(hard_signals)
            + "."
        )

    if failure_reasons:
        return ValidationResult.fail_result(
            summary=(
                "Platform health failed during or after "
                "scenario execution."
            ),
            confidence=1.0,
            reasons=failure_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    warning_reasons: List[str] = []

    if explicit_platform_status in {
        "warn",
        "warning",
        "degraded",
        "partial",
    }:
        warning_reasons.append(
            f"Explicit platform health status was "
            f"{explicit_platform_status}."
        )

    if warning_signals:
        warning_reasons.append(
            "Platform warning signal(s) detected: "
            + ", ".join(warning_signals)
            + "."
        )

    if warning_reasons:
        return ValidationResult.warn_result(
            summary=(
                "Platform remained operational, but "
                "warning-level signals were present."
            ),
            ok=True,
            confidence=0.8,
            reasons=warning_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    if explicit_platform_status in {
        "pass",
        "passed",
        "ok",
        "healthy",
    }:
        reasons = [
            "Explicit platform-health evidence passed.",
            "No hard platform-health signals were detected.",
        ]

        if informational_signals:
            reasons.append(
                "Informational signal(s) were observed: "
                + ", ".join(informational_signals)
                + "."
            )

        return ValidationResult.pass_result(
            summary=(
                "Platform remained healthy through "
                "scenario execution and recovery."
            ),
            confidence=1.0,
            reasons=reasons,
            evidence=evidence,
            metrics=metrics,
        )

    return ValidationResult.inconclusive_result(
        summary=(
            "No complete platform-health evidence was available "
            "to confirm CPU, memory, process, alarm, core, or "
            "optics health."
        ),
        confidence=0.0,
        reasons=[
            "No explicit platform-health result was provided.",
            (
                "Available CoS and telemetry evidence does not "
                "constitute complete platform-health validation."
            ),
            *(
                [
                    "Only informational signal(s) were present: "
                    + ", ".join(informational_signals)
                    + "."
                ]
                if informational_signals
                else []
            ),
        ],
        evidence=evidence,
        metrics=metrics,
    )
