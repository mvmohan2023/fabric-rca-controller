from __future__ import annotations

import json
import os
import statistics
from typing import Any, Dict, List, Optional

def _normalize_iface_name(iface: str) -> str:
    if not iface:
        return ""
    return str(iface).strip().lower()

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = 0) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _get_node_block(report: Dict[str, Any], node: str) -> Optional[Dict[str, Any]]:
    for item in report.get("nodes", []):
        if str(item.get("node", "")).lower() == str(node).lower():
            return item
    return None


def _get_snapshot_timestamp(report: Dict[str, Any]) -> Optional[float]:
    for key in ("captured_epoch", "timestamp_epoch", "generated_epoch"):
        if key in report:
            try:
                return float(report[key])
            except Exception:
                pass
    return None


def extract_interface_counters_from_snapshot(
    *,
    snapshot_path: str,
    node: str,
) -> Dict[str, Dict[str, Optional[int]]]:
    report = _load_json_file(snapshot_path)
    node_block = _get_node_block(report, node)
    if not node_block:
        return {}

    counters: Dict[str, Dict[str, Optional[int]]] = {}

    def _touch(iface: str) -> Dict[str, Optional[int]]:
        if iface not in counters:
            counters[iface] = {
                "in_octets": None,
                "out_octets": None,
                "carrier_transitions": None,
            }
        return counters[iface]

    normalized_records = node_block.get("normalized_records", []) or []
    for rec in normalized_records:
        if not isinstance(rec, dict):
            continue

        path = str(rec.get("path", ""))
        metric = str(rec.get("metric", "") or rec.get("update_path", "")).strip()
        value = rec.get("value")

        iface = None
        marker = "/interfaces/interface[name="
        if marker in path:
            try:
                start = path.index(marker) + len(marker)
                end = path.index("]", start)
                iface = path[start:end].strip("'\"")
            except Exception:
                iface = None

        if not iface:
            continue

        entry = _touch(iface)

        metric_l = metric.lower()
        if metric_l == "in-octets":
            entry["in_octets"] = _safe_int(value, None)
        elif metric_l == "out-octets":
            entry["out_octets"] = _safe_int(value, None)
        elif metric_l == "carrier-transitions":
            entry["carrier_transitions"] = _safe_int(value, None)

    return counters


def _compute_interval_seconds(
    older_report: Dict[str, Any],
    newer_report: Dict[str, Any],
    default_interval_seconds: int,
) -> float:
    t1 = _get_snapshot_timestamp(older_report)
    t2 = _get_snapshot_timestamp(newer_report)
    if t1 is not None and t2 is not None and t2 > t1:
        return float(t2 - t1)
    return float(default_interval_seconds)


def _compute_rate_bps(
    old_value: Optional[int],
    new_value: Optional[int],
    interval_seconds: float,
) -> Optional[float]:
    if old_value is None or new_value is None:
        return None
    if interval_seconds <= 0:
        return None

    delta = new_value - old_value
    if delta < 0:
        return None

    return (delta * 8.0) / interval_seconds


def _summarize_share_skew(shares: Dict[str, float]) -> Dict[str, float]:
    if not shares:
        return {
            "max_share": 0.0,
            "min_share": 0.0,
            "spread": 0.0,
            "stddev": 0.0,
        }

    values = list(shares.values())
    return {
        "max_share": round(max(values), 4),
        "min_share": round(min(values), 4),
        "spread": round(max(values) - min(values), 4),
        "stddev": round(statistics.pstdev(values) if len(values) > 1 else 0.0, 4),
    }


def _summarize_numeric(values_map: Dict[str, float], max_key: str, min_key: str) -> Dict[str, float]:
    if not values_map:
        return {
            max_key: 0.0,
            min_key: 0.0,
            "spread": 0.0,
            "stddev": 0.0,
        }

    values = list(values_map.values())
    return {
        max_key: round(max(values), 4),
        min_key: round(min(values), 4),
        "spread": round(max(values) - min(values), 4),
        "stddev": round(statistics.pstdev(values) if len(values) > 1 else 0.0, 4),
    }


