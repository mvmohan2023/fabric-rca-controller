# controller/fabric_hotspot_ranker.py

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def build_output_paths(input_path: str) -> Tuple[str, str]:
    base, _ = os.path.splitext(input_path)
    return f"{base}_fabric_hotspots.json", f"{base}_fabric_hotspots.txt"


def rank_fabric_hotspots(analysis: Dict[str, Any], top_n: int = 10) -> Dict[str, Any]:
    hotspots = analysis.get("hotspots", []) or []

    sorted_queues = sorted(
        hotspots,
        key=lambda x: (x.get("score", 0), x.get("severity", "")),
        reverse=True,
    )

    interface_rollup: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
        lambda: {
            "node": None,
            "interface": None,
            "total_score": 0.0,
            "max_queue_score": 0.0,
            "hotspot_queues": 0,
            "critical_queues": 0,
            "high_queues": 0,
            "queues": [],
        }
    )

    node_rollup: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "node": None,
            "total_score": 0.0,
            "hotspot_queues": 0,
            "affected_interfaces": set(),
            "critical_queues": 0,
            "high_queues": 0,
        }
    )

    severity_counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "none": 0,
    }

    for item in sorted_queues:
        node = item.get("node")
        interface = item.get("interface")
        queue = item.get("queue")
        score = float(item.get("score", 0) or 0)
        severity = item.get("severity", "none")

        if severity not in severity_counts:
            severity_counts[severity] = 0
        severity_counts[severity] += 1

        intf_key = (node, interface)
        intf_entry = interface_rollup[intf_key]
        intf_entry["node"] = node
        intf_entry["interface"] = interface
        intf_entry["total_score"] += score
        intf_entry["max_queue_score"] = max(intf_entry["max_queue_score"], score)
        intf_entry["hotspot_queues"] += 1
        intf_entry["queues"].append(
            {
                "queue": queue,
                "score": score,
                "severity": severity,
                "probable_cause": item.get("probable_cause"),
                "signals": item.get("signals", {}),
            }
        )
        if severity == "critical":
            intf_entry["critical_queues"] += 1
        if severity == "high":
            intf_entry["high_queues"] += 1

        node_entry = node_rollup[node]
        node_entry["node"] = node
        node_entry["total_score"] += score
        node_entry["hotspot_queues"] += 1
        node_entry["affected_interfaces"].add(interface)
        if severity == "critical":
            node_entry["critical_queues"] += 1
        if severity == "high":
            node_entry["high_queues"] += 1

    top_queues = []
    for item in sorted_queues[:top_n]:
        top_queues.append(
            {
                "node": item.get("node"),
                "interface": item.get("interface"),
                "queue": item.get("queue"),
                "score": item.get("score"),
                "severity": item.get("severity"),
                "probable_cause": item.get("probable_cause"),
                "signals": item.get("signals", {}),
            }
        )

    top_interfaces = sorted(
        interface_rollup.values(),
        key=lambda x: (x["total_score"], x["max_queue_score"]),
        reverse=True,
    )[:top_n]

    top_nodes = sorted(
        (
            {
                **value,
                "affected_interfaces": sorted(list(value["affected_interfaces"])),
                "affected_interface_count": len(value["affected_interfaces"]),
            }
            for value in node_rollup.values()
        ),
        key=lambda x: x["total_score"],
        reverse=True,
    )[:top_n]

    return {
        "generated_at": utc_now_iso(),
        "run_id": analysis.get("run_id"),
        "profile": analysis.get("profile"),
        "input_snapshot": analysis.get("input_snapshot"),
        "total_hotspots": len(hotspots),
        "top_n": top_n,
        "severity_counts": severity_counts,
        "top_queues": top_queues,
        "top_interfaces": top_interfaces,
        "top_nodes": top_nodes,
    }


def render_text(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("FABRIC HOTSPOT RANKING")
    lines.append(f"  Run ID          : {result.get('run_id')}")
    lines.append(f"  Profile         : {result.get('profile')}")
    lines.append(f"  Input Snapshot  : {result.get('input_snapshot')}")
    lines.append(f"  Total Hotspots  : {result.get('total_hotspots')}")
    lines.append(f"  Top N           : {result.get('top_n')}")
    lines.append(f"  Severity Counts : {result.get('severity_counts')}")
    lines.append("")

    lines.append("TOP QUEUES")
    for idx, item in enumerate(result.get("top_queues", []), start=1):
        sig = item.get("signals", {})
        lines.append(
            f"  {idx}. node={item.get('node')} interface={item.get('interface')} "
            f"queue={item.get('queue')} score={item.get('score')} "
            f"severity={item.get('severity')} cause={item.get('probable_cause')}"
        )
        lines.append(
            f"     peak_buffer%={sig.get('peak_buffer_occupancy_percent')} "
            f"tail_drop={sig.get('tail_drop_pkts')} "
            f"red_drop={sig.get('red_drop_pkts')} "
            f"ecn_marked={sig.get('ecn_marked_pkts')}"
        )
    lines.append("")

    lines.append("TOP INTERFACES")
    for idx, item in enumerate(result.get("top_interfaces", []), start=1):
        lines.append(
            f"  {idx}. node={item.get('node')} interface={item.get('interface')} "
            f"total_score={round(item.get('total_score', 0), 2)} "
            f"hotspot_queues={item.get('hotspot_queues')} "
            f"critical_queues={item.get('critical_queues')} "
            f"high_queues={item.get('high_queues')}"
        )
    lines.append("")

    lines.append("TOP NODES")
    for idx, item in enumerate(result.get("top_nodes", []), start=1):
        lines.append(
            f"  {idx}. node={item.get('node')} "
            f"total_score={round(item.get('total_score', 0), 2)} "
            f"hotspot_queues={item.get('hotspot_queues')} "
            f"affected_interfaces={item.get('affected_interface_count')} "
            f"critical_queues={item.get('critical_queues')} "
            f"high_queues={item.get('high_queues')}"
        )
        lines.append(
            f"     interfaces={', '.join(item.get('affected_interfaces', []))}"
        )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank congestion hotspots across the whole fabric.")
    parser.add_argument("--input", required=True, help="Input congestion analysis JSON file")
    parser.add_argument("--top-n", type=int, default=10, help="Number of top entries to keep")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        analysis = load_json(args.input)
        result = rank_fabric_hotspots(analysis, top_n=args.top_n)
        json_out, txt_out = build_output_paths(args.input)
        write_json(json_out, result)
        write_text(txt_out, render_text(result))

        print(f"Fabric hotspot JSON report : {json_out}")
        print(f"Fabric hotspot text report : {txt_out}")
        print("")
        print("FABRIC HOTSPOT RANKING")
        print(f"  Run ID          : {result.get('run_id')}")
        print(f"  Profile         : {result.get('profile')}")
        print(f"  Input Snapshot  : {result.get('input_snapshot')}")
        print(f"  Total Hotspots  : {result.get('total_hotspots')}")
        print(f"  Top N           : {result.get('top_n')}")

        if result.get("top_queues"):
            top = result["top_queues"][0]
            print(
                f"  Top Queue       : node={top.get('node')} "
                f"interface={top.get('interface')} queue={top.get('queue')} "
                f"score={top.get('score')} severity={top.get('severity')}"
            )
        else:
            print("  Top Queue       : none")

        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
