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

def _evaluate_stream_telemetry(
    *,
    stream_health: Dict[str, Any],
    strict_telemetry: bool,
) -> ValidationResult:
    """Evaluate bounded gNMI streaming subscription health."""

    if not stream_health:
        return ValidationResult.inconclusive_result(
            summary=(
                "gNMI streaming telemetry health could not be "
                "validated because stream evidence is unavailable."
            ),
            confidence=0.0,
            reasons=[
                "gNMI stream health evidence was not provided."
            ],
            evidence=[],
            metrics={},
        )

    status = str(
        stream_health.get("status") or ""
    ).strip().lower()

    nodes_total = int(
        stream_health.get("nodes_total") or 0
    )
    nodes_passed = int(
        stream_health.get("nodes_passed") or 0
    )
    nodes_failed = int(
        stream_health.get("nodes_failed") or 0
    )

    subscriptions_total = int(
        stream_health.get("subscriptions_total") or 0
    )
    subscriptions_passed = int(
        stream_health.get("subscriptions_passed") or 0
    )
    subscriptions_failed = int(
        stream_health.get("subscriptions_failed") or 0
    )

    update_count = int(
        stream_health.get("update_count") or 0
    )
    unexpected_disconnects = int(
        stream_health.get("unexpected_disconnects") or 0
    )

    metrics = {
        "validation_mode": "stream",
        "stream_status": status,
        "nodes_total": nodes_total,
        "nodes_passed": nodes_passed,
        "nodes_failed": nodes_failed,
        "subscriptions_total": subscriptions_total,
        "subscriptions_passed": subscriptions_passed,
        "subscriptions_failed": subscriptions_failed,
        "update_count": update_count,
        "unexpected_disconnects": unexpected_disconnects,
        "strict_telemetry": strict_telemetry,
    }

    evidence = []

    stream_path = (
        stream_health.get("artifact_path")
        or stream_health.get("path")
    )

    if stream_path:
        evidence.append(str(stream_path))

    missing_reasons: List[str] = []

    if not status:
        missing_reasons.append(
            "Stream health status is unavailable."
        )

    if nodes_total <= 0:
        missing_reasons.append(
            "No nodes were evaluated by the gNMI stream collector."
        )

    if subscriptions_total <= 0:
        missing_reasons.append(
            "No gNMI streaming subscriptions were evaluated."
        )

    if missing_reasons:
        return ValidationResult.inconclusive_result(
            summary=(
                "gNMI streaming telemetry health could not be "
                "conclusively validated because required stream "
                "evidence is incomplete."
            ),
            confidence=0.0,
            reasons=missing_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    failure_reasons: List[str] = []

    if status == "fail":
        failure_reasons.append(
            "The gNMI stream collector reported failed health."
        )

    if nodes_failed > 0:
        failure_reasons.append(
            f"{nodes_failed} telemetry node(s) failed "
            "stream validation."
        )

    if subscriptions_failed > 0:
        failure_reasons.append(
            f"{subscriptions_failed} gNMI subscription(s) failed."
        )

    if unexpected_disconnects > 0:
        failure_reasons.append(
            f"{unexpected_disconnects} unexpected gNMI "
            "stream disconnect(s) were observed."
        )

    if update_count <= 0:
        failure_reasons.append(
            "No gNMI streaming updates were received."
        )

    if failure_reasons:
        return ValidationResult.fail_result(
            summary=(
                "gNMI streaming telemetry validation failed."
            ),
            confidence=1.0,
            reasons=failure_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    if status != "pass":
        return ValidationResult.inconclusive_result(
            summary=(
                "gNMI streaming telemetry health could not be "
                "conclusively validated."
            ),
            confidence=0.0,
            reasons=[
                f"Unsupported or incomplete stream status: {status}."
            ],
            evidence=evidence,
            metrics=metrics,
        )

    if nodes_passed != nodes_total:
        return ValidationResult.inconclusive_result(
            summary=(
                "gNMI streaming telemetry node accounting "
                "is incomplete."
            ),
            confidence=0.0,
            reasons=[
                "Not all evaluated nodes are accounted for as passed."
            ],
            evidence=evidence,
            metrics=metrics,
        )

    if subscriptions_passed != subscriptions_total:
        return ValidationResult.inconclusive_result(
            summary=(
                "gNMI streaming telemetry subscription accounting "
                "is incomplete."
            ),
            confidence=0.0,
            reasons=[
                "Not all evaluated subscriptions are accounted "
                "for as passed."
            ],
            evidence=evidence,
            metrics=metrics,
        )

    return ValidationResult.pass_result(
        summary=(
            "gNMI streaming subscriptions remained healthy "
            "during the bounded observation window."
        ),
        confidence=1.0,
        reasons=[
            (
                f"{nodes_passed}/{nodes_total} telemetry nodes "
                "passed stream validation."
            ),
            (
                f"{subscriptions_passed}/{subscriptions_total} "
                "gNMI subscriptions passed."
            ),
            (
                f"{update_count} streaming update(s) were received "
                "without unexpected disconnects."
            ),
        ],
        evidence=evidence,
        metrics=metrics,
    )

def evaluate_telemetry(
    *,
    evidence_rollup: Dict[str, Any],
    phase_timeline: Dict[str, Any],
    post_sample_health: List[Dict[str, Any]] | None = None,
    scenario: Dict[str, Any] | None = None,
    stream_health: Dict[str, Any] | None = None,
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



    scenario = dict(
        scenario or {}
    )

    stream_health = dict(
        stream_health or {}
    )

    telemetry_validation_mode = str(
        scenario.get("telemetry_validation_mode")
        or "snapshot"
    ).strip().lower()

    if telemetry_validation_mode == "stream":
        return _evaluate_stream_telemetry(
            stream_health=stream_health,
            strict_telemetry=bool(
                scenario.get("strict_telemetry")
        ),
    )

    strict_telemetry = bool(
        scenario.get("strict_telemetry")
    )

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
        if (
            str(status or "").lower() == "failed"
            or (
                strict_telemetry
                and str(status or "").lower()
                == "partial"
            )
        )
    ]

    missing_stages = [
        stage
        for stage, status in stage_results.items()
        if (
            str(status or "").lower()
            not in {"ok", "failed"}
            and not (
                strict_telemetry
                and str(status or "").lower()
                == "partial"
            )
        )
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
