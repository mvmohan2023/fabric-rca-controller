import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from controller.ecmp_recovery_view import (
    build_ecmp_recovery_input_from_existing_artifacts,
    build_ecmp_recovery_view,
)

def _normalize_mixed_speed_spec_validation(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw = raw or {}
    group_validation = raw.get("group_validation", {}) or {}

    tolerance_pct = _to_float(raw.get("tolerance_pct", 0.0), 0.0)
    tolerance_fraction = tolerance_pct / 100.0

    def _row(speed_group: str) -> Dict[str, Any]:
        g = group_validation.get(speed_group, {}) or {}
        expected = _to_float(g.get("expected_share", 0.0), 0.0)
        actual = _to_float(g.get("actual_share", 0.0), 0.0)

        min_allowed = max(0.0, expected - tolerance_fraction)
        max_allowed = min(1.0, expected + tolerance_fraction)
        deviation_pct_points = (actual - expected) * 100.0

        return {
            "speed_group": speed_group,
            "expected_pct": round(expected * 100.0, 1),
            "actual_pct": round(actual * 100.0, 1),
            "allowed_min_pct": round(min_allowed * 100.0, 1),
            "allowed_max_pct": round(max_allowed * 100.0, 1),
            "allowed_range_text": f"{round(min_allowed * 100.0, 1)}–{round(max_allowed * 100.0, 1)}%",
            "deviation_pct": round(deviation_pct_points, 1),
            "in_spec": bool(g.get("in_spec", False)),
        }

    rows: List[Dict[str, Any]] = []
    for speed_group in ("400G", "100G"):
        if speed_group in group_validation:
            rows.append(_row(speed_group))

    return {
        "overall_status": raw.get("overall_status"),
        "tolerance_pct": round(tolerance_pct, 1),
        "traffic_start_mode": raw.get("traffic_start_mode", "all_at_once"),
        "rows": rows,
    }

def build_ixia_port_map(case_summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    files = safe_get(case_summary, "files", {}) or {}

    candidate_paths = []
    ixia_inventory = files.get("ixia_inventory")
    if ixia_inventory:
        candidate_paths.append(ixia_inventory)

    candidate_paths.append(str(Path.cwd() / "controller" / "ixia_inventory.json"))

    for path in candidate_paths:
        p = resolve_artifact(path)
        if not p or not p.exists():
            continue
        try:
            data = load_json(p)
            ports = data.get("ports", []) or []
            result: Dict[str, Dict[str, Any]] = {}
            for item in ports:
                ixia_port = str(item.get("ixia_port") or "").strip()
                port_name = str(item.get("port_name") or "").strip()
                payload = {
                    "switch": item.get("switch"),
                    "switch_interface": item.get("switch_interface"),
                    "port_name": item.get("port_name"),
                    "line_speed": item.get("line_speed"),
                    "expected_link_state": item.get("expected_link_state"),
                    "ixia_port": item.get("ixia_port"),
                }
                if ixia_port:
                    result[ixia_port] = payload
                if port_name:
                    result[port_name] = payload
            return result
        except Exception:
            continue

    return {}
def enrich_rx_port_rows(rows: List[Dict[str, Any]], ixia_port_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []

    for row in rows or []:
        item = dict(row)
        rx_port = str(
            item.get("rx_port")
            or item.get("port")
            or item.get("name")
            or ""
        ).strip()

        port_ctx = ixia_port_map.get(rx_port, {}) if rx_port else {}

        item["rx_port"] = rx_port or item.get("rx_port") or item.get("port") or item.get("name")
        item["switch"] = port_ctx.get("switch")
        item["switch_interface"] = port_ctx.get("switch_interface")
        item["port_name"] = port_ctx.get("port_name")
        item["line_speed"] = port_ctx.get("line_speed")
        item["expected_link_state"] = port_ctx.get("expected_link_state")

        enriched.append(item)

    return enriched

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default) if isinstance(d, dict) else default


def to_entity_id(node: str, interface: str, queue: int | None = None) -> str:
    if queue is None:
        return f"{node}|{interface}"
    return f"{node}|{interface}|q{queue}"


def normalize_hotspot_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    node = safe_get(item, "node", "unknown")
    interface = safe_get(item, "interface", "unknown")
    queue = safe_get(item, "queue")
    severity = safe_get(item, "severity", "none")
    score = safe_get(item, "score", 0.0)
    probable_cause = safe_get(item, "probable_cause", "unknown")
    signals = safe_get(item, "signals", {}) or {}

    return {
        "entity_id": to_entity_id(node, interface, queue),
        "node": node,
        "interface": interface,
        "queue": queue,
        "severity": severity,
        "score": score,
        "probable_cause": probable_cause,
        "signals": {
            "peak_buffer_occupancy_percent": signals.get("peak_buffer_occupancy_percent", 0.0),
            "tail_drop_pkts": signals.get("tail_drop_pkts", 0.0),
            "red_drop_pkts": signals.get("red_drop_pkts", 0.0),
            "ecn_marked_pkts": signals.get("ecn_marked_pkts", 0.0),
            "in_resource_drops": signals.get("in_resource_drops", 0.0),
            "out_ecn_ce_marked_pkts": signals.get("out_ecn_ce_marked_pkts", 0.0),
            "fec_corrected_words": signals.get("fec_corrected_words", 0.0),
            "fec_uncorrectable_words": signals.get("fec_uncorrectable_words", 0.0),
            "pfc_activity": signals.get("pfc_activity", 0.0),
        },
    }


def normalize_delta_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    node = safe_get(item, "node", "unknown")
    interface = safe_get(item, "interface", "unknown")
    queue = safe_get(item, "queue")

    return {
        "entity_id": to_entity_id(node, interface, queue),
        "node": node,
        "interface": interface,
        "queue": queue,
        "delta_running": safe_get(item, "delta_running", {}) or {},
        "delta_post": safe_get(item, "delta_post", {}) or {},
        "running_metrics": safe_get(item, "running_metrics", {}) or {},
    }


def infer_primary_cause(top_hotspots: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    if not top_hotspots:
        return "unknown", []

    causes = [h.get("probable_cause", "unknown") for h in top_hotspots]
    top_cause = causes[0]

    contributing = []
    for hotspot in top_hotspots[:5]:
        cause = hotspot.get("probable_cause", "unknown")
        node = hotspot.get("node", "unknown")
        interface = hotspot.get("interface", "unknown")
        queue = hotspot.get("queue", "unknown")
        contributing.append(f"{cause} on {node} {interface} queue {queue}")

    return top_cause, contributing


def build_summary(
    case_summary: Dict[str, Any],
    hotspots_summary: Dict[str, Any],
    hotspots_detail: Dict[str, Any],
) -> Dict[str, Any]:
    top_queues = safe_get(hotspots_summary, "top_queues", []) or []
    severity_counts = safe_get(hotspots_summary, "severity_counts", {}) or {}

    top_hotspot = top_queues[0] if top_queues else {}
    top_score = top_hotspot.get("score", 0.0)
    primary_cause, contributing = infer_primary_cause(top_queues)

    confidence = min(0.99, round(0.50 + min(top_score, 500.0) / 1000.0, 2)) if top_score else 0.50

    return {
        "primary_cause": primary_cause,
        "confidence": confidence,
        "severity": top_hotspot.get("severity", "none"),
        "top_hotspot_node": top_hotspot.get("node"),
        "top_hotspot_interface": top_hotspot.get("interface"),
        "top_hotspot_queue": top_hotspot.get("queue"),
        "top_hotspot_score": top_score,
        "total_hotspots": safe_get(hotspots_summary, "total_hotspots", 0),
        "severity_counts": severity_counts,
        "contributing_factors": contributing,
    }


def build_evidence_index(
    hotspots: List[Dict[str, Any]],
    deltas: List[Dict[str, Any]],
    cos_hotspots: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {}

    delta_map = {d["entity_id"]: d for d in deltas}
    cos_map = {c["entity_id"]: c for c in (cos_hotspots or [])}

    for hotspot in hotspots:
        entity_id = hotspot["entity_id"]
        delta = delta_map.get(entity_id, {})
        cos_item = cos_map.get(entity_id, {})

        evidence[entity_id] = {
            "entity_id": entity_id,
            "node": hotspot["node"],
            "interface": hotspot["interface"],
            "queue": hotspot["queue"],
            "severity": hotspot["severity"],
            "score": hotspot["score"],
            "probable_cause": hotspot["probable_cause"],
            "signals": hotspot["signals"],
            "delta_running": delta.get("delta_running", {}),
            "delta_post": delta.get("delta_post", {}),
            "running_metrics": delta.get("running_metrics", {}),

            # phase-aware RCA fields from cos_hotspots
            "rise_tail_dropped_packets": cos_item.get("rise_tail_dropped_packets", 0.0),
            "linger_tail_dropped_packets": cos_item.get("linger_tail_dropped_packets", 0.0),
            "pre_tail_baseline_series": cos_item.get("pre_tail_baseline_series", []) or [],
            "post_tail_linger_series": cos_item.get("post_tail_linger_series", []) or [],
            "rise_ecn_ce_packets": cos_item.get("rise_ecn_ce_packets", 0.0),
            "linger_ecn_ce_packets": cos_item.get("linger_ecn_ce_packets", 0.0),
            "recovery_ratio_tail": cos_item.get("recovery_ratio_tail", 0.0),
            "event_delta_classification": cos_item.get("event_delta_classification"),
            "tail_linger_trend": cos_item.get("tail_linger_trend"),
            "ecn_linger_trend": cos_item.get("ecn_linger_trend"),
            "temporal_pattern": cos_item.get("temporal_pattern"),
            "classification_rank": cos_item.get("classification_rank", 0.0),
            "forwarding_class": cos_item.get("forwarding_class"),
            "classification": cos_item.get("classification"),
            "classification_confidence": cos_item.get("classification_confidence", 0.0),
        }

    return evidence

def build_topology_entities(hotspots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entities = []
    for h in hotspots:
        entities.append({
            "entity_id": h["entity_id"],
            "node": h["node"],
            "interface": h["interface"],
            "queue": h["queue"],
            "severity": h["severity"],
            "score": h["score"],
            "probable_cause": h["probable_cause"],
        })
    return entities

def resolve_cos_hotspot_correlation(case_summary: Dict[str, Any], case_path: Path) -> Path | None:
    files = safe_get(case_summary, "files", {}) or {}

    rel = files.get("cos_hotspot_correlation")
    if rel:
        p = resolve_artifact(rel)
        if p and p.exists():
            return p

    run_id = safe_get(case_summary, "run_id")
    if run_id:
        p = Path.cwd() / "artifacts" / "campaigns" / run_id / "cos_hotspot_correlation.json"
        if p.exists():
            return p

    p = case_path.parent / "cos_hotspot_correlation.json"
    if p.exists():
        return p

    return None


def resolve_orchestrator_report(case_summary: Dict[str, Any], case_path: Path) -> Path | None:
    files = safe_get(case_summary, "files", {}) or {}

    orchestrator_path = files.get("stress_orchestrator_report")
    if orchestrator_path:
        p = Path(orchestrator_path)
        if p.exists():
            return p
        abs_p = Path.cwd() / orchestrator_path
        if abs_p.exists():
            return abs_p

    run_id = safe_get(case_summary, "run_id")
    if run_id:
        p = Path.cwd() / "artifacts" / "orchestrator" / run_id / "stress_orchestrator_report.json"
        if p.exists():
            return p

    p = Path.cwd() / "artifacts" / "orchestrator" / "stress_orchestrator_report.json"
    if p.exists():
        return p

    return None


def compute_related_entities(result: Dict[str, Any]) -> List[str]:
    target = safe_get(result, "target", {}) or {}
    node = safe_get(target, "node")
    interface = safe_get(target, "interface")

    if not node or not interface:
        return []

    related = [to_entity_id(node, interface)]
    return related


def normalize_stress_result_to_event(
    result: Dict[str, Any],
    iteration: Dict[str, Any],
    orchestrator_report: Dict[str, Any],
) -> Dict[str, Any]:
    target = safe_get(result, "target", {}) or {}
    steps = safe_get(result, "steps", []) or []

    node = safe_get(target, "node", "unknown")
    interface = safe_get(target, "interface", "unknown")
    stress_mode = safe_get(result, "stress_mode", "unknown")
    result_status = safe_get(result, "status", "unknown")
    trigger_time = safe_get(iteration, "timestamp") or safe_get(orchestrator_report, "timestamp")

    disable_step = next((s for s in steps if " disable " in safe_get(s, "step", "")), {})
    enable_step = next((s for s in steps if " enable " in safe_get(s, "step", "")), {})

    if stress_mode == "interface_bounce":
        event_name = "fabric_interface_bounce"
        event_type = "fabric_link"
        summary = safe_get(result, "details", f"Interface bounce executed on {node}:{interface}.")
    else:
        event_name = f"stress_{stress_mode}"
        event_type = "stress_trigger"
        summary = safe_get(result, "details", f"Stress action {stress_mode} executed on {node}:{interface}.")

    return {
        "event_name": event_name,
        "event_type": event_type,
        "target_node": node,
        "target_interface": interface,
        "trigger_time": trigger_time,
        "clear_time": trigger_time,
        "duration_seconds": None,
        "status": result_status,
        "anomaly_detected": None,
        "recovery_time_seconds": None,
        "impact_score": None,
        "related_entities": compute_related_entities(result),
        "summary": summary,
        "details": {
            "run_id": safe_get(orchestrator_report, "run_id"),
            "overall_status": safe_get(orchestrator_report, "overall_status"),
            "iteration": safe_get(iteration, "iteration"),
            "stress_mode": stress_mode,
            "target_host": safe_get(target, "host"),
            "disable_command": safe_get(disable_step, "command"),
            "disable_status": safe_get(disable_step, "status"),
            "enable_command": safe_get(enable_step, "command"),
            "enable_status": safe_get(enable_step, "status"),
            "steps": steps,
        },
    }


def build_events_from_orchestrator(orchestrator_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    iteration_results = safe_get(orchestrator_report, "iteration_results", []) or []
    for iteration in iteration_results:
        stress_action = safe_get(iteration, "stress_action", {}) or {}
        results = safe_get(stress_action, "results", []) or []

        for result in results:
            events.append(
                normalize_stress_result_to_event(
                    result=result,
                    iteration=iteration,
                    orchestrator_report=orchestrator_report,
                )
            )

    return events

def load_config_intent(case_summary: Dict[str, Any]) -> Dict[str, Any]:
    run_meta = safe_get(case_summary, "run_metadata", {}) or {}
    run_id = safe_get(case_summary, "run_id")

    candidate_paths = [
        Path.cwd() / "artifacts" / "config_intent" / "leaf1_config_intent.json",
    ]

    # Future-friendly: allow case_summary file pointer if added later
    files = safe_get(case_summary, "files", {}) or {}
    cfg_path = files.get("config_intent")
    if cfg_path:
        p = resolve_artifact(cfg_path)
        if p and p.exists():
            return load_json(p)

    for p in candidate_paths:
        if p.exists():
            return load_json(p)

    return {}

def resolve_artifact(rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    p = Path(rel_path)
    if p.is_absolute():
        return p
    return Path.cwd() / rel_path


def load_optional_artifact(rel_path: str | None) -> Dict[str, Any]:
    p = resolve_artifact(rel_path)
    if not p or not p.exists():
        return {}
    return load_json(p)

def load_ecmp_recovery(case_summary: Dict[str, Any]) -> Dict[str, Any]:
    files = safe_get(case_summary, "files", {}) or {}

    # Try from case_summary first (future-proof)
    ecmp_path = files.get("ecmp_recovery")

    if ecmp_path:
        data = load_optional_artifact(ecmp_path)
        if data:
            return data

    # Fallback (your current structure)
    run_id = safe_get(case_summary, "run_id")
    if run_id:
        p = Path.cwd() / "artifacts" / "campaigns" / run_id / "ecmp_recovery_rates.json"
        if p.exists():
            return load_json(p)

    return {}

def build_live_alert_summary(live_report: Dict[str, Any]) -> Dict[str, Any]:
    if not live_report:
        return {
            "iterations": 0,
            "total_alerts": 0,
            "critical_alerts": 0,
            "warning_alerts": 0,
            "top_alerts": [],
        }

    total_alerts = 0
    critical_alerts = 0
    warning_alerts = 0
    top_alerts: List[Dict[str, Any]] = []

    for iteration in live_report.get("iterations", []):
        alerts = iteration.get("alerts", []) or []
        total_alerts += len(alerts)
        critical_alerts += sum(1 for a in alerts if a.get("severity") == "critical")
        warning_alerts += sum(1 for a in alerts if a.get("severity") == "warning")
        for alert in alerts[:5]:
            top_alerts.append({
                "iteration": iteration.get("iteration"),
                "timestamp": iteration.get("timestamp"),
                "severity": alert.get("severity"),
                "type": alert.get("type"),
                "flow_key": alert.get("flow_key"),
                "rx_port": alert.get("rx_port"),
                "value": alert.get("value"),
            })

    return {
        "iterations": len(live_report.get("iterations", [])),
        "total_alerts": total_alerts,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "top_alerts": top_alerts[:10],
    }

def build_interface_drop_health(case_summary: Dict[str, Any]) -> Dict[str, Any]:
    files = safe_get(case_summary, "files", {}) or {}
    telemetry_diff = load_optional_artifact(files.get("telemetry_diff"))
    telemetry_analyzer = load_optional_artifact(files.get("telemetry_analyzer"))

    top_anomalies = telemetry_analyzer.get("anomalies", []) or []
    entity_rollup = telemetry_analyzer.get("entity_rollup", {}) or {}

    totals = {
        "in_errors": 0.0,
        "out_errors": 0.0,
        "in_discards": 0.0,
        "out_discards": 0.0,
        "carrier_transitions": 0.0,
    }

    impacted: Dict[str, Dict[str, Any]] = {}

    def _safe_num(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _touch(node: str, interface: str) -> Dict[str, Any]:
        key = f"{node}|{interface}"
        if key not in impacted:
            impacted[key] = {
                "node": node,
                "interface": interface,
                "in_errors": 0.0,
                "out_errors": 0.0,
                "in_discards": 0.0,
                "out_discards": 0.0,
                "carrier_transitions": 0.0,
            }
        return impacted[key]

    for item in top_anomalies:
        node = str(item.get("node") or item.get("device") or "unknown")
        interface = str(item.get("interface") or item.get("port") or "unknown")
        if not interface:
            continue
        interface = str(interface)
        metric = str(item.get("metric") or item.get("path") or "").lower()
        value = _safe_num(item.get("value", item.get("delta", 0.0)))
        entry = _touch(node, interface)

        if "in-errors" in metric or metric.endswith("in_errors"):
            totals["in_errors"] += value
            entry["in_errors"] += value
        elif "out-errors" in metric or metric.endswith("out_errors"):
            totals["out_errors"] += value
            entry["out_errors"] += value
        elif "in-discards" in metric or metric.endswith("in_discards"):
            totals["in_discards"] += value
            entry["in_discards"] += value
        elif "out-discards" in metric or metric.endswith("out_discards"):
            totals["out_discards"] += value
            entry["out_discards"] += value
        elif "carrier-transitions" in metric or metric.endswith("carrier_transitions"):
            totals["carrier_transitions"] += value
            entry["carrier_transitions"] += value

    if isinstance(entity_rollup, dict):
        for entity_id, rollup in entity_rollup.items():
            if not isinstance(rollup, dict):
                continue

            node = str(rollup.get("node") or "unknown")
            interface = rollup.get("interface")

            if not interface and isinstance(entity_id, str) and "|" in entity_id:
                parts = entity_id.split("|")
                if len(parts) >= 2 and parts[1].strip():
                    interface = parts[1].strip()

            if not interface:
                continue

            interface = str(interface)
            entry = _touch(node, interface)

            for src_key, dst_key in (
                ("in-errors", "in_errors"),
                ("out-errors", "out_errors"),
                ("in-discards", "in_discards"),
                ("out-discards", "out_discards"),
                ("carrier-transitions", "carrier_transitions"),
            ):
                val = _safe_num(rollup.get(src_key, 0.0))
                if val > 0:
                    totals[dst_key] += val
                    entry[dst_key] += val

    non_zero_impacted = [
        row for row in impacted.values()
        if (
            _safe_num(row.get("in_discards", 0.0)) > 0
            or _safe_num(row.get("out_discards", 0.0)) > 0
            or _safe_num(row.get("in_errors", 0.0)) > 0
            or _safe_num(row.get("out_errors", 0.0)) > 0
            or _safe_num(row.get("carrier_transitions", 0.0)) > 0
        )
    ]

    top_impacted_interfaces = sorted(
        non_zero_impacted,
        key=lambda x: (
            -(x["in_discards"] + x["out_discards"] + x["in_errors"] + x["out_errors"]),
            -x["carrier_transitions"],
            x["node"],
            x["interface"],
        ),
    )[:10]

    status = (
        "warning"
        if any(v > 0 for v in totals.values())
        else "normal"
    )

    return {
        "status": status,
        "totals": totals,
        "top_impacted_interfaces": top_impacted_interfaces,
        "diff_summary": telemetry_diff.get("summary", {}),
    }


def build_traffic_health(case_summary: Dict[str, Any]) -> Dict[str, Any]:
    files = safe_get(case_summary, "files", {}) or {}
    status = safe_get(case_summary, "status", {}) or {}

    rocev2_verdict = load_optional_artifact(files.get("rocev2_verdict"))
    traffic_verdict = load_optional_artifact(files.get("traffic_verifier"))
    live_report = load_optional_artifact(files.get("ixia_live_monitor"))
    port_pre = load_optional_artifact(files.get("ixia_port_pre"))
    port_post = load_optional_artifact(files.get("ixia_port_post"))
    hotspot_report = load_optional_artifact(files.get("rocev2_hotspot_report"))
    deep_report = load_optional_artifact(files.get("rocev2_deep_inspection"))

    live_summary = build_live_alert_summary(live_report)
    ixia_port_map = build_ixia_port_map(case_summary)

    worst_rx_ports = enrich_rx_port_rows(
        hotspot_report.get("worst_rx_ports", []) or [],
        ixia_port_map,
    )
    deep_rx_rollup = enrich_rx_port_rows(
        deep_report.get("rx_rollup", []) or [],
        ixia_port_map,
    )

    live_status = status.get("ixia_live_monitor")
    live_error = status.get("ixia_live_monitor_error")

    # Start with artifact verdicts
    deep_verdict_summary = deep_report.get("verdict_summary", {}) or {}

    root_cause_summary = deep_report.get("root_cause_summary", {}) or {}

    effective_rocev2_verdict = rocev2_verdict.get("verdict")
    effective_rocev2_summary = rocev2_verdict.get("summary", {}) or {}

    # Prefer deep inspection verdict/summary when it has real findings
    if deep_verdict_summary.get("total_findings", 0) > 0:
        effective_rocev2_verdict = deep_verdict_summary.get(
            "verdict", effective_rocev2_verdict
        )
        effective_rocev2_summary = deep_verdict_summary

    effective_traffic_verdict = traffic_verdict.get("verdict")
    effective_traffic_summary = traffic_verdict.get("summary", {}) or {}

    # If traffic verdict is missing or misleadingly pass, fall back to RoCE evidence
    if not effective_traffic_verdict:
        if effective_rocev2_verdict:
            effective_traffic_verdict = effective_rocev2_verdict
            effective_traffic_summary = {
                "derived_from": "rocev2_deep_inspection",
                "rocev2_verdict": effective_rocev2_verdict,
                "rocev2_total_findings": effective_rocev2_summary.get("total_findings", 0),
            }
    elif effective_traffic_verdict == "pass" and effective_rocev2_verdict in {"warn", "fail"}:
        effective_traffic_verdict = effective_rocev2_verdict
        effective_traffic_summary = {
            "derived_from": "rocev2_deep_inspection",
            "rocev2_verdict": effective_rocev2_verdict,
            "rocev2_total_findings": effective_rocev2_summary.get("total_findings", 0),
    }




    # Promote deep-inspection flow lists to top-level UI fields
    rocev2_top_seqerror_flows = deep_report.get("top_by_seqerror", []) or []
    rocev2_top_post_seqerror_increase_flows = (
        deep_report.get("top_by_seqerror_increase", []) or []
    )
    rocev2_top_delta_flows = deep_report.get("top_by_delta", []) or []
    rocev2_top_latency_flows = deep_report.get("top_by_latency", []) or []
    rocev2_total_findings = effective_rocev2_summary.get("total_findings", 0)
    rocev2_unique_flow_count = len((effective_rocev2_summary.get("by_flow", {}) or {}).keys())
    by_flow = effective_rocev2_summary.get("by_flow", {}) or {}

    top_unique_flow_key = None
    top_unique_flow_findings = 0
    if by_flow:
        top_unique_flow_key, top_unique_flow_findings = max(
            by_flow.items(),
            key=lambda item: item[1],
        )

    rocev2_top_unique_flow_summary = {}
    if top_unique_flow_key:
        parts = top_unique_flow_key.split("|")
        rocev2_top_unique_flow_summary = {
            "flow_key": top_unique_flow_key,
            "findings": top_unique_flow_findings,
            "tx_port": parts[0] if len(parts) > 0 else "",
            "rx_port": parts[1] if len(parts) > 1 else "",
            "flow_name": parts[2] if len(parts) > 2 else "",
            "src_qp": parts[3] if len(parts) > 3 else "",
            "dest_qp": parts[4] if len(parts) > 4 else "",
        }

    by_flow = effective_rocev2_summary.get("by_flow", {}) or {}

    deep_top_delta = deep_report.get("top_by_delta", []) or []
    deep_top_latency = deep_report.get("top_by_latency", []) or []

    flow_detail_index = {}

    for item in deep_top_delta + deep_top_latency:
        flow_key = "|".join([
            str(item.get("tx_port", "")),
            str(item.get("rx_port", "")),
            str(item.get("flow_name", "")),
            str(item.get("src_qp", "")),
            str(item.get("dest_qp", "")),
        ])
        if flow_key and flow_key != "||||":
            existing = flow_detail_index.get(flow_key)
            if not existing or (item.get("score", 0) > existing.get("score", 0)):
                flow_detail_index[flow_key] = item

    rocev2_top_unique_flows = []
    for flow_key, findings in sorted(by_flow.items(), key=lambda kv: kv[1], reverse=True)[:5]:
        parts = flow_key.split("|")
        detail = flow_detail_index.get(flow_key, {})
        rocev2_top_unique_flows.append({
            "flow_key": flow_key,
            "flow_name": parts[2] if len(parts) > 2 else "",
            "tx_port": parts[0] if len(parts) > 0 else "",
            "rx_port": parts[1] if len(parts) > 1 else "",
            "src_qp": parts[3] if len(parts) > 3 else "",
            "dest_qp": parts[4] if len(parts) > 4 else "",
            "findings": findings,
            "max_latency_ns": detail.get("max_latency_ns", 0),
            "ecn": detail.get("ecn", 0),
            "score": detail.get("score", 0),
        })

    rocev2_root_cause_summary = deep_report.get("root_cause_summary", {}) or {}
    rocev2_signal_breakdown = effective_rocev2_summary.get("signal_breakdown", {}) or {}

    return {
        "rocev2_verdict": effective_rocev2_verdict,
        "rocev2_summary": effective_rocev2_summary,
        "traffic_verdict": effective_traffic_verdict,
        "traffic_summary": effective_traffic_summary,
        "live_requested": live_status in {"ok", "failed"},
        "live_available": live_status == "ok",
        "live_error": live_error if live_status == "failed" else None,
        "live_alert_summary": live_summary,
        "worst_rx_ports": worst_rx_ports[:5],
        "deep_rx_hotspots": deep_rx_rollup[:5],
        "port_pre_summary": port_pre.get("summary", {}),
        "port_post_summary": port_post.get("summary", {}),
        "rocev2_deep_inspection": deep_report or {},
        "rocev2_top_seqerror_flows": rocev2_top_seqerror_flows,
        "rocev2_top_post_seqerror_increase_flows": rocev2_top_post_seqerror_increase_flows,
        "rocev2_top_delta_flows": rocev2_top_delta_flows,
        "rocev2_top_latency_flows": rocev2_top_latency_flows,
        "flow_drilldown_status": case_summary.get("roce_drilldown_status", {}),
        "rocev2_root_cause_summary": root_cause_summary,
        "rocev2_total_findings": rocev2_total_findings,
        "rocev2_unique_flow_count": rocev2_unique_flow_count,
        "rocev2_top_unique_flow_summary": rocev2_top_unique_flow_summary,
        "rocev2_root_cause_summary": rocev2_root_cause_summary,
        "rocev2_signal_breakdown": rocev2_signal_breakdown,
        "rocev2_top_unique_flows": rocev2_top_unique_flows,
    }


def build_telemetry_health(case_summary: Dict[str, Any]) -> Dict[str, Any]:
    files = safe_get(case_summary, "files", {}) or {}
    telemetry_diff = load_optional_artifact(files.get("telemetry_diff"))
    telemetry_analyzer = load_optional_artifact(files.get("telemetry_analyzer"))

    return {
        "diff_summary": telemetry_diff.get("summary", {}),
        "anomaly_summary": telemetry_analyzer.get("summary", {}),
        "entity_rollup": telemetry_analyzer.get("entity_rollup", {}),
        "top_anomalies": (telemetry_analyzer.get("anomalies", []) or [])[:20],
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "yes", "Yes"):
        return True
    if value in (0, "0", "false", "False", "no", "No"):
        return False
    return None


def _normalize_severity(value: Any) -> str:
    s = str(value or "low").strip().lower()
    if s in {"critical", "high", "medium", "low"}:
        return s
    if s in {"warning", "warn", "moderate"}:
        return "medium"
    if s in {"none", "normal", "info", "informational"}:
        return "low"
    return "low"


def _is_suspicious_classification(classification: str) -> bool:
    return classification in {
        "localized-lossy-mcast-pressure",
        "unexpected-taildrop-on-lossless",
        "queue-without-explicit-scheduler",
        "needs-manual-review",
    }


def _is_expected_classification(classification: str) -> bool:
    return classification in {
        "expected-ecn-pressure",
        "expected-transient-control-impact",
    }

def _normalize_cos_hotspot(item: Dict[str, Any]) -> Dict[str, Any]:
    node = safe_get(item, "node", "unknown")
    interface = safe_get(item, "interface", "unknown")
    queue = safe_get(item, "queue")
    classification = safe_get(item, "classification", "unknown")
    severity = _normalize_severity(safe_get(item, "severity", "low"))
    probable_cause = safe_get(item, "probable_cause", "unknown")

    tail_dropped_packets = _to_float(safe_get(item, "tail_dropped_packets", 0.0))
    ecn_ce_packets = _to_float(safe_get(item, "ecn_ce_packets", 0.0))
    red_dropped_packets = _to_float(safe_get(item, "red_dropped_packets", 0.0))
    in_resource_drops = _to_float(safe_get(item, "in_resource_drops", 0.0))
    peak_buffer_occupancy_percent = _to_float(safe_get(item, "peak_buffer_occupancy_percent", 0.0))
    classification_confidence = _to_float(safe_get(item, "classification_confidence", 0.0))

    correlation_score = _to_float(
        safe_get(item, "correlation_score", safe_get(item, "score", 0.0))
    )

    hotspot = {
        "entity_id": to_entity_id(node, interface, _safe_int(queue)),
        "node": node,
        "interface": interface,
        "queue": queue,
        "forwarding_class": safe_get(item, "forwarding_class"),
        "severity": severity,
        "severity_bucket": severity,
        "classification": classification,
        "classification_confidence": classification_confidence,
        "probable_cause": probable_cause,
        "correlation_score": correlation_score,
        "score": correlation_score,
        "tail_dropped_packets": tail_dropped_packets,
        "ecn_ce_packets": ecn_ce_packets,
        "red_dropped_packets": red_dropped_packets,
        "in_resource_drops": in_resource_drops,
        "peak_buffer_occupancy_percent": peak_buffer_occupancy_percent,
        "drop_rate": tail_dropped_packets + red_dropped_packets + in_resource_drops,
        "ecn_mark_rate": ecn_ce_packets,
        "no_loss": _safe_bool(safe_get(item, "no_loss")),
        "ecn_enabled": _safe_bool(safe_get(item, "ecn_enabled")),
        "explicit_scheduler_present": _safe_bool(safe_get(item, "explicit_scheduler_present")),
        "scheduler": safe_get(item, "scheduler"),
        "signals": safe_get(item, "signals", {}) or {},

        # existing delta fields
        "delta_tail_dropped_packets": _to_float(item.get("delta_tail_dropped_packets", 0.0)),
        "delta_ecn_ce_packets": _to_float(item.get("delta_ecn_ce_packets", 0.0)),
        "uses_delta_scoring": bool(item.get("uses_delta_scoring", False)),

        # phase-aware RCA fields
        "rise_tail_dropped_packets": _to_float(item.get("rise_tail_dropped_packets", 0.0)),
        "linger_tail_dropped_packets": _to_float(item.get("linger_tail_dropped_packets", 0.0)),
        "pre_tail_baseline_series": safe_get(item, "pre_tail_baseline_series", []) or [],
        "rise_ecn_ce_packets": _to_float(item.get("rise_ecn_ce_packets", 0.0)),
        "linger_ecn_ce_packets": _to_float(item.get("linger_ecn_ce_packets", 0.0)),
        "recovery_ratio_tail": _to_float(item.get("recovery_ratio_tail", 0.0)),
        "event_delta_classification": safe_get(item, "event_delta_classification", "unknown"),
        "tail_linger_trend": safe_get(item, "tail_linger_trend"),
        "ecn_linger_trend": safe_get(item, "ecn_linger_trend"),
        "temporal_pattern": safe_get(item, "temporal_pattern"),
        "classification_rank": _to_float(item.get("classification_rank", 0.0)),
        "post_tail_linger_series": safe_get(item, "post_tail_linger_series", []) or [],
    }

    hotspot["is_suspicious"] = _is_suspicious_classification(classification)
    hotspot["is_expected_ecn"] = _is_expected_classification(classification)
    hotspot["symptom_type"] = (
        "suspicious"
        if hotspot["is_suspicious"]
        else "expected_ecn" if hotspot["is_expected_ecn"] else "informational"
    )

    hotspot["interpretation"] = (
        probable_cause
        if probable_cause and probable_cause != "unknown"
        else classification
    )

    return hotspot




def _build_cos_severity_distribution(all_hotspots: List[Dict[str, Any]]) -> Dict[str, Any]:
    distribution = {
        "suspicious": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "expected_ecn": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "informational": {"count": 0},
    }

    for item in all_hotspots:
        sev = _normalize_severity(item.get("severity"))
        if item.get("is_suspicious"):
            distribution["suspicious"][sev] += 1
        elif item.get("is_expected_ecn"):
            distribution["expected_ecn"][sev] += 1
        else:
            distribution["informational"]["count"] += 1

    return distribution

def build_cos_health(case_summary: Dict[str, Any], case_path: Path) -> Dict[str, Any]:
    cos_report_path = resolve_cos_hotspot_correlation(case_summary, case_path)
    cos_report = load_json(cos_report_path) if cos_report_path and cos_report_path.exists() else {}

    raw_hotspots = cos_report.get("hotspots", []) or []
    summary = cos_report.get("summary", {}) or {}

    all_hotspots = [_normalize_cos_hotspot(item) for item in raw_hotspots]

    all_hotspots.sort(
        key=lambda x: (
            0 if x.get("is_suspicious") else 1,
            -_to_float(x.get("correlation_score", 0.0)),
            -_to_float(x.get("drop_rate", 0.0)),
            -_to_float(x.get("ecn_mark_rate", 0.0)),
            str(x.get("node") or ""),
            str(x.get("interface") or ""),
            str(x.get("queue") or ""),
        )
    )

    suspicious_hotspots = [x for x in all_hotspots if x.get("is_suspicious")]
    expected_hotspots = [x for x in all_hotspots if x.get("is_expected_ecn")]
    top_hotspots = all_hotspots[:10]
    top_cos_hotspot = suspicious_hotspots[0] if suspicious_hotspots else (all_hotspots[0] if all_hotspots else {})

    severity_distribution = _build_cos_severity_distribution(all_hotspots)
    status, queue_rca_summary, rca_interpretation, hotspot_interpretation = _build_cos_interpretation(
        all_hotspots=all_hotspots,
        suspicious_hotspots=suspicious_hotspots,
        expected_hotspots=expected_hotspots,
    )

    return {
        "status": status,
        "summary": summary,
        "queue_rca_summary": queue_rca_summary,
        "rca_interpretation": rca_interpretation,
        "hotspot_interpretation": hotspot_interpretation,
        "hotspots": top_hotspots,
        "top_hotspots": top_hotspots,
        "all_hotspots": all_hotspots,
        "total_hotspots": len(all_hotspots),
        "suspicious_hotspot_count": len(suspicious_hotspots),
        "expected_hotspot_count": len(expected_hotspots),
        "informational_hotspot_count": max(len(all_hotspots) - len(suspicious_hotspots) - len(expected_hotspots), 0),
        "severity_distribution": severity_distribution,
        "top_cos_hotspot": top_cos_hotspot,
        "source_path": str(cos_report_path) if cos_report_path else None,
    }


def _build_cos_interpretation(
    all_hotspots: List[Dict[str, Any]],
    suspicious_hotspots: List[Dict[str, Any]],
    expected_hotspots: List[Dict[str, Any]],
) -> Tuple[str, str, str, str]:
    total = len(all_hotspots)
    suspicious_total = len(suspicious_hotspots)
    expected_total = len(expected_hotspots)
    info_total = max(total - suspicious_total - expected_total, 0)

    status = "pass"
    if suspicious_total > 0:
        status = "warning"
    elif total == 0:
        status = "normal"

    queue_rca_summary = (
        f"{suspicious_total} suspicious, "
        f"{expected_total} expected-ECN, "
        f"{info_total} informational hotspot(s)"
    )

    if suspicious_total > 0:
        top = suspicious_hotspots[0]
        rca_interpretation = (
            f"Detected {suspicious_total} suspicious CoS hotspot(s) beyond expected ECN-regulated "
            f"behavior. Primary queue of interest is {safe_get(top, 'node', 'unknown')} "
            f"{safe_get(top, 'interface', 'unknown')} queue {safe_get(top, 'queue', 'unknown')} "
            f"classified as {safe_get(top, 'classification', 'unknown')}."
        )
    elif expected_total > 0:
        top = expected_hotspots[0]
        rca_interpretation = (
            f"Observed {expected_total} congestion hotspot(s) dominated by ECN/marking behavior. "
            f"Top queue appears consistent with expected congestion handling on "
            f"{safe_get(top, 'node', 'unknown')} {safe_get(top, 'interface', 'unknown')} "
            f"queue {safe_get(top, 'queue', 'unknown')}."
        )
    else:
        rca_interpretation = "No significant CoS hotspot anomalies were detected."

    hotspot_interpretation = (
        f"Hotspots are ranked by suspiciousness, correlation score, drop behavior, and ECN mark rate. "
        f"Showing interpreted results for {total} hotspot record(s)."
    )

    return status, queue_rca_summary, rca_interpretation, hotspot_interpretation




def build_bug_candidate_signals(
    traffic_health: Dict[str, Any],
    telemetry_health: Dict[str, Any],
    root_cause: Dict[str, Any],
    cos_health: Dict[str, Any],
) -> List[str]:
    signals: List[str] = []

    if traffic_health.get("rocev2_verdict") in ("warning", "fail"):
        signals.append(f"rocev2_verdict_{traffic_health.get('rocev2_verdict')}")
    if traffic_health.get("traffic_verdict") in ("warning", "fail"):
        signals.append(f"traffic_verdict_{traffic_health.get('traffic_verdict')}")

    live = traffic_health.get("live_alert_summary", {})
    if live.get("critical_alerts", 0) > 0:
        signals.append("ixia_live_critical_alert")
    elif live.get("total_alerts", 0) > 0:
        signals.append("ixia_live_alert")

    anomaly_summary = telemetry_health.get("anomaly_summary", {})
    if anomaly_summary.get("by_severity", {}).get("critical", 0) > 0:
        signals.append("telemetry_critical_anomaly")
    if anomaly_summary.get("by_severity", {}).get("warning", 0) > 0:
        signals.append("telemetry_warning_anomaly")

    diff_summary = telemetry_health.get("diff_summary", {})
    if diff_summary.get("total_differences", 0) > 0:
        signals.append("telemetry_diff_detected")

    top_hotspots = (root_cause.get("summary", {}) or {}).get("top_hotspots", []) or []
    if top_hotspots:
        top = top_hotspots[0]
        if top.get("device") and top.get("interface"):
            signals.append("root_cause_mapped_to_dut")
        if top.get("classification"):
            signals.append(f"root_cause_{top.get('classification')}")

    cos_top = cos_health.get("top_cos_hotspot", {}) or {}
    cos_summary = cos_health.get("summary", {}) or {}
    if cos_top.get("classification") == "localized-lossy-mcast-pressure":
        signals.append("cos_localized_lossy_mcast_pressure")
    if cos_top.get("classification") == "unexpected-taildrop-on-lossless":
        signals.append("cos_unexpected_taildrop_on_lossless")
    if cos_top.get("classification") == "queue-without-explicit-scheduler":
        signals.append("cos_queue_without_explicit_scheduler")
    if cos_top.get("classification") == "needs-manual-review":
        signals.append("cos_needs_manual_review")

    if cos_summary.get("expected_ecn_pressure", 0) > 0 or cos_health.get("expected_hotspot_count", 0) > 0:
        signals.append("cos_expected_ecn_pressure")

    return signals


def build_stress_classification(
    case_summary: Dict[str, Any],
    traffic_health: Dict[str, Any],
    telemetry_health: Dict[str, Any],
    root_cause: Dict[str, Any],
    cos_health: Dict[str, Any],
    events: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    signals = build_bug_candidate_signals(traffic_health, telemetry_health, root_cause, cos_health)
    status = case_summary.get("status", {}) or {}

    event_count = len(events)
    hotspot_count = summary.get("total_hotspots", 0)
    suspicious_cos_hotspots = cos_health.get("suspicious_hotspot_count", 0)
    expected_cos_hotspots = cos_health.get("expected_hotspot_count", 0)

    hard_status_fail = any(
        status.get(name) == "failed"
        for name in (
            "pre_snapshot",
            "running_snapshot",
            "post_snapshot",
            "congestion_analysis",
            "fabric_ranking",
            "delta_analysis",
        )
    )

    if hard_status_fail or event_count == 0:
        classification = "FAIL"
        reason = "stress execution or RCA pipeline failed"
    elif hotspot_count > 0 and suspicious_cos_hotspots > 0:
        classification = "BUG-CANDIDATE"
        reason = "stress impact is visible and CoS correlation found suspicious hotspot behavior"
    elif hotspot_count > 0 and signals and suspicious_cos_hotspots == 0 and expected_cos_hotspots > 0:
        classification = "PASS"
        reason = "stress event executed and top hotspots align with expected ECN-regulated behavior"
    elif hotspot_count > 0 and signals:
        classification = "BUG-CANDIDATE"
        reason = "stress impact is visible and traffic/telemetry evidence indicates suspicious behavior"
    elif hotspot_count > 0:
        classification = "PASS"
        reason = "stress event executed and impact is visible without additional suspicious evidence"
    else:
        classification = "PARTIAL"
        reason = "stress event exists but hotspot evidence is weak or incomplete"

    return {
        "classification": classification,
        "reason": reason,
        "bug_candidate_signals": signals,
    }


def _normalize_nodes_field(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [n.strip() for n in value.split(",") if n.strip()]
    return []


def build_rca_ui_report(case_summary_path: str) -> Dict[str, Any]:
    case_path = Path(case_summary_path)
    case_summary = load_json(case_path)
    files = safe_get(case_summary, "files", {}) or {}

    running_congestion_path = resolve_artifact(files["running_congestion"])
    running_hotspots_path = resolve_artifact(files["running_fabric_hotspots"])
    running_delta_path = resolve_artifact(files["running_delta"])

    running_congestion = load_json(running_congestion_path)
    running_hotspots = load_json(running_hotspots_path)
    running_delta = load_json(running_delta_path)

    interface_drop_health = build_interface_drop_health(case_summary)

    hotspots_detail = [
        normalize_hotspot_entry(item)
        for item in safe_get(running_congestion, "hotspots", []) or []
    ]

    top_hotspots = [
        normalize_hotspot_entry(item)
        for item in safe_get(running_hotspots, "top_queues", []) or []
    ]

    delta_entries = [normalize_delta_entry(item) for item in (running_delta or [])]

    summary = build_summary(case_summary, running_hotspots, running_congestion)

    traffic_health = build_traffic_health(case_summary)
    telemetry_health = build_telemetry_health(case_summary)
    cos_health = build_cos_health(case_summary, case_path)

    evidence_index = build_evidence_index(
        hotspots_detail,
        delta_entries,
        cos_hotspots=cos_health.get("all_hotspots", []),
    )

    orchestrator_report = {}


    orchestrator_report_path = resolve_orchestrator_report(case_summary, case_path)
    if orchestrator_report_path and orchestrator_report_path.exists():
        orchestrator_report = load_json(orchestrator_report_path)

    events = build_events_from_orchestrator(orchestrator_report) if orchestrator_report else []

    ecmp_recovery = load_ecmp_recovery(case_summary)
    config_intent = load_config_intent(case_summary)
    root_cause = load_optional_artifact(files.get("root_cause_correlation"))
    congestion_inspection = load_optional_artifact(files.get("congestion_inspection"))

    stress_classification = build_stress_classification(
        case_summary=case_summary,
        traffic_health=traffic_health,
        telemetry_health=telemetry_health,
        root_cause=root_cause,
        cos_health=cos_health,
        events=events,
        summary=summary,
    )

    top_cos_hotspot = cos_health.get("top_cos_hotspot", {}) or {}
    summary["top_hotspot_event_outcome"] = top_cos_hotspot.get("event_delta_classification")
    summary["top_hotspot_recovery_trend"] = top_cos_hotspot.get("tail_linger_trend")
    summary["top_hotspot_persistence_ratio"] = top_cos_hotspot.get("recovery_ratio_tail")
    summary["total_queue_hotspots_detected"] = summary.get("total_hotspots", 0)
    summary["suspicious_cos_hotspots"] = cos_health.get("suspicious_hotspot_count", 0)
    summary["expected_ecn_hotspots"] = cos_health.get("expected_hotspot_count", 0)
    summary["informational_cos_hotspots"] = cos_health.get("informational_hotspot_count", 0)
    summary["top_affected_queue"] = top_cos_hotspot.get("queue")
    summary["top_forwarding_class"] = top_cos_hotspot.get("forwarding_class")
    summary["top_hotspot_classification"] = top_cos_hotspot.get("classification")
    summary["pattern_scope"] = (
        "localized"
        if cos_health.get("suspicious_hotspot_count", 0) == 1
        else "fabric-wide" if cos_health.get("suspicious_hotspot_count", 0) > 1
        else "expected"
    )
    summary["queue_rca_summary"] = cos_health.get("queue_rca_summary")
    summary["rca_interpretation"] = cos_health.get("rca_interpretation")
    summary["hotspot_interpretation"] = cos_health.get("hotspot_interpretation")

    ecmp_analysis = ecmp_recovery.get("analysis", {}) or {}
    summary["ecmp_classification"] = ecmp_analysis.get("classification")
    summary["ecmp_severity"] = ecmp_analysis.get("severity")
    summary["ecmp_confidence"] = ecmp_analysis.get("confidence")
    if ecmp_recovery.get("mode") == "per_target":
        ecmp_targets = ecmp_recovery.get("targets", []) or []

        enriched_ecmp_targets = []
        for t in ecmp_targets:
            item = dict(t)
            raw_report = item.get("raw_report", {}) or {}
            item["mixed_speed_spec_validation_ui"] = _normalize_mixed_speed_spec_validation(
                raw_report.get("mixed_speed_spec_validation", {})
            )
            enriched_ecmp_targets.append(item)

        ecmp_recovery_ui = {
            "mode": "per_target",
            "target_count": ecmp_recovery.get("target_count", len(enriched_ecmp_targets)),
            "targets": enriched_ecmp_targets,
            "summary": ecmp_recovery.get(
                "summary",
                {
                    "ok_targets": sum(1 for t in enriched_ecmp_targets if t.get("status") == "ok"),
                    "failed_targets": sum(1 for t in enriched_ecmp_targets if t.get("status") == "failed"),
                    "skipped_targets": sum(1 for t in enriched_ecmp_targets if t.get("status") == "skipped"),
                },
            ),
            "config_intent": config_intent,
    }
    else:
        ecmp_recovery_ui = {
            "mode": "single_target",
            "analysis": ecmp_recovery.get("analysis", {}) or {},
            "analysis_node": ecmp_recovery.get("node"),
            "baseline_summary": ecmp_recovery.get("baseline_summary", {}) or {},
            "recovery_summary": ecmp_recovery.get("recovery_summary", {}) or {},
            "config_intent": config_intent,
        }

    # Backfill ECMP input/view from telemetry artifacts when needed.
    # Keep legacy ecmp_recovery behavior intact for older working runs.
    ecmp_recovery_input = None
    ecmp_recovery_view = None

    try:
        ecmp_recovery_input = build_ecmp_recovery_input_from_existing_artifacts(
            case_summary, {}
        )
    except Exception:
        ecmp_recovery_input = None

    try:
        # Build against a minimal report context that includes the injected ECMP input
        ecmp_view_context = {
            "ecmp_recovery_input": ecmp_recovery_input or {}
        }
        ecmp_recovery_view = build_ecmp_recovery_view(
            case_summary,
            ecmp_view_context,
        )
    except Exception:
        ecmp_recovery_view = None
    report = {
        "run_metadata": {
            "generated_at": safe_get(case_summary, "generated_at"),
            "run_id": safe_get(case_summary, "run_id"),
            "intent_name": safe_get(case_summary, "intent_name"),
            "src": safe_get(case_summary, "src"),
            "dst": safe_get(case_summary, "dst"),
            "profile": safe_get(case_summary, "profile"),
            "nodes": _normalize_nodes_field(safe_get(case_summary, "nodes", [])),
        },
        "summary": summary,
        "events": events,
        "hotspots": top_hotspots,
        "all_hotspots": hotspots_detail,
        "deltas": delta_entries,
        "severity_counts": safe_get(running_hotspots, "severity_counts", {}),
        "topology_entities": build_topology_entities(top_hotspots),
        "root_cause": {
            "primary_cause": summary["primary_cause"],
            "confidence": summary["confidence"],
            "contributing_factors": summary["contributing_factors"],
            "mapped_summary": root_cause.get("summary", {}),
            "mapped_conclusion": root_cause.get("conclusion"),
        },
        "stress_classification": stress_classification,
        "traffic_health": traffic_health,
        "telemetry_health": telemetry_health,
        "cos_health": cos_health,
        "congestion_inspection": {
            "summary": congestion_inspection.get("summary", {}),
            "conclusion": congestion_inspection.get("conclusion"),
        },
        "bug_candidate_signals": stress_classification.get("bug_candidate_signals", []),
        "evidence_index": evidence_index,
        "source_files": {
            **files,
            "cos_hotspot_correlation": (
                cos_health.get("source_path")
                or files.get("cos_hotspot_correlation")
            ),
            "stress_orchestrator_report": str(orchestrator_report_path) if orchestrator_report_path else None,
            "topology": safe_get(case_summary, "topology"),
        },
        "interface_drop_health": interface_drop_health,
        "ecmp_recovery": ecmp_recovery_ui,
        "ecmp_recovery_input": ecmp_recovery_input,
        "ecmp_recovery_view": ecmp_recovery_view,
    }

    return report


def write_rca_ui_report(case_summary_path: str, output_path: str | None = None) -> str:
    report = build_rca_ui_report(case_summary_path)

    if output_path is None:
        case_path = Path(case_summary_path)
        run_dir = case_path.parent
        output_path = str(run_dir / "rca_ui_report.json")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return str(out)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build UI-friendly RCA report from RCA case artifacts")
    parser.add_argument("--case-summary", required=True, help="Path to rca_case_summary.json")
    parser.add_argument("--output", help="Optional output path for rca_ui_report.json")
    args = parser.parse_args()

    out = write_rca_ui_report(args.case_summary, args.output)
    print(f"RCA UI report written to: {out}")
