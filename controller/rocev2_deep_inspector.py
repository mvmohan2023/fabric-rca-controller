from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value))
    except Exception:
        return 0


def safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value)
    except Exception:
        return 0.0


def classify_root_cause(verdict_summary: Dict[str, Any], top_delta: List[Dict[str, Any]], top_seqerror: List[Dict[str, Any]], top_retx: List[Dict[str, Any]], top_latency: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_type = verdict_summary.get("by_type", {}) or {}

    loss_count = by_type.get("loss", 0)
    ecn_count = by_type.get("ecn_pressure", 0)
    cnp_count = by_type.get("cnp_pressure", 0)
    seqerror_count = by_type.get("seqerror", 0)
    retx_count = by_type.get("retx", 0)
    latency_count = by_type.get("latency", 0)

    if seqerror_count > 0:
        return {
            "root_cause": "packet_reordering_or_corruption",
            "confidence": "high",
            "reason": "SeqError findings are present in RoCE flow analysis.",
        }

    if retx_count > 0 and loss_count > 0:
        return {
            "root_cause": "loss_induced_retransmission",
            "confidence": "high",
            "reason": "Loss and retransmission indicators are both present.",
        }

    if loss_count > 0 and (ecn_count > 0 or cnp_count > 0):
        return {
            "root_cause": "congestion_hotspot",
            "confidence": "high",
            "reason": "Loss is present along with ECN/CNP congestion indicators.",
        }

    if latency_count > 0:
        return {
            "root_cause": "latency_pressure",
            "confidence": "medium",
            "reason": "Latency findings are elevated without stronger error signatures.",
        }

    return {
        "root_cause": "no_clear_roce_anomaly",
        "confidence": "low",
        "reason": "No strong RoCE anomaly signature was detected.",
    }



def get_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return report.get("normalized_rows", []) or []


def flow_key(row: Dict[str, Any]) -> str:
    tx_port = row.get("tx_port") or "?"
    rx_port = row.get("rx_port") or "?"
    flow_name = row.get("flow_name") or "?"
    src_qp = row.get("src_qp") or 0
    dest_qp = row.get("dest_qp") or 0
    return f"{tx_port}|{rx_port}|{flow_name}|{src_qp}|{dest_qp}"


def score_flow(row: Dict[str, Any]) -> float:
    delta = safe_int(row.get("frames_delta"))
    retx = safe_int(row.get("retx"))
    seqerror = safe_int(row.get("seqerror"))
    msg_failed = safe_int(row.get("message_failed"))
    ecn = safe_int(row.get("ecn"))
    cnp_tx = safe_int(row.get("cnp_tx"))
    cnp_rx = safe_int(row.get("cnp_rx"))
    latency = safe_float(row.get("latency_ns"))
    max_latency = safe_float(row.get("max_latency_ns"))

    return round(
        (delta * 1.0)
        + (retx * 25.0)
        + (seqerror * 100.0)
        + (msg_failed * 300.0)
        + (ecn * 0.05)
        + ((cnp_tx + cnp_rx) * 0.05)
        + (latency * 2.0)
        + (max_latency * 0.5),
        2,
    )

def normalize_for_ui(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tx_port": row.get("tx_port"),
        "rx_port": row.get("rx_port"),
        "flow_name": row.get("flow_name"),
        "src_qp": row.get("src_qp"),
        "dest_qp": row.get("dest_qp"),
        "src_ipv4": row.get("src_ipv4"),
        "dest_ipv4": row.get("dest_ipv4"),
        "src_ipv6": row.get("src_ipv6"),
        "dest_ipv6": row.get("dest_ipv6"),
        "frames_tx": safe_int(row.get("data_frames_tx")),
        "frames_rx": safe_int(row.get("data_frames_rx")),
        "frames_delta": safe_int(row.get("frames_delta")),
        "retx": safe_int(row.get("retx")),
        "seqerror": safe_int(row.get("seqerror")),
        "message_failed": safe_int(row.get("message_failed")),
        "ecn": safe_int(row.get("ecn")),
        "cnp_tx": safe_int(row.get("cnp_tx")),
        "cnp_rx": safe_int(row.get("cnp_rx")),
        "nak_tx": safe_int(row.get("nak_tx")),
        "nak_rx": safe_int(row.get("nak_rx")),
        "latency_ns": safe_float(row.get("latency_ns")),
        "min_latency_ns": safe_float(row.get("min_latency_ns")),
        "max_latency_ns": safe_float(row.get("max_latency_ns")),
        "rate_tx_gbps": safe_float(row.get("rate_tx_gbps")),
        "rate_rx_gbps": safe_float(row.get("rate_rx_gbps")),
        "score": round(score_flow(row), 2),
    }


def top_n(rows: List[Dict[str, Any]], key: str, n: int = 10) -> List[Dict[str, Any]]:
    best_by_flow: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if safe_float(row.get(key)) <= 0:
            continue

        fk = flow_key(row)
        current = best_by_flow.get(fk)

        if current is None or safe_float(row.get(key)) > safe_float(current.get(key)):
            best_by_flow[fk] = row

    ranked = sorted(
        best_by_flow.values(),
        key=lambda r: safe_float(r.get(key)),
        reverse=True,
    )

    return [normalize_for_ui(r) for r in ranked[:n]]

def build_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {flow_key(r): r for r in rows}


def compare_pre_post(pre_rows: List[Dict[str, Any]], post_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pre_idx = build_index(pre_rows)
    post_idx = build_index(post_rows)

    merged: List[Dict[str, Any]] = []

    for key in sorted(set(pre_idx.keys()) | set(post_idx.keys())):
        pre = pre_idx.get(key, {})
        post = post_idx.get(key, {})

        row = dict(post or pre)
        row["frames_delta_pre"] = safe_int(pre.get("frames_delta"))
        row["frames_delta_post"] = safe_int(post.get("frames_delta"))
        row["frames_delta_increase"] = row["frames_delta_post"] - row["frames_delta_pre"]

        row["retx_pre"] = safe_int(pre.get("retx"))
        row["retx_post"] = safe_int(post.get("retx"))
        row["retx_increase"] = row["retx_post"] - row["retx_pre"]

        row["seqerror_pre"] = safe_int(pre.get("seqerror"))
        row["seqerror_post"] = safe_int(post.get("seqerror"))
        row["seqerror_increase"] = row["seqerror_post"] - row["seqerror_pre"]

        row["message_failed_pre"] = safe_int(pre.get("message_failed"))
        row["message_failed_post"] = safe_int(post.get("message_failed"))
        row["message_failed_increase"] = row["message_failed_post"] - row["message_failed_pre"]

        row["ecn_pre"] = safe_int(pre.get("ecn"))
        row["ecn_post"] = safe_int(post.get("ecn"))
        row["ecn_increase"] = row["ecn_post"] - row["ecn_pre"]

        row["impact_score"] = round(score_flow(post or pre), 2)
        merged.append(row)

    return merged


def build_rx_rollup(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rollup: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        rx_port = row.get("rx_port") or "unknown"
        entry = rollup.setdefault(
            rx_port,
            {
                "rx_port": rx_port,
                "flows": 0,
                "frames_delta": 0,
                "retx": 0,
                "seqerror": 0,
                "message_failed": 0,
                "ecn": 0,
                "cnp_tx": 0,
                "cnp_rx": 0,
                "max_latency_ns": 0.0,
                "avg_latency_ns_sum": 0.0,
            },
        )

        entry["flows"] += 1
        entry["frames_delta"] += safe_int(row.get("frames_delta"))
        entry["retx"] += safe_int(row.get("retx"))
        entry["seqerror"] += safe_int(row.get("seqerror"))
        entry["message_failed"] += safe_int(row.get("message_failed"))
        entry["ecn"] += safe_int(row.get("ecn"))
        entry["cnp_tx"] += safe_int(row.get("cnp_tx"))
        entry["cnp_rx"] += safe_int(row.get("cnp_rx"))
        entry["max_latency_ns"] = max(entry["max_latency_ns"], safe_float(row.get("max_latency_ns")))
        entry["avg_latency_ns_sum"] += safe_float(row.get("latency_ns"))

    result = []
    for rx_port, entry in rollup.items():
        flows = max(entry["flows"], 1)
        entry["avg_latency_ns"] = round(entry["avg_latency_ns_sum"] / flows, 2)
        del entry["avg_latency_ns_sum"]
        entry["score"] = round(
            entry["frames_delta"]
            + entry["retx"] * 20
            + entry["seqerror"] * 50
            + entry["message_failed"] * 200
            + entry["ecn"] * 0.05
            + (entry["cnp_tx"] + entry["cnp_rx"]) * 0.05
            + entry["max_latency_ns"] * 0.5,
            2,
        )
        result.append(entry)

    return sorted(result, key=lambda x: x["score"], reverse=True)


def build_verdict_summary(post_rows: List[Dict[str, Any]], compared_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Tunable thresholds
    LOSS_THRESHOLD = 1000
    MSG_FAIL_THRESHOLD = 10
    ECN_THRESHOLD = 10000
    CNP_THRESHOLD = 10000
    RETX_THRESHOLD = 1
    SEQERROR_THRESHOLD = 1
    LATENCY_THRESHOLD_NS = 20000

    findings = []

    signal_breakdown = {
        "loss": 0,
        "retx": 0,
        "seqerror": 0,
        "message_failed": 0,
        "ecn_pressure": 0,
        "cnp_pressure": 0,
        "latency": 0,
    }

    for row in post_rows:
        flow_id = flow_key(row)
        delta = safe_int(row.get("frames_delta"))
        retx = safe_int(row.get("retx"))
        seqerror = safe_int(row.get("seqerror"))
        msg_failed = safe_int(row.get("message_failed"))
        ecn = safe_int(row.get("ecn"))
        cnp = safe_int(row.get("cnp_tx")) + safe_int(row.get("cnp_rx"))
        latency = safe_float(row.get("latency_ns"))

        if delta > LOSS_THRESHOLD:
            findings.append({"flow": flow_id, "type": "loss", "severity": "warn", "value": delta})
            signal_breakdown["loss"] += 1

        if retx >= RETX_THRESHOLD:
            findings.append({"flow": flow_id, "type": "retx", "severity": "warn", "value": retx})
            signal_breakdown["retx"] += 1

        if seqerror >= SEQERROR_THRESHOLD:
            findings.append({"flow": flow_id, "type": "seqerror", "severity": "fail", "value": seqerror})
            signal_breakdown["seqerror"] += 1

        if msg_failed > MSG_FAIL_THRESHOLD:
            findings.append({"flow": flow_id, "type": "message_failed", "severity": "fail", "value": msg_failed})
            signal_breakdown["message_failed"] += 1

        if ecn > ECN_THRESHOLD:
            findings.append({"flow": flow_id, "type": "ecn_pressure", "severity": "info", "value": ecn})
            signal_breakdown["ecn_pressure"] += 1

        if cnp > CNP_THRESHOLD:
            findings.append({"flow": flow_id, "type": "cnp_pressure", "severity": "info", "value": cnp})
            signal_breakdown["cnp_pressure"] += 1

        if latency > LATENCY_THRESHOLD_NS:
            findings.append({"flow": flow_id, "type": "latency", "severity": "warn", "value": latency})
            signal_breakdown["latency"] += 1

    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    by_rx_port: Dict[str, int] = {}
    by_flow: Dict[str, int] = {}

    for item in findings:
        by_type[item["type"]] = by_type.get(item["type"], 0) + 1
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        flow = item["flow"]
        by_flow[flow] = by_flow.get(flow, 0) + 1
        rx_port = flow.split("|")[1] if "|" in flow else "unknown"
        by_rx_port[rx_port] = by_rx_port.get(rx_port, 0) + 1

    if by_severity.get("fail", 0) > 0:
        verdict = "fail"
    elif by_severity.get("warn", 0) > 0:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "verdict": verdict,
        "total_findings": len(findings),
        "by_type": by_type,
        "by_severity": by_severity,
        "by_rx_port": by_rx_port,
        "by_flow": by_flow,
        "signal_breakdown": signal_breakdown,
        "findings": findings[:200],
    }

def classify_root_cause(verdict_summary: Dict[str, Any]) -> Dict[str, Any]:
    signal_breakdown = verdict_summary.get("signal_breakdown", {}) or {}

    loss_count = signal_breakdown.get("loss", 0)
    retx_count = signal_breakdown.get("retx", 0)
    seqerror_count = signal_breakdown.get("seqerror", 0)
    msg_failed_count = signal_breakdown.get("message_failed", 0)
    ecn_count = signal_breakdown.get("ecn_pressure", 0)
    cnp_count = signal_breakdown.get("cnp_pressure", 0)
    latency_count = signal_breakdown.get("latency", 0)

    if seqerror_count > 0:
        return {
            "root_cause": "packet_reordering_or_corruption",
            "confidence": "high",
            "reason": "SeqError indicators are present in the affected flow set.",
        }

    if retx_count > 0 and loss_count > 0:
        return {
            "root_cause": "loss_induced_retransmission",
            "confidence": "high",
            "reason": "Both loss and retransmission indicators are present.",
        }

    if loss_count > 0 and (ecn_count > 0 or cnp_count > 0):
        return {
            "root_cause": "congestion_hotspot",
            "confidence": "high",
            "reason": "Loss is present along with ECN/CNP congestion indicators.",
        }

    if latency_count > 0 and msg_failed_count > 0:
        return {
            "root_cause": "receiver_or_path_pressure",
            "confidence": "medium",
            "reason": "Latency and message failure indicators are elevated.",
        }

    if latency_count > 0:
        return {
            "root_cause": "latency_pressure",
            "confidence": "medium",
            "reason": "Latency indicators are elevated without stronger error signatures.",
        }

    return {
        "root_cause": "no_clear_roce_anomaly",
        "confidence": "low",
        "reason": "No dominant RoCE anomaly signature was detected.",
    }

def inspect(
    pre_path: str,
    post_path: str,
    verdict_path: str,
    output_path: str,
    run_id: str,
    source_type: str,
) -> Dict[str, Any]:
    pre_report = load_json(pre_path)
    post_report = load_json(post_path)

    pre_rows = get_rows(pre_report)
    post_rows = get_rows(post_report)
    compared_rows = compare_pre_post(pre_rows, post_rows)
    rx_rollup = build_rx_rollup(post_rows)

    top_by_delta = top_n(post_rows, "frames_delta", 10)
    top_by_retx = top_n(post_rows, "retx", 10)
    top_by_seqerror = top_n(post_rows, "seqerror", 10)
    top_by_latency = top_n(post_rows, "latency_ns", 10)

    top_by_delta_increase = top_n(compared_rows, "frames_delta_increase", 10)
    top_by_retx_increase = top_n(compared_rows, "retx_increase", 10)
    top_by_seqerror_increase = top_n(compared_rows, "seqerror_increase", 10)

    verdict_summary = build_verdict_summary(post_rows, compared_rows)
    root_cause_summary = classify_root_cause(verdict_summary)

    ecmp_correlation = {
        "candidate_rx_ports": [item.get("rx_port") for item in rx_rollup[:5]],
        "candidate_fabric_interfaces": [],
        "correlation_hint": "Correlate impacted RX ports with ECMP recovery and ingress skew evidence.",
    }

    output = {
        "run_id": run_id,
        "source_type": source_type,
        "pre_snapshot": pre_path,
        "post_snapshot": post_path,
        "verdict_path": verdict_path,
        "total_flows": len(post_rows),
        "rx_rollup": rx_rollup,
        "top_by_delta": top_by_delta,
        "top_by_retx": top_by_retx,
        "top_by_seqerror": top_by_seqerror,
        "top_by_latency": top_by_latency,
        "top_by_delta_increase": top_by_delta_increase,
        "top_by_retx_increase": top_by_retx_increase,
        "top_by_seqerror_increase": top_by_seqerror_increase,
        "hotspot_summary": {
            "top_rx_ports": rx_rollup[:10],
        },
        "verdict_summary": verdict_summary,
        "root_cause_summary": root_cause_summary,
        "ecmp_correlation": ecmp_correlation,
    }

    save_json(output_path, output)
    return output

def main() -> None:
    parser = argparse.ArgumentParser(description="RoCEv2 deep inspection")
    parser.add_argument("--pre", required=True)
    parser.add_argument("--post", required=True)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-type", default="campaign")
    args = parser.parse_args()

    out = inspect(
        pre_path=args.pre,
        post_path=args.post,
        verdict_path=args.verdict,
        output_path=args.output,
        run_id=args.run_id,
        source_type=args.source_type,
    )
    print(json.dumps({
        "output": args.output,
        "total_flows": out["total_flows"],
        "verdict": out["verdict_summary"]["verdict"],
        "total_findings": out["verdict_summary"]["total_findings"],
    }, indent=2))


if __name__ == "__main__":
    main()
