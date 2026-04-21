from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import time
import random
from controller.progress_logger import ProgressLogger
from controller.run_rca_case import (
    inject_phase_delta_into_ui_report,
    telemetry_json_path,
    build_phase_sample_paths,
)
from controller.ecmp_recovery_view import (
    build_ecmp_recovery_input_from_existing_artifacts,
    build_ecmp_recovery_view,
)
from controller.suite_registry import (
    register_run,
    write_suite_summary,
    write_suite_dashboard,
)
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TOPOLOGY = str(BASE_DIR / "artifacts" / "topology" / "topology_full.json")
DEFAULT_UI_SERVER = "http://127.0.0.1:8000"
DEFAULT_IXIA_INVENTORY = str(BASE_DIR / "controller" / "ixia_inventory.json")

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "normal_baseline_no_churn": {
        "stress_mode": "noop",
        "description": "Run RCA, telemetry, IXIA, and RoCE validation with no injected churn event.",
        "expected_behavior": {
            "network": "Fabric remains stable with no injected event.",
            "telemetry": "No transient control-plane or fabric disturbance should appear.",
            "rca": "Any detected hotspot reflects steady-state behavior rather than event-induced churn.",
        },
    },
    "single_interface_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Bounce one explicit or auto-selected fabric interface.",
        "tier": "smoke",
        "maturity": "stable",
        "release_gate": True,
        "recovery_slo_seconds": 30,
        "requires_explicit_target": False,
        "selection_policy": {
            "selection_mode": "manual_or_auto",
            "interface_role": "fabric",
            "blast_radius": "localized",
            "max_targets": 1,
            "prefer_healthy": True,
            "spread_across_nodes": False,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-control-impact",
        ],
        "expected_behavior": {
            "network": "Target fabric link goes down briefly, traffic redistributes, and link recovers cleanly.",
            "telemetry": "Transient interface state changes, bounded ingress/egress drops, and possible alternate-path queue pressure.",
            "rca": "UI should show one interface-bounce event with target node/interface and transient impact classification.",
        },
    },
    "leaf_fabric_parallel_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Bounce one or more fabric-facing interfaces on leaf nodes in parallel.",
        "tier": "production_basic",
        "maturity": "stable",
        "release_gate": True,
        "recovery_slo_seconds": 45,
        "role_filter": ["leaf"],
        "parallel_targets": True,
        "selection_policy": {
            "selection_mode": "auto",
            "interface_role": "fabric",
            "blast_radius": "node_scoped",
            "max_targets_per_node": 1,
            "prefer_healthy": True,
            "spread_across_nodes": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-control-impact",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "Leaf-side path diversity reduces temporarily and traffic shifts to surviving paths.",
            "telemetry": "Potential queue buildup, hotspot movement, and bounded interface discard spikes on alternate paths.",
            "rca": "UI should show grouped or multiple interface-bounce events across leaf fabric links with transient recovery.",
        },
    },
    "spine_fabric_parallel_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Bounce one or more fabric-facing interfaces on spine nodes in parallel.",
        "tier": "production_basic",
        "maturity": "stable",
        "release_gate": True,
        "recovery_slo_seconds": 45,
        "role_filter": ["spine"],
        "parallel_targets": True,
        "selection_policy": {
            "selection_mode": "auto",
            "interface_role": "fabric",
            "blast_radius": "corridor_scoped",
            "max_targets_per_node": 1,
            "prefer_healthy": True,
            "spread_across_nodes": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "Spine capacity reduces temporarily and traffic rebalances across remaining paths.",
            "telemetry": "Potential congestion on surviving spine corridors with bounded recovery.",
            "rca": "UI should show multi-target interface-bounce event impact across the fabric.",
        },
    },
    "all_fabric_parallel_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Bounce all selected fabric-facing interfaces on leaf and spine nodes in parallel.",
        "tier": "production_extended",
        "maturity": "beta",
        "release_gate": False,
        "recovery_slo_seconds": 60,
        "role_filter": ["leaf", "spine"],
        "parallel_targets": True,
        "selection_policy": {
            "selection_mode": "auto",
            "interface_role": "fabric",
            "blast_radius": "fabric_wide",
            "max_targets_per_node": "all",
            "prefer_healthy": True,
            "spread_across_nodes": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "Broad fabric disruption with reduced path diversity and transient instability.",
            "telemetry": "Broader hotspot spread, stronger interface discard spikes, and stronger impact across alternate paths.",
            "rca": "UI should show broad multi-target event mapping with clear corridor impact.",
        },
    },
    "selected_nodes_parallel_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Bounce all fabric-facing interfaces only on explicitly selected nodes.",
        "tier": "production_extended",
        "maturity": "stable",
        "release_gate": True,
        "recovery_slo_seconds": 45,
        "parallel_targets": True,
        "requires_selected_nodes": True,
        "selection_policy": {
            "selection_mode": "selected_nodes",
            "interface_role": "fabric",
            "blast_radius": "bounded_selected_nodes",
            "max_targets_per_node": "all",
            "prefer_healthy": True,
            "spread_across_nodes": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-control-impact",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "Targeted node-group disruption with bounded impact.",
            "telemetry": "Localized congestion or path movement around selected nodes.",
            "rca": "UI should correlate event only to the selected node set.",
        },
    },
    # Planned next-stage scenarios
    "repeated_link_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Bounce the same fabric-facing interface repeatedly to expose stale-state or cumulative degradation issues.",
        "tier": "production_basic",
        "maturity": "planned",
        "release_gate": True,
        "recovery_slo_seconds": 30,
        "requires_explicit_target": True,
        "selection_policy": {
            "selection_mode": "manual_or_auto",
            "interface_role": "fabric",
            "blast_radius": "localized",
            "max_targets": 1,
            "prefer_healthy": True,
            "spread_across_nodes": False,
        },
        "expected_classifications": [
            "expected-transient-control-impact",
            "expected-ecn-pressure",
        ],
        "expected_behavior": {
            "network": "Repeated transient path loss with clean recovery after each iteration.",
            "telemetry": "No cumulative queue buildup, no cumulative interface errors, no persistent post-state anomaly.",
            "rca": "UI should show repeatable transient events without growing bug signals.",
        },
    },
    "bgp_clear_selected_nodes": {
        "stress_mode": "bgp_clear",
        "description": "Clear BGP neighbors on explicitly selected nodes under active traffic.",
        "requires_selected_nodes": True,
        "node_only_targets": True,
        "expected_behavior": {
            "network": "Transient control-plane reconvergence while physical links remain up.",
            "telemetry": "Short-lived control queue movement and routing convergence activity.",
            "rca": "UI should correlate BGP clear with bounded control-plane symptoms and clean recovery.",
        },
    },
    "bgp_evpn_flap_under_load": {
        "stress_mode": "bgp_evpn_flap",
        "description": "Flap BGP/EVPN control-plane sessions during active traffic to validate bounded reconvergence.",
        "tier": "production_basic",
        "maturity": "planned",
        "release_gate": True,
        "recovery_slo_seconds": 60,
        "selection_policy": {
            "selection_mode": "auto",
            "session_role": "control_plane",
            "blast_radius": "bounded_control",
            "prefer_healthy": True,
        },
        "expected_classifications": [
            "expected-transient-control-impact",
        ],
        "expected_behavior": {
            "network": "Routing control-plane reconverges with bounded transient traffic impact.",
            "telemetry": "Transient control-queue pressure may occur but should recover.",
            "rca": "UI should correlate the event to control-plane recovery rather than sustained data-plane damage.",
        },
    },
    "queue_pressure_plus_bounce": {
        "stress_mode": "combined_queue_pressure_bounce",
        "description": "Inject queue pressure and bounce one relevant fabric link to validate QoS behavior under reconvergence.",
        "tier": "production_extended",
        "maturity": "planned",
        "release_gate": True,
        "recovery_slo_seconds": 45,
        "selection_policy": {
            "selection_mode": "auto",
            "interface_role": "fabric",
            "blast_radius": "localized",
            "max_targets": 1,
            "prefer_healthy": True,
            "prefer_traffic_carrying": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-control-impact",
        ],
        "expected_behavior": {
            "network": "Traffic shifts during queue stress and reconverges without sustained damage.",
            "telemetry": "Expected ECN pressure may rise; tail-drop on protected/lossless queues should not persist.",
            "rca": "UI should differentiate expected congestion from real queue pathology.",
        },
    },
        "random_single_fabric_port_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Randomly pick one fabric-facing interface and bounce it.",
        "tier": "production_basic",
        "maturity": "planned",
        "release_gate": True,
        "recovery_slo_seconds": 30,
        "requires_explicit_target": False,
        "selection_policy": {
            "selection_mode": "random_single",
            "interface_role": "fabric",
            "blast_radius": "localized",
            "max_targets": 1,
            "prefer_healthy": True,
            "spread_across_nodes": False,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-control-impact",
        ],
        "expected_behavior": {
            "network": "One randomly selected fabric link goes down briefly and traffic redistributes cleanly.",
            "telemetry": "Transient queue or ingress/egress movement may occur on alternate paths.",
            "rca": "UI should show one randomly selected interface-bounce event with bounded impact.",
        },
    },
    "random_one_port_per_node_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Randomly pick one fabric-facing interface per selected node and bounce them in parallel.",
        "tier": "production_basic",
        "maturity": "planned",
        "release_gate": True,
        "recovery_slo_seconds": 45,
        "parallel_targets": True,
        "requires_selected_nodes": True,
        "selection_policy": {
            "selection_mode": "random_one_per_node",
            "interface_role": "fabric",
            "blast_radius": "bounded_selected_nodes",
            "prefer_healthy": True,
            "spread_across_nodes": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "One random fabric member per selected node is removed and restored with bounded distributed impact.",
            "telemetry": "Transient hotspot movement and queue shifts may occur but should recover.",
            "rca": "UI should show one bounced fabric target per selected node.",
        },
    },
    "random_n_fabric_ports_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Randomly pick N fabric-facing interfaces across the candidate set and bounce them.",
        "tier": "production_extended",
        "maturity": "planned",
        "release_gate": False,
        "recovery_slo_seconds": 45,
        "parallel_targets": True,
        "selection_policy": {
            "selection_mode": "random_n",
            "interface_role": "fabric",
            "blast_radius": "bounded_random_set",
            "prefer_healthy": True,
            "spread_across_nodes": True,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "Randomly selected fabric links are removed and restored with bounded churn.",
            "telemetry": "Transient queue pressure and path movement may appear around affected corridors.",
            "rca": "UI should correlate the event to the random target set selected for the run.",
        },
    },
    "repeated_random_bounce": {
        "stress_mode": "interface_bounce",
        "description": "Repeatedly bounce a random fabric-facing interface target across iterations.",
        "tier": "production_extended",
        "maturity": "planned",
        "release_gate": False,
        "recovery_slo_seconds": 45,
        "selection_policy": {
            "selection_mode": "random_single",
            "interface_role": "fabric",
            "blast_radius": "localized_randomized",
            "prefer_healthy": True,
            "spread_across_nodes": False,
        },
        "expected_classifications": [
            "expected-transient-control-impact",
            "expected-ecn-pressure",
        ],
        "expected_behavior": {
            "network": "A different or random fabric target may be bounced each iteration with clean recovery.",
            "telemetry": "No progressive degradation should accumulate across random bounce iterations.",
            "rca": "UI should still show bounded transient event impact for each run.",
        },
    },
    "all_fabric_if_down_up_single_node": {
        "stress_mode": "interface_bounce",
        "description": "Bounce all fabric-facing interfaces on one selected node.",
        "tier": "production_extended",
        "maturity": "planned",
        "release_gate": True,
        "recovery_slo_seconds": 60,
        "parallel_targets": True,
        "requires_selected_nodes": True,
        "selection_policy": {
            "selection_mode": "all_on_one_selected_node",
            "interface_role": "fabric",
            "blast_radius": "single_node_all_fabric",
            "prefer_healthy": True,
            "spread_across_nodes": False,
        },
        "expected_classifications": [
            "expected-ecn-pressure",
            "expected-transient-fabric-reconvergence",
        ],
        "expected_behavior": {
            "network": "All fabric links on one selected node are removed and restored together.",
            "telemetry": "Broader but node-bounded hotspot spread may occur and should recover.",
            "rca": "UI should show a single-node broad fabric interface event with bounded recovery.",
        },
    },
}
SUITES: Dict[str, List[str]] = {
    "smoke": [
        "single_interface_bounce",
    ],

    "production_basic": [
        "single_interface_bounce",
        "leaf_fabric_parallel_bounce",
        "spine_fabric_parallel_bounce",
        # promote here after validation
        # "repeated_link_bounce",
        # "bgp_evpn_flap_under_load",
    ],

    "production_extended": [
        "single_interface_bounce",
        "leaf_fabric_parallel_bounce",
        "spine_fabric_parallel_bounce",
        "selected_nodes_parallel_bounce",
        # promote here after validation
        # "repeated_link_bounce",
        # "bgp_evpn_flap_under_load",
        # "queue_pressure_plus_bounce",
    ],

    "master_release": [
        "single_interface_bounce",
        "leaf_fabric_parallel_bounce",
        "spine_fabric_parallel_bounce",
        "selected_nodes_parallel_bounce",
        # promote here only after stable validation
        # "repeated_link_bounce",
        # "bgp_evpn_flap_under_load",
        # "queue_pressure_plus_bounce",
    ],

    "chaos_extended": [
        "all_fabric_parallel_bounce",
    ],
        "production_basic": [
        "single_interface_bounce",
        "leaf_fabric_parallel_bounce",
        "spine_fabric_parallel_bounce",
        "random_single_fabric_port_bounce",
        "random_one_port_per_node_bounce",
    ],

    "production_extended": [
        "single_interface_bounce",
        "leaf_fabric_parallel_bounce",
        "spine_fabric_parallel_bounce",
        "selected_nodes_parallel_bounce",
        "random_single_fabric_port_bounce",
        "random_one_port_per_node_bounce",
        "random_n_fabric_ports_bounce",
        "repeated_link_bounce",
        "repeated_random_bounce",
        "all_fabric_if_down_up_single_node",
    ],

    "chaos_extended": [
        "all_fabric_parallel_bounce",
        "all_fabric_if_down_up_single_node",
        "random_n_fabric_ports_bounce",
    ],
}

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def write_json(path: str, data: Any) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)

def phase_samples_dir(run_id: str) -> str:
    return os.path.join("artifacts", "campaigns", run_id, "phase_samples")

def phase_samples_path(run_id: str, phase_name: str) -> str:
    return os.path.join(phase_samples_dir(run_id), f"{phase_name}.json")


def inject_ecmp_recovery_view_into_ui_report(
    *,
    case_summary_path: str,
    ui_report_path: str,
    progress=None,
) -> None:
    case_summary = load_json(case_summary_path)
    ui_report = load_json(ui_report_path)

    ecmp_input = build_ecmp_recovery_input_from_existing_artifacts(
        case_summary=case_summary,
        ui_report=ui_report,
    )
    ui_report["ecmp_recovery_input"] = ecmp_input

    ui_report["ecmp_recovery_view"] = build_ecmp_recovery_view(
        case_summary=case_summary,
        ui_report=ui_report,
    )

    target_debug = None
    for t in (ui_report.get("ecmp_recovery_view", {}) or {}).get("targets", []):
        if t.get("target_id") == "leaf1:et-0/0/11~0":
            target_debug = {
                "target_id": t.get("target_id"),
                "has_baseline_same_speed_group_view": "baseline_same_speed_group_view" in t,
                "has_recovery_same_speed_group_view": "recovery_same_speed_group_view" in t,
                "baseline_same_speed_group_view": t.get("baseline_same_speed_group_view"),
                "recovery_same_speed_group_view": t.get("recovery_same_speed_group_view"),
            }
            break

    if progress:
        progress.info(f"ecmp_same_speed_debug={target_debug}")

    write_json(Path(ui_report_path), ui_report)

    if progress:
        progress.info("ecmp_recovery_view_injected=true")


