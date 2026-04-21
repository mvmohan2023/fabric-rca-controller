from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from ixnetwork_restpy import SessionAssistant

def normalize_page_rows(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Backward-compatible shim for older callers.
    The old implementation normalized raw IXIA page payloads.
    The new collector uses StatViewAssistant, so this shim simply returns
    an empty list when called on legacy page content.
    """
    if not page:
        return []
    return []


def summarize_rows_legacy(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Backward-compatible shim for older callers that may expect summarize_rows
    semantics from page-based collection.
    """
    return summarize_rows(rows or [])


def load_json_file(path: str) -> dict:
    p = Path(path)
    with p.open() as f:
        return json.load(f)


def _artifact_base_dir(source_type: str, run_id: str) -> Path:
    if source_type == "campaign":
        return Path("artifacts") / "campaigns" / run_id / "traffic"
    if source_type == "orchestrator":
        return Path("artifacts") / "orchestrator" / run_id / "traffic"
    raise ValueError(f"Unsupported source_type: {source_type}")


def output_paths(source_type: str, run_id: str, snapshot_name: str) -> Dict[str, str]:
    base = _artifact_base_dir(source_type, run_id)
    base.mkdir(parents=True, exist_ok=True)
    stem = f"{snapshot_name}_ixia_rocev2_flow_stats"
    return {
        "json": str(base / f"{stem}.json"),
        "txt": str(base / f"{stem}.txt"),
    }


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value)
    except Exception:
        return 0.0


def row_to_dict(row: Any) -> Dict[str, Any]:
    """
    RestPy StatViewAssistant rows print cleanly but are not reliably dict-like.
    Parse the string form into key/value pairs.
    """
    text = str(row)
    result: Dict[str, Any] = {"raw_row": text}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Row:"):
            continue
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()

    return result


