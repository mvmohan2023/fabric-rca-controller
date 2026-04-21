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
    runs_data = load_json_file(suite_runs_path(suite_id), {})
    runs = runs_data.get("runs", [])

    summary = {
        "suite_id": suite_id,
        "suite_name": runs_data.get("suite_name", suite_id),
        "updated_at": _utc_now_iso(),
        "total_runs": 0,
        "pass_count": 0,
        "fail_count": 0,
        "warn_count": 0,
        "unknown_count": 0,
        "runs": [],
    }

    for run in runs:
        run_id = run.get("run_id", "")
        summary_path = run.get("summary_path", "")
        ui_report_path = run.get("ui_report_path", "")

        case_summary = _safe_load(summary_path)
        ui_report = _safe_load(ui_report_path)

        traffic_health = ui_report.get("traffic_health", {}) or {}
        rocev2_verdict = traffic_health.get("rocev2_verdict", "unknown")
        traffic_verdict = traffic_health.get("traffic_verdict", "unknown")

        test_verdict = rocev2_verdict
        if test_verdict == "pass":
            summary["pass_count"] += 1
        elif test_verdict == "fail":
            summary["fail_count"] += 1
        elif test_verdict == "warn":
            summary["warn_count"] += 1
        else:
            summary["unknown_count"] += 1

        status = case_summary.get("status", {}) or {}
        root_cause = (
            (traffic_health.get("executive_summary", {}) or {}).get("detected_root_cause")
            or traffic_health.get("detected_root_cause")
            or "unknown"
        )

        summary["runs"].append(
            {
                "run_id": run_id,
                "test_case_id": run.get("test_case_id", ""),
                "scenario": run.get("scenario", ""),
                "traffic_verdict": traffic_verdict,
                "rocev2_verdict": rocev2_verdict,
                "test_verdict": test_verdict,
                "root_cause": root_cause,
                "summary_path": summary_path,
                "ui_report_path": ui_report_path,
                "status": status,
            }
        )

    summary["total_runs"] = len(summary["runs"])
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
