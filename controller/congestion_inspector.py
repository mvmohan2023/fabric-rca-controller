import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


def load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
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
        "json": os.path.join(out, "congestion_inspection.json"),
        "txt": os.path.join(out, "congestion_inspection.txt"),
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


def safe_float(value: Any) -> float:
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def build_port_stats_index(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for row in snapshot.get("rows", []):
        port_name = row.get("Port Name") or row.get("port_name")
        if port_name:
            idx[port_name] = row
    return idx


def normalize_hotspot_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rx_port": item.get("rx_port"),
        "flow_count": safe_int(item.get("flow_count")),
        "frame_delta": safe_int(item.get("frame_delta") or item.get("sum_frames_delta")),
        "retransmissions": safe_int(item.get("retransmissions") or item.get("sum_frames_retx")),
        "sequence_errors": safe_int(item.get("sequence_errors") or item.get("sum_frames_seqerror")),
        "max_latency_ns": safe_int(item.get("max_latency_ns")),
        "message_failed": safe_int(item.get("sum_messages_failed")),
        "ecn_ce_rx": safe_int(item.get("sum_ecn_ce_rx")),
        "cnp_tx": safe_int(item.get("sum_cnp_tx")),
        "cnp_rx": safe_int(item.get("sum_cnp_rx")),
        "nak_tx": safe_int(item.get("sum_nak_tx")),
        "nak_rx": safe_int(item.get("sum_nak_rx")),
    }


