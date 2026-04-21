import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


DEFAULT_IXIA_INVENTORY = os.path.join(os.path.dirname(__file__), "ixia_inventory.json")


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


def output_dir(source_type: str, run_id: str) -> str:
    out_dir = os.path.join("artifacts", f"{source_type}s", run_id, "traffic")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def default_output_paths(source_type: str, run_id: str) -> Dict[str, str]:
    out = output_dir(source_type, run_id)
    return {
        "json": os.path.join(out, "root_cause_correlation.json"),
        "txt": os.path.join(out, "root_cause_correlation.txt"),
    }


def build_ixia_port_mapping(inventory: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Supports a few likely inventory shapes.

    Preferred shape:
    {
      "port_map": [
        {
          "ixia_port_name": "Ethernet - 013",
          "ixia_location": "ix020-ares.englab.juniper.net/13",
          "device": "san-q5700-03",
          "interface": "et-6/0/2"
        }
      ]
    }

    Also supports:
    {
      "ports": [...]
    }
    """
    result: Dict[str, Dict[str, Any]] = {}

    candidates = []
    if isinstance(inventory.get("port_map"), list):
        candidates.extend(inventory["port_map"])
    if isinstance(inventory.get("ports"), list):
        candidates.extend(inventory["ports"])

    for item in candidates:
        port_name = (
            item.get("ixia_port_name")
            or item.get("port_name")
            or item.get("name")
        )
        if not port_name:
            continue

        result[port_name] = {
            "ixia_port_name": port_name,
            "ixia_location": item.get("ixia_location") or item.get("location"),
            "device": item.get("device") or item.get("switch"),
            "interface": item.get("interface") or item.get("switch_interface"),
            "line_speed": item.get("line_speed"),
            "link_state": item.get("link_state"),
        }

    return result


def infer_mapping_from_known_ports(port_name: str) -> Dict[str, Any]:
    """
    Fallback for your currently known mapping from conversation context.
    Only used if the inventory file does not already define it.
    """
    known = {
        "Ethernet - 013": {
            "device": "san-q5700-03",
            "interface": "et-6/0/2",
            "ixia_location": "ix020-ares.englab.juniper.net/13",
        },
        "Ethernet - 014": {
            "device": "san-q5700-03",
            "interface": "et-6/0/3",
            "ixia_location": "ix020-ares.englab.juniper.net/14",
        },
        "Ethernet - 001": {
            "device": "san-q5240-01",
            "interface": "et-0/0/0:0",
            "ixia_location": "ix020-ares.englab.juniper.net/1",
        },
        "Ethernet - 002": {
            "device": "san-q5240-02",
            "interface": "et-0/0/1:0",
            "ixia_location": "ix020-ares.englab.juniper.net/2",
        },
        "Ethernet - 003": {
            "device": "san-q5240-03",
            "interface": "et-0/0/0:0",
            "ixia_location": "ix020-ares.englab.juniper.net/3",
        },
        "Ethernet - 004": {
            "device": "san-q5240-03",
            "interface": "et-0/0/0:1",
            "ixia_location": "ix020-ares.englab.juniper.net/4",
        },
        "Ethernet - 005": {
            "device": "san-q5240-01",
            "interface": "et-0/0/0:1",
            "ixia_location": "ix020-ares.englab.juniper.net/5",
        },
        "Ethernet - 006": {
            "device": "san-q5240-02",
            "interface": "et-0/0/1:1",
            "ixia_location": "ix020-ares.englab.juniper.net/6",
        },
        "Ethernet - 007": {
            "device": "san-q5230-01",
            "interface": "et-0/0/30",
            "ixia_location": "ix020-ares.englab.juniper.net/7",
        },
        "Ethernet - 008": {
            "device": "san-q5230-01",
            "interface": "et-0/0/31",
            "ixia_location": "ix020-ares.englab.juniper.net/8",
        },
        "Ethernet - 009": {
            "device": "san-q5220-01",
            "interface": "et-0/0/0",
            "ixia_location": "ix020-ares.englab.juniper.net/9",
        },
        "Ethernet - 010": {
            "device": "san-q5220-01",
            "interface": "et-0/0/1",
            "ixia_location": "ix020-ares.englab.juniper.net/10",
        },
        "Ethernet - 011": {
            "device": "san-q5130-01",
            "interface": "et-0/0/0",
            "ixia_location": "ix020-ares.englab.juniper.net/11",
        },
        "Ethernet - 012": {
            "device": "san-q5130-01",
            "interface": "et-0/0/1",
            "ixia_location": "ix020-ares.englab.juniper.net/12",
        },
        "Ethernet - 015": {
            "device": "san-q5240-15",
            "interface": "et-0/0/1:0",
            "ixia_location": "ix020-ares.englab.juniper.net/15",
        },
        "Ethernet - 016": {
            "device": "san-q5240-q02",
            "interface": "et-0/0/1:0",
            "ixia_location": "ix020-ares.englab.juniper.net/16",
        },
    }
    return known.get(port_name, {})


def normalize_hotspot(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rx_port": item.get("rx_port"),
        "classification": item.get("classification"),
        "tags": item.get("tags", []),
        "score": safe_int(item.get("score")),
        "flow_count": safe_int(item.get("flow_count")),
        "frame_delta": safe_int(item.get("frame_delta")),
        "retransmissions": safe_int(item.get("retransmissions")),
        "sequence_errors": safe_int(item.get("sequence_errors")),
        "max_latency_ns": safe_int(item.get("max_latency_ns")),
        "highest_severity": item.get("highest_severity"),
        "verdict_count": safe_int(item.get("verdict_count")),
        "verdict_types": item.get("verdict_types", {}),
        "port_health": item.get("port_health", {}),
    }


def map_hotspots_to_dut(
    congestion: Dict[str, Any],
    port_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    items = []
    for raw in congestion.get("hotspot_analysis", []):
        h = normalize_hotspot(raw)
        rx_port = h["rx_port"]
        mapping = port_map.get(rx_port) or infer_mapping_from_known_ports(rx_port)

        items.append({
            **h,
            "ixia_location": mapping.get("ixia_location"),
            "device": mapping.get("device"),
            "interface": mapping.get("interface"),
            "line_speed": mapping.get("line_speed"),
            "link_state": mapping.get("link_state"),
        })

    return items


def correlate_problem_flows(
    congestion: Dict[str, Any],
    port_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    flows = []
    for item in congestion.get("top_problem_flows", []):
        tx_port = item.get("tx_port")
        rx_port = item.get("rx_port")

        tx_mapping = port_map.get(tx_port) or infer_mapping_from_known_ports(tx_port)
        rx_mapping = port_map.get(rx_port) or infer_mapping_from_known_ports(rx_port)

        flows.append({
            "flow": item.get("flow"),
            "tx_port": tx_port,
            "rx_port": rx_port,
            "tx_device": tx_mapping.get("device"),
            "tx_interface": tx_mapping.get("interface"),
            "rx_device": rx_mapping.get("device"),
            "rx_interface": rx_mapping.get("interface"),
            "frames_delta": safe_int(item.get("frames_delta")),
            "frames_retx": safe_int(item.get("frames_retx")),
            "frames_seqerror": safe_int(item.get("frames_seqerror")),
            "max_latency_ns": safe_int(item.get("max_latency_ns")),
        })

    return flows


def build_evidence(item: Dict[str, Any]) -> Dict[str, Any]:
    supporting = []
    missing = []
    next_checks = []

    if item["frame_delta"] > 10_000_000:
        supporting.append(f"high frame delta ({item['frame_delta']})")
    if item["retransmissions"] > 1_000_000:
        supporting.append(f"high retransmissions ({item['retransmissions']})")
    if item["sequence_errors"] > 1_000_000:
        supporting.append(f"high sequence errors ({item['sequence_errors']})")
    if item["max_latency_ns"] > 100_000:
        supporting.append(f"high latency spike ({item['max_latency_ns']} ns)")

    verdict_types = item.get("verdict_types", {})
    if verdict_types.get("ecn_activity", 0) > 0:
        supporting.append("ECN activity present")
    if verdict_types.get("cnp_activity", 0) > 0:
        supporting.append("CNP activity present")
    if verdict_types.get("nak_activity", 0) > 0:
        supporting.append("NAK activity present")
    if verdict_types.get("message_failed", 0) > 0:
        supporting.append("message failures present")

    ph = item.get("port_health", {})
    crc_errors = safe_int(ph.get("crc_errors"))
    fec_loss = safe_float(ph.get("fec_frame_loss_ratio"))
    pre_fec_ber = safe_float(ph.get("pre_fec_ber"))
    bad_icrc = safe_int(ph.get("roce_bad_icrc"))
    opcode_error = safe_int(ph.get("roce_opcode_error"))
    misdirected = safe_int(ph.get("misdirected_packets"))

    if crc_errors > 0:
        supporting.append(f"CRC errors present ({crc_errors})")
    if fec_loss > 0:
        supporting.append(f"FEC frame loss ratio present ({fec_loss})")
    if pre_fec_ber > 0:
        supporting.append(f"pre-FEC BER present ({pre_fec_ber})")
    if bad_icrc > 0:
        supporting.append(f"RoCE bad iCRC present ({bad_icrc})")
    if opcode_error > 0:
        supporting.append(f"RoCE opcode errors present ({opcode_error})")
    if misdirected > 0:
        supporting.append(f"misdirected packets present ({misdirected})")

    if (
        crc_errors == 0
        and fec_loss == 0
        and pre_fec_ber == 0
        and bad_icrc == 0
        and opcode_error == 0
        and misdirected == 0
    ):
        missing.append("no strong port-health signal from current Ixia port stats")

    if item.get("classification") == "transport_instability":
        next_checks.extend([
            "inspect DUT queue / congestion counters",
            "inspect DUT ECN / PFC / pause telemetry",
            "inspect DUT optics / FEC / interface telemetry",
        ])
    elif item.get("classification") == "port_health_signal":
        next_checks.extend([
            "inspect physical link health",
            "inspect optics DOM / lane diagnostics",
            "inspect FEC corrected / uncorrected counters",
        ])
    elif item.get("classification") == "fabric_congestion_signal":
        next_checks.extend([
            "inspect receiver-side queue buildup",
            "inspect congestion domains in fabric path",
            "inspect ECN / PFC reaction on mapped DUT ports",
        ])
    else:
        next_checks.extend([
            "inspect mapped DUT port telemetry",
            "inspect transport counters and congestion signals",
        ])

    return {
        "supporting_evidence": supporting,
        "missing_evidence": missing,
        "next_checks": next_checks,
    }


def build_summary(hotspots: List[Dict[str, Any]], flows: List[Dict[str, Any]]) -> Dict[str, Any]:
    top_hotspots = []
    for item in hotspots[:5]:
        top_hotspots.append({
            "rx_port": item["rx_port"],
            "device": item.get("device"),
            "interface": item.get("interface"),
            "classification": item.get("classification"),
            "frame_delta": item.get("frame_delta"),
            "retransmissions": item.get("retransmissions"),
            "sequence_errors": item.get("sequence_errors"),
            "max_latency_ns": item.get("max_latency_ns"),
            "tags": item.get("tags", []),
        })

    top_flows = flows[:10]

    return {
        "top_hotspots": top_hotspots,
        "top_problem_flows": top_flows,
    }


def build_conclusion(summary: Dict[str, Any]) -> str:
    hotspots = summary.get("top_hotspots", [])
    if not hotspots:
        return "No mapped root-cause hotspot could be derived from the available congestion artifacts."

    parts = []
    for item in hotspots[:3]:
        rx = item.get("rx_port")
        dev = item.get("device") or "unknown-device"
        intf = item.get("interface") or "unknown-interface"
        cls = item.get("classification")
        parts.append(f"{rx}->{dev} {intf} ({cls})")

    return (
        "Root-cause correlation indicates the strongest receiver-side hotspots map to "
        + ", ".join(parts)
        + ". These locations should be prioritized for DUT-side queue, ECN/PFC, optics, and FEC inspection."
    )


def render_text(report: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("ROOT CAUSE CORRELATION SUMMARY")
    lines.append("")

    lines.append("TOP HOTSPOTS")
    for item in report.get("summary", {}).get("top_hotspots", []):
        lines.append(
            f"  {item['rx_port']} -> {item.get('device')} {item.get('interface')} | "
            f"class={item.get('classification')} | "
            f"delta={item.get('frame_delta')} | "
            f"retx={item.get('retransmissions')} | "
            f"seqerr={item.get('sequence_errors')} | "
            f"max_lat_ns={item.get('max_latency_ns')}"
        )
    lines.append("")

    lines.append("TOP PROBLEM FLOWS")
    for item in report.get("summary", {}).get("top_problem_flows", []):
        lines.append(
            f"  {item.get('flow')} | "
            f"TX={item.get('tx_device')} {item.get('tx_interface')} | "
            f"RX={item.get('rx_device')} {item.get('rx_interface')} | "
            f"delta={item.get('frames_delta')} | "
            f"retx={item.get('frames_retx')} | "
            f"seqerr={item.get('frames_seqerror')} | "
            f"max_lat_ns={item.get('max_latency_ns')}"
        )
    lines.append("")

    lines.append("HOTSPOT EVIDENCE")
    for item in report.get("hotspots_with_evidence", []):
        lines.append(
            f"  {item['rx_port']} -> {item.get('device')} {item.get('interface')} | "
            f"class={item.get('classification')} | tags={item.get('tags', [])}"
        )
        for ev in item.get("evidence", {}).get("supporting_evidence", []):
            lines.append(f"    + {ev}")
        for ev in item.get("evidence", {}).get("missing_evidence", []):
            lines.append(f"    - {ev}")
        for ev in item.get("evidence", {}).get("next_checks", []):
            lines.append(f"    * {ev}")
    lines.append("")

    lines.append("CONCLUSION")
    lines.append(report.get("conclusion", ""))
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map congestion hotspots to DUT ports and build RCA summary")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--congestion", required=True)
    parser.add_argument("--inventory", default=DEFAULT_IXIA_INVENTORY)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        congestion = load_json(args.congestion)
        inventory = load_json(args.inventory)

        port_map = build_ixia_port_mapping(inventory)
        mapped_hotspots = map_hotspots_to_dut(congestion, port_map)
        mapped_flows = correlate_problem_flows(congestion, port_map)

        hotspots_with_evidence = []
        for item in mapped_hotspots:
            enriched = dict(item)
            enriched["evidence"] = build_evidence(item)
            hotspots_with_evidence.append(enriched)

        summary = build_summary(mapped_hotspots, mapped_flows)
        conclusion = build_conclusion(summary)

        report = {
            "summary": summary,
            "hotspots_with_evidence": hotspots_with_evidence,
            "port_mapping_used": port_map,
            "conclusion": conclusion,
        }

        outputs = default_output_paths(args.source_type, args.run_id)
        out_json = args.out_json or outputs["json"]
        out_txt = args.out_txt or outputs["txt"]

        write_json(out_json, report)
        write_text(out_txt, render_text(report))

        print(f"Root cause correlation JSON report : {out_json}")
        print(f"Root cause correlation text report : {out_txt}")
        print("")
        print("ROOT CAUSE CORRELATION SUMMARY")
        for item in summary.get("top_hotspots", [])[:5]:
            print(
                f"  {item['rx_port']:<12} -> "
                f"{(item.get('device') or 'unknown-device'):<15} "
                f"{(item.get('interface') or 'unknown-interface'):<15} "
                f"class={item.get('classification')}"
            )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
