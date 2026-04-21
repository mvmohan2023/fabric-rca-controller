# controller/telemetry_diff.py

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Set, Tuple


DIFF_ENTITY_ADDED = "entity_added"
DIFF_ENTITY_REMOVED = "entity_removed"
DIFF_METRIC_ADDED = "metric_added"
DIFF_METRIC_REMOVED = "metric_removed"
DIFF_VALUE_CHANGED = "value_changed"
DIFF_STATE_CHANGED = "state_changed"


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_optics_path(path: str) -> bool:
    return path.startswith("/junos/system/linecard/optics/")


def normalize_value_for_compare(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def telemetry_dir(source_type: str, run_id: str) -> str:
    return os.path.join("artifacts", f"{source_type}s", run_id, "telemetry")


def snapshot_json_path(source_type: str, run_id: str, snapshot_name: str, profile: str) -> str:
    return os.path.join(telemetry_dir(source_type, run_id), f"{snapshot_name}_{profile}.json")


def output_paths(source_type: str, run_id: str, profile: str) -> Tuple[str, str]:
    out_dir = telemetry_dir(source_type, run_id)
    os.makedirs(out_dir, exist_ok=True)
    return (
        os.path.join(out_dir, f"diff_{profile}.json"),
        os.path.join(out_dir, f"diff_{profile}.txt"),
    )


def record_key(node: str, record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        node,
        record.get("entity", ""),
        record.get("metric", ""),
        record.get("path", ""),
    )


def entity_key(node: str, record: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        node,
        record.get("entity", ""),
        record.get("path", ""),
    )


def build_metric_index(snapshot: Dict[str, Any]) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

    for node_entry in snapshot.get("nodes", []):
        node = node_entry.get("node", "")
        for record in node_entry.get("normalized_records", []):
            index[record_key(node, record)] = record

    return index


def build_entity_index(snapshot: Dict[str, Any]) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    index: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

    for node_entry in snapshot.get("nodes", []):
        node = node_entry.get("node", "")
        for record in node_entry.get("normalized_records", []):
            index[entity_key(node, record)].append(record)

    return dict(index)


def summarize_entity_metrics(records: List[Dict[str, Any]]) -> List[str]:
    metrics = sorted({r.get("metric", "") for r in records})
    return metrics


def compare_snapshots(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    pre_metric_idx = build_metric_index(pre)
    post_metric_idx = build_metric_index(post)

    pre_entity_idx = build_entity_index(pre)
    post_entity_idx = build_entity_index(post)

    pre_entity_keys: Set[Tuple[str, str, str]] = set(pre_entity_idx.keys())
    post_entity_keys: Set[Tuple[str, str, str]] = set(post_entity_idx.keys())

    pre_metric_keys: Set[Tuple[str, str, str, str]] = set(pre_metric_idx.keys())
    post_metric_keys: Set[Tuple[str, str, str, str]] = set(post_metric_idx.keys())

    added_entity_keys = post_entity_keys - pre_entity_keys
    removed_entity_keys = pre_entity_keys - post_entity_keys

    diffs: List[Dict[str, Any]] = []

    # Entity-level added / removed
    for key in sorted(added_entity_keys):
        node, entity, path = key
        records = post_entity_idx[key]
        diffs.append({
            "type": DIFF_ENTITY_ADDED,
            "node": node,
            "entity": entity,
            "path": path,
            "metric_count": len(records),
            "metrics": summarize_entity_metrics(records),
        })

    for key in sorted(removed_entity_keys):
        node, entity, path = key
        records = pre_entity_idx[key]
        diffs.append({
            "type": DIFF_ENTITY_REMOVED,
            "node": node,
            "entity": entity,
            "path": path,
            "metric_count": len(records),
            "metrics": summarize_entity_metrics(records),
        })

    # Metric-level added / removed
    for key in sorted(post_metric_keys - pre_metric_keys):
        node, entity, metric, path = key

        # If the whole entity is new, don't also report every metric as added.
        if (node, entity, path) in added_entity_keys:
            continue

        rec = post_metric_idx[key]
        diffs.append({
            "type": DIFF_METRIC_ADDED,
            "node": node,
            "entity": entity,
            "metric": metric,
            "path": path,
            "post_value": rec.get("value"),
            "record_type": rec.get("type"),
        })

    for key in sorted(pre_metric_keys - post_metric_keys):
        node, entity, metric, path = key

        # If the whole entity is removed, don't also report every metric as removed.
        if (node, entity, path) in removed_entity_keys:
            continue

        rec = pre_metric_idx[key]
        diffs.append({
            "type": DIFF_METRIC_REMOVED,
            "node": node,
            "entity": entity,
            "metric": metric,
            "path": path,
            "pre_value": rec.get("value"),
            "record_type": rec.get("type"),
        })

    # Common metric keys: compare values / states
    for key in sorted(pre_metric_keys & post_metric_keys):
        node, entity, metric, path = key
        pre_rec = pre_metric_idx[key]
        post_rec = post_metric_idx[key]

        pre_val = normalize_value_for_compare(pre_rec.get("value"))
        post_val = normalize_value_for_compare(post_rec.get("value"))
        record_type = post_rec.get("type") or pre_rec.get("type") or "unknown"

        if pre_val == post_val:
            continue

        if record_type == "state":
            diffs.append({
                "type": DIFF_STATE_CHANGED,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "pre_value": pre_val,
                "post_value": post_val,
                "record_type": record_type,
            })
            continue

        # For numeric-like record types, emit only when both values are numeric.
        if record_type in ("gauge", "counter"):
            if not (is_number(pre_val) and is_number(post_val)):
                # Suppress malformed optics/native string churn for numeric fields.
                continue

            diffs.append({
                "type": DIFF_VALUE_CHANGED,
                "node": node,
                "entity": entity,
                "metric": metric,
                "path": path,
                "pre_value": pre_val,
                "post_value": post_val,
                "record_type": record_type,
                "delta": round(post_val - pre_val, 6),
            })
            continue

        # For optics string churn, skip noisy non-state/non-numeric compare.
        if is_optics_path(path):
            continue

        diffs.append({
            "type": DIFF_VALUE_CHANGED,
            "node": node,
            "entity": entity,
            "metric": metric,
            "path": path,
            "pre_value": pre_val,
            "post_value": post_val,
            "record_type": record_type,
        })

    by_type = Counter(item["type"] for item in diffs)
    by_node = Counter(item["node"] for item in diffs)

    return {
        "summary": {
            "total_differences": len(diffs),
            "by_type": dict(by_type),
            "by_node": dict(by_node),
        },
        "differences": diffs,
    }


def render_text_report(report: Dict[str, Any]) -> str:
    summary = report.get("summary", {})
    differences = report.get("differences", [])

    lines: List[str] = []
    lines.append("TELEMETRY DIFF SUMMARY")
    lines.append(f"  Total differences : {summary.get('total_differences', 0)}")
    lines.append("")

    lines.append("BY TYPE")
    for k, v in sorted(summary.get("by_type", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("BY NODE")
    for k, v in sorted(summary.get("by_node", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("DIFFERENCE DETAILS")
    for item in differences:
        lines.append(json.dumps(item, sort_keys=True))
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare pre/post telemetry snapshots using normalized records.")
    parser.add_argument("--source-type", required=True, choices=["orchestrator", "campaign"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pre-snapshot", required=True, help="snapshot name like pre")
    parser.add_argument("--post-snapshot", required=True, help="snapshot name like post")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        pre_path = snapshot_json_path(
            source_type=args.source_type,
            run_id=args.run_id,
            snapshot_name=args.pre_snapshot,
            profile=args.profile,
        )
        post_path = snapshot_json_path(
            source_type=args.source_type,
            run_id=args.run_id,
            snapshot_name=args.post_snapshot,
            profile=args.profile,
        )
        out_json, out_txt = output_paths(
            source_type=args.source_type,
            run_id=args.run_id,
            profile=args.profile,
        )

        pre_snapshot = load_json(pre_path)
        post_snapshot = load_json(post_path)

        diff_report = compare_snapshots(pre_snapshot, post_snapshot)
        diff_report["pre_snapshot"] = pre_path
        diff_report["post_snapshot"] = post_path

        write_json(out_json, diff_report)
        write_text(out_txt, render_text_report(diff_report))

        print(f"Telemetry diff JSON report : {out_json}")
        print(f"Telemetry diff text report : {out_txt}")
        print("")
        print("TELEMETRY DIFF SUMMARY")
        print(f"  Total differences : {diff_report['summary']['total_differences']}")
        for k, v in sorted(diff_report["summary"]["by_type"].items()):
            print(f"  {k:<18} {v}")

        return 0

    except Exception as exc:  # noqa
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