def collect_queue_snapshot_for_phase(
    *,
    run_id: str,
    phase_name: str,
    sample_index: int,
    profile: str,
    nodes: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Wrapper hook for your existing telemetry collection.
    Replace the commented command invocation with however you already collect telemetry snapshots.
    """

    snapshot_name = f"{phase_name}_{sample_index:03d}"

    # Replace this with your existing collection path / function.
    # Example shell command shape only:
    #
    # cmd = (
    #   f"python -m controller.telemetry_monitor "
    #   f"--source-type campaign "
    #   f"--run-id {run_id} "
    #   f"--snapshot-name {snapshot_name} "
    #   f"--profile {profile} "
    #   f"--nodes {nodes} "
    #   f"--timeout {timeout}"
    # )
    # os.system(cmd)
    #
    # Then load the generated telemetry json.

    telemetry_path = os.path.join(
        "artifacts",
        "campaigns",
        run_id,
        "telemetry",
        f"{snapshot_name}_{profile}.json",
    )

    payload: Dict[str, Any] = {
        "phase": phase_name,
        "sample_index": sample_index,
        "snapshot_name": snapshot_name,
        "telemetry_path": telemetry_path,
        "captured_at_epoch": time.time(),
    }

    return payload

def collect_phase_window(
    *,
    run_id: str,
    phase_name: str,
    duration_seconds: int,
    interval_seconds: int,
    profile: str,
    nodes: str,
    timeout: int = 30,
    logger=None,
) -> Dict[str, Any]:
    """
    Collect repeated telemetry snapshots for a named phase window.
    """
    sample_count = max(1, math.ceil(duration_seconds / max(interval_seconds, 1)))

    if logger:
        logger.info(
            "[PHASE] collecting %s window: duration=%ss interval=%ss samples=%s",
            phase_name,
            duration_seconds,
            interval_seconds,
            sample_count,
        )

    samples: List[Dict[str, Any]] = []
    started = time.time()

    for idx in range(sample_count):
        sample = collect_queue_snapshot_for_phase(
            run_id=run_id,
            phase_name=phase_name,
            sample_index=idx,
            profile=profile,
            nodes=nodes,
            timeout=timeout,
        )
        samples.append(sample)

        if logger:
            logger.info(
                "[PHASE] %s sample %s/%s snapshot=%s",
                phase_name,
                idx + 1,
                sample_count,
                sample.get("snapshot_name"),
            )

        if idx < sample_count - 1:
            time.sleep(interval_seconds)

    payload = {
        "phase_name": phase_name,
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "sample_count": sample_count,
        "started_at_epoch": started,
        "ended_at_epoch": time.time(),
        "samples": samples,
    }

    write_json(phase_samples_path(run_id, phase_name), payload)
    return payload


def progress_log_path_for_run(run_id: str) -> str:
    return str(BASE_DIR / "artifacts" / "campaigns" / run_id / "run_progress.log")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def ensure_exists(path: str | Path, label: str) -> None:
    if not Path(path).exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def run_subprocess(cmd: List[str], label: str) -> None:
    print(f"\n[{label}] Running:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with rc={result.returncode}")


def normalize_role(value: str | None) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    if "leaf" in v:
        return "leaf"
    if "spine" in v:
        return "spine"
    return v


def sanitize_name(value: str) -> str:
    return (
        value.strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace(":", "~")
        .replace("-", "_")
        .lower()
    )

def normalize_phase_timing_args(args: argparse.Namespace) -> None:
    """
    Normalize legacy and new timing knobs so the runner always passes
    consistent phase windows into run_rca_case().

    Priority:
      explicit new flags > legacy baseline_window/post_window > defaults
    """

    # Backward-compatible aliases
    if getattr(args, "pre_baseline_duration", None):
        args.baseline_window = int(args.pre_baseline_duration)

    if getattr(args, "post_recovery_duration", None):
        args.post_window = int(args.post_recovery_duration)

    # If caller still uses post-sample-count + post-sample-interval,
    # ensure post_window is large enough to cover the intended recovery series.
    sample_count = max(1, int(getattr(args, "post_sample_count", 1) or 1))
    sample_interval = max(1, int(getattr(args, "post_sample_interval", 1) or 1))
    sampled_post_duration = sample_count * sample_interval

    if sampled_post_duration > int(args.post_window):
        args.post_window = sampled_post_duration

    # post_wait should never be shorter than the effective post window,
    # otherwise the downstream flow can observe less than intended.
    if int(args.post_wait) < int(args.post_window):
        args.post_wait = int(args.post_window)

    # Keep values sane
    args.baseline_window = max(1, int(args.baseline_window))
    args.running_decay = max(0, int(args.running_decay))
    args.settle_gap = max(0, int(args.settle_gap))
    args.post_window = max(1, int(args.post_window))
    args.post_wait = max(1, int(args.post_wait))

def get_release_gate_scenarios() -> List[str]:
    return [
        name for name, meta in SCENARIOS.items()
        if meta.get("release_gate")
    ]


def get_scenarios_by_tier(tier: str) -> List[str]:
    return [
        name for name, meta in SCENARIOS.items()
        if meta.get("tier") == tier
    ]

def check_ui_server(url: str) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=2) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def extract_node_roles(topology: Dict[str, Any]) -> Dict[str, str]:
    role_map: Dict[str, str] = {}
    nodes_obj = topology.get("nodes")

    if isinstance(nodes_obj, list):
        for item in nodes_obj:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("node") or item.get("id") or item.get("hostname")
            role = (
                item.get("role")
                or item.get("type")
                or item.get("node_role")
                or item.get("device_role")
            )
            if name:
                role_map[str(name)] = normalize_role(str(role))
    elif isinstance(nodes_obj, dict):
        for name, item in nodes_obj.items():
            if isinstance(item, dict):
                role = (
                    item.get("role")
                    or item.get("type")
                    or item.get("node_role")
                    or item.get("device_role")
                )
                role_map[str(name)] = normalize_role(str(role))
            else:
                role_map[str(name)] = ""

    return role_map


def extract_link_endpoints(link: Dict[str, Any]) -> Optional[Tuple[str, str, str, str]]:
    candidates = [
        ("node1", "interface1", "node2", "interface2"),
        ("node1", "intf1", "node2", "intf2"),
        ("a_node", "a_intf", "z_node", "z_intf"),
        ("src_node", "src_interface", "dst_node", "dst_interface"),
        ("local_node", "local_interface", "remote_node", "remote_interface"),
        ("local_node", "local_intf", "peer_node", "peer_intf"),
        ("local_node", "local_intf", "remote_node", "remote_intf"),
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
    ep2 = link.get("endpoint2") or link.get("z") or link.get("dst") or link.get("remote") or link.get("peer")

    if isinstance(ep1, dict) and isinstance(ep2, dict):
        n1 = ep1.get("node") or ep1.get("device") or ep1.get("name") or ep1.get("hostname")
        i1 = ep1.get("interface") or ep1.get("intf") or ep1.get("port") or ep1.get("name")
        n2 = ep2.get("node") or ep2.get("device") or ep2.get("name") or ep2.get("hostname")
        i2 = ep2.get("interface") or ep2.get("intf") or ep2.get("port") or ep2.get("name")
        if n1 and i1 and n2 and i2:
            return str(n1), str(i1), str(n2), str(i2)

    return None


def extract_fabric_interfaces(topology: Dict[str, Any]) -> List[Dict[str, str]]:
    role_map = extract_node_roles(topology)
    links = topology.get("links") or topology.get("edges") or topology.get("connections") or []

    interface_targets: Dict[Tuple[str, str], Dict[str, str]] = {}

    for link in links:
        if not isinstance(link, dict):
            continue

        endpoints = extract_link_endpoints(link)
        if not endpoints:
            continue

        node1, intf1, node2, intf2 = endpoints

        role1 = normalize_role(role_map.get(node1))
        role2 = normalize_role(role_map.get(node2))

        if role1 and role2:
            valid_roles = {"leaf", "spine"}
            if role1 not in valid_roles or role2 not in valid_roles:
                continue

        interface_targets[(node1, intf1)] = {"node": node1, "interface": intf1}
        interface_targets[(node2, intf2)] = {"node": node2, "interface": intf2}

    return sorted(interface_targets.values(), key=lambda x: (x["node"], x["interface"]))



def filter_targets_by_roles(
    topology: Dict[str, Any],
    targets: List[Dict[str, str]],
    role_filter: Optional[List[str]] = None,
    selected_nodes: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    role_map = extract_node_roles(topology)
    role_filter_norm = {normalize_role(r) for r in (role_filter or [])}
    selected_nodes_set = {n.strip() for n in (selected_nodes or []) if n.strip()}

    filtered: List[Dict[str, str]] = []
    for item in targets:
        node = item["node"]
        role = normalize_role(role_map.get(node))

        if role_filter_norm and role not in role_filter_norm:
            continue

        if selected_nodes_set and node not in selected_nodes_set:
            continue

        filtered.append(item)

    return filtered

def pick_single_auto_target(
    topology: Dict[str, Any],
    targets: List[Dict[str, str]],
    selected_nodes: Optional[List[str]] = None,
) -> Dict[str, str]:
    selected_nodes_set = {n.strip() for n in (selected_nodes or []) if n.strip()}

    candidates = targets
    if selected_nodes_set:
        candidates = [t for t in targets if t["node"] in selected_nodes_set]

    if not candidates:
        raise RuntimeError("no candidate targets available for auto single-interface selection")

    # deterministic selection for now: first sorted candidate
    # later we can enhance to prefer healthiest / traffic-carrying / corridor-relevant
    candidates = sorted(candidates, key=lambda x: (x["node"], x["interface"]))
    return candidates[0]


def parse_explicit_targets(raw: str) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    if not raw.strip():
        return result

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if ":" not in part:
            raise ValueError(f"invalid target '{part}', expected node:interface")
        node, interface = part.split(":", 1)
        result.append({"node": node.strip(), "interface": interface.strip()})
    return result

def pick_random_targets(
    *,
    targets: List[Dict[str, str]],
    selection_mode: str,
    selected_nodes: Optional[List[str]] = None,
    random_count: Optional[int] = None,
) -> List[Dict[str, str]]:
    if not targets:
        raise RuntimeError("no candidate targets available for random selection")

    candidates = list(targets)
    random.shuffle(candidates)

    if selection_mode == "random_single":
        return [candidates[0]]

    if selection_mode == "random_one_per_node":
        selected_nodes_set = {n.strip() for n in (selected_nodes or []) if n.strip()}
        if selected_nodes_set:
            candidates = [t for t in candidates if t["node"] in selected_nodes_set]

        by_node: Dict[str, Dict[str, str]] = {}
        for item in candidates:
            if item["node"] not in by_node:
                by_node[item["node"]] = item

        resolved = list(sorted(by_node.values(), key=lambda x: (x["node"], x["interface"])))
        if not resolved:
            raise RuntimeError("no candidate targets available for random_one_per_node selection")
        return resolved

    if selection_mode == "random_n":
        n = max(1, int(random_count or 2))
        return list(sorted(candidates[:n], key=lambda x: (x["node"], x["interface"])))

    raise ValueError(f"unsupported random selection_mode={selection_mode}")

def load_device_facts_for_node(target_node: str) -> Dict[str, Any]:
    device_facts_dir = os.path.join("artifacts", "device_facts")
    candidate_paths = [
        os.path.join(device_facts_dir, f"{target_node}_facts.json"),
        os.path.join(device_facts_dir, f"{str(target_node).lower()}_facts.json"),
        os.path.join(device_facts_dir, f"{str(target_node).upper()}_facts.json"),
    ]

    facts_path = None
    facts_data: Dict[str, Any] = {}

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
                    probe = json.load(fh)
                if str(probe.get("node_name", "")).strip().lower() == str(target_node).strip().lower():
                    facts_path = path
                    facts_data = probe
                    break
            except Exception:
                continue

    if facts_path and not facts_data:
        with open(facts_path, "r", encoding="utf-8") as fh:
            facts_data = json.load(fh)

    return facts_data

import re

def extract_fabric_interfaces_from_device_facts(target_node: str) -> List[Dict[str, str]]:
    facts_data = load_device_facts_for_node(target_node)
    if not facts_data:
        return []

    interface_speeds = facts_data.get("interface_speeds", {}) or {}
    lldp_neighbors = facts_data.get("lldp_neighbors", "") or ""

    lldp_interfaces = set()
    for line in str(lldp_neighbors).splitlines():
        line = line.strip()
        if not line or line.startswith("Local Interface"):
            continue
        parts = line.split()
        if parts:
            lldp_interfaces.add(parts[0])

    targets: List[Dict[str, str]] = []

    for interface_name in sorted(interface_speeds.keys()):
        if lldp_interfaces and interface_name not in lldp_interfaces:
            continue
        targets.append({"node": target_node, "interface": interface_name})

    return targets

def resolve_targets_for_scenario(
    scenario_name: str,
    topology_path: str,
    explicit_node: Optional[str],
    explicit_interface: Optional[str],
    explicit_targets: Optional[str],
    selected_nodes_raw: Optional[str],
    one_per_node: bool,
) -> List[Dict[str, str]]:
    scenario = SCENARIOS[scenario_name]

    # Manual target always wins
    if explicit_node and explicit_interface:
        return [{"node": explicit_node, "interface": explicit_interface}]

    # Explicit targets override topology resolution
    if explicit_targets:
        targets = parse_explicit_targets(explicit_targets)
        if scenario_name == "single_interface_bounce" and len(targets) != 1:
            raise ValueError("single_interface_bounce requires exactly one target when using --targets")
        return targets

    topology = load_json(topology_path)
    all_targets = extract_fabric_interfaces(topology)
    if not all_targets:
        raise RuntimeError(f"could not resolve fabric interfaces from topology: {topology_path}")

    selected_nodes = [n.strip() for n in (selected_nodes_raw or "").split(",") if n.strip()]
    role_filter = scenario.get("role_filter")
    selection_policy = scenario.get("selection_policy", {}) or {}
    selection_mode = selection_policy.get("selection_mode", "")

    if scenario.get("requires_selected_nodes") and not selected_nodes:
        raise ValueError(f"{scenario_name} requires --selected-nodes")

    filtered = filter_targets_by_roles(
        topology=topology,
        targets=all_targets,
        role_filter=role_filter,
        selected_nodes=selected_nodes,
    )

    if not filtered:
        raise RuntimeError(f"no targets resolved for scenario={scenario_name}")

    if scenario.get("node_only_targets"):
        node_targets = [{"node": item["node"]} for item in filtered]
        deduped: Dict[str, Dict[str, str]] = {}
        for item in node_targets:
            deduped.setdefault(item["node"], item)
        return list(sorted(deduped.values(), key=lambda x: x["node"]))

    # New random selection modes
    if selection_mode in ("random_single", "random_one_per_node", "random_n"):
        random_count = selection_policy.get("random_count")
        return pick_random_targets(
            targets=filtered,
            selection_mode=selection_mode,
            selected_nodes=selected_nodes,
            random_count=random_count,
        )

    # New all-fabric-on-one-selected-node mode
    if selection_mode == "all_on_one_selected_node":
        if not selected_nodes:
            raise ValueError(f"{scenario_name} requires exactly one node in --selected-nodes")
        if len(selected_nodes) != 1:
            raise ValueError(f"{scenario_name} requires exactly one selected node")

        node_name = selected_nodes[0]

        device_fact_targets = extract_fabric_interfaces_from_device_facts(node_name)
        if device_fact_targets:
            return list(sorted(device_fact_targets, key=lambda x: (x["node"], x["interface"])))

        node_targets = [t for t in filtered if t["node"] == node_name]
        if not node_targets:
            raise RuntimeError(f"no fabric interfaces found for selected node={node_name}")
        return list(sorted(node_targets, key=lambda x: (x["node"], x["interface"])))

    # Existing one-per-node narrowing
    if one_per_node:
        by_node: Dict[str, Dict[str, str]] = {}
        for item in filtered:
            by_node.setdefault(item["node"], item)
        filtered = list(sorted(by_node.values(), key=lambda x: (x["node"], x["interface"])))

    return filtered



def write_resolved_targets_artifacts(
    *,
    run_id: str,
    scenario_name: str,
    release_tag: Optional[str],
    target_mode: str,
    targets: List[Dict[str, str]],
) -> Dict[str, str]:
    run_dir = BASE_DIR / "artifacts" / "campaigns" / run_id
    repro_dir = BASE_DIR / "artifacts" / "repro_targets"
    run_dir.mkdir(parents=True, exist_ok=True)
    repro_dir.mkdir(parents=True, exist_ok=True)

    if targets and all(t.get("interface") for t in targets):
        targets_arg = ",".join(f"{t['node']}:{t['interface']}" for t in targets)
    else:
        targets_arg = ",".join(f"{t['node']}" for t in targets)

    payload = {
        "run_id": run_id,
        "scenario": scenario_name,
        "release_tag": release_tag,
        "target_mode": target_mode,
        "generated_at": utc_now_iso(),
        "resolved_target_count": len(targets),
        "targets": targets,
        "targets_arg": targets_arg,
    }

    run_json = run_dir / "resolved_targets.json"
    run_txt = run_dir / "resolved_targets.txt"
    repro_json = repro_dir / f"{run_id}.json"
    repro_txt = repro_dir / f"{run_id}.txt"

    write_json(run_json, payload)
    write_json(repro_json, payload)

    text = [
        f"Run ID              : {run_id}",
        f"Scenario            : {scenario_name}",
        f"Release Tag         : {release_tag or '-'}",
        f"Target Mode         : {target_mode}",
        f"Resolved Count      : {len(targets)}",
        f"Targets Arg         : {targets_arg}",
        "",
        "Resolved Targets:",
    ]
    text.extend([
        f"  - {t['node']}:{t['interface']}" if t.get("interface") else f"  - {t['node']}"
        for t in targets
    ])
    run_txt.write_text("\n".join(text) + "\n", encoding="utf-8")
    repro_txt.write_text("\n".join(text) + "\n", encoding="utf-8")

    return {
        "run_json": str(run_json),
        "run_txt": str(run_txt),
        "repro_json": str(repro_json),
        "repro_txt": str(repro_txt),
        "targets_arg": targets_arg,
    }

def run_stress_event(
    *,
    scenario_name: str,
    stress_run_id: str,
    targets: List[Dict[str, str]],
    settle_seconds: int,
    interval_seconds: int,
    stop_on_failure: bool,
    stress_iterations: int,
    pre_event_stabilize_seconds: int,
    strict_pre_event_gate: bool,
    ixia_inventory: Optional[str],
    ixia_session_id: Optional[int],
    profile: str,
    nodes: str,
    timeout: int,
    topology: str,
) -> str:
    stress_mode = SCENARIOS[scenario_name]["stress_mode"]

    cmd = [
        sys.executable,
        "-m",
        "controller.stress_orchestrator",
        "--mode",
        stress_mode,
        "--run-id",
        stress_run_id,
        "--settle-seconds",
        str(settle_seconds),
        "--interval-seconds",
        str(interval_seconds),
        "--iterations",
        str(stress_iterations),
        "--pre-event-stabilize-seconds",
        str(pre_event_stabilize_seconds),
    ]


    if ixia_inventory:
        cmd.extend(["--ixia-inventory", ixia_inventory])

    if ixia_session_id is not None:
        cmd.extend(["--ixia-session-id", str(ixia_session_id)])

    if profile:
        cmd.extend(["--baseline-profile", profile])
    

    if nodes:
        cmd.extend(["--baseline-nodes", nodes])

    if timeout is not None:
        cmd.extend(["--baseline-timeout", str(timeout)])

    if topology:
        cmd.extend(["--baseline-topology", topology])
    if stop_on_failure:
        cmd.append("--stop-on-failure")

    if strict_pre_event_gate:
        cmd.append("--strict-pre-event-gate")

    if targets:
        if stress_mode == "bgp_clear":
            targets_arg = ",".join(
                f"{t['node']}" for t in targets if t.get("node")
            )
        else:
            targets_arg = ",".join(
                f"{t['node']}|{t['interface']}"
                for t in targets
                if t.get("node") and t.get("interface")
            )

        if targets_arg:
            cmd.extend(["--targets", targets_arg])
            cmd.extend(["--parallel", str(len(targets))])

    run_subprocess(cmd, "STRESS_ORCHESTRATOR")

    json_out = BASE_DIR / "artifacts" / "orchestrator" / stress_run_id / "stress_orchestrator_report.json"
    ensure_exists(str(json_out), "stress_orchestrator_report.json")
    return str(json_out)

def run_rca_case(
    *,
    rca_run_id: str,
    src: str,
    dst: str,
    intent_name: str,
    nodes: str,
    profile: str,
    phase_profile: str = "hotspot_congestion_qmon_phase",
    timeout: int,
    topology: str,
    top_n: int,
    ixia_inventory: Optional[str],
    ixia_session_id: Optional[int],
    running_wait: int,
    post_wait: int,
    resume_after_post: bool,
    stress_orchestrator_report: str,
    enable_live_monitor: bool,
    live_monitor_iterations: int,
    live_monitor_interval: int,
    enable_port_stats: bool,
    baseline_window: int,
    running_decay: int,
    settle_gap: int,
    post_window: int,
    post_sample_count: int,
    post_sample_interval: int,
    node: Optional[str] = None,
    interface: Optional[str] = None,
) -> str:
    cmd = [
        sys.executable,
        "-m",
        "controller.run_rca_case",
        "--run-id",
        rca_run_id,
        "--src",
        src,
        "--dst",
        dst,
        "--intent-name",
        intent_name,
        "--nodes",
        nodes,
        "--profile",
        profile,
        "--phase-profile",
        phase_profile,
        "--timeout",
        str(timeout),
        "--topology",
        topology,
        "--top-n",
        str(top_n),
        "--running-wait",
        str(running_wait),
        "--post-wait",
        str(post_wait),
        "--stress-orchestrator-report",
        stress_orchestrator_report,
        "--baseline-window",
        str(baseline_window),
        "--running-decay",
        str(running_decay),
        "--settle-gap",
        str(settle_gap),
        "--post-window",
        str(post_window),
        "--post-sample-count",
        str(post_sample_count),
        "--post-sample-interval",
        str(post_sample_interval),
    ]

    if node:
        cmd.extend(["--node", node])

    if interface:
        cmd.extend(["--interface", interface])

    if ixia_inventory:
        cmd.extend(["--ixia-inventory", ixia_inventory])

    if ixia_session_id is not None:
        cmd.extend(["--ixia-session-id", str(ixia_session_id)])

    if resume_after_post:
        cmd.append("--resume-after-post")

    if enable_live_monitor:
        cmd.append("--enable-live-monitor")
        cmd.extend(["--live-monitor-iterations", str(live_monitor_iterations)])
        cmd.extend(["--live-monitor-interval", str(live_monitor_interval)])

    if enable_port_stats:
        cmd.append("--enable-port-stats")

    run_subprocess(cmd, "RCA_CASE")

    summary_path = str(BASE_DIR / "artifacts" / "campaigns" / rca_run_id / "rca_case_summary.json")
    ensure_exists(summary_path, "rca_case_summary.json")
    return summary_path


def run_cos_hotspot_correlation(
    *,
    rca_run_id: str,
    ui_report_path: str,
    telemetry_reference_path: str | None = None,
    baseline_reference_path: str | None = None,
    running_reference_path: str | None = None,
    post_reference_path: str | None = None,
    top_n: int = 5,
) -> str:
    cmd = [
        sys.executable,
        "-m",
        "controller.cos_hotspot_correlator",
        "--run-id",
        rca_run_id,
        "--rca-ui-report",
        ui_report_path,
        "--top-n",
        str(top_n),
    ]

    if baseline_reference_path and running_reference_path and post_reference_path:
        cmd.extend(
            [
                "--baseline-reference",
                baseline_reference_path,
                "--running-reference",
                running_reference_path,
                "--post-reference",
                post_reference_path,
            ]
        )
    elif telemetry_reference_path:
        cmd.extend(["--telemetry-reference", telemetry_reference_path])
    else:
        raise ValueError(
            "run_cos_hotspot_correlation requires either "
            "telemetry_reference_path or all of "
            "baseline_reference_path, running_reference_path, post_reference_path"
        )

    run_subprocess(cmd, "COS_HOTSPOT_CORRELATOR")
    output_path = str(
        BASE_DIR / "artifacts" / "campaigns" / rca_run_id / "cos_hotspot_correlation.json"
    )
    ensure_exists(output_path, "cos_hotspot_correlation.json")
    return output_path



def build_ui_report(case_summary_path: str) -> str:
    cmd = [
        sys.executable,
        "-m",
        "controller.rca_ui_report_builder",
        "--case-summary",
        case_summary_path,
    ]
    run_subprocess(cmd, "RCA_UI_REPORT_BUILDER")

    output_path = str(Path(case_summary_path).parent / "rca_ui_report.json")
    ensure_exists(output_path, "rca_ui_report.json")
    return output_path


def validate_stress_report(path: str, expected_target_count: int) -> Dict[str, Any]:
    data = load_json(path)
    verdict = data.get("overall_status")
    resolved_count = data.get("resolved_target_count")
    iteration_results = data.get("iteration_results", []) or []

    # Some stress reports do not populate resolved_target_count.
    # In that case, fall back to overall_status + iteration presence.
    if resolved_count is None:
        ok = (verdict == "pass") and (len(iteration_results) > 0)
    else:
        ok = (verdict == "pass") and (resolved_count == expected_target_count)

    return {
        "path": path,
        "overall_status": verdict,
        "resolved_target_count": resolved_count,
        "iteration_count": len(iteration_results),
        "ok": ok,
    }

def validate_rca_summary(path: str, expected_stress_path: str) -> Dict[str, Any]:
    data = load_json(path)
    files = data.get("files", {}) or {}
    linked_path = files.get("stress_orchestrator_report")

    return {
        "path": path,
        "run_id": data.get("run_id"),
        "linked_stress_report": linked_path,
        "status": data.get("status", {}),
        "files": files,
        "ok": linked_path == expected_stress_path,
    }


def validate_ui_report(path: str) -> Dict[str, Any]:
    data = load_json(path)
    run_metadata = data.get("run_metadata", {}) or {}
    summary = data.get("summary", {}) or {}
    events = data.get("events", []) or []

    return {
        "path": path,
        "run_id": run_metadata.get("run_id"),
        "event_count": len(events),
        "top_event_name": events[0].get("event_name") if events else "",
        "primary_cause": summary.get("primary_cause", "unknown"),
        "total_hotspots": summary.get("total_hotspots", 0),
        "traffic_health": data.get("traffic_health", {}) or {},
        "telemetry_health": data.get("telemetry_health", {}) or {},
        "bug_candidate_signals": data.get("bug_candidate_signals", []) or [],
        "stress_classification": data.get("stress_classification", {}) or {},
        "ok": bool(run_metadata) and isinstance(events, list) and len(events) > 0,
    }

def build_stress_run_id(
    scenario_name: str,
    release_tag: Optional[str],
    explicit_stress_run_id: Optional[str],
) -> str:
    if explicit_stress_run_id:
        return explicit_stress_run_id

    parts = ["evt"]
    if release_tag:
        parts.append(sanitize_name(release_tag))
    parts.append(sanitize_name(scenario_name))
    parts.append(utc_compact())
    return "_".join(parts)


def build_rca_run_id_for_suite(
    scenario_name: str,
    release_tag: Optional[str],
    suite_run_id: str,
    index: int,
) -> str:
    prefix_parts = []
    if release_tag:
        prefix_parts.append(sanitize_name(release_tag))
    prefix_parts.append(sanitize_name(scenario_name))
    prefix_parts.append(f"{index:03d}")
    return "_".join(prefix_parts)


def load_optional_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return load_json(p)

def _safe_number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_interface_counter_summary(telemetry_analyzer: Dict[str, Any], telemetry_diff: Dict[str, Any]) -> Dict[str, Any]:
    top_anomalies = telemetry_analyzer.get("anomalies", []) or []
    entity_rollup = telemetry_analyzer.get("entity_rollup", {}) or {}
    diff_summary = telemetry_diff.get("summary", {}) or {}

    counters = {
        "in_errors": 0.0,
        "out_errors": 0.0,
        "in_discards": 0.0,
        "out_discards": 0.0,
        "carrier_transitions": 0.0,
    }

    impacted_interfaces: Dict[str, Dict[str, Any]] = {}

    def _touch_interface(node: str, interface: str) -> Dict[str, Any]:
        key = f"{node}|{interface}"
        if key not in impacted_interfaces:
            impacted_interfaces[key] = {
                "node": node,
                "interface": interface,
                "in_errors": 0.0,
                "out_errors": 0.0,
                "in_discards": 0.0,
                "out_discards": 0.0,
                "carrier_transitions": 0.0,
            }
        return impacted_interfaces[key]


    for item in top_anomalies:
        node = str(item.get("node") or item.get("device") or "unknown")
        interface = item.get("interface") or item.get("port")
        if not interface:
            continue
        interface = str(interface)

        metric = str(item.get("metric") or item.get("path") or "").lower()
        value = _safe_number(item.get("value", item.get("delta", 0.0)))

        entry = _touch_interface(node, interface)
        if "in-errors" in metric or metric.endswith("in_errors"):
            counters["in_errors"] += value
            entry["in_errors"] += value
        elif "out-errors" in metric or metric.endswith("out_errors"):
            counters["out_errors"] += value
            entry["out_errors"] += value
        elif "in-discards" in metric or metric.endswith("in_discards"):
            counters["in_discards"] += value
            entry["in_discards"] += value
        elif "out-discards" in metric or metric.endswith("out_discards"):
            counters["out_discards"] += value
            entry["out_discards"] += value
        elif "carrier-transitions" in metric or metric.endswith("carrier_transitions"):
            counters["carrier_transitions"] += value
            entry["carrier_transitions"] += value

    # also scan entity_rollup if available
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
            entry = _touch_interface(node, interface)
            for key, dest in (
                ("in-errors", "in_errors"),
                ("out-errors", "out_errors"),
                ("in-discards", "in_discards"),
                ("out-discards", "out_discards"),
                ("carrier-transitions", "carrier_transitions"),
            ):
                val = _safe_number(rollup.get(key, 0.0))
                if val > 0:
                    counters[dest] += val
                    entry[dest] += val

    top_impacted = sorted(
        impacted_interfaces.values(),
        key=lambda x: (
            -(x["in_discards"] + x["out_discards"] + x["in_errors"] + x["out_errors"]),
            -x["carrier_transitions"],
            x["node"],
            x["interface"],
        ),
    )[:10]

    return {
        "totals": counters,
        "top_impacted_interfaces": top_impacted,
        "diff_summary": diff_summary,
    }

def build_evidence_rollup(rca_summary: Dict[str, Any]) -> Dict[str, Any]:
    files = rca_summary.get("files", {}) or {}
    status = rca_summary.get("status", {}) or {}

    telemetry_analyzer = load_optional_json(files.get("telemetry_analyzer"))
    telemetry_diff = load_optional_json(files.get("telemetry_diff"))
    rocev2_verdict = load_optional_json(files.get("rocev2_verdict"))
    traffic_verifier = load_optional_json(files.get("traffic_verifier"))
    ixia_live_monitor = load_optional_json(files.get("ixia_live_monitor"))
    congestion_inspection = load_optional_json(files.get("congestion_inspection"))
    root_cause_correlation = load_optional_json(files.get("root_cause_correlation"))
    cos_hotspot_correlation = load_optional_json(files.get("cos_hotspot_correlation"))

    live_alerts = 0
    critical_live_alerts = 0
    if ixia_live_monitor.get("iterations"):
        for it in ixia_live_monitor["iterations"]:
            alerts = it.get("alerts", []) or []
            live_alerts += len(alerts)
            critical_live_alerts += sum(1 for a in alerts if a.get("severity") == "critical")

    telemetry_summary = telemetry_analyzer.get("summary", {})
    telemetry_diff_summary = telemetry_diff.get("summary", {})
    interface_drop_health = _extract_interface_counter_summary(telemetry_analyzer, telemetry_diff)
    interface_totals = interface_drop_health.get("totals", {})
    rocev2_summary = rocev2_verdict.get("summary", {})
    traffic_summary = traffic_verifier.get("summary", {})
    congestion_summary = congestion_inspection.get("summary", {})
    root_summary = root_cause_correlation.get("summary", {})
    cos_summary = cos_hotspot_correlation.get("summary", {})
    cos_hotspots = cos_hotspot_correlation.get("hotspots", []) or []

    # ------------------------------------------------------------------
    # Event-aware gating:
    # only escalate many signals if we actually saw event-time queue growth.
    # ------------------------------------------------------------------
    event_congestion = False
    entity_rollup = telemetry_analyzer.get("entity_rollup", {}) or {}

    for item in entity_rollup.values():
        rise_tail = item.get("rise_tail_dropped_packets") or 0
        post_linger = item.get("post_tail_linger_series") or []
        if (rise_tail > 0) or (sum(post_linger) > 0):
            event_congestion = True
            break

    # Traffic/RoCE evidence should only be treated as meaningful when present.
    traffic_available = traffic_verifier.get("verdict") is not None
    rocev2_available = rocev2_verdict.get("verdict") is not None

    bug_signals: List[str] = []

    # ------------------------------------------------------------------
    # Telemetry signals
    # Gate anomaly/diff signals on event-time congestion so background/static
    # anomalies do not automatically escalate the run to BUG-CANDIDATE.
    # ------------------------------------------------------------------
    if telemetry_summary.get("by_severity", {}).get("critical", 0) > 0 and event_congestion:
        bug_signals.append("telemetry_critical_anomaly")
    if telemetry_summary.get("by_severity", {}).get("warning", 0) > 0 and event_congestion:
        bug_signals.append("telemetry_warning_anomaly")
    if telemetry_diff_summary.get("total_differences", 0) > 0 and event_congestion:
        bug_signals.append("telemetry_diff_detected")

    # Keep hard interface counters as direct bug signals, since these are more concrete.
    if interface_totals.get("in_discards", 0) > 0:
        bug_signals.append("interface_ingress_discards_detected")
    if interface_totals.get("out_discards", 0) > 0:
        bug_signals.append("interface_egress_discards_detected")
    if interface_totals.get("in_errors", 0) > 0:
        bug_signals.append("interface_in_errors_detected")
    if interface_totals.get("out_errors", 0) > 0:
        bug_signals.append("interface_out_errors_detected")

    # ------------------------------------------------------------------
    # RoCE / traffic signals
    # Only use them if the corresponding evidence actually exists.
    # ------------------------------------------------------------------
    if rocev2_available and rocev2_verdict.get("verdict") in ("warning", "fail"):
        bug_signals.append(f"rocev2_verdict_{rocev2_verdict.get('verdict')}")
    if rocev2_available and rocev2_summary.get("by_severity", {}).get("critical", 0) > 0:
        bug_signals.append("rocev2_critical_finding")
    if rocev2_available and rocev2_summary.get("by_severity", {}).get("warning", 0) > 0:
        bug_signals.append("rocev2_warning_finding")

    if traffic_available and traffic_verifier.get("verdict") in ("warning", "fail"):
        bug_signals.append(f"traffic_verdict_{traffic_verifier.get('verdict')}")

    # Live monitor alerts should only matter if traffic evidence exists.
    if traffic_available:
        if critical_live_alerts > 0:
            bug_signals.append("ixia_live_critical_alert")
        elif live_alerts > 0:
            bug_signals.append("ixia_live_alert")

    # ------------------------------------------------------------------
    # Congestion / root cause signals
    # Strong hotspots are only meaningful as bug signals when event-time
    # congestion exists.
    # ------------------------------------------------------------------
    top_hotspots = congestion_summary.get("top_hotspots", []) or []
    if top_hotspots and event_congestion:
        top = top_hotspots[0]
        if (top.get("score") or 0) >= 5:
            bug_signals.append("strong_congestion_hotspot")
        if top.get("classification") in ("transport_instability", "port_health_signal"):
            bug_signals.append(f"hotspot_{top.get('classification')}")

    if root_summary.get("top_hotspots") and event_congestion:
        first = root_summary["top_hotspots"][0]
        if first.get("device") and first.get("interface"):
            bug_signals.append("root_cause_mapped_to_dut")

    # ------------------------------------------------------------------
    # CoS correlation signals
    # Count everything for reporting, but only promote strong/manual-review
    # signals when event-time congestion exists.
    # ------------------------------------------------------------------
    localized_mcast = 0
    expected_ecn = 0
    unexpected_lossless = 0
    queue_without_scheduler = 0
    needs_manual_review = 0

    for item in cos_hotspots:
        cls = item.get("classification")
        if cls == "localized-lossy-mcast-pressure":
            localized_mcast += 1
        elif cls == "expected-ecn-pressure":
            expected_ecn += 1
        elif cls == "unexpected-taildrop-on-lossless":
            unexpected_lossless += 1
        elif cls == "queue-without-explicit-scheduler":
            queue_without_scheduler += 1
        elif cls == "needs-manual-review":
            needs_manual_review += 1

    if localized_mcast > 0 and event_congestion:
        bug_signals.append("cos_localized_lossy_mcast_pressure")
    if unexpected_lossless > 0 and event_congestion:
        bug_signals.append("cos_unexpected_taildrop_on_lossless")
    if queue_without_scheduler > 0 and event_congestion:
        bug_signals.append("cos_queue_without_explicit_scheduler")
    if needs_manual_review > 0 and event_congestion:
        bug_signals.append("cos_needs_manual_review")

    # Keep expected ECN pressure informational, not a bug signal driver.
    # It is still counted below in cos_health.
    if expected_ecn > 0:
        bug_signals.append("cos_expected_ecn_pressure")

    telemetry_health = {
        "diff_summary": telemetry_diff_summary,
        "anomaly_summary": telemetry_summary,
        "entity_rollup": entity_rollup,
        "top_anomalies": (telemetry_analyzer.get("anomalies", []) or [])[:10],
        "event_congestion_detected": event_congestion,
    }

    cos_health = {
        "summary": cos_summary,
        "top_hotspots": cos_hotspots[:10],
        "counts": {
            "localized_lossy_mcast_pressure": localized_mcast,
            "expected_ecn_pressure": expected_ecn,
            "unexpected_taildrop_on_lossless": unexpected_lossless,
            "queue_without_explicit_scheduler": queue_without_scheduler,
            "needs_manual_review": needs_manual_review,
        },
    }

    return {
        "status": status,
        "telemetry_analyzer": telemetry_summary,
        "telemetry_diff": telemetry_diff_summary,
        "telemetry_health": telemetry_health,
        "rocev2_verdict": rocev2_verdict.get("verdict"),
        "rocev2_summary": rocev2_summary,
        "traffic_verdict": traffic_verifier.get("verdict"),
        "traffic_summary": traffic_summary,
        "live_alerts": live_alerts,
        "critical_live_alerts": critical_live_alerts,
        "congestion_summary": congestion_summary,
        "root_cause_summary": root_summary,
        "cos_health": cos_health,
        "bug_candidate_signals": bug_signals,
    }

def classify_scenario_result(
    *,
    stress_validation: Dict[str, Any],
    rca_validation: Dict[str, Any],
    ui_validation: Dict[str, Any],
    evidence_rollup: Dict[str, Any],
) -> Tuple[str, bool, bool]:
    # ------------------------------------------------------------------
    # event_ok should answer:
    # "Did the event execute and make it into the report?"
    #
    # Do NOT tie this to stress_validation["ok"], because that can become
    # a false negative even when interface bounce steps actually passed.
    # ------------------------------------------------------------------
    event_ok = (
        rca_validation.get("ok", False) and
        ui_validation.get("ok", False) and
        ui_validation.get("event_count", 0) > 0
    )

    impact_ok = (
        ui_validation.get("total_hotspots", 0) not in (None, 0) and
        ui_validation.get("primary_cause") not in (None, "", "unknown")
    )

    # ------------------------------------------------------------------
    # Hard pipeline/report failures still force final FAIL
    # ------------------------------------------------------------------
    if not stress_validation.get("ok", False):
        return "FAIL", event_ok, impact_ok
    if not rca_validation.get("ok", False):
        return "FAIL", event_ok, impact_ok
    if not ui_validation.get("ok", False):
        return "FAIL", event_ok, impact_ok

    status = evidence_rollup.get("status", {})
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
    if hard_status_fail:
        return "FAIL", event_ok, impact_ok

    bug_signals = evidence_rollup.get("bug_candidate_signals", [])
    cos_counts = (evidence_rollup.get("cos_health") or {}).get("counts", {}) or {}

    strong_bug = any(
        key in bug_signals
        for key in (
            "cos_unexpected_taildrop_on_lossless",
            "cos_localized_lossy_mcast_pressure",
            "telemetry_critical_anomaly",
            "rocev2_verdict_fail",
            "traffic_verdict_fail",
            "ixia_live_critical_alert",
            "strong_congestion_hotspot",
            "root_cause_mapped_to_dut",
            "interface_in_errors_detected",
            "interface_out_errors_detected",
        )
    )

    medium_bug = any(
        key in bug_signals
        for key in (
            "cos_queue_without_explicit_scheduler",
            "cos_needs_manual_review",
            "telemetry_warning_anomaly",
            "rocev2_verdict_warning",
            "traffic_verdict_warning",
            "ixia_live_alert",
            "telemetry_diff_detected",
            "hotspot_transport_instability",
            "hotspot_port_health_signal",
            "interface_ingress_discards_detected",
            "interface_egress_discards_detected",
        )
    )

    expected_only = (
        cos_counts.get("expected_ecn_pressure", 0) > 0 and
        cos_counts.get("localized_lossy_mcast_pressure", 0) == 0 and
        cos_counts.get("unexpected_taildrop_on_lossless", 0) == 0 and
        cos_counts.get("queue_without_explicit_scheduler", 0) == 0 and
        cos_counts.get("needs_manual_review", 0) == 0
    )

    if event_ok and impact_ok and strong_bug:
        return "BUG-CANDIDATE", event_ok, impact_ok
    if event_ok and impact_ok and medium_bug:
        return "BUG-CANDIDATE", event_ok, impact_ok
    if event_ok and impact_ok and expected_only:
        return "PASS", event_ok, impact_ok
    if event_ok and impact_ok:
        return "PASS", event_ok, impact_ok
    if event_ok:
        return "PARTIAL", event_ok, impact_ok
    return "FAIL", event_ok, impact_ok

def maybe_replay_bug_candidate(
    *,
    result: Dict[str, Any],
    replay_count: int,
    replay_base_kwargs: Dict[str, Any],
) -> Dict[str, Any] | None:
    if replay_count <= 0:
        return None
    if result.get("final_status") != "BUG-CANDIDATE":
        return None

    replay_result = {
        "requested_replays": replay_count,
        "executed_replays": 0,
        "bug_candidate_reproduced": 0,
        "final_replay_status": "not-run",
        "runs": [],
    }

    for idx in range(1, replay_count + 1):
        replay_kwargs = dict(replay_base_kwargs)
        replay_kwargs["stress_run_id"] = None
        replay_kwargs["rca_run_id"] = f"{replay_base_kwargs['rca_run_id']}_replay{idx:02d}"
        replay_kwargs["bug_replay_count"] = 0
        replay_kwargs["continue_on_failure"] = False if "continue_on_failure" in replay_kwargs else False
        replay_single = run_single_scenario(**replay_kwargs)
        replay_result["executed_replays"] += 1
        replay_result["runs"].append({
            "rca_run_id": replay_single.get("rca_run_id"),
            "final_status": replay_single.get("final_status"),
            "bug_candidate_signals": replay_single.get("evidence_rollup", {}).get("bug_candidate_signals", []),
        })
        if replay_single.get("final_status") == "BUG-CANDIDATE":
            replay_result["bug_candidate_reproduced"] += 1

    replay_result["final_replay_status"] = (
        "reproduced" if replay_result["bug_candidate_reproduced"] > 0 else "not-reproduced"
    )
    return replay_result

def _safe_load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return load_json(p)
    except Exception:
        return {}


def _load_ixia_port_map(ixia_inventory_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """
    Build lookup:
      "Ethernet - 011" -> {
          "switch": "...",
          "switch_interface": "...",
          "ixia_port": "...",
          "port_name": "Ethernet - 011",
          ...
      }
    """
    data = _safe_load_json(ixia_inventory_path)
    mapping: Dict[str, Dict[str, Any]] = {}

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            port_name = obj.get("port_name")
            if port_name:
                mapping[str(port_name)] = obj
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return mapping


def _load_resolved_targets_for_run(run_id: str) -> Dict[str, Any]:
    path = BASE_DIR / "artifacts" / "campaigns" / run_id / "resolved_targets.json"
    return _safe_load_json(str(path))


def _build_roce_victim_flows(
    *,
    traffic_health: Dict[str, Any],
    ixia_inventory_path: Optional[str],
) -> List[Dict[str, Any]]:
    port_map = _load_ixia_port_map(ixia_inventory_path)
    rocev2_summary = (traffic_health.get("rocev2_summary") or {})
    by_flow = rocev2_summary.get("by_flow", {}) or {}
    findings = rocev2_summary.get("findings", []) or []

    victim_flows: List[Dict[str, Any]] = []

    for flow_key, finding_count in by_flow.items():
        parts = str(flow_key).split("|")
        if len(parts) < 5:
            continue

        tx_port, rx_port, flow_name, src_qp, dst_qp = parts[:5]
        tx_map = port_map.get(tx_port, {})
        rx_map = port_map.get(rx_port, {})

        signal_counts = {
            "loss": 0,
            "message_failed": 0,
            "ecn_pressure": 0,
            "cnp_pressure": 0,
            "retx": 0,
            "seqerror": 0,
            "latency": 0,
        }

        max_values = {
            "loss": 0,
            "message_failed": 0,
            "ecn_pressure": 0,
            "cnp_pressure": 0,
            "retx": 0,
            "seqerror": 0,
            "latency": 0,
        }

        for item in findings:
            if item.get("flow") != flow_key:
                continue
            t = str(item.get("type") or "")
            v = _safe_number(item.get("value"))
            if t in signal_counts:
                signal_counts[t] += 1
                if v > max_values[t]:
                    max_values[t] = v

        victim_flows.append(
            {
                "flow": flow_key,
                "flow_name": flow_name,
                "finding_count": int(finding_count),
                "tx_port": tx_port,
                "rx_port": rx_port,
                "src_qp": src_qp,
                "dst_qp": dst_qp,
                "tx_switch": tx_map.get("switch"),
                "tx_switch_interface": tx_map.get("switch_interface"),
                "rx_switch": rx_map.get("switch"),
                "rx_switch_interface": rx_map.get("switch_interface"),
                "observed_at": "receiver",
                "signal_counts": signal_counts,
                "max_values": max_values,
            }
        )

    victim_flows = sorted(
        victim_flows,
        key=lambda x: (
            -x["finding_count"],
            -x["signal_counts"].get("message_failed", 0),
            -x["signal_counts"].get("loss", 0),
        ),
    )
    return victim_flows[:10]


def _load_roce_snapshot(path: Optional[str]) -> Dict[str, Any]:
    return _safe_load_json(path)


def _iter_roce_flow_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not snapshot:
        return []

    for key in ("normalized_rows", "flows", "rows", "data", "flow_stats", "raw_rows"):
        rows = snapshot.get(key)
        if isinstance(rows, list):
            return rows

    if isinstance(snapshot, list):
        return snapshot

    return []

def _flow_key_from_row(row: Dict[str, Any]) -> str:
    tx_port = str(row.get("tx_port") or row.get("Tx Port") or "")
    rx_port = str(row.get("rx_port") or row.get("Rx Port") or "")
    flow_name = str(row.get("flow_name") or row.get("Flow Name") or "")

    # IMPORTANT FIX
    src_qp = str(row.get("src_qp") if row.get("src_qp") is not None else row.get("Src QP") or "")
    dst_qp = str(row.get("dest_qp") if row.get("dest_qp") is not None else row.get("Dest QP") or "")

    return "|".join([tx_port, rx_port, flow_name, src_qp, dst_qp])



def _safe_metric(row: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in row:
            return _safe_number(row.get(key))
    return 0.0


def _index_roce_snapshot_by_flow(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for row in _iter_roce_flow_rows(snapshot):
        if not isinstance(row, dict):
            continue
        key = _flow_key_from_row(row)
        if not key.strip("|"):
            continue
        indexed[key] = row
    return indexed


def _extract_pre_post_for_victim_flow(
    *,
    victim_flow_key: str,
    rocev2_pre_path: Optional[str],
    rocev2_post_path: Optional[str],
) -> Dict[str, Any]:
    pre_snapshot = _load_roce_snapshot(rocev2_pre_path)
    post_snapshot = _load_roce_snapshot(rocev2_post_path)

    pre_index = _index_roce_snapshot_by_flow(pre_snapshot)
    post_index = _index_roce_snapshot_by_flow(post_snapshot)

    pre_row = pre_index.get(victim_flow_key, {})
    post_row = post_index.get(victim_flow_key, {})

    # tolerate schema variation
    pre_loss = max(
        _safe_metric(pre_row, "frames_delta", "Frames Delta", "delta"),
        max(0.0, _safe_metric(pre_row, "frames_tx", "Frames Tx") - _safe_metric(pre_row, "frames_rx", "Frames Rx")),
    )
    post_loss = max(
        _safe_metric(post_row, "frames_delta", "Frames Delta", "delta"),
        max(0.0, _safe_metric(post_row, "frames_tx", "Frames Tx") - _safe_metric(post_row, "frames_rx", "Frames Rx")),
    )

    pre_message_failed = _safe_metric(pre_row, "message_failed", "Message Failed")
    post_message_failed = _safe_metric(post_row, "message_failed", "Message Failed")

    pre_ecn = _safe_metric(pre_row, "ecn", "ECN")
    post_ecn = _safe_metric(post_row, "ecn", "ECN")

    pre_cnp = max(
        _safe_metric(pre_row, "cnp_rx", "CNP Rx"),
        _safe_metric(pre_row, "cnp_tx", "CNP Tx"),
    )
    post_cnp = max(
        _safe_metric(post_row, "cnp_rx", "CNP Rx"),
        _safe_metric(post_row, "cnp_tx", "CNP Tx"),
    )

    pre_retx = _safe_metric(pre_row, "retx", "Retransmissions")
    post_retx = _safe_metric(post_row, "retx", "Retransmissions")

    pre_seqerror = _safe_metric(pre_row, "seqerror", "SeqError")
    post_seqerror = _safe_metric(post_row, "seqerror", "SeqError")

    pre_latency = max(
        _safe_metric(pre_row, "latency_ns", "Latency (ns)", "latency"),
        _safe_metric(pre_row, "max_latency_ns", "Max Latency (ns)"),
    )
    post_latency = max(
        _safe_metric(post_row, "latency_ns", "Latency (ns)", "latency"),
        _safe_metric(post_row, "max_latency_ns", "Max Latency (ns)"),
    )

    return {
        "flow": victim_flow_key,
        "pre": {
            "loss": pre_loss,
            "message_failed": pre_message_failed,
            "ecn_pressure": pre_ecn,
            "cnp_pressure": pre_cnp,
            "retx": pre_retx,
            "seqerror": pre_seqerror,
            "latency": pre_latency,
        },
        "post": {
            "loss": post_loss,
            "message_failed": post_message_failed,
            "ecn_pressure": post_ecn,
            "cnp_pressure": post_cnp,
            "retx": post_retx,
            "seqerror": post_seqerror,
            "latency": post_latency,
        },
        "delta": {
            "loss": post_loss - pre_loss,
            "message_failed": post_message_failed - pre_message_failed,
            "ecn_pressure": post_ecn - pre_ecn,
            "cnp_pressure": post_cnp - pre_cnp,
            "retx": post_retx - pre_retx,
            "seqerror": post_seqerror - pre_seqerror,
            "latency": post_latency - pre_latency,
        },
    }


def _build_congestion_origin_analysis(
    *,
    run_id: str,
    case_summary_path: str,
    ui_report_path: str,
    ixia_inventory_path: Optional[str],
) -> Dict[str, Any]:
    case_summary = _safe_load_json(case_summary_path)
    ui_report = _safe_load_json(ui_report_path)

    summary = ui_report.get("summary", {}) or {}
    traffic_health = ui_report.get("traffic_health", {}) or {}
    telemetry_health = ui_report.get("telemetry_health", {}) or {}
    stress_classification = ui_report.get("stress_classification", {}) or {}

    resolved_targets_payload = _load_resolved_targets_for_run(run_id)
    resolved_targets = resolved_targets_payload.get("targets", []) or []
    event_nodes = sorted({t.get("node") for t in resolved_targets if t.get("node")})
    event_interfaces = [
        f"{t.get('node')}:{t.get('interface')}"
        for t in resolved_targets
        if t.get("node") and t.get("interface")
    ]

    cos_health = (case_summary.get("evidence_rollup", {}) or {}).get("cos_health", {})
    if not cos_health:
        # newer path: rebuild from ui/case summary if evidence_rollup not embedded
        cos_path = (case_summary.get("files", {}) or {}).get("cos_hotspot_correlation")
        cos_health = _safe_load_json(cos_path) if cos_path else {}

    cos_hotspots = (
        cos_health.get("top_hotspots")
        or cos_health.get("hotspots")
        or []
    )

    primary_origin = None
    secondary_hotspots: List[Dict[str, Any]] = []

    top_node = summary.get("top_hotspot_node")
    top_interface = summary.get("top_hotspot_interface")
    top_queue = summary.get("top_hotspot_queue")
    top_classification = summary.get("top_hotspot_classification")
    top_confidence = summary.get("confidence")
    event_outcome = summary.get("top_hotspot_event_outcome")
    recovery_trend = summary.get("top_hotspot_recovery_trend")
    persistence_ratio = summary.get("top_hotspot_persistence_ratio")
    pattern_scope = summary.get("pattern_scope")

    if top_node and top_interface:
        reasons = []
        score = 0

        if top_node in event_nodes:
            score += 3
            reasons.append("top hotspot is on event node")

        if event_outcome == "persistent_taildrop":
            score += 3
            reasons.append("persistent taildrop observed")

        if recovery_trend in ("flat", "increasing", "worsening"):
            score += 2
            reasons.append(f"recovery trend={recovery_trend}")

        if top_classification in ("localized-lossy-mcast-pressure", "unexpected-taildrop-on-lossless"):
            score += 3
            reasons.append(f"classification={top_classification}")

        if _safe_number(persistence_ratio) >= 1.0:
            score += 2
            reasons.append(f"persistence_ratio={persistence_ratio}")

        primary_origin = {
            "node": top_node,
            "interface": top_interface,
            "queue": top_queue,
            "classification": top_classification,
            "confidence": top_confidence,
            "event_outcome": event_outcome,
            "recovery_trend": recovery_trend,
            "persistence_ratio": persistence_ratio,
            "origin_score": score,
            "reason": "; ".join(reasons) if reasons else "highest ranked hotspot",
        }

    for item in cos_hotspots[:10]:
        node = item.get("node")
        interface = item.get("interface")
        if not node or not interface:
            continue
        if primary_origin and node == primary_origin["node"] and interface == primary_origin["interface"]:
            continue
        secondary_hotspots.append(
            {
                "node": node,
                "interface": interface,
                "queue": item.get("queue"),
                "classification": item.get("classification"),
                "score": item.get("score"),
                "forwarding_class": item.get("forwarding_class"),
            }
        )

    victim_flows = _build_roce_victim_flows(
        traffic_health=traffic_health,
        ixia_inventory_path=ixia_inventory_path,
    )

    top_victim = victim_flows[0] if victim_flows else {}

    files_map = case_summary.get("files", {}) or {}
    victim_flow_baseline = {}
    if top_victim and top_victim.get("flow"):
        victim_flow_baseline = _extract_pre_post_for_victim_flow(
            victim_flow_key=top_victim["flow"],
            rocev2_pre_path=files_map.get("rocev2_pre"),
            rocev2_post_path=files_map.get("rocev2_post"),
        )

    causality_score = 0
    causality_signals = []

    if event_nodes and primary_origin and primary_origin.get("node") in event_nodes:
        causality_score += 2
        causality_signals.append("event_node_matches_origin")

    if len(event_interfaces) >= 4:
        causality_score += 1
        causality_signals.append("broad_event_targets_applied")

    if primary_origin and primary_origin.get("event_outcome") == "persistent_taildrop":
        causality_score += 2
        causality_signals.append("persistent_taildrop_on_origin")

    if primary_origin and primary_origin.get("classification") in (
        "localized-lossy-mcast-pressure",
        "unexpected-taildrop-on-lossless",
    ):
        causality_score += 1
        causality_signals.append("suspicious_queue_classification")

    baseline_gate = "unknown"
    baseline_reason = ""

    if victim_flow_baseline:
        pre_vals = victim_flow_baseline.get("pre", {}) or {}
        post_vals = victim_flow_baseline.get("post", {}) or {}
        delta_vals = victim_flow_baseline.get("delta", {}) or {}

        pre_loss = _safe_number(pre_vals.get("loss"))
        post_loss = _safe_number(post_vals.get("loss"))
        delta_loss = _safe_number(delta_vals.get("loss"))

        pre_msg = _safe_number(pre_vals.get("message_failed"))
        post_msg = _safe_number(post_vals.get("message_failed"))
        delta_msg = _safe_number(delta_vals.get("message_failed"))

        if pre_loss == 0 and pre_msg == 0 and (post_loss > 0 or post_msg > 0):
            baseline_gate = "strong"
            causality_score += 3
            causality_signals.append("baseline_clean_then_failure_after_event")
            baseline_reason = "pre-event flow was clean and post-event flow shows loss/message failure"
        elif (delta_loss > 0) or (delta_msg > 0):
            baseline_gate = "moderate"
            causality_score += 2
            causality_signals.append("post_event_worsening_vs_baseline")
            baseline_reason = "pre-event issue existed but worsened after the event"
        elif pre_loss > 0 or pre_msg > 0:
            baseline_gate = "weak"
            causality_signals.append("pre_existing_issue_without_clear_worsening")
            baseline_reason = "issue existed before the event without strong worsening signal"
        else:
            baseline_gate = "unknown"
            baseline_reason = "insufficient pre/post contrast to prove event causality"

    if victim_flows:
        sig = top_victim.get("signal_counts", {}) or {}
        if (sig.get("loss", 0) > 0) or (sig.get("message_failed", 0) > 0):
            causality_score += 2
            causality_signals.append("victim_flow_failure_present")

    if pattern_scope in ("fabric-wide", "corridor-wide"):
        causality_score += 1
        causality_signals.append("fabric_wide_propagation")

    if primary_origin and primary_origin.get("classification") == "localized-lossy-mcast-pressure":
        causality_score += 1
        causality_signals.append("config_consistent_lossy_queue")

    if baseline_gate == "strong" and causality_score >= 7:
        causality_confidence = "high"
    elif baseline_gate in ("strong", "moderate") and causality_score >= 4:
        causality_confidence = "medium"
    else:
        causality_confidence = "low"

    causality_reason_parts = []
    if "event_node_matches_origin" in causality_signals:
        causality_reason_parts.append("event node matches congestion origin candidate")
    if "persistent_taildrop_on_origin" in causality_signals:
        causality_reason_parts.append("persistent taildrop observed on origin candidate")
    if "victim_flow_failure_present" in causality_signals:
        causality_reason_parts.append("victim flow shows loss/message failure")
    if "config_consistent_lossy_queue" in causality_signals:
        causality_reason_parts.append("origin queue is lossy multicast path")
    if "fabric_wide_propagation" in causality_signals:
        causality_reason_parts.append("impact scope is fabric-wide")
    if baseline_reason:
        causality_reason_parts.append(baseline_reason)

    causality_assessment = {
        "confidence": causality_confidence,
        "score": causality_score,
        "signals": causality_signals,
        "baseline_gate": baseline_gate,
        "reason": "; ".join(causality_reason_parts),
        "victim_flow_baseline_comparison": victim_flow_baseline,
    }

    propagation_hypothesis_parts = []

    if event_nodes:
        propagation_hypothesis_parts.append(
            f"Event injected on {', '.join(event_nodes)} with {len(event_interfaces)} fabric interface target(s)"
        )

    if primary_origin:
        propagation_hypothesis_parts.append(
            f"Strongest congestion-origin candidate is {primary_origin.get('node')} "
            f"{primary_origin.get('interface')} queue {primary_origin.get('queue')}"
        )

    if primary_origin and primary_origin.get("classification"):
        propagation_hypothesis_parts.append(
            f"classified as {primary_origin.get('classification')}"
        )

    if top_victim:
        propagation_hypothesis_parts.append(
            f"RoCE victim flow observed on receiver {top_victim.get('rx_switch')} "
            f"{top_victim.get('rx_switch_interface')} from transmitter "
            f"{top_victim.get('tx_switch')} {top_victim.get('tx_switch_interface')}"
        )

    if pattern_scope:
        propagation_hypothesis_parts.append(
            f"impact scope appears {pattern_scope}"
        )

    return {
        "event_nodes": event_nodes,
        "event_interfaces": event_interfaces,
        "event_target_count": len(event_interfaces),
        "primary_origin_candidate": primary_origin,
        "secondary_hotspots": secondary_hotspots[:8],
        "victim_flows": victim_flows,
        "impact_scope": pattern_scope or "unknown",
        "stress_classification": stress_classification,
        "propagation_hypothesis": ". ".join(propagation_hypothesis_parts) if propagation_hypothesis_parts else "",
        "causality_assessment": causality_assessment,
    }


def inject_congestion_origin_analysis_into_ui_report(
    *,
    run_id: str,
    case_summary_path: str,
    ui_report_path: str,
    ixia_inventory_path: Optional[str],
    progress=None,
) -> None:
    ui_report = _safe_load_json(ui_report_path)
    analysis = _build_congestion_origin_analysis(
        run_id=run_id,
        case_summary_path=case_summary_path,
        ui_report_path=ui_report_path,
        ixia_inventory_path=ixia_inventory_path,
    )
    ui_report["congestion_origin_analysis"] = analysis
    write_json(Path(ui_report_path), ui_report)

    if progress:
        poc = analysis.get("primary_origin_candidate") or {}
        progress.info(
            f"congestion_origin_analysis_injected=true "
            f"origin={poc.get('node')}|{poc.get('interface')}|q{poc.get('queue')}"
        )



def run_single_scenario(
    *,
    scenario_name: str,
    rca_run_id: str,
    stress_run_id: Optional[str],
    release_tag: Optional[str],
    src: str,
    dst: str,
    intent_name: str,
    nodes: str,
    profile: str,
    phase_profile: str,
    timeout: int,
    topology: str,
    top_n: int,
    ixia_inventory: Optional[str],
    ixia_session_id: Optional[int],
    running_wait: int,
    post_wait: int,
    resume_after_post: bool,
    settle_seconds: int,
    interval_seconds: int,
    stop_on_failure: bool,
    stress_iterations: int,
    node: Optional[str],
    interface: Optional[str],
    targets: Optional[str],
    selected_nodes: Optional[str],
    one_per_node: bool,
    ui_server_url: str,
    skip_ui_check: bool,
    enable_live_monitor: bool = False,
    live_monitor_iterations: int = 6,
    live_monitor_interval: int = 5,
    enable_port_stats: bool = False,
    bug_replay_count: int = 0,
    baseline_window: int = 300,
    running_decay: int = 15,
    settle_gap: int = 30,
    post_window: int = 300,
    post_sample_count: int = 10,
    post_sample_interval: int = 30,
    pre_event_stabilize_seconds: int = 10,
    strict_pre_event_gate: bool = False,
) -> Dict[str, Any]:
    scenario = SCENARIOS[scenario_name]


    run_started_epoch = time.time()
    run_started_iso = utc_now_iso()

    print("\n" + "=" * 88)
    print("RUN SINGLE SCENARIO")
    print("=" * 88)
    print(f"Scenario            : {scenario_name}")
    print(f"Description         : {scenario.get('description', '')}")
    print(f"RCA Run ID          : {rca_run_id}")
    if release_tag:
        print(f"Release Tag         : {release_tag}")

    progress = ProgressLogger(progress_log_path_for_run(rca_run_id))
    progress.stage("RUN SINGLE SCENARIO")
    progress.info(f"scenario={scenario_name}")
    progress.info(f"rca_run_id={rca_run_id}")
    if release_tag:
        progress.info(f"release_tag={release_tag}")

    # -------------------------------------------------------------------------
    # Explicit phase timing metadata for baseline-aware CoS correlation
    # -------------------------------------------------------------------------
    progress.stage("PHASE_TIMELINE")
    progress.info(f"baseline_window_seconds={baseline_window}")
    progress.info(f"running_decay_seconds={running_decay}")
    progress.info(f"settle_gap_seconds={settle_gap}")
    progress.info(f"post_window_seconds={post_window}")
    progress.info(f"post_wait_seconds={post_wait}")

    print(
        f"[PHASE TIMING] baseline={baseline_window}s, "
        f"running_decay={running_decay}s, "
        f"settle_gap={settle_gap}s, "
        f"post_window={post_window}s, "
        f"post_wait={post_wait}s"
    )

    progress.stage("TARGET_RESOLUTION")
    t0 = time.time()
    targets_resolved = resolve_targets_for_scenario(
        scenario_name=scenario_name,
        topology_path=topology,
        explicit_node=node,
        explicit_interface=interface,
        explicit_targets=targets,
        selected_nodes_raw=selected_nodes,
        one_per_node=one_per_node,
    )

    target_mode = "explicit" if (node and interface) or targets else "auto"
    resolved_target_artifacts = write_resolved_targets_artifacts(
        run_id=rca_run_id,
        scenario_name=scenario_name,
        release_tag=release_tag,
        target_mode=target_mode,
        targets=targets_resolved,
    )
    progress.info(f"resolved_targets_json={resolved_target_artifacts['run_json']}")
    progress.info(f"resolved_targets_txt={resolved_target_artifacts['run_txt']}")
    progress.info(f"targets_arg={resolved_target_artifacts['targets_arg']}")

    progress.info(f"resolved_target_count={len(targets_resolved)}")
    if scenario_name == "single_interface_bounce" and not (node and interface) and not targets:
        progress.info("single_interface_bounce_target_mode=auto")
        print("[RESOLVE] single_interface_bounce using auto-selected target")
    elif scenario_name == "single_interface_bounce":
        progress.info("single_interface_bounce_target_mode=manual")

    print(f"\n[RESOLVE] target count = {len(targets_resolved)}")
    for item in targets_resolved[:20]:
        if item.get("interface"):
            target_str = f"{item['node']}:{item['interface']}"
        else:
            target_str = f"{item['node']}"
        print(f"  - {target_str}")
        progress.info(f"target={target_str}")
    if len(targets_resolved) > 20:
        progress.info(f"additional_targets={len(targets_resolved) - 20}")
        print(f"  ... {len(targets_resolved) - 20} more targets")
    progress.info(f"target_resolution_elapsed_sec={time.time() - t0:.1f}")

    actual_stress_run_id = build_stress_run_id(
        scenario_name=scenario_name,
        release_tag=release_tag,
        explicit_stress_run_id=stress_run_id,
    )

    rca_node = node
    rca_interface = interface

    if scenario_name == "single_interface_bounce" and targets_resolved:
        first_target = targets_resolved[0]
        rca_node = first_target.get("node")
        rca_interface = first_target.get("interface")
        progress.info(f"rca_bounced_node={rca_node}")
        progress.info(f"rca_bounced_interface={rca_interface}")

    print(f"\n[PLAN] stress_run_id = {actual_stress_run_id}")

    progress.stage("STRESS_EVENT_EXECUTION")
    progress.info(f"stress_run_id={actual_stress_run_id}")
    t0 = time.time()
    stress_report_path = run_stress_event(
        scenario_name=scenario_name,
        stress_run_id=actual_stress_run_id,
        targets=targets_resolved,
        settle_seconds=settle_seconds,
        interval_seconds=interval_seconds,
        stop_on_failure=stop_on_failure,
        stress_iterations=stress_iterations,
        pre_event_stabilize_seconds=pre_event_stabilize_seconds,
        strict_pre_event_gate=strict_pre_event_gate,
        ixia_inventory=ixia_inventory,
        ixia_session_id=ixia_session_id,
        profile=profile,
        nodes=nodes,
        timeout=timeout,
        topology=topology,
    )
    progress.info(f"stress_report_path={stress_report_path}")
    progress.info(f"stress_event_elapsed_sec={time.time() - t0:.1f}")

    progress.stage("RCA_CASE_EXECUTION")
    t0 = time.time()

    case_summary_path = run_rca_case(
        rca_run_id=rca_run_id,
        src=src,
        dst=dst,
        intent_name=intent_name,
        nodes=nodes,
        profile=profile,
        phase_profile=phase_profile,
        timeout=timeout,
        topology=topology,
        top_n=top_n,
        ixia_inventory=ixia_inventory,
        ixia_session_id=ixia_session_id,
        running_wait=running_wait,
        post_wait=post_wait,
        resume_after_post=resume_after_post,
        stress_orchestrator_report=stress_report_path,
        enable_live_monitor=enable_live_monitor,
        live_monitor_iterations=live_monitor_iterations,
        live_monitor_interval=live_monitor_interval,
        enable_port_stats=enable_port_stats,

        # Required for ECMP recovery
        node=rca_node,
        interface=rca_interface,

        # phase-aware knobs
        baseline_window=baseline_window,
        running_decay=running_decay,
        settle_gap=settle_gap,
        post_window=post_window,
        post_sample_count=post_sample_count,
        post_sample_interval=post_sample_interval,
    )
    progress.info(f"rca_case_summary={case_summary_path}")
    progress.info(f"rca_case_elapsed_sec={time.time() - t0:.1f}")

    progress.stage("RCA_UI_REPORT_BUILD")
    t0 = time.time()

    # Initial UI build from RCA case summary
    ui_report_path = build_ui_report(case_summary_path)

    # -------------------------------------------------------------------------
    # Load phase-based telemetry references for CoS correlation / phase injection
    # -------------------------------------------------------------------------
    case_summary_data = load_json(case_summary_path)
    files = case_summary_data.get("files", {}) or {}

    baseline_telemetry_path = files.get("baseline_telemetry") or files.get("baseline_no_churn_telemetry")
    running_telemetry_path = files.get("running_telemetry")
    post_telemetry_path = files.get("post_telemetry")

    pre_sample_paths, post_sample_paths = build_phase_sample_paths(rca_run_id, phase_profile)

    # legacy fallback for older runs
    legacy_telemetry_reference_path = (
        files.get("running_telemetry")
        or files.get("pre_telemetry")
        or files.get("post_telemetry")
    )

    progress.info(f"baseline_telemetry_path={baseline_telemetry_path}")
    progress.info(f"running_telemetry_path={running_telemetry_path}")
    progress.info(f"post_telemetry_path={post_telemetry_path}")
    progress.info(f"legacy_telemetry_reference_path={legacy_telemetry_reference_path}")
    progress.info(f"pre_sample_paths={pre_sample_paths}")
    progress.info(f"post_sample_paths={post_sample_paths}")

    if not baseline_telemetry_path or not running_telemetry_path or not post_telemetry_path:
        raise RuntimeError(
            "Missing telemetry paths for phase delta injection: "
            f"baseline={baseline_telemetry_path}, "
            f"running={running_telemetry_path}, "
            f"post={post_telemetry_path}"
        )

    # First phase injection after initial UI build
    inject_phase_delta_into_ui_report(
        ui_report_path=ui_report_path,
        baseline_telemetry_path=baseline_telemetry_path,
        running_telemetry_path=running_telemetry_path,
        post_telemetry_path=post_telemetry_path,
        pre_sample_paths=pre_sample_paths,
        post_sample_paths=post_sample_paths,
    )
    progress.info("phase_delta_injected_into_ui_report=true")

    cos_hotspot_path = None
    cos_hotspot_data: Dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # Prefer 3-phase baseline/running/post correlation
    # -------------------------------------------------------------------------
    have_phase_telemetry = bool(
        baseline_telemetry_path and running_telemetry_path and post_telemetry_path
    )

    if have_phase_telemetry or legacy_telemetry_reference_path:
        try:
            progress.stage("COS_HOTSPOT_CORRELATION")

            if have_phase_telemetry:
                progress.info("cos_hotspot_mode=phase_aware")
                progress.info(f"cos_baseline_reference={baseline_telemetry_path}")
                progress.info(f"cos_running_reference={running_telemetry_path}")
                progress.info(f"cos_post_reference={post_telemetry_path}")

                cos_hotspot_path = run_cos_hotspot_correlation(
                    rca_run_id=rca_run_id,
                    ui_report_path=ui_report_path,
                    baseline_reference_path=baseline_telemetry_path,
                    running_reference_path=running_telemetry_path,
                    post_reference_path=post_telemetry_path,
                    top_n=15,
                )
            else:
                progress.info("cos_hotspot_mode=legacy_single_reference")
                progress.info(f"telemetry_reference_path={legacy_telemetry_reference_path}")

                cos_hotspot_path = run_cos_hotspot_correlation(
                    rca_run_id=rca_run_id,
                    ui_report_path=ui_report_path,
                    telemetry_reference_path=legacy_telemetry_reference_path,
                    top_n=15,
                )

            progress.info(f"cos_hotspot_correlation={cos_hotspot_path}")

            if cos_hotspot_path:
                try:
                    cos_hotspot_data = load_json(cos_hotspot_path)

                    # Inject CoS artifact into case summary BEFORE rebuilding UI/evidence
                    files = case_summary_data.get("files", {}) or {}
                    files["cos_hotspot_correlation"] = cos_hotspot_path
                    case_summary_data["files"] = files

                    # Persist phase timeline metadata into case summary for UI/reporting
                    case_summary_data.setdefault("phase_timeline", {})
                    case_summary_data["phase_timeline"].update(
                        {
                            "baseline_window": baseline_window,
                            "running_decay": running_decay,
                            "settle_gap": settle_gap,
                            "post_window": post_window,
                            "baseline_telemetry": baseline_telemetry_path,
                            "running_telemetry": running_telemetry_path,
                            "post_telemetry": post_telemetry_path,
                            "pre_sample_paths": pre_sample_paths,
                            "post_sample_paths": post_sample_paths,
                        }
                    )

                    write_json(Path(case_summary_path), case_summary_data)

                    progress.info(
                        f"injected cos_hotspot_correlation into case summary: {cos_hotspot_path}"
                    )
                except Exception as exc:
                    print(f"[WARN] failed to inject cos hotspot correlation into case summary: {exc}")
                    progress.info(f"cos_hotspot_injection_failed={exc}")
                    cos_hotspot_data = {}
        except Exception as exc:
            print(f"[WARN] cos hotspot correlation failed: {exc}")
            progress.info(f"cos_hotspot_correlation_failed={exc}")

    # -------------------------------------------------------------------------
    # Final UI rebuild + automatic phase/ECMP enrichment
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # Final UI rebuild + automatic phase/ECMP enrichment
    # -------------------------------------------------------------------------
    ui_report_path = build_ui_report(case_summary_path)

    # Re-inject phase delta fields because rebuild can overwrite earlier injection
    inject_phase_delta_into_ui_report(
        ui_report_path=ui_report_path,
        baseline_telemetry_path=baseline_telemetry_path,
        running_telemetry_path=running_telemetry_path,
        post_telemetry_path=post_telemetry_path,
        pre_sample_paths=pre_sample_paths,
        post_sample_paths=post_sample_paths,
    )
    progress.info("phase_delta_reinjected_after_final_ui_rebuild=true")

    # Inject congestion origin / propagation analysis automatically
    try:
        inject_congestion_origin_analysis_into_ui_report(
            run_id=rca_run_id,
            case_summary_path=case_summary_path,
            ui_report_path=ui_report_path,
            ixia_inventory_path=ixia_inventory,
            progress=progress,
        )
    except Exception as exc:
        progress.info(f"congestion_origin_analysis_injection_failed={exc}")
        print(f"[WARN] congestion origin analysis injection failed: {exc}")

    # Inject ECMP Recovery RCA sidecar block automatically
    try:
        inject_ecmp_recovery_view_into_ui_report(
            case_summary_path=case_summary_path,
            ui_report_path=ui_report_path,
            progress=progress,
        )
    except Exception as exc:
        progress.info(f"ecmp_recovery_view_injection_failed={exc}")
        print(f"[WARN] ECMP recovery view injection failed: {exc}")

    try:
        ui_after = load_json(ui_report_path)
        ecmp_targets = list(((ui_after.get("ecmp_recovery_input") or {}).get("targets") or {}).keys())[:5]
        progress.info(f"ecmp_recovery_view_injection_verify_targets={ecmp_targets}")
    except Exception as verify_exc:
        progress.info(f"ecmp_recovery_view_injection_verify_failed={verify_exc}")
    progress.info(f"ui_report_path={ui_report_path}")
    progress.info(f"ui_report_elapsed_sec={time.time() - t0:.1f}")
    progress.stage("VALIDATION_AND_CLASSIFICATION")
    stress_validation = validate_stress_report(
        stress_report_path,
        expected_target_count=len(targets_resolved),
    )
    rca_validation = validate_rca_summary(
        case_summary_path,
        expected_stress_path=stress_report_path,
    )
    ui_validation = validate_ui_report(ui_report_path)

    refreshed_case_summary = load_json(case_summary_path)
    evidence_rollup = build_evidence_rollup(refreshed_case_summary)

    ui_server_ok = True
    if not skip_ui_check:
        ui_server_ok = check_ui_server(ui_server_url)

    final_status, event_ok, impact_ok = classify_scenario_result(
        stress_validation=stress_validation,
        rca_validation=rca_validation,
        ui_validation=ui_validation,
        evidence_rollup=evidence_rollup,
    )

    print(f"Validation Status   : {final_status}")
    print(f"Event Execution OK  : {'YES' if event_ok else 'NO'}")
    print(f"Impact Observed     : {'YES' if impact_ok else 'NO'}")

    result = {
        "generated_at": utc_now_iso(),
        "scenario": scenario_name,
        "description": scenario.get("description", ""),
        "expected_behavior": scenario.get("expected_behavior", {}),
        "release_tag": release_tag,
        "stress_run_id": actual_stress_run_id,
        "rca_run_id": rca_run_id,
        "resolved_targets": targets_resolved,
        "stress_iterations": stress_iterations,
        "stress_report": stress_validation,
        "rca_summary": rca_validation,
        "ui_report": ui_validation,
        "ui_server_reachable": ui_server_ok,
        "event_ok": event_ok,
        "impact_ok": impact_ok,
        "evidence_rollup": evidence_rollup,
        "telemetry_health": ui_validation.get("telemetry_health", {}),
        "bug_candidate_signals": ui_validation.get("bug_candidate_signals", []),
        "stress_classification": ui_validation.get("stress_classification", {}),
        "cos_hotspot_correlation": cos_hotspot_path,
        "cos_hotspot_summary": cos_hotspot_data.get("summary", {}),
        "cos_hotspot_top": cos_hotspot_data.get("hotspots", [])[:10],
        "final_status": final_status,
        "resolved_targets_artifacts": resolved_target_artifacts,
        "phase_timeline": {
            "baseline_window": baseline_window,
            "running_decay": running_decay,
            "settle_gap": settle_gap,
            "post_window": post_window,
            "baseline_telemetry": baseline_telemetry_path,
            "running_telemetry": running_telemetry_path,
            "post_telemetry": post_telemetry_path,
            "pre_sample_paths": pre_sample_paths,
            "post_sample_paths": post_sample_paths,
        },
    }

    progress.info(f"final_status={final_status}")
    progress.info(f"event_ok={event_ok}")
    progress.info(f"impact_ok={impact_ok}")
    progress.info(f"ui_server_reachable={ui_server_ok}")
    progress.info(f"bug_candidate_signals={evidence_rollup.get('bug_candidate_signals', [])}")

    if bug_replay_count > 0 and final_status == "BUG-CANDIDATE":
        replay_kwargs = {
            "scenario_name": scenario_name,
            "rca_run_id": rca_run_id,
            "stress_run_id": stress_run_id,
            "release_tag": release_tag,
            "src": src,
            "dst": dst,
            "intent_name": intent_name,
            "nodes": nodes,
            "profile": profile,
            "phase_profile": phase_profile,
            "timeout": timeout,
            "topology": topology,
            "top_n": top_n,
            "ixia_inventory": ixia_inventory,
            "ixia_session_id": ixia_session_id,
            "running_wait": running_wait,
            "post_wait": post_wait,
            "resume_after_post": resume_after_post,
            "settle_seconds": settle_seconds,
            "interval_seconds": interval_seconds,
            "stop_on_failure": stop_on_failure,
            "stress_iterations": stress_iterations,
            "node": node,
            "interface": interface,
            "targets": targets,
            "selected_nodes": selected_nodes,
            "one_per_node": one_per_node,
            "ui_server_url": ui_server_url,
            "skip_ui_check": skip_ui_check,
            "enable_live_monitor": enable_live_monitor,
            "live_monitor_iterations": live_monitor_iterations,
            "live_monitor_interval": live_monitor_interval,
            "enable_port_stats": enable_port_stats,
            "baseline_window": baseline_window,
            "running_decay": running_decay,
            "settle_gap": settle_gap,
            "post_window": post_window,
            "post_sample_count": post_sample_count,
            "post_sample_interval": post_sample_interval,
            "pre_event_stabilize_seconds": pre_event_stabilize_seconds,
            "strict_pre_event_gate": strict_pre_event_gate,
        }
        replay_info = maybe_replay_bug_candidate(
            result=result,
            replay_count=bug_replay_count,
            replay_base_kwargs=replay_kwargs,
        )
        if replay_info:
            result["replay_validation"] = replay_info

    validation_path = BASE_DIR / "artifacts" / "campaigns" / rca_run_id / "fault_injection_validation.json"
    progress.info(f"validation_output={validation_path}")
    write_json(validation_path, result)

    try:
        from controller.topology_html_report import build_topology_html_report

        topology_outputs = build_topology_html_report(
            run_id=rca_run_id,
            topology_path=topology,
            validation_path=str(validation_path),
            rca_ui_report_path=ui_validation["path"],
            ixia_inventory_path=ixia_inventory,
        )
        result["topology_view"] = topology_outputs
        write_json(validation_path, result)
        progress.info(f"topology_view_html={topology_outputs.get('html')}")
        progress.info(f"topology_view_json={topology_outputs.get('json')}")
    except Exception as exc:
        progress.info(f"topology_view_generation_failed={exc}")
        print(f"[WARN] topology view generation failed: {exc}")

    progress.stage("SCENARIO_COMPLETE")
    progress.info(f"scenario={scenario_name}")
    progress.info(f"stress_run_id={actual_stress_run_id}")
    progress.info(f"rca_run_id={rca_run_id}")
    progress.info(f"final_status={final_status}")

    print("\n" + "=" * 88)
    print("SCENARIO RESULT")
    print("=" * 88)
    print(f"Scenario Name       : {scenario_name}")
    print(f"Stress Run ID       : {actual_stress_run_id}")
    print(f"RCA Run ID          : {rca_run_id}")
    print(f"Resolved Targets    : {len(targets_resolved)}")
    print(f"Stress Iterations   : {stress_iterations}")
    print(f"Stress Report       : {stress_validation['path']}")
    print(f"RCA Summary         : {rca_validation['path']}")
    print(f"RCA UI Report       : {ui_validation['path']}")
    print(f"Validation Status   : {final_status}")
    print(f"Event Execution OK  : {'YES' if event_ok else 'NO'}")
    print(f"Impact Observed     : {'YES' if impact_ok else 'NO'}")
    print(f"Event Count         : {ui_validation['event_count']}")
    print(f"Top Event           : {ui_validation['top_event_name'] or '-'}")
    print(f"Primary Cause       : {ui_validation['primary_cause'] or '-'}")
    print(f"Total Hotspots      : {ui_validation['total_hotspots']}")
    print(f"UI Server Reachable : {'YES' if ui_server_ok else 'NO'}")
    print(
        f"Phase Timing        : baseline={baseline_window}s, "
        f"running_decay={running_decay}s, settle_gap={settle_gap}s, post={post_window}s"
    )

    if cos_hotspot_path:
        print(f"CoS Correlation     : {cos_hotspot_path}")
        cos_summary = cos_hotspot_data.get("summary", {}) or {}
        if cos_summary:
            print(
                "CoS Summary         : "
                f"localized_lossy_mcast_pressure={cos_summary.get('localized_lossy_mcast_pressure', 0)}, "
                f"expected_ecn_pressure={cos_summary.get('expected_ecn_pressure', 0)}, "
                f"needs_manual_review={cos_summary.get('needs_manual_review', 0)}"
            )

    bug_signals = evidence_rollup.get("bug_candidate_signals", [])
    if bug_signals:
        print(f"Bug Signals         : {', '.join(bug_signals[:8])}")
    print(f"Validation Report   : {validation_path}")

    run_ended_epoch = time.time()
    run_ended_iso = utc_now_iso()
    end_to_end_runtime_seconds = round(run_ended_epoch - run_started_epoch, 2)
    end_to_end_runtime_minutes = round(end_to_end_runtime_seconds / 60.0, 2)

    progress.info(f"run_started_at={run_started_iso}")
    progress.info(f"run_ended_at={run_ended_iso}")
    progress.info(f"end_to_end_runtime_seconds={end_to_end_runtime_seconds}")
    progress.info(f"end_to_end_runtime_minutes={end_to_end_runtime_minutes}")

    runtime_summary_path = BASE_DIR / "artifacts" / "campaigns" / rca_run_id / "runtime_summary.json"
    write_json(
        runtime_summary_path,
        {
            "run_id": rca_run_id,
            "scenario": scenario_name,
            "run_started_at": run_started_iso,
            "run_ended_at": run_ended_iso,
            "end_to_end_runtime_seconds": end_to_end_runtime_seconds,
            "end_to_end_runtime_minutes": end_to_end_runtime_minutes,
        },
    )
    progress.info(f"runtime_summary={runtime_summary_path}")

    refreshed_ui_report = _safe_load_json(ui_validation["path"])
    result["congestion_origin_analysis"] = refreshed_ui_report.get("congestion_origin_analysis", {})

    return result




def run_suite(
    *,
    suite_name: str,
    suite_run_id: str,
    release_tag: Optional[str],
    continue_on_failure: bool,
    src: str,
    dst: str,
    intent_name: str,
    nodes: str,
    profile: str,
    timeout: int,
    topology: str,
    top_n: int,
    ixia_inventory: Optional[str],
    ixia_session_id: Optional[int],
    running_wait: int,
    post_wait: int,
    resume_after_post: bool,
    settle_seconds: int,
    interval_seconds: int,
    stop_on_failure: bool,
    stress_iterations: int,
    node: Optional[str],
    interface: Optional[str],
    targets: Optional[str],
    selected_nodes: Optional[str],
    one_per_node: bool,
    ui_server_url: str,
    skip_ui_check: bool,
    enable_live_monitor: bool,
    live_monitor_iterations: int,
    live_monitor_interval: int,
    enable_port_stats: bool,
    bug_replay_count: int,
    post_sample_count: int,
    post_sample_interval: int,
) -> Dict[str, Any]:
    scenarios = SUITES[suite_name]
    suite_results: List[Dict[str, Any]] = []

    print("\n" + "=" * 88)
    print("RUN SUITE")
    print("=" * 88)
    print(f"Suite Name          : {suite_name}")
    print(f"Suite Run ID        : {suite_run_id}")
    if release_tag:
        print(f"Release Tag         : {release_tag}")
    print(f"Scenario Count      : {len(scenarios)}")

    for index, scenario_name in enumerate(scenarios, start=1):
        print("\n" + "#" * 88)
        print(f"[SUITE] Scenario {index}/{len(scenarios)} : {scenario_name}")
        print("#" * 88)

        scenario_node = node if scenario_name == "single_interface_bounce" else None
        scenario_interface = interface if scenario_name == "single_interface_bounce" else None

        try:
            scenario_rca_run_id = build_rca_run_id_for_suite(
                scenario_name=scenario_name,
                release_tag=release_tag,
                suite_run_id=suite_run_id,
                index=index,
            )

            result = run_single_scenario(
                scenario_name=scenario_name,
                rca_run_id=scenario_rca_run_id,
                stress_run_id=None,
                release_tag=release_tag,
                src=src,
                dst=dst,
                intent_name=intent_name,
                nodes=nodes,
                profile=profile,
                timeout=timeout,
                topology=topology,
                top_n=top_n,
                ixia_inventory=ixia_inventory,
                ixia_session_id=ixia_session_id,
                running_wait=running_wait,
                post_wait=post_wait,
                resume_after_post=resume_after_post,
                settle_seconds=settle_seconds,
                interval_seconds=interval_seconds,
                stop_on_failure=stop_on_failure,
                stress_iterations=stress_iterations,
                node=scenario_node,
                interface=scenario_interface,
                targets=targets,
                selected_nodes=selected_nodes,
                one_per_node=one_per_node,
                ui_server_url=ui_server_url,
                skip_ui_check=skip_ui_check,
                enable_live_monitor=enable_live_monitor,
                live_monitor_iterations=live_monitor_iterations,
                live_monitor_interval=live_monitor_interval,
                enable_port_stats=enable_port_stats,
                bug_replay_count=bug_replay_count,
                post_sample_count=post_sample_count,
                post_sample_interval=post_sample_interval,
            )
            suite_results.append(result)

            if result["final_status"] == "FAIL" and not continue_on_failure:
                print(f"\n[SUITE STOP] scenario failed and continue_on_failure is False: {scenario_name}")
                break

        except Exception as exc:
            failed_result = {
                "generated_at": utc_now_iso(),
                "scenario": scenario_name,
                "release_tag": release_tag,
                "error": str(exc),
                "event_ok": False,
                "impact_ok": False,
                "final_status": "FAIL",
            }
            suite_results.append(failed_result)
            print(f"\n[SUITE ERROR] scenario={scenario_name} error={exc}")

            if not continue_on_failure:
                print("\n[SUITE STOP] stopping due to scenario failure")
                break

    passed = sum(1 for r in suite_results if r.get("final_status") == "PASS")
    partial = sum(1 for r in suite_results if r.get("final_status") == "PARTIAL")
    failed = sum(1 for r in suite_results if r.get("final_status") == "FAIL")
    bug_candidate = sum(1 for r in suite_results if r.get("final_status") == "BUG-CANDIDATE")
    suite_summary = {
        "generated_at": utc_now_iso(),
        "suite_name": suite_name,
        "suite_run_id": suite_run_id,
        "release_tag": release_tag,
        "total_scenarios": len(scenarios),
        "executed_scenarios": len(suite_results),
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "bug_candidate": bug_candidate,
        "continue_on_failure": continue_on_failure,
        "results": suite_results,
    }

    suite_dir = BASE_DIR / "artifacts" / "suites" / suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)

    suite_summary_json = suite_dir / "suite_summary.json"
    write_json(suite_summary_json, suite_summary)

    suite_summary_txt = suite_dir / "suite_summary.txt"
    with open(suite_summary_txt, "w", encoding="utf-8") as f:
        f.write(f"Suite Name       : {suite_name}\n")
        f.write(f"Suite Run ID     : {suite_run_id}\n")
        f.write(f"Release Tag      : {release_tag or '-'}\n")
        f.write(f"Generated At     : {suite_summary['generated_at']}\n")
        f.write(f"Total Scenarios  : {len(scenarios)}\n")
        f.write(f"Executed         : {len(suite_results)}\n")
        f.write(f"Passed           : {passed}\n")
        f.write(f"Partial          : {partial}\n")
        f.write(f"Failed           : {failed}\n")
        f.write(f"Bug Candidate    : {bug_candidate}\n\n")
        for item in suite_results:
            f.write(f"- Scenario       : {item.get('scenario')}\n")
            f.write(f"  RCA Run ID     : {item.get('rca_run_id', '-')}\n")
            f.write(f"  Final Status   : {item.get('final_status')}\n")
            f.write(f"  Event OK       : {item.get('event_ok')}\n")
            f.write(f"  Impact OK      : {item.get('impact_ok')}\n")
            if item.get("ui_report"):
                f.write(f"  Event Count    : {item['ui_report'].get('event_count')}\n")
                f.write(f"  Top Event      : {item['ui_report'].get('top_event_name')}\n")
                f.write(f"  Primary Cause  : {item['ui_report'].get('primary_cause')}\n")
            ev = item.get("evidence_rollup", {})
            bug_signals = ev.get("bug_candidate_signals", [])
            if bug_signals:
                f.write(f"  Bug Signals    : {', '.join(bug_signals[:8])}\n")
            if item.get("error"):
                f.write(f"  Error          : {item['error']}\n")
            f.write("\n")

    print("\n" + "=" * 88)
    print("SUITE RESULT")
    print("=" * 88)
    print(f"Suite Name          : {suite_name}")
    print(f"Suite Run ID        : {suite_run_id}")
    print(f"Release Tag         : {release_tag or '-'}")
    print(f"Total Scenarios     : {len(scenarios)}")
    print(f"Executed            : {len(suite_results)}")
    print(f"Passed              : {passed}")
    print(f"Partial             : {partial}")
    print(f"Failed              : {failed}")
    print(f"Bug Candidate       : {bug_candidate}")
    print(f"Suite Summary JSON  : {suite_summary_json}")
    print(f"Suite Summary TXT   : {suite_summary_txt}")

    return suite_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scenario-driven fault injection runner for end-to-end Fabric RCA automation."
    )

    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS.keys()),
        help="Run one named scenario end to end.",
    )
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES.keys()),
        help="Run a named suite of scenarios in sequence.",
    )

    parser.add_argument("--rca-run-id", help="RCA campaign run id for single-scenario mode")
    parser.add_argument("--stress-run-id", help="Optional explicit stress run id for single-scenario mode")

    parser.add_argument("--suite-run-id", help="Optional suite run id for suite mode")
    parser.add_argument("--release-tag", help="Release/build label, e.g. 25.2R1-EVO")
    parser.add_argument("--continue-on-failure", action="store_true")

    parser.add_argument("--src", required=True, help="Traffic source endpoint")
    parser.add_argument("--dst", required=True, help="Traffic destination endpoint")
    parser.add_argument("--intent-name", required=True, help="Intent name for RCA flow")
    parser.add_argument("--nodes", required=True, help="Comma-separated RCA telemetry nodes")

    parser.add_argument("--profile", default="hotspot_congestion_qmon")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--top-n", type=int, default=10)

    parser.add_argument("--ixia-inventory", default=DEFAULT_IXIA_INVENTORY)
    parser.add_argument("--ixia-session-id", type=int, default=None)

    parser.add_argument("--running-wait", type=int, default=15)
    parser.add_argument(
        "--post-wait",
        type=int,
        default=300,
        help="Overall post-event wait/observation duration in seconds. Default: 300.",
    )
    parser.add_argument("--resume-after-post", action="store_true")

    parser.add_argument("--settle-seconds", type=int, default=5)
    parser.add_argument("--interval-seconds", type=int, default=0)
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--stress-iterations", type=int, default=1)
    parser.add_argument("--bug-replay-count", type=int, default=0)

    parser.add_argument(
        "--node",
        help="Explicit node for single_interface_bounce (optional if auto target selection is used)",
    )
    parser.add_argument(
        "--interface",
        help="Explicit interface for single_interface_bounce (optional if auto target selection is used)",
    )
    parser.add_argument(
        "--targets",
        help="Explicit targets in format node1:intf1,node2:intf2. Overrides topology resolution where applicable.",
    )
    parser.add_argument(
        "--selected-nodes",
        help="Comma-separated node list for selected_nodes_parallel_bounce",
    )
    parser.add_argument(
        "--one-per-node",
        action="store_true",
        help="When resolving from topology, keep only one fabric interface per node.",
    )

    parser.add_argument("--ui-server-url", default=DEFAULT_UI_SERVER)
    parser.add_argument("--skip-ui-check", action="store_true")

    parser.add_argument("--enable-live-monitor", action="store_true")
    parser.add_argument("--live-monitor-iterations", type=int, default=6)
    parser.add_argument("--live-monitor-interval", type=int, default=5)
    parser.add_argument("--enable-port-stats", action="store_true")

    # Phase-aware timing knobs used by run_rca_case
    parser.add_argument(
        "--baseline-window",
        type=int,
        default=300,
        help="Measured pre-event baseline telemetry collection window in seconds. Default: 300.",
    )
    parser.add_argument(
        "--running-decay",
        type=int,
        default=15,
        help="Additional seconds to include after event completion as part of running window.",
    )
    parser.add_argument(
        "--settle-gap",
        type=int,
        default=30,
        help="Gap after running window before post collection starts.",
    )
    parser.add_argument(
        "--post-window",
        type=int,
        default=300,
        help="Measured post-event recovery telemetry collection window in seconds. Default: 300.",
    )

    parser.add_argument("--pre-event-stabilize-seconds", type=int, default=10)
    parser.add_argument("--strict-pre-event-gate", action="store_true")

    parser.add_argument(
        "--post-sample-count",
        type=int,
        default=10,
        help="Number of post-event recovery samples to collect. Default: 10.",
    )
    parser.add_argument(
        "--post-sample-interval",
        type=int,
        default=30,
        help="Interval in seconds between post-event recovery samples. Default: 30.",
    )

    # User-friendly aliases; these override baseline-window/post-window when provided
    parser.add_argument(
        "--pre-baseline-duration",
        type=int,
        default=None,
        help="Alias for --baseline-window. If set, overrides baseline-window.",
    )
    parser.add_argument(
        "--pre-baseline-interval",
        type=int,
        default=30,
        help="Sampling interval in seconds for pre-event baseline window. Default: 30.",
    )
    parser.add_argument(
        "--post-recovery-duration",
        type=int,
        default=None,
        help="Alias for --post-window. If set, overrides post-window.",
    )
    parser.add_argument(
        "--post-recovery-interval",
        type=int,
        default=30,
        help="Sampling interval in seconds for post-event recovery window. Default: 30.",
    )
    parser.add_argument(
        "--phase-profile",
        default="hotspot_congestion_qmon_phase",
        help="Lightweight telemetry profile for pre/recovery phase samples.",
    )

    parser.add_argument("--suite-id", default="", help="Logical suite grouping ID")
    parser.add_argument("--test-case-id", default="", help="Logical test case / event ID")
    parser.add_argument("--suite-name", default="", help="Optional human readable suite name")

    args = parser.parse_args()
    normalize_phase_timing_args(args)

    print(
        f"[TIMING] baseline_window={args.baseline_window}s "
        f"running_decay={args.running_decay}s "
        f"settle_gap={args.settle_gap}s "
        f"post_window={args.post_window}s "
        f"post_wait={args.post_wait}s "
        f"post_sample_count={args.post_sample_count} "
        f"post_sample_interval={args.post_sample_interval}s"
    )


    if bool(args.scenario) == bool(args.suite):
        parser.error("Exactly one of --scenario or --suite must be provided")

    if args.scenario and not args.rca_run_id:
        parser.error("--rca-run-id is required for single-scenario mode")

    if args.stress_iterations < 1:
        parser.error("--stress-iterations must be >= 1")

    # ------------------------------------------------------------------
    # Normalize overlapping timing knobs
    # ------------------------------------------------------------------

    # Alias override: pre-baseline-duration -> baseline-window
    if args.pre_baseline_duration is not None:
        args.baseline_window = int(args.pre_baseline_duration)

    # Alias override: post-recovery-duration -> post-window
    if args.post_recovery_duration is not None:
        args.post_window = int(args.post_recovery_duration)

    # Keep values sane
    args.baseline_window = max(1, int(args.baseline_window))
    args.running_decay = max(0, int(args.running_decay))
    args.settle_gap = max(0, int(args.settle_gap))
    args.post_window = max(1, int(args.post_window))
    args.post_wait = max(1, int(args.post_wait))
    args.post_sample_count = max(1, int(args.post_sample_count))
    args.post_sample_interval = max(1, int(args.post_sample_interval))
    args.pre_baseline_interval = max(1, int(args.pre_baseline_interval))
    args.post_recovery_interval = max(1, int(args.post_recovery_interval))

    # Ensure post_window is large enough to cover requested post sampling
    sampled_post_duration = args.post_sample_count * args.post_sample_interval
    if sampled_post_duration > args.post_window:
        args.post_window = sampled_post_duration

    # Ensure post_wait is not shorter than post_window
    if args.post_wait < args.post_window:
        args.post_wait = args.post_window

    return args


def main() -> int:
    args = parse_args()

    try:
        if args.scenario:
            result = run_single_scenario(
                scenario_name=args.scenario,
                rca_run_id=args.rca_run_id,
                stress_run_id=args.stress_run_id,
                release_tag=args.release_tag,
                src=args.src,
                dst=args.dst,
                intent_name=args.intent_name,
                nodes=args.nodes,
                profile=args.profile,
                phase_profile=args.phase_profile,
                timeout=args.timeout,
                topology=args.topology,
                top_n=args.top_n,
                ixia_inventory=args.ixia_inventory,
                ixia_session_id=args.ixia_session_id,
                running_wait=args.running_wait,
                post_wait=args.post_wait,
                resume_after_post=args.resume_after_post,
                settle_seconds=args.settle_seconds,
                interval_seconds=args.interval_seconds,
                stop_on_failure=args.stop_on_failure,
                stress_iterations=args.stress_iterations,
                node=args.node,
                interface=args.interface,
                targets=args.targets,
                selected_nodes=args.selected_nodes,
                one_per_node=args.one_per_node,
                ui_server_url=args.ui_server_url,
                skip_ui_check=args.skip_ui_check,
                enable_live_monitor=args.enable_live_monitor,
                live_monitor_iterations=args.live_monitor_iterations,
                live_monitor_interval=args.live_monitor_interval,
                enable_port_stats=args.enable_port_stats,
                bug_replay_count=args.bug_replay_count,
                baseline_window=args.baseline_window,
                running_decay=args.running_decay,
                settle_gap=args.settle_gap,
                post_window=args.post_window,
                post_sample_count=args.post_sample_count,
                post_sample_interval=args.post_sample_interval,
                pre_event_stabilize_seconds=args.pre_event_stabilize_seconds,
                strict_pre_event_gate=args.strict_pre_event_gate,
            )
        if args.suite_id:
            summary_path = os.path.join(
                "artifacts", "campaigns", args.rca_run_id, "rca_case_summary.json"
            )
            ui_report_path = os.path.join(
                "artifacts", "campaigns", args.rca_run_id, "rca_ui_report.json"
            )

            if os.path.exists(summary_path) and os.path.exists(ui_report_path):
                register_run(
                    suite_id=args.suite_id,
                    suite_name=args.suite_name or args.suite_id,
                    test_case_id=args.test_case_id,
                    run_id=args.rca_run_id,
                    scenario=args.scenario,
                    summary_path=summary_path,
                    ui_report_path=ui_report_path,
                )

                suite_summary = write_suite_summary(suite_id=args.suite_id)
                suite_dashboard = write_suite_dashboard(suite_id=args.suite_id)

                print(f"[SUITE] summary written: {suite_summary}")
                print(f"[SUITE] dashboard written: {suite_dashboard}")
            else:
                print(
                    f"[SUITE] skipped registry update because summary/ui report is missing "
                    f"for run_id={args.rca_run_id}"
                    )

        return 0 if result["final_status"] in ("PASS", "PARTIAL", "BUG-CANDIDATE") else 1

        suite_run_id = args.suite_run_id
        if not suite_run_id:
            parts = []
            if args.release_tag:
                parts.append(sanitize_name(args.release_tag))
            parts.append(sanitize_name(args.suite))
            parts.append(utc_compact())
            suite_run_id = "_".join(parts)

        suite_summary = run_suite(
            suite_name=args.suite,
            suite_run_id=suite_run_id,
            release_tag=args.release_tag,
            continue_on_failure=args.continue_on_failure,
            src=args.src,
            dst=args.dst,
            intent_name=args.intent_name,
            nodes=args.nodes,
            profile=args.profile,
            timeout=args.timeout,
            topology=args.topology,
            top_n=args.top_n,
            ixia_inventory=args.ixia_inventory,
            ixia_session_id=args.ixia_session_id,
            running_wait=args.running_wait,
            post_wait=args.post_wait,
            resume_after_post=args.resume_after_post,
            settle_seconds=args.settle_seconds,
            interval_seconds=args.interval_seconds,
            stop_on_failure=args.stop_on_failure,
            stress_iterations=args.stress_iterations,
            node=args.node,
            interface=args.interface,
            targets=args.targets,
            selected_nodes=args.selected_nodes,
            one_per_node=args.one_per_node,
            ui_server_url=args.ui_server_url,
            skip_ui_check=args.skip_ui_check,
            enable_live_monitor=args.enable_live_monitor,
            live_monitor_iterations=args.live_monitor_iterations,
            live_monitor_interval=args.live_monitor_interval,
            enable_port_stats=args.enable_port_stats,
            bug_replay_count=args.bug_replay_count,
            post_sample_count=args.post_sample_count,
            post_sample_interval=args.post_sample_interval,
        )

        return 0 if suite_summary["failed"] == 0 else 1

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
