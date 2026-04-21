import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple

from controller.cos_state_collector import collect_cos_state, write_outputs as write_cos_raw_outputs
from controller.cos_parsers import parse_all

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _metric_value(metrics: Dict[str, Any], *keys: str) -> float:
    if not isinstance(metrics, dict):
        return 0.0
    for key in keys:
        if key in metrics:
            return _safe_float(metrics.get(key))
    return 0.0


def _get_entity_evidence(ui_report: Dict[str, Any], entity_id: str) -> Dict[str, Any]:
    evidence_index = ui_report.get("evidence_index", {}) or {}
    if not entity_id:
        return {}
    return evidence_index.get(entity_id, {}) or {}


def _extract_delta_signal_bundle(
    *,
    ui_report: Dict[str, Any],
    entity_id: str,
) -> Dict[str, float]:
    evidence = _get_entity_evidence(ui_report, entity_id)
    delta_running = evidence.get("delta_running", {}) or {}
    running_metrics = evidence.get("running_metrics", {}) or {}
    delta_post = evidence.get("delta_post", {}) or {}

    # Prefer explicit running deltas, fallback to running metrics only if needed
    delta_tail = _metric_value(
        delta_running,
        "tail_drop_pkts",
        "tail_dropped_packets",
        "out_drop_pkts",
        "drop_pkts",
    )
    delta_ecn = _metric_value(
        delta_running,
        "ecn_marked_pkts",
        "out_ecn_ce_marked_pkts",
        "ecn_ce_packets",
    )
    delta_red = _metric_value(
        delta_running,
        "red_drop_pkts",
        "red_dropped_packets",
    )
    delta_resource = _metric_value(
        delta_running,
        "in_resource_drops",
        "resource_drops",
    )

    # fallback if delta_running is empty but running_metrics has the live values
    if delta_tail <= 0:
        delta_tail = _metric_value(
            running_metrics,
            "tail_drop_pkts",
            "tail_dropped_packets",
            "out_drop_pkts",
            "drop_pkts",
        )
    if delta_ecn <= 0:
        delta_ecn = _metric_value(
            running_metrics,
            "ecn_marked_pkts",
            "out_ecn_ce_marked_pkts",
            "ecn_ce_packets",
        )
    if delta_red <= 0:
        delta_red = _metric_value(
            running_metrics,
            "red_drop_pkts",
            "red_dropped_packets",
        )
    if delta_resource <= 0:
        delta_resource = _metric_value(
            running_metrics,
            "in_resource_drops",
            "resource_drops",
        )

    post_tail = _metric_value(
        delta_post,
        "tail_drop_pkts",
        "tail_dropped_packets",
        "out_drop_pkts",
        "drop_pkts",
    )
    post_ecn = _metric_value(
        delta_post,
        "ecn_marked_pkts",
        "out_ecn_ce_marked_pkts",
        "ecn_ce_packets",
    )

    return {
        # existing fields used by current scorer
        "delta_tail_drop_pkts": _safe_float(
            delta_running.get("tail-drop-pkts", evidence.get("delta_tail_dropped_packets", 0.0))
        ),
        "delta_ecn_marked_pkts": _safe_float(
            delta_running.get("ecn-marked-pkts", evidence.get("delta_ecn_ce_packets", 0.0))
        ),
        "delta_red_drop_pkts": _safe_float(
            delta_running.get("red-drop-pkts", evidence.get("delta_red_dropped_packets", 0.0))
        ),
        "delta_resource_drops": _safe_float(
            evidence.get("delta_resource_drops", 0.0)
        ),
        "post_tail_drop_pkts": _safe_float(
            delta_post.get("tail-drop-pkts", evidence.get("post_tail_dropped_packets", 0.0))
        ),
        "post_ecn_marked_pkts": _safe_float(
            delta_post.get("ecn-marked-pkts", evidence.get("post_ecn_ce_packets", 0.0))
        ),

        # existing raw/current metrics
        "running_tail_drop_pkts": _safe_float(
            running_metrics.get("tail-drop-pkts", evidence.get("tail_dropped_packets", 0.0))
        ),
        "running_ecn_marked_pkts": _safe_float(
            running_metrics.get("ecn-marked-pkts", evidence.get("ecn_ce_packets", 0.0))
        ),

        # new event-aware fields injected into rca_ui_report
        "rise_tail_dropped_packets": _safe_float(
            evidence.get("rise_tail_dropped_packets", evidence.get("delta_tail_dropped_packets", 0.0))
        ),
        "linger_tail_dropped_packets": _safe_float(
            evidence.get("linger_tail_dropped_packets", evidence.get("post_tail_dropped_packets", 0.0))
        ),
        "rise_ecn_ce_packets": _safe_float(
            evidence.get("rise_ecn_ce_packets", evidence.get("delta_ecn_ce_packets", 0.0))
        ),
        "linger_ecn_ce_packets": _safe_float(
            evidence.get("linger_ecn_ce_packets", evidence.get("post_ecn_ce_packets", 0.0))
        ),
        "rise_red_dropped_packets": _safe_float(
            evidence.get("rise_red_dropped_packets", evidence.get("delta_red_dropped_packets", 0.0))
        ),
        "linger_red_dropped_packets": _safe_float(
            evidence.get("linger_red_dropped_packets", evidence.get("post_red_dropped_packets", 0.0))
        ),
        "rise_resource_drops": _safe_float(
            evidence.get("rise_resource_drops", evidence.get("delta_resource_drops", 0.0))
        ),
        "linger_resource_drops": _safe_float(
            evidence.get("linger_resource_drops", evidence.get("post_resource_drops", 0.0))
        ),
        "recovery_ratio_tail": _safe_float(
            evidence.get("recovery_ratio_tail", 0.0)
        ),
        "recovery_ratio_ecn": _safe_float(
            evidence.get("recovery_ratio_ecn", 0.0)
        ),
        "recovery_ratio_red": _safe_float(
            evidence.get("recovery_ratio_red", 0.0)
        ),
        "recovery_ratio_resource": _safe_float(
            evidence.get("recovery_ratio_resource", 0.0)
        ),
        "event_delta_classification": evidence.get("event_delta_classification"),
        "tail_linger_trend": evidence.get("tail_linger_trend"),
        "ecn_linger_trend": evidence.get("ecn_linger_trend"),
    } 

