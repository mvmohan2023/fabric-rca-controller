# controller/telemetry_analyzer.py

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple


ANOMALY_MISSING_RECORD = "missing_record"
ANOMALY_EMPTY_VALUE = "empty_value"
ANOMALY_STATE_CHANGE = "state_change"
ANOMALY_COUNTER_DROP = "counter_drop"
ANOMALY_COUNTER_SPIKE = "counter_spike"
ANOMALY_GAUGE_JUMP = "gauge_jump"
ANOMALY_THRESHOLD_BREACH = "threshold_breach"
ANOMALY_BOOLEAN_ALARM = "boolean_alarm"

ANOMALY_INFO_EMPTY_VALUE = "info_empty_value"
ANOMALY_INFO_RECORD_APPEARED = "info_record_appeared"
ANOMALY_INFO_RECORD_DISAPPEARED = "info_record_disappeared"


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


STABLE_OPTICS_METRICS = {
    "snmp-if-index",
    "optics-type",
    "module-temperature-c",
    "module-temperature-high-alarm",
    "module-temperature-low-alarm",
    "module-temperature-high-warning",
    "module-temperature-low-warning",
}

IGNORE_MISSING_OPTICS_METRICS = {
    "lane-number",
    "lane-laser-temperature-c",
    "lane-laser-output-power-dbm",
    "lane-laser-receiver-power-dbm",
    "lane-laser-bias-current",
    "lane-laser-output-power-high-alarm",
    "lane-laser-output-power-low-alarm",
    "lane-laser-output-power-high-warning",
    "lane-laser-output-power-low-warning",
    "lane-laser-receiver-power-high-alarm",
    "lane-laser-receiver-power-low-alarm",
    "lane-laser-receiver-power-high-warning",
    "lane-laser-receiver-power-low-warning",
    "lane-laser-bias-current-high-alarm",
    "lane-laser-bias-current-low-alarm",
    "lane-laser-bias-current-high-warning",
    "lane-laser-bias-current-low-warning",
    "lane-tx-loss-of-signal-alarm",
    "lane-rx-loss-of-signal-alarm",
    "lane-tx-laser-disabled-alarm",
    "media-fec-corr-bits",
    "media-fec-uncorr-blocks",
    "wavelength-channel",
    "wavelength-setpoint",
    "tx-dither",
    "frequency-error",
    "wavelength-error",
    "tec-fault",
    "w-unlocked-alarm",
    "tx-tune-alarm",
    "laser-output-power-high-alarm-threshold-dbm",
    "laser-output-power-low-alarm-threshold-dbm",
    "laser-output-power-high-warning-threshold-dbm",
    "laser-output-power-low-warning-threshold-dbm",
    "laser-rx-power-high-alarm-threshold-dbm",
    "laser-rx-power-low-alarm-threshold-dbm",
    "laser-rx-power-high-warning-threshold-dbm",
    "laser-rx-power-low-warning-threshold-dbm",
    "laser-bias-current-high-alarm-threshold",
    "laser-bias-current-low-alarm-threshold",
    "laser-bias-current-high-warning-threshold",
    "laser-bias-current-low-warning-threshold",
}


