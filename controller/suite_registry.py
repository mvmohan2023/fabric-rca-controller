import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def suite_dir(suite_id: str) -> str:
    return os.path.join("artifacts", "suites", suite_id)


def suite_runs_path(suite_id: str) -> str:
    return os.path.join(suite_dir(suite_id), "suite_runs.json")


def suite_summary_path(suite_id: str) -> str:
    return os.path.join(suite_dir(suite_id), "suite_summary.json")


def suite_dashboard_path(suite_id: str) -> str:
    return os.path.join(suite_dir(suite_id), "suite_dashboard.html")


def ensure_suite_dir(suite_id: str) -> str:
    path = suite_dir(suite_id)
    os.makedirs(path, exist_ok=True)
    return path


def load_json_file(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json_file(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def register_run(
    *,
    suite_id: str,
    suite_name: str,
    test_case_id: str,
    run_id: str,
    scenario: str,
    summary_path: str,
    ui_report_path: str,
    validation_path: str = "",
) -> None:
    if not suite_id:
        return

    ensure_suite_dir(suite_id)
    path = suite_runs_path(suite_id)

    data = load_json_file(
        path,
        {
            "suite_id": suite_id,
            "suite_name": suite_name or suite_id,
            "runs": [],
            "updated_at": _utc_now_iso(),
        },
    )

    runs: List[Dict[str, Any]] = data.setdefault("runs", [])

    runs = [r for r in runs if r.get("run_id") != run_id]

    runs.append(
        {
            "run_id": run_id,
            "test_case_id": test_case_id,
            "scenario": scenario,
            "summary_path": summary_path,
            "ui_report_path": ui_report_path,
            "validation_path": validation_path,
            "registered_at": _utc_now_iso(),

        }
    )

    data["runs"] = sorted(runs, key=lambda r: r.get("registered_at", ""))
    data["updated_at"] = _utc_now_iso()
    write_json_file(path, data)


def _safe_load(path: str) -> Dict[str, Any]:
    try:
        return load_json_file(path, {})
    except Exception:
        return {}


def build_suite_summary(*, suite_id: str) -> Dict[str, Any]:
    runs_data = load_json_file(
        suite_runs_path(suite_id),
        {},
    )
    runs = runs_data.get("runs", []) or []

    summary = {
        "suite_id": suite_id,
        "suite_name": runs_data.get(
            "suite_name",
            suite_id,
        ),
        "updated_at": _utc_now_iso(),
        "total_runs": 0,

        # Legacy counters — preserved.
        "pass_count": 0,
        "fail_count": 0,
        "warn_count": 0,
        "unknown_count": 0,

        # Additive engineering-validation aggregation.
        "engineering_counts": {
            "pass": 0,
            "warn": 0,
            "fail": 0,
            "inconclusive": 0,
            "unknown": 0,
        },
        "engineering_confidence": 0.0,
        "blocking_runs": [],
        "warning_runs": [],
        "inconclusive_runs": [],
        "runs": [],
    }

    # Only runs containing a real EVL result contribute to suite confidence.
    engineering_confidences: List[float] = []

    for run in runs:
        run_id = run.get("run_id", "")
        summary_path = run.get("summary_path", "")
        ui_report_path = run.get(
            "ui_report_path",
            "",
        )
        validation_path = run.get(
            "validation_path",
            "",
        )

        # Backward-compatible fallback for older suite entries.
        if not validation_path and run_id:
            candidate = os.path.join(
                "artifacts",
                "campaigns",
                run_id,
                "fault_injection_validation.json",
            )
            if os.path.exists(candidate):
                validation_path = candidate

        case_summary = _safe_load(summary_path)
        ui_report = _safe_load(ui_report_path)
        validation_report = _safe_load(
            validation_path
        )

        engineering_validation = (
            validation_report.get(
                "engineering_validation",
                {},
            )
            or {}
        )

        # --------------------------------------------------------------
        # Legacy traffic/RoCEv2 suite aggregation — preserved.
        # --------------------------------------------------------------
        traffic_health = (
            ui_report.get("traffic_health", {})
            or {}
        )

        rocev2_verdict = str(
            traffic_health.get(
                "rocev2_verdict",
                "unknown",
            )
            or "unknown"
        ).strip().lower()

        traffic_verdict = str(
            traffic_health.get(
                "traffic_verdict",
                "unknown",
            )
            or "unknown"
        ).strip().lower()

        test_verdict = rocev2_verdict

        if test_verdict == "pass":
            summary["pass_count"] += 1
        elif test_verdict == "fail":
            summary["fail_count"] += 1
        elif test_verdict in {"warn", "warning"}:
            summary["warn_count"] += 1
        else:
            summary["unknown_count"] += 1

        # --------------------------------------------------------------
        # New engineering-validation aggregation.
        # --------------------------------------------------------------
        engineering_status = str(
            engineering_validation.get(
                "overall_status",
            )
            or "UNKNOWN"
        ).strip().upper()

        try:
            engineering_confidence = float(
                engineering_validation.get(
                    "overall_confidence",
                    0.0,
                )
                or 0.0
            )
        except (TypeError, ValueError):
            engineering_confidence = 0.0

        # Protect suite aggregation from malformed values.
        engineering_confidence = max(
            0.0,
            min(
                1.0,
                engineering_confidence,
            ),
        )

        engineering_summary = str(
            engineering_validation.get(
                "summary",
            )
            or ""
        )

        engineering_count_key = {
            "PASS": "pass",
            "WARN": "warn",
            "FAIL": "fail",
            "INCONCLUSIVE": "inconclusive",
        }.get(
            engineering_status,
            "unknown",
        )

        summary["engineering_counts"][
            engineering_count_key
        ] += 1

        # Do not let legacy/unknown runs contribute zero confidence.
        if engineering_status in {
            "PASS",
            "WARN",
            "FAIL",
            "INCONCLUSIVE",
        }:
            engineering_confidences.append(
                engineering_confidence
            )

        engineering_run = {
            "run_id": run_id,
            "test_case_id": run.get(
                "test_case_id",
                "",
            ),
            "scenario": run.get(
                "scenario",
                "",
            ),
            "engineering_status":
                engineering_status,
            "engineering_confidence":
                engineering_confidence,
            "engineering_summary":
                engineering_summary,
            "validation_path":
                validation_path,
        }

        if engineering_status == "FAIL":
            summary["blocking_runs"].append(
                engineering_run
            )
        elif engineering_status == "WARN":
            summary["warning_runs"].append(
                engineering_run
            )
        elif engineering_status in {
            "INCONCLUSIVE",
            "UNKNOWN",
        }:
            summary[
                "inconclusive_runs"
            ].append(
                engineering_run
            )

        status = (
            case_summary.get("status", {})
            or {}
        )

        root_cause = (
            (
                traffic_health.get(
                    "executive_summary",
                    {},
                )
                or {}
            ).get("detected_root_cause")
            or traffic_health.get(
                "detected_root_cause"
            )
            or "unknown"
        )

        summary["runs"].append(
            {
                "run_id": run_id,
                "test_case_id": run.get(
                    "test_case_id",
                    "",
                ),
                "scenario": run.get(
                    "scenario",
                    "",
                ),

                # Legacy fields.
                "traffic_verdict":
                    traffic_verdict,
                "rocev2_verdict":
                    rocev2_verdict,
                "test_verdict":
                    test_verdict,
                "root_cause":
                    root_cause,
                "summary_path":
                    summary_path,
                "ui_report_path":
                    ui_report_path,
                "status":
                    status,

                # Additive engineering fields.
                "validation_path":
                    validation_path,
                "engineering_status":
                    engineering_status,
                "engineering_confidence":
                    engineering_confidence,
                "engineering_summary":
                    engineering_summary,
            }
        )

    summary["total_runs"] = len(
        summary["runs"]
    )

    if engineering_confidences:
        summary["engineering_confidence"] = round(
            sum(engineering_confidences)
            / len(engineering_confidences),
            3,
        )

    return summary


def write_suite_summary(*, suite_id: str) -> str:
    summary = build_suite_summary(suite_id=suite_id)
    path = suite_summary_path(suite_id)
    write_json_file(path, summary)
    return path


def write_suite_dashboard(*, suite_id: str) -> str:
    summary = build_suite_summary(suite_id=suite_id)
    out_path = suite_dashboard_path(suite_id)

    rows = []
    for run in summary["runs"]:
        rows.append(
            f"""
            <tr>
              <td>{run['test_case_id']}</td>
              <td>{run['scenario']}</td>
              <td>{run['run_id']}</td>
              <td>{run['test_verdict']}</td>
              <td>{run['traffic_verdict']}</td>
              <td>{run['rocev2_verdict']}</td>
              <td>{run['root_cause']}</td>
              <td><a href="../../{run['summary_path']}">summary</a></td>
              <td><a href="../../{run['ui_report_path']}">ui report</a></td>
            </tr>
            """
        )

    html = f"""
    <html>
    <head>
      <title>Suite Dashboard - {summary['suite_id']}</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        .cards {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
        .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; min-width: 140px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f5f5f5; }}
      </style>
    </head>
    <body>
      <h1>Suite Dashboard: {summary['suite_name']}</h1>
      <div class="cards">
        <div class="card"><b>Total Runs</b><br>{summary['total_runs']}</div>
        <div class="card"><b>Pass</b><br>{summary['pass_count']}</div>
        <div class="card"><b>Warn</b><br>{summary['warn_count']}</div>
        <div class="card"><b>Fail</b><br>{summary['fail_count']}</div>
        <div class="card"><b>Unknown</b><br>{summary['unknown_count']}</div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Test Case ID</th>
            <th>Scenario</th>
            <th>Run ID</th>
            <th>Test Verdict</th>
            <th>Traffic Verdict</th>
            <th>RoCEv2 Verdict</th>
            <th>Root Cause</th>
            <th>Summary</th>
            <th>UI Report</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </body>
    </html>
    """

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    return out_path
