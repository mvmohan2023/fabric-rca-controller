# controller/traffic_verifier.py

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

FINDING_LINK_MISMATCH = "link_mismatch"
FINDING_ZERO_RX_WITH_TX = "zero_rx_with_tx"
FINDING_RX_TX_IMBALANCE = "rx_tx_imbalance"
FINDING_CRC_ERROR = "crc_error"
FINDING_MISDIRECTED_PACKET = "misdirected_packet"
FINDING_FEC_FRAME_LOSS = "fec_frame_loss"
FINDING_PRE_FEC_BER = "pre_fec_ber"
FINDING_ROCE_OPCODE_ERROR = "roce_opcode_error"
FINDING_ROCE_ICRC_ERROR = "roce_icrc_error"
FINDING_POST_DROP_TX_RATE = "post_drop_tx_rate"
FINDING_POST_DROP_RX_RATE = "post_drop_rx_rate"
FINDING_IDLE_PORT = "idle_port"


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def traffic_output_dir(source_type: str, run_id: str) -> str:
    out_dir = os.path.join("artifacts", f"{source_type}s", run_id, "traffic")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def default_output_paths(source_type: str, run_id: str) -> Tuple[str, str]:
    out_dir = traffic_output_dir(source_type, run_id)
    return (
        os.path.join(out_dir, "traffic_verdict.json"),
        os.path.join(out_dir, "traffic_verdict.txt"),
    )


def safe_float(value: Any) -> Optional[float]:
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def safe_int(value: Any) -> Optional[int]:
    if value in ("", None):
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def normalize_port_key(port: Dict[str, Any]) -> str:
    return port.get("ixia_port") or port.get("port_name") or "unknown"


