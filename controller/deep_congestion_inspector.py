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
        "json": os.path.join(out, "deep_congestion_inspection.json"),
        "txt": os.path.join(out, "deep_congestion_inspection.txt"),
    }


def safe_int(value: Any) -> int:
    if value in ("", None):
        return 0
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return 0


def build_fabric_evidence_index(fabric_evidence: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in fabric_evidence.get("interfaces", []):
        iface = item.get("interface")
        if iface:
            result[iface] = item
    return result


def refine_classification(
    hotspot: Dict[str, Any],
    fabric_item: Dict[str, Any],
) -> Dict[str, Any]:
    base_class = hotspot.get("classification", "unknown")
    tags = list(hotspot.get("tags", []))

    snapshot_summary = fabric_item.get("snapshot_summary", {})
    anomaly_summary = fabric_item.get("anomaly_summary", {})

    queue_metrics = safe_int(snapshot_summary.get("queue_or_drop"))
    ecn_pfc_metrics = safe_int(snapshot_summary.get("ecn_pfc_pause"))
    fec_metrics = safe_int(snapshot_summary.get("fec_or_error"))
    optics_metrics = safe_int(snapshot_summary.get("optics_or_temp"))
    anomaly_count = sum(safe_int(v) for v in anomaly_summary.values())

    final_class = base_class

    if queue_metrics > 0 and ecn_pfc_metrics > 0:
        final_class = "ecn_pfc_correlated_congestion"
        tags.extend(["dut_queue_evidence", "dut_ecn_pfc_evidence"])
    elif queue_metrics > 0:
        final_class = "receiver_congestion_hotspot"
        tags.append("dut_queue_evidence")
    elif fec_metrics > 0 or optics_metrics > 0:
        final_class = "possible_link_health_issue"
        tags.append("dut_link_health_evidence")
    elif anomaly_count > 0:
        final_class = "transport_instability_with_dut_anomalies"
        tags.append("dut_anomaly_evidence")
    else:
        final_class = f"{base_class}_without_dut_evidence"

    seen = set()
    tags = [x for x in tags if not (x in seen or seen.add(x))]

    return {
        "base_classification": base_class,
        "final_classification": final_class,
        "tags": tags,
        "anomaly_count": anomaly_count,
        "snapshot_summary": snapshot_summary,
        "anomaly_summary": anomaly_summary,
    }


def build_report(
    root_cause: Dict[str, Any],
    fabric_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_index = build_fabric_evidence_index(fabric_evidence)

    results = []
    for hotspot in root_cause.get("hotspots_with_evidence", []):
        iface = hotspot.get("interface")
        fabric_item = evidence_index.get(iface, {})
        refined = refine_classification(hotspot, fabric_item)

        item = {
            "rx_port": hotspot.get("rx_port"),
            "device": hotspot.get("device"),
            "interface": iface,
            "ixia_location": hotspot.get("ixia_location"),
            "frame_delta": hotspot.get("frame_delta"),
            "retransmissions": hotspot.get("retransmissions"),
            "sequence_errors": hotspot.get("sequence_errors"),
            "max_latency_ns": hotspot.get("max_latency_ns"),
            "base_classification": refined["base_classification"],
            "final_classification": refined["final_classification"],
            "tags": refined["tags"],
            "evidence": hotspot.get("evidence", {}),
            "fabric_evidence": {
                "snapshot_summary": refined["snapshot_summary"],
                "anomaly_summary": refined["anomaly_summary"],
                "anomaly_count": refined["anomaly_count"],
                "sample_records": fabric_item.get("snapshot_records", [])[:10],
                "sample_anomalies": fabric_item.get("anomalies", [])[:10],
            },
        }
        results.append(item)

    results = sorted(
        results,
        key=lambda x: (
            safe_int(x.get("sequence_errors")),
            safe_int(x.get("retransmissions")),
            safe_int(x.get("frame_delta")),
        ),
        reverse=True,
    )

    conclusion = "No hotspot correlation could be built."
    if results:
        top = results[:3]
        conclusion = (
            "Deep congestion inspection prioritizes "
            + ", ".join(
                f"{x['rx_port']}->{x.get('device')} {x.get('interface')} ({x['final_classification']})"
                for x in top
            )
            + " based on RoCE transport symptoms and available DUT-side evidence."
        )

    return {
        "summary": {
            "top_hotspots": results[:5],
        },
        "results": results,
        "conclusion": conclusion,
    }


def render_text(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("DEEP CONGESTION INSPECTION SUMMARY")
    lines.append("")

    for item in report.get("summary", {}).get("top_hotspots", []):
        lines.append(
            f"  {item['rx_port']} -> {item.get('device')} {item.get('interface')} | "
            f"base={item.get('base_classification')} | final={item.get('final_classification')} | "
            f"delta={item.get('frame_delta')} | retx={item.get('retransmissions')} | "
            f"seqerr={item.get('sequence_errors')}"
        )
        fe = item.get("fabric_evidence", {})
        lines.append(
            f"    snapshot_summary={fe.get('snapshot_summary')} "
            f"anomaly_summary={fe.get('anomaly_summary')} "
            f"anomaly_count={fe.get('anomaly_count')}"
        )
    lines.append("")
    lines.append("CONCLUSION")
    lines.append(report.get("conclusion", ""))
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deep congestion inspection using root cause + fabric evidence")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--root-cause", required=True)
    parser.add_argument("--fabric-evidence", default=None)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        root_cause = load_json(args.root_cause)
        fabric_evidence = load_json(args.fabric_evidence)

        report = build_report(
            root_cause=root_cause,
            fabric_evidence=fabric_evidence,
        )

        outputs = default_output_paths(args.source_type, args.run_id)
        out_json = args.out_json or outputs["json"]
        out_txt = args.out_txt or outputs["txt"]

        write_json(out_json, report)
        write_text(out_txt, render_text(report))

        print(f"Deep congestion inspection JSON report : {out_json}")
        print(f"Deep congestion inspection text report : {out_txt}")
        print("")
        print("DEEP CONGESTION INSPECTION SUMMARY")
        for item in report.get("summary", {}).get("top_hotspots", [])[:5]:
            print(
                f"  {item['rx_port']:<12} -> "
                f"{(item.get('device') or 'unknown-device'):<15} "
                f"{(item.get('interface') or 'unknown-interface'):<15} "
                f"final={item.get('final_classification')}"
            )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
