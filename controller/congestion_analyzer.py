# controller/congestion_analyzer.py

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
import math

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_report(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def severity_from_score(score: float) -> str:
    if score >= 120:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 30:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def classify_cause(signals: Dict[str, Any]) -> str:
    if (signals.get("tail_drop_pkts", 0) or 0) > 0:
        return "queue-pressure-with-taildrop"
    if (signals.get("red_drop_pkts", 0) or 0) > 0:
        return "queue-pressure-with-red-drop"
    if (signals.get("ecn_marked_pkts", 0) or 0) > 0:
        return "queue-pressure-with-ecn"
    if (signals.get("pfc_activity", 0) or 0) > 0:
        return "pause-induced-congestion"
    if (signals.get("fec_uncorrectable_words", 0) or 0) > 0:
        return "fec-degradation"
    return "queue-pressure"


def safe_num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return 0.0


def analyze_congestion(report: Dict[str, Any]) -> Dict[str, Any]:
    all_records: List[Dict[str, Any]] = []
    for node_entry in report.get("nodes", []):
        all_records.extend(node_entry.get("normalized_records", []))

    interface_metrics: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(dict)
    queue_metrics: Dict[Tuple[str, str, int], Dict[str, float]] = defaultdict(dict)
    pfc_activity_map: Dict[Tuple[str, str], float] = defaultdict(float)

    for record in all_records:
        node = record.get("node")
        metric = record.get("metric")
        value = safe_num(record.get("value"))
        labels = record.get("labels", {}) or {}
        group = labels.get("group")
        interface = labels.get("interface")

        if not node or not interface or not metric:
            continue

        if group == "qmon-queue":
            queue = labels.get("queue")
            if queue is not None:
                try:
                    queue = int(queue)
                except Exception:
                    continue
                queue_metrics[(node, interface, queue)][metric] = value

        elif group in ("errors", "ethernet", "interface", "ipv4", "ipv6"):
            interface_metrics[(node, interface)][metric] = value

        elif group == "pfc":
            priority = labels.get("priority")
            key = (node, interface)
            if metric in ("in-pkts", "out-pkts"):
                pfc_activity_map[key] += value

    hotspots: List[Dict[str, Any]] = []

    for (node, interface, queue), metrics in queue_metrics.items():
        peak_pct = safe_num(metrics.get("peak-buffer-occupancy-percent"))
        tail_drop = safe_num(metrics.get("tail-drop-pkts"))
        red_drop = safe_num(metrics.get("red-drop-pkts"))
        ecn_pkts = safe_num(metrics.get("ecn-marked-pkts"))


        score = (
            (peak_pct * 2.0)
            + (tail_drop * 5.0)
            + (red_drop * 4.0)
            + (math.log10(ecn_pkts + 1) * 10.0)
        )
        intf = interface_metrics.get((node, interface), {})
        in_resource_drops = safe_num(intf.get("in-resource-drops"))
        out_ecn_ce = safe_num(intf.get("out-ecn-ce-marked-pkts"))
        fec_corr = safe_num(intf.get("fec-corrected-words"))
        fec_uncorr = safe_num(intf.get("fec-uncorrectable-words"))
        pfc_activity = safe_num(pfc_activity_map.get((node, interface)))

        if in_resource_drops > 0:
            score += 20
        if out_ecn_ce > 0:
            score += 15
        if pfc_activity > 0:
            score += 15
        if fec_uncorr > 0:
            score += 10
        elif fec_corr > 1000:
            score += 5

        if score <= 0:
            continue

        signals = {
            "peak_buffer_occupancy_percent": peak_pct,
            "tail_drop_pkts": tail_drop,
            "red_drop_pkts": red_drop,
            "ecn_marked_pkts": ecn_pkts,
            "in_resource_drops": in_resource_drops,
            "out_ecn_ce_marked_pkts": out_ecn_ce,
            "fec_corrected_words": fec_corr,
            "fec_uncorrectable_words": fec_uncorr,
            "pfc_activity": pfc_activity,
        }

        hotspots.append(
            {
                "node": node,
                "interface": interface,
                "queue": queue,
                "score": round(score, 2),
                "severity": severity_from_score(score),
                "signals": signals,
                "probable_cause": classify_cause(signals),
            }
        )

    hotspots.sort(key=lambda x: x["score"], reverse=True)

    return {
        "generated_at": utc_now_iso(),
        "run_id": report.get("run_id"),
        "profile": report.get("profile"),
        "input_snapshot": report.get("snapshot_name"),
        "hotspots": hotspots,
        "total_hotspots": len(hotspots),
    }


def render_text_summary(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("CONGESTION ANALYSIS SUMMARY")
    lines.append(f"  Run ID          : {result.get('run_id')}")
    lines.append(f"  Profile         : {result.get('profile')}")
    lines.append(f"  Input Snapshot  : {result.get('input_snapshot')}")
    lines.append(f"  Total Hotspots  : {result.get('total_hotspots')}")
    lines.append("")

    hotspots = result.get("hotspots", [])
    if not hotspots:
        lines.append("No congestion hotspots detected.")
        lines.append("")
        return "\n".join(lines)

    lines.append("TOP HOTSPOTS")
    for idx, hotspot in enumerate(hotspots[:20], start=1):
        sig = hotspot.get("signals", {})
        lines.append(
            f"  {idx}. node={hotspot.get('node')} "
            f"interface={hotspot.get('interface')} "
            f"queue={hotspot.get('queue')} "
            f"severity={hotspot.get('severity')} "
            f"score={hotspot.get('score')}"
        )
        lines.append(
            f"     peak_buffer%={sig.get('peak_buffer_occupancy_percent')} "
            f"tail_drop={sig.get('tail_drop_pkts')} "
            f"red_drop={sig.get('red_drop_pkts')} "
            f"ecn_marked={sig.get('ecn_marked_pkts')}"
        )
        lines.append(
            f"     in_resource_drops={sig.get('in_resource_drops')} "
            f"out_ecn_ce={sig.get('out_ecn_ce_marked_pkts')} "
            f"pfc_activity={sig.get('pfc_activity')} "
            f"cause={hotspot.get('probable_cause')}"
        )
    lines.append("")

    return "\n".join(lines)


def build_output_paths(input_path: str) -> Tuple[str, str]:
    base, _ = os.path.splitext(input_path)
    json_out = f"{base}_congestion_analysis.json"
    txt_out = f"{base}_congestion_analysis.txt"
    return json_out, txt_out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze telemetry snapshot for congestion hotspots.")
    parser.add_argument("--input", required=True, help="Input telemetry JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        report = load_report(args.input)
        result = analyze_congestion(report)
        json_out, txt_out = build_output_paths(args.input)

        write_json(json_out, result)
        write_text(txt_out, render_text_summary(result))

        print(f"Congestion JSON report : {json_out}")
        print(f"Congestion text report : {txt_out}")
        print("")
        print("CONGESTION ANALYSIS SUMMARY")
        print(f"  Run ID          : {result.get('run_id')}")
        print(f"  Profile         : {result.get('profile')}")
        print(f"  Input Snapshot  : {result.get('input_snapshot')}")
        print(f"  Total Hotspots  : {result.get('total_hotspots')}")

        hotspots = result.get("hotspots", [])
        if hotspots:
            top = hotspots[0]
            print(
                f"  Top Hotspot     : node={top.get('node')} "
                f"interface={top.get('interface')} queue={top.get('queue')} "
                f"severity={top.get('severity')} score={top.get('score')}"
            )
        else:
            print("  Top Hotspot     : none")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
