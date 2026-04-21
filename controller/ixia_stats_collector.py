# controller/ixia_stats_collector.py

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import time
from controller.ixia_client import IxiaClient, IxiaClientError

DEFAULT_IXIA_INVENTORY = os.path.join(os.path.dirname(__file__), "ixia_inventory.json")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ixia_output_dir(source_type: str, run_id: str) -> str:
    out_dir = os.path.join("artifacts", f"{source_type}s", run_id, "traffic")
    ensure_dir(out_dir)
    return out_dir


def snapshot_paths(source_type: str, run_id: str, snapshot_name: str) -> Dict[str, str]:
    out_dir = ixia_output_dir(source_type, run_id)
    return {
        "json": os.path.join(out_dir, f"{snapshot_name}_ixia_port_stats.json"),
        "txt": os.path.join(out_dir, f"{snapshot_name}_ixia_port_stats.txt"),
    }


def discovery_paths(source_type: str, run_id: str, snapshot_name: str) -> Dict[str, str]:
    out_dir = ixia_output_dir(source_type, run_id)
    return {
        "json": os.path.join(out_dir, f"{snapshot_name}_ixia_discovery.json"),
    }


def safe_int(value: Any) -> Optional[int]:
    if value in ("", None):
        return None
    try:
        if isinstance(value, str) and ("E" in value or "e" in value or "." in value):
            return int(float(value))
        return int(value)
    except Exception:
        return None