def _build_bounced_interface_set(ui_report: Dict[str, Any]) -> set[tuple[str, str]]:
    bounced = set()

    for event in ui_report.get("events", []) or []:
        event_name = str(event.get("event_name", "") or "").strip().lower()
        event_type = str(event.get("event_type", "") or "").strip().lower()
        details = event.get("details", {}) or {}
        stress_mode = str(details.get("stress_mode", "") or "").strip().lower()

        node = event.get("target_node")
        interface = event.get("target_interface")

        if not node or not interface:
            continue

        if (
            event_name == "fabric_interface_bounce"
            or event_type == "fabric_link"
            or stress_mode == "interface_bounce"
        ):
            bounced.add((str(node), str(interface)))

    return bounced

def _build_link_peer_map(ui_report: Dict[str, Any]) -> Dict[tuple[str, str], tuple[str, str]]:
    peer_map: Dict[tuple[str, str], tuple[str, str]] = {}

    source_files = ui_report.get("source_files", {}) or {}
    topology_path = source_files.get("topology")

    if not topology_path:
        return peer_map

    try:
        topo = load_json(topology_path)
    except Exception:
        return peer_map

    links = topo.get("links") or topo.get("edges") or topo.get("connections") or []

    def _extract_link_endpoints(link: Dict[str, Any]):
        candidates = [
            ("node1", "interface1", "node2", "interface2"),
            ("node1", "intf1", "node2", "intf2"),
            ("a_node", "a_intf", "z_node", "z_intf"),
            ("src_node", "src_interface", "dst_node", "dst_interface"),
            ("local_node", "local_interface", "remote_node", "remote_interface"),
        ]
        for n1k, i1k, n2k, i2k in candidates:
            if all(k in link for k in (n1k, i1k, n2k, i2k)):
                return (
                    str(link[n1k]),
                    str(link[i1k]),
                    str(link[n2k]),
                    str(link[i2k]),
                )

        ep1 = link.get("endpoint1") or link.get("a") or link.get("src") or link.get("local")
        ep2 = link.get("endpoint2") or link.get("z") or link.get("dst") or link.get("remote")

        if isinstance(ep1, dict) and isinstance(ep2, dict):
            n1 = ep1.get("node") or ep1.get("device") or ep1.get("name") or ep1.get("hostname")
            i1 = ep1.get("interface") or ep1.get("port") or ep1.get("name")
            n2 = ep2.get("node") or ep2.get("device") or ep2.get("name") or ep2.get("hostname")
            i2 = ep2.get("interface") or ep2.get("port") or ep2.get("name")
            if n1 and i1 and n2 and i2:
                return str(n1), str(i1), str(n2), str(i2)

        return None

    for link in links:
        if not isinstance(link, dict):
            continue
        endpoints = _extract_link_endpoints(link)
        if not endpoints:
            continue
        node1, intf1, node2, intf2 = endpoints
        peer_map[(node1, intf1)] = (node2, intf2)
        peer_map[(node2, intf2)] = (node1, intf1)

    return peer_map

def _is_control_queue(enriched: Dict[str, Any]) -> bool:
    fc = str(enriched.get("forwarding_class", "") or "").strip().lower()
    queue = enriched.get("queue")

    return fc in {"network_control", "nc", "control"} or queue in {7}


def _get_drop_value_from_metrics(metrics: Dict[str, Any]) -> float:
    if not isinstance(metrics, dict):
        return 0.0

    candidate_keys = (
        "tail_drop_pkts",
        "red_drop_pkts",
        "in_resource_drops",
        "out_ecn_ce_marked_pkts",
        "ecn_marked_pkts",
    )
    return sum(_safe_float(metrics.get(k, 0.0)) for k in candidate_keys)


