import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from controller.telemetry_monitor import (
    collect_orchestrator_snapshots,
    collect_campaign_snapshots,
)
from controller.anomaly_rules import DEFAULT_RULES


BASE_DIR = Path("/root/fabric-controller")
ARTIFACTS_DIR = BASE_DIR / "artifacts"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Telemetry-driven detection engine")
    parser.add_argument(
        "--source-type",
        required=True,
        choices=["orchestrator", "campaign"],
        help="Artifact source type to analyze",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID for orchestrator or campaign artifacts",
    )
    return parser.parse_args()


def evaluate_rules(pre: dict, post: dict, rules=None):
    rules = rules or DEFAULT_RULES

    results = []
    for rule in rules:
        results.append(rule(pre, post))

    detected = [r for r in results if r.get("detected")]
    highest_severity = "none"

    if any(r["severity"] == "critical" for r in detected):
        highest_severity = "critical"
    elif any(r["severity"] == "major" for r in detected):
        highest_severity = "major"
    elif any(r["severity"] == "minor" for r in detected):
        highest_severity = "minor"

    return {
        "rules_evaluated": len(results),
        "anomalies_detected": len(detected),
        "highest_severity": highest_severity,
        "rule_results": results,
    }


def analyze_orchestrator(run_id: str):
    snapshots = collect_orchestrator_snapshots(run_id)
    result = evaluate_rules(snapshots["pre"], snapshots["post"])

    return {
        "source_type": "orchestrator",
        "run_id": run_id,
        "timestamp": utc_now(),
        "summary": result,
        "snapshots": {
            "pre": snapshots["pre"],
            "post": snapshots["post"],
        }
    }


def analyze_campaign(run_id: str):
    snapshots = collect_campaign_snapshots(run_id)

    baseline = snapshots["baseline"]
    iteration_analyses = []

    for item in snapshots["iterations"]:
        iteration = item["iteration"]
        snap = item["snapshot"]
        analysis = evaluate_rules(baseline, snap)

        iteration_analyses.append({
            "iteration": iteration,
            "iteration_status": item.get("status"),
            "summary": analysis,
            "snapshot": snap,
        })

    total_detected_iterations = sum(
        1 for x in iteration_analyses
        if x["summary"]["anomalies_detected"] > 0
    )

    highest_severity = "none"
    for x in iteration_analyses:
        sev = x["summary"]["highest_severity"]
        if sev == "critical":
            highest_severity = "critical"
            break
        if sev == "major" and highest_severity not in ("critical",):
            highest_severity = "major"
        if sev == "minor" and highest_severity not in ("critical", "major"):
            highest_severity = "minor"

    return {
        "source_type": "campaign",
        "run_id": run_id,
        "timestamp": utc_now(),
        "baseline": baseline,
        "summary": {
            "iterations_analyzed": len(iteration_analyses),
            "iterations_with_anomalies": total_detected_iterations,
            "highest_severity": highest_severity,
        },
        "iteration_analyses": iteration_analyses,
    }


def write_report(report: dict, source_type: str, run_id: str):
    if source_type == "orchestrator":
        out_dir = ARTIFACTS_DIR / "orchestrator" / run_id
    else:
        out_dir = ARTIFACTS_DIR / "campaigns" / run_id

    ensure_dir(out_dir)

    json_out = out_dir / "detection_report.json"
    txt_out = out_dir / "detection_report.txt"

    with open(json_out, "w") as f:
        json.dump(report, f, indent=2)

    with open(txt_out, "w") as f:
        f.write("DETECTION REPORT\n")
        f.write("================\n\n")
        f.write(f"Source Type : {report.get('source_type')}\n")
        f.write(f"Run ID      : {report.get('run_id')}\n")
        f.write(f"Timestamp   : {report.get('timestamp')}\n\n")

        if source_type == "orchestrator":
            summary = report["summary"]
            f.write("SUMMARY\n")
            f.write("-------\n")
            f.write(f"Rules evaluated    : {summary.get('rules_evaluated')}\n")
            f.write(f"Anomalies detected : {summary.get('anomalies_detected')}\n")
            f.write(f"Highest severity   : {summary.get('highest_severity')}\n\n")

            f.write("RULE RESULTS\n")
            f.write("------------\n")
            for item in summary.get("rule_results", []):
                f.write(
                    f"{item['rule_name']}: detected={item['detected']} "
                    f"severity={item['severity']} details={item['details']}\n"
                )

        else:
            summary = report["summary"]
            f.write("SUMMARY\n")
            f.write("-------\n")
            f.write(f"Iterations analyzed       : {summary.get('iterations_analyzed')}\n")
            f.write(f"Iterations with anomalies : {summary.get('iterations_with_anomalies')}\n")
            f.write(f"Highest severity          : {summary.get('highest_severity')}\n\n")

            f.write("ITERATION RESULTS\n")
            f.write("-----------------\n")
            for item in report.get("iteration_analyses", []):
                s = item["summary"]
                f.write(
                    f"Iteration {item['iteration']}: "
                    f"status={item.get('iteration_status')} "
                    f"anomalies={s.get('anomalies_detected')} "
                    f"severity={s.get('highest_severity')}\n"
                )

    return json_out, txt_out


def main():
    args = parse_args()

    if args.source_type == "orchestrator":
        report = analyze_orchestrator(args.run_id)
    else:
        report = analyze_campaign(args.run_id)

    json_out, txt_out = write_report(report, args.source_type, args.run_id)

    print(f"Detection JSON report : {json_out}")
    print(f"Detection text report : {txt_out}")

    if args.source_type == "orchestrator":
        summary = report["summary"]
        print("\nDETECTION SUMMARY")
        print(f"  Rules evaluated    : {summary.get('rules_evaluated')}")
        print(f"  Anomalies detected : {summary.get('anomalies_detected')}")
        print(f"  Highest severity   : {summary.get('highest_severity')}")
    else:
        summary = report["summary"]
        print("\nDETECTION SUMMARY")
        print(f"  Iterations analyzed       : {summary.get('iterations_analyzed')}")
        print(f"  Iterations with anomalies : {summary.get('iterations_with_anomalies')}")
        print(f"  Highest severity          : {summary.get('highest_severity')}")


if __name__ == "__main__":
    main()