def normalize_stat_rows(rows: List[Any], view_name: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for row in rows:
        raw = row_to_dict(row)

        norm: Dict[str, Any] = {
            "view_name": view_name,
            "raw": raw,
        }

        # Flow-level fields
        norm["tx_port"] = raw.get("Tx Port")
        norm["rx_port"] = raw.get("Rx Port")
        norm["traffic_item"] = raw.get("Traffic Item")
        norm["flow_name"] = raw.get("Flow Name")
        norm["src_qp"] = _safe_int(raw.get("Src QP"))
        norm["dest_qp"] = _safe_int(raw.get("Dest QP"))
        norm["src_ipv4"] = raw.get("Src IPv4")
        norm["dest_ipv4"] = raw.get("Dest IPv4")
        norm["src_ipv6"] = raw.get("Src IPv6")
        norm["dest_ipv6"] = raw.get("Dest IPv6")

        norm["data_frames_tx"] = _safe_int(raw.get("Frames Tx"))
        norm["data_frames_rx"] = _safe_int(raw.get("Frames Rx"))
        norm["frames_delta"] = _safe_int(raw.get("Frames Delta"))
        norm["retx"] = _safe_int(raw.get("Frames ReTx"))
        norm["seqerror"] = _safe_int(raw.get("Frames SeqError"))
        norm["bytes_tx"] = _safe_int(raw.get("Bytes Tx"))
        norm["bytes_rx"] = _safe_int(raw.get("Bytes Rx"))
        norm["rate_tx_gbps"] = _safe_float(raw.get("Rate Tx (Gbps)"))
        norm["rate_rx_gbps"] = _safe_float(raw.get("Rate Rx (Gbps)"))
        norm["messages_tx"] = _safe_int(raw.get("Messages Tx"))
        norm["messages_rx"] = _safe_int(raw.get("Messages Rx"))
        norm["message_failed"] = _safe_int(raw.get("Messages Failed"))
        norm["fct_ms"] = _safe_float(raw.get("FCT (ms)"))
        norm["latency_ns"] = _safe_float(raw.get("Avg Latency (ns)"))
        norm["min_latency_ns"] = _safe_float(raw.get("Min Latency (ns)"))
        norm["max_latency_ns"] = _safe_float(raw.get("Max Latency (ns)"))
        norm["ecn"] = _safe_int(raw.get("ECN-CE Rx"))
        norm["cnp_tx"] = _safe_int(raw.get("CNP Tx"))
        norm["cnp_rx"] = _safe_int(raw.get("CNP Rx"))
        norm["ack_tx"] = _safe_int(raw.get("ACK Tx"))
        norm["ack_rx"] = _safe_int(raw.get("ACK Rx"))
        norm["nak_tx"] = _safe_int(raw.get("NAK Tx"))
        norm["nak_rx"] = _safe_int(raw.get("NAK Rx"))
        norm["first_timestamp"] = raw.get("First TimeStamp")
        norm["last_timestamp"] = raw.get("Last TimeStamp")

        # Per-port view support
        norm["port"] = raw.get("Port") or raw.get("Port Name") or raw.get("Stat Name")
        norm["sessions_up"] = _safe_int(raw.get("Sessions Up"))
        norm["sessions_down"] = _safe_int(raw.get("Sessions Down"))
        norm["sessions_not_started"] = _safe_int(raw.get("Sessions Not Started"))
        norm["sessions_total"] = _safe_int(raw.get("Sessions Total"))
        norm["qp_configured"] = _safe_int(raw.get("QP Configured"))
        norm["qp_up"] = _safe_int(raw.get("QP Up"))
        norm["qp_down"] = _safe_int(raw.get("QP Down"))
        norm["connect_request_tx"] = _safe_int(raw.get("Connect Request Tx"))
        norm["connect_request_rx"] = _safe_int(raw.get("Connect Request Rx"))
        norm["connect_reply_tx"] = _safe_int(raw.get("Connect Reply Tx"))
        norm["connect_reply_rx"] = _safe_int(raw.get("Connect Reply Rx"))
        norm["ready_tx"] = _safe_int(raw.get("Ready Tx"))
        norm["ready_rx"] = _safe_int(raw.get("Ready Rx"))
        norm["disconnect_request_tx"] = _safe_int(raw.get("Disconnect Request Tx"))
        norm["disconnect_request_rx"] = _safe_int(raw.get("Disconnect Request Rx"))
        norm["disconnect_reply_tx"] = _safe_int(raw.get("Disconnect Reply Tx"))
        norm["disconnect_reply_rx"] = _safe_int(raw.get("Disconnect Reply Rx"))
        norm["reject_tx"] = _safe_int(raw.get("Reject Tx"))
        norm["reject_rx"] = _safe_int(raw.get("Reject Rx"))
        norm["unknown_msg_rx"] = _safe_int(raw.get("Unknown MSG Rx"))

        normalized.append(norm)

    return normalized


def summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "total_flows": len(rows),
        "zero_rx_flows": 0,
        "tx_gt_rx_flows": 0,
        "lossy_flows": 0,
        "retx_flows": 0,
        "seqerror_flows": 0,
        "message_failed_flows": 0,
        "ecn_flows": 0,
        "cnp_flows": 0,
        "nak_flows": 0,
    }

    for row in rows:
        tx = _safe_int(row.get("data_frames_tx"))
        rx = _safe_int(row.get("data_frames_rx"))
        delta = _safe_int(row.get("frames_delta"))
        retx = _safe_int(row.get("retx"))
        seqerror = _safe_int(row.get("seqerror"))
        msg_failed = _safe_int(row.get("message_failed"))
        ecn = _safe_int(row.get("ecn"))
        cnp_tx = _safe_int(row.get("cnp_tx"))
        cnp_rx = _safe_int(row.get("cnp_rx"))
        nak_tx = _safe_int(row.get("nak_tx"))
        nak_rx = _safe_int(row.get("nak_rx"))

        if rx == 0:
            summary["zero_rx_flows"] += 1
        if tx > rx and tx > 0:
            summary["tx_gt_rx_flows"] += 1
        if delta > 0:
            summary["lossy_flows"] += 1
        if retx > 0:
            summary["retx_flows"] += 1
        if seqerror > 0:
            summary["seqerror_flows"] += 1
        if msg_failed > 0:
            summary["message_failed_flows"] += 1
        if ecn > 0:
            summary["ecn_flows"] += 1
        if cnp_tx > 0 or cnp_rx > 0:
            summary["cnp_flows"] += 1
        if nak_tx > 0 or nak_rx > 0:
            summary["nak_flows"] += 1

    return summary