def _is_short_lived_and_recovered(ui_report: Dict[str, Any], hotspot: Dict[str, Any]) -> bool:
    evidence_index = ui_report.get("evidence_index", {}) or {}
    entity_id = hotspot.get("entity_id")

    evidence = {}
    if entity_id and entity_id in evidence_index:
        evidence = evidence_index.get(entity_id, {}) or {}

    delta_running = evidence.get("delta_running", {}) or {}
    delta_post = evidence.get("delta_post", {}) or {}
    running_metrics = evidence.get("running_metrics", {}) or {}

    running_delta_val = _get_drop_value_from_metrics(delta_running)
    post_delta_val = _get_drop_value_from_metrics(delta_post)
    running_metric_val = _get_drop_value_from_metrics(running_metrics)

    # Preferred path: explicit queue-level evidence exists
    if delta_running or delta_post or running_metrics:
        running_seen = max(running_delta_val, running_metric_val) > 0
        recovered = (
            post_delta_val <= 0
            or post_delta_val <= max(5.0, running_delta_val * 0.30)
        )
        return running_seen and recovered

    # Fallback path:
    # If queue-level evidence is missing, allow event-aware transient classification
    # only for directly bounced control queues with bounded/manual-review style impact.
    classification = str(hotspot.get("classification", "") or "")
    fc = str(hotspot.get("forwarding_class", "") or "").strip().lower()
    queue = hotspot.get("queue")
    probable_cause = str(hotspot.get("probable_cause", "") or "").strip().lower()

    is_control = fc in {"network_control", "nc", "control"} or queue in {7}
    bounded_taildrop_case = probable_cause in {
        "queue-pressure-with-taildrop",
        "queue-pressure-with-ecn",
        "unknown",
        "",
    }

    if is_control and classification in {
        "needs-manual-review",
        "unexpected-taildrop-on-lossless",
    } and bounded_taildrop_case:
        return True

    return False


def apply_event_aware_classification(
    *,
    enriched: Dict[str, Any],
    ui_report: Dict[str, Any],
) -> Dict[str, Any]:

    bounced_ifaces = _build_bounced_interface_set(ui_report)
    peer_map = _build_link_peer_map(ui_report)

    eligible_ifaces = set(bounced_ifaces)
    for item in list(bounced_ifaces):
        peer = peer_map.get(item)
        if peer:
            eligible_ifaces.add(peer)

    node = str(enriched.get("node", "") or "")
    interface = str(enriched.get("interface", "") or "")
    classification = str(enriched.get("classification", "") or "")

    if (node, interface) not in eligible_ifaces:
        return enriched

    if not _is_control_queue(enriched):
        return enriched

    if not _is_short_lived_and_recovered(ui_report, enriched):
        return enriched

    if classification in {
        "needs-manual-review",
        "unexpected-taildrop-on-lossless",
    } and str(enriched.get("probable_cause", "") or "").strip().lower() == "queue-pressure-with-taildrop":
        enriched["classification"] = "expected-transient-control-impact"
        enriched["classification_confidence"] = max(
            _safe_float(enriched.get("classification_confidence", 0.0)),
            0.92,
        )
        
        flags = enriched.get("classification_flags", []) or []
        if "interface-bounce-transient" not in flags:
            flags.append("interface-bounce-transient")
        if "post-recovery-observed" not in flags:
            flags.append("post-recovery-observed")
        enriched["classification_flags"] = flags

        existing_cause = str(enriched.get("probable_cause", "") or "").strip()
        enriched["probable_cause"] = (
            "Expected transient control-plane queue impact during interface bounce; "
            "drops observed during trigger window and recovered in post state."
        )
        if existing_cause and existing_cause.lower() != "unknown":
            enriched["base_probable_cause"] = existing_cause

    return enriched

def refine_lossy_mcast_classification(
    *,
    enriched: Dict[str, Any],
    ui_report: Dict[str, Any],
) -> Dict[str, Any]:
    classification = str(enriched.get("classification", "") or "")
    fc = str(enriched.get("forwarding_class", "") or "").strip().lower()
    no_loss = bool(enriched.get("no_loss", False))

    if classification != "expected-lossy-mcast-pressure":
        return enriched

    if fc != "mcast":
        return enriched

    if no_loss:
        return enriched

    tail_drop = _safe_float(enriched.get("tail_dropped_packets", 0.0))
    score = _safe_float(enriched.get("correlation_score", enriched.get("score", 0.0)))

    traffic_health = ui_report.get("traffic_health", {}) or {}
    live = traffic_health.get("live_alert_summary", {}) or {}
    traffic_verdict = str(traffic_health.get("traffic_verdict") or "").strip().lower()
    rocev2_verdict = str(traffic_health.get("rocev2_verdict") or "").strip().lower()

    strong_service_impact = (
        traffic_verdict == "fail"
        or rocev2_verdict == "fail"
        or _safe_float(live.get("critical_alerts", 0)) > 0
    )

    excessive_drop = tail_drop >= 1000000
    strong_outlier = score >= 1000

    if strong_service_impact or excessive_drop or strong_outlier:
        enriched["classification"] = "localized-lossy-mcast-pressure"
        enriched["classification_confidence"] = max(
            _safe_float(enriched.get("classification_confidence", 0.0)),
            0.95,
        )

        flags = enriched.get("classification_flags", []) or []
        if "localized_excessive_mcast_pressure" not in flags:
            flags.append("localized_excessive_mcast_pressure")
        enriched["classification_flags"] = flags

    return enriched