def _dominant_port(shares: Dict[str, float]) -> Optional[str]:
    if not shares:
        return None
    return max(shares, key=shares.get)


def _flip_count(sequence: List[str]) -> int:
    flips = 0
    for idx in range(1, len(sequence)):
        if sequence[idx] != sequence[idx - 1]:
            flips += 1
    return flips


def _speed_to_gbps(speed: Optional[str]) -> float:
    if not speed:
        return 0.0
    s = str(speed).strip().upper().replace(" ", "")
    if s.endswith("GBPS"):
        s = s[:-4] + "G"
    elif s.endswith("MBPS"):
        s = s[:-4] + "M"

    if s.endswith("G"):
        return _safe_float(s[:-1], 0.0)
    if s.endswith("M"):
        return _safe_float(s[:-1], 0.0) / 1000.0
    return 0.0


def _bucket_interfaces_by_speed(
    interfaces: List[str],
    interface_speeds: Optional[Dict[str, str]],
) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {}
    speed_map = interface_speeds or {}

    for iface in interfaces:
        speed = str(speed_map.get(iface, "UNKNOWN") or "UNKNOWN")
        buckets.setdefault(speed, []).append(iface)

    return {speed: sorted(ifaces) for speed, ifaces in buckets.items()}


def _top_ranked_items(values: Dict[str, float], reverse: bool, limit: int = 5) -> List[Dict[str, Any]]:
    ranked = sorted(values.items(), key=lambda x: x[1], reverse=reverse)[:limit]
    return [{"interface": k, "value": round(v, 4)} for k, v in ranked]


