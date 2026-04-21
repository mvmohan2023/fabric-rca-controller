# controller/ixia_live_monitor.py

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from controller.ixia_client import IxiaClient, IxiaClientError


DEFAULT_IXIA_INVENTORY = os.path.join(os.path.dirname(__file__), "ixia_inventory.json")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def output_dir(source_type: str, run_id: str) -> str:
    out_dir = os.path.join("artifacts", f"{source_type}s", run_id, "traffic")
    ensure_dir(out_dir)
    return out_dir


def output_paths(source_type: str, run_id: str, snapshot_name: str) -> Dict[str, str]:
    out = output_dir(source_type, run_id)
    return {
        "json": os.path.join(out, f"{snapshot_name}_ixia_live_monitor.json"),
        "txt": os.path.join(out, f"{snapshot_name}_ixia_live_monitor.txt"),
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


def normalize_value(value: Any) -> Any:
    if value in ("", None):
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        v = value.strip()
        try:
            if "." in v or "E" in v or "e" in v:
                return float(v)
            return int(v)
        except Exception:
            return v
    return value


def page_to_rows(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    captions = page.get("columnCaptions", [])
    rows = page.get("pageValues", [])
    normalized: List[Dict[str, Any]] = []

    for entry in rows:
        if not entry or not isinstance(entry, list) or not entry[0]:
            continue
        row = entry[0]
        row_map: Dict[str, Any] = {}
        for idx, caption in enumerate(captions):
            row_map[caption] = normalize_value(row[idx] if idx < len(row) else None)
        normalized.append(row_map)

    return normalized


def get_view_rows(client: IxiaClient, session_id: int, view_name: str, page_size: int = 50) -> List[Dict[str, Any]]:
    data = client.get_statistics_view_rows(view_name, session_id, page_size=page_size)
    return page_to_rows(data.get("page", {}))

def build_flow_key(row: Dict[str, Any]) -> str:
    return f"{row.get('Tx Port')} -> {row.get('Rx Port')} | {row.get('Flow Name')}"

def analyze_rocev2(rows: List[Dict[str, Any]], top_n: int) -> Dict[str, Any]:
    if not rows:
        return {
            "summary": {
                "total_flows": 0,
                "lossy_flows": 0,
                "retx_flows": 0,
                "seqerror_flows": 0,
                "ecn_flows": 0,
                "cnp_flows": 0,
                "nak_flows": 0,
                "message_failed_flows": 0,
            },
            "top_rx_hotspots": [],
            "top_by_delta": [],
            "top_by_retx": [],
            "top_by_seqerror": [],
            "top_by_latency": [],
        }

    for row in rows:
        item = {
            "flow_key": build_flow_key(row),
            "tx_port": row.get("Tx Port"),
            "rx_port": row.get("Rx Port"),
            "traffic_item": row.get("Traffic Item"),
            "flow_name": row.get("Flow Name"),
            "frames_tx": safe_int(row.get("Frames Tx")),
            "frames_rx": safe_int(row.get("Frames Rx")),
            "frames_delta": safe_int(row.get("Frames Delta")),
            "frames_retx": safe_int(row.get("Frames ReTx")),
            "frames_seqerror": safe_int(row.get("Frames SeqError")),
            "messages_failed": safe_int(row.get("Messages Failed")),
            "avg_latency_ns": safe_int(row.get("Avg Latency (ns)")),
            "max_latency_ns": safe_int(row.get("Max Latency (ns)")),
            "ecn_ce_rx": safe_int(row.get("ECN-CE Rx")),
            "cnp_tx": safe_int(row.get("CNP Tx")),
            "cnp_rx": safe_int(row.get("CNP Rx")),
            "nak_tx": safe_int(row.get("NAK Tx")),
            "nak_rx": safe_int(row.get("NAK Rx")),
            "rate_tx_gbps": safe_float(row.get("Rate Tx (Gbps)")),
            "rate_rx_gbps": safe_float(row.get("Rate Rx (Gbps)")),
        }
        flow_rows.append(item)

    rx_rollup: Dict[str, Dict[str, Any]] = {}
    for row in flow_rows:
        rx = row["rx_port"] or "unknown"
        if rx not in rx_rollup:
            rx_rollup[rx] = {
                "rx_port": rx,
                "flow_count": 0,
                "sum_frames_delta": 0,
                "sum_frames_retx": 0,
                "sum_frames_seqerror": 0,
                "sum_messages_failed": 0,
                "sum_ecn_ce_rx": 0,
                "sum_cnp_tx": 0,
                "sum_cnp_rx": 0,
                "sum_nak_tx": 0,
                "sum_nak_rx": 0,
                "max_latency_ns": 0,
            }

        g = rx_rollup[rx]
        g["flow_count"] += 1
        g["sum_frames_delta"] += row["frames_delta"]
        g["sum_frames_retx"] += row["frames_retx"]
        g["sum_frames_seqerror"] += row["frames_seqerror"]
        g["sum_messages_failed"] += row["messages_failed"]
        g["sum_ecn_ce_rx"] += row["ecn_ce_rx"]
        g["sum_cnp_tx"] += row["cnp_tx"]
        g["sum_cnp_rx"] += row["cnp_rx"]
        g["sum_nak_tx"] += row["nak_tx"]
        g["sum_nak_rx"] += row["nak_rx"]
        g["max_latency_ns"] = max(g["max_latency_ns"], row["max_latency_ns"])

    top_rx = sorted(
        rx_rollup.values(),
        key=lambda x: (
            x["sum_frames_seqerror"],
            x["sum_frames_retx"],
            x["sum_frames_delta"],
            x["max_latency_ns"],
        ),
        reverse=True,
    )[:top_n]

    top_delta = sorted(flow_rows, key=lambda x: x["frames_delta"], reverse=True)[:top_n]
    top_retx = sorted(flow_rows, key=lambda x: x["frames_retx"], reverse=True)[:top_n]
    top_seqerror = sorted(flow_rows, key=lambda x: x["frames_seqerror"], reverse=True)[:top_n]
    top_latency = sorted(flow_rows, key=lambda x: x["max_latency_ns"], reverse=True)[:top_n]

    summary = {
        "total_flows": len(flow_rows),
        "lossy_flows": sum(1 for x in flow_rows if x["frames_delta"] > 0),
        "retx_flows": sum(1 for x in flow_rows if x["frames_retx"] > 0),
        "seqerror_flows": sum(1 for x in flow_rows if x["frames_seqerror"] > 0),
        "ecn_flows": sum(1 for x in flow_rows if x["ecn_ce_rx"] > 0),
        "cnp_flows": sum(1 for x in flow_rows if x["cnp_tx"] > 0 or x["cnp_rx"] > 0),
        "nak_flows": sum(1 for x in flow_rows if x["nak_tx"] > 0 or x["nak_rx"] > 0),
        "message_failed_flows": sum(1 for x in flow_rows if x["messages_failed"] > 0),
    }

    return {
        "summary": summary,
        "top_rx_hotspots": top_rx,
        "top_by_delta": top_delta,
        "top_by_retx": top_retx,
        "top_by_seqerror": top_seqerror,
        "top_by_latency": top_latency,
    }


def analyze_port_stats(rows: List[Dict[str, Any]], top_n: int) -> Dict[str, Any]:
    if not rows:
        return {
            "summary": {
                "total_ports": 0,
                "link_up_ports": 0,
                "crc_issue_ports": 0,
                "fec_issue_ports": 0,
                "ber_issue_ports": 0,
            },
            "top_by_crc": [],
            "top_by_fec_loss": [],
            "top_by_pre_fec_ber": [],
        }
    ports = []

    for row in rows:
        item = {
            "port_name": row.get("Port Name"),
            "line_speed": row.get("Line Speed"),
            "link_state": row.get("Link State"),
            "frames_tx_rate": safe_int(row.get("Frames Tx. Rate")),
            "frames_rx_rate": safe_int(row.get("Valid Frames Rx. Rate")),
            "crc_errors": safe_int(row.get("CRC Errors")),
            "misdirected_packets": safe_int(row.get("Misdirected Packet Count")),
            "oversize": safe_int(row.get("Oversize")),
            "fragments": safe_int(row.get("Fragments")),
            "undersize": safe_int(row.get("Undersize")),
            "fec_frame_loss_ratio": safe_float(row.get("FEC Frame Loss Ratio")),
            "pre_fec_ber": safe_float(row.get("pre FEC Bit Error Ratio")),
            "roce_bad_icrc": safe_int(row.get("RoCEv2 Bad iCRC Count")),
            "roce_opcode_error": safe_int(row.get("RoCEv2 OpCode Error Count")),
        }
        ports.append(item)

    top_crc = sorted(ports, key=lambda x: x["crc_errors"], reverse=True)[:top_n]
    top_fec = sorted(ports, key=lambda x: x["fec_frame_loss_ratio"], reverse=True)[:top_n]
    top_ber = sorted(ports, key=lambda x: x["pre_fec_ber"], reverse=True)[:top_n]

    summary = {
        "total_ports": len(ports),
        "link_up_ports": sum(1 for x in ports if (x["link_state"] or "").lower() == "link up"),
        "crc_issue_ports": sum(1 for x in ports if x["crc_errors"] > 0),
        "fec_issue_ports": sum(1 for x in ports if x["fec_frame_loss_ratio"] > 0),
        "ber_issue_ports": sum(1 for x in ports if x["pre_fec_ber"] > 0),
    }

    return {
        "summary": summary,
        "top_by_crc": top_crc,
        "top_by_fec_loss": top_fec,
        "top_by_pre_fec_ber": top_ber,
    }


def detect_alerts(
    rocev2_analysis: Dict[str, Any],
    port_analysis: Dict[str, Any],
    delta_alert_threshold: int,
    retx_alert_threshold: int,
    seqerror_alert_threshold: int,
    latency_alert_threshold_ns: int,
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    for row in rocev2_analysis["top_by_delta"]:
        if row["frames_delta"] >= delta_alert_threshold:
            alerts.append({
                "severity": "critical",
                "type": "flow_delta_spike",
                "flow_key": row["flow_key"],
                "rx_port": row["rx_port"],
                "value": row["frames_delta"],
                "threshold": delta_alert_threshold,
            })

    for row in rocev2_analysis["top_by_retx"]:
        if row["frames_retx"] >= retx_alert_threshold:
            alerts.append({
                "severity": "critical",
                "type": "flow_retx_spike",
                "flow_key": row["flow_key"],
                "rx_port": row["rx_port"],
                "value": row["frames_retx"],
                "threshold": retx_alert_threshold,
            })

    for row in rocev2_analysis["top_by_seqerror"]:
        if row["frames_seqerror"] >= seqerror_alert_threshold:
            alerts.append({
                "severity": "critical",
                "type": "flow_seqerror_spike",
                "flow_key": row["flow_key"],
                "rx_port": row["rx_port"],
                "value": row["frames_seqerror"],
                "threshold": seqerror_alert_threshold,
            })

    for row in rocev2_analysis["top_by_latency"]:
        if row["max_latency_ns"] >= latency_alert_threshold_ns:
            alerts.append({
                "severity": "warning",
                "type": "flow_latency_spike",
                "flow_key": row["flow_key"],
                "rx_port": row["rx_port"],
                "value": row["max_latency_ns"],
                "threshold": latency_alert_threshold_ns,
            })

    for row in port_analysis["top_by_crc"]:
        if row["crc_errors"] > 0:
            alerts.append({
                "severity": "warning",
                "type": "port_crc_issue",
                "port_name": row["port_name"],
                "value": row["crc_errors"],
            })

    return alerts


def render_text(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("IXIA LIVE MONITOR SUMMARY")
    lines.append(f"  Run ID                : {report.get('run_id')}")
    lines.append(f"  Iterations            : {len(report.get('iterations', []))}")
    lines.append(f"  Poll interval sec     : {report.get('poll_interval_sec')}")
    lines.append("")

    for item in report.get("iterations", []):
        lines.append(f"ITERATION {item['iteration']} @ {item['timestamp']}")
        roce_summary = ((item.get("rocev2") or {}).get("summary") or {})
        port_summary = ((item.get("ports") or {}).get("summary") or {})
        lines.append(f"  RoCE flows            : {roce_summary.get('total_flows', 0)}")
        lines.append(f"  Lossy flows           : {roce_summary.get('lossy_flows', 0)}")
        lines.append(f"  ReTx flows            : {roce_summary.get('retx_flows', 0)}")
        lines.append(f"  SeqError flows        : {roce_summary.get('seqerror_flows', 0)}")
        lines.append(f"  ECN flows             : {roce_summary.get('ecn_flows', 0)}")
        lines.append(f"  CNP flows             : {roce_summary.get('cnp_flows', 0)}")
        lines.append(f"  NAK flows             : {roce_summary.get('nak_flows', 0)}")
        lines.append(f"  Message failed flows  : {roce_summary.get('message_failed_flows', 0)}")
        lines.append(f"  Link up ports         : {port_summary.get('link_up_ports', 0)}/{port_summary.get('total_ports', 0)}")
        lines.append(f"  Alerts                : {len(item['alerts'])}")
        top_rx_hotspots = ((item.get("rocev2") or {}).get("top_rx_hotspots") or [])
        for hotspot in top_rx_hotspots[:3]:
            lines.append(
                f"    HOT RX {hotspot['rx_port']} | "
                f"delta={hotspot['sum_frames_delta']} "
                f"retx={hotspot['sum_frames_retx']} "
                f"seqerr={hotspot['sum_frames_seqerror']} "
                f"max_lat_ns={hotspot['max_latency_ns']}"
            )
        for alert in item["alerts"][:10]:
            lines.append(f"    ALERT {alert}")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live IXIA monitor for RoCEv2 and Port Statistics")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--snapshot-name", default="live")
    parser.add_argument("--inventory", default=DEFAULT_IXIA_INVENTORY)
    parser.add_argument("--api-server", default=None)
    parser.add_argument("--session-id", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--verify-tls", action="store_true")
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--poll-interval-sec", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=10)

    parser.add_argument("--delta-alert-threshold", type=int, default=10000000)
    parser.add_argument("--retx-alert-threshold", type=int, default=1000000)
    parser.add_argument("--seqerror-alert-threshold", type=int, default=1000000)
    parser.add_argument("--latency-alert-threshold-ns", type=int, default=100000)

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
        report = {
            "run_id": args.run_id,
            "source_type": args.source_type,
            "snapshot_name": args.snapshot_name,
            "api_server": api_server,
            "session_id": session_id,
            "poll_interval_sec": args.poll_interval_sec,
            "iterations": [],
        }

        for i in range(1, args.iterations + 1):
            ts = utc_now_iso()

            rocev2_rows = []
            for view_name in ["RoCEv2 Per Port", "RoCEv2 Drill Down", "RoCEv2"]:
                try:
                    rocev2_rows = get_view_rows(client, session_id, view_name)
                    if rocev2_rows:
                        break
                except Exception:
                    continue
            port_rows = client.get_port_statistics(session_id)

            rocev2_analysis = analyze_rocev2(rocev2_rows, args.top_n)
            port_analysis = analyze_port_stats(port_rows, args.top_n)

            alerts = detect_alerts(
                rocev2_analysis=rocev2_analysis,
                port_analysis=port_analysis,
                delta_alert_threshold=args.delta_alert_threshold,
                retx_alert_threshold=args.retx_alert_threshold,
                seqerror_alert_threshold=args.seqerror_alert_threshold,
                latency_alert_threshold_ns=args.latency_alert_threshold_ns,
            )

            iteration_data = {
                "iteration": i,
                "timestamp": ts,
                "rocev2": rocev2_analysis,
                "ports": port_analysis,
                "alerts": alerts,
            }
            report["iterations"].append(iteration_data)

            print(f"[LIVE] iteration={i} timestamp={ts} alerts={len(alerts)}")
            if i < args.iterations:
                time.sleep(args.poll_interval_sec)

        out = output_paths(args.source_type, args.run_id, args.snapshot_name)
        with open(out["json"], "w") as f:
            json.dump(report, f, indent=2)

        with open(out["txt"], "w") as f:
            f.write(render_text(report))

        print(f"Ixia live monitor JSON report : {out['json']}")
        print(f"Ixia live monitor text report : {out['txt']}")
        print("")
        print("IXIA LIVE MONITOR SUMMARY")
        print(f"  Iterations            : {len(report['iterations'])}")
        if report["iterations"]:
            last = report["iterations"][-1]
            print(f"  Last alerts           : {len(last['alerts'])}")
            top_rx_hotspots = ((last.get("rocev2") or {}).get("top_rx_hotspots") or [])
            for hotspot in top_rx_hotspots[:5]:
                print(
                    f"  {hotspot['rx_port']:<12} "
                    f"delta={hotspot['sum_frames_delta']:<12} "
                    f"retx={hotspot['sum_frames_retx']:<12} "
                    f"seqerr={hotspot['sum_frames_seqerror']:<12}"
                )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