def build_port_index(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for port in snapshot.get("normalized_ports", []):
        index[normalize_port_key(port)] = port
    return index


def add_finding(
    findings: List[Dict[str, Any]],
    finding_type: str,
    severity: str,
    port_key: str,
    port: Dict[str, Any],
    details: Dict[str, Any],
) -> None:
    findings.append({
        "type": finding_type,
        "severity": severity,
        "ixia_port": port.get("ixia_port"),
        "port_name": port.get("port_name"),
        "switch": port.get("switch"),
        "switch_interface": port.get("switch_interface"),
        "line_speed": port.get("line_speed"),
        "link_state": port.get("link_state"),
        "details": details,
    })


def compare_single_snapshot(
    snapshot: Dict[str, Any],
    zero_rx_min_tx_rate: int,
    low_rx_ratio_threshold: float,
    idle_tx_rate_threshold: int,
    pre_fec_ber_threshold: float,
    fec_frame_loss_threshold: float,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    for port in snapshot.get("normalized_ports", []):
        port_key = normalize_port_key(port)
        metrics = port.get("metrics", {})

        expected_link_state = port.get("expected_link_state")
        actual_link_state = port.get("link_state")

        tx_rate = safe_int(metrics.get("frames_tx_rate")) or 0
        rx_rate = safe_int(metrics.get("valid_frames_rx_rate")) or 0
        crc_errors = safe_int(metrics.get("crc_errors")) or 0
        misdirected = safe_int(metrics.get("misdirected_packet_count")) or 0
        fec_frame_loss_ratio = safe_float(metrics.get("fec_frame_loss_ratio")) or 0.0
        pre_fec_ber = safe_float(metrics.get("pre_fec_bit_error_ratio")) or 0.0
        roce_opcode = safe_int(metrics.get("rocev2_opcode_error_count")) or 0
        roce_icrc = safe_int(metrics.get("rocev2_bad_icrc_count")) or 0

        if expected_link_state and actual_link_state != expected_link_state:
            add_finding(
                findings,
                FINDING_LINK_MISMATCH,
                SEVERITY_CRITICAL,
                port_key,
                port,
                {
                    "expected_link_state": expected_link_state,
                    "actual_link_state": actual_link_state,
                },
            )

        if tx_rate >= zero_rx_min_tx_rate and rx_rate == 0:
            add_finding(
                findings,
                FINDING_ZERO_RX_WITH_TX,
                SEVERITY_CRITICAL,
                port_key,
                port,
                {
                    "frames_tx_rate": tx_rate,
                    "valid_frames_rx_rate": rx_rate,
                    "zero_rx_min_tx_rate": zero_rx_min_tx_rate,
                },
            )

        if tx_rate >= zero_rx_min_tx_rate and rx_rate > 0:
            ratio = rx_rate / tx_rate if tx_rate else 0.0
            if ratio < low_rx_ratio_threshold:
                add_finding(
                    findings,
                    FINDING_RX_TX_IMBALANCE,
                    SEVERITY_WARNING,
                    port_key,
                    port,
                    {
                        "frames_tx_rate": tx_rate,
                        "valid_frames_rx_rate": rx_rate,
                        "rx_tx_ratio": round(ratio, 4),
                        "threshold": low_rx_ratio_threshold,
                    },
                )

        if tx_rate < idle_tx_rate_threshold and rx_rate < idle_tx_rate_threshold:
            add_finding(
                findings,
                FINDING_IDLE_PORT,
                SEVERITY_INFO,
                port_key,
                port,
                {
                    "frames_tx_rate": tx_rate,
                    "valid_frames_rx_rate": rx_rate,
                    "idle_tx_rate_threshold": idle_tx_rate_threshold,
                },
            )

        if crc_errors > 0:
            add_finding(
                findings,
                FINDING_CRC_ERROR,
                SEVERITY_CRITICAL,
                port_key,
                port,
                {"crc_errors": crc_errors},
            )

        if misdirected > 0:
            add_finding(
                findings,
                FINDING_MISDIRECTED_PACKET,
                SEVERITY_CRITICAL,
                port_key,
                port,
                {"misdirected_packet_count": misdirected},
            )

        if fec_frame_loss_ratio > fec_frame_loss_threshold:
            add_finding(
                findings,
                FINDING_FEC_FRAME_LOSS,
                SEVERITY_CRITICAL,
                port_key,
                port,
                {
                    "fec_frame_loss_ratio": fec_frame_loss_ratio,
                    "threshold": fec_frame_loss_threshold,
                },
            )

        if pre_fec_ber > pre_fec_ber_threshold:
            add_finding(
                findings,
                FINDING_PRE_FEC_BER,
                SEVERITY_WARNING,
                port_key,
                port,
                {
                    "pre_fec_bit_error_ratio": pre_fec_ber,
                    "threshold": pre_fec_ber_threshold,
                },
            )

        if roce_opcode > 0:
            add_finding(
                findings,
                FINDING_ROCE_OPCODE_ERROR,
                SEVERITY_WARNING,
                port_key,
                port,
                {"rocev2_opcode_error_count": roce_opcode},
            )

        if roce_icrc > 0:
            add_finding(
                findings,
                FINDING_ROCE_ICRC_ERROR,
                SEVERITY_WARNING,
                port_key,
                port,
                {"rocev2_bad_icrc_count": roce_icrc},
            )

    return findings


def compare_pre_post(
    pre_snapshot: Dict[str, Any],
    post_snapshot: Dict[str, Any],
    post_drop_ratio_threshold: float,
    rate_drop_min_pre_rate: int,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    pre_idx = build_port_index(pre_snapshot)
    post_idx = build_port_index(post_snapshot)

    for port_key in sorted(set(pre_idx.keys()) & set(post_idx.keys())):
        pre = pre_idx[port_key]
        post = post_idx[port_key]

        pre_metrics = pre.get("metrics", {})
        post_metrics = post.get("metrics", {})

        pre_tx = safe_int(pre_metrics.get("frames_tx_rate")) or 0
        post_tx = safe_int(post_metrics.get("frames_tx_rate")) or 0
        pre_rx = safe_int(pre_metrics.get("valid_frames_rx_rate")) or 0
        post_rx = safe_int(post_metrics.get("valid_frames_rx_rate")) or 0

        if pre_tx >= rate_drop_min_pre_rate:
            ratio = (post_tx / pre_tx) if pre_tx else 1.0
            if ratio < post_drop_ratio_threshold:
                add_finding(
                    findings,
                    FINDING_POST_DROP_TX_RATE,
                    SEVERITY_WARNING,
                    port_key,
                    post,
                    {
                        "pre_frames_tx_rate": pre_tx,
                        "post_frames_tx_rate": post_tx,
                        "ratio": round(ratio, 4),
                        "threshold": post_drop_ratio_threshold,
                    },
                )

        if pre_rx >= rate_drop_min_pre_rate:
            ratio = (post_rx / pre_rx) if pre_rx else 1.0
            if ratio < post_drop_ratio_threshold:
                add_finding(
                    findings,
                    FINDING_POST_DROP_RX_RATE,
                    SEVERITY_WARNING,
                    port_key,
                    post,
                    {
                        "pre_valid_frames_rx_rate": pre_rx,
                        "post_valid_frames_rx_rate": post_rx,
                        "ratio": round(ratio, 4),
                        "threshold": post_drop_ratio_threshold,
                    },
                )

    return findings


def summarize_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_type = Counter(item.get("type", "unknown") for item in findings)
    by_severity = Counter(item.get("severity", "unknown") for item in findings)
    by_port = Counter(item.get("ixia_port", "unknown") for item in findings)

    return {
        "total_findings": len(findings),
        "by_type": dict(by_type),
        "by_severity": dict(by_severity),
        "by_port": dict(by_port),
    }


def build_port_rollup(findings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in findings:
        key = item.get("ixia_port") or "unknown"
        grouped[key].append(item)

    rollup: Dict[str, Dict[str, Any]] = {}
    for port_key, items in grouped.items():
        sev_counts = Counter(item.get("severity", "unknown") for item in items)
        type_counts = Counter(item.get("type", "unknown") for item in items)

        highest = SEVERITY_INFO
        if sev_counts.get(SEVERITY_CRITICAL, 0):
            highest = SEVERITY_CRITICAL
        elif sev_counts.get(SEVERITY_WARNING, 0):
            highest = SEVERITY_WARNING

        exemplar = items[0]
        rollup[port_key] = {
            "ixia_port": exemplar.get("ixia_port"),
            "port_name": exemplar.get("port_name"),
            "switch": exemplar.get("switch"),
            "switch_interface": exemplar.get("switch_interface"),
            "count": len(items),
            "highest_severity": highest,
            "by_type": dict(type_counts),
            "by_severity": dict(sev_counts),
        }

    return rollup


def overall_verdict(summary: Dict[str, Any]) -> str:
    by_severity = summary.get("by_severity", {})
    if by_severity.get(SEVERITY_CRITICAL, 0):
        return "fail"
    if by_severity.get(SEVERITY_WARNING, 0):
        return "warning"
    return "pass"


def render_text_report(report: Dict[str, Any]) -> str:
    summary = report.get("summary", {})
    rollup = report.get("port_rollup", {})
    findings = report.get("findings", [])

    lines: List[str] = []
    lines.append("IXIA TRAFFIC VERIFIER SUMMARY")
    lines.append(f"  Verdict              : {report.get('verdict')}")
    lines.append(f"  Total findings       : {summary.get('total_findings', 0)}")
    lines.append("")

    lines.append("BY SEVERITY")
    for k, v in sorted(summary.get("by_severity", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("BY TYPE")
    for k, v in sorted(summary.get("by_type", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("PORT ROLL-UP")
    for _, item in sorted(
        rollup.items(),
        key=lambda kv: (
            0 if kv[1]["highest_severity"] == SEVERITY_CRITICAL else
            1 if kv[1]["highest_severity"] == SEVERITY_WARNING else
            2,
            -kv[1]["count"],
            kv[1]["ixia_port"] or "",
        )
    ):
        lines.append(
            f"  [{item['highest_severity']}] "
            f"{item['ixia_port']} | {item['switch']} {item['switch_interface']} -> "
            f"{item['count']} findings {item['by_type']}"
        )
    lines.append("")

    lines.append("FINDING DETAILS")
    for item in findings:
        lines.append(json.dumps(item, sort_keys=True))
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Ixia pre/post port statistics and flag suspicious traffic behavior")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pre", required=True, help="pre ixia port stats json")
    parser.add_argument("--post", required=True, help="post ixia port stats json")
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)

    parser.add_argument("--zero-rx-min-tx-rate", type=int, default=1000)
    parser.add_argument("--low-rx-ratio-threshold", type=float, default=0.80)
    parser.add_argument("--idle-tx-rate-threshold", type=int, default=10)
    parser.add_argument("--pre-fec-ber-threshold", type=float, default=1e-12)
    parser.add_argument("--fec-frame-loss-threshold", type=float, default=0.0)
    parser.add_argument("--post-drop-ratio-threshold", type=float, default=0.50)
    parser.add_argument("--rate-drop-min-pre-rate", type=int, default=1000)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        pre_snapshot = load_json(args.pre)
        post_snapshot = load_json(args.post)

        findings: List[Dict[str, Any]] = []

        findings.extend(compare_single_snapshot(
            snapshot=post_snapshot,
            zero_rx_min_tx_rate=args.zero_rx_min_tx_rate,
            low_rx_ratio_threshold=args.low_rx_ratio_threshold,
            idle_tx_rate_threshold=args.idle_tx_rate_threshold,
            pre_fec_ber_threshold=args.pre_fec_ber_threshold,
            fec_frame_loss_threshold=args.fec_frame_loss_threshold,
        ))

        findings.extend(compare_pre_post(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            post_drop_ratio_threshold=args.post_drop_ratio_threshold,
            rate_drop_min_pre_rate=args.rate_drop_min_pre_rate,
        ))

        summary = summarize_findings(findings)
        rollup = build_port_rollup(findings)
        verdict = overall_verdict(summary)

        report = {
            "source_type": args.source_type,
            "run_id": args.run_id,
            "pre_snapshot": args.pre,
            "post_snapshot": args.post,
            "verdict": verdict,
            "summary": summary,
            "port_rollup": rollup,
            "findings": findings,
        }

        out_json = args.out_json
        out_txt = args.out_txt
        if not out_json or not out_txt:
            default_json, default_txt = default_output_paths(args.source_type, args.run_id)
            out_json = out_json or default_json
            out_txt = out_txt or default_txt

        write_json(out_json, report)
        write_text(out_txt, render_text_report(report))

        print(f"Traffic verifier JSON report : {out_json}")
        print(f"Traffic verifier text report : {out_txt}")
        print("")
        print("IXIA TRAFFIC VERIFIER SUMMARY")
        print(f"  Verdict              : {verdict}")
        print(f"  Total findings       : {summary.get('total_findings', 0)}")
        for k, v in sorted(summary.get("by_severity", {}).items()):
            print(f"  {k:<20} {v}")
        for k, v in sorted(summary.get("by_type", {}).items()):
            print(f"  {k:<20} {v}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