def _summarize_speed_groups_for_interval(
    *,
    interfaces: List[str],
    shares: Dict[str, float],
    expected_shares: Dict[str, float],
    imbalance_ratio: Dict[str, float],
    interface_speeds: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    speed_groups = _bucket_interfaces_by_speed(interfaces, interface_speeds)
    summary: Dict[str, Any] = {}

    for speed, members in speed_groups.items():
        member_actual = {m: _safe_float(shares.get(m), 0.0) for m in members}
        member_expected = {m: _safe_float(expected_shares.get(m), 0.0) for m in members}
        member_ratio = {m: _safe_float(imbalance_ratio.get(m), 0.0) for m in members}

        actual_total = sum(member_actual.values())
        expected_total = sum(member_expected.values())
        actual_spread = max(member_actual.values()) - min(member_actual.values()) if member_actual else 0.0
        ratio_spread = max(member_ratio.values()) - min(member_ratio.values()) if member_ratio else 0.0

        summary[speed] = {
            "members": members,
            "member_count": len(members),
            "actual_share_total": round(actual_total, 4),
            "expected_share_total": round(expected_total, 4),
            "actual_minus_expected_total": round(actual_total - expected_total, 4),
            "actual_share_spread": round(actual_spread, 4),
            "imbalance_ratio_spread": round(ratio_spread, 4),
            "mean_actual_share": round(statistics.mean(member_actual.values()), 4) if member_actual else 0.0,
            "mean_expected_share": round(statistics.mean(member_expected.values()), 4) if member_expected else 0.0,
            "mean_imbalance_ratio": round(statistics.mean(member_ratio.values()), 4) if member_ratio else 0.0,
        }

    return summary


def build_rate_intervals(
    *,
    sample_paths: List[str],
    node: str,
    interfaces_of_interest: Optional[List[str]] = None,
    interface_speeds: Optional[Dict[str, str]] = None,
    default_interval_seconds: int = 10,
) -> Dict[str, Any]:
    if len(sample_paths) < 2:
        return {
            "sample_paths": sample_paths,
            "intervals": [],
            "interfaces": interfaces_of_interest or [],
        }

    #interfaces_filter = set(interfaces_of_interest or [])
    interfaces_filter = set(_normalize_iface_name(x) for x in (interfaces_of_interest or []))
    speed_map = interface_speeds or {}

    intervals: List[Dict[str, Any]] = []
    all_seen_interfaces: List[str] = []

    loaded_reports = [_load_json_file(path) for path in sample_paths]

    for idx in range(1, len(sample_paths)):
        prev_path = sample_paths[idx - 1]
        curr_path = sample_paths[idx]
        prev_report = loaded_reports[idx - 1]
        curr_report = loaded_reports[idx]

        prev_counters = extract_interface_counters_from_snapshot(
            snapshot_path=prev_path,
            node=node,
        )
        curr_counters = extract_interface_counters_from_snapshot(
            snapshot_path=curr_path,
            node=node,
        )

        interval_seconds = _compute_interval_seconds(
            prev_report,
            curr_report,
            default_interval_seconds=default_interval_seconds,
        )

        candidate_ifaces = sorted(set(prev_counters.keys()) | set(curr_counters.keys()))
        if interfaces_filter:
            candidate_ifaces = [
                x for x in candidate_ifaces
                if _normalize_iface_name(x) in interfaces_filter
            ]

        rates_in_bps: Dict[str, float] = {}
        rates_out_bps: Dict[str, float] = {}
        carrier_transition_delta: Dict[str, int] = {}

        for iface in candidate_ifaces:
            prev_item = prev_counters.get(iface, {})
            curr_item = curr_counters.get(iface, {})

            in_bps = _compute_rate_bps(
                prev_item.get("in_octets"),
                curr_item.get("in_octets"),
                interval_seconds,
            )
            out_bps = _compute_rate_bps(
                prev_item.get("out_octets"),
                curr_item.get("out_octets"),
                interval_seconds,
            )

            prev_carrier = _safe_int(prev_item.get("carrier_transitions"), 0) or 0
            curr_carrier = _safe_int(curr_item.get("carrier_transitions"), 0) or 0
            delta_carrier = max(0, curr_carrier - prev_carrier)

            if in_bps is not None:
                rates_in_bps[iface] = round(in_bps, 2)
            if out_bps is not None:
                rates_out_bps[iface] = round(out_bps, 2)
            carrier_transition_delta[iface] = delta_carrier

            if iface not in all_seen_interfaces:
                all_seen_interfaces.append(iface)

        total_in_bps = sum(rates_in_bps.values())

        shares: Dict[str, float] = {}
        expected_shares: Dict[str, float] = {}
        imbalance_ratio: Dict[str, float] = {}
        share_delta_vs_expected: Dict[str, float] = {}
        capacity_gbps: Dict[str, float] = {}

        for iface in rates_in_bps:
            capacity_gbps[iface] = _speed_to_gbps(speed_map.get(iface))

        total_capacity_gbps = sum(capacity_gbps.values())

        if total_in_bps > 0:
            for iface, rate in rates_in_bps.items():
                actual_share = rate / total_in_bps
                shares[iface] = round(actual_share, 4)

                expected_share = (
                    capacity_gbps.get(iface, 0.0) / total_capacity_gbps
                    if total_capacity_gbps > 0
                    else 0.0
                )
                expected_shares[iface] = round(expected_share, 4)
                share_delta_vs_expected[iface] = round(actual_share - expected_share, 4)

                if expected_share > 0:
                    imbalance_ratio[iface] = round(actual_share / expected_share, 3)
                else:
                    imbalance_ratio[iface] = 0.0

        speed_group_summary = _summarize_speed_groups_for_interval(
            interfaces=candidate_ifaces,
            shares=shares,
            expected_shares=expected_shares,
            imbalance_ratio=imbalance_ratio,
            interface_speeds=speed_map,
        )

        interval_entry = {
            "from_sample": os.path.basename(prev_path),
            "to_sample": os.path.basename(curr_path),
            "interval_seconds": round(interval_seconds, 3),
            "rates_in_bps": rates_in_bps,
            "rates_out_bps": rates_out_bps,
            "shares": shares,
            "expected_shares": expected_shares,
            "imbalance_ratio": imbalance_ratio,
            "share_delta_vs_expected": share_delta_vs_expected,
            "capacity_gbps": capacity_gbps,
            "total_capacity_gbps": round(total_capacity_gbps, 3),
            "carrier_transition_delta": carrier_transition_delta,
            "skew": _summarize_share_skew(shares),
            "imbalance_skew": _summarize_numeric(imbalance_ratio, "max_ratio", "min_ratio"),
            "share_delta_skew": _summarize_numeric(share_delta_vs_expected, "max_delta", "min_delta"),
            "dominant_port": _dominant_port(shares),
            "total_in_bps": round(total_in_bps, 2),
            "speed_group_summary": speed_group_summary,
        }
        intervals.append(interval_entry)

    dominant_sequence = [
        item["dominant_port"]
        for item in intervals
        if item.get("dominant_port")
    ]

    return {
        "sample_paths": sample_paths,
        "interfaces": all_seen_interfaces,
        "intervals": intervals,
        "dominant_port_sequence": dominant_sequence,
        "dominant_port_flips": _flip_count(dominant_sequence),
    }


def summarize_window(window_report: Dict[str, Any], interface_speeds: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    intervals = window_report.get("intervals", [])
    if not intervals:
        return {
            "avg_spread": 0.0,
            "avg_stddev": 0.0,
            "avg_total_in_bps": 0.0,
            "avg_imbalance_spread": 0.0,
            "avg_imbalance_stddev": 0.0,
            "avg_share_delta_spread": 0.0,
            "dominant_port_sequence": [],
            "dominant_port_flips": 0,
            "mean_share_by_port": {},
            "mean_expected_share_by_port": {},
            "mean_imbalance_ratio_by_port": {},
            "mean_share_delta_by_port": {},
            "speed_group_summary": {},
            "top_overloaded_ports": [],
            "top_underloaded_ports": [],
        }

    avg_spread = statistics.mean(
        _safe_float(item.get("skew", {}).get("spread"), 0.0) for item in intervals
    )
    avg_stddev = statistics.mean(
        _safe_float(item.get("skew", {}).get("stddev"), 0.0) for item in intervals
    )
    avg_total_in_bps = statistics.mean(
        _safe_float(item.get("total_in_bps"), 0.0) for item in intervals
    )
    avg_imbalance_spread = statistics.mean(
        _safe_float(item.get("imbalance_skew", {}).get("spread"), 0.0) for item in intervals
    )
    avg_imbalance_stddev = statistics.mean(
        _safe_float(item.get("imbalance_skew", {}).get("stddev"), 0.0) for item in intervals
    )
    avg_share_delta_spread = statistics.mean(
        _safe_float(item.get("share_delta_skew", {}).get("spread"), 0.0) for item in intervals
    )

    port_share_values: Dict[str, List[float]] = {}
    port_expected_share_values: Dict[str, List[float]] = {}
    port_imbalance_ratio_values: Dict[str, List[float]] = {}
    port_share_delta_values: Dict[str, List[float]] = {}

    for item in intervals:
        for iface, share in item.get("shares", {}).items():
            port_share_values.setdefault(iface, []).append(_safe_float(share, 0.0))
        for iface, share in item.get("expected_shares", {}).items():
            port_expected_share_values.setdefault(iface, []).append(_safe_float(share, 0.0))
        for iface, ratio in item.get("imbalance_ratio", {}).items():
            port_imbalance_ratio_values.setdefault(iface, []).append(_safe_float(ratio, 0.0))
        for iface, delta in item.get("share_delta_vs_expected", {}).items():
            port_share_delta_values.setdefault(iface, []).append(_safe_float(delta, 0.0))

    mean_share_by_port = {
        iface: round(statistics.mean(values), 4)
        for iface, values in port_share_values.items()
        if values
    }
    mean_expected_share_by_port = {
        iface: round(statistics.mean(values), 4)
        for iface, values in port_expected_share_values.items()
        if values
    }
    mean_imbalance_ratio_by_port = {
        iface: round(statistics.mean(values), 4)
        for iface, values in port_imbalance_ratio_values.items()
        if values
    }
    mean_share_delta_by_port = {
        iface: round(statistics.mean(values), 4)
        for iface, values in port_share_delta_values.items()
        if values
    }

    # Window-level speed-group summary from mean values
    all_interfaces = sorted(set(mean_share_by_port.keys()) | set(mean_expected_share_by_port.keys()))
    speed_groups = _bucket_interfaces_by_speed(all_interfaces, interface_speeds)
    speed_group_summary: Dict[str, Any] = {}

    for speed, members in speed_groups.items():
        member_actual = {m: _safe_float(mean_share_by_port.get(m), 0.0) for m in members}
        member_expected = {m: _safe_float(mean_expected_share_by_port.get(m), 0.0) for m in members}
        member_ratio = {m: _safe_float(mean_imbalance_ratio_by_port.get(m), 0.0) for m in members}

        actual_total = sum(member_actual.values())
        expected_total = sum(member_expected.values())
        actual_spread = max(member_actual.values()) - min(member_actual.values()) if member_actual else 0.0
        ratio_spread = max(member_ratio.values()) - min(member_ratio.values()) if member_ratio else 0.0

        speed_group_summary[speed] = {
            "members": members,
            "member_count": len(members),
            "actual_share_total": round(actual_total, 4),
            "expected_share_total": round(expected_total, 4),
            "actual_minus_expected_total": round(actual_total - expected_total, 4),
            "actual_share_spread": round(actual_spread, 4),
            "imbalance_ratio_spread": round(ratio_spread, 4),
            "mean_actual_share": round(statistics.mean(member_actual.values()), 4) if member_actual else 0.0,
            "mean_expected_share": round(statistics.mean(member_expected.values()), 4) if member_expected else 0.0,
            "mean_imbalance_ratio": round(statistics.mean(member_ratio.values()), 4) if member_ratio else 0.0,
        }

    
    speed_group_top_ports: Dict[str, Any] = {}
    for speed, group in speed_group_summary.items():
        members = group.get("members", [])

        group_ratios = {
            iface: mean_imbalance_ratio_by_port.get(iface, 0.0)
            for iface in members
            if iface in mean_imbalance_ratio_by_port
        }

        speed_group_top_ports[speed] = {
            "top_overloaded_ports": _top_ranked_items(group_ratios, reverse=True, limit=3),
            "top_underloaded_ports": _top_ranked_items(group_ratios, reverse=False, limit=3),
        }

    dominant_port_sequence = window_report.get("dominant_port_sequence", [])
    dominant_port_persistence = 0.0

    if dominant_port_sequence:
        most_common_port = max(
            set(dominant_port_sequence),
            key=dominant_port_sequence.count,
        )
        dominant_port_persistence = round(
            dominant_port_sequence.count(most_common_port) / float(len(dominant_port_sequence)),
            4,
        )

    if not intervals:
        return {
            "avg_spread": 0.0,
            "avg_stddev": 0.0,
            "avg_total_in_bps": 0.0,
            "avg_imbalance_spread": 0.0,
            "avg_imbalance_stddev": 0.0,
            "avg_share_delta_spread": 0.0,
            "dominant_port_sequence": [],
            "dominant_port_flips": 0,
            "dominant_port_persistence": 0.0,
            "mean_share_by_port": {},
            "mean_expected_share_by_port": {},
            "mean_imbalance_ratio_by_port": {},
            "mean_share_delta_by_port": {},
            "speed_group_summary": {},
            "top_overloaded_ports": [],
            "top_underloaded_ports": [],
            "speed_group_top_ports": {},
        }
    return {
        "avg_spread": round(avg_spread, 4),
        "avg_stddev": round(avg_stddev, 4),
        "avg_total_in_bps": round(avg_total_in_bps, 2),
        "avg_imbalance_spread": round(avg_imbalance_spread, 4),
        "avg_imbalance_stddev": round(avg_imbalance_stddev, 4),
        "avg_share_delta_spread": round(avg_share_delta_spread, 4),
        "dominant_port_sequence": window_report.get("dominant_port_sequence", []),
        "dominant_port_flips": window_report.get("dominant_port_flips", 0),
        "dominant_port_persistence": dominant_port_persistence,
        "mean_share_by_port": mean_share_by_port,
        "mean_expected_share_by_port": mean_expected_share_by_port,
        "mean_imbalance_ratio_by_port": mean_imbalance_ratio_by_port,
        "mean_share_delta_by_port": mean_share_delta_by_port,
        "speed_group_summary": speed_group_summary,
        "top_overloaded_ports": _top_ranked_items(mean_imbalance_ratio_by_port, reverse=True, limit=5),
        "top_underloaded_ports": _top_ranked_items(mean_imbalance_ratio_by_port, reverse=False, limit=5),
        "speed_group_top_ports": speed_group_top_ports,
    }


def classify_ecmp_behavior(
    *,
    baseline_summary: Dict[str, Any],
    recovery_summary: Dict[str, Any],
    q8_taildrop_growth: Optional[float] = None,
) -> Dict[str, Any]:
    base_spread = _safe_float(baseline_summary.get("avg_spread"), 0.0)
    rec_spread = _safe_float(recovery_summary.get("avg_spread"), 0.0)
    spread_delta = rec_spread - base_spread

    base_imbalance_spread = _safe_float(baseline_summary.get("avg_imbalance_spread"), 0.0)
    rec_imbalance_spread = _safe_float(recovery_summary.get("avg_imbalance_spread"), 0.0)
    imbalance_spread_delta = rec_imbalance_spread - base_imbalance_spread

    rec_share_delta_spread = _safe_float(recovery_summary.get("avg_share_delta_spread"), 0.0)
    rec_flips = int(recovery_summary.get("dominant_port_flips", 0))

    recovery_speed_groups = recovery_summary.get("speed_group_summary", {}) or {}
    rec_400g_spread = _safe_float(
        (recovery_speed_groups.get("400G") or {}).get("actual_share_spread"),
        0.0,
    )
    rec_100g_spread = _safe_float(
        (recovery_speed_groups.get("100G") or {}).get("actual_share_spread"),
        0.0,
    )
    rec_400g_ratio_spread = _safe_float(
        (recovery_speed_groups.get("400G") or {}).get("imbalance_ratio_spread"),
        0.0,
    )
    rec_100g_ratio_spread = _safe_float(
        (recovery_speed_groups.get("100G") or {}).get("imbalance_ratio_spread"),
        0.0,
    )


    rec_share_delta_spread = _safe_float(recovery_summary.get("avg_share_delta_spread"), 0.0)
    rec_flips = int(recovery_summary.get("dominant_port_flips", 0))

    recovery_speed_groups = recovery_summary.get("speed_group_summary", {}) or {}
    high_ratio_spread = 0.0
    for group_data in recovery_speed_groups.values():
        high_ratio_spread = max(
            high_ratio_spread,
            _safe_float(group_data.get("imbalance_ratio_spread"), 0.0),
        )

    classification = "balanced_recovery"
    reason = "recovery traffic distribution looks stable"
    confidence = "medium"
    severity = "low"

    if rec_imbalance_spread >= 3.0 or rec_400g_spread >= 0.10:
        classification = "persistent_mixed_speed_skew"
        reason = (
            "recovery traffic remains materially imbalanced relative to "
            "speed-weighted expectation, especially within the 400G group"
        )
        confidence = "high"
        severity = "critical"
    elif rec_share_delta_spread >= 0.10 and rec_flips <= 1:
        classification = "sticky_flow_bias_after_recovery"
        reason = (
            "recovery traffic shows persistent deviation from expected per-member "
            "share with limited dominant-port movement"
        )
        confidence = "high"
        severity = "high"
    elif rec_flips >= 2:
        classification = "ecmp_toggling_after_recovery"
        reason = "dominant ECMP member flips repeatedly across recovery intervals"
        confidence = "high"
        severity = "high"
    elif rec_imbalance_spread >= 1.0 or rec_100g_ratio_spread >= 1.5:
        classification = "mild_skew_after_recovery"
        reason = "recovery traffic is somewhat imbalanced relative to speed-weighted expectation"
        confidence = "medium"
        severity = "medium"
    elif rec_spread >= 0.10:
        classification = "stable_but_uneven_distribution"
        reason = "recovery traffic is stable, but same-speed ECMP members are unevenly utilized"
        confidence = "medium"
        severity = "medium"


    if q8_taildrop_growth is not None and q8_taildrop_growth > 0:
        if classification in (
            "persistent_mixed_speed_skew",
            "sticky_flow_bias_after_recovery",
            "ecmp_toggling_after_recovery",
            "mild_skew_after_recovery",
            "stable_but_uneven_distribution",
        ):
            reason += "; this aligns with continued q8 taildrop growth"
        else:
            classification = "taildrop_growth_without_strong_ecmp_signal"
            reason = "q8 taildrop grows, but ECMP skew/toggling signal is weak"
            confidence = "medium"

    return {
        "classification": classification,
        "reason": reason,
        "confidence": confidence,
        "severity": severity,
        "baseline_avg_spread": round(base_spread, 4),
        "recovery_avg_spread": round(rec_spread, 4),
        "spread_delta": round(spread_delta, 4),
        "baseline_avg_imbalance_spread": round(base_imbalance_spread, 4),
        "recovery_avg_imbalance_spread": round(rec_imbalance_spread, 4),
        "imbalance_spread_delta": round(imbalance_spread_delta, 4),
        "recovery_avg_share_delta_spread": round(rec_share_delta_spread, 4),
        "recovery_400g_actual_share_spread": round(rec_400g_spread, 4),
        "recovery_100g_actual_share_spread": round(rec_100g_spread, 4),
        "recovery_400g_ratio_spread": round(rec_400g_ratio_spread, 4),
        "recovery_100g_ratio_spread": round(rec_100g_ratio_spread, 4),
        "recovery_dominant_port_flips": rec_flips,
        "top_overloaded_ports": recovery_summary.get("top_overloaded_ports", []),
        "top_underloaded_ports": recovery_summary.get("top_underloaded_ports", []),
        "q8_taildrop_growth": q8_taildrop_growth,
    }


def build_ecmp_recovery_report(
    *,
    run_id: str,
    node: str,
    bounced_interface: str,
    ecmp_pre_sample_paths: List[str],
    ecmp_recovery_sample_paths: List[str],
    interfaces_of_interest: Optional[List[str]] = None,
    interface_speeds: Optional[Dict[str, str]] = None,
    q8_taildrop_growth: Optional[float] = None,
    default_interval_seconds: int = 10,
) -> Dict[str, Any]:
    baseline_window = build_rate_intervals(
        sample_paths=ecmp_pre_sample_paths,
        node=node,
        interfaces_of_interest=interfaces_of_interest,
        interface_speeds=interface_speeds,
        default_interval_seconds=default_interval_seconds,
    )

    recovery_window = build_rate_intervals(
        sample_paths=ecmp_recovery_sample_paths,
        node=node,
        interfaces_of_interest=interfaces_of_interest,
        interface_speeds=interface_speeds,
        default_interval_seconds=default_interval_seconds,
    )

    baseline_summary = summarize_window(baseline_window, interface_speeds=interface_speeds)
    recovery_summary = summarize_window(recovery_window, interface_speeds=interface_speeds)

    classification = classify_ecmp_behavior(
        baseline_summary=baseline_summary,
        recovery_summary=recovery_summary,
        q8_taildrop_growth=q8_taildrop_growth,
    )

    return {
        "run_id": run_id,
        "node": node,
        "bounced_interface": bounced_interface,
        "interfaces_of_interest": interfaces_of_interest or recovery_window.get("interfaces", []),
        "interface_speeds": interface_speeds or {},
        "baseline_window": baseline_window,
        "recovery_window": recovery_window,
        "baseline_summary": baseline_summary,
        "recovery_summary": recovery_summary,
        "analysis": classification,
    }


def write_ecmp_recovery_report(
    *,
    out_path: str,
    report: Dict[str, Any],
) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=False)
    return out_path