def apply_delta_aware_hotspot_scoring(
    *,
    enriched: Dict[str, Any],
    ui_report: Dict[str, Any],
    telemetry_reference: str | None = None,
    baseline_reference: str | None = None,
    running_reference: str | None = None,
    post_reference: str | None = None,
    telemetry_mode: str = "legacy_single_reference",
) -> Dict[str, Any]:
    entity_id = str(enriched.get("entity_id") or "")
    if not entity_id:
        return enriched

    delta = _extract_delta_signal_bundle(ui_report=ui_report, entity_id=entity_id)

    delta_tail = _safe_float(delta.get("delta_tail_drop_pkts", 0.0))
    delta_ecn = _safe_float(delta.get("delta_ecn_marked_pkts", 0.0))
    delta_red = _safe_float(delta.get("delta_red_drop_pkts", 0.0))
    delta_resource = _safe_float(delta.get("delta_resource_drops", 0.0))

    post_tail = _safe_float(delta.get("post_tail_drop_pkts", 0.0))
    post_ecn = _safe_float(delta.get("post_ecn_marked_pkts", 0.0))

    rise_tail = _safe_float(delta.get("rise_tail_dropped_packets", 0.0))
    linger_tail = _safe_float(delta.get("linger_tail_dropped_packets", 0.0))
    rise_ecn = _safe_float(delta.get("rise_ecn_ce_packets", 0.0))
    linger_ecn = _safe_float(delta.get("linger_ecn_ce_packets", 0.0))

    rise_red = _safe_float(delta.get("rise_red_dropped_packets", 0.0))
    linger_red = _safe_float(delta.get("linger_red_dropped_packets", 0.0))
    rise_resource = _safe_float(delta.get("rise_resource_drops", 0.0))
    linger_resource = _safe_float(delta.get("linger_resource_drops", 0.0))

    # Defensive fallback:
    # if injected rise/linger fields are missing or zero, fall back to the
    # already-available delta/post fields so classification still works.
    if rise_tail <= 0 and delta_tail > 0:
        rise_tail = delta_tail
    if linger_tail <= 0 and post_tail > 0:
        linger_tail = post_tail

    if rise_ecn <= 0 and delta_ecn > 0:
        rise_ecn = delta_ecn
    if linger_ecn <= 0 and post_ecn > 0:
        linger_ecn = post_ecn

    if rise_red <= 0 and delta_red > 0:
        rise_red = delta_red
    if rise_resource <= 0 and delta_resource > 0:
        rise_resource = delta_resource

    tail_linger_trend = delta.get("tail_linger_trend")
    ecn_linger_trend = delta.get("ecn_linger_trend")

    if (tail_linger_trend in (None, "cleared")) and post_tail > 0:
        if post_tail > delta_tail > 0:
            tail_linger_trend = "increasing"
        elif 0 < post_tail < delta_tail:
            tail_linger_trend = "decreasing"
        elif post_tail == delta_tail and post_tail > 0:
            tail_linger_trend = "flat"

    if (ecn_linger_trend in (None, "cleared")) and post_ecn > 0:
        if post_ecn > delta_ecn > 0:
            ecn_linger_trend = "increasing"
        elif 0 < post_ecn < delta_ecn:
            ecn_linger_trend = "decreasing"
        elif post_ecn == delta_ecn and post_ecn > 0:
            ecn_linger_trend = "flat"

    absolute_tail = _safe_float(enriched.get("tail_dropped_packets", 0.0))
    absolute_ecn = _safe_float(enriched.get("ecn_ce_packets", 0.0))

    # --------------------------------------------------------------
    # Recompute recovery ratios locally from actual values
    # --------------------------------------------------------------
    recovery_ratio_tail = (linger_tail / rise_tail) if rise_tail > 0 else 0.0
    recovery_ratio_ecn = (linger_ecn / rise_ecn) if rise_ecn > 0 else 0.0
    recovery_ratio_red = (linger_red / rise_red) if rise_red > 0 else 0.0
    recovery_ratio_resource = (linger_resource / rise_resource) if rise_resource > 0 else 0.0

    # --------------------------------------------------------------
    # Derive event classification from actual behavior
    # --------------------------------------------------------------
    if rise_tail <= 0 and rise_ecn <= 0 and rise_red <= 0 and rise_resource <= 0:
        event_delta_classification = "no_event_delta"
    elif rise_tail > 0:
        if linger_tail > rise_tail or recovery_ratio_tail > 0.8:
            event_delta_classification = "persistent_taildrop"
        elif recovery_ratio_tail > 0.2:
            event_delta_classification = "lingering_taildrop"
        else:
            event_delta_classification = "expected_transient_taildrop"
    elif rise_red > 0 or rise_resource > 0:
        if recovery_ratio_red > 0.8 or recovery_ratio_resource > 0.8:
            event_delta_classification = "persistent_resource_pressure"
        else:
            event_delta_classification = "transient_non_tail_pressure"
    elif rise_ecn > 0:
        if recovery_ratio_ecn > 0.2:
            event_delta_classification = "lingering_ecn_pressure"
        else:
            event_delta_classification = "expected_ecn_transient"
    else:
        event_delta_classification = "unknown"

    # --------------------------------------------------------------
    # Persist derived fields
    # --------------------------------------------------------------
    enriched["delta_tail_dropped_packets"] = delta_tail
    enriched["delta_ecn_ce_packets"] = delta_ecn
    enriched["delta_red_dropped_packets"] = delta_red
    enriched["delta_resource_drops"] = delta_resource

    enriched["post_tail_dropped_packets"] = post_tail
    enriched["post_ecn_ce_packets"] = post_ecn

    enriched["rise_tail_dropped_packets"] = rise_tail
    enriched["linger_tail_dropped_packets"] = linger_tail
    enriched["rise_ecn_ce_packets"] = rise_ecn
    enriched["linger_ecn_ce_packets"] = linger_ecn
    enriched["rise_red_dropped_packets"] = rise_red
    enriched["linger_red_dropped_packets"] = linger_red
    enriched["rise_resource_drops"] = rise_resource
    enriched["linger_resource_drops"] = linger_resource

    enriched["recovery_ratio_tail"] = recovery_ratio_tail
    enriched["recovery_ratio_ecn"] = recovery_ratio_ecn
    enriched["recovery_ratio_red"] = recovery_ratio_red
    enriched["recovery_ratio_resource"] = recovery_ratio_resource

    enriched["event_delta_classification"] = event_delta_classification
    enriched["tail_linger_trend"] = tail_linger_trend
    enriched["ecn_linger_trend"] = ecn_linger_trend

    enriched["telemetry_mode"] = telemetry_mode
    enriched["telemetry_references"] = {
        "telemetry_reference": telemetry_reference,
        "baseline_reference": baseline_reference,
        "running_reference": running_reference,
        "post_reference": post_reference,
    }

    meaningful_delta = (delta_tail + delta_ecn + delta_red + delta_resource) > 0

    # --------------------------------------------------------------
    # Temporal interpretation
    # --------------------------------------------------------------
    if telemetry_mode == "phase_aware":
        if rise_tail > 0:
            if tail_linger_trend == "increasing":
                enriched["temporal_pattern"] = "persistent_worsening"
            elif tail_linger_trend == "flat":
                enriched["temporal_pattern"] = "persistent_flat"
            elif tail_linger_trend == "decreasing":
                enriched["temporal_pattern"] = "recovering"
            elif recovery_ratio_tail <= 0.2:
                enriched["temporal_pattern"] = "expected_transient"
            elif recovery_ratio_tail <= 0.8:
                enriched["temporal_pattern"] = "lingering"
            else:
                enriched["temporal_pattern"] = "persistent"
        elif rise_ecn > 0:
            if ecn_linger_trend == "increasing":
                enriched["temporal_pattern"] = "ecn_worsening"
            elif ecn_linger_trend == "decreasing":
                enriched["temporal_pattern"] = "ecn_recovering"
            elif recovery_ratio_ecn <= 0.2:
                enriched["temporal_pattern"] = "ecn_transient"
            else:
                enriched["temporal_pattern"] = "ecn_lingering"
        else:
            enriched["temporal_pattern"] = "baseline_or_historical_only"
    else:
        enriched["temporal_pattern"] = enriched.get("temporal_pattern", "legacy_single_reference")

    # --------------------------------------------------------------
    # Score = class rank + actual measured magnitude
    # Use class mainly for ordering across categories, not as magic truth.
    # --------------------------------------------------------------
    if meaningful_delta:
        enriched["drop_rate"] = delta_tail + delta_red + delta_resource
        enriched["ecn_mark_rate"] = delta_ecn

        occupancy = _safe_float((enriched.get("signals", {}) or {}).get("peak_buffer_occupancy_percent", 0.0))

        classification_rank_map = {
            "no_event_delta": 0,
            "expected_ecn_transient": 1,
            "expected_transient_taildrop": 2,
            "transient_non_tail_pressure": 3,
            "lingering_ecn_pressure": 4,
            "lingering_taildrop": 6,
            "persistent_taildrop": 8,
            "persistent_resource_pressure": 9,
            "unknown": 3,
        }
        class_rank = classification_rank_map.get(event_delta_classification, 3)

        # Main score components:
        # - class_rank decides coarse severity bucket
        # - rise/linger/occupancy decide fine-grained ranking within bucket
        delta_score = (
            (class_rank * 100.0)
            + rise_tail
            + min(linger_tail, 1000000.0)
            + delta_red
            + delta_resource
            + occupancy
            + (rise_ecn * 0.01)
        )

        # Mild trend adjustments
        if tail_linger_trend == "increasing":
            delta_score *= 1.25
        elif tail_linger_trend == "decreasing":
            delta_score *= 0.85
        elif tail_linger_trend == "flat":
            delta_score *= 1.05

        # ECN-only cases should rank lower than real drop persistence
        if rise_tail <= 0 and rise_ecn > 0 and delta_red <= 0 and delta_resource <= 0:
            delta_score *= 0.75

        enriched["correlation_score"] = delta_score
        enriched["score"] = delta_score
        enriched["classification_rank"] = class_rank
        enriched["uses_delta_scoring"] = True
        return enriched

    # --------------------------------------------------------------
    # No meaningful delta -> likely historical/stale counter only
    # --------------------------------------------------------------
    if (absolute_tail + absolute_ecn) > 0:
        enriched["drop_rate"] = 0.0
        enriched["ecn_mark_rate"] = 0.0
        enriched["correlation_score"] = 1.0
        enriched["score"] = 1.0
        enriched["classification_rank"] = 0
        enriched["uses_delta_scoring"] = False

        flags = enriched.get("classification_flags", []) or []
        if "historical_counter_only" not in flags:
            flags.append("historical_counter_only")
        enriched["classification_flags"] = flags

        if telemetry_mode == "phase_aware":
            enriched["temporal_pattern"] = "baseline_or_historical_only"

    return enriched


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def build_output_paths(run_id: str) -> Dict[str, str]:
    base = Path("artifacts") / "campaigns" / run_id
    return {
        "json": str(base / "cos_hotspot_correlation.json"),
        "txt": str(base / "cos_hotspot_correlation.txt"),
    }


