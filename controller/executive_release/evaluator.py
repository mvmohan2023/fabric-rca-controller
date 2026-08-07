"""Executive Release Qualification evaluator."""

from __future__ import annotations

from typing import Any, Dict, List

from controller.executive_release.models import (
    ExecutiveReleaseResult,
)


_STATUS_POINTS = {
    "PASS": 100.0,
    "WARN": 75.0,
    "INCONCLUSIVE": 50.0,
    "FAIL": 0.0,
    "UNKNOWN": 0.0,
}


def _risk_level(score: float) -> str:
    """Architecture-defined risk bands.

    Note: higher score means lower release risk.
    """

    if score >= 90.0:
        return "VERY_LOW"
    if score >= 75.0:
        return "LOW"
    if score >= 60.0:
        return "MEDIUM"
    if score >= 40.0:
        return "HIGH"

    return "CRITICAL"


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_feature_health(
    runs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Group run health by scenario family/name.

    The current suite registry does not yet expose an explicit feature-family
    field, so scenario is used as the grouping key. This remains traceable and
    can later be replaced by catalog-defined family metadata.
    """

    feature_health: Dict[str, Dict[str, Any]] = {}

    for run in runs:
        feature = str(
            run.get("scenario")
            or "unknown"
        )

        status = str(
            run.get("engineering_status")
            or "UNKNOWN"
        ).strip().upper()

        confidence = _safe_float(
            run.get(
                "engineering_confidence",
                0.0,
            )
        )

        entry = feature_health.setdefault(
            feature,
            {
                "runs": 0,
                "pass": 0,
                "warn": 0,
                "fail": 0,
                "inconclusive": 0,
                "unknown": 0,
                "confidence_values": [],
                "run_ids": [],
            },
        )

        entry["runs"] += 1
        entry["run_ids"].append(
            run.get("run_id")
        )

        status_key = {
            "PASS": "pass",
            "WARN": "warn",
            "FAIL": "fail",
            "INCONCLUSIVE": "inconclusive",
        }.get(
            status,
            "unknown",
        )

        entry[status_key] += 1

        if status != "UNKNOWN":
            entry[
                "confidence_values"
            ].append(
                confidence
            )

    output: Dict[str, Any] = {}

    for feature, entry in feature_health.items():
        if entry["fail"] > 0:
            feature_status = "FAIL"
        elif entry["inconclusive"] > 0:
            feature_status = "INCONCLUSIVE"
        elif entry["warn"] > 0:
            feature_status = "WARN"
        elif entry["pass"] > 0:
            feature_status = "PASS"
        else:
            feature_status = "UNKNOWN"

        confidences = entry.pop(
            "confidence_values"
        )

        feature_confidence = (
            round(
                sum(confidences)
                / len(confidences),
                3,
            )
            if confidences
            else 0.0
        )

        output[feature] = {
            **entry,
            "status": feature_status,
            "confidence": feature_confidence,
        }

    return output


def evaluate_executive_release(
    *,
    release_id: str,
    suite_summary: Dict[str, Any],
) -> ExecutiveReleaseResult:
    """Build one release-level qualification result.

    v1-provisional scoring policy:

    validation score:
        average engineering status score across suite runs.

    confidence:
        suite engineering confidence.

    evidence coverage:
        percentage of registered runs containing a recognized
        engineering-validation verdict.

    release health:
        60% validation score
        25% engineering confidence
        15% evidence coverage

    This formula is explicitly provisional because architecture document 07
    defines the dimensions but does not prescribe the exact arithmetic.

    Explicit engineering FAIL remains release-blocking regardless of score.
    """

    suite_id = str(
        suite_summary.get("suite_id")
        or ""
    )

    runs = list(
        suite_summary.get("runs")
        or []
    )

    total_runs = len(runs)

    recognized_runs = [
        run
        for run in runs
        if str(
            run.get("engineering_status")
            or ""
        ).strip().upper()
        in {
            "PASS",
            "WARN",
            "FAIL",
            "INCONCLUSIVE",
        }
    ]

    validation_scores = [
        _STATUS_POINTS.get(
            str(
                run.get(
                    "engineering_status"
                )
                or "UNKNOWN"
            ).strip().upper(),
            0.0,
        )
        for run in runs
    ]

    validation_score = (
        sum(validation_scores)
        / len(validation_scores)
        if validation_scores
        else 0.0
    )

    confidence = max(
        0.0,
        min(
            1.0,
            _safe_float(
                suite_summary.get(
                    "engineering_confidence",
                    0.0,
                )
            ),
        ),
    )

    evidence_coverage = (
        (
            len(recognized_runs)
            / total_runs
        )
        * 100.0
        if total_runs
        else 0.0
    )

    release_health = (
        0.60 * validation_score
        + 0.25 * (
            confidence * 100.0
        )
        + 0.15 * evidence_coverage
    )

    release_health = round(
        release_health,
        2,
    )

    # Architecture risk bands use a higher-is-better score.
    risk_score = release_health
    risk_level = _risk_level(
        risk_score
    )

    blocking_runs = list(
        suite_summary.get(
            "blocking_runs",
            [],
        )
        or []
    )

    warning_runs = list(
        suite_summary.get(
            "warning_runs",
            [],
        )
        or []
    )

    inconclusive_runs = list(
        suite_summary.get(
            "inconclusive_runs",
            [],
        )
        or []
    )

    engineering_counts = dict(
        suite_summary.get(
            "engineering_counts",
            {},
        )
        or {}
    )

    fail_count = int(
        engineering_counts.get(
            "fail",
            0,
        )
        or 0
    )

    warn_count = int(
        engineering_counts.get(
            "warn",
            0,
        )
        or 0
    )

    inconclusive_count = int(
        engineering_counts.get(
            "inconclusive",
            0,
        )
        or 0
    )

    unknown_count = int(
        engineering_counts.get(
            "unknown",
            0,
        )
        or 0
    )

    missing_inputs: List[str] = [
        "planned_scenario_coverage",
        "rca_confidence_aggregate",
        "complete_platform_health",
        "historical_release_trend",
    ]

    if total_runs == 0:
        release_status = "INCONCLUSIVE"
        recommendation = "NOT READY"

    elif fail_count > 0 or blocking_runs:
        release_status = "BLOCKED"
        recommendation = "BLOCK RELEASE"

    elif unknown_count > 0:
        release_status = "INCONCLUSIVE"
        recommendation = "NOT READY"

    elif inconclusive_count > 0:
        release_status = "NOT_READY"
        recommendation = "NOT READY"

    elif warn_count > 0:
        release_status = "READY_WITH_RISK"

        if risk_level in {
            "VERY_LOW",
            "LOW",
        }:
            recommendation = (
                "READY WITH LOW RISK"
            )
        else:
            recommendation = (
                "READY WITH MEDIUM RISK"
            )

    elif risk_level == "VERY_LOW":
        release_status = "READY"
        recommendation = (
            "READY FOR PRODUCTION"
        )

    elif risk_level == "LOW":
        release_status = "READY_WITH_RISK"
        recommendation = (
            "READY WITH LOW RISK"
        )

    elif risk_level == "MEDIUM":
        release_status = "READY_WITH_RISK"
        recommendation = (
            "READY WITH MEDIUM RISK"
        )

    else:
        release_status = "NOT_READY"
        recommendation = "NOT READY"

    top_findings: List[str] = []

    if fail_count:
        top_findings.append(
            f"{fail_count} engineering run(s) "
            "reported FAIL."
        )

    if warn_count:
        top_findings.append(
            f"{warn_count} engineering run(s) "
            "reported WARN."
        )

    if inconclusive_count:
        top_findings.append(
            f"{inconclusive_count} engineering run(s) "
            "were INCONCLUSIVE."
        )

    if unknown_count:
        top_findings.append(
            f"{unknown_count} suite run(s) "
            "do not contain engineering-validation evidence."
        )

    if (
        total_runs > 0
        and fail_count == 0
        and warn_count == 0
        and inconclusive_count == 0
        and unknown_count == 0
    ):
        top_findings.append(
            "All suite engineering-validation runs passed."
        )

    feature_health = _build_feature_health(
        runs
    )

    coverage = {
        "registered_runs": total_runs,
        "engineering_evidence_runs": len(
            recognized_runs
        ),
        "engineering_evidence_coverage_percent": round(
            evidence_coverage,
            2,
        ),

        # True planned scenario coverage is not yet available from
        # suite_registry and must not be fabricated.
        "planned_scenario_coverage_percent": None,
    }

    traceability = {
        "suite_id": suite_id,
        "suite_runs": [
            {
                "run_id": run.get(
                    "run_id"
                ),
                "scenario": run.get(
                    "scenario"
                ),
                "engineering_status": run.get(
                    "engineering_status"
                ),
                "validation_path": run.get(
                    "validation_path"
                ),
                "summary_path": run.get(
                    "summary_path"
                ),
                "ui_report_path": run.get(
                    "ui_report_path"
                ),
            }
            for run in runs
        ],
    }

    return ExecutiveReleaseResult(
        release_id=release_id,
        suite_id=suite_id,
        release_status=release_status,
        release_health=release_health,
        confidence=confidence,
        risk_score=risk_score,
        risk_level=risk_level,
        recommendation=recommendation,
        blocking_conditions=blocking_runs,
        warning_conditions=warning_runs,
        inconclusive_conditions=inconclusive_runs,
        feature_health=feature_health,
        coverage=coverage,
        top_findings=top_findings,
        traceability=traceability,
        missing_inputs=missing_inputs,
    )