def build_text_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("IXIA ROCEV2 FLOW STATISTICS SUMMARY")
    lines.append(f"  View name              : {report.get('view_name')}")
    lines.append(f"  View found             : {report.get('view_found')}")
    lines.append(f"  View mismatch          : {report.get('view_mismatch')}")
    lines.append(f"  View mismatch reason   : {report.get('view_mismatch_reason')}")
    lines.append(f"  Total normalized rows  : {len(report.get('normalized_rows', []) or [])}")

    summary = report.get("summary", {}) or {}
    if summary:
        lines.append("  Summary:")
        for key, value in summary.items():
            lines.append(f"    - {key}: {value}")

    sample_rows = report.get("normalized_rows", [])[:5]
    if sample_rows:
        lines.append("  Sample rows:")
        for idx, row in enumerate(sample_rows, 1):
            lines.append(
                "    "
                f"{idx}. tx_port={row.get('tx_port')!r}, "
                f"rx_port={row.get('rx_port')!r}, "
                f"flow_name={row.get('flow_name')!r}, "
                f"frames_delta={row.get('frames_delta')}, "
                f"retx={row.get('retx')}, "
                f"seqerror={row.get('seqerror')}, "
                f"ecn={row.get('ecn')}, "
                f"latency_ns={row.get('latency_ns')}"
            )

    if report.get("available_views"):
        lines.append("  Available views:")
        for name in report["available_views"]:
            lines.append(f"    - {name}")

    return "\n".join(lines) + "\n"


def collect_rocev2_stats(
    *,
    source_type: str,
    run_id: str,
    snapshot_name: str,
    inventory_path: str,
    api_server: str | None,
    session_id: int | None,
    view_name: str,
) -> Dict[str, Any]:
    inventory = load_json_file(inventory_path)
    resolved_api_server = api_server or inventory.get("ixnetwork_api_server")
    if not resolved_api_server:
        raise RuntimeError("ixnetwork_api_server not found in inventory and not provided")

    resolved_session_id = session_id or 1
    username = inventory.get("username") or inventory.get("user") or "administrator"
    password = inventory.get("password") or inventory.get("pass") or ""

    session = SessionAssistant(
        IpAddress=resolved_api_server,
        RestPort=11009,
        UserName=username,
        Password=password,
        SessionId=resolved_session_id,
        ClearConfig=False,
        LogLevel="info",
    )

    stat_view_names: List[str] = []
    try:
        for view in session.Ixnetwork.Statistics.View.find():
            caption = getattr(view, "Caption", None)
            if caption:
                stat_view_names.append(str(caption))
    except Exception:
        pass

    report: Dict[str, Any] = {
        "run_id": run_id,
        "source_type": source_type,
        "snapshot_name": snapshot_name,
        "api_server": resolved_api_server,
        "session_id": resolved_session_id,
        "view_name": view_name,
        "view_found": False,
        "view_mismatch": None,
        "view_mismatch_reason": None,
        "available_views": sorted(stat_view_names),
        "summary": {},
        "normalized_rows": [],
        "raw_rows": [],
        "column_captions": [],
    }

    if stat_view_names and view_name not in stat_view_names:
        return report

    stat_view = session.StatViewAssistant(view_name)
    rows = list(stat_view.Rows)

    raw_rows = [row_to_dict(row) for row in rows]
    normalized_rows = normalize_stat_rows(rows, view_name=view_name)
    summary = summarize_rows(normalized_rows)

    report["view_found"] = True
    report["raw_rows"] = raw_rows
    report["normalized_rows"] = normalized_rows
    report["summary"] = summary

    # Lightweight transparency only for per-port view
    if view_name.strip().lower() == "rocev2 per port":
        report["view_mismatch"] = True
        report["view_mismatch_reason"] = (
            "Selected IXIA view is port-level, not flow-level; deep flow inspection is unavailable"
        )
    else:
        report["view_mismatch"] = False
        report["view_mismatch_reason"] = None

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect RoCEv2 statistics from an existing IxNetwork session using RestPy StatViewAssistant"
    )
    parser.add_argument("--source-type", choices=["campaign", "orchestrator"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--inventory", default="controller/ixia_inventory.json")
    parser.add_argument("--api-server", default=None)
    parser.add_argument("--session-id", type=int, default=None)
    parser.add_argument("--view-name", default="RoCEv2 Flow Statistics")
    args = parser.parse_args()

    report = collect_rocev2_stats(
        source_type=args.source_type,
        run_id=args.run_id,
        snapshot_name=args.snapshot_name,
        inventory_path=args.inventory,
        api_server=args.api_server,
        session_id=args.session_id,
        view_name=args.view_name,
    )

    out = output_paths(args.source_type, args.run_id, args.snapshot_name)
    Path(out["json"]).write_text(json.dumps(report, indent=2))
    Path(out["txt"]).write_text(build_text_report(report))

    print(f"Ixia RoCEv2 flow stats JSON report : {out['json']}")
    print(f"Ixia RoCEv2 flow stats text report : {out['txt']}")
    print()
    print(build_text_report(report))


if __name__ == "__main__":
    main()