def build_node_host_map_from_telemetry(telemetry_json_path: str) -> Dict[str, Dict[str, Any]]:
    report = load_json(telemetry_json_path)
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in report.get("nodes", []) or []:
        node = item.get("node")
        if not node:
            continue
        mapping[node] = {
            "host": item.get("resolved_mgt_ip") or item.get("resolved_device") or node,
            "resolved_device": item.get("resolved_device"),
            "resolved_mgt_ip": item.get("resolved_mgt_ip"),
        }
    return mapping


def take_top_hotspots(ui_report: Dict[str, Any], top_n: int) -> List[Dict[str, Any]]:
    hotspots = ui_report.get("all_hotspots") or ui_report.get("hotspots") or []
    ranked = sorted(hotspots, key=lambda x: x.get("score", 0), reverse=True)
    return ranked[:top_n]


def classify_hotspot(enriched: Dict[str, Any]) -> Tuple[str, List[str], float]:
    flags: List[str] = []

    queue = enriched.get("queue")
    fc = enriched.get("forwarding_class")
    no_loss = enriched.get("no_loss", False)
    ecn_enabled = enriched.get("ecn_enabled", False)
    explicit_scheduler_present = enriched.get("explicit_scheduler_present", False)
    tail_drop_pkts = enriched.get("tail_dropped_packets", 0) or 0
    ecn_ce_pkts = enriched.get("ecn_ce_packets", 0) or 0
    probable_cause = enriched.get("probable_cause")

    if no_loss and tail_drop_pkts > 0:
        flags.append("unexpected_taildrop_on_lossless")
        return "unexpected-taildrop-on-lossless", flags, 0.99

    if fc == "rdma_storage" and ecn_enabled and ecn_ce_pkts > 0 and tail_drop_pkts == 0:
        flags.append("expected_ecn_pressure")
        return "expected-ecn-pressure", flags, 0.90

    if fc == "mcast" and not no_loss and tail_drop_pkts > 0:
        flags.append("lossy_mcast_pressure")
        if not explicit_scheduler_present:
            flags.append("missing_explicit_scheduler")
        return "expected-lossy-mcast-pressure", flags, 0.75

    if tail_drop_pkts > 0 and not explicit_scheduler_present:
        flags.append("taildrop_without_explicit_scheduler")
        return "queue-without-explicit-scheduler", flags, 0.80

    if probable_cause == "queue-pressure-with-ecn" and ecn_enabled:
        flags.append("ecn_correlated")
        return "ecn-correlated-hotspot", flags, 0.85

    return "needs-manual-review", flags, 0.60


