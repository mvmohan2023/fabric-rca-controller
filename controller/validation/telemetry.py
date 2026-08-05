"""Telemetry-domain engineering validation."""

from __future__ import annotations

from typing import Any, Dict, List

from controller.validation.models import ValidationResult


_REQUIRED_STAGES = (
    "pre_snapshot",
    "running_snapshot",
    "post_snapshot",
    "telemetry_diff",
    "telemetry_analyzer",
)


def evaluate_telemetry(
    *,
    evidence_rollup: Dict[str, Any],
    phase_timeline: Dict[str, Any],
    post_sample_health: List[Dict[str, Any]] | None = None,
) -> ValidationResult:
    """Evaluate telemetry collection continuity and health.

    Telemetry anomalies are interpreted using the same event-aware
    gating already used by build_evidence_rollup(). Background or
    static anomalies do not fail validation when no event-time
    congestion was detected.

    Missing required telemetry evidence is INCONCLUSIVE.
    Confirmed collection failure is FAIL.
    """

    post_sample_health = list(post_sample_health or [])

    evidence_status = dict(
        evidence_rollup.get("status") or {}
    )
    telemetry_health = dict(
        evidence_rollup.get("telemetry_health") or {}
    )
    anomaly_summary = dict(
        telemetry_health.get("anomaly_summary") or {}
    )
    diff_summary = dict(
        telemetry_health.get("diff_summary") or {}
    )

    severity = dict(
        anomaly_summary.get("by_severity") or {}
    )

    critical_count = int(severity.get("critical") or 0)
    warning_count = int(severity.get("warning") or 0)
    info_count = int(severity.get("info") or 0)
    total_anomalies = int(
        anomaly_summary.get("total") or 0
    )
    total_differences = int(
        diff_summary.get("total_differences") or 0
    )

    event_congestion = bool(
        telemetry_health.get(
            "event_congestion_detected",
            False,
        )
    )

    post_sample_paths = list(
        phase_timeline.get("post_sample_paths") or []
    )
    post_telemetry = (
        phase_timeline.get("post_telemetry") or ""
    )

    failed_post_samples = 0
    total_failed_nodes = 0
    total_ok_nodes = 0

    for sample in post_sample_health:
        failed_nodes = sample.get("failed_nodes", [])
        ok_nodes = sample.get("ok_nodes", [])

        if isinstance(failed_nodes, list):
            failed_count = len(failed_nodes)
        else:
            try:
                failed_count = int(failed_nodes or 0)
            except (TypeError, ValueError):
                failed_count = 0

        if isinstance(ok_nodes, list):
            ok_count = len(ok_nodes)
        else:
            try:
                ok_count = int(ok_nodes or 0)
            except (TypeError, ValueError):
                ok_count = 0

        total_failed_nodes += failed_count
        total_ok_nodes += ok_count

        if failed_count > 0:
            failed_post_samples += 1

    stage_results = {
        stage: evidence_status.get(stage)
        for stage in _REQUIRED_STAGES
    }

    failed_stages = [
        stage
        for stage, status in stage_results.items()
        if str(status or "").lower() == "failed"
    ]

    missing_stages = [
        stage
        for stage, status in stage_results.items()
        if str(status or "").lower()
        not in {"ok", "failed"}
    ]

    evidence = [
        value
        for value in (
            post_telemetry,
            *post_sample_paths,
        )
        if value
    ]

    metrics = {
        "required_stage_status": stage_results,
        "failed_stages": failed_stages,
        "missing_stages": missing_stages,
        "total_anomalies": total_anomalies,
        "critical_anomalies": critical_count,
        "warning_anomalies": warning_count,
        "info_anomalies": info_count,
        "total_differences": total_differences,
        "event_congestion_detected": event_congestion,
        "post_sample_count": len(post_sample_paths),
        "post_sample_health_count": len(
            post_sample_health
        ),
        "failed_post_samples": failed_post_samples,
        "total_failed_nodes": total_failed_nodes,
        "total_ok_nodes": total_ok_nodes,
    }

    failure_reasons: List[str] = []

    if failed_stages:
        failure_reasons.append(
            "Required telemetry stage(s) failed: "
            + ", ".join(failed_stages)
            + "."
        )

    if failed_post_samples > 0:
        failure_reasons.append(
            "One or more post-window telemetry samples "
            "reported failed nodes."
        )

    if critical_count > 0 and event_congestion:
        failure_reasons.append(
            f"{critical_count} critical telemetry anomaly/anomalies "
            "were correlated with event-time congestion."
        )

    if failure_reasons:
        return ValidationResult.fail_result(
            summary=(
                "Telemetry collection or event-correlated "
                "telemetry health failed."
            ),
            confidence=1.0,
            reasons=failure_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    missing_reasons: List[str] = []

    if missing_stages:
        missing_reasons.append(
            "Required telemetry stage status is unavailable: "
            + ", ".join(missing_stages)
            + "."
        )

    if not post_sample_paths:
        missing_reasons.append(
            "No post-window telemetry sample paths were recorded."
        )

    if not post_sample_health:
        missing_reasons.append(
            "Post-window telemetry sample health is unavailable."
        )

    if missing_reasons:
        return ValidationResult.inconclusive_result(
            summary=(
                "Telemetry health could not be conclusively "
                "validated because required evidence is incomplete."
            ),
            confidence=0.0,
            reasons=missing_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    warning_reasons: List[str] = []

    if warning_count > 0 and event_congestion:
        warning_reasons.append(
            f"{warning_count} warning telemetry anomaly/anomalies "
            "were correlated with event-time congestion."
        )

    if total_differences > 0 and event_congestion:
        warning_reasons.append(
            f"{total_differences} telemetry difference(s) "
            "were correlated with the event."
        )

    if warning_reasons:
        return ValidationResult.warn_result(
            summary=(
                "Telemetry collection completed, but "
                "event-correlated warning signals were present."
            ),
            ok=True,
            confidence=0.8,
            reasons=warning_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    reasons = [
        "All required telemetry stages completed successfully.",
        (
            f"{len(post_sample_health)} post-window telemetry "
            "sample(s) completed without failed nodes."
        ),
    ]

    if total_anomalies > 0 and not event_congestion:
        reasons.append(
            "Observed telemetry anomalies were not correlated "
            "with event-time congestion and remain informational."
        )

    if total_differences > 0 and not event_congestion:
        reasons.append(
            "Telemetry differences were not promoted because "
            "no event-time congestion was detected."
        )

    return ValidationResult.pass_result(
        summary=(
            "Telemetry collection remained healthy through "
            "the event and recovery windows."
        ),
        confidence=1.0,
        reasons=reasons,
        evidence=evidence,
        metrics=metrics,
    )
