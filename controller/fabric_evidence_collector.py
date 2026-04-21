import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


def load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def output_dir(source_type: str, run_id: str) -> str:
    out_dir = os.path.join("artifacts", f"{source_type}s", run_id, "traffic")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def default_output_paths(source_type: str, run_id: str) -> Dict[str, str]:
    out = output_dir(source_type, run_id)
    return {
        "json": os.path.join(out, "fabric_evidence.json"),
        "txt": os.path.join(out, "fabric_evidence.txt"),
    }


def metric_matches(metric: str, keywords: List[str]) -> bool:
    metric_l = (metric or "").lower()
    return any(k in metric_l for k in keywords)


def categorize_metric(metric: str) -> str:
    metric_l = (metric or "").lower()

    if any(k in metric_l for k in ["drop", "discard", "queue", "buffer"]):
        return "queue_or_drop"
    if any(k in metric_l for k in ["ecn", "pfc", "pause", "cnp"]):
        return "ecn_pfc_pause"
    if any(k in metric_l for k in ["fec", "crc", "error", "signal", "loss-of-signal"]):
        return "fec_or_error"
    if any(k in metric_l for k in ["optic", "laser", "temperature", "bias", "rx-power", "output-power"]):
        return "optics_or_temp"
    return "other"


def build_interface_targets(root_cause: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets = []
    seen = set()

    for item in root_cause.get("summary", {}).get("top_hotspots", []):
        key = (item.get("device"), item.get("interface"))
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            "rx_port": item.get("rx_port"),
            "device": item.get("device"),
            "interface": item.get("interface"),
            "classification": item.get("classification"),
        })

    return targets


def collect_snapshot_evidence(
    telemetry_snapshot: Dict[str, Any],
    targets: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}

    for t in targets:
        iface = t["interface"]
        result[iface] = {
            "target": t,
            "records": [],
            "summary": {
                "queue_or_drop": 0,
                "ecn_pfc_pause": 0,
                "fec_or_error": 0,
                "optics_or_temp": 0,
                "other": 0,
            }
        }

    for node in telemetry_snapshot.get("nodes", []):
        for rec in node.get("normalized_records", []):
            entity = rec.get("entity", "")
            metric = rec.get("metric", "")
            for t in targets:
                iface = t["interface"]
                if iface and iface in entity:
                    category = categorize_metric(metric)
                    result[iface]["summary"][category] += 1
                    if len(result[iface]["records"]) < 50:
                        result[iface]["records"].append({
                            "node": node.get("node_name") or node.get("node"),
                            "entity": entity,
                            "metric": metric,
                            "value": rec.get("value"),
                            "category": category,
                        })

    return result


def collect_anomaly_evidence(
    telemetry_anomaly: Dict[str, Any],
    targets: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}

    for t in targets:
        iface = t["interface"]
        result[iface] = {
            "anomalies": [],
            "by_type": {}
        }

    for a in telemetry_anomaly.get("anomalies", []):
        entity = a.get("entity", "")
        for t in targets:
            iface = t["interface"]
            if iface and iface in entity:
                atype = a.get("type", "unknown")
                result[iface]["by_type"][atype] = result[iface]["by_type"].get(atype, 0) + 1
                if len(result[iface]["anomalies"]) < 50:
                    result[iface]["anomalies"].append(a)

    return result


def build_report(
    root_cause: Dict[str, Any],
    telemetry_snapshot: Dict[str, Any],
    telemetry_anomaly: Dict[str, Any],
) -> Dict[str, Any]:
    targets = build_interface_targets(root_cause)
    snapshot_evidence = collect_snapshot_evidence(telemetry_snapshot, targets)
    anomaly_evidence = collect_anomaly_evidence(telemetry_anomaly, targets)

    interfaces = []

    for t in targets:
        iface = t["interface"]
        interfaces.append({
            "rx_port": t["rx_port"],
            "device": t["device"],
            "interface": iface,
            "classification": t.get("classification"),
            "snapshot_summary": snapshot_evidence.get(iface, {}).get("summary", {}),
            "snapshot_records": snapshot_evidence.get(iface, {}).get("records", []),
            "anomaly_summary": anomaly_evidence.get(iface, {}).get("by_type", {}),
            "anomalies": anomaly_evidence.get(iface, {}).get("anomalies", []),
        })

    return {
        "targets": targets,
        "interfaces": interfaces,
    }


def render_text(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("FABRIC EVIDENCE SUMMARY")
    lines.append("")

    for item in report.get("interfaces", []):
        lines.append(
            f"  {item['rx_port']} -> {item['device']} {item['interface']} | "
            f"class={item.get('classification')}"
        )
        lines.append(f"    snapshot_summary={item.get('snapshot_summary')}")
        lines.append(f"    anomaly_summary={item.get('anomaly_summary')}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect DUT-side evidence for mapped hotspot interfaces")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--root-cause", required=True)
    parser.add_argument("--telemetry-snapshot", default=None)
    parser.add_argument("--telemetry-anomaly", default=None)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        root_cause = load_json(args.root_cause)
        telemetry_snapshot = load_json(args.telemetry_snapshot)
        telemetry_anomaly = load_json(args.telemetry_anomaly)

        report = build_report(root_cause, telemetry_snapshot, telemetry_anomaly)

        outputs = default_output_paths(args.source_type, args.run_id)
        out_json = args.out_json or outputs["json"]
        out_txt = args.out_txt or outputs["txt"]

        write_json(out_json, report)
        write_text(out_txt, render_text(report))

        print(f"Fabric evidence JSON report : {out_json}")
        print(f"Fabric evidence text report : {out_txt}")
        print("")
        print("FABRIC EVIDENCE SUMMARY")
        for item in report.get("interfaces", [])[:5]:
            print(
                f"  {item['rx_port']:<12} -> "
                f"{item['device']:<15} {item['interface']:<15} "
                f"anomalies={sum(item.get('anomaly_summary', {}).values())}"
            )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
