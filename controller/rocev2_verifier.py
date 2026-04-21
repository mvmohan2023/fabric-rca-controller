# controller/rocev2_verifier.py

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

FINDING_ZERO_RX_FLOW = "zero_rx_flow"
FINDING_FRAME_DELTA = "frame_delta"
FINDING_RETX = "retx"
FINDING_SEQERROR = "seqerror"
FINDING_MESSAGE_FAILED = "message_failed"
FINDING_LATENCY_HIGH = "latency_high"
FINDING_ECN_ACTIVITY = "ecn_activity"
FINDING_CNP_ACTIVITY = "cnp_activity"
FINDING_NAK_ACTIVITY = "nak_activity"
FINDING_POST_DELTA_INCREASE = "post_delta_increase"
FINDING_POST_RETX_INCREASE = "post_retx_increase"
FINDING_POST_SEQERROR_INCREASE = "post_seqerror_increase"
FINDING_POST_LATENCY_INCREASE = "post_latency_increase"


def load_json(path: str) -> Dict[str, Any]:
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


def default_output_paths(source_type: str, run_id: str) -> Tuple[str, str]:
    out = output_dir(source_type, run_id)
    return (
        os.path.join(out, "rocev2_verdict.json"),
        os.path.join(out, "rocev2_verdict.txt"),
    )


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


def safe_float(value: Any) -> Optional[float]:
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def flow_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        row.get("Tx Port") or "",
        row.get("Rx Port") or "",
        row.get("Traffic Item") or "",
        row.get("Flow Name") or "",
    )


def build_flow_index(snapshot: Dict[str, Any]) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    idx: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for row in snapshot.get("normalized_rows", []):
        idx[flow_key(row)] = row
    return idx


def add_finding(
    findings: List[Dict[str, Any]],
    finding_type: str,
    severity: str,
    row: Dict[str, Any],
    details: Dict[str, Any],
) -> None:
    findings.append({
        "type": finding_type,
        "severity": severity,
        "tx_port": row.get("Tx Port"),
        "rx_port": row.get("Rx Port"),
        "traffic_item": row.get("Traffic Item"),
        "flow_name": row.get("Flow Name"),
        "src_qp": safe_int(row.get("Src QP")),
        "dest_qp": safe_int(row.get("Dest QP")),
        "details": details,
    })