def enrich_hotspot(
    hotspot: Dict[str, Any],
    parsed_cos: Dict[str, Any],
) -> Dict[str, Any]:
    queue = str(hotspot.get("queue"))
    fc_by_queue = parsed_cos.get("forwarding_class", {}).get("by_queue", {})
    qstats_by_queue = parsed_cos.get("interface_queue", {}).get("by_queue", {})
    sched_by_fc = parsed_cos.get("scheduler_map", {}).get("by_forwarding_class", {})
    cos_ifd = parsed_cos.get("cos_interface", {})

    fc_entry = fc_by_queue.get(queue, {})
    qstats = qstats_by_queue.get(queue, {})
    fc_name = fc_entry.get("forwarding_class") or qstats.get("forwarding_class")
    sched_entry = sched_by_fc.get(fc_name, {}) if fc_name else {}

    enriched = {
        "entity_id": hotspot.get("entity_id"),
        "node": hotspot.get("node"),
        "interface": hotspot.get("interface"),
        "queue": hotspot.get("queue"),
        "severity": hotspot.get("severity"),
        "score": hotspot.get("score"),
        "probable_cause": hotspot.get("probable_cause"),
        "signals": hotspot.get("signals", {}),
        "forwarding_class": fc_name,
        "no_loss": fc_entry.get("no_loss", False),
        "pfc_priority": fc_entry.get("pfc_priority"),
        "explicit_scheduler_present": bool(sched_entry),
        "scheduler": sched_entry.get("scheduler"),
        "transmit_rate_percent": sched_entry.get("transmit_rate_percent"),
        "buffer_size_percent": sched_entry.get("buffer_size_percent"),
        "priority": sched_entry.get("priority"),
        "ecn_enabled": sched_entry.get("ecn_enabled", False),
        "drop_profiles": sched_entry.get("drop_profiles", []),
        "tail_dropped_packets": qstats.get("tail_dropped_packets", 0),
        "tail_dropped_bytes": qstats.get("tail_dropped_bytes", 0),
        "red_dropped_packets": qstats.get("red_dropped_packets", 0),
        "ecn_ce_packets": qstats.get("ecn_ce_packets", 0),
        "queued_packets": qstats.get("queued_packets", 0),
        "transmitted_packets": qstats.get("transmitted_packets", 0),
        "classifier": cos_ifd.get("classifier"),
        "scheduler_map_name": cos_ifd.get("scheduler_map"),
        "congestion_notification": cos_ifd.get("congestion_notification"),
        "dynamic_threshold_profile": cos_ifd.get("dynamic_threshold_profile"),
        "drop_congestion_notification": cos_ifd.get("drop_congestion_notification"),
    }

    classification, flags, confidence = classify_hotspot(enriched)
    enriched["classification"] = classification
    enriched["classification_flags"] = flags
    enriched["classification_confidence"] = confidence
    return enriched