def classify_hotspot(h: Dict[str, Any], post_port_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    rx_port = h["rx_port"]
    port_row = post_port_stats.get(rx_port, {})

    crc_errors = safe_int(port_row.get("CRC Errors") or port_row.get("crc_errors"))
    fec_loss = safe_float(port_row.get("FEC Frame Loss Ratio") or port_row.get("fec_frame_loss_ratio"))
    pre_fec_ber = safe_float(port_row.get("pre FEC Bit Error Ratio") or port_row.get("pre_fec_ber"))
    bad_icrc = safe_int(port_row.get("RoCEv2 Bad iCRC Count") or port_row.get("roce_bad_icrc"))
    opcode_error = safe_int(port_row.get("RoCEv2 OpCode Error Count") or port_row.get("roce_opcode_error"))
    misdirected = safe_int(port_row.get("Misdirected Packet Count") or port_row.get("misdirected_packets"))

    tags: List[str] = []
    score = 0

    if h["frame_delta"] > 10_000_000:
        tags.append("fabric_congestion_signal")
        score += 2

    if h["retransmissions"] > 1_000_000:
        tags.append("transport_instability")
        score += 3

    if h["sequence_errors"] > 1_000_000:
        tags.append("transport_instability")
        score += 3

    if h["ecn_ce_rx"] > 0 or h["cnp_tx"] > 0 or h["cnp_rx"] > 0:
        tags.append("receiver_hotspot")
        score += 2

    if h["nak_tx"] > 0 or h["nak_rx"] > 0:
        tags.append("transport_instability")
        score += 2

    if h["max_latency_ns"] > 100_000:
        tags.append("latency_spike")
        score += 1

    if crc_errors > 0 or fec_loss > 0 or pre_fec_ber > 0 or bad_icrc > 0 or opcode_error > 0 or misdirected > 0:
        tags.append("port_health_signal")
        score += 3

    # de-duplicate while preserving order
    seen = set()
    tags = [x for x in tags if not (x in seen or seen.add(x))]

    primary = "receiver_hotspot"
    if "port_health_signal" in tags:
        primary = "port_health_signal"
    elif "transport_instability" in tags:
        primary = "transport_instability"
    elif "fabric_congestion_signal" in tags:
        primary = "fabric_congestion_signal"
    elif "receiver_hotspot" in tags:
        primary = "receiver_hotspot"

    return {
        "rx_port": rx_port,
        "classification": primary,
        "tags": tags,
        "score": score,
        "port_health": {
            "crc_errors": crc_errors,
            "fec_frame_loss_ratio": fec_loss,
            "pre_fec_ber": pre_fec_ber,
            "roce_bad_icrc": bad_icrc,
            "roce_opcode_error": opcode_error,
            "misdirected_packets": misdirected,
        },
    }


def correlate(
    verdict: Dict[str, Any],
    deep: Dict[str, Any],
    hotspot: Dict[str, Any],
    pre_port_stats_raw: Dict[str, Any],
    post_port_stats_raw: Dict[str, Any],
) -> Dict[str, Any]:
    pre_port_stats = build_port_stats_index(pre_port_stats_raw)
    post_port_stats = build_port_stats_index(post_port_stats_raw)

    hotspot_rows = [
        normalize_hotspot_entry(x)
        for x in hotspot.get("worst_rx_ports", [])
    ]

    if not hotspot_rows and deep.get("rx_rollup"):
        hotspot_rows = [
            normalize_hotspot_entry(x)
            for x in deep.get("rx_rollup", [])[:10]
        ]

    classifications = [
        classify_hotspot(h, post_port_stats)
        for h in hotspot_rows
    ]

    by_rx = verdict.get("rx_port_rollup", {})

    hotspot_analysis = []
    for h in hotspot_rows:
        rx = h["rx_port"]
        cls = next((x for x in classifications if x["rx_port"] == rx), {})
        verdict_rollup = by_rx.get(rx, {})
        hotspot_analysis.append({
            "rx_port": rx,
            "flow_count": h["flow_count"],
            "frame_delta": h["frame_delta"],
            "retransmissions": h["retransmissions"],
            "sequence_errors": h["sequence_errors"],
            "max_latency_ns": h["max_latency_ns"],
            "classification": cls.get("classification"),
            "tags": cls.get("tags", []),
            "score": cls.get("score", 0),
            "verdict_count": verdict_rollup.get("count", 0),
            "highest_severity": verdict_rollup.get("highest_severity"),
            "verdict_types": verdict_rollup.get("by_type", {}),
            "port_health": cls.get("port_health", {}),
        })

    hotspot_analysis = sorted(
        hotspot_analysis,
        key=lambda x: (
            x["score"],
            x["sequence_errors"],
            x["retransmissions"],
            x["frame_delta"],
            x["max_latency_ns"],
        ),
        reverse=True,
    )

    top_problem_flows = hotspot.get("top_problem_flows", [])
    if not top_problem_flows and deep:
        top_problem_flows = []
        for row in deep.get("top_by_seqerror", [])[:15]:
            top_problem_flows.append({
                "flow": row.get("flow_key"),
                "rx_port": row.get("rx_port"),
                "tx_port": row.get("tx_port"),
                "frames_delta": row.get("frames_delta"),
                "frames_retx": row.get("frames_retx"),
                "frames_seqerror": row.get("frames_seqerror"),
                "max_latency_ns": row.get("max_latency_ns"),
            })

    summary = {
        "verdict": "fail" if verdict.get("summary", {}).get("total_findings", 0) > 0 else "pass",
        "total_findings": verdict.get("summary", {}).get("total_findings", 0),
        "critical_findings": verdict.get("summary", {}).get("by_severity", {}).get("critical", 0),
        "warning_findings": verdict.get("summary", {}).get("by_severity", {}).get("warning", 0),
        "top_hotspots": hotspot_analysis[:5],
        "top_problem_flows": top_problem_flows[:10],
    }

    return {
        "summary": summary,
        "hotspot_analysis": hotspot_analysis,
        "top_problem_flows": top_problem_flows,
        "inputs": {
            "verdict_summary": verdict.get("summary", {}),
            "deep_hotspot_summary": deep.get("hotspot_summary", {}),
        },
    }


def build_conclusion(report: Dict[str, Any]) -> str:
    hotspots = report.get("summary", {}).get("top_hotspots", [])
    flows = report.get("summary", {}).get("top_problem_flows", [])

    if not hotspots:
        return "No congestion hotspot was identified from the provided artifacts."

    top_ports = ", ".join(h["rx_port"] for h in hotspots[:3])
    top_classes = ", ".join(
        f"{h['rx_port']}={h['classification']}" for h in hotspots[:3]
    )

    top_flow_desc = ""
    if flows:
        top_flow_desc = "; top problem flows include " + ", ".join(
            f"{f.get('tx_port')}->{f.get('rx_port')}" for f in flows[:3]
        )

    return (
        f"Congestion inspection indicates the strongest receiver-side hotspots are {top_ports}. "
        f"Primary classifications are {top_classes}. "
        f"The evidence combines frame delta, retransmission, sequence error, latency, and ECN/CNP/NAK activity"
        f"{top_flow_desc}."
    )


def render_text(report: Dict[str, Any]) -> str:
    lines: List[str] = []

    summary = report.get("summary", {})
    lines.append("CONGESTION INSPECTION SUMMARY")
    lines.append(f"  Verdict              : {summary.get('verdict')}")
    lines.append(f"  Total findings       : {summary.get('total_findings')}")
    lines.append(f"  Critical findings    : {summary.get('critical_findings')}")
    lines.append(f"  Warning findings     : {summary.get('warning_findings')}")
    lines.append("")

    lines.append("TOP HOTSPOTS")
    for item in summary.get("top_hotspots", []):
        lines.append(
            f"  {item['rx_port']} | class={item['classification']} | "
            f"delta={item['frame_delta']} | retx={item['retransmissions']} | "
            f"seqerr={item['sequence_errors']} | max_lat_ns={item['max_latency_ns']} | "
            f"tags={item['tags']}"
        )
    lines.append("")

    lines.append("TOP PROBLEM FLOWS")
    for item in summary.get("top_problem_flows", []):
        lines.append(
            f"  {item.get('flow')} | delta={item.get('frames_delta')} | "
            f"retx={item.get('frames_retx')} | seqerr={item.get('frames_seqerror')} | "
            f"max_lat_ns={item.get('max_latency_ns')}"
        )
    lines.append("")

    lines.append("DETAILED HOTSPOT ANALYSIS")
    for item in report.get("hotspot_analysis", []):
        lines.append(json.dumps(item, sort_keys=True))
    lines.append("")

    lines.append("CONCLUSION")
    lines.append(build_conclusion(report))
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Correlate RoCE/Ixia artifacts into congestion inspection summary")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--deep", required=True)
    parser.add_argument("--hotspot", required=True)
    parser.add_argument("--pre-port-stats", default=None)
    parser.add_argument("--post-port-stats", default=None)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        verdict = load_json(args.verdict)
        deep = load_json(args.deep)
        hotspot = load_json(args.hotspot)
        pre_port_stats = load_json(args.pre_port_stats) if args.pre_port_stats else {}
        post_port_stats = load_json(args.post_port_stats) if args.post_port_stats else {}

        report = correlate(
            verdict=verdict,
            deep=deep,
            hotspot=hotspot,
            pre_port_stats_raw=pre_port_stats,
            post_port_stats_raw=post_port_stats,
        )
        report["conclusion"] = build_conclusion(report)

        outputs = default_output_paths(args.source_type, args.run_id)
        out_json = args.out_json or outputs["json"]
        out_txt = args.out_txt or outputs["txt"]

        write_json(out_json, report)
        write_text(out_txt, render_text(report))

        print(f"Congestion inspection JSON report : {out_json}")
        print(f"Congestion inspection text report : {out_txt}")
        print("")
        print("CONGESTION INSPECTION SUMMARY")
        for item in report.get("summary", {}).get("top_hotspots", [])[:5]:
            print(
                f"  {item['rx_port']:<12} "
                f"class={item['classification']:<22} "
                f"delta={item['frame_delta']:<12} "
                f"retx={item['retransmissions']:<12} "
                f"seqerr={item['sequence_errors']:<12}"
            )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