def evaluate_single_snapshot(
    snapshot: Dict[str, Any],
    delta_warn_threshold: int,
    delta_critical_threshold: int,
    retx_warn_threshold: int,
    retx_critical_threshold: int,
    seqerr_warn_threshold: int,
    seqerr_critical_threshold: int,
    latency_warn_ns: int,
    latency_critical_ns: int,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    for row in snapshot.get("normalized_rows", []):
        frames_tx = safe_int(row.get("Frames Tx")) or 0
        frames_rx = safe_int(row.get("Frames Rx")) or 0
        frames_delta = safe_int(row.get("Frames Delta")) or 0
        frames_retx = safe_int(row.get("Frames ReTx")) or 0
        frames_seqerror = safe_int(row.get("Frames SeqError")) or 0
        messages_failed = safe_int(row.get("Messages Failed")) or 0
        avg_latency_ns = safe_int(row.get("Avg Latency (ns)")) or 0
        max_latency_ns = safe_int(row.get("Max Latency (ns)")) or 0
        ecn_ce_rx = safe_int(row.get("ECN-CE Rx")) or 0
        cnp_tx = safe_int(row.get("CNP Tx")) or 0
        cnp_rx = safe_int(row.get("CNP Rx")) or 0
        nak_tx = safe_int(row.get("NAK Tx")) or 0
        nak_rx = safe_int(row.get("NAK Rx")) or 0

        if frames_tx > 0 and frames_rx == 0:
            add_finding(
                findings,
                FINDING_ZERO_RX_FLOW,
                SEVERITY_CRITICAL,
                row,
                {
                    "frames_tx": frames_tx,
                    "frames_rx": frames_rx,
                },
            )

        if frames_delta >= delta_critical_threshold:
            add_finding(
                findings,
                FINDING_FRAME_DELTA,
                SEVERITY_CRITICAL,
                row,
                {
                    "frames_delta": frames_delta,
                    "threshold": delta_critical_threshold,
                },
            )
        elif frames_delta >= delta_warn_threshold:
            add_finding(
                findings,
                FINDING_FRAME_DELTA,
                SEVERITY_WARNING,
                row,
                {
                    "frames_delta": frames_delta,
                    "threshold": delta_warn_threshold,
                },
            )

        if frames_retx >= retx_critical_threshold:
            add_finding(
                findings,
                FINDING_RETX,
                SEVERITY_CRITICAL,
                row,
                {
                    "frames_retx": frames_retx,
                    "threshold": retx_critical_threshold,
                },
            )
        elif frames_retx >= retx_warn_threshold:
            add_finding(
                findings,
                FINDING_RETX,
                SEVERITY_WARNING,
                row,
                {
                    "frames_retx": frames_retx,
                    "threshold": retx_warn_threshold,
                },
            )

        if frames_seqerror >= seqerr_critical_threshold:
            add_finding(
                findings,
                FINDING_SEQERROR,
                SEVERITY_CRITICAL,
                row,
                {
                    "frames_seqerror": frames_seqerror,
                    "threshold": seqerr_critical_threshold,
                },
            )
        elif frames_seqerror >= seqerr_warn_threshold:
            add_finding(
                findings,
                FINDING_SEQERROR,
                SEVERITY_WARNING,
                row,
                {
                    "frames_seqerror": frames_seqerror,
                    "threshold": seqerr_warn_threshold,
                },
            )

        if messages_failed > 0:
            add_finding(
                findings,
                FINDING_MESSAGE_FAILED,
                SEVERITY_WARNING,
                row,
                {"messages_failed": messages_failed},
            )

        if max_latency_ns >= latency_critical_ns:
            add_finding(
                findings,
                FINDING_LATENCY_HIGH,
                SEVERITY_CRITICAL,
                row,
                {
                    "avg_latency_ns": avg_latency_ns,
                    "max_latency_ns": max_latency_ns,
                    "threshold": latency_critical_ns,
                },
            )
        elif max_latency_ns >= latency_warn_ns:
            add_finding(
                findings,
                FINDING_LATENCY_HIGH,
                SEVERITY_WARNING,
                row,
                {
                    "avg_latency_ns": avg_latency_ns,
                    "max_latency_ns": max_latency_ns,
                    "threshold": latency_warn_ns,
                },
            )

        if ecn_ce_rx > 0:
            add_finding(
                findings,
                FINDING_ECN_ACTIVITY,
                SEVERITY_INFO,
                row,
                {"ecn_ce_rx": ecn_ce_rx},
            )

        if cnp_tx > 0 or cnp_rx > 0:
            add_finding(
                findings,
                FINDING_CNP_ACTIVITY,
                SEVERITY_INFO,
                row,
                {
                    "cnp_tx": cnp_tx,
                    "cnp_rx": cnp_rx,
                },
            )

        if nak_tx > 0 or nak_rx > 0:
            add_finding(
                findings,
                FINDING_NAK_ACTIVITY,
                SEVERITY_WARNING,
                row,
                {
                    "nak_tx": nak_tx,
                    "nak_rx": nak_rx,
                },
            )

    return findings


def evaluate_pre_post(
    pre_snapshot: Dict[str, Any],
    post_snapshot: Dict[str, Any],
    delta_increase_warn: int,
    retx_increase_warn: int,
    seqerror_increase_warn: int,
    latency_increase_warn_ns: int,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    pre_idx = build_flow_index(pre_snapshot)
    post_idx = build_flow_index(post_snapshot)

    for key in sorted(set(pre_idx.keys()) & set(post_idx.keys())):
        pre = pre_idx[key]
        post = post_idx[key]

        pre_delta = safe_int(pre.get("Frames Delta")) or 0
        post_delta = safe_int(post.get("Frames Delta")) or 0

        pre_retx = safe_int(pre.get("Frames ReTx")) or 0
        post_retx = safe_int(post.get("Frames ReTx")) or 0

        pre_seq = safe_int(pre.get("Frames SeqError")) or 0
        post_seq = safe_int(post.get("Frames SeqError")) or 0

        pre_max_lat = safe_int(pre.get("Max Latency (ns)")) or 0
        post_max_lat = safe_int(post.get("Max Latency (ns)")) or 0

        if (post_delta - pre_delta) >= delta_increase_warn:
            add_finding(
                findings,
                FINDING_POST_DELTA_INCREASE,
                SEVERITY_WARNING,
                post,
                {
                    "pre_frames_delta": pre_delta,
                    "post_frames_delta": post_delta,
                    "increase": post_delta - pre_delta,
                    "threshold": delta_increase_warn,
                },
            )

        if (post_retx - pre_retx) >= retx_increase_warn:
            add_finding(
                findings,
                FINDING_POST_RETX_INCREASE,
                SEVERITY_WARNING,
                post,
                {
                    "pre_frames_retx": pre_retx,
                    "post_frames_retx": post_retx,
                    "increase": post_retx - pre_retx,
                    "threshold": retx_increase_warn,
                },
            )

        if (post_seq - pre_seq) >= seqerror_increase_warn:
            add_finding(
                findings,
                FINDING_POST_SEQERROR_INCREASE,
                SEVERITY_WARNING,
                post,
                {
                    "pre_frames_seqerror": pre_seq,
                    "post_frames_seqerror": post_seq,
                    "increase": post_seq - pre_seq,
                    "threshold": seqerror_increase_warn,
                },
            )

        if (post_max_lat - pre_max_lat) >= latency_increase_warn_ns:
            add_finding(
                findings,
                FINDING_POST_LATENCY_INCREASE,
                SEVERITY_WARNING,
                post,
                {
                    "pre_max_latency_ns": pre_max_lat,
                    "post_max_latency_ns": post_max_lat,
                    "increase": post_max_lat - pre_max_lat,
                    "threshold": latency_increase_warn_ns,
                },
            )

    return findings


def summarize_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_type = Counter(item.get("type", "unknown") for item in findings)
    by_severity = Counter(item.get("severity", "unknown") for item in findings)
    by_rx_port = Counter(item.get("rx_port", "unknown") for item in findings)
    by_flow = Counter(f"{item.get('tx_port')}->{item.get('rx_port')}:{item.get('flow_name')}" for item in findings)

    return {
        "total_findings": len(findings),
        "by_type": dict(by_type),
        "by_severity": dict(by_severity),
        "by_rx_port": dict(by_rx_port),
        "by_flow": dict(by_flow),
    }


def build_rx_port_rollup(findings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in findings:
        grouped[item.get("rx_port") or "unknown"].append(item)

    rollup: Dict[str, Dict[str, Any]] = {}
    for rx_port, items in grouped.items():
        sev_counts = Counter(item.get("severity", "unknown") for item in items)
        type_counts = Counter(item.get("type", "unknown") for item in items)

        highest = SEVERITY_INFO
        if sev_counts.get(SEVERITY_CRITICAL, 0):
            highest = SEVERITY_CRITICAL
        elif sev_counts.get(SEVERITY_WARNING, 0):
            highest = SEVERITY_WARNING

        rollup[rx_port] = {
            "rx_port": rx_port,
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
    lines: List[str] = []
    summary = report.get("summary", {})
    rx_rollup = report.get("rx_port_rollup", {})
    findings = report.get("findings", [])

    lines.append("ROCEV2 VERIFIER SUMMARY")
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

    lines.append("BY RX PORT")
    for k, v in sorted(summary.get("by_rx_port", {}).items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("RX PORT ROLL-UP")
    for _, item in sorted(
        rx_rollup.items(),
        key=lambda kv: (
            0 if kv[1]["highest_severity"] == SEVERITY_CRITICAL else
            1 if kv[1]["highest_severity"] == SEVERITY_WARNING else
            2,
            -kv[1]["count"],
            kv[1]["rx_port"],
        )
    ):
        lines.append(
            f"  [{item['highest_severity']}] {item['rx_port']} -> "
            f"{item['count']} findings {item['by_type']}"
        )
    lines.append("")

    lines.append("FINDING DETAILS")
    for item in findings:
        lines.append(json.dumps(item, sort_keys=True))
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify RoCEv2 flow stats and flag bad streams / regressions")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pre", required=True)
    parser.add_argument("--post", required=True)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)

    parser.add_argument("--delta-warn-threshold", type=int, default=100000)
    parser.add_argument("--delta-critical-threshold", type=int, default=10000000)

    parser.add_argument("--retx-warn-threshold", type=int, default=1)
    parser.add_argument("--retx-critical-threshold", type=int, default=1000000)

    parser.add_argument("--seqerr-warn-threshold", type=int, default=1)
    parser.add_argument("--seqerr-critical-threshold", type=int, default=1000000)

    parser.add_argument("--latency-warn-ns", type=int, default=10000)
    parser.add_argument("--latency-critical-ns", type=int, default=100000)

    parser.add_argument("--delta-increase-warn", type=int, default=100000)
    parser.add_argument("--retx-increase-warn", type=int, default=1000)
    parser.add_argument("--seqerror-increase-warn", type=int, default=1000)
    parser.add_argument("--latency-increase-warn-ns", type=int, default=5000)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        pre_snapshot = load_json(args.pre)
        post_snapshot = load_json(args.post)

        findings: List[Dict[str, Any]] = []

        findings.extend(evaluate_single_snapshot(
            snapshot=post_snapshot,
            delta_warn_threshold=args.delta_warn_threshold,
            delta_critical_threshold=args.delta_critical_threshold,
            retx_warn_threshold=args.retx_warn_threshold,
            retx_critical_threshold=args.retx_critical_threshold,
            seqerr_warn_threshold=args.seqerr_warn_threshold,
            seqerr_critical_threshold=args.seqerr_critical_threshold,
            latency_warn_ns=args.latency_warn_ns,
            latency_critical_ns=args.latency_critical_ns,
        ))

        findings.extend(evaluate_pre_post(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            delta_increase_warn=args.delta_increase_warn,
            retx_increase_warn=args.retx_increase_warn,
            seqerror_increase_warn=args.seqerror_increase_warn,
            latency_increase_warn_ns=args.latency_increase_warn_ns,
        ))

        summary = summarize_findings(findings)
        rx_rollup = build_rx_port_rollup(findings)
        verdict = overall_verdict(summary)

        report = {
            "source_type": args.source_type,
            "run_id": args.run_id,
            "pre_snapshot": args.pre,
            "post_snapshot": args.post,
            "verdict": verdict,
            "summary": summary,
            "rx_port_rollup": rx_rollup,
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

        print(f"RoCEv2 verifier JSON report : {out_json}")
        print(f"RoCEv2 verifier text report : {out_txt}")
        print("")
        print("ROCEV2 VERIFIER SUMMARY")
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
