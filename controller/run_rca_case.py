import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from controller.ixia_client import IxiaClient, load_json_file
from controller.progress_logger import ProgressLogger
from typing import Any, Dict, List, Tuple, Optional
from controller.ecmp_recovery_analyzer import (
    build_ecmp_recovery_report,
    write_ecmp_recovery_report,
)
from controller.telemetry_monitor import collect_recovery_snapshot
from controller.utils import atomic_write_json
DEFAULT_PROFILE = "hotspot_congestion_qmon"
DEFAULT_TOPOLOGY = "artifacts/topology/topology_full.json"
DEFAULT_IXIA_INVENTORY = os.path.join("controller", "ixia_inventory.json")

def _parse_ecmp_analysis_targets(value):
    result = []
    for item in str(value or "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        node, iface = item.split(":", 1)
        result.append({
            "node": node.strip(),
            "interface": iface.strip().replace("~", ":"),
        })
    return result


def _extract_orchestrator_degraded_sample_paths(stress_report_path):
    if not stress_report_path or not os.path.exists(stress_report_path):
        return {}

    with open(stress_report_path, "r", encoding="utf-8") as fh:
        report = json.load(fh)

    paths = {}

    def add_variants(node, iface, sample_paths):
        iface_colon = str(iface).replace("~", ":")
        iface_tilde = str(iface).replace(":", "~")

        for key in (
            f"{node}|{iface_colon}",
            f"{node}:{iface_colon}",
            f"{node}|{iface_tilde}",
            f"{node}:{iface_tilde}",
        ):
            paths[key] = sample_paths

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("stress_mode") == "interface_hold_restore":
                target = obj.get("target") or {}
                node = target.get("node")
                iface = target.get("interface")
                sample_paths = obj.get("ecmp_degraded_sample_paths") or []

                if node and iface and sample_paths:
                    add_variants(node, iface, sample_paths)

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(report)
    return paths

def _extract_degraded_hold_windows(stress_report_path):
    if not stress_report_path or not os.path.exists(stress_report_path):
        return {}

    with open(stress_report_path, "r", encoding="utf-8") as fh:
        report = json.load(fh)

    windows = {}

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("stress_mode") == "interface_hold_restore":
                target = obj.get("target") or {}
                node = target.get("node")
                iface = target.get("interface")
                ts = obj.get("phase_timestamps") or {}
                if node and iface and ts:
                    windows[f"{node}|{iface}"] = ts
                    windows[f"{node}:{iface}"] = ts
                    windows[f"{node}|{str(iface).replace(':', '~')}"] = ts
                    windows[f"{node}:{str(iface).replace(':', '~')}"] = ts

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(report)
    return windows



def _parse_ecmp_analysis_targets(raw: str | None) -> list:
    if not raw:
        return []

    targets = []
    for item in str(raw).split(","):
        item = item.strip()
        if not item:
            continue

        if ":" not in item:
            raise ValueError(
                f"Invalid --ecmp-analysis-targets item '{item}', expected node:interface"
            )

        node, interface = item.split(":", 1)
        node = node.strip()
        interface = interface.strip()

        if not node or not interface:
            raise ValueError(
                f"Invalid --ecmp-analysis-targets item '{item}', expected node:interface"
            )

        targets.append(
            {
                "node": node,
                "interface": interface,
                "entity": f"{node}|{interface}",
                "target_source": "ecmp_analysis_targets_override",
            }
        )

    return targets


def _resolve_ecmp_interfaces_from_device_facts(node_name: str) -> list:
    facts_path = Path("artifacts") / "device_facts" / f"{node_name}_facts.json"
    if not facts_path.exists():
        return []

    try:
        facts = load_json(facts_path)
    except Exception:
        return []

    interface_speeds = facts.get("interface_speeds", {}) or {}
    if not isinstance(interface_speeds, dict) or not interface_speeds:
        return []

    interfaces = []
    for ifname in sorted(interface_speeds.keys()):
        # Keep only physical/chassis interfaces used for fabric ECMP.
        if not str(ifname).startswith(("et-", "xe-", "ge-")):
            continue

        interfaces.append(
            {
                "node": node_name,
                "interface": ifname,
            }
        )

    return interfaces

def _build_ecmp_analysis_targets(
    *,
    args,
    file_overrides: dict,
    fallback_targets: list,
) -> list:
    """
    Build ECMP analysis targets independently from stress targets.

    Use this when the event target is different from the ECMP decision point.
    Example:
      event target    = spine1/spine2 links
      analysis target = leaf1 ECMP member group
    """
    override_node = getattr(args, "ecmp_analysis_node", None)
    override_interface = getattr(args, "ecmp_analysis_interface", None)

    explicit_targets = _parse_ecmp_analysis_targets(
        getattr(args, "ecmp_analysis_targets", None)
    )

    if explicit_targets:
        return explicit_targets

    if not override_node:
        return fallback_targets or []

    if override_interface:
        return [
            {
                "node": override_node,
                "interface": override_interface,
                "entity": f"{override_node}|{override_interface}",
                "target_source": "ecmp_analysis_override",
            }
        ]

    interfaces = []

    # First try device facts.
    try:
        interfaces = _resolve_ecmp_interfaces_from_device_facts(override_node)
    except Exception:
        interfaces = []

    # Fallback to topology if device facts are empty.
    if not interfaces:
        try:
            topology = load_json(args.topology)
            all_targets = extract_fabric_interfaces(topology)
            interfaces = [
                t for t in all_targets
                if str(t.get("node", "")).strip().lower()
                == str(override_node).strip().lower()
            ]
        except Exception:
            interfaces = []

    if not interfaces:
        progress = getattr(args, "progress", None)
        print(f"[ECMP-DEBUG] override_node={override_node} resolved_interfaces={interfaces[:10]}")
        raise RuntimeError(
            f"--ecmp-analysis-node {override_node} was provided, "
            "but no fabric interfaces could be resolved from device facts or topology"
        )

    targets = []
    for item in interfaces:
        node = item.get("node") or override_node
        interface = item.get("interface")
        if not interface:
            continue
        targets.append(
            {
                "node": node,
                "interface": interface,
                "entity": f"{node}|{interface}",
                "target_source": "ecmp_analysis_override",
            }
        )

    return targets

def _encode_iface_for_snapshot(iface: str) -> str:
    # '/' -> '_' and ':' -> '~' so sample suffix _1,_2,_3 stays distinct
    return str(iface).replace("/", "_").replace(":", "~")

def _update_roce_case_summary(
    *,
    case_summary_path: str,
    rocev2_pre: str | None = None,
    rocev2_post: str | None = None,
    rocev2_verdict: str | None = None,
    rocev2_deep_inspection: str | None = None,
    rocev2_hotspot_report: str | None = None,
    ixia_live_monitor: str | None = None,
    rocev2_pre_status: str | None = None,
    rocev2_post_status: str | None = None,
    rocev2_verdict_status: str | None = None,
    rocev2_deep_inspection_status: str | None = None,
    rocev2_hotspot_report_status: str | None = None,
    ixia_live_monitor_status: str | None = None,
) -> None:
    data = load_json(case_summary_path)
    files = data.setdefault("files", {})
    status = data.setdefault("status", {})

    if rocev2_pre is not None:
        files["rocev2_pre"] = rocev2_pre
    if rocev2_post is not None:
        files["rocev2_post"] = rocev2_post
    if rocev2_verdict is not None:
        files["rocev2_verdict"] = rocev2_verdict
    if rocev2_deep_inspection is not None:
        files["rocev2_deep_inspection"] = rocev2_deep_inspection
    if rocev2_hotspot_report is not None:
        files["rocev2_hotspot_report"] = rocev2_hotspot_report
    if ixia_live_monitor is not None:
        files["ixia_live_monitor"] = ixia_live_monitor

    if rocev2_pre_status is not None:
        status["rocev2_pre"] = rocev2_pre_status
    if rocev2_post_status is not None:
        status["rocev2_post"] = rocev2_post_status
    if rocev2_verdict_status is not None:
        status["rocev2_verdict"] = rocev2_verdict_status
    if rocev2_deep_inspection_status is not None:
        status["rocev2_deep_inspection"] = rocev2_deep_inspection_status
    if rocev2_hotspot_report_status is not None:
        status["rocev2_hotspot_report"] = rocev2_hotspot_report_status
    if ixia_live_monitor_status is not None:
        status["ixia_live_monitor"] = ixia_live_monitor_status

    #with open(case_summary_path, "w") as f:
    #    json.dump(data, f, indent=2)
    atomic_write_json(case_summary_path, data, indent=2)


def _run_roce_deep_inspection(
    *,
    run_id: str,
    pre_path: str,
    post_path: str,
    verdict_path: str,
) -> str:
    from controller.rocev2_deep_inspector import inspect

    output_path = f"artifacts/campaigns/{run_id}/traffic/rocev2_deep_inspection.json"

    inspect(
        pre_path=pre_path,
        post_path=post_path,
        verdict_path=verdict_path,
        output_path=output_path,
        run_id=run_id,
        source_type="campaign",
    )
    return output_path


def get_lightweight_roce_view_candidates() -> list[str]:
    return [
        "RoCEv2 Per Port",
        "RoCEv2",
    ]


def build_roce_drilldown_status_lightweight(
    selected_view: str | None,
    view_found: bool,
    error: str | None = None,
) -> dict:
    selected = str(selected_view or "").strip()

    if error:
        return {
            "attempted": False,
            "available": False,
            "reason": f"lightweight_mode_error: {error}",
            "selected_view": selected or None,
        }

    if not view_found:
        return {
            "attempted": False,
            "available": False,
            "reason": "lightweight_mode_view_not_found",
            "selected_view": selected or None,
        }

    if selected.lower() == "rocev2 per port":
        return {
            "attempted": False,
            "available": False,
            "reason": "lightweight_mode_port_level_only",
            "selected_view": selected,
        }

    return {
        "attempted": False,
        "available": False,
        "reason": "lightweight_mode_no_flow_drilldown",
        "selected_view": selected or None,
    }


def _extract_targets_from_orchestrator_report(path: str) -> List[Dict[str, str]]:
    import json

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    out: List[Dict[str, str]] = []
    seen = set()

    iteration_results = data.get("iteration_results", []) or []

    for iteration in iteration_results:
        stress_action = iteration.get("stress_action", {}) or {}
        results = stress_action.get("results", []) or []

        for result in results:
            target = result.get("target", {}) or {}
            node = str(target.get("node") or "").strip()
            interface = str(target.get("interface") or "").strip()

            if not node or not interface:
                continue

            key = f"{node}|{interface}"
            if key in seen:
                continue

            out.append(
                {
                    "entity": key,
                    "node": node,
                    "interface": interface,
                }
            )
            seen.add(key)

    return out

def _resolve_ixia_view_caption(client, session_id: int, preferred: list[str]) -> str | None:
    views = client.get_statistics_views(session_id) or []

    captions = []
    for v in views:
        cap = str(v.get("caption") or "").strip()
        if cap:
            captions.append(cap)

    for want in preferred:
        for cap in captions:
            if cap == want:
                return cap

    for want in preferred:
        want_l = want.lower()
        for cap in captions:
            if want_l in cap.lower():
                return cap

    return None

# optional helper if you already have q8 metric extraction elsewhere
def _extract_q8_taildrop_growth_from_running_outputs(run_id: str) -> Optional[float]:
    try:
        ui_report_path = os.path.join("artifacts", "campaigns", run_id, "rca_ui_report.json")
        if not os.path.exists(ui_report_path):
            return None

        with open(ui_report_path, "r", encoding="utf-8") as fh:
            ui_report = json.load(fh)

        entities = ui_report.get("entities", [])
        for ent in entities:
            if str(ent.get("node", "")).lower() == str(bounced_node).lower() and str(ent.get("interface")) == str(bounced_interface):
                if str(ent.get("queue")) == "8":
                    phase_rca = ent.get("phase_aware_rca", {}) or {}
                    linger = phase_rca.get("linger")
                    if linger is not None:
                        return float(linger)
                    rise = phase_rca.get("rise")
                    if rise is not None:
                        return float(rise)
        return None
    except Exception:
        return None


def _resolve_best_telemetry_interface_alias(
    *,
    baseline_report: Dict[str, Any],
    running_report: Dict[str, Any],
    post_report: Dict[str, Any],
    pre_reports: List[Dict[str, Any]],
    post_reports: List[Dict[str, Any]],
    node: str,
    queue: int,
    preferred_tail_value: int,
    current_interface: str,
) -> str:
    """
    Resolve one telemetry interface alias that works consistently across
    baseline/running/post + pre/recovery samples.

    Preference:
      1. exact/current interface if it already produces data anywhere
      2. alias resolved across all reports
      3. fallback to existing interface
    """
    all_reports: List[Dict[str, Any]] = []

    for rep in [baseline_report, running_report, post_report]:
        if isinstance(rep, dict) and rep:
            all_reports.append(rep)

    for rep in pre_reports or []:
        if isinstance(rep, dict) and rep:
            all_reports.append(rep)

    for rep in post_reports or []:
        if isinstance(rep, dict) and rep:
            all_reports.append(rep)

    def _score_interface(candidate_interface: str) -> Tuple[int, int, int]:
        hits = 0
        max_tail = 0
        max_occ = 0

        for rep in all_reports:
            metrics = _extract_qmon_queue_counters(
                rep,
                node=node,
                interface=candidate_interface,
                queue=queue,
            )
            tail_val = _safe_int(metrics.get("tail_dropped_packets"))
            occ_val = _safe_int(metrics.get("peak_buffer_occupancy_percent"))

            if tail_val > 0 or occ_val > 0:
                hits += 1
            max_tail = max(max_tail, tail_val)
            max_occ = max(max_occ, occ_val)

        return hits, max_tail, max_occ

    # First, keep exact interface if it already works anywhere.
    exact_hits, exact_tail, exact_occ = _score_interface(current_interface)
    if exact_hits > 0:
        return current_interface

    # Then gather alias candidates from all reports.
    alias_candidates: Dict[str, Dict[str, int]] = {}

    for rep in all_reports:
        for c in _extract_all_queue_candidates(
            snapshot_report=rep,
            node=node,
            queue=queue,
        ):
            intf = str(c.get("interface") or "").strip()
            if not intf:
                continue

            entry = alias_candidates.setdefault(
                intf,
                {"hits": 0, "max_tail": 0, "max_occ": 0},
            )

            tail_val = _safe_int(c.get("tail_dropped_packets"))
            occ_val = _safe_int(c.get("peak_buffer_occupancy_percent"))

            if tail_val > 0 or occ_val > 0:
                entry["hits"] += 1
            entry["max_tail"] = max(entry["max_tail"], tail_val)
            entry["max_occ"] = max(entry["max_occ"], occ_val)

    if not alias_candidates:
        return current_interface

    ranked = sorted(
        alias_candidates.items(),
        key=lambda kv: (
            -kv[1]["hits"],
            abs(kv[1]["max_tail"] - preferred_tail_value) if preferred_tail_value > 0 else 0,
            -kv[1]["max_tail"],
            -kv[1]["max_occ"],
            kv[0],
        ),
    )

    best_interface = ranked[0][0]
    return best_interface or current_interface

def _resolve_telemetry_interface_alias_from_reports(
    *,
    reports: List[Dict[str, Any]],
    node: str,
    queue: int,
    preferred_tail_value: int,
) -> str | None:
    """
    Resolve interface alias using multiple recovery reports.
    Choose the interface whose tail-drop values are closest to the preferred UI value
    and which appears consistently across reports.
    """
    by_interface: Dict[str, Dict[str, Any]] = {}

    for report in reports:
        candidates = _extract_all_queue_candidates(
            snapshot_report=report,
            node=node,
            queue=queue,
        )
        for c in candidates:
            intf = str(c.get("interface"))
            entry = by_interface.setdefault(
                intf,
                {
                    "interface": intf,
                    "hits": 0,
                    "tail_values": [],
                    "max_tail": 0,
                    "max_occ": 0,
                },
            )
            tail_val = _safe_int(c.get("tail_dropped_packets"))
            occ_val = _safe_int(c.get("peak_buffer_occupancy_percent"))
            entry["hits"] += 1
            entry["tail_values"].append(tail_val)
            entry["max_tail"] = max(entry["max_tail"], tail_val)
            entry["max_occ"] = max(entry["max_occ"], occ_val)

    if not by_interface:
        return None

    ranked = sorted(
        by_interface.values(),
        key=lambda x: (
            -x["hits"],
            abs(x["max_tail"] - preferred_tail_value) if preferred_tail_value > 0 else 0,
            -x["max_tail"],
            -x["max_occ"],
            x["interface"],
        ),
    )
    return str(ranked[0]["interface"])

def evaluate_pre_event_cleanliness(pre_report: dict) -> dict:
    summary = pre_report.get("summary", {}) or {}
    hotspots = pre_report.get("hotspots", []) or []

    severe_hotspots = [
        h for h in hotspots
        if str(h.get("severity", "")).lower() in {"high", "critical"}
    ]

    total_tail_drop = 0
    max_occupancy = 0.0

    for h in hotspots:
        total_tail_drop += int(h.get("tail-drop-pkts", 0) or h.get("tail_dropped_packets", 0) or 0)
        occ = float(h.get("peak-buffer-occupancy-percent", 0) or h.get("peak_buffer_occupancy_percent", 0) or 0)
        max_occupancy = max(max_occupancy, occ)

    contaminated = bool(severe_hotspots) or total_tail_drop > 0

    reasons = []
    if severe_hotspots:
        reasons.append(f"severe_hotspots={len(severe_hotspots)}")
    if total_tail_drop > 0:
        reasons.append(f"tail_drop_present={total_tail_drop}")
    if max_occupancy >= 70:
        reasons.append(f"high_baseline_occupancy={max_occupancy}")

    return {
        "pass": not contaminated,
        "baseline_contaminated": contaminated,
        "severe_hotspot_count": len(severe_hotspots),
        "total_tail_drop": total_tail_drop,
        "max_occupancy": max_occupancy,
        "reasons": reasons,
    }





def snapshot_health(report: dict) -> str:
    ok_nodes = int(report.get("ok_nodes", 0) or 0)
    failed_nodes = int(report.get("failed_nodes", 0) or 0)

    if ok_nodes > 0 and failed_nodes == 0:
        return "ok"
    if ok_nodes > 0 and failed_nodes > 0:
        return "partial"
    return "failed"

def load_snapshot_health(path: str) -> dict:
    data = load_json(path)
    return {
        "path": path,
        "total_nodes": data.get("total_nodes", 0),
        "ok_nodes": data.get("ok_nodes", 0),
        "failed_nodes": data.get("failed_nodes", 0),
        "nodes": data.get("nodes", []),
    }


def derive_snapshot_status(snapshot_health: dict) -> str:
    ok_nodes = snapshot_health.get("ok_nodes", 0)
    failed_nodes = snapshot_health.get("failed_nodes", 0)

    if ok_nodes == 0:
        return "failed"
    if failed_nodes > 0:
        return "partial"
    return "ok"


def progress_log_path(run_id: str) -> str:
    return os.path.join("artifacts", "campaigns", run_id, "run_progress.log")


def load_json(path: str):
    with open(path, "r") as f:
        return json.load(f)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_file(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"expected file not found: {path}")


def telemetry_json_path(run_id: str, snapshot_name: str, profile: str) -> str:
    return os.path.join(
        "artifacts", "campaigns", run_id, "telemetry", f"{snapshot_name}_{profile}.json"
    )


def congestion_json_path(run_id: str, snapshot_name: str, profile: str) -> str:
    return os.path.join(
        "artifacts",
        "campaigns",
        run_id,
        "telemetry",
        f"{snapshot_name}_{profile}_congestion_analysis.json",
    )


def fabric_hotspot_json_path(run_id: str, snapshot_name: str, profile: str) -> str:
    return os.path.join(
        "artifacts",
        "campaigns",
        run_id,
        "telemetry",
        f"{snapshot_name}_{profile}_congestion_analysis_fabric_hotspots.json",
    )


def delta_json_path(run_id: str, snapshot_name: str, profile: str) -> str:
    return os.path.join(
        "artifacts",
        "campaigns",
        run_id,
        "telemetry",
        f"{snapshot_name}_{profile}_delta_analysis.json",
    )


def telemetry_diff_json_path(run_id: str, profile: str) -> str:
    return os.path.join(
        "artifacts", "campaigns", run_id, "telemetry", f"diff_{profile}.json"
    )


def telemetry_anomaly_json_path(run_id: str, profile: str) -> str:
    return os.path.join(
        "artifacts", "campaigns", run_id, "telemetry", f"anomaly_{profile}.json"
    )

def _start_ixia_traffic(
    *,
    ixia: IxiaClient,
    sid: int,
    traffic_start_mode: str,
    traffic_start_interval_ms: int,
    progress: ProgressLogger,
) -> None:
    interval_seconds = max(0.0, float(traffic_start_interval_ms) / 1000.0)

    if traffic_start_mode != "flow_by_flow":
        progress.info("Starting IXIA traffic all at once")
        ixia.traffic_start(session_id=sid)
        return

    progress.info(
        f"Starting IXIA traffic in flow_by_flow mode "
        f"(interval_ms={traffic_start_interval_ms})"
    )

    traffic_items = ixia.get_traffic_items(sid) or []
    progress.info(f"IXIA traffic item count before generate: {len(traffic_items)}")
    progress.info(f"IXIA traffic items before generate: {[x.get('name') for x in traffic_items]}")

    if not traffic_items:
        progress.info("No IXIA traffic items found; generating traffic")
        ixia.traffic_generate(session_id=sid)
        ixia.traffic_apply(session_id=sid)
        time.sleep(2)

        traffic_items = ixia.get_traffic_items(sid) or []
        progress.info(f"IXIA traffic item count after generate: {len(traffic_items)}")
        progress.info(f"IXIA traffic items after generate: {[x.get('name') for x in traffic_items]}")

    if not traffic_items:
        raise RuntimeError(
            "flow_by_flow requested, but IXIA session has no traffic items even after traffic_generate/apply"
        )

    seq_results = ixia.start_traffic_items_sequential(
        session_id=sid,
        interval_seconds=interval_seconds,
    )
    progress.info(f"Sequential IXIA start results: {seq_results}")


def traffic_dir(run_id: str) -> str:
    return os.path.join("artifacts", "campaigns", run_id, "traffic")


def traffic_json_path(run_id: str, name: str) -> str:
    return os.path.join(traffic_dir(run_id), f"{name}.json")


def write_final_report(
    *,
    run_id: str,
    intent_name: str,
    src: str,
    dst: str,
    profile: str,
    nodes: str,
    topology_path: str,
) -> str:
    running_congestion_path = congestion_json_path(run_id, "running", profile)
    running_fabric_path = fabric_hotspot_json_path(run_id, "running", profile)
    running_delta_path = delta_json_path(run_id, "running", profile)

    congestion = load_json(running_congestion_path)
    fabric = load_json(running_fabric_path)
    delta = load_json(running_delta_path)
    topology = load_json(topology_path)

    from controller.traffic_intent_rca_ecmp import (
        load_hotspots,
        build_corridor,
        correlate_hotspots,
        classify_cause,
    )

    intent_rca_error = None
    try:
        hotspots = load_hotspots(running_fabric_path)
        corridor, src_leaf, dst_leaf = build_corridor(topology, src, dst)
        matched = correlate_hotspots(corridor, hotspots)
        top = matched[0] if matched else None
    except Exception as exc:
        intent_rca_error = str(exc)
        hotspots = []
        corridor = []
        src_leaf = None
        dst_leaf = None
        matched = []
        top = None

    intent_rca = {
        "src_leaf": src_leaf,
        "dst_leaf": dst_leaf,
        "corridor": [{"node": n, "interface": i} for n, i in corridor],
        "matched_hotspots": matched[:20],
        "top_path_hotspot": top,
        "rca_summary": None,
        "status": "failed" if intent_rca_error else "ok",
        "error": intent_rca_error,
    }

    if top:
        intent_rca["rca_summary"] = {
            "node": top.get("node"),
            "interface": top.get("interface"),
            "queue": top.get("queue"),
            "severity": top.get("severity"),
            "score": top.get("score"),
            "probable_cause": top.get("probable_cause"),
            "intent_cause": classify_cause(top),
            "signals": top.get("signals", {}),
        }

    report = {
        "generated_at": utc_now_iso(),
        "run_id": run_id,
        "intent_name": intent_name,
        "src": src,
        "dst": dst,
        "profile": profile,
        "nodes": [n.strip() for n in nodes.split(",") if n.strip()],
        "status": {
            "pre_snapshot": "ok",
            "running_snapshot": "ok",
            "post_snapshot": "ok",
            "congestion_analysis": "ok",
            "fabric_ranking": "ok",
            "delta_analysis": "ok",
            "intent_rca": "ok",
        },
        "files": {
            "pre_telemetry": telemetry_json_path(run_id, "pre", profile),
            "running_telemetry": telemetry_json_path(run_id, "running", profile),
            "post_telemetry": telemetry_json_path(run_id, "post", profile),
            "running_congestion": running_congestion_path,
            "running_fabric_hotspots": running_fabric_path,
            "running_delta": running_delta_path,
        },
        "congestion_summary": {
            "total_hotspots": congestion.get("total_hotspots", 0),
            "top_hotspot": (congestion.get("hotspots") or [None])[0],
        },
        "fabric_summary": {
            "severity_counts": fabric.get("severity_counts", {}),
            "top_queues": fabric.get("top_queues", [])[:10],
            "top_interfaces": fabric.get("top_interfaces", [])[:10],
            "top_nodes": fabric.get("top_nodes", [])[:10],
        },
        "delta_summary": {
            "top_deltas": delta[:10] if isinstance(delta, list) else delta,
        },
        "intent_rca": intent_rca,
    }

    out_path = os.path.join("artifacts", "campaigns", run_id, "rca_final_report.json")
    #with open(out_path, "w") as f:
    #    json.dump(report, f, indent=2, sort_keys=False)
    atomic_write_json(out_path, report, indent=2, sort_keys=False)

    return out_path


def write_summary(
    *,
    run_id: str,
    intent_name: str,
    src: str,
    dst: str,
    profile: str,
    nodes: str,
    out_path: str,
    stress_orchestrator_report: str | None = None,
    status: dict | None = None,
    files_override: dict | None = None,
    intent_rca_status: str = "ok",
    baseline_window: int | None = None,
    running_decay: int | None = None,
    settle_gap: int | None = None,
    post_window: int | None = None,
) -> None:
    files = {
        # NEW explicit phase-aware naming
        "baseline_telemetry": telemetry_json_path(run_id, "pre", profile),
        "running_telemetry": telemetry_json_path(run_id, "running", profile),
        "post_telemetry": telemetry_json_path(run_id, "post", profile),

        # LEGACY compatibility
        "pre_telemetry": telemetry_json_path(run_id, "pre", profile),

        # Existing derived artifacts
        "running_congestion": congestion_json_path(run_id, "running", profile),
        "running_fabric_hotspots": fabric_hotspot_json_path(run_id, "running", profile),
        "running_delta": delta_json_path(run_id, "running", profile),
    }

    if stress_orchestrator_report:
        files["stress_orchestrator_report"] = stress_orchestrator_report

    if files_override:
        files.update(files_override)

    data = {
        "generated_at": utc_now_iso(),
        "run_id": run_id,
        "intent_name": intent_name,
        "src": src,
        "dst": dst,
        "profile": profile,
        "nodes": nodes,
        "files": files,
        "status": status or {"intent_rca": intent_rca_status},
        "phase_timeline": {
            "baseline_window": baseline_window,
            "running_decay": running_decay,
            "settle_gap": settle_gap,
            "post_window": post_window,
            "phase_windows": (files_override or {}).get("phase_windows"),
        },
        "pre_event_cleanliness": (files_override or {}).get("pre_event_cleanliness"),
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    #with open(out_path, "w") as f:
    #    json.dump(data, f, indent=2, sort_keys=False)
    atomic_write_json(out_path, data, indent=2, sort_keys=False)



def collect_pre_window_samples(
    *,
    run_id: str,
    profile: str,
    nodes: str,
    timeout: int,
    topology_path: str,
    baseline_window: int,
    sample_count: int = 3,
    progress: ProgressLogger | None = None,
) -> list[str]:
    sample_count = max(1, int(sample_count))
    baseline_window = max(1, int(baseline_window))

    pre_sample_paths: list[str] = []

    if sample_count == 1:
        sample_offsets = [baseline_window]
    else:
        interval = baseline_window / float(sample_count - 1)
        sample_offsets = [round(i * interval) for i in range(sample_count)]

    if progress:
        progress.info(
            f"[PRE-SAMPLING] Collecting {sample_count} pre samples over baseline_window={baseline_window}s "
            f"offsets={sample_offsets}"
        )

    started_at = time.time()

    for i, target_offset in enumerate(sample_offsets):
        elapsed = time.time() - started_at
        sleep_needed = max(0.0, target_offset - elapsed)

        if sleep_needed > 0:
            time.sleep(sleep_needed)

        snapshot_name = f"pre_sample_{i + 1}"

        if progress:
            progress.info(
                f"[PRE-SAMPLING] Collecting {snapshot_name} at offset={target_offset}s"
            )

        collect_snapshot(
            run_id=run_id,
            snapshot_name=snapshot_name,
            profile=profile,
            nodes=nodes,
            timeout=timeout,
            topology_path=topology_path,
        )

        sample_path = telemetry_json_path(run_id, snapshot_name, profile)
        ensure_file(sample_path)
        pre_sample_paths.append(sample_path)

    return pre_sample_paths

def collect_post_window_samples(
    *,
    run_id: str,
    profile: str,
    nodes: str,
    timeout: int,
    topology_path: str,
    post_window: int,
    sample_count: int = 3,
    progress: ProgressLogger | None = None,
) -> list[str]:
    sample_count = max(1, int(sample_count))
    post_window = max(1, int(post_window))

    if sample_count == 1:
        sample_offsets = [post_window]
    else:
        interval = post_window / float(sample_count - 1)
        sample_offsets = [round(i * interval) for i in range(sample_count)]

    post_sample_paths: list[str] = []

    if progress:
        progress.info(
            f"[POST-SAMPLING] Collecting {sample_count} post samples over post_window={post_window}s "
            f"offsets={sample_offsets}"
        )

    started_at = time.time()

    for i, target_offset in enumerate(sample_offsets):
        elapsed = time.time() - started_at
        sleep_needed = max(0.0, target_offset - elapsed)

        if sleep_needed > 0:
            time.sleep(sleep_needed)

        snapshot_name = "post" if i == sample_count - 1 else f"recover_{i + 1}"

        if progress:
            progress.info(
                f"[POST-SAMPLING] Collecting {snapshot_name} at offset={target_offset}s"
            )

        collect_snapshot(
            run_id=run_id,
            snapshot_name=snapshot_name,
            profile=profile,
            nodes=nodes,
            timeout=timeout,
            topology_path=topology_path,
        )

        sample_path = telemetry_json_path(run_id, snapshot_name, profile)
        ensure_file(sample_path)
        post_sample_paths.append(sample_path)

    return post_sample_paths

def collect_targeted_window_samples(
    *,
    run_id: str,
    profile: str,
    nodes: str,
    timeout: int,
    topology_path: str,
    total_window: int,
    sample_count: int,
    snapshot_prefix: str,
    bounced_node: str,
    bounced_interface: str,
    progress: ProgressLogger | None = None,
) -> list[str]:
    sample_count = max(1, int(sample_count))
    total_window = max(1, int(total_window))

    if sample_count == 1:
        sample_offsets = [total_window]
    else:
        interval = total_window / float(sample_count - 1)
        sample_offsets = [round(i * interval) for i in range(sample_count)]

    sample_paths: list[str] = []
    started_at = time.time()

    if progress:
        progress.info(
            f"[TARGETED-SAMPLING] prefix={snapshot_prefix} count={sample_count} "
            f"window={total_window}s offsets={sample_offsets}"
        )

    for i, target_offset in enumerate(sample_offsets):
        elapsed = time.time() - started_at
        sleep_needed = max(0.0, target_offset - elapsed)

        if sleep_needed > 0:
            time.sleep(sleep_needed)

        snapshot_name = f"{snapshot_prefix}_{i + 1}"

        if progress:
            progress.info(
                f"[TARGETED-SAMPLING] Collecting {snapshot_name} at offset={target_offset}s"
            )

        collect_recovery_snapshot(
            run_id=run_id,
            snapshot_name=snapshot_name,
            profile=profile,
            nodes=nodes,
            timeout=timeout,
            topology_path=topology_path,
            bounced_node=bounced_node,
            bounced_interface=bounced_interface,
        )

        sample_path = telemetry_json_path(run_id, snapshot_name, profile)
        ensure_file(sample_path)
        sample_paths.append(sample_path)

    return sample_paths



def collect_snapshot(
    *,
    run_id: str,
    snapshot_name: str,
    profile: str,
    nodes: str,
    timeout: int,
    topology_path: str,
) -> None:
    from controller.telemetry_monitor import (
        load_catalog,
        get_profile_paths,
        load_inventory,
        parse_nodes,
        collect_snapshot as telemetry_collect_snapshot,
        build_output_paths,
        write_json,
        write_text,
        render_text_report,
    )

    from controller.telemetry_monitor import DEFAULT_CATALOG, DEFAULT_INVENTORY, DEFAULT_TELEMETRY_SERVER

    catalog = load_catalog(DEFAULT_CATALOG)
    paths = get_profile_paths(catalog, profile)
    inventory = load_inventory(DEFAULT_INVENTORY)
    node_list = parse_nodes(nodes)

    report = telemetry_collect_snapshot(
        telemetry_server=DEFAULT_TELEMETRY_SERVER,
        ssh_user="root",
        nodes=node_list,
        paths=paths,
        inventory=inventory,
        timeout=timeout,
        snapshot_name=snapshot_name,
        profile=profile,
        source_type="campaign",
        run_id=run_id,
        default_gnmi_port=60061,
        topology_path=topology_path,
    )
    json_path, txt_path = build_output_paths(
        run_id=run_id,
        snapshot_name=snapshot_name,
        profile=profile,
    )

    write_json(json_path, report)
    write_text(txt_path, render_text_report(report))

    print(f"Telemetry JSON report : {json_path}")
    print(f"Telemetry text report : {txt_path}")


def run_congestion_analysis(run_id: str, profile: str) -> None:
    from controller.congestion_analyzer import (
        load_report,
        analyze_congestion,
        build_output_paths,
        write_json,
        write_text,
        render_text_summary,
    )

    input_path = telemetry_json_path(run_id, "running", profile)
    report = load_report(input_path)
    result = analyze_congestion(report)
    json_out, txt_out = build_output_paths(input_path)
    write_json(json_out, result)
    write_text(txt_out, render_text_summary(result))
    print(f"Congestion JSON report : {json_out}")
    print(f"Congestion text report : {txt_out}")


def run_fabric_ranker(run_id: str, profile: str, top_n: int) -> None:
    from controller.fabric_hotspot_ranker import (
        load_json,
        rank_fabric_hotspots,
        build_output_paths,
        write_json,
        write_text,
        render_text,
    )

    input_path = congestion_json_path(run_id, "running", profile)
    analysis = load_json(input_path)
    result = rank_fabric_hotspots(analysis, top_n=top_n)
    json_out, txt_out = build_output_paths(input_path)
    write_json(json_out, result)
    write_text(txt_out, render_text(result))
    print(f"Fabric hotspot JSON report : {json_out}")
    print(f"Fabric hotspot text report : {txt_out}")


def run_delta_analysis(run_id: str, profile: str, top_n: int) -> None:
    from controller.congestion_delta_analyzer import (
        load_snapshot,
        build_metric_map,
        compute_delta,
        rank_hotspots,
        write_report,
    )

    pre = load_snapshot(telemetry_json_path(run_id, "pre", profile))
    running = load_snapshot(telemetry_json_path(run_id, "running", profile))
    post = load_snapshot(telemetry_json_path(run_id, "post", profile))

    pre_map = build_metric_map(pre)
    run_map = build_metric_map(running)
    post_map = build_metric_map(post)

    delta_records = compute_delta(pre_map, run_map, post_map)
    ranked = rank_hotspots(delta_records)

    out_path = delta_json_path(run_id, "running", profile)
    write_report(out_path, ranked, top_n)


def run_intent_rca(run_id: str, profile: str, topology: str, src: str, dst: str, intent_name: str) -> None:
    from controller.traffic_intent_rca_ecmp import (
        load_json,
        load_hotspots,
        build_corridor,
        correlate_hotspots,
        render,
    )

    topology_data = load_json(topology)
    hotspots = load_hotspots(fabric_hotspot_json_path(run_id, "running", profile))
    corridor, src_leaf, dst_leaf = build_corridor(topology_data, src, dst)
    matched = correlate_hotspots(corridor, hotspots)
    render(intent_name, src_leaf, dst_leaf, corridor, matched)


def run_telemetry_diff_and_analyzer(run_id: str, profile: str) -> dict:
    outputs = {}
    try:
        from controller.telemetry_diff import compare_snapshots, write_json as diff_write_json, write_text as diff_write_text, render_text_report as diff_render_text_report
        pre_snapshot = load_json(telemetry_json_path(run_id, "pre", profile))
        post_snapshot = load_json(telemetry_json_path(run_id, "post", profile))
        diff_report = compare_snapshots(pre_snapshot, post_snapshot)
        diff_report["pre_snapshot"] = telemetry_json_path(run_id, "pre", profile)
        diff_report["post_snapshot"] = telemetry_json_path(run_id, "post", profile)
        diff_json = telemetry_diff_json_path(run_id, profile)
        diff_txt = diff_json.replace(".json", ".txt")
        diff_write_json(diff_json, diff_report)
        diff_write_text(diff_txt, diff_render_text_report(diff_report))
        outputs["telemetry_diff"] = diff_json
        print(f"Telemetry diff JSON report : {diff_json}")
    except Exception as exc:
        outputs["telemetry_diff_error"] = str(exc)

    try:
        from controller.telemetry_analyzer import (
            detect_anomalies,
            summarize_anomalies,
            build_entity_rollup,
            write_json as ta_write_json,
            write_text as ta_write_text,
            render_text_report as ta_render_text_report,
        )
        pre_snapshot = load_json(telemetry_json_path(run_id, "pre", profile))
        post_snapshot = load_json(telemetry_json_path(run_id, "post", profile))
        anomalies = detect_anomalies(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            spike_ratio=5.0,
            gauge_delta_threshold=3.0,
        )
        summary = summarize_anomalies(anomalies)
        analyzer_report = {
            "pre_snapshot": telemetry_json_path(run_id, "pre", profile),
            "post_snapshot": telemetry_json_path(run_id, "post", profile),
            "summary": summary,
            "entity_rollup": build_entity_rollup(anomalies),
            "anomalies": anomalies,
        }
        anomaly_json = telemetry_anomaly_json_path(run_id, profile)
        anomaly_txt = anomaly_json.replace(".json", ".txt")
        ta_write_json(anomaly_json, analyzer_report)
        ta_write_text(anomaly_txt, ta_render_text_report(summary, anomalies))
        outputs["telemetry_analyzer"] = anomaly_json
        print(f"Telemetry anomaly JSON report : {anomaly_json}")
    except Exception as exc:
        outputs["telemetry_analyzer_error"] = str(exc)

    return outputs


def run_roce_and_traffic_evidence(
    *,
    run_id: str,
    timeout: int,
    ixia_inventory: str,
    session_id: int | None,
    enable_live_monitor: bool,
    live_monitor_iterations: int,
    live_monitor_interval: int,
    enable_port_stats: bool,
) -> dict:
    outputs = {}

    def safe_step(name, func):
        try:
            path = func()
            outputs[name] = path
        except Exception as exc:
            outputs[f"{name}_error"] = str(exc)

    safe_step(
        "rocev2_pre",
        lambda: _run_roce_stats(run_id=run_id, snapshot_name="rocev2_pre", timeout=timeout, ixia_inventory=ixia_inventory, session_id=session_id),
    )
    safe_step(
        "rocev2_post",
        lambda: _run_roce_stats(run_id=run_id, snapshot_name="rocev2_post", timeout=timeout, ixia_inventory=ixia_inventory, session_id=session_id),
    )

    pre_roce = outputs.get("rocev2_pre")
    post_roce = outputs.get("rocev2_post")
    if pre_roce and post_roce:
        safe_step(
            "rocev2_verdict",
            lambda: _run_roce_verifier(run_id=run_id, pre_path=pre_roce, post_path=post_roce),
        )
        verdict = outputs.get("rocev2_verdict")
        if verdict:
            safe_step(
                "rocev2_deep_inspection",
                lambda: _run_roce_deep(run_id=run_id, pre_path=pre_roce, post_path=post_roce, verdict_path=verdict),
            )
            deep = outputs.get("rocev2_deep_inspection")
            if deep:
                safe_step(
                    "rocev2_hotspot_report",
                    lambda: _run_roce_hotspot(run_id=run_id, deep_path=deep),
                )

    if enable_live_monitor:
        safe_step(
            "ixia_live_monitor",
            lambda: _run_ixia_live_monitor(
                run_id=run_id,
                timeout=timeout,
                ixia_inventory=ixia_inventory,
                session_id=session_id,
                iterations=live_monitor_iterations,
                poll_interval=live_monitor_interval,
            ),
        )

    if enable_port_stats:
        safe_step(
            "ixia_port_pre",
            lambda: _run_ixia_port_stats(run_id=run_id, snapshot_name="ixia_port_pre", timeout=timeout, ixia_inventory=ixia_inventory, session_id=session_id),
        )
        safe_step(
            "ixia_port_post",
            lambda: _run_ixia_port_stats(run_id=run_id, snapshot_name="ixia_port_post", timeout=timeout, ixia_inventory=ixia_inventory, session_id=session_id),
        )
        pre_port = outputs.get("ixia_port_pre")
        post_port = outputs.get("ixia_port_post")
        if pre_port and post_port:
            safe_step(
                "traffic_verifier",
                lambda: _run_traffic_verifier(run_id=run_id, pre_path=pre_port, post_path=post_port),
            )

    deep_path = outputs.get("rocev2_deep_inspection")
    verdict_path = outputs.get("rocev2_verdict")
    hotspot_path = outputs.get("rocev2_hotspot_report")
    if verdict_path and deep_path and hotspot_path:
        safe_step(
            "congestion_inspection",
            lambda: _run_congestion_inspector(
                run_id=run_id,
                verdict_path=verdict_path,
                deep_path=deep_path,
                hotspot_path=hotspot_path,
                pre_port_stats=outputs.get("ixia_port_pre"),
                post_port_stats=outputs.get("ixia_port_post"),
            ),
        )
        congestion_path = outputs.get("congestion_inspection")
        if congestion_path:
            safe_step(
                "root_cause_correlation",
                lambda: _run_root_cause_correlator(
                    run_id=run_id,
                    congestion_path=congestion_path,
                    ixia_inventory=ixia_inventory,
                ),
            )

    root_cause = outputs.get("root_cause_correlation")
    telemetry_anomaly = telemetry_anomaly_json_path(run_id, DEFAULT_PROFILE)
    if root_cause and os.path.exists(telemetry_json_path(run_id, "post", DEFAULT_PROFILE)):
        pass

    return outputs


def _run_roce_stats(
    *,
    run_id: str,
    snapshot_name: str,
    timeout: int,
    ixia_inventory: str,
    session_id: int | None,
) -> str:
    from controller.ixia_rocev2_stats import (
        collect_rocev2_stats,
        output_paths,
        build_text_report,
    )

    report = collect_rocev2_stats(
        source_type="campaign",
        run_id=run_id,
        snapshot_name=snapshot_name,
        inventory_path=ixia_inventory,
        api_server=None,
        session_id=session_id,
        view_name="RoCEv2 Flow Statistics",
    )

    out = output_paths("campaign", run_id, snapshot_name)
    #with open(out["json"], "w") as f:
    #    json.dump(report, f, indent=2)
    atomic_write_json(out["json"], report, indent=2)

    with open(out["txt"], "w") as f:
        f.write(build_text_report(report))


    return out["json"]

def _run_roce_verifier(*, run_id: str, pre_path: str, post_path: str) -> str:
    from controller.rocev2_verifier import (
        load_json as r_load_json,
        evaluate_single_snapshot,
        evaluate_pre_post,
        summarize_findings,
        build_rx_port_rollup,
        overall_verdict,
        write_json,
        write_text,
        render_text_report,
        default_output_paths,
    )
    pre_snapshot = r_load_json(pre_path)
    post_snapshot = r_load_json(post_path)
    findings = []
    findings.extend(evaluate_single_snapshot(
        snapshot=post_snapshot,
        delta_warn_threshold=100000,
        delta_critical_threshold=10000000,
        retx_warn_threshold=1,
        retx_critical_threshold=1000000,
        seqerr_warn_threshold=1,
        seqerr_critical_threshold=1000000,
        latency_warn_ns=10000,
        latency_critical_ns=100000,
    ))
    findings.extend(evaluate_pre_post(
        pre_snapshot=pre_snapshot,
        post_snapshot=post_snapshot,
        delta_increase_warn=100000,
        retx_increase_warn=1000,
        seqerror_increase_warn=1000,
        latency_increase_warn_ns=5000,
    ))
    summary = summarize_findings(findings)
    rx_rollup = build_rx_port_rollup(findings)
    verdict = overall_verdict(summary)
    report = {
        "source_type": "campaign",
        "run_id": run_id,
        "pre_snapshot": pre_path,
        "post_snapshot": post_path,
        "verdict": verdict,
        "summary": summary,
        "rx_port_rollup": rx_rollup,
        "findings": findings,
    }
    out_json, out_txt = default_output_paths("campaign", run_id)
    write_json(out_json, report)
    write_text(out_txt, render_text_report(report))
    return out_json


def _run_roce_deep(*, run_id: str, pre_path: str, post_path: str, verdict_path: str) -> str:
    return _run_roce_deep_inspection(
        run_id=run_id,
        pre_path=pre_path,
        post_path=post_path,
        verdict_path=verdict_path,
    )

def _run_roce_hotspot(*, run_id: str, deep_path: str) -> str:
    from controller.rocev2_hotspot_report import load, build_hotspot_report, output_paths, render_text
    deep = load(deep_path)
    report = build_hotspot_report(deep)
    json_path, txt_path = output_paths("campaign", run_id)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    #with open(json_path, "w") as f:
    #    json.dump(report, f, indent=2)
    atomic_write_json(json_path, report, indent=2)
    with open(txt_path, "w") as f:
        f.write(render_text(report, run_id))
    return json_path

def _run_ixia_live_monitor(
    *,
    run_id: str,
    timeout: int,
    ixia_inventory: str,
    session_id: int | None,
    iterations: int,
    poll_interval: int,
) -> str:
    from controller.ixia_live_monitor import (
        output_paths,
        utc_now_iso,
        get_view_rows,
        analyze_rocev2,
        analyze_port_stats,
        detect_alerts,
        render_text,
    )
    from controller.ixia_client import IxiaClient

    inventory = load_json_file(ixia_inventory)
    api_server = inventory.get("ixnetwork_api_server")
    if not api_server:
        raise RuntimeError("ixnetwork_api_server not found in ixia inventory")

    client = IxiaClient(
        api_server=api_server,
        inventory_path=ixia_inventory,
        timeout=max(timeout, 120),
        verify_tls=False,
    )
    sid = client.resolve_session_id(session_id)

    report = {
        "run_id": run_id,
        "source_type": "campaign",
        "snapshot_name": "live",
        "api_server": api_server,
        "session_id": sid,
        "poll_interval_sec": poll_interval,
        "live_requested": True,
        "live_available": False,
        "live_source": None,
        "live_error": None,
        "iterations": [],
    }

    for i in range(1, iterations + 1):
        ts = utc_now_iso()

        rocev2_rows = []
        rocev2_view_used = None
        rocev2_error = None

        # Lightweight mode: prefer per-port summary view only
        for view_name in get_lightweight_roce_view_candidates():
            try:
                rocev2_rows = get_view_rows(client, sid, view_name, page_size=10)
                if rocev2_rows:
                    rocev2_view_used = view_name
                    break
            except Exception as exc:
                rocev2_error = str(exc)
                continue

        # Port Statistics is optional and skipped by default for live mode
        port_rows = []
        port_error = "Port Statistics skipped in live mode"

        rocev2_analysis = analyze_rocev2(rocev2_rows, 10)
        port_analysis = analyze_port_stats(port_rows, 10)

        if rocev2_rows:
            report["live_available"] = True
            report["live_source"] = rocev2_view_used
        elif rocev2_error:
            report["live_error"] = rocev2_error

        alerts = detect_alerts(
            rocev2_analysis=rocev2_analysis,
            port_analysis=port_analysis,
            delta_alert_threshold=10000000,
            retx_alert_threshold=1000000,
            seqerror_alert_threshold=1000000,
            latency_alert_threshold_ns=100000,
        )

        report["iterations"].append(
            {
                "iteration": i,
                "timestamp": ts,
                "rocev2_view_used": rocev2_view_used,
                "rocev2_error": rocev2_error,
                "port_error": port_error,
                "rocev2": rocev2_analysis,
                "ports": port_analysis,
                "alerts": alerts,
            }
        )

        if i < iterations:
            time.sleep(poll_interval)

    if not report["live_available"] and not report["live_error"]:
        report["live_error"] = "RoCE live statistics returned no usable rows"

    out = output_paths("campaign", run_id, "live")
    #with open(out["json"], "w") as f:
    #    json.dump(report, f, indent=2)
    atomic_write_json(out["json"], report, indent=2)
    with open(out["txt"], "w") as f:
        f.write(render_text(report))

    return out["json"]


def _run_ixia_port_stats(
    *,
    run_id: str,
    snapshot_name: str,
    timeout: int,
    ixia_inventory: str,
    session_id: int | None,
) -> str:
    import time

    from controller.ixia_stats_collector import (
        snapshot_paths,
        normalize_port_stats,
        build_summary,
        render_text_report,
    )
    from controller.ixia_client import IxiaClient

    inventory = load_json_file(ixia_inventory)
    api_server = inventory.get("ixnetwork_api_server")
    if not api_server:
        raise RuntimeError("ixnetwork_api_server not found in ixia inventory")

    # Port Statistics can be slow on busy sessions.
    # Use a safer floor so caller-provided low timeouts do not make this too fragile.
    effective_timeout = max(int(timeout or 0), 90)

    last_exc = None
    retries = 2

    for attempt in range(1, retries + 1):
        try:
            client = IxiaClient(
                api_server=api_server,
                inventory_path=ixia_inventory,
                timeout=effective_timeout,
                verify_tls=False,
            )
            sid = client.resolve_session_id(session_id)

            port_stats = client.get_port_statistics(sid)
            page = port_stats.get("page", {}) or {}

            normalized_ports = normalize_port_stats(page, client.get_inventory_ports())
            summary = build_summary(normalized_ports)

            report = {
                "collected_at": utc_now_iso(),
                "api_server": api_server,
                "session_id": sid,
                "snapshot_name": snapshot_name,
                "source_type": "campaign",
                "summary": summary,
                "column_captions": page.get("columnCaptions", []),
                "normalized_ports": normalized_ports,
                "raw_statistics_view": port_stats,
                "collection_status": "success",
                "timeout_used_seconds": effective_timeout,
                "attempt": attempt,
            }

            out = snapshot_paths("campaign", run_id, snapshot_name)
            #with open(out["json"], "w") as f:
            #    json.dump(report, f, indent=2)
            atomic_write_json(out["json"], report, indent=2)
            with open(out["txt"], "w") as f:
                f.write(render_text_report(report))

            return out["json"]

        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(3)
            else:
                raise RuntimeError(
                    f"ixia port statistics collection failed after {retries} attempts "
                    f"(timeout={effective_timeout}s): {exc}"
                ) from exc


def _run_traffic_verifier(*, run_id: str, pre_path: str, post_path: str) -> str:
    from controller.traffic_verifier import (
        load_json as t_load_json,
        compare_single_snapshot,
        compare_pre_post,
        summarize_findings,
        build_port_rollup,
        overall_verdict,
        write_json,
        write_text,
        render_text_report,
        default_output_paths,
    )
    pre_snapshot = t_load_json(pre_path)
    post_snapshot = t_load_json(post_path)
    findings = []
    findings.extend(compare_single_snapshot(
        snapshot=post_snapshot,
        zero_rx_min_tx_rate=1000,
        low_rx_ratio_threshold=0.80,
        idle_tx_rate_threshold=10,
        pre_fec_ber_threshold=1e-12,
        fec_frame_loss_threshold=0.0,
    ))
    findings.extend(compare_pre_post(
        pre_snapshot=pre_snapshot,
        post_snapshot=post_snapshot,
        post_drop_ratio_threshold=0.50,
        rate_drop_min_pre_rate=1000,
    ))
    summary = summarize_findings(findings)
    rollup = build_port_rollup(findings)
    verdict = overall_verdict(summary)
    report = {
        "source_type": "campaign",
        "run_id": run_id,
        "pre_snapshot": pre_path,
        "post_snapshot": post_path,
        "verdict": verdict,
        "summary": summary,
        "port_rollup": rollup,
        "findings": findings,
    }
    out_json, out_txt = default_output_paths("campaign", run_id)
    write_json(out_json, report)
    write_text(out_txt, render_text_report(report))
    return out_json


def _run_congestion_inspector(*, run_id: str, verdict_path: str, deep_path: str, hotspot_path: str, pre_port_stats: str | None, post_port_stats: str | None) -> str:
    from controller.congestion_inspector import (
        load_json as c_load_json,
        correlate,
        build_conclusion,
        write_json,
        write_text,
        render_text,
        default_output_paths,
    )
    verdict = c_load_json(verdict_path)
    deep = c_load_json(deep_path)
    hotspot = c_load_json(hotspot_path)
    pre_ps = c_load_json(pre_port_stats) if pre_port_stats else {}
    post_ps = c_load_json(post_port_stats) if post_port_stats else {}
    report = correlate(
        verdict=verdict,
        deep=deep,
        hotspot=hotspot,
        pre_port_stats_raw=pre_ps,
        post_port_stats_raw=post_ps,
    )
    report["conclusion"] = build_conclusion(report)
    outputs = default_output_paths("campaign", run_id)
    write_json(outputs["json"], report)
    write_text(outputs["txt"], render_text(report))
    return outputs["json"]


def _run_root_cause_correlator(*, run_id: str, congestion_path: str, ixia_inventory: str) -> str:
    from controller.root_cause_correlator import (
        load_json as r_load_json,
        build_ixia_port_mapping,
        map_hotspots_to_dut,
        correlate_problem_flows,
        build_evidence,
        build_summary,
        build_conclusion,
        write_json,
        write_text,
        render_text,
        default_output_paths,
    )
    congestion = r_load_json(congestion_path)
    inventory = r_load_json(ixia_inventory)
    port_map = build_ixia_port_mapping(inventory)
    mapped_hotspots = map_hotspots_to_dut(congestion, port_map)
    mapped_flows = correlate_problem_flows(congestion, port_map)
    hotspots_with_evidence = []
    for item in mapped_hotspots:
        enriched = dict(item)
        enriched["evidence"] = build_evidence(item)
        hotspots_with_evidence.append(enriched)
    summary = build_summary(mapped_hotspots, mapped_flows)
    conclusion = build_conclusion(summary)
    report = {
        "summary": summary,
        "hotspots_with_evidence": hotspots_with_evidence,
        "port_mapping_used": port_map,
        "conclusion": conclusion,
    }
    outputs = default_output_paths("campaign", run_id)
    write_json(outputs["json"], report)
    write_text(outputs["txt"], render_text(report))
    return outputs["json"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run end-to-end RCA case with embedded IXIA traffic control.", allow_abbrev=False)

    parser.add_argument("--run-id", required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--intent-name", required=True)
    parser.add_argument("--nodes", required=True)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--top-n", type=int, default=10)

    parser.add_argument("--ixia-inventory", default=DEFAULT_IXIA_INVENTORY)
    parser.add_argument("--ixia-session-id", type=int, default=None)
    parser.add_argument("--running-wait", type=int, default=15)
    parser.add_argument("--post-wait", type=int, default=300)
    parser.add_argument("--resume-after-post", action="store_true")
    parser.add_argument(
        "--stress-orchestrator-report",
        help="Optional path to stress_orchestrator_report.json for trigger/event correlation",
    )

    parser.add_argument("--enable-live-monitor", action="store_true")
    parser.add_argument("--live-monitor-iterations", type=int, default=6)
    parser.add_argument("--live-monitor-interval", type=int, default=5)
    parser.add_argument("--enable-port-stats", action="store_true")

    parser.add_argument("--baseline-window", type=int, default=300)
    parser.add_argument("--running-decay", type=int, default=15)
    parser.add_argument("--settle-gap", type=int, default=30)
    parser.add_argument("--post-window", type=int, default=300)
    parser.add_argument("--post-sample-count", type=int, default=10)
    parser.add_argument("--post-sample-interval", type=int, default=30)
    parser.add_argument("--phase-profile", default="hotspot_congestion_qmon_phase")
    parser.add_argument(
        "--node",
        help="Bounced node for single-interface ECMP recovery analysis.",
    )
    parser.add_argument(
        "--interface",
        help="Bounced interface for single-interface ECMP recovery analysis.",
    )

    parser.add_argument("--traffic-start-mode", default="all_at_once",
                    choices=["all_at_once", "flow_by_flow", "batch"])
    parser.add_argument("--ecmp-spec-tolerance-pct", type=float, default=15.0)
    parser.add_argument(
        "--traffic-start-interval-ms",
        type=int,
        default=100,
        help="Delay between flow starts (flow-by-flow mode)",
    )

    parser.add_argument(
        "--ecmp-analysis-node",
        default=None,
        help="Optional node to use for ECMP recovery analysis. Useful when stress target is not the ECMP decision node.",
    )

    parser.add_argument(
        "--ecmp-analysis-interface",
        default=None,
        help="Optional interface to use for ECMP recovery analysis when overriding the stress target.",
    )

    parser.add_argument(
        "--ecmp-analysis-targets",
        default=None,
        help=(
            "Comma-separated ECMP analysis targets, e.g. "
            "leaf1:et-0/0/11:0,leaf1:et-0/0/40:0. "
            "Use when stress target differs from ECMP decision node."
        ),
    )

    args = parser.parse_args()

    args.baseline_window = max(1, int(args.baseline_window))
    args.running_decay = max(0, int(args.running_decay))
    args.settle_gap = max(0, int(args.settle_gap))
    args.post_window = max(1, int(args.post_window))
    args.post_wait = max(1, int(args.post_wait))
    args.post_sample_count = max(1, int(args.post_sample_count))
    args.post_sample_interval = max(1, int(args.post_sample_interval))

    sampled_post_duration = args.post_sample_count * args.post_sample_interval
    if sampled_post_duration > args.post_window:
        args.post_window = sampled_post_duration

    if args.post_wait < args.post_window:
        args.post_wait = args.post_window

    return args



def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except Exception:
        return 0


def _extract_hotspot_entities_from_ui(ui_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _collect(items: List[Dict[str, Any]] | None) -> None:
        for item in items or []:
            entity_id = str(item.get("entity_id") or "").strip()
            if not entity_id or entity_id in seen:
                continue

            node = item.get("node")
            interface = item.get("interface")
            queue = item.get("queue")

            parsed_node = None
            parsed_interface = None
            parsed_queue = None

            parts = entity_id.split("|")
            if len(parts) >= 3:
                parsed_node = parts[0].strip() or None
                parsed_interface = parts[1].strip() or None

                qpart = parts[2].strip().lower()
                if qpart.startswith("q"):
                    parsed_queue = _safe_int(qpart[1:])
                else:
                    parsed_queue = _safe_int(qpart)

            node_val = str(parsed_node or node or "").strip()
            interface_val = str(parsed_interface or interface or "").strip()

            if parsed_queue is not None and parsed_queue >= 0:
                queue_val = parsed_queue
            else:
                queue_val = _safe_int(queue)

            if not node_val or not interface_val or queue_val < 0:
                continue

            out.append(
                {
                    "entity_id": entity_id,
                    "node": node_val,
                    "interface": interface_val,
                    "queue": queue_val,
                }
            )
            seen.add(entity_id)

    _collect(ui_report.get("hotspots", []) or [])
    _collect(ui_report.get("all_hotspots", []) or [])

    cos_health = ui_report.get("cos_health", {}) or {}
    _collect(cos_health.get("hotspots", []) or [])
    _collect(cos_health.get("top_hotspots", []) or [])
    _collect(cos_health.get("all_hotspots", []) or [])

    return out


def _load_json_if_exists(path: str) -> Dict[str, Any]:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

import re


def _iter_queue_records_for_node(
    snapshot_report: Dict[str, Any],
    *,
    node: str,
) -> List[Dict[str, Any]]:
    """
    Return all normalized records that belong to the requested node.

    This is intentionally tolerant because snapshot JSON shapes vary:
    - nodes[].normalized_records
    - nodes[].subscriptions[].normalized_records
    - nodes[].records
    - top-level normalized_records / subscriptions
    """
    out: List[Dict[str, Any]] = []

    def node_matches(candidate: Any) -> bool:
        if candidate is None:
            return False
        c = str(candidate).strip()
        n = str(node).strip()
        return c == n or c.lower() == n.lower()

    def collect_from_node_entry(node_entry: Dict[str, Any]) -> None:
        out.extend(node_entry.get("normalized_records", []) or [])
        out.extend(node_entry.get("records", []) or [])

        for sub in node_entry.get("subscriptions", []) or []:
            out.extend(sub.get("normalized_records", []) or [])
            out.extend(sub.get("records", []) or [])

    # 1) Normal path: iterate nodes[]
    matched_any_node = False
    for node_entry in snapshot_report.get("nodes", []) or []:
        node_name = (
            node_entry.get("node")
            or node_entry.get("name")
            or node_entry.get("hostname")
            or node_entry.get("device")
        )
        if node_matches(node_name):
            matched_any_node = True
            collect_from_node_entry(node_entry)

    if matched_any_node:
        return out

    # 2) Fallback: if node names are not normalized as expected, collect from all nodes
    #    and let downstream filtering happen by interface/queue.
    for node_entry in snapshot_report.get("nodes", []) or []:
        if isinstance(node_entry, dict):
            collect_from_node_entry(node_entry)

    # 3) Extra fallback: top-level normalized records / subscriptions
    out.extend(snapshot_report.get("normalized_records", []) or [])
    out.extend(snapshot_report.get("records", []) or [])
    for sub in snapshot_report.get("subscriptions", []) or []:
        out.extend(sub.get("normalized_records", []) or [])
        out.extend(sub.get("records", []) or [])

    return out


def _parse_interface_from_record_path(path: str) -> str | None:
    if not path:
        return None
    m = re.search(r'interface\[name="?([^"\]]+)"?\]', path)
    if m:
        return m.group(1).strip()
    return None


def _parse_queue_from_record_path(path: str) -> int | None:
    if not path:
        return None

    m = re.search(r'queue\[queue=(\d+)\]', path)
    if m:
        return int(m.group(1))

    m = re.search(r'queue\[name="?(\d+)"?\]', path)
    if m:
        return int(m.group(1))

    m = re.search(r'/queue/(\d+)(?:/|$)', path)
    if m:
        return int(m.group(1))

    return None


def _extract_all_queue_candidates(
    snapshot_report: Dict[str, Any],
    *,
    node: str,
    queue: int,
) -> List[Dict[str, Any]]:
    """
    Return all candidate interface/queue records for a node+queue pair.
    """
    candidates: Dict[str, Dict[str, Any]] = {}

    def pick_from_sources(rec: Dict[str, Any], rec_fields: Dict[str, Any], *names: str) -> int:
        for name in names:
            if name in rec_fields:
                return _safe_int(rec_fields.get(name))
            if rec.get(name) is not None:
                return _safe_int(rec.get(name))
        return 0

    for rec in _iter_queue_records_for_node(snapshot_report, node=node):
        rec_path = str(
            rec.get("path")
            or rec.get("xpath")
            or rec.get("key")
            or rec.get("prefix")
            or rec.get("gnmi_prefix")
            or ""
        )
        rec_fields = rec.get("fields") or rec.get("values") or {}

        rec_queue = rec.get("queue")
        if rec_queue is None:
            rec_queue = _parse_queue_from_record_path(rec_path)

        if _safe_int(rec_queue) != _safe_int(queue):
            continue

        rec_intf = (
            rec.get("interface")
            or rec.get("interface_name")
            or rec.get("if_name")
            or rec.get("ifname")
            or rec.get("port")
        )
        if rec_intf is None:
            rec_intf = _parse_interface_from_record_path(rec_path)

        if not rec_intf:
            continue

        rec_intf = str(rec_intf)

        entry = candidates.setdefault(
            rec_intf,
            {
                "interface": rec_intf,
                "tail_dropped_packets": 0,
                "ecn_ce_packets": 0,
                "red_dropped_packets": 0,
                "resource_drops": 0,
                "peak_buffer_occupancy_percent": 0,
            },
        )

        entry["tail_dropped_packets"] = max(
            entry["tail_dropped_packets"],
            pick_from_sources(
                rec,
                rec_fields,
                "tail-dropped-packets",
                "tail-drop-pkts",
                "tail_drop_pkts",
                "tail_dropped_packets",
                "tail-drop-packets",
            ),
        )
        entry["ecn_ce_packets"] = max(
            entry["ecn_ce_packets"],
            pick_from_sources(
                rec,
                rec_fields,
                "ecn-ce-packets",
                "ecn-marked-pkts",
                "ecn_marked_pkts",
                "ecn_ce_packets",
                "ecn-ce-marked-packets",
            ),
        )
        entry["red_dropped_packets"] = max(
            entry["red_dropped_packets"],
            pick_from_sources(
                rec,
                rec_fields,
                "red-dropped-packets",
                "red-drop-pkts",
                "red_drop_pkts",
                "red_dropped_packets",
            ),
        )
        entry["resource_drops"] = max(
            entry["resource_drops"],
            pick_from_sources(
                rec,
                rec_fields,
                "in-resource-drops",
                "resource_drops",
                "in_resource_drops",
                "resource-drop-pkts",
            ),
        )
        entry["peak_buffer_occupancy_percent"] = max(
            entry["peak_buffer_occupancy_percent"],
            pick_from_sources(
                rec,
                rec_fields,
                "peak-buffer-occupancy-percent",
                "peak_buffer_occupancy_percent",
                "buffer-occupancy-percent",
                "buffer_occupancy_percent",
            ),
        )

    return list(candidates.values())


def _resolve_telemetry_interface_alias(
    *,
    snapshot_report: Dict[str, Any],
    node: str,
    queue: int,
    preferred_tail_value: int,
) -> str | None:
    """
    Resolve the best telemetry interface alias for a hotspot entity when the
    hotspot interface name does not match telemetry naming.

    Strategy:
      - same node
      - same queue
      - choose candidate with tail_dropped_packets closest to preferred_tail_value
      - if all tails are zero, choose highest occupancy candidate
    """
    candidates = _extract_all_queue_candidates(
        snapshot_report=snapshot_report,
        node=node,
        queue=queue,
    )
    if not candidates:
        return None

    if preferred_tail_value > 0:
        candidates = sorted(
            candidates,
            key=lambda x: (
                abs(_safe_int(x.get("tail_dropped_packets")) - preferred_tail_value),
                -_safe_int(x.get("peak_buffer_occupancy_percent")),
                x.get("interface", ""),
            ),
        )
    else:
        candidates = sorted(
            candidates,
            key=lambda x: (
                -_safe_int(x.get("tail_dropped_packets")),
                -_safe_int(x.get("peak_buffer_occupancy_percent")),
                x.get("interface", ""),
            ),
        )

    return str(candidates[0].get("interface")) if candidates else None


def _extract_qmon_queue_counters(
    snapshot_report: Dict[str, Any],
    *,
    node: str,
    interface: str,
    queue: int,
) -> Dict[str, int]:
    """
    Best-effort extractor for queue counters from telemetry snapshot JSON.

    Supports:
    1. Raw gNMI prefix + updates[] schema:
       - prefix: cos/interfaces/interface[name=...]/queues/queue[queue=7]
       - updates[].Path / updates[].values
    2. Older / structured normalized-record shapes using:
       - path/xpath/key/prefix
       - fields / values
    3. Metric-oriented normalized records using:
       - labels.interface
       - labels.queue
       - metric
       - value
    """
    result = {
        "tail_dropped_packets": 0,
        "ecn_ce_packets": 0,
        "red_dropped_packets": 0,
        "resource_drops": 0,
        "peak_buffer_occupancy_percent": 0,
    }

    def pick_from_sources(rec: Dict[str, Any], rec_fields: Dict[str, Any], *names: str) -> int:
        for name in names:
            if name in rec_fields:
                return _safe_int(rec_fields.get(name))
            if rec.get(name) is not None:
                return _safe_int(rec.get(name))
        return 0

    def parse_queue_from_path(path: str) -> int | None:
        if not path:
            return None

        patterns = [
            rf"queue\[queue={queue}\]",
            rf'queue\[name="{queue}"\]',
            rf"queue\[name={queue}\]",
            rf"queue\[{queue}\]",
            rf"/queue/{queue}(?:/|$)",
            rf"\|q{queue}(?:\b|$)",
            rf"\bq{queue}\b",
        ]

        for pat in patterns:
            if re.search(pat, path):
                return queue
        return None

    def parse_interface_from_path(path: str) -> str | None:
        if not path:
            return None

        m = re.search(r'interface\[name="?([^"\]]+)"?\]', path)
        if m:
            return m.group(1).strip()

        if interface and interface in path:
            return interface

        return None

    records = _iter_queue_records_for_node(snapshot_report, node=node)

    for rec in records:
        rec_fields = rec.get("fields") or rec.get("values") or {}
        labels = rec.get("labels", {}) or {}

        rec_path = str(
            rec.get("path")
            or rec.get("xpath")
            or rec.get("key")
            or rec.get("prefix")
            or rec.get("gnmi_prefix")
            or rec.get("source_prefix")
            or ""
        )

        rec_intf = (
            labels.get("interface")
            or rec.get("interface")
            or rec.get("interface_name")
            or rec.get("if_name")
            or rec.get("ifname")
            or rec.get("port")
        )

        rec_queue = labels.get("queue")
        if rec_queue is None:
            rec_queue = rec.get("queue")

        if rec_intf is None:
            rec_intf = parse_interface_from_path(rec_path)

        if rec_queue is None:
            rec_queue = parse_queue_from_path(rec_path)

        if str(rec_intf) != str(interface) or _safe_int(rec_queue) != _safe_int(queue):
            continue

        # ------------------------------------------------------------------
        # 0) Raw gNMI prefix + updates[] schema
        # ------------------------------------------------------------------
        updates = rec.get("updates") or []
        if updates:
            for upd in updates:
                upd_path = str(upd.get("Path") or "").strip()
                upd_values = upd.get("values") or {}

                if upd_path == "tailDropPkts":
                    result["tail_dropped_packets"] = max(
                        result["tail_dropped_packets"],
                        _safe_int(upd_values.get("tailDropPkts")),
                    )
                    continue

                if upd_path == "ecnMarkedPkts":
                    result["ecn_ce_packets"] = max(
                        result["ecn_ce_packets"],
                        _safe_int(upd_values.get("ecnMarkedPkts")),
                    )
                    continue

                if upd_path in ("redDropPkts", "redDroppedPkts"):
                    result["red_dropped_packets"] = max(
                        result["red_dropped_packets"],
                        _safe_int(upd_values.get(upd_path)),
                    )
                    continue

                if upd_path in ("resourceDrops", "resourceDropPkts"):
                    result["resource_drops"] = max(
                        result["resource_drops"],
                        _safe_int(upd_values.get(upd_path)),
                    )
                    continue

                if upd_path == "peakBufferOccupancyPercent":
                    result["peak_buffer_occupancy_percent"] = max(
                        result["peak_buffer_occupancy_percent"],
                        _safe_int(upd_values.get("peakBufferOccupancyPercent")),
                    )
                    continue

            continue

        metric = str(rec.get("metric") or rec.get("update_path") or "").strip()
        metric_lc = metric.lower()
        metric_value = _safe_int(rec.get("value", rec.get("raw_value", 0)))

        # ------------------------------------------------------------------
        # 1) Current metric/value schema
        # ------------------------------------------------------------------
        if metric_lc in ("tail-drop-pkts", "taildroppkts", "tail_dropped_packets"):
            result["tail_dropped_packets"] = max(result["tail_dropped_packets"], metric_value)
            continue

        if metric_lc in (
            "ecn-ce-pkts",
            "ecn-ce-marked-pkts",
            "out-ecn-ce-marked-pkts",
            "ecn_ce_packets",
        ):
            result["ecn_ce_packets"] = max(result["ecn_ce_packets"], metric_value)
            continue

        if metric_lc in ("red-drop-pkts", "reddroppkts", "red_dropped_packets"):
            result["red_dropped_packets"] = max(result["red_dropped_packets"], metric_value)
            continue

        if metric_lc in ("resource-drop-pkts", "resourcedroppkts", "resource_drops"):
            result["resource_drops"] = max(result["resource_drops"], metric_value)
            continue

        if metric_lc in (
            "buffer-occupancy-percent",
            "peak-buffer-occupancy-percent",
            "peak_buffer_occupancy_percent",
        ):
            result["peak_buffer_occupancy_percent"] = max(
                result["peak_buffer_occupancy_percent"], metric_value
            )
            continue

        # ------------------------------------------------------------------
        # 2) Backward-compatible structured schema
        # ------------------------------------------------------------------
        result["tail_dropped_packets"] = max(
            result["tail_dropped_packets"],
            pick_from_sources(
                rec,
                rec_fields,
                "tail-dropped-packets",
                "tail-drop-pkts",
                "tail_drop_pkts",
                "tail_dropped_packets",
                "tail-drop-packets",
                "tailDropPkts",
            ),
        )
        result["ecn_ce_packets"] = max(
            result["ecn_ce_packets"],
            pick_from_sources(
                rec,
                rec_fields,
                "ecn-ce-packets",
                "ecn-marked-pkts",
                "ecn_marked_pkts",
                "ecn_ce_packets",
                "ecn-ce-marked-packets",
                "out-ecn-ce-marked-pkts",
                "ecnMarkedPkts",
            ),
        )
        result["red_dropped_packets"] = max(
            result["red_dropped_packets"],
            pick_from_sources(
                rec,
                rec_fields,
                "red-dropped-packets",
                "red-drop-pkts",
                "red_drop_pkts",
                "red_dropped_packets",
                "redDropPkts",
                "redDroppedPkts",
            ),
        )
        result["resource_drops"] = max(
            result["resource_drops"],
            pick_from_sources(
                rec,
                rec_fields,
                "in-resource-drops",
                "resource_drops",
                "in_resource_drops",
                "resource-drop-pkts",
                "resourceDrops",
                "resourceDropPkts",
            ),
        )
        result["peak_buffer_occupancy_percent"] = max(
            result["peak_buffer_occupancy_percent"],
            pick_from_sources(
                rec,
                rec_fields,
                "peak-buffer-occupancy-percent",
                "peak_buffer_occupancy_percent",
                "buffer-occupancy-percent",
                "buffer_occupancy_percent",
                "peakBufferOccupancyPercent",
            ),
        )

    return result

def _resolve_queue_metrics_with_preference(
    *,
    entity_id: str,
    evidence_index: Dict[str, Any],
    baseline_metrics: Dict[str, int],
    running_metrics: Dict[str, int],
    post_metrics: Dict[str, int],
) -> Dict[str, Any]:
    """
    Prefer RCA evidence when raw telemetry extraction is empty/incomplete.
    Return resolved metrics plus source metadata.
    """
    evidence = evidence_index.get(entity_id, {}) or {}

    signals = evidence.get("signals", {}) or {}
    delta_running = evidence.get("delta_running", {}) or {}
    delta_post = evidence.get("delta_post", {}) or {}

    # Raw snapshot values
    raw_baseline_tail = _safe_int(baseline_metrics.get("tail_dropped_packets"))
    raw_running_tail = _safe_int(running_metrics.get("tail_dropped_packets"))
    raw_post_tail = _safe_int(post_metrics.get("tail_dropped_packets"))

    raw_baseline_ecn = _safe_int(baseline_metrics.get("ecn_ce_packets"))
    raw_running_ecn = _safe_int(running_metrics.get("ecn_ce_packets"))
    raw_post_ecn = _safe_int(post_metrics.get("ecn_ce_packets"))

    # RCA evidence values
    ui_total_tail = _safe_int(signals.get("tail_drop_pkts"))
    ui_running_delta_tail = _safe_int(delta_running.get("tail-drop-pkts"))
    ui_post_delta_tail = _safe_int(delta_post.get("tail-drop-pkts"))

    ui_running_delta_ecn = _safe_int(delta_running.get("ecn-marked-pkts"))
    ui_post_delta_ecn = _safe_int(delta_post.get("ecn-marked-pkts"))

    # Heuristic:
    # if raw extraction is all zeros but UI evidence has values, trust UI evidence
    raw_tail_empty = (raw_baseline_tail == 0 and raw_running_tail == 0 and raw_post_tail == 0)
    raw_ecn_empty = (raw_baseline_ecn == 0 and raw_running_ecn == 0 and raw_post_ecn == 0)

    use_ui_tail = raw_tail_empty and (ui_total_tail > 0 or ui_running_delta_tail > 0 or ui_post_delta_tail > 0)
    use_ui_ecn = raw_ecn_empty and (ui_running_delta_ecn > 0 or ui_post_delta_ecn > 0)

    if use_ui_tail:
        resolved_baseline_tail = 0
        resolved_running_tail = ui_running_delta_tail
        resolved_post_tail = ui_post_delta_tail
        tail_source = "rca_ui_evidence"
    else:
        resolved_baseline_tail = raw_baseline_tail
        resolved_running_tail = raw_running_tail
        resolved_post_tail = raw_post_tail
        tail_source = "raw_telemetry"

    if use_ui_ecn:
        resolved_baseline_ecn = 0
        resolved_running_ecn = ui_running_delta_ecn
        resolved_post_ecn = ui_post_delta_ecn
        ecn_source = "rca_ui_evidence"
    else:
        resolved_baseline_ecn = raw_baseline_ecn
        resolved_running_ecn = raw_running_ecn
        resolved_post_ecn = raw_post_ecn
        ecn_source = "raw_telemetry"

    return {
        "baseline_tail": resolved_baseline_tail,
        "running_tail": resolved_running_tail,
        "post_tail": resolved_post_tail,
        "baseline_ecn": resolved_baseline_ecn,
        "running_ecn": resolved_running_ecn,
        "post_ecn": resolved_post_ecn,
        "tail_source": tail_source,
        "ecn_source": ecn_source,
        "raw_baseline_metrics": baseline_metrics,
        "raw_running_metrics": running_metrics,
        "raw_post_metrics": post_metrics,
        "ui_signals": signals,
        "ui_delta_running": delta_running,
        "ui_delta_post": delta_post,
    }


def _compute_delta_bundle(
    *,
    baseline_metrics: Dict[str, int],
    running_metrics: Dict[str, int],
    post_metrics: Dict[str, int],
) -> Dict[str, float]:
    baseline_tail = _safe_int(baseline_metrics.get("tail_dropped_packets"))
    running_tail = _safe_int(running_metrics.get("tail_dropped_packets"))
    post_tail = _safe_int(post_metrics.get("tail_dropped_packets"))

    baseline_ecn = _safe_int(baseline_metrics.get("ecn_ce_packets"))
    running_ecn = _safe_int(running_metrics.get("ecn_ce_packets"))
    post_ecn = _safe_int(post_metrics.get("ecn_ce_packets"))

    baseline_red = _safe_int(baseline_metrics.get("red_dropped_packets"))
    running_red = _safe_int(running_metrics.get("red_dropped_packets"))
    post_red = _safe_int(post_metrics.get("red_dropped_packets"))

    baseline_resource = _safe_int(baseline_metrics.get("resource_drops"))
    running_resource = _safe_int(running_metrics.get("resource_drops"))
    post_resource = _safe_int(post_metrics.get("resource_drops"))

    rise_tail = max(0, running_tail - baseline_tail)
    linger_tail = max(0, post_tail - baseline_tail)

    rise_ecn = max(0, running_ecn - baseline_ecn)
    linger_ecn = max(0, post_ecn - baseline_ecn)

    rise_red = max(0, running_red - baseline_red)
    linger_red = max(0, post_red - baseline_red)

    rise_resource = max(0, running_resource - baseline_resource)
    linger_resource = max(0, post_resource - baseline_resource)

    recovery_ratio_tail = float(linger_tail / rise_tail) if rise_tail > 0 else 0.0
    recovery_ratio_ecn = float(linger_ecn / rise_ecn) if rise_ecn > 0 else 0.0
    recovery_ratio_red = float(linger_red / rise_red) if rise_red > 0 else 0.0
    recovery_ratio_resource = float(linger_resource / rise_resource) if rise_resource > 0 else 0.0

    if rise_tail <= 0 and rise_ecn <= 0 and rise_red <= 0 and rise_resource <= 0:
        event_delta_classification = "no_event_delta"
    elif rise_tail <= 0 and rise_red <= 0 and rise_resource <= 0 and rise_ecn > 0:
        if recovery_ratio_ecn <= 0.2:
            event_delta_classification = "expected_ecn_transient"
        else:
            event_delta_classification = "lingering_ecn_pressure"
    else:
        if rise_tail > 0:
            if recovery_ratio_tail <= 0.2:
                event_delta_classification = "expected_transient_taildrop"
            elif recovery_ratio_tail <= 0.8:
                event_delta_classification = "lingering_taildrop"
            else:
                event_delta_classification = "persistent_taildrop"
        else:
            if recovery_ratio_red > 0.8 or recovery_ratio_resource > 0.8:
                event_delta_classification = "persistent_resource_pressure"
            else:
                event_delta_classification = "transient_non_tail_pressure"

    return {
        "delta_tail_dropped_packets": float(rise_tail),
        "delta_ecn_ce_packets": float(rise_ecn),
        "delta_red_dropped_packets": float(rise_red),
        "delta_resource_drops": float(rise_resource),

        "post_tail_dropped_packets": float(linger_tail),
        "post_ecn_ce_packets": float(linger_ecn),
        "post_red_dropped_packets": float(linger_red),
        "post_resource_drops": float(linger_resource),

        "rise_tail_dropped_packets": float(rise_tail),
        "linger_tail_dropped_packets": float(linger_tail),
        "pre_tail_baseline_series": [0.0, 0.0, 0.0],
        "rise_ecn_ce_packets": float(rise_ecn),
        "linger_ecn_ce_packets": float(linger_ecn),
        "rise_red_dropped_packets": float(rise_red),
        "linger_red_dropped_packets": float(linger_red),
        "rise_resource_drops": float(rise_resource),
        "linger_resource_drops": float(linger_resource),

        "recovery_ratio_tail": recovery_ratio_tail,
        "recovery_ratio_ecn": recovery_ratio_ecn,
        "recovery_ratio_red": recovery_ratio_red,
        "recovery_ratio_resource": recovery_ratio_resource,

        "event_delta_classification": event_delta_classification,
    }


def _classify_linger_trend(values: list[float], flat_tolerance: float = 0.05) -> str:
    if not values:
        return "unknown"

    if len(values) == 1:
        return "single_sample"

    if max(values) <= 0:
        return "cleared"

    decreasing = all(values[i] <= values[i - 1] for i in range(1, len(values)))
    increasing = all(values[i] >= values[i - 1] for i in range(1, len(values)))

    span = max(values) - min(values)
    denom = max(max(values), 1.0)
    relative_span = span / denom

    if relative_span <= flat_tolerance:
        return "flat"
    if decreasing and values[-1] < values[0]:
        return "decreasing"
    if increasing and values[-1] > values[0]:
        return "increasing"
    return "mixed"

def build_phase_sample_paths(run_id: str, phase_profile: str) -> tuple[list[str], list[str]]:
    pre_paths = [
        telemetry_json_path(run_id, "pre_sample_1", phase_profile),
        telemetry_json_path(run_id, "pre_sample_2", phase_profile),
        telemetry_json_path(run_id, "pre_sample_3", phase_profile),
    ]
    post_paths = [
        telemetry_json_path(run_id, "recover_1", phase_profile),
        telemetry_json_path(run_id, "recover_2", phase_profile),
        telemetry_json_path(run_id, "post", phase_profile),
    ]
    return pre_paths, post_paths

def inject_phase_delta_into_ui_report(
    *,
    ui_report_path: str,
    baseline_telemetry_path: str,
    running_telemetry_path: str,
    post_telemetry_path: str,
    pre_sample_paths: list[str] | None = None,
    post_sample_paths: list[str] | None = None,
) -> None:

    def _extract_snapshot_timestamp(snapshot_report: Dict[str, Any]) -> str | None:
        if not snapshot_report:
            return None

        for key in ("generated_at", "collected_at", "timestamp", "captured_at", "snapshot_time"):
            value = snapshot_report.get(key)
            if value:
                return str(value)

        return None

    ui_report = _load_json_if_exists(ui_report_path)
    if not ui_report:
        raise RuntimeError(f"failed to load ui_report: {ui_report_path}")

    baseline_report = _load_json_if_exists(baseline_telemetry_path)
    running_report = _load_json_if_exists(running_telemetry_path)
    post_report = _load_json_if_exists(post_telemetry_path)

    pre_reports: list[Dict[str, Any]] = []
    for p in (pre_sample_paths or [baseline_telemetry_path]):
        loaded = _load_json_if_exists(p)
        if loaded:
            pre_reports.append(loaded)

    post_reports: list[Dict[str, Any]] = []
    for p in (post_sample_paths or [post_telemetry_path]):
        loaded = _load_json_if_exists(p)
        if loaded:
            post_reports.append(loaded)

    hotspot_entities = _extract_hotspot_entities_from_ui(ui_report)
    evidence_index = ui_report.get("evidence_index", {}) or {}

    for item in hotspot_entities:
        entity_id = item["entity_id"]
        node = item["node"]
        interface = item["interface"]
        queue = item["queue"]

        evidence = evidence_index.get(entity_id, {}) or {}
        signals = evidence.get("signals", {}) or {}
        preferred_tail_value = _safe_int(signals.get("tail_drop_pkts"))

        # Resolve one telemetry interface alias consistently across all phases.
        resolved_interface = _resolve_best_telemetry_interface_alias(
            baseline_report=baseline_report,
            running_report=running_report,
            post_report=post_report,
            pre_reports=pre_reports[:3],
            post_reports=post_reports,
            node=node,
            queue=queue,
            preferred_tail_value=preferred_tail_value,
            current_interface=interface,
        )

        baseline_metrics = _extract_qmon_queue_counters(
            baseline_report,
            node=node,
            interface=resolved_interface,
            queue=queue,
        )
        running_metrics = _extract_qmon_queue_counters(
            running_report,
            node=node,
            interface=resolved_interface,
            queue=queue,
        )
        post_metrics = _extract_qmon_queue_counters(
            post_report,
            node=node,
            interface=resolved_interface,
            queue=queue,
        )

        resolved = _resolve_queue_metrics_with_preference(
            entity_id=entity_id,
            evidence_index=evidence_index,
            baseline_metrics=baseline_metrics,
            running_metrics=running_metrics,
            post_metrics=post_metrics,
        )

        baseline_tail = _safe_int(resolved["baseline_tail"])
        running_tail = _safe_int(resolved["running_tail"])
        post_tail = _safe_int(resolved["post_tail"])

        baseline_ecn = _safe_int(resolved["baseline_ecn"])
        running_ecn = _safe_int(resolved["running_ecn"])
        post_ecn = _safe_int(resolved["post_ecn"])

        normalized_baseline_metrics = dict(baseline_metrics)
        normalized_running_metrics = dict(running_metrics)
        normalized_post_metrics = dict(post_metrics)

        normalized_baseline_metrics["tail_dropped_packets"] = baseline_tail
        normalized_running_metrics["tail_dropped_packets"] = running_tail
        normalized_post_metrics["tail_dropped_packets"] = post_tail

        normalized_baseline_metrics["ecn_ce_packets"] = baseline_ecn
        normalized_running_metrics["ecn_ce_packets"] = running_ecn
        normalized_post_metrics["ecn_ce_packets"] = post_ecn

        delta_bundle = _compute_delta_bundle(
            baseline_metrics=normalized_baseline_metrics,
            running_metrics=normalized_running_metrics,
            post_metrics=normalized_post_metrics,
        )

        # ------------------------------------------------------------------
        # Pre-phase extraction
        # ------------------------------------------------------------------
        provisional_pre_tail_values: list[int] = []
        for report in pre_reports[:3]:
            pm_try = _extract_qmon_queue_counters(
                report,
                node=node,
                interface=resolved_interface,
                queue=queue,
            )
            provisional_pre_tail_values.append(
                _safe_int(pm_try.get("tail_dropped_packets"))
            )

        all_pre_samples_zero = all(v == 0 for v in provisional_pre_tail_values)

        if all_pre_samples_zero and baseline_tail > 0:
            alias_interface = _resolve_best_telemetry_interface_alias(
                baseline_report=baseline_report,
                running_report=running_report,
                post_report=post_report,
                pre_reports=pre_reports[:3],
                post_reports=post_reports,
                node=node,
                queue=queue,
                preferred_tail_value=baseline_tail if baseline_tail > 0 else preferred_tail_value,
                current_interface=resolved_interface,
            )
            if alias_interface:
                resolved_interface = alias_interface

                baseline_metrics = _extract_qmon_queue_counters(
                    baseline_report,
                    node=node,
                    interface=resolved_interface,
                    queue=queue,
                )
                running_metrics = _extract_qmon_queue_counters(
                    running_report,
                    node=node,
                    interface=resolved_interface,
                    queue=queue,
                )
                post_metrics = _extract_qmon_queue_counters(
                    post_report,
                    node=node,
                    interface=resolved_interface,
                    queue=queue,
                )

                resolved = _resolve_queue_metrics_with_preference(
                    entity_id=entity_id,
                    evidence_index=evidence_index,
                    baseline_metrics=baseline_metrics,
                    running_metrics=running_metrics,
                    post_metrics=post_metrics,
                )

                baseline_tail = _safe_int(resolved["baseline_tail"])
                running_tail = _safe_int(resolved["running_tail"])
                post_tail = _safe_int(resolved["post_tail"])

                baseline_ecn = _safe_int(resolved["baseline_ecn"])
                running_ecn = _safe_int(resolved["running_ecn"])
                post_ecn = _safe_int(resolved["post_ecn"])

                normalized_baseline_metrics = dict(baseline_metrics)
                normalized_running_metrics = dict(running_metrics)
                normalized_post_metrics = dict(post_metrics)

                normalized_baseline_metrics["tail_dropped_packets"] = baseline_tail
                normalized_running_metrics["tail_dropped_packets"] = running_tail
                normalized_post_metrics["tail_dropped_packets"] = post_tail

                normalized_baseline_metrics["ecn_ce_packets"] = baseline_ecn
                normalized_running_metrics["ecn_ce_packets"] = running_ecn
                normalized_post_metrics["ecn_ce_packets"] = post_ecn

                delta_bundle = _compute_delta_bundle(
                    baseline_metrics=normalized_baseline_metrics,
                    running_metrics=normalized_running_metrics,
                    post_metrics=normalized_post_metrics,
                )

        pre_tail_raw: list[int] = []
        pre_ecn_raw: list[int] = []
        pre_sample_metrics: list[Dict[str, Any]] = []

        for report in pre_reports[:3]:
            pre_metrics = _extract_qmon_queue_counters(
                report,
                node=node,
                interface=resolved_interface,
                queue=queue,
            )
            pre_sample_metrics.append(pre_metrics)

            pre_tail = _safe_int(pre_metrics.get("tail_dropped_packets"))
            pre_ecn = _safe_int(pre_metrics.get("ecn_ce_packets"))

            if pre_tail == 0 and resolved["tail_source"] == "rca_ui_evidence":
                pre_tail = baseline_tail

            if pre_ecn == 0 and resolved["ecn_source"] == "rca_ui_evidence":
                pre_ecn = baseline_ecn

            pre_tail_raw.append(pre_tail)
            pre_ecn_raw.append(pre_ecn)

        while len(pre_tail_raw) < 3:
            pre_tail_raw.append(baseline_tail)

        while len(pre_ecn_raw) < 3:
            pre_ecn_raw.append(baseline_ecn)

        # Use the last pre-sample as the graph baseline so P3 becomes zero reference.
        graph_baseline_tail = pre_tail_raw[-1] if pre_tail_raw else baseline_tail
        graph_baseline_ecn = pre_ecn_raw[-1] if pre_ecn_raw else baseline_ecn

        pre_tail_series = [float(v - graph_baseline_tail) for v in pre_tail_raw[:3]]
        pre_ecn_series = [float(v - graph_baseline_ecn) for v in pre_ecn_raw[:3]]

        while len(pre_tail_series) < 3:
            pre_tail_series.append(0.0)

        while len(pre_ecn_series) < 3:
            pre_ecn_series.append(0.0)

        graph_rise_tail = float(running_tail - graph_baseline_tail)
        graph_linger_tail = float(post_tail - graph_baseline_tail)

        graph_rise_ecn = float(running_ecn - graph_baseline_ecn)
        graph_linger_ecn = float(post_ecn - graph_baseline_ecn)

        delta_bundle["rise_tail_dropped_packets"] = graph_rise_tail
        delta_bundle["linger_tail_dropped_packets"] = graph_linger_tail
        delta_bundle["rise_ecn_ce_packets"] = graph_rise_ecn
        delta_bundle["linger_ecn_ce_packets"] = graph_linger_ecn
        delta_bundle["pre_tail_baseline_series"] = pre_tail_series
        delta_bundle["pre_ecn_baseline_series"] = pre_ecn_series

        pre_timestamps = [_extract_snapshot_timestamp(r) for r in pre_reports[:3]]
        post_timestamps = [_extract_snapshot_timestamp(r) for r in post_reports]

        while len(pre_timestamps) < 3:
            pre_timestamps.append(None)

        while len(post_timestamps) < 3:
            post_timestamps.append(None)

        delta_bundle["phase_timestamps"] = {
            "pre_samples": pre_timestamps[:3],
            "event_window": _extract_snapshot_timestamp(running_report),
            "post_samples": post_timestamps[:3],
        }

        # ------------------------------------------------------------------
        # Post-phase extraction
        # ------------------------------------------------------------------
        provisional_tail_values: list[int] = []

        for report in post_reports:
            pm_try = _extract_qmon_queue_counters(
                report,
                node=node,
                interface=resolved_interface,
                queue=queue,
            )
            provisional_tail_values.append(
                _safe_int(pm_try.get("tail_dropped_packets"))
            )

        all_post_samples_zero = all(v == 0 for v in provisional_tail_values)

        if all_post_samples_zero and post_tail > 0:
            alias_interface = _resolve_telemetry_interface_alias_from_reports(
                reports=post_reports,
                node=node,
                queue=queue,
                preferred_tail_value=post_tail if post_tail > 0 else preferred_tail_value,
            )
            if alias_interface:
                resolved_interface = alias_interface

        tail_lingers: list[float] = []
        ecn_lingers: list[float] = []
        post_sample_metrics: list[Dict[str, Any]] = []

        for report in post_reports:
            pm = _extract_qmon_queue_counters(
                report,
                node=node,
                interface=resolved_interface,
                queue=queue,
            )
            post_sample_metrics.append(pm)

            pm_tail = _safe_int(pm.get("tail_dropped_packets"))
            pm_ecn = _safe_int(pm.get("ecn_ce_packets"))

            if pm_tail == 0 and resolved["tail_source"] == "rca_ui_evidence":
                pm_tail = post_tail

            if pm_ecn == 0 and resolved["ecn_source"] == "rca_ui_evidence":
                pm_ecn = post_ecn

            tail_linger_val = float(pm_tail - graph_baseline_tail)
            ecn_linger_val = float(pm_ecn - graph_baseline_ecn)

            tail_lingers.append(tail_linger_val)
            ecn_lingers.append(ecn_linger_val)

        delta_bundle["post_tail_linger_series"] = tail_lingers[:3]
        delta_bundle["post_ecn_linger_series"] = ecn_lingers[:3]

        while len(delta_bundle["post_tail_linger_series"]) < 3:
            delta_bundle["post_tail_linger_series"].append(0.0)

        while len(delta_bundle["post_ecn_linger_series"]) < 3:
            delta_bundle["post_ecn_linger_series"].append(0.0)

        delta_bundle["tail_linger_trend"] = _classify_linger_trend(tail_lingers)
        delta_bundle["ecn_linger_trend"] = _classify_linger_trend(ecn_lingers)
        delta_bundle["pre_sample_metrics"] = pre_sample_metrics
        delta_bundle["post_sample_metrics"] = post_sample_metrics
        delta_bundle["metric_resolution"] = {
            "tail_source": resolved["tail_source"],
            "ecn_source": resolved["ecn_source"],
        }
        delta_bundle["telemetry_interface_resolved"] = resolved_interface
        delta_bundle["debug_phase_series"] = {
            "entity_id": entity_id,
            "original_interface": interface,
            "resolved_interface": resolved_interface,
            "preferred_tail_value": preferred_tail_value,
            "baseline_tail": baseline_tail,
            "running_tail": running_tail,
            "post_tail": post_tail,
            "pre_tail_raw": pre_tail_raw[:3],
            "pre_ecn_raw": pre_ecn_raw[:3],
            "graph_baseline_tail": graph_baseline_tail,
            "graph_baseline_ecn": graph_baseline_ecn,
            "tail_lingers": tail_lingers[:3],
            "ecn_lingers": ecn_lingers[:3],
        }
        delta_bundle["telemetry_interface_match_mode"] = (
            "exact" if resolved_interface == interface else "alias_resolved"
        )

        def _update_hotspot_list(items: list[Dict[str, Any]] | None) -> None:
            for hotspot in items or []:
                if str(hotspot.get("entity_id")) == entity_id:
                    hotspot.update(delta_bundle)
                    hotspot["baseline_metrics"] = normalized_baseline_metrics
                    hotspot["running_metrics"] = normalized_running_metrics
                    hotspot["post_metrics"] = normalized_post_metrics

        _update_hotspot_list(ui_report.get("hotspots", []) or [])
        _update_hotspot_list(ui_report.get("all_hotspots", []) or [])

        cos_health = ui_report.get("cos_health", {}) or {}
        _update_hotspot_list(cos_health.get("hotspots", []) or [])
        _update_hotspot_list(cos_health.get("top_hotspots", []) or [])
        _update_hotspot_list(cos_health.get("all_hotspots", []) or [])



        if entity_id in evidence_index and isinstance(evidence_index[entity_id], dict):
            evidence_index[entity_id].update(delta_bundle)
            evidence_index[entity_id]["baseline_metrics"] = normalized_baseline_metrics
            evidence_index[entity_id]["running_metrics"] = normalized_running_metrics
            evidence_index[entity_id]["post_metrics"] = normalized_post_metrics
    ui_report["evidence_index"] = evidence_index

    # keep nested dict attached explicitly
    ui_report["cos_health"] = ui_report.get("cos_health", {}) or {}

    #with open(ui_report_path, "w", encoding="utf-8") as f:
    #    json.dump(ui_report, f, indent=2)
    atomic_write_json(ui_report_path, ui_report, indent=2)

def main() -> int:
    args = parse_args()

    def _collect_targeted_recovery_series(
        *,
        snapshot_prefix: str,
        total_window: int,
        sample_count: int,
        bounced_node: str,
        bounced_interface: str,
    ) -> list[str]:
        sample_count_local = max(1, int(sample_count))
        total_window_local = max(1, int(total_window))

        if sample_count_local == 1:
            sample_offsets = [total_window_local]
        else:
            interval = total_window_local / float(sample_count_local - 1)
            sample_offsets = [round(i * interval) for i in range(sample_count_local)]

        sample_paths: list[str] = []
        started_at = time.time()

        progress.info(
            f"[TARGETED-RECOVERY-SAMPLING] prefix={snapshot_prefix} "
            f"count={sample_count_local} window={total_window_local}s "
            f"offsets={sample_offsets} node={bounced_node} interface={bounced_interface}"
        )

        for i, target_offset in enumerate(sample_offsets):
            elapsed = time.time() - started_at
            sleep_needed = max(0.0, target_offset - elapsed)

            if sleep_needed > 0:
                time.sleep(sleep_needed)

            snapshot_name = f"{snapshot_prefix}_{i + 1}"

            progress.info(
                f"[TARGETED-RECOVERY-SAMPLING] Collecting {snapshot_name} "
                f"at offset={target_offset}s"
            )

            collect_recovery_snapshot(
                run_id=args.run_id,
                snapshot_name=snapshot_name,
                profile=args.phase_profile,
                nodes=args.nodes,
                timeout=args.timeout,
                topology_path=args.topology,
                bounced_node=bounced_node,
                bounced_interface=bounced_interface,
            )

            sample_path = telemetry_json_path(args.run_id, snapshot_name, args.phase_profile)
            ensure_file(sample_path)
            sample_paths.append(sample_path)

        return sample_paths

    print(
        f"[PHASE TIMING] baseline_window={args.baseline_window}s, "
        f"running_decay={args.running_decay}s, "
        f"settle_gap={args.settle_gap}s, "
        f"post_window={args.post_window}s, "
        f"post_wait={args.post_wait}s, "
        f"post_sample_count={args.post_sample_count}, "
        f"post_sample_interval={args.post_sample_interval}s"
    )

    if args.stress_orchestrator_report:
        try:
            stress_report = load_json_file(args.stress_orchestrator_report)
            verdict = stress_report.get("verdict", {}) or {}
            precheck_before_stress = verdict.get("precheck_before_stress")
            overall_status = stress_report.get("overall_status")

            print(f"[RCA-GATE] precheck_before_stress={precheck_before_stress}")
            print(f"[RCA-GATE] overall_status={overall_status}")

            if precheck_before_stress is False:
                print(
                    "\n[RCA-GATE] ABORTING RCA: Fabric already unhealthy before event "
                    "(precheck_before_stress=False)\n",
                    file=sys.stderr,
                )
                return 1

        except Exception as exc:
            print(f"[RCA-GATE] warning: failed to read stress report: {exc}", file=sys.stderr)
            return 1

    progress = ProgressLogger(progress_log_path(args.run_id))
    progress.stage("RUN_RCA_CASE_START")
    progress.info(f"run_id={args.run_id}")
    progress.info(f"profile={args.profile}")
    progress.info(f"phase_profile={args.phase_profile}")
    progress.info(f"nodes={args.nodes}")
    progress.info(f"enable_live_monitor={args.enable_live_monitor}")
    progress.info(f"enable_port_stats={args.enable_port_stats}")

    progress.stage("PHASE_TIMELINE")
    progress.info(f"baseline_window={args.baseline_window}")
    progress.info(f"running_decay={args.running_decay}")
    progress.info(f"settle_gap={args.settle_gap}")
    progress.info(f"post_window={args.post_window}")

    bounced_node = getattr(args, "node", None)
    bounced_interface = getattr(args, "interface", None)
    progress.info(f"bounced_node={bounced_node}")
    progress.info(f"bounced_interface={bounced_interface}")

    status = {
        "pre_snapshot": "pending",
        "pre_event_cleanliness": "pending",
        "running_snapshot": "pending",
        "post_snapshot": "pending",
        "congestion_analysis": "pending",
        "fabric_ranking": "pending",
        "delta_analysis": "pending",
        "telemetry_diff": "pending",
        "telemetry_analyzer": "pending",
        "rocev2_pre": "pending",
        "rocev2_post": "pending",
        "rocev2_verdict": "pending",
        "rocev2_deep_inspection": "pending",
        "rocev2_hotspot_report": "pending",
        "ixia_live_monitor": "skipped",
        "ixia_port_pre": "skipped",
        "ixia_port_post": "skipped",
        "traffic_verifier": "skipped",
        "congestion_inspection": "pending",
        "root_cause_correlation": "pending",
        "intent_rca": "pending",
        "cos_hotspot_correlation": "skipped",
        "ecmp_pre_sampling": "skipped",
        "ecmp_recovery_sampling": "skipped",
        "ecmp_degraded_sampling": "skipped",
    }
    file_overrides = {}

    try:
        progress.stage("IXIA_SESSION_INIT")
        interval_seconds = args.traffic_start_interval_ms / 1000.0
        inv = load_json_file(args.ixia_inventory)
        api_server = inv.get("ixnetwork_api_server")
        if not api_server:
            raise RuntimeError("ixnetwork_api_server not found in ixia inventory")

        progress.info(f"ixia_api_server={api_server}")

        ixia = IxiaClient(
            api_server=api_server,
            inventory_path=args.ixia_inventory,
            timeout=args.timeout,
            verify_tls=False,
        )

        sid = ixia.resolve_session_id(args.ixia_session_id)
        progress.info(f"ixia_session_id={sid}")

        # ------------------------------------------------------------------
        # PRE = traffic-on baseline window with lightweight pre samples,
        # optional targeted ECMP baseline samples, then canonical PRE
        # ------------------------------------------------------------------
        progress.stage("PREPARE_PRE_STAGE")
        progress.info("Starting traffic for BASELINE (PRE) stage")
        print("\n[IXIA] starting traffic for BASELINE snapshot ...")
        _start_ixia_traffic(
            ixia=ixia,
            sid=sid,
            traffic_start_mode=args.traffic_start_mode,
            traffic_start_interval_ms=args.traffic_start_interval_ms,
            progress=progress,
        )
        progress.info(
            f"Collecting true pre-window samples over baseline_window={args.baseline_window}s"
        )
        pre_sample_paths = collect_pre_window_samples(
            run_id=args.run_id,
            profile=args.phase_profile,
            nodes=args.nodes,
            timeout=args.timeout,
            topology_path=args.topology,
            baseline_window=args.baseline_window,
            sample_count=3,
            progress=progress,
        )
        file_overrides["pre_sample_paths"] = pre_sample_paths
        progress.info(f"pre_sample_paths={pre_sample_paths}")


        stress_ecmp_targets = file_overrides.get("ecmp_targets") or _extract_targets_from_orchestrator_report(
            args.stress_orchestrator_report
        )

        ecmp_targets = _build_ecmp_analysis_targets(
            args=args,
            file_overrides=file_overrides,
            fallback_targets=stress_ecmp_targets,
        )

        file_overrides["stress_ecmp_targets"] = stress_ecmp_targets
        file_overrides["ecmp_targets"] = ecmp_targets
        target_names = [
            f"{t.get('node')}|{t.get('interface')}"
            for t in ecmp_targets
        ]
        progress.info(
            f"[ECMP-ANALYSIS-TARGETS] "
            f"override_node={getattr(args, 'ecmp_analysis_node', None)} "
            f"targets={target_names}"
        )
        if ecmp_targets:
            progress.stage("ECMP_PRE_BASELINE_SAMPLING")
            try:
                ecmp_pre_sample_paths_by_target = {}

                for target in ecmp_targets:
                    target_node = target["node"]
                    target_interface = target["interface"]

                    target_paths = _collect_targeted_recovery_series(
                        #snapshot_prefix=f"ecmp_pre_{target_node}_{target_interface.replace('/', '_').replace(':', '_')}",
                        snapshot_prefix=f"ecmp_pre_{target_node}_{_encode_iface_for_snapshot(target_interface)}",
                        total_window=args.baseline_window,
                        sample_count=3,
                        bounced_node=target_node,
                        bounced_interface=target_interface,
                    )

                    ecmp_pre_sample_paths_by_target[target["entity"]] = target_paths
                    progress.info(
                        f"ECMP baseline sample paths for {target['entity']}: {target_paths}"
                    )

                file_overrides["ecmp_targets"] = ecmp_targets
                file_overrides["ecmp_pre_sample_paths_by_target"] = ecmp_pre_sample_paths_by_target
                status["ecmp_pre_sampling"] = "ok"

            except Exception as exc:
                status["ecmp_pre_sampling"] = "failed"
                status["ecmp_pre_sampling_error"] = str(exc)
                progress.warn(f"ECMP baseline sampling failed: {exc}")
        else:
            progress.warn(
                "ECMP baseline sampling skipped because no ECMP bounce targets were available"
        )

        progress.stage("PRE_TELEMETRY_SNAPSHOT")
        progress.info("Collecting PRE (baseline with traffic) telemetry snapshot")

        collect_snapshot(
            run_id=args.run_id,
            snapshot_name="pre",
            profile=args.profile,
            nodes=args.nodes,
            timeout=args.timeout,
            topology_path=args.topology,
        )

        pre_snapshot_path = telemetry_json_path(args.run_id, "pre", args.profile)
        ensure_file(pre_snapshot_path)
        pre_report = load_json(pre_snapshot_path)
        pre_health = load_snapshot_health(pre_snapshot_path)
        status["pre_snapshot"] = derive_snapshot_status(pre_health)

        progress.info(
            f"PRE snapshot health: ok_nodes={pre_health['ok_nodes']} "
            f"failed_nodes={pre_health['failed_nodes']} "
            f"status={status['pre_snapshot']}"
        )
        progress.info(f"PRE telemetry snapshot complete: {pre_snapshot_path}")

        progress.stage("PRE_ROCE_CAPTURE")
        try:
            pre_roce_path = _run_roce_stats(
                run_id=args.run_id,
                snapshot_name="rocev2_pre",
                timeout=args.timeout,
                ixia_inventory=args.ixia_inventory,
                session_id=sid,
            )
            file_overrides["rocev2_pre"] = pre_roce_path
            status["rocev2_pre"] = "ok"
            progress.info(f"PRE RoCE stats complete: {pre_roce_path}")
        except Exception as exc:
            status["rocev2_pre"] = "failed"
            status["rocev2_pre_error"] = str(exc)
            progress.error(f"PRE RoCE stats failed: {exc}")

        if args.enable_port_stats:
            progress.stage("PRE_PORT_STATS_CAPTURE")
            try:
                port_pre = _run_ixia_port_stats(
                    run_id=args.run_id,
                    snapshot_name="ixia_port_pre",
                    timeout=args.timeout,
                    ixia_inventory=args.ixia_inventory,
                    session_id=sid,
                )
                file_overrides["ixia_port_pre"] = port_pre
                status["ixia_port_pre"] = "ok"
                progress.info(f"PRE port stats complete: {port_pre}")
            except Exception as exc:
                status["ixia_port_pre"] = "failed"
                status["ixia_port_pre_error"] = str(exc)
                progress.error(f"PRE port stats failed: {exc}")

        # ------------------------------------------------------------------
        # RUNNING = continue traffic, wait, then snapshot
        # ------------------------------------------------------------------
        progress.stage("RUNNING_STAGE_WAIT")
        progress.info(f"Traffic already running; sleeping running_wait={args.running_wait}s")
        time.sleep(args.running_wait)

        if args.enable_live_monitor:
            progress.stage("LIVE_MONITOR_STAGE")
            progress.info(
                f"Starting live monitor iterations={args.live_monitor_iterations} "
                f"interval={args.live_monitor_interval}s"
            )
            try:
                live_path = _run_ixia_live_monitor(
                    run_id=args.run_id,
                    timeout=args.timeout,
                    ixia_inventory=args.ixia_inventory,
                    session_id=sid,
                    iterations=args.live_monitor_iterations,
                    poll_interval=args.live_monitor_interval,
                )
                file_overrides["ixia_live_monitor"] = live_path
                status["ixia_live_monitor"] = "ok"
                progress.info(f"Live monitor complete: {live_path}")
            except Exception as exc:
                status["ixia_live_monitor"] = "failed"
                status["ixia_live_monitor_error"] = str(exc)
                progress.error(f"Live monitor failed: {exc}")

        # ------------------------------------------------------------------
        # RUNNING snapshot: immediate event impact under traffic
        # ------------------------------------------------------------------
        progress.stage("RUNNING_TELEMETRY_SNAPSHOT")
        progress.info("Collecting RUNNING telemetry snapshot")
        collect_snapshot(
            run_id=args.run_id,
            snapshot_name="running",
            profile=args.profile,
            nodes=args.nodes,
            timeout=args.timeout,
            topology_path=args.topology,
        )

        running_snapshot_path = telemetry_json_path(args.run_id, "running", args.profile)
        ensure_file(running_snapshot_path)
        running_report = load_json(running_snapshot_path)
        running_health = load_snapshot_health(running_snapshot_path)
        status["running_snapshot"] = derive_snapshot_status(running_health)

        progress.info(
            f"RUNNING snapshot health: ok_nodes={running_health['ok_nodes']} "
            f"failed_nodes={running_health['failed_nodes']} "
            f"status={status['running_snapshot']}"
        )
        progress.info(f"RUNNING telemetry snapshot complete: {running_snapshot_path}")

        # ------------------------------------------------------------------
        # POST = stop traffic after event, wait quiet gap, restart traffic,
        # then collect lightweight recovery samples under resumed traffic,
        # optional targeted ECMP recovery samples, then canonical POST
        # ------------------------------------------------------------------
        progress.stage("STOP_TRAFFIC_FOR_POST_STAGE")
        progress.info("Stopping traffic after RUNNING snapshot")
        print("\n[IXIA] stopping traffic after RUNNING snapshot ...")
        ixia.stop_traffic(sid)

        progress.info(
            f"Traffic stopped; waiting post_wait={args.post_wait}s before post recovery window"
        )
        time.sleep(args.post_wait)

        progress.stage("RESTART_TRAFFIC_FOR_POST_WINDOW")
        progress.info("Restarting traffic for POST recovery window")
        print("\n[IXIA] starting traffic for POST recovery window ...")
        _start_ixia_traffic(
            ixia=ixia,
            sid=sid,
            traffic_start_mode=args.traffic_start_mode,
            traffic_start_interval_ms=args.traffic_start_interval_ms,
            progress=progress,
        )

        sample_count = 3
        recovery_sample_names = ["recover_1", "recover_2", "post"]

        post_sample_paths = collect_post_window_samples(
            run_id=args.run_id,
            profile=args.phase_profile,
            nodes=args.nodes,
            timeout=args.timeout,
            topology_path=args.topology,
            post_window=args.post_window,
            sample_count=sample_count,
            progress=progress,
        )
        file_overrides["post_sample_paths"] = post_sample_paths
        file_overrides["post_sample_names"] = recovery_sample_names


        fallback_targets = file_overrides.get("stress_ecmp_targets") or []

        if not fallback_targets:
            fallback_targets = [
                {
                    "node": r.get("target", {}).get("node"),
                    "interface": str(r.get("target", {}).get("interface") or "").replace("~", ":"),
                }
                for item in (stress_report.get("iteration_results") or [])
                for r in ((item.get("stress_action") or {}).get("results") or [])
                if r.get("target", {}).get("node") and r.get("target", {}).get("interface")
            ]
        ecmp_targets = _build_ecmp_analysis_targets(
            args=args,
            file_overrides=file_overrides,
            fallback_targets=fallback_targets,
        )

        file_overrides["ecmp_targets"] = ecmp_targets

        target_names = [
            f"{t.get('node')}|{t.get('interface')}"
            for t in ecmp_targets
        ]
        progress.info(
            f"[ECMP-ANALYSIS-TARGETS] "
            f"override_node={getattr(args, 'ecmp_analysis_node', None)} "
            f"targets={target_names}"
        ) 

        if ecmp_targets:
            progress.stage("ECMP_DEGRADED_HOLD_SAMPLING")

            try:
                ecmp_degraded_sample_paths_by_target = {}

                for target in ecmp_targets:
                    target_node = target["node"]
                    target_interface = target["interface"]

                    target_paths = _collect_targeted_recovery_series(
                        snapshot_prefix=(
                            f"ecmp_degraded_{target_node}_"
                            f"{_encode_iface_for_snapshot(target_interface)}"
                        ),
                        total_window=max(
                            1,
                            int(getattr(args, "degraded_hold_seconds", 60))
                        ),
                        sample_count=max(
                            1,
                            int(getattr(args, "degraded_ecmp_sample_count", 3))
                        ),
                        bounced_node=target_node,
                        bounced_interface=target_interface,
                    )

                    ecmp_degraded_sample_paths_by_target[
                        target["entity"]
                    ] = target_paths

                    progress.info(
                        f"ECMP degraded sample paths for "
                        f"{target['entity']}: {target_paths}"
                    )

                file_overrides[
                    "ecmp_degraded_sample_paths_by_target"
                ] = ecmp_degraded_sample_paths_by_target

                status["ecmp_degraded_sampling"] = "ok"

            except Exception as exc:
                status["ecmp_degraded_sampling"] = "failed"
                status["ecmp_degraded_sampling_error"] = str(exc)

                progress.warn(
                    f"ECMP degraded sampling failed: {exc}"
                )

            # legacy
            progress.stage("ECMP_POST_RECOVERY_SAMPLING")

            try:
                ecmp_recovery_sample_paths_by_target = {}

                for target in ecmp_targets:
                    target_node = target["node"]
                    target_interface = target["interface"]

                    target_paths = _collect_targeted_recovery_series(
                        #snapshot_prefix=f"ecmp_recover_{target_node}_{target_interface.replace('/', '_').replace(':', '_')}",
                        snapshot_prefix=f"ecmp_recover_{target_node}_{_encode_iface_for_snapshot(target_interface)}",
                        total_window=args.post_window,
                        sample_count=3,
                        bounced_node=target_node,
                        bounced_interface=target_interface,
                    )

                    ecmp_recovery_sample_paths_by_target[target["entity"]] = target_paths
                    progress.info(
                        f"ECMP recovery sample paths for {target['entity']}: {target_paths}"
                    )

                file_overrides["ecmp_recovery_sample_paths_by_target"] = ecmp_recovery_sample_paths_by_target
                status["ecmp_recovery_sampling"] = "ok"

            except Exception as exc:
                status["ecmp_recovery_sampling"] = "failed"
                status["ecmp_recovery_sampling_error"] = str(exc)
                progress.warn(f"ECMP recovery sampling failed: {exc}")
        else:
            progress.warn(
                "ECMP recovery sampling skipped because no ECMP bounce targets were available"
    )
        recovery_sample_health: List[Dict[str, Any]] = []
        for sample_path in post_sample_paths:
            sample_health = load_snapshot_health(sample_path)
            recovery_sample_health.append(sample_health)
            progress.info(
                f"POST sample health: path={sample_path} "
                f"ok_nodes={sample_health['ok_nodes']} "
                f"failed_nodes={sample_health['failed_nodes']} "
                f"status={derive_snapshot_status(sample_health)}"
            )

        progress.stage("POST_TELEMETRY_SNAPSHOT")
        progress.info("Collecting canonical POST telemetry snapshot with full profile")

        collect_snapshot(
            run_id=args.run_id,
            snapshot_name="post",
            profile=args.profile,
            nodes=args.nodes,
            timeout=args.timeout,
            topology_path=args.topology,
        )

        post_snapshot_path = telemetry_json_path(args.run_id, "post", args.profile)
        ensure_file(post_snapshot_path)
        post_report = load_json(post_snapshot_path)
        post_health = load_snapshot_health(post_snapshot_path)
        status["post_snapshot"] = derive_snapshot_status(post_health)

        file_overrides["phase_windows"] = {
            "baseline_window": int(args.baseline_window),
            "running_decay": int(args.running_decay),
            "settle_gap": int(args.settle_gap),
            "post_window": int(args.post_window),
            "post_wait": int(args.post_wait),
            "post_sample_count": int(sample_count),
            "post_sample_interval": int(args.post_window // 2) if int(args.post_window) > 1 else 1,
        }

        progress.info(f"POST recovery sample paths: {post_sample_paths}")
        progress.info(f"Canonical POST snapshot: {post_snapshot_path}")

        # ------------------------------------------------------------------
        # POST RoCE / Port stats under resumed traffic
        # ------------------------------------------------------------------
        progress.stage("POST_ROCE_CAPTURE")
        try:
            post_roce_path = _run_roce_stats(
                run_id=args.run_id,
                snapshot_name="rocev2_post",
                timeout=args.timeout,
                ixia_inventory=args.ixia_inventory,
                session_id=sid,
            )
            file_overrides["rocev2_post"] = post_roce_path
            status["rocev2_post"] = "ok"
            progress.info(f"POST RoCE stats complete: {post_roce_path}")
        except Exception as exc:
            status["rocev2_post"] = "failed"
            status["rocev2_post_error"] = str(exc)
            progress.error(f"POST RoCE stats failed: {exc}")

        if args.enable_port_stats:
            progress.stage("POST_PORT_STATS_CAPTURE")
            try:
                port_post = _run_ixia_port_stats(
                    run_id=args.run_id,
                    snapshot_name="ixia_port_post",
                    timeout=args.timeout,
                    ixia_inventory=args.ixia_inventory,
                    session_id=sid,
                )
                file_overrides["ixia_port_post"] = port_post
                status["ixia_port_post"] = "ok"
                progress.info(f"POST port stats complete: {port_post}")
            except Exception as exc:
                status["ixia_port_post"] = "failed"
                status["ixia_port_post_error"] = str(exc)
                progress.error(f"POST port stats failed: {exc}")

        # ------------------------------------------------------------------
        # Stop traffic only after the full recovery-under-load series
        # ------------------------------------------------------------------
        progress.stage("STOP_TRAFFIC_AFTER_POST_SERIES")
        progress.info("Stopping traffic after POST recovery series")
        print("\n[IXIA] stopping traffic after POST recovery series ...")
        ixia.stop_traffic(sid)

        if args.resume_after_post:
            progress.stage("RESUME_TRAFFIC_AFTER_POST")
            progress.info("Resuming traffic after POST recovery series")
            print("\n[IXIA] resuming traffic after POST recovery series ...")
            _start_ixia_traffic(
                ixia=ixia,
                sid=sid,
                traffic_start_mode=args.traffic_start_mode,
                traffic_start_interval_ms=args.traffic_start_interval_ms,
                progress=progress,
            )
            progress.info("Traffic resumed after POST recovery series")

        telemetry_usable = any(
            s in ("ok", "partial")
            for s in (
                status["pre_snapshot"],
                status["running_snapshot"],
                status["post_snapshot"],
            )
        ) and status["running_snapshot"] in ("ok", "partial")

        if telemetry_usable:
            progress.stage("RUNNING_CONGESTION_ANALYSIS")
            progress.info("Running congestion analysis on RUNNING snapshot")
            run_congestion_analysis(args.run_id, args.profile)
            ensure_file(congestion_json_path(args.run_id, "running", args.profile))
            status["congestion_analysis"] = "ok"
            progress.info(
                f"Congestion analysis complete: {congestion_json_path(args.run_id, 'running', args.profile)}"
            )

            progress.stage("FABRIC_HOTSPOT_RANKING")
            progress.info(f"Running fabric hotspot ranking top_n={args.top_n}")
            run_fabric_ranker(args.run_id, args.profile, args.top_n)
            ensure_file(fabric_hotspot_json_path(args.run_id, "running", args.profile))
            status["fabric_ranking"] = "ok"
            progress.info(
                f"Fabric hotspot ranking complete: {fabric_hotspot_json_path(args.run_id, 'running', args.profile)}"
            )

            progress.stage("DELTA_ANALYSIS")
            progress.info("Running pre/running/post delta analysis")
            run_delta_analysis(args.run_id, args.profile, args.top_n)
            status["delta_analysis"] = "ok"
            progress.info(
                f"Delta analysis complete: {delta_json_path(args.run_id, 'running', args.profile)}"
            )

            progress.stage("TELEMETRY_DIFF_AND_ANALYZER")
            progress.info("Running telemetry diff and anomaly analyzer")
            telemetry_outputs = run_telemetry_diff_and_analyzer(args.run_id, args.profile)

            if telemetry_outputs.get("telemetry_diff"):
                file_overrides["telemetry_diff"] = telemetry_outputs["telemetry_diff"]
                status["telemetry_diff"] = "ok"
                progress.info(f"Telemetry diff complete: {telemetry_outputs['telemetry_diff']}")
            else:
                status["telemetry_diff"] = "failed"
                status["telemetry_diff_error"] = telemetry_outputs.get("telemetry_diff_error")
                progress.warn(f"Telemetry diff failed: {status['telemetry_diff_error']}")

            if telemetry_outputs.get("telemetry_analyzer"):
                file_overrides["telemetry_analyzer"] = telemetry_outputs["telemetry_analyzer"]
                status["telemetry_analyzer"] = "ok"
                progress.info(
                    f"Telemetry analyzer complete: {telemetry_outputs['telemetry_analyzer']}"
                )
            else:
                status["telemetry_analyzer"] = "failed"
                status["telemetry_analyzer_error"] = telemetry_outputs.get("telemetry_analyzer_error")
                progress.warn(f"Telemetry analyzer failed: {status['telemetry_analyzer_error']}")
        else:
            progress.stage("TELEMETRY_DEPENDENT_STAGES_SKIPPED")
            progress.warn("Skipping telemetry-dependent RCA stages because RUNNING snapshot is not usable")
            status["congestion_analysis"] = "failed"
            status["fabric_ranking"] = "failed"
            status["delta_analysis"] = "failed"
            status["telemetry_diff"] = "failed"
            status["telemetry_analyzer"] = "failed"

        if file_overrides.get("rocev2_pre") and file_overrides.get("rocev2_post"):
            progress.stage("ROCE_VERIFIER")
            try:
                verdict_path = _run_roce_verifier(
                    run_id=args.run_id,
                    pre_path=file_overrides["rocev2_pre"],
                    post_path=file_overrides["rocev2_post"],
                )
                file_overrides["rocev2_verdict"] = verdict_path
                status["rocev2_verdict"] = "ok"
                progress.info(f"RoCE verifier complete: {verdict_path}")
            except Exception as exc:
                status["rocev2_verdict"] = "failed"
                status["rocev2_verdict_error"] = str(exc)
                progress.error(f"RoCE verifier failed: {exc}")
        else:
            status["rocev2_verdict"] = "skipped"
            progress.warn(
                "RoCE verifier skipped because PRE/POST RoCE stats are not both available"
            )

        if file_overrides.get("rocev2_verdict"):
            progress.stage("ROCE_DEEP_INSPECTION")
            try:
                deep_path = _run_roce_deep(
                    run_id=args.run_id,
                    pre_path=file_overrides["rocev2_pre"],
                    post_path=file_overrides["rocev2_post"],
                    verdict_path=file_overrides["rocev2_verdict"],
                )
                file_overrides["rocev2_deep_inspection"] = deep_path
                status["rocev2_deep_inspection"] = "ok"
                progress.info(f"RoCE deep inspection complete: {deep_path}")
            except Exception as exc:
                status["rocev2_deep_inspection"] = "failed"
                status["rocev2_deep_inspection_error"] = str(exc)
                progress.error(f"RoCE deep inspection failed: {exc}")
        else:
            status["rocev2_deep_inspection"] = "skipped"
            progress.warn(
                "RoCE deep inspection skipped because RoCE verdict is not available"
            )

        if file_overrides.get("rocev2_deep_inspection"):
            progress.stage("ROCE_HOTSPOT_REPORT")
            try:
                hotspot_path = _run_roce_hotspot(
                    run_id=args.run_id,
                    deep_path=file_overrides["rocev2_deep_inspection"],
                )
                file_overrides["rocev2_hotspot_report"] = hotspot_path
                status["rocev2_hotspot_report"] = "ok"
                progress.info(f"RoCE hotspot report complete: {hotspot_path}")
            except Exception as exc:
                status["rocev2_hotspot_report"] = "failed"
                status["rocev2_hotspot_report_error"] = str(exc)
                progress.error(f"RoCE hotspot report failed: {exc}")
        else:
            status["rocev2_hotspot_report"] = "skipped"
            progress.warn(
                "RoCE hotspot report skipped because RoCE deep inspection is not available"
            )

        if (
            file_overrides.get("rocev2_verdict")
            and file_overrides.get("rocev2_deep_inspection")
            and file_overrides.get("rocev2_hotspot_report")
        ):
            progress.stage("CONGESTION_INSPECTOR")
            try:
                congestion_path = _run_congestion_inspector(
                    run_id=args.run_id,
                    verdict_path=file_overrides["rocev2_verdict"],
                    deep_path=file_overrides["rocev2_deep_inspection"],
                    hotspot_path=file_overrides["rocev2_hotspot_report"],
                    pre_port_stats=file_overrides.get("ixia_port_pre"),
                    post_port_stats=file_overrides.get("ixia_port_post"),
                )
                file_overrides["congestion_inspection"] = congestion_path
                status["congestion_inspection"] = "ok"
                progress.info(f"Congestion inspection complete: {congestion_path}")
            except Exception as exc:
                status["congestion_inspection"] = "failed"
                status["congestion_inspection_error"] = str(exc)
                progress.error(f"Congestion inspection failed: {exc}")

        if file_overrides.get("congestion_inspection"):
            progress.stage("ROOT_CAUSE_CORRELATOR")
            try:
                root_cause = _run_root_cause_correlator(
                    run_id=args.run_id,
                    congestion_path=file_overrides["congestion_inspection"],
                    ixia_inventory=args.ixia_inventory,
                )
                file_overrides["root_cause_correlation"] = root_cause
                status["root_cause_correlation"] = "ok"
                progress.info(f"Root cause correlation complete: {root_cause}")
            except Exception as exc:
                status["root_cause_correlation"] = "failed"
                status["root_cause_correlation_error"] = str(exc)
                progress.error(f"Root cause correlation failed: {exc}")

        if args.enable_port_stats and file_overrides.get("ixia_port_pre") and file_overrides.get("ixia_port_post"):
            progress.stage("TRAFFIC_VERIFIER")
            try:
                traffic_verdict = _run_traffic_verifier(
                    run_id=args.run_id,
                    pre_path=file_overrides["ixia_port_pre"],
                    post_path=file_overrides["ixia_port_post"],
                )
                file_overrides["traffic_verifier"] = traffic_verdict
                status["traffic_verifier"] = "ok"
                progress.info(f"Traffic verifier complete: {traffic_verdict}")
            except Exception as exc:
                status["traffic_verifier"] = "failed"
                status["traffic_verifier_error"] = str(exc)
                progress.error(f"Traffic verifier failed: {exc}")

        progress.stage("INTENT_RCA")
        intent_rca_status = "ok"
        try:
            if telemetry_usable:
                progress.info("Running intent RCA")
                run_intent_rca(
                    run_id=args.run_id,
                    profile=args.profile,
                    topology=args.topology,
                    src=args.src,
                    dst=args.dst,
                    intent_name=args.intent_name,
                )
                progress.info("Intent RCA complete")
            else:
                intent_rca_status = "failed"
                status["intent_rca_error"] = "skipped because telemetry was not usable"
                progress.warn("Intent RCA skipped because telemetry was not usable")
        except Exception as exc:
            intent_rca_status = "failed"
            status["intent_rca_error"] = str(exc)
            print(f"[WARN] intent RCA failed: {exc}")
            progress.warn(f"Intent RCA failed: {exc}")

        status["intent_rca"] = intent_rca_status
        if (
            file_overrides.get("ecmp_pre_sample_paths_by_target")
            and file_overrides.get("ecmp_degraded_sample_paths_by_target")
            and file_overrides.get("ecmp_recovery_sample_paths_by_target")
        ):
            progress.stage("ECMP_RECOVERY_ANALYSIS")
            try:
                import json
                from controller.telemetry_targets import resolve_recovery_interfaces_for_bounce
                from controller.ecmp_recovery_analyzer import (
                    build_ecmp_recovery_report,
                    write_ecmp_recovery_report,
                )

                ecmp_targets = file_overrides.get("ecmp_targets", []) or []
                per_target_reports = []
                degraded_hold_windows = _extract_degraded_hold_windows(
                    args.stress_orchestrator_report
                )
                orchestrator_degraded_paths = _extract_orchestrator_degraded_sample_paths(
                    args.stress_orchestrator_report
                )
                degraded_event_sample_paths = sorted(set(
                    path
                    for paths in (orchestrator_degraded_paths or {}).values()
                    for path in (paths or [])
                ))

                degraded_event_hold_window = {}
                for window in (degraded_hold_windows or {}).values():
                    if window:
                        degraded_event_hold_window = window
                        break

                cli_ecmp_targets = _parse_ecmp_analysis_targets(args.ecmp_analysis_targets)
                for target in ecmp_targets:
                    target_entity = target["entity"]
                    target_node = target["node"]
                    target_interface = target["interface"]
                    
                    degraded_hold_window = degraded_event_hold_window
                    target_pre_paths = file_overrides["ecmp_pre_sample_paths_by_target"].get(target_entity, [])

                    target_degraded_paths = degraded_event_sample_paths

                    target_recovery_paths = file_overrides["ecmp_recovery_sample_paths_by_target"].get(target_entity, [])

                    stress_targets_for_node = [
                        x for x in (file_overrides.get("stress_ecmp_targets") or [])
                        if str(x.get("node", "")).lower() == str(target_node).lower()
                    ]

                    degraded_disabled_interfaces = sorted(set(
                        str(r.get("target", {}).get("interface") or "").replace("~", ":")
                        for item in (stress_report.get("iteration_results") or [])
                        for r in ((item.get("stress_action") or {}).get("results") or [])
                        if (r.get("target") or {}).get("interface")
                    ))

                    if (
                        not target_pre_paths
                        or not target_recovery_paths
                    ):
                        per_target_reports.append(
                            {
                                "entity": target_entity,
                                "node": target_node,
                                "interface": target_interface,
                                "status": "skipped",
                                "reason": "missing targeted ECMP sample paths",
                                "analysis": {},
                                "baseline_summary": {},
                                "recovery_summary": {},
                            }
                        )
                        continue

                    recovery_if_map = resolve_recovery_interfaces_for_bounce(
                        topology_path=args.topology,
                        selected_nodes=[target_node],
                        bounced_node=target_node,
                        bounced_interface=target_interface,
                    )
                    interfaces_of_interest = (
                        recovery_if_map.get(target_node, [])
                        or recovery_if_map.get(target_node.lower(), [])
                        or [target_interface]
                    )

                    interface_speeds = {}
                    device_facts_dir = os.path.join("artifacts", "device_facts")
                    candidate_paths = [
                        os.path.join(device_facts_dir, f"{target_node}_facts.json"),
                        os.path.join(device_facts_dir, f"{str(target_node).lower()}_facts.json"),
                        os.path.join(device_facts_dir, f"{str(target_node).upper()}_facts.json"),
                    ]

                    facts_path = None
                    for path in candidate_paths:
                        if os.path.exists(path):
                            facts_path = path
                            break

                    if not facts_path and os.path.isdir(device_facts_dir):
                        for name in os.listdir(device_facts_dir):
                            if not name.endswith("_facts.json"):
                                continue
                            path = os.path.join(device_facts_dir, name)
                            try:
                                with open(path, "r", encoding="utf-8") as fh:
                                    facts_data = json.load(fh)
                                if str(facts_data.get("node_name", "")).strip().lower() == str(target_node).strip().lower():
                                    facts_path = path
                                    interface_speeds = facts_data.get("interface_speeds", {}) or {}
                                    break
                            except Exception:
                                continue

                    if facts_path and not interface_speeds:
                        with open(facts_path, "r", encoding="utf-8") as fh:
                            facts_data = json.load(fh)
                        interface_speeds = facts_data.get("interface_speeds", {}) or {}

                    q8_taildrop_growth = None


                    analysis_interfaces_of_interest = sorted(set(
                        t["interface"]
                        for t in cli_ecmp_targets
                        if str(t["node"]).lower() == str(target_node).lower()
                    ))

                    if not analysis_interfaces_of_interest:
                        analysis_interfaces_of_interest = sorted(set(
                            str(t.get("interface") or "").replace("~", ":")
                            for t in (file_overrides.get("ecmp_targets") or [])
                            if str(t.get("node", "")).lower() == str(target_node).lower()
                            and t.get("interface")
                        ))

                    if not analysis_interfaces_of_interest:
                        analysis_interfaces_of_interest = interfaces_of_interest
                   
                    expected_min_ecmp_members = 3

                    if len(analysis_interfaces_of_interest) < expected_min_ecmp_members:
                        raise RuntimeError(
                            f"ECMP analysis interface set too small: "
                            f"target={target_entity}, interfaces={analysis_interfaces_of_interest}"
                        )

                    print("[ECMP-ANALYSIS-INTERFACES]", target_entity, len(analysis_interfaces_of_interest), analysis_interfaces_of_interest)
                    try:
                        ecmp_report = build_ecmp_recovery_report(
                            run_id=args.run_id,
                            node=target_node,
                            bounced_interface=target_interface,
                            ecmp_pre_sample_paths=target_pre_paths,
                            ecmp_recovery_sample_paths=target_recovery_paths,
                            ecmp_degraded_sample_paths=target_degraded_paths,
                            ecmp_degraded_disabled_interfaces=degraded_disabled_interfaces,
                            ecmp_degraded_hold_window=degraded_hold_window,
                            interfaces_of_interest=analysis_interfaces_of_interest,
                            interface_speeds=interface_speeds,
                            q8_taildrop_growth=q8_taildrop_growth,
                            default_interval_seconds=max(1, int(args.post_sample_interval or 10)),
                            traffic_start_mode=args.traffic_start_mode,
                            ecmp_spec_tolerance_pct=args.ecmp_spec_tolerance_pct,
                        )

                        per_target_reports.append(
                            {
                                "entity": target_entity,
                                "node": target_node,
                                "interface": target_interface,
                                "status": "ok",
                                "analysis": ecmp_report.get("analysis", {}),
                                "baseline_summary": ecmp_report.get("baseline_summary", {}),
                                "degraded_summary": ecmp_report.get("degraded_summary", {}),
                                "recovery_summary": ecmp_report.get("recovery_summary", {}),
                                "raw_report": ecmp_report,
                            }
                        )

                    except Exception as exc:
                        per_target_reports.append(
                            {
                                "entity": target_entity,
                                "node": target_node,
                                "interface": target_interface,
                                "status": "failed",
                                "error": str(exc),
                                "analysis": {},
                                "baseline_summary": {},
                                "recovery_summary": {},
                            }
                        )

                ecmp_report_path = os.path.join(
                    "artifacts",
                    "campaigns",
                    args.run_id,
                    "ecmp_recovery_rates.json",
                )

                aggregate_ecmp_report = {
                    "mode": "per_target",
                    "target_count": len(per_target_reports),
                    "targets": per_target_reports,
                    "summary": {
                        "ok_targets": sum(1 for x in per_target_reports if x["status"] == "ok"),
                        "failed_targets": sum(1 for x in per_target_reports if x["status"] == "failed"),
                        "skipped_targets": sum(1 for x in per_target_reports if x["status"] == "skipped"),
                    },
                }

                write_ecmp_recovery_report(
                    out_path=ecmp_report_path,
                    report=aggregate_ecmp_report,
                )

                file_overrides["ecmp_recovery_rates"] = ecmp_report_path
                file_overrides["ecmp_recovery_analysis"] = aggregate_ecmp_report
                progress.info(f"ECMP per-target recovery analysis complete: {ecmp_report_path}")
            except Exception as exc:
                progress.warn(f"ECMP recovery analysis failed: {exc}")

        progress.stage("WRITE_SUMMARY_AND_FINAL_REPORT")
        summary_path = os.path.join("artifacts", "campaigns", args.run_id, "rca_case_summary.json")

        write_summary(
            run_id=args.run_id,
            intent_name=args.intent_name,
            src=args.src,
            dst=args.dst,
            profile=args.profile,
            nodes=args.nodes,
            out_path=summary_path,
            stress_orchestrator_report=args.stress_orchestrator_report,
            status=status,
            files_override=file_overrides,
            intent_rca_status=intent_rca_status,
            baseline_window=args.baseline_window,
            running_decay=args.running_decay,
            settle_gap=args.settle_gap,
            post_window=args.post_window,
        )

        progress.info(f"RCA case summary written: {summary_path}")

        final_report = write_final_report(
            run_id=args.run_id,
            intent_name=args.intent_name,
            src=args.src,
            dst=args.dst,
            profile=args.profile,
            nodes=args.nodes,
            topology_path=args.topology,
        )
        progress.info(f"RCA final report written: {final_report}")
        progress.stage("RUN_RCA_CASE_COMPLETED")

        print("\nRCA CASE COMPLETED")
        print(f"  Run ID       : {args.run_id}")
        print(f"  Intent       : {args.intent_name}")
        print(f"  Summary      : {summary_path}")
        print(f"  Final Report : {final_report}")
        return 0

    except Exception as exc:
        progress.error(f"RUN_RCA_CASE_FATAL: {exc}")
        progress.stage("RUN_RCA_CASE_FAILED")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