def load_snapshot(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_optics_record(record: Dict[str, Any]) -> bool:
    path = record.get("path", "")
    return path.startswith("/junos/system/linecard/optics/")


def metric_key(node: str, record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    entity = record.get("entity", "")
    metric = record.get("metric", "")
    path = record.get("path", "")
    return (node, entity, metric, path)


def build_metric_index(snapshot: Dict[str, Any]) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

    for node_entry in snapshot.get("nodes", []):
        node = node_entry.get("node", "")
        for record in node_entry.get("normalized_records", []):
            key = metric_key(node, record)
            index[key] = record

    return index


def merge_thresholds(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = {}
    if pre and pre.get("thresholds"):
        thresholds.update(pre["thresholds"])
    if post and post.get("thresholds"):
        thresholds.update(post["thresholds"])
    return thresholds


def detect_boolean_alarm(record: Dict[str, Any]) -> bool:
    metric = record.get("metric", "")
    value = record.get("value")
    if not isinstance(value, bool):
        return False
    if metric.endswith("-alarm") or metric.endswith("-warning"):
        return value is True
    return False


def should_flag_missing_record(record: Dict[str, Any]) -> bool:
    path = record.get("path", "")
    metric = record.get("metric", "")

    if path.startswith("/junos/system/linecard/optics/"):
        if metric in IGNORE_MISSING_OPTICS_METRICS:
            return False
        if metric in STABLE_OPTICS_METRICS:
            return True
        return False

    return True


def determine_severity(anomaly_type: str, record: Dict[str, Any]) -> str:
    if anomaly_type == ANOMALY_BOOLEAN_ALARM:
        return SEVERITY_CRITICAL

    if anomaly_type == ANOMALY_THRESHOLD_BREACH:
        return SEVERITY_CRITICAL

    if anomaly_type in (
        ANOMALY_STATE_CHANGE,
        ANOMALY_COUNTER_DROP,
        ANOMALY_COUNTER_SPIKE,
        ANOMALY_GAUGE_JUMP,
        ANOMALY_MISSING_RECORD,
    ):
        return SEVERITY_WARNING

    if anomaly_type in (
        ANOMALY_EMPTY_VALUE,
        ANOMALY_INFO_EMPTY_VALUE,
        ANOMALY_INFO_RECORD_APPEARED,
        ANOMALY_INFO_RECORD_DISAPPEARED,
    ):
        return SEVERITY_INFO

    return SEVERITY_INFO


def add_severity(anomaly: Dict[str, Any]) -> Dict[str, Any]:
    anomaly["severity"] = determine_severity(anomaly.get("type", ""), anomaly)
    return anomaly


def compare_records(
    pre: Dict[str, Any],
    post: Dict[str, Any],
    spike_ratio: float,
    gauge_delta_threshold: float,
) -> List[Dict[str, Any]]:
    anomalies: List[Dict[str, Any]] = []

    node = post.get("node") or pre.get("node")
    entity = post.get("entity") or pre.get("entity")
    metric = post.get("metric") or pre.get("metric")
    path = post.get("path") or pre.get("path")

    pre_val = pre.get("value")
    post_val = post.get("value")
    metric_type = post.get("type") or pre.get("type") or "unknown"

    if pre_val is None or post_val is None:
        anomaly_type = ANOMALY_EMPTY_VALUE
        if is_optics_record(post or pre):
            anomaly_type = ANOMALY_INFO_EMPTY_VALUE

        anomalies.append(add_severity({
            "type": anomaly_type,
            "node": node,
            "entity": entity,
            "metric": metric,
            "path": path,
            "pre_value": pre_val,
            "post_value": post_val,
        }))
        return anomalies

    if detect_boolean_alarm(post):
        anomalies.append(add_severity({
            "type": ANOMALY_BOOLEAN_ALARM,
            "node": node,
            "entity": entity,
            "metric": metric,
            "path": path,
            "value": post_val,
        }))

    thresholds = merge_thresholds(pre, post)
    if thresholds and is_number(post_val):
        min_v = thresholds.get("min")
        max_v = thresholds.get("max")
        if min_v is not None and post_val < min_v:
            anomalies.append(add_severity({
                "type": ANOMALY_THRESHOLD_BREACH,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "value": post_val,
                "threshold": {"min": min_v},
            }))
        if max_v is not None and post_val > max_v:
            anomalies.append(add_severity({
                "type": ANOMALY_THRESHOLD_BREACH,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "value": post_val,
                "threshold": {"max": max_v},
            }))

    if metric_type == "state":
        if pre_val != post_val:
            anomalies.append(add_severity({
                "type": ANOMALY_STATE_CHANGE,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "pre_value": pre_val,
                "post_value": post_val,
            }))
        return anomalies

    if metric_type == "counter" and is_number(pre_val) and is_number(post_val):
        if post_val < pre_val:
            anomalies.append(add_severity({
                "type": ANOMALY_COUNTER_DROP,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "pre_value": pre_val,
                "post_value": post_val,
            }))
        elif pre_val > 0:
            ratio = post_val / pre_val
            if ratio >= spike_ratio:
                anomalies.append(add_severity({
                    "type": ANOMALY_COUNTER_SPIKE,
                    "node": node,
                    "entity": entity,
                    "metric": metric,
                    "path": path,
                    "pre_value": pre_val,
                    "post_value": post_val,
                    "ratio": round(ratio, 2),
                }))
        return anomalies

    if metric_type == "gauge" and is_number(pre_val) and is_number(post_val):
        delta = abs(post_val - pre_val)
        if delta >= gauge_delta_threshold:
            anomalies.append(add_severity({
                "type": ANOMALY_GAUGE_JUMP,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "pre_value": pre_val,
                "post_value": post_val,
                "delta": round(delta, 3),
            }))
        return anomalies

    return anomalies


def detect_anomalies(
    pre_snapshot: Dict[str, Any],
    post_snapshot: Dict[str, Any],
    spike_ratio: float,
    gauge_delta_threshold: float,
) -> List[Dict[str, Any]]:
    pre_idx = build_metric_index(pre_snapshot)
    post_idx = build_metric_index(post_snapshot)

    all_keys = sorted(set(pre_idx.keys()) | set(post_idx.keys()))
    anomalies: List[Dict[str, Any]] = []

    for key in all_keys:
        pre = pre_idx.get(key)
        post = post_idx.get(key)

        if pre is None or post is None:
            record = post or pre or {}
            if should_flag_missing_record(record):
                if pre is None and post is not None:
                    anomaly_type = "record_appeared"
                    if is_optics_record(record):
                        anomaly_type = ANOMALY_INFO_RECORD_APPEARED
                elif pre is not None and post is None:
                    anomaly_type = "record_disappeared"
                    if is_optics_record(record):
                        anomaly_type = ANOMALY_INFO_RECORD_DISAPPEARED
                else:
                    anomaly_type = ANOMALY_MISSING_RECORD

                anomalies.append(add_severity({
                    "type": anomaly_type,
                    "node": record.get("node"),
                    "entity": record.get("entity"),
                    "metric": record.get("metric"),
                    "path": record.get("path"),
                    "pre_present": pre is not None,
                    "post_present": post is not None,
                }))
            continue

        anomalies.extend(compare_records(
            pre=pre,
            post=post,
            spike_ratio=spike_ratio,
            gauge_delta_threshold=gauge_delta_threshold,
        ))

    return anomalies


def summarize_anomalies(anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_type = Counter(item.get("type", "unknown") for item in anomalies)
    by_node = Counter(item.get("node", "unknown") for item in anomalies)
    by_severity = Counter(item.get("severity", "unknown") for item in anomalies)
    return {
        "total": len(anomalies),
        "by_type": dict(by_type),
        "by_node": dict(by_node),
        "by_severity": dict(by_severity),
    }


def build_entity_rollup(anomalies: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    rollup: Dict[str, Dict[str, Any]] = {}

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for item in anomalies:
        grouped[(item.get("node", "unknown"), item.get("entity", "unknown"))].append(item)

    for (node, entity), items in grouped.items():
        severity_counts = Counter(item.get("severity", "unknown") for item in items)
        type_counts = Counter(item.get("type", "unknown") for item in items)

        highest_severity = SEVERITY_INFO
        if severity_counts.get(SEVERITY_CRITICAL, 0):
            highest_severity = SEVERITY_CRITICAL
        elif severity_counts.get(SEVERITY_WARNING, 0):
            highest_severity = SEVERITY_WARNING

        rollup[f"{node}:{entity}"] = {
            "node": node,
            "entity": entity,
            "count": len(items),
            "highest_severity": highest_severity,
            "by_type": dict(type_counts),
            "by_severity": dict(severity_counts),
        }

    return rollup

def render_text_report(summary: Dict[str, Any], anomalies: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("TELEMETRY ANOMALY SUMMARY")
    lines.append(f"  Total anomalies : {summary.get('total', 0)}")
    lines.append("")

    lines.append("BY SEVERITY")
    for k, v in sorted(summary.get("by_severity", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("BY TYPE")
    for k, v in sorted(summary.get("by_type", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("BY NODE")
    for k, v in sorted(summary.get("by_node", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    rollup = build_entity_rollup(anomalies)

    lines.append("ENTITY ROLL-UP")
    for _, item in sorted(
        rollup.items(),
        key=lambda kv: (
            0 if kv[1]["highest_severity"] == SEVERITY_CRITICAL else
            1 if kv[1]["highest_severity"] == SEVERITY_WARNING else
            2,
            -kv[1]["count"],
            kv[1]["entity"],
        )
    ):
        lines.append(
            f"  [{item['highest_severity']}] "
            f"{item['node']} / {item['entity']} -> "
            f"{item['count']} anomalies "
            f"{item['by_type']}"
        )
    lines.append("")

    lines.append("ANOMALY DETAILS")
    for item in anomalies:
        lines.append(json.dumps(item, sort_keys=True))
    lines.append("")

    return "\n".join(lines)


def default_output_paths(post_path: str) -> Tuple[str, str]:
    directory = os.path.dirname(post_path)
    base_json = os.path.join(directory, "anomaly_report.json")
    base_txt = os.path.join(directory, "anomaly_report.txt")
    return base_json, base_txt


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze telemetry snapshots for anomalies.")
    parser.add_argument("--pre", required=True, help="pre snapshot json")
    parser.add_argument("--post", required=True, help="post snapshot json")
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-txt", default=None)
    parser.add_argument("--spike-ratio", type=float, default=5.0)
    parser.add_argument("--gauge-delta-threshold", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        pre_snapshot = load_snapshot(args.pre)
        post_snapshot = load_snapshot(args.post)

        anomalies = detect_anomalies(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            spike_ratio=args.spike_ratio,
            gauge_delta_threshold=args.gauge_delta_threshold,
        )

        summary = summarize_anomalies(anomalies)
        report = {
            "pre_snapshot": args.pre,
            "post_snapshot": args.post,
            "summary": summary,
            "entity_rollup": build_entity_rollup(anomalies),
            "anomalies": anomalies,
        }

        out_json = args.out_json
        out_txt = args.out_txt
        if not out_json or not out_txt:
            default_json, default_txt = default_output_paths(args.post)
            out_json = out_json or default_json
            out_txt = out_txt or default_txt

        write_json(out_json, report)
        write_text(out_txt, render_text_report(summary, anomalies))

        print(f"Telemetry anomaly JSON report : {out_json}")
        print(f"Telemetry anomaly text report : {out_txt}")
        print("")
        print("TELEMETRY ANOMALY SUMMARY")
        print(f"  Total anomalies : {summary.get('total', 0)}")
        for k, v in sorted(summary.get("by_severity", {}).items()):
            print(f"  {k:<22} {v}")
        for k, v in sorted(summary.get("by_type", {}).items()):
            print(f"  {k:<22} {v}")

        return 0

    except Exception as exc:  # noqa
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
