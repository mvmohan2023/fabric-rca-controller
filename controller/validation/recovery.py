"""Recovery-domain engineering validation."""

from __future__ import annotations

from typing import Any, Dict, List

from controller.validation.models import ValidationResult


def evaluate_recovery(
    *,
    stress_validation: Dict[str, Any],
    evidence_rollup: Dict[str, Any],
    phase_timeline: Dict[str, Any],
    post_sample_health: List[Dict[str, Any]] | None = None,
) -> ValidationResult:
    """Evaluate recovery using stress and post-window evidence.

    The evaluator does not read files directly. The caller may supply
    lightweight health metadata loaded from post-window sample artifacts.

    Confirmed recovery requires:
    - successful stress/orchestrator outcome,
    - successful post snapshot,
    - one or more post-window samples,
    - no failed nodes in supplied sample health.

    Missing required evidence is INCONCLUSIVE rather than PASS.
    """

    post_sample_health = list(post_sample_health or [])

    stress_ok = bool(stress_validation.get("ok", False))
    stress_status = str(
        stress_validation.get("overall_status") or ""
    ).strip().lower()

    evidence_status = dict(
        evidence_rollup.get("status") or {}
    )
    post_snapshot_status = str(
        evidence_status.get("post_snapshot") or ""
    ).strip().lower()

    post_window = int(
        phase_timeline.get("post_window") or 0
    )
    post_telemetry = (
        phase_timeline.get("post_telemetry") or ""
    )
    post_sample_paths = list(
        phase_timeline.get("post_sample_paths") or []
    )

    failed_sample_count = 0
    total_failed_nodes = 0
    total_ok_nodes = 0
    total_nodes = 0

    for sample in post_sample_health:
        failed_nodes = sample.get("failed_nodes", 0)
        ok_nodes = sample.get("ok_nodes", 0)
        sample_total_nodes = sample.get("total_nodes", 0)

        if isinstance(failed_nodes, list):
            failed_node_count = len(failed_nodes)
        else:
            try:
                failed_node_count = int(failed_nodes or 0)
            except (TypeError, ValueError):
                failed_node_count = 0

        if isinstance(ok_nodes, list):
            ok_node_count = len(ok_nodes)
        else:
            try:
                ok_node_count = int(ok_nodes or 0)
            except (TypeError, ValueError):
                ok_node_count = 0

        try:
            sample_total_count = int(
                sample_total_nodes or 0
            )
        except (TypeError, ValueError):
            sample_total_count = 0

        total_failed_nodes += failed_node_count
        total_ok_nodes += ok_node_count
        total_nodes += sample_total_count

        if failed_node_count > 0:
            failed_sample_count += 1

    evidence = [
        value
        for value in (
            stress_validation.get("path"),
            post_telemetry,
            *post_sample_paths,
        )
        if value
    ]

    metrics = {
        "stress_report_ok": stress_ok,
        "stress_overall_status": stress_status,
        "post_snapshot_status": post_snapshot_status,
        "post_window_seconds": post_window,
        "post_sample_count": len(post_sample_paths),
        "post_sample_health_count": len(post_sample_health),
        "failed_sample_count": failed_sample_count,
        "total_failed_nodes": total_failed_nodes,
        "total_ok_nodes": total_ok_nodes,
        "total_nodes_observed": total_nodes,
    }

    hard_failure_reasons: List[str] = []

    if stress_status == "fail":
        hard_failure_reasons.append(
            "Stress/orchestrator report ended in failure."
        )

    if post_snapshot_status == "failed":
        hard_failure_reasons.append(
            "Post-event telemetry snapshot failed."
        )

    if failed_sample_count > 0 or total_failed_nodes > 0:
        hard_failure_reasons.append(
            "One or more post-window samples reported failed nodes."
        )

    if hard_failure_reasons:
        return ValidationResult.fail_result(
            summary=(
                "The fabric did not demonstrate clean recovery "
                "during the post-event window."
            ),
            confidence=1.0,
            reasons=hard_failure_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    missing_reasons: List[str] = []

    if not stress_validation.get("path"):
        missing_reasons.append(
            "Stress validation evidence path is unavailable."
        )

    if stress_status not in {"pass", "fail"}:
        missing_reasons.append(
            "Stress/orchestrator final status is unavailable."
        )

    if post_snapshot_status not in {"ok", "failed"}:
        missing_reasons.append(
            "Post-event snapshot status is unavailable."
        )

    if post_window <= 0:
        missing_reasons.append(
            "Post-event recovery window is not defined."
        )

    if not post_sample_paths:
        missing_reasons.append(
            "No post-window recovery sample paths were recorded."
        )

    if not post_sample_health:
        missing_reasons.append(
            "Post-window sample health metadata is unavailable."
        )

    if missing_reasons:
        return ValidationResult.inconclusive_result(
            summary=(
                "Recovery could not be conclusively validated "
                "because required post-window evidence is incomplete."
            ),
            confidence=0.0,
            reasons=missing_reasons,
            evidence=evidence,
            metrics=metrics,
        )

    if (
        stress_ok
        and stress_status == "pass"
        and post_snapshot_status == "ok"
        and failed_sample_count == 0
        and total_failed_nodes == 0
    ):
        return ValidationResult.pass_result(
            summary=(
                "The fabric recovered successfully during the "
                "configured post-event window."
            ),
            confidence=1.0,
            reasons=[
                "Stress/orchestrator execution completed successfully.",
                "Post-event telemetry snapshot completed successfully.",
                (
                    f"{len(post_sample_health)} post-window sample(s) "
                    "completed without failed nodes."
                ),
            ],
            evidence=evidence,
            metrics=metrics,
        )

    return ValidationResult.inconclusive_result(
        summary=(
            "Recovery evidence was present but did not provide "
            "a definitive engineering verdict."
        ),
        confidence=0.5,
        reasons=[
            "Available recovery indicators were not fully consistent."
        ],
        evidence=evidence,
        metrics=metrics,
    )