def render_text(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("COS HOTSPOT CORRELATION")
    lines.append("=" * 88)
    lines.append(f"Generated At : {report.get('generated_at')}")
    lines.append(f"Run ID       : {report.get('run_id')}")
    lines.append(f"Top N        : {report.get('top_n')}")
    lines.append("")

    summary = report.get("summary", {})
    lines.append("SUMMARY")
    lines.append("-" * 88)
    lines.append(f"Collected interfaces   : {summary.get('collected_interfaces', 0)}")
    lines.append(f"Failed interfaces      : {summary.get('failed_interfaces', 0)}")
    lines.append(f"Localized mcast        : {summary.get('localized_lossy_mcast_pressure', 0)}")
    lines.append(f"Expected ECN pressure  : {summary.get('expected_ecn_pressure', 0)}")
    lines.append(f"Needs manual review    : {summary.get('needs_manual_review', 0)}")
    lines.append("")

    lines.append("ENRICHED HOTSPOTS")
    lines.append("-" * 88)
    for idx, item in enumerate(report.get("hotspots", []), start=1):
        lines.append(
            f"{idx}. {item.get('node')} {item.get('interface')} q{item.get('queue')} "
            f"sev={item.get('severity')} score={item.get('score')} "
            f"fc={item.get('forwarding_class')} class={item.get('classification')} "
            f"conf={item.get('classification_confidence')}"
        )
        lines.append(
            f"   cause={item.get('probable_cause')} "
            f"tail_drop={item.get('tail_dropped_packets')} "
            f"ecn_ce={item.get('ecn_ce_packets')} "
            f"no_loss={item.get('no_loss')} ecn_enabled={item.get('ecn_enabled')} "
            f"explicit_scheduler={item.get('explicit_scheduler_present')}"
        )
    lines.append("")
    return "\n".join(lines)


def run_correlation(
    *,
    run_id: str,
    rca_ui_report: str,
    telemetry_reference: str | None = None,
    baseline_reference: str | None = None,
    running_reference: str | None = None,
    post_reference: str | None = None,
    top_n: int,
    scheduler_map: str,
    ssh_user: str,
) -> str:




    have_phase_refs = bool(baseline_reference and running_reference and post_reference)

    if have_phase_refs:
        telemetry_mode = "phase_aware"
        telemetry_reference_to_use = running_reference
    else:
        telemetry_mode = "legacy_single_reference"
        telemetry_reference_to_use = telemetry_reference

    if not telemetry_reference_to_use:
        raise ValueError(
            "run_correlation requires either telemetry_reference "
            "or phase-aware inputs (baseline_reference, running_reference, post_reference)"
        )

    ui_report = load_json(rca_ui_report)
    node_host_map = build_node_host_map_from_telemetry(telemetry_reference_to_use)
    hotspots = take_top_hotspots(ui_report, top_n=top_n)

    enriched_hotspots = []
    failures = []

    for hotspot in hotspots:
        node = hotspot.get("node")
        interface_name = hotspot.get("interface")
        node_ctx = node_host_map.get(node, {})
        host = node_ctx.get("resolved_mgt_ip") or node_ctx.get("host")

        if not host:
            failures.append(
                {"node": node, "interface": interface_name, "error": "failed to resolve management host"}
            )
            continue

        try:
            raw_report = collect_cos_state(
                host=host,
                node=node,
                interface_name=interface_name,
                scheduler_map=scheduler_map,
                ssh_user=ssh_user,
            )
            raw_path = write_cos_raw_outputs(run_id=run_id, report=raw_report)

            parsed = parse_all(raw_report.get("raw", {}))
            enriched = enrich_hotspot(hotspot=hotspot, parsed_cos=parsed)
            enriched = apply_event_aware_classification(
                enriched=enriched,
                ui_report=ui_report,
            )
            enriched = refine_lossy_mcast_classification(
                enriched=enriched,
                ui_report=ui_report,
            )

            # NEW: pass phase refs when available, otherwise fall back to legacy single reference
            enriched = apply_delta_aware_hotspot_scoring(
                enriched=enriched,
                ui_report=ui_report,
                telemetry_reference=telemetry_reference_to_use,
                baseline_reference=baseline_reference,
                running_reference=running_reference,
                post_reference=post_reference,
                telemetry_mode=telemetry_mode,
            )

            enriched["raw_cos_path"] = raw_path
            enriched["telemetry_mode"] = telemetry_mode

            if have_phase_refs:
                enriched["phase_references"] = {
                    "baseline_reference": baseline_reference,
                    "running_reference": running_reference,
                    "post_reference": post_reference,
                }
            else:
                enriched["phase_references"] = {
                    "telemetry_reference": telemetry_reference_to_use,
                }

            enriched_hotspots.append(enriched)

        except Exception as exc:
            failures.append({"node": node, "interface": interface_name, "error": str(exc)})

    summary = {
        "collected_interfaces": len(enriched_hotspots),
        "failed_interfaces": len(failures),
        "telemetry_mode": telemetry_mode,
        "localized_lossy_mcast_pressure": sum(
            1 for x in enriched_hotspots if x.get("classification") == "localized-lossy-mcast-pressure"
        ),
        "expected_ecn_pressure": sum(
            1 for x in enriched_hotspots if x.get("classification") == "expected-ecn-pressure"
        ),
        "needs_manual_review": sum(
            1 for x in enriched_hotspots if x.get("classification") == "needs-manual-review"
        ),
        "expected_transient_control_impact": sum(
            1 for x in enriched_hotspots if x.get("classification") == "expected-transient-control-impact"
        ),
        "expected_lossy_mcast_pressure": sum(
            1 for x in enriched_hotspots if x.get("classification") == "expected-lossy-mcast-pressure"
        ),
    }

    report = {
        "generated_at": utc_now_iso(),
        "run_id": run_id,
        "rca_ui_report": rca_ui_report,
        "telemetry_mode": telemetry_mode,
        "telemetry_reference": telemetry_reference_to_use,
        "baseline_reference": baseline_reference,
        "running_reference": running_reference,
        "post_reference": post_reference,
        "top_n": top_n,
        "summary": summary,
        "hotspots": enriched_hotspots,
        "failures": failures,
    }

    outputs = build_output_paths(run_id)
    write_json(outputs["json"], report)
    write_text(outputs["txt"], render_text(report))
    return outputs["json"]

def main() -> int:
    parser = argparse.ArgumentParser(description="Correlate RCA hotspots with CoS state.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--rca-ui-report", required=True)

    # LEGACY single-reference mode
    parser.add_argument("--telemetry-reference", default=None)

    # NEW phase-aware mode
    parser.add_argument("--baseline-reference", default=None)
    parser.add_argument("--running-reference", default=None)
    parser.add_argument("--post-reference", default=None)

    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--scheduler-map", default="sm1")
    parser.add_argument("--ssh-user", default="root")
    args = parser.parse_args()

    have_phase_refs = bool(
        args.baseline_reference and args.running_reference and args.post_reference
    )

    if not have_phase_refs and not args.telemetry_reference:
        raise ValueError(
            "Provide either --telemetry-reference "
            "or all of --baseline-reference, --running-reference, --post-reference"
        )

    out = run_correlation(
        run_id=args.run_id,
        rca_ui_report=args.rca_ui_report,
        telemetry_reference=args.telemetry_reference,
        baseline_reference=args.baseline_reference,
        running_reference=args.running_reference,
        post_reference=args.post_reference,
        top_n=args.top_n,
        scheduler_map=args.scheduler_map,
        ssh_user=args.ssh_user,
    )
    print(out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
