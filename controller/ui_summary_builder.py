import argparse
import json
import os


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def output_dir(source_type, run_id):
    path = f"artifacts/{source_type}s/{run_id}/traffic"
    os.makedirs(path, exist_ok=True)
    return path


def main():
    parser = argparse.ArgumentParser(description="Build UI-ready summary JSON")
    parser.add_argument("--source-type", default="campaign")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    base = f"artifacts/{args.source_type}s/{args.run_id}/traffic"

    verdict = load(f"{base}/rocev2_verdict.json")
    hotspot = load(f"{base}/rocev2_hotspot_report.json")
    congestion = load(f"{base}/congestion_inspection.json")
    root_cause = load(f"{base}/root_cause_correlation.json")
    deep_congestion = load(f"{base}/deep_congestion_inspection.json")
    live = load(f"{base}/live_ixia_live_monitor.json")

    summary = {
        "run_id": args.run_id,
        "verdict": "fail" if verdict.get("summary", {}).get("total_findings", 0) > 0 else "pass",
        "overview": verdict.get("summary", {}),
        "top_hotspots": deep_congestion.get("summary", {}).get("top_hotspots")
            or root_cause.get("summary", {}).get("top_hotspots", []),
        "top_problem_flows": root_cause.get("summary", {}).get("top_problem_flows", []),
        "hotspot_rollup": hotspot.get("worst_rx_ports", []),
        "congestion_summary": congestion.get("summary", {}),
        "rca_summary": root_cause.get("conclusion"),
        "deep_congestion_summary": deep_congestion.get("conclusion"),
        "live_alerts": [],
    }

    if live.get("iterations"):
        for it in live["iterations"]:
            for alert in it.get("alerts", []):
                summary["live_alerts"].append({
                    "timestamp": it.get("timestamp"),
                    "severity": alert.get("severity"),
                    "type": alert.get("type"),
                    "flow": alert.get("flow_key"),
                    "rx_port": alert.get("rx_port"),
                    "value": alert.get("value"),
                })

    out = output_dir(args.source_type, args.run_id)
    out_json = f"{out}/ui_summary.json"

    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)

    print("UI SUMMARY GENERATED")
    print(out_json)


if __name__ == "__main__":
    main()