def safe_float(value: Any) -> Optional[float]:
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def normalize_port_stats(page: Dict[str, Any], inventory_ports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    captions = page.get("columnCaptions", [])
    rows = page.get("pageValues", [])

    inventory_by_location = {
        item.get("ixia_port"): item for item in inventory_ports
    }

    normalized: List[Dict[str, Any]] = []

    for entry in rows:
        if not entry or not isinstance(entry, list) or not entry[0]:
            continue

        row = entry[0]
        row_map = {}
        for idx, caption in enumerate(captions):
            value = row[idx] if idx < len(row) else None
            row_map[caption] = value

        ixia_port = row_map.get("Stat Name")
        inventory_match = inventory_by_location.get(ixia_port, {})

        record = {
            "ixia_port": ixia_port,
            "port_name": row_map.get("Port Name"),
            "line_speed": row_map.get("Line Speed"),
            "link_state": row_map.get("Link State"),
            "switch": inventory_match.get("switch"),
            "switch_interface": inventory_match.get("switch_interface"),
            "expected_link_state": inventory_match.get("expected_link_state"),
            "expected_line_speed": inventory_match.get("line_speed"),
            "metrics": {
                "frames_tx": safe_int(row_map.get("Frames Tx.")),
                "valid_frames_rx": safe_int(row_map.get("Valid Frames Rx.")),
                "frames_tx_rate": safe_int(row_map.get("Frames Tx. Rate")),
                "valid_frames_rx_rate": safe_int(row_map.get("Valid Frames Rx. Rate")),
                "bytes_tx": safe_int(row_map.get("Bytes Tx.")),
                "bytes_rx": safe_int(row_map.get("Bytes Rx.")),
                "bits_sent": safe_int(row_map.get("Bits Sent")),
                "bits_received": safe_int(row_map.get("Bits Received")),
                "bytes_tx_rate": safe_int(row_map.get("Bytes Tx. Rate")),
                "tx_rate_bps": safe_int(row_map.get("Tx. Rate (bps)")),
                "tx_rate_kbps": safe_float(row_map.get("Tx. Rate (Kbps)")),
                "tx_rate_mbps": safe_float(row_map.get("Tx. Rate (Mbps)")),
                "bytes_rx_rate": safe_int(row_map.get("Bytes Rx. Rate")),
                "rx_rate_bps": safe_int(row_map.get("Rx. Rate (bps)")),
                "rx_rate_kbps": safe_float(row_map.get("Rx. Rate (Kbps)")),
                "rx_rate_mbps": safe_float(row_map.get("Rx. Rate (Mbps)")),
                "scheduled_frames_tx": safe_int(row_map.get("Scheduled Frames Tx.")),
                "scheduled_frames_tx_rate": safe_int(row_map.get("Scheduled Frames Tx. Rate")),
                "control_frames_tx": safe_int(row_map.get("Control Frames Tx")),
                "control_frames_rx": safe_int(row_map.get("Control Frames Rx")),
                "misdirected_packet_count": safe_int(row_map.get("Misdirected Packet Count")),
                "crc_errors": safe_int(row_map.get("CRC Errors")),
                "oversize": safe_int(row_map.get("Oversize")),
                "fragments": safe_int(row_map.get("Fragments")),
                "undersize": safe_int(row_map.get("Undersize")),
                "fec_frame_loss_ratio": safe_float(row_map.get("FEC Frame Loss Ratio")),
                "pre_fec_bit_error_ratio": safe_float(row_map.get("pre FEC Bit Error Ratio")),
                "rocev2_opcode_error_count": safe_int(row_map.get("RoCEv2 OpCode Error Count")),
                "rocev2_bad_icrc_count": safe_int(row_map.get("RoCEv2 Bad iCRC Count")),
            },
            "raw_row": row_map,
        }

        normalized.append(record)

    return normalized


def build_summary(normalized_ports: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_ports = len(normalized_ports)
    link_up = sum(1 for p in normalized_ports if p.get("link_state") == "Link Up")
    expected_up_mismatch = []
    low_or_zero_rx = []
    crc_or_fec_issues = []

    for port in normalized_ports:
        metrics = port.get("metrics", {})

        if port.get("expected_link_state") and port.get("link_state") != port.get("expected_link_state"):
            expected_up_mismatch.append({
                "ixia_port": port.get("ixia_port"),
                "switch": port.get("switch"),
                "switch_interface": port.get("switch_interface"),
                "expected_link_state": port.get("expected_link_state"),
                "actual_link_state": port.get("link_state"),
            })

        rx_rate = metrics.get("valid_frames_rx_rate")
        tx_rate = metrics.get("frames_tx_rate")
        if (tx_rate or 0) > 0 and (rx_rate is None or rx_rate == 0):
            low_or_zero_rx.append({
                "ixia_port": port.get("ixia_port"),
                "switch": port.get("switch"),
                "switch_interface": port.get("switch_interface"),
                "frames_tx_rate": tx_rate,
                "valid_frames_rx_rate": rx_rate,
            })

        if any([
            (metrics.get("crc_errors") or 0) > 0,
            (metrics.get("misdirected_packet_count") or 0) > 0,
            (metrics.get("fec_frame_loss_ratio") or 0.0) > 0,
            (metrics.get("pre_fec_bit_error_ratio") or 0.0) > 0,
            (metrics.get("rocev2_opcode_error_count") or 0) > 0,
            (metrics.get("rocev2_bad_icrc_count") or 0) > 0,
        ]):
            crc_or_fec_issues.append({
                "ixia_port": port.get("ixia_port"),
                "switch": port.get("switch"),
                "switch_interface": port.get("switch_interface"),
                "crc_errors": metrics.get("crc_errors"),
                "misdirected_packet_count": metrics.get("misdirected_packet_count"),
                "fec_frame_loss_ratio": metrics.get("fec_frame_loss_ratio"),
                "pre_fec_bit_error_ratio": metrics.get("pre_fec_bit_error_ratio"),
                "rocev2_opcode_error_count": metrics.get("rocev2_opcode_error_count"),
                "rocev2_bad_icrc_count": metrics.get("rocev2_bad_icrc_count"),
            })

    return {
        "total_ports": total_ports,
        "link_up_ports": link_up,
        "expected_link_state_mismatch_count": len(expected_up_mismatch),
        "zero_or_missing_rx_count": len(low_or_zero_rx),
        "crc_fec_issue_count": len(crc_or_fec_issues),
        "expected_link_state_mismatches": expected_up_mismatch,
        "zero_or_missing_rx_ports": low_or_zero_rx,
        "crc_fec_issue_ports": crc_or_fec_issues,
    }


def render_text_report(report: Dict[str, Any]) -> str:
    summary = report.get("summary", {})
    ports = report.get("normalized_ports", [])

    lines: List[str] = []
    lines.append("IXIA PORT STATISTICS SUMMARY")
    lines.append(f"  Snapshot time                  : {report.get('collected_at')}")
    lines.append(f"  API server                     : {report.get('api_server')}")
    lines.append(f"  Session ID                     : {report.get('session_id')}")
    lines.append(f"  Total ports                    : {summary.get('total_ports', 0)}")
    lines.append(f"  Link Up ports                  : {summary.get('link_up_ports', 0)}")
    lines.append(f"  Expected link mismatches       : {summary.get('expected_link_state_mismatch_count', 0)}")
    lines.append(f"  Zero/missing RX ports          : {summary.get('zero_or_missing_rx_count', 0)}")
    lines.append(f"  CRC/FEC issue ports            : {summary.get('crc_fec_issue_count', 0)}")
    lines.append("")

    if summary.get("expected_link_state_mismatches"):
        lines.append("EXPECTED LINK STATE MISMATCHES")
        for item in summary["expected_link_state_mismatches"]:
            lines.append(
                f"  {item['ixia_port']} -> {item['switch']} {item['switch_interface']} "
                f"expected={item['expected_link_state']} actual={item['actual_link_state']}"
            )
        lines.append("")

    if summary.get("zero_or_missing_rx_ports"):
        lines.append("ZERO OR MISSING RX PORTS")
        for item in summary["zero_or_missing_rx_ports"]:
            lines.append(
                f"  {item['ixia_port']} -> {item['switch']} {item['switch_interface']} "
                f"tx_rate={item['frames_tx_rate']} rx_rate={item['valid_frames_rx_rate']}"
            )
        lines.append("")

    if summary.get("crc_fec_issue_ports"):
        lines.append("CRC / FEC / RoCE ISSUE PORTS")
        for item in summary["crc_fec_issue_ports"]:
            lines.append(
                f"  {item['ixia_port']} -> {item['switch']} {item['switch_interface']} "
                f"crc={item['crc_errors']} misdirected={item['misdirected_packet_count']} "
                f"fec_loss_ratio={item['fec_frame_loss_ratio']} pre_fec_ber={item['pre_fec_bit_error_ratio']} "
                f"roce_opcode={item['rocev2_opcode_error_count']} roce_icrc={item['rocev2_bad_icrc_count']}"
            )
        lines.append("")

    lines.append("PORT DETAILS")
    for port in ports:
        metrics = port.get("metrics", {})
        lines.append(
            f"  {port.get('ixia_port')} | {port.get('port_name')} | "
            f"{port.get('switch')} {port.get('switch_interface')} | "
            f"link={port.get('link_state')} | "
            f"tx_rate={metrics.get('frames_tx_rate')} | "
            f"rx_rate={metrics.get('valid_frames_rx_rate')} | "
            f"crc={metrics.get('crc_errors')} | "
            f"fec_loss_ratio={metrics.get('fec_frame_loss_ratio')} | "
            f"pre_fec_ber={metrics.get('pre_fec_bit_error_ratio')}"
        )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect and normalize Ixia Port Statistics")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--inventory", default=DEFAULT_IXIA_INVENTORY)
    parser.add_argument("--api-server", default=None)
    parser.add_argument("--session-id", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--verify-tls", action="store_true")
    parser.add_argument("--with-discovery", action="store_true", help="also save discovery snapshot")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        inventory = json.load(open(args.inventory))
        api_server = args.api_server or inventory.get("ixnetwork_api_server")
        if not api_server:
            raise IxiaClientError("api server not provided and not found in inventory")

        client = IxiaClient(
            api_server=api_server,
            inventory_path=args.inventory,
            timeout=args.timeout,
            verify_tls=args.verify_tls,
        )

        session_id = client.resolve_session_id(args.session_id)

        port_stats = client.get_port_statistics(session_id)
        page = port_stats.get("page", {})
        normalized_ports = normalize_port_stats(page, client.get_inventory_ports())
        summary = build_summary(normalized_ports)

        report = {
            "collected_at": utc_now_iso(),
            "api_server": api_server,
            "session_id": session_id,
            "snapshot_name": args.snapshot_name,
            "source_type": args.source_type,
            "summary": summary,
            "column_captions": page.get("columnCaptions", []),
            "normalized_ports": normalized_ports,
            "raw_statistics_view": port_stats,
        }

        out_paths = snapshot_paths(args.source_type, args.run_id, args.snapshot_name)
        with open(out_paths["json"], "w") as f:
            json.dump(report, f, indent=2)

        with open(out_paths["txt"], "w") as f:
            f.write(render_text_report(report))

        if args.with_discovery:
            discovery = client.build_discovery_snapshot(session_id)
            disc_path = discovery_paths(args.source_type, args.run_id, args.snapshot_name)["json"]
            with open(disc_path, "w") as f:
                json.dump(discovery, f, indent=2)

        print(f"Ixia port stats JSON report : {out_paths['json']}")
        print(f"Ixia port stats text report : {out_paths['txt']}")
        print("")
        print("IXIA PORT STATISTICS SUMMARY")
        print(f"  Total ports              : {summary.get('total_ports', 0)}")
        print(f"  Link Up ports            : {summary.get('link_up_ports', 0)}")
        print(f"  Link mismatches          : {summary.get('expected_link_state_mismatch_count', 0)}")
        print(f"  Zero/missing RX ports    : {summary.get('zero_or_missing_rx_count', 0)}")
        print(f"  CRC/FEC issue ports      : {summary.get('crc_fec_issue_count', 0)}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
