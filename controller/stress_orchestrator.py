import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import paramiko

from controller.config_loader import load_inventory
from typing import Any, Dict, List, Optional

# Reuse existing RCA helpers instead of re-implementing telemetry logic
from controller.run_rca_case import (
    IxiaClient,
    collect_snapshot,
    telemetry_json_path,
    evaluate_pre_event_cleanliness,
)

from controller.ecmp_phase_sampler import (
    collect_ecmp_phase_snapshot,
    encode_iface_for_snapshot,
)

from controller.core import (
    StressActionContext,
    stress_action_registry,
)

from controller.utils import atomic_write_json

BASE_DIR = Path("/root/fabric-controller")
ARTIFACTS_DIR = BASE_DIR / "artifacts"
OUTPUT_DIR = ARTIFACTS_DIR / "orchestrator"
INVENTORY_FILE = BASE_DIR / "inventory" / "inventory.active.yaml"

TOPOLOGY_FILE = ARTIFACTS_DIR / "topology" / "discovered_topology.json"
VALIDATION_JSON = ARTIFACTS_DIR / "validation" / "fabric_validation_report.json"
VALIDATION_TXT = ARTIFACTS_DIR / "validation" / "fabric_validation_report.txt"
PRECHECK_JSON = ARTIFACTS_DIR / "precheck" / "stress_precheck_report.json"
PRECHECK_TXT = ARTIFACTS_DIR / "precheck" / "stress_precheck_report.txt"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def default_run_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def first_non_empty(*values):
    for value in values:
        if value not in (None, "", {}):
            return value
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI-DC Stress & Validation Controller - Stress Orchestrator"
    )
    parser.add_argument(
        "--mode",
        default="noop",
        choices=[
            "noop",
            "interface_bounce",
            "interface_hold_restore",
            "interface_flap",
            "interface_shutdown",
            "interface_restore",
            "bgp_clear",
        ],
        help="Stress mode to execute.",
    )
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=10,
        help="Seconds to wait after stress action before validation.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=0,
        help="Seconds to wait between iterations.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of stress iterations to execute.",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop the loop immediately when an iteration fails.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run identifier. Default is timestamp-based.",
    )
    parser.add_argument(
        "--node",
        default=None,
        help="Single target node name from inventory.",
    )
    parser.add_argument(
        "--interface",
        default=None,
        help="Single target interface, used with interface_bounce mode.",
    )
    parser.add_argument(
        "--targets",
        default=None,
        help=(
            "Comma-separated targets for parallel execution. "
            "For bgp_clear: leaf1,leaf2,leaf3 "
            "For interface_bounce use node|interface format: "
            "leaf1|et-0/0/11:0,leaf2|et-0/0/11:0"
        ),
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Maximum number of parallel stress worker threads.",
    )
    parser.add_argument(
        "--stress-orchestrator-report",
        help="Optional path to stress_orchestrator_report.json for trigger/event correlation",
    )

    parser.add_argument(
        "--pre-event-stabilize-seconds",
        type=int,
        default=10,
        help="Seconds to wait after precheck passes before confirming clean baseline and injecting stress.",
    )
    parser.add_argument(
        "--strict-pre-event-gate",
        action="store_true",
        help="Fail the run if pre-event confirmation detects pre-existing instability.",
    )


    parser.add_argument(
        "--ixia-inventory",
        default=None,
        help="Path to ixia inventory json used to start/stop traffic for pre-event baseline validation.",
    )
    parser.add_argument(
        "--ixia-session-id",
        type=int,
        default=None,
        help="Optional IXIA session id. If omitted, the client resolves the active session.",
    )
    parser.add_argument(
        "--baseline-profile",
        default="hotspot_congestion_qmon",
        help="Telemetry profile used for pre-event traffic baseline validation.",
    )
    parser.add_argument(
        "--baseline-nodes",
        default=None,
        help="Comma-separated nodes to collect baseline telemetry from before event injection.",
    )
    parser.add_argument(
        "--baseline-timeout",
        type=int,
        default=30,
        help="Timeout for pre-event baseline telemetry collection.",
    )
    parser.add_argument(
        "--baseline-topology",
        default=str(TOPOLOGY_FILE),
        help="Topology file passed to telemetry collection for pre-event baseline validation.",
    )

    parser.add_argument(
        "--degraded-hold-seconds",
        type=int,
        default=300,
        help="How long to keep interfaces down before restore.",
    )

    parser.add_argument(
        "--restore-after-degraded-validation",
        action="store_true",
        help="Restore interfaces after degraded hold validation.",
    )

    parser.add_argument("--degraded-ecmp-sample-count", type=int, default=3)
    parser.add_argument("--degraded-ecmp-sample-interval", type=int, default=30)
    parser.add_argument(
        "--degraded-sample-start-delay",
        type=int,
        default=60,
        help="Wait time after interface disable before degraded ECMP sampling starts.",
    )

    parser.add_argument(
        "--degraded-ecmp-analysis-targets",
        default="",
        help="Comma-separated node:interface list to collect during degraded hold.",
    )

    parser.add_argument("--flap-repeat", type=int, default=5)
    parser.add_argument("--flap-down-seconds", type=int, default=10)
    parser.add_argument("--flap-up-wait-seconds", type=int, default=60)
    return parser.parse_args()


def run_cmd(cmd, step_name):
    print(f"\n[STEP] {step_name}")
    print(f"  CMD: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        return {
            "step": name,
            "status": "fail",
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"timeout after 300s: {' '.join(cmd)}",
        }

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    return {
        "step": step_name,
        "command": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": "pass" if result.returncode == 0 else "fail",
    }


def load_json_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    with open(path, "r") as f:
        return json.load(f)


def load_inventory_data():
    return load_inventory(str(INVENTORY_FILE))


def get_node_connection(node_name, inventory):
    node_data = inventory.get("nodes", {}).get(node_name)
    if not node_data:
        raise KeyError(f"Node '{node_name}' not found in inventory")

    defaults = inventory.get("defaults", {})
    auth_defaults = inventory.get("auth", {})
    cred_defaults = inventory.get("credentials", {})
    conn_defaults = inventory.get("connection", {})
    device_defaults = inventory.get("device_defaults", {})

    node_conn = node_data.get("connection", {})
    node_auth = node_data.get("auth", {})
    node_creds = node_data.get("credentials", {})

    host = first_non_empty(
        node_data.get("management_ip"),
        node_data.get("mgmt_ip"),
        node_data.get("ip"),
        node_data.get("host"),
        node_data.get("hostname"),
        node_conn.get("host"),
        node_conn.get("management_ip"),
        defaults.get("management_ip"),
        conn_defaults.get("host"),
        conn_defaults.get("management_ip"),
    )

    user = first_non_empty(
        node_data.get("username"),
        node_data.get("user"),
        node_conn.get("username"),
        node_conn.get("user"),
        node_auth.get("username"),
        node_auth.get("user"),
        node_creds.get("username"),
        node_creds.get("user"),
        defaults.get("username"),
        defaults.get("user"),
        auth_defaults.get("username"),
        auth_defaults.get("user"),
        cred_defaults.get("username"),
        cred_defaults.get("user"),
        conn_defaults.get("username"),
        conn_defaults.get("user"),
        device_defaults.get("username"),
        device_defaults.get("user"),
        os.getenv("FABRIC_CONTROLLER_USERNAME"),
        "root",
    )

    password = first_non_empty(
        node_data.get("password"),
        node_conn.get("password"),
        node_auth.get("password"),
        node_creds.get("password"),
        defaults.get("password"),
        auth_defaults.get("password"),
        cred_defaults.get("password"),
        conn_defaults.get("password"),
        device_defaults.get("password"),
        os.getenv("FABRIC_CONTROLLER_PASSWORD"),
    )

    if not host:
        raise ValueError(f"Management IP/host not found for node '{node_name}' in inventory")

    if not password:
        raise ValueError(
            f"Password not found in inventory for node '{node_name}'. "
            f"Checked node-level, nested auth/connection blocks, inventory defaults, and FABRIC_CONTROLLER_PASSWORD."
        )

    return {
        "host": host,
        "user": user,
        "password": password,
    }


def run_remote_command(host, user, password, remote_cmd, step_name, timeout=120):
    print(f"\n[STEP] {step_name}")
    print(f"  REMOTE: {user}@{host}")
    print(f"  CMD   : {remote_cmd}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    stdout_text = ""
    stderr_text = ""
    returncode = 0

    try:
        client.connect(
            hostname=host,
            username=user,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=30,
            banner_timeout=30,
            auth_timeout=30,
        )

        stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=timeout)
        returncode = stdout.channel.recv_exit_status()
        stdout_text = stdout.read().decode(errors="replace")
        stderr_text = stderr.read().decode(errors="replace")

        if stdout_text:
            print(stdout_text, end="")
        if stderr_text:
            print(stderr_text, end="", file=sys.stderr)

    except Exception as exc:
        returncode = 1
        stderr_text = str(exc)
        print(f"  ERROR: {stderr_text}", file=sys.stderr)

    finally:
        client.close()

    return {
        "step": step_name,
        "command": remote_cmd,
        "returncode": returncode,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "status": "pass" if returncode == 0 else "fail",
    }


def copy_file_if_exists(src: Path, dst: Path):
    if src.exists():
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)
        return True
    return False


def snapshot_artifacts(snapshot_root: Path, stage: str):
    stage_root = snapshot_root / stage
    copied = []

    targets = [
        (TOPOLOGY_FILE, stage_root / "topology" / TOPOLOGY_FILE.name),
        (VALIDATION_JSON, stage_root / "validation" / VALIDATION_JSON.name),
        (VALIDATION_TXT, stage_root / "validation" / VALIDATION_TXT.name),
        (PRECHECK_JSON, stage_root / "precheck" / PRECHECK_JSON.name),
        (PRECHECK_TXT, stage_root / "precheck" / PRECHECK_TXT.name),
    ]

    for src, dst in targets:
        if copy_file_if_exists(src, dst):
            copied.append(str(dst))

    return copied


def summarize_pipeline_steps(steps):
    total = len(steps)
    failed = [step for step in steps if step["status"] != "pass"]

    return {
        "total_steps": total,
        "failed_steps": len(failed),
        "status": "pass" if not failed else "fail",
        "failed_step_names": [step["step"] for step in failed],
    }


def run_pipeline(stage_label):
    steps = []

    steps.append(run_cmd(
        ["python", "-m", "controller.collect_device_facts"],
        f"collect_device_facts ({stage_label})"
    ))
    if steps[-1]["returncode"] != 0:
        return steps

    steps.append(run_cmd(
        ["python", "-m", "controller.topology_discovery"],
        f"topology_discovery ({stage_label})"
    ))
    if steps[-1]["returncode"] != 0:
        return steps

    steps.append(run_cmd(
        ["python", "-m", "controller.topology_validator"],
        f"topology_validator ({stage_label})"
    ))
    if steps[-1]["returncode"] != 0:
        return steps

    steps.append(run_cmd(
        ["python", "-m", "controller.stress_precheck"],
        f"stress_precheck ({stage_label})"
    ))

    return steps


def run_noop_action(settle_seconds):
    print("\n[STRESS] mode=noop")
    print("  No-op stress action selected. No changes applied to the fabric.")
    time.sleep(settle_seconds)
    return {
        "stress_mode": "noop",
        "status": "pass",
        "details": f"No-op action executed. Slept for {settle_seconds} seconds.",
    }

def run_interface_admin_action(node, interface, inventory, action, step_name):
    if not node:
        return None, {
            "status": "fail",
            "details": "Missing required argument: --node",
            "target": {"node": node, "interface": interface},
        }

    if not interface:
        return None, {
            "status": "fail",
            "details": "Missing required argument: --interface",
            "target": {"node": node, "interface": interface},
        }

    try:
        conn = get_node_connection(node, inventory)
    except Exception as exc:
        return None, {
            "status": "fail",
            "details": str(exc),
            "target": {"node": node, "interface": interface},
        }

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    if action == "disable":
        cmd = (
            f'cli -c "configure; '
            f'set interfaces {interface} disable; '
            f'commit and-quit"'
        )
    elif action == "enable":
        cmd = (
            f'cli -c "configure; '
            f'delete interfaces {interface} disable; '
            f'commit and-quit"'
        )
    else:
        return conn, {
            "status": "fail",
            "details": f"Unsupported interface admin action: {action}",
            "target": {"node": node, "interface": interface, "host": host},
        }

    step = run_remote_command(
        host,
        user,
        password,
        cmd,
        f"{step_name} {action} {node}:{interface}",
    )

    return conn, step


def run_interface_shutdown(node, interface, inventory):
    print(f"\n[STRESS] mode=interface_shutdown node={node} interface={interface}")

    conn, step = run_interface_admin_action(
        node=node,
        interface=interface,
        inventory=inventory,
        action="disable",
        step_name="interface_shutdown",
    )

    if step.get("status") == "fail" and "returncode" not in step:
        return {
            "stress_mode": "interface_shutdown",
            "status": "fail",
            "details": step["details"],
            "target": step.get("target", {"node": node, "interface": interface}),
            "steps": [],
        }

    host = conn["host"] if conn else None

    return {
        "stress_mode": "interface_shutdown",
        "status": "pass" if step.get("returncode") == 0 else "fail",
        "details": (
            f"Interface shutdown completed on {node}:{interface}."
            if step.get("returncode") == 0
            else f"Failed to shutdown interface {node}:{interface}."
        ),
        "target": {"node": node, "interface": interface, "host": host},
        "steps": [step],
    }


def run_interface_restore(node, interface, inventory, settle_seconds=10):
    print(f"\n[STRESS] mode=interface_restore node={node} interface={interface}")

    conn, step = run_interface_admin_action(
        node=node,
        interface=interface,
        inventory=inventory,
        action="enable",
        step_name="interface_restore",
    )

    if step.get("status") == "fail" and "returncode" not in step:
        return {
            "stress_mode": "interface_restore",
            "status": "fail",
            "details": step["details"],
            "target": step.get("target", {"node": node, "interface": interface}),
            "steps": [],
        }

    host = conn["host"] if conn else None

    if step.get("returncode") == 0:
        print(f"  Waiting {settle_seconds} seconds for fabric recovery...")
        time.sleep(max(0, int(settle_seconds or 0)))

    return {
        "stress_mode": "interface_restore",
        "status": "pass" if step.get("returncode") == 0 else "fail",
        "details": (
            f"Interface restore completed on {node}:{interface}."
            if step.get("returncode") == 0
            else f"Failed to restore interface {node}:{interface}."
        ),
        "target": {"node": node, "interface": interface, "host": host},
        "steps": [step],
    }

def run_interface_flap(
    node,
    interface,
    inventory,
    down_seconds=10,
    up_wait_seconds=60,
    repeat=5,
):
    print(
        f"\n[STRESS] mode=interface_flap node={node} interface={interface} "
        f"repeat={repeat} down_seconds={down_seconds} up_wait_seconds={up_wait_seconds}"
    )

    steps = []
    host = None

    repeat = max(1, int(repeat or 1))
    down_seconds = max(0, int(down_seconds or 0))
    up_wait_seconds = max(0, int(up_wait_seconds or 0))

    for idx in range(repeat):
        iteration = idx + 1

        conn, step_down = run_interface_admin_action(
            node=node,
            interface=interface,
            inventory=inventory,
            action="disable",
            step_name=f"interface_flap iteration={iteration}",
        )

        if step_down["status"] == "fail" and "returncode" not in step_down:
            print(f"  ERROR: {step_down['details']}")
            return {
                "stress_mode": "interface_flap",
                "status": "fail",
                "details": step_down["details"],
                "target": step_down.get("target", {"node": node, "interface": interface}),
                "steps": steps,
            }

        host = conn["host"] if conn else host
        steps.append(step_down)

        if step_down["returncode"] != 0:
            return {
                "stress_mode": "interface_flap",
                "status": "fail",
                "details": f"Failed to disable interface {node}:{interface} on iteration {iteration}",
                "target": {"node": node, "interface": interface, "host": host},
                "iteration": iteration,
                "steps": steps,
            }

        print(f"  Iteration {iteration}/{repeat}: waiting {down_seconds}s while disabled")
        time.sleep(down_seconds)

        conn, step_up = run_interface_admin_action(
            node=node,
            interface=interface,
            inventory=inventory,
            action="enable",
            step_name=f"interface_flap iteration={iteration}",
        )

        if step_up["status"] == "fail" and "returncode" not in step_up:
            print(f"  ERROR: {step_up['details']}")
            return {
                "stress_mode": "interface_flap",
                "status": "fail",
                "details": step_up["details"],
                "target": step_up.get("target", {"node": node, "interface": interface}),
                "iteration": iteration,
                "steps": steps,
            }

        host = conn["host"] if conn else host
        steps.append(step_up)

        if step_up["returncode"] != 0:
            return {
                "stress_mode": "interface_flap",
                "status": "fail",
                "details": f"Failed to re-enable interface {node}:{interface} on iteration {iteration}",
                "target": {"node": node, "interface": interface, "host": host},
                "iteration": iteration,
                "steps": steps,
            }

        print(f"  Iteration {iteration}/{repeat}: waiting {up_wait_seconds}s for recovery")
        time.sleep(up_wait_seconds)

    return {
        "stress_mode": "interface_flap",
        "status": "pass",
        "details": (
            f"Interface flap completed on {node}:{interface}; "
            f"repeat={repeat}, down_seconds={down_seconds}, up_wait_seconds={up_wait_seconds}."
        ),
        "target": {"node": node, "interface": interface, "host": host},
        "repeat": repeat,
        "down_seconds": down_seconds,
        "up_wait_seconds": up_wait_seconds,
        "steps": steps,
    }

def run_interface_bounce(node, interface, inventory, settle_seconds):
    print(f"\n[STRESS] mode=interface_bounce node={node} interface={interface}")

    conn, step1 = run_interface_admin_action(
        node=node,
        interface=interface,
        inventory=inventory,
        action="disable",
        step_name="interface_bounce",
    )

    if step1["status"] == "fail" and "returncode" not in step1:
        print(f"  ERROR: {step1['details']}")
        return {
            "stress_mode": "interface_bounce",
            "status": "fail",
            "details": step1["details"],
            "target": step1.get("target", {"node": node, "interface": interface}),
            "steps": [],
        }

    if step1["returncode"] != 0:
        return {
            "stress_mode": "interface_bounce",
            "status": "fail",
            "details": f"Failed to disable interface {node}:{interface}",
            "target": {
                "node": node,
                "interface": interface,
                "host": conn["host"] if conn else None,
            },
            "steps": [step1],
        }

    print(f"  Waiting {settle_seconds} seconds before re-enable...")
    time.sleep(settle_seconds)

    conn, step2 = run_interface_admin_action(
        node=node,
        interface=interface,
        inventory=inventory,
        action="enable",
        step_name="interface_bounce",
    )

    if step2["status"] == "fail" and "returncode" not in step2:
        print(f"  ERROR: {step2['details']}")
        return {
            "stress_mode": "interface_bounce",
            "status": "fail",
            "details": step2["details"],
            "target": step2.get("target", {"node": node, "interface": interface}),
            "steps": [step1],
        }

    if step2["returncode"] != 0:
        return {
            "stress_mode": "interface_bounce",
            "status": "fail",
            "details": f"Failed to re-enable interface {node}:{interface}",
            "target": {
                "node": node,
                "interface": interface,
                "host": conn["host"] if conn else None,
            },
            "steps": [step1, step2],
        }

    print(f"  Waiting {settle_seconds} seconds for fabric recovery...")
    time.sleep(settle_seconds)

    return {
        "stress_mode": "interface_bounce",
        "status": "pass",
        "details": f"Interface bounce completed on {node}:{interface}.",
        "target": {
            "node": node,
            "interface": interface,
            "host": conn["host"] if conn else None,
        },
        "steps": [step1, step2],
    }


def run_interface_hold_restore(
    node,
    interface,
    inventory,
    settle_seconds,
    degraded_hold_seconds,
    restore_after_degraded_validation,
    degraded_ecmp_sample_count: int = 3,
    degraded_ecmp_sample_interval: int = 30,
    degraded_sample_start_delay: int = 60,
    degraded_ecmp_analysis_targets=None,
    run_id=None,
    phase_profile: str = "hotspot_congestion_qmon_phase",
    topology: str = "artifacts/topology/topology_full.json",
    timeout: int = 30,
):

    def _parse_degraded_sample_targets(value):
        targets = []

        if isinstance(value, list):
            return value

        for item in str(value or "").split(","):
            item = item.strip()
            if not item or ":" not in item:
                continue

            node_name, iface_name = item.split(":", 1)
            targets.append({
                "node": node_name.strip(),
                "interface": iface_name.strip().replace("~", ":"),
            })

        return targets

    print(f"\n[STRESS] mode=interface_hold_restore node={node} interface={interface}")

    steps = []
    degraded_samples = []
    degraded_sample_paths = []

    degraded_hold_start_ts = None
    degraded_hold_end_ts = None
    restore_start_ts = None

    # ------------------------------------------------------------------
    # Step 1: Disable selected member
    # ------------------------------------------------------------------
    conn, step1 = run_interface_admin_action(
        node=node,
        interface=interface,
        inventory=inventory,
        action="disable",
        step_name="interface_hold_restore",
    )

    if step1["status"] == "fail" and "returncode" not in step1:
        print(f"  ERROR: {step1['details']}")
        return {
            "stress_mode": "interface_hold_restore",
            "status": "fail",
            "details": step1["details"],
            "target": step1.get("target", {"node": node, "interface": interface}),
        }

    host = conn["host"] if conn else None
    steps.append(step1)

    if step1["returncode"] != 0:
        return {
            "stress_mode": "interface_hold_restore",
            "status": "fail",
            "details": f"Failed to disable interface {node}:{interface}",
            "target": {
                "node": node,
                "interface": interface,
                "host": host,
            },
            "degraded_state": {
                "enabled": True,
                "hold_seconds": degraded_hold_seconds,
                "restore_after_degraded_validation": restore_after_degraded_validation,
            },
            "steps": steps,
            "degraded_ecmp_samples": degraded_samples,
        }

    # ------------------------------------------------------------------
    # Step 2: True degraded HOLD window
    # ------------------------------------------------------------------
    if degraded_sample_start_delay > 0:
        time.sleep(degraded_sample_start_delay)

    sample_count = max(1, int(degraded_ecmp_sample_count or 1))
    sample_interval = max(1, int(degraded_ecmp_sample_interval or 30))

    degraded_hold_start_ts = datetime.now(timezone.utc).isoformat()

    print(
        f"  Holding degraded state for {degraded_hold_seconds} seconds "
        f"(sample_count={sample_count}, sample_interval={sample_interval}s)"
    )

    sample_targets = _parse_degraded_sample_targets(degraded_ecmp_analysis_targets)

    if not sample_targets:
        sample_targets = [{
            "node": node,
            "interface": interface,
        }]

    fault_encoded_iface = encode_iface_for_snapshot(interface)

    for idx in range(sample_count):
        sample_ts = datetime.now(timezone.utc).isoformat()

        snapshot_name = (
            f"ecmp_degraded_fault_{node}_{fault_encoded_iface}_{idx + 1}"
        )

        sample_path = collect_ecmp_phase_snapshot(
            run_id=run_id,
            snapshot_name=snapshot_name,
            profile=phase_profile,
            node=node,
            interface=interface,
            topology=topology,
            timeout=timeout,
        )

        sample = {
            "sample": f"degraded_ecmp_sample_{idx + 1}",
            "node": node,
            "interface": interface,
            "timestamp": sample_ts,
            "phase": "degraded_hold",
            "inside_hold_window": True,
            "path": sample_path,
        }

        degraded_samples.append(sample)
        degraded_sample_paths.append(sample_path)

        print(
            f"  [DEGRADED-ECMP] sample={idx + 1}/{sample_count} "
            f"fault={node}:{interface} "
            f"ts={sample_ts} path={sample_path}"
        )

        if idx < sample_count - 1:
            time.sleep(sample_interval)

    elapsed_sample_time = (sample_count - 1) * sample_interval
    remaining_hold = max(0, int(degraded_hold_seconds or 0) - elapsed_sample_time)

    if remaining_hold > 0:
        print(f"  Remaining degraded hold sleep={remaining_hold}s")
        time.sleep(remaining_hold)

    degraded_hold_end_ts = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Step 3: Restore selected member
    # ------------------------------------------------------------------
    if restore_after_degraded_validation:
        restore_start_ts = datetime.now(timezone.utc).isoformat()

        conn, step2 = run_interface_admin_action(
            node=node,
            interface=interface,
            inventory=inventory,
            action="enable",
            step_name="interface_hold_restore",
        )
        steps.append(step2)

        if step2["status"] == "fail" and "returncode" not in step2:
            print(f"  ERROR: {step2['details']}")
            return {
                "stress_mode": "interface_hold_restore",
                "status": "fail",
                "details": step2["details"],
                "target": step2.get("target", {"node": node, "interface": interface}),
                "degraded_state": {
                    "enabled": True,
                    "hold_seconds": degraded_hold_seconds,
                    "restore_after_degraded_validation": restore_after_degraded_validation,
                },
                "phase_timestamps": {
                    "degraded_hold_start_ts": degraded_hold_start_ts,
                    "degraded_hold_end_ts": degraded_hold_end_ts,
                    "restore_start_ts": restore_start_ts,
                },
                "steps": steps,
                "degraded_ecmp_samples": degraded_samples,
                "ecmp_degraded_sample_paths": degraded_sample_paths,
            }

        if step2["returncode"] != 0:
            return {
                "stress_mode": "interface_hold_restore",
                "status": "fail",
                "details": f"Failed to re-enable interface {node}:{interface}",
                "target": {
                    "node": node,
                    "interface": interface,
                    "host": host,
                },
                "degraded_state": {
                    "enabled": True,
                    "hold_seconds": degraded_hold_seconds,
                    "restore_after_degraded_validation": restore_after_degraded_validation,
                },
                "phase_timestamps": {
                    "degraded_hold_start_ts": degraded_hold_start_ts,
                    "degraded_hold_end_ts": degraded_hold_end_ts,
                    "restore_start_ts": restore_start_ts,
                },
                "steps": steps,
                "degraded_ecmp_samples": degraded_samples,
                "ecmp_degraded_sample_paths": degraded_sample_paths,
            }

        print(f"  Waiting {settle_seconds} seconds for fabric recovery...")
        time.sleep(max(0, int(settle_seconds or 0)))
    else:
        print("  Restore skipped by request.")

    return {
        "stress_mode": "interface_hold_restore",
        "status": "pass",
        "details": (
            f"Interface degraded hold completed on {node}:{interface}; "
            f"hold_seconds={degraded_hold_seconds}, "
            f"restore={restore_after_degraded_validation}."
        ),
        "target": {
            "node": node,
            "interface": interface,
            "host": host,
        },
        "degraded_state": {
            "enabled": True,
            "hold_seconds": degraded_hold_seconds,
            "restore_after_degraded_validation": restore_after_degraded_validation,
        },
        "phase_timestamps": {
            "degraded_hold_start_ts": degraded_hold_start_ts,
            "degraded_hold_end_ts": degraded_hold_end_ts,
            "restore_start_ts": restore_start_ts,
        },
        "steps": steps,
        "degraded_ecmp_samples": degraded_samples,
        "ecmp_degraded_sample_paths": degraded_sample_paths,
    }



def run_bgp_clear(node, inventory, settle_seconds):
    print(f"\n[STRESS] mode=bgp_clear node={node}")

    if not node:
        details = "Missing required argument: --node"
        print(f"  ERROR: {details}")
        return {
            "stress_mode": "bgp_clear",
            "status": "fail",
            "details": details,
            "target": {"node": node},
        }

    try:
        conn = get_node_connection(node, inventory)
    except Exception as exc:
        details = str(exc)
        print(f"  ERROR: {details}")
        return {
            "stress_mode": "bgp_clear",
            "status": "fail",
            "details": details,
            "target": {"node": node},
        }

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    clear_cmd = 'cli -c "clear bgp neighbor all"'
    step1 = run_remote_command(
        host, user, password, clear_cmd,
        f"bgp_clear on {node}"
    )

    if step1["returncode"] != 0:
        return {
            "stress_mode": "bgp_clear",
            "status": "fail",
            "details": f"Failed to clear BGP neighbors on {node}",
            "target": {
                "node": node,
                "host": host,
            },
            "steps": [step1],
        }

    print(f"  Waiting {settle_seconds} seconds for BGP recovery...")
    time.sleep(settle_seconds)

    return {
        "stress_mode": "bgp_clear",
        "status": "pass",
        "details": f"BGP clear completed on {node}.",
        "target": {
            "node": node,
            "host": host,
        },
        "steps": [step1],
    }



# ---------------------------------------------------------------------------
# Registry-compatible stress action adapters
#
# Each adapter accepts one StressActionContext and calls the existing,
# production-tested handler without changing the handler or result schema.
# ---------------------------------------------------------------------------

def _execute_noop(context: StressActionContext):
    return run_noop_action(
        context.settle_seconds,
    )


def _execute_bgp_clear(context: StressActionContext):
    return run_bgp_clear(
        node=context.target.get("node"),
        inventory=context.inventory,
        settle_seconds=context.settle_seconds,
    )


def _execute_interface_bounce(context: StressActionContext):
    return run_interface_bounce(
        node=context.target.get("node"),
        interface=context.target.get("interface"),
        inventory=context.inventory,
        settle_seconds=context.settle_seconds,
    )


def _execute_interface_flap(context: StressActionContext):
    return run_interface_flap(
        node=context.target.get("node"),
        interface=context.target.get("interface"),
        inventory=context.inventory,
        down_seconds=context.option("flap_down_seconds", 10),
        up_wait_seconds=context.option(
            "flap_up_wait_seconds",
            context.settle_seconds,
        ),
        repeat=context.option("flap_repeat", 5),
    )


def _execute_interface_shutdown(context: StressActionContext):
    return run_interface_shutdown(
        node=context.target.get("node"),
        interface=context.target.get("interface"),
        inventory=context.inventory,
    )


def _execute_interface_restore(context: StressActionContext):
    return run_interface_restore(
        node=context.target.get("node"),
        interface=context.target.get("interface"),
        inventory=context.inventory,
        settle_seconds=context.settle_seconds,
    )


def _execute_interface_hold_restore(context: StressActionContext):
    return run_interface_hold_restore(
        node=context.target["node"],
        interface=context.target["interface"],
        inventory=context.inventory,
        settle_seconds=context.settle_seconds,
        degraded_hold_seconds=context.option(
            "degraded_hold_seconds",
            300,
        ),
        restore_after_degraded_validation=context.option(
            "restore_after_degraded_validation",
            False,
        ),
        degraded_ecmp_sample_count=context.option(
            "degraded_ecmp_sample_count",
            3,
        ),
        degraded_ecmp_sample_interval=context.option(
            "degraded_ecmp_sample_interval",
            30,
        ),
        degraded_sample_start_delay=context.option(
            "degraded_sample_start_delay",
            60,
        ),
        degraded_ecmp_analysis_targets=context.option(
            "degraded_ecmp_analysis_targets",
        ),
        run_id=context.option("run_id"),
        phase_profile=context.option(
            "phase_profile",
            "hotspot_congestion_qmon_phase",
        ),
        topology=context.option(
            "topology",
            "artifacts/topology/topology_full.json",
        ),
        timeout=context.option("timeout", 30),
    )

def register_builtin_stress_actions() -> None:
    """Register built-in stress handlers.

    replace=True keeps this function safe if the module is reloaded during
    development or testing.
    """

    builtin_actions = {
        "noop": _execute_noop,
        "bgp_clear": _execute_bgp_clear,
        "interface_bounce": _execute_interface_bounce,
        "interface_flap": _execute_interface_flap,
        "interface_shutdown": _execute_interface_shutdown,
        "interface_restore": _execute_interface_restore,
        "interface_hold_restore": _execute_interface_hold_restore,
    }

    for mode, handler in builtin_actions.items():
        stress_action_registry.register(
            mode,
            handler,
            replace=True,
        )

register_builtin_stress_actions()

def parse_targets(mode, targets_arg, node=None, interface=None):
    targets = []

    interface_modes = (
        "interface_bounce",
        "interface_hold_restore",
        "interface_flap",
        "interface_shutdown",
        "interface_restore",
    )

    if mode == "noop":
        return [{}]

    if targets_arg:
        raw_items = [item.strip() for item in targets_arg.split(",") if item.strip()]

        for item in raw_items:
            if mode == "bgp_clear":
                targets.append({"node": item})
            elif mode in interface_modes:
                if "|" not in item:
                    raise ValueError(
                        f"Invalid {mode} target '{item}'. Expected format node|interface"
                    )

                node_name, intf = item.split("|", 1)
                node_name = node_name.strip()
                intf = intf.strip()

                if not node_name or not intf:
                    raise ValueError(
                        f"Invalid {mode} target '{item}'. Expected non-empty node|interface"
                    )

                targets.append({
                    "node": node_name,
                    "interface": intf,
                })
    else:
        if mode == "bgp_clear":
            if not node:
                raise ValueError("For bgp_clear provide --node or --targets")
            targets.append({"node": node})
        elif mode in interface_modes:
            if not node or not interface:
                raise ValueError(f"For {mode} provide --node/--interface or --targets")
            targets.append({
                "node": node,
                "interface": interface,
            })

    return targets


def run_single_stress_target(
    stress_mode,
    target,
    settle_seconds,
    inventory,
    degraded_hold_seconds=300,
    restore_after_degraded_validation=False,
    degraded_ecmp_sample_count: int = 3,
    degraded_ecmp_sample_interval: int = 30,
    degraded_sample_start_delay: int = 60,
    degraded_ecmp_analysis_targets=None,
    run_id=None,
    phase_profile: str = "hotspot_congestion_qmon_phase",
    topology: str = "artifacts/topology/topology_full.json",
    timeout: int = 30,
    flap_repeat=5,
    flap_down_seconds=10,
    flap_up_wait_seconds=60,
):
    context = StressActionContext(
        stress_mode=stress_mode,
        target=dict(target or {}),
        inventory=inventory,
        settle_seconds=settle_seconds,
        options={
            "degraded_hold_seconds": degraded_hold_seconds,
            "restore_after_degraded_validation":
                restore_after_degraded_validation,
            "degraded_ecmp_sample_count":
                degraded_ecmp_sample_count,
            "degraded_ecmp_sample_interval":
                degraded_ecmp_sample_interval,
            "degraded_sample_start_delay":
                degraded_sample_start_delay,
            "degraded_ecmp_analysis_targets":
                degraded_ecmp_analysis_targets,
            "run_id": run_id,
            "phase_profile": phase_profile,
            "topology": topology,
            "timeout": timeout,
            "flap_repeat": flap_repeat,
            "flap_down_seconds": flap_down_seconds,
            "flap_up_wait_seconds": flap_up_wait_seconds,
        },
    )

    handler = stress_action_registry.get(stress_mode)

    if handler is None:
        return {
            "stress_mode": stress_mode,
            "status": "fail",
            "details": f"Unsupported stress mode: {stress_mode}",
            "target": target,
        }

    result = handler(context)

    if not isinstance(result, dict):
        return {
            "stress_mode": stress_mode,
            "status": "fail",
            "details": (
                f"Stress handler for mode '{stress_mode}' returned "
                f"{type(result).__name__}; expected dict"
            ),
            "target": target,
        }

    return result



def run_parallel_stress_actions(
    stress_mode,
    targets,
    settle_seconds,
    parallel,
    inventory,
    degraded_hold_seconds=300,
    restore_after_degraded_validation=False,
    degraded_ecmp_sample_count: int = 3,
    degraded_ecmp_sample_interval: int = 30,
    degraded_sample_start_delay: int = 60,
    degraded_ecmp_analysis_targets=None,
    run_id=None,
    phase_profile: str = "hotspot_congestion_qmon_phase",
    topology: str = "artifacts/topology/topology_full.json",
    timeout: int = 30,
    flap_repeat=5,
    flap_down_seconds=10,
    flap_up_wait_seconds=60,
):
    print(f"\n[STRESS-GROUP] mode={stress_mode} parallel={parallel} targets={len(targets)}")

    if stress_mode == "noop":
        result = run_noop_action(settle_seconds)
        return {
            "stress_mode": stress_mode,
            "status": result["status"],
            "details": result["details"],
            "targets_total": 1,
            "targets_passed": 1 if result["status"] == "pass" else 0,
            "targets_failed": 0 if result["status"] == "pass" else 1,
            "results": [result],
        }

    results = []
    max_workers = max(1, parallel)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                run_single_stress_target,
                stress_mode,
                target,
                settle_seconds,
                inventory,
                degraded_hold_seconds,
                restore_after_degraded_validation,
                degraded_ecmp_sample_count,
                degraded_ecmp_sample_interval,
                degraded_sample_start_delay,
                degraded_ecmp_analysis_targets,
                run_id,
                phase_profile,
                topology,
                timeout,
                flap_repeat,
                flap_down_seconds,
                flap_up_wait_seconds,

            ): target
            for target in targets
        }

        for future in as_completed(future_map):
            target = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "stress_mode": stress_mode,
                    "status": "fail",
                    "details": str(exc),
                    "target": target,
                }
            results.append(result)

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") != "pass")

    return {
        "stress_mode": stress_mode,
        "status": "pass" if failed == 0 else "fail",
        "details": f"Parallel stress execution complete: passed={passed}, failed={failed}",
        "targets_total": len(results),
        "targets_passed": passed,
        "targets_failed": failed,
        "results": results,
    }


def run_stress_action(
    stress_mode,
    settle_seconds,
    inventory,
    node=None,
    interface=None,
    targets_arg=None,
    parallel=1,
    degraded_hold_seconds=300,
    restore_after_degraded_validation=True,
    degraded_ecmp_sample_count: int = 3,
    degraded_ecmp_sample_interval: int = 30,
    degraded_sample_start_delay: int = 60,
    degraded_ecmp_analysis_targets=None,
    run_id = None,
    phase_profile: str = "hotspot_congestion_qmon_phase",
    topology: str = "artifacts/topology/topology_full.json",
    timeout: int = 30,
    flap_repeat=5,
    flap_down_seconds=10,
    flap_up_wait_seconds=60,
):
    try:
        targets = parse_targets(
            mode=stress_mode,
            targets_arg=targets_arg,
            node=node,
            interface=interface,
        )
    except Exception as exc:
        return {
            "stress_mode": stress_mode,
            "status": "fail",
            "details": str(exc),
            "results": [],
        }

    return run_parallel_stress_actions(
        stress_mode=stress_mode,
        targets=targets,
        settle_seconds=settle_seconds,
        parallel=parallel,
        inventory=inventory,
        degraded_hold_seconds=degraded_hold_seconds,
        restore_after_degraded_validation=restore_after_degraded_validation,
        degraded_ecmp_sample_count=degraded_ecmp_sample_count,
        degraded_ecmp_sample_interval=degraded_ecmp_sample_interval,
        degraded_sample_start_delay = degraded_sample_start_delay,
        degraded_ecmp_analysis_targets=degraded_ecmp_analysis_targets,
        run_id=run_id,
        phase_profile=phase_profile,
        topology=topology,
        timeout=timeout,
        flap_repeat=flap_repeat,
        flap_down_seconds=flap_down_seconds,
        flap_up_wait_seconds=flap_up_wait_seconds,
    )


def build_comparison(pre_report, post_report):
    pre_summary = pre_report.get("summary", {})
    post_summary = post_report.get("summary", {})

    return {
        "physical_links": {
            "pre": pre_summary.get("physical_links", {}),
            "post": post_summary.get("physical_links", {}),
        },
        "ip_consistency": {
            "pre": pre_summary.get("ip_consistency", {}),
            "post": post_summary.get("ip_consistency", {}),
        },
        "bgp": {
            "pre": pre_summary.get("bgp", {}),
            "post": post_summary.get("bgp", {}),
        },
        "ready_for_stress": {
            "pre": pre_report.get("ready_for_stress"),
            "post": post_report.get("ready_for_stress"),
        }
    }


def build_iteration_report(iteration, stress_result, post_steps, post_report):
    post_pipeline = summarize_pipeline_steps(post_steps)
    iteration_pass = (
        stress_result.get("status") == "pass" and
        post_pipeline.get("status") == "pass" and
        post_report.get("ready_for_stress") is True
    )

    return {
        "iteration": iteration,
        "timestamp": utc_now(),
        "stress_action": stress_result,
        "post_pipeline": post_pipeline,
        "post_precheck": post_report,
        "status": "pass" if iteration_pass else "fail",
    }


def build_failure_report(pre_steps, stress_mode, reason):
    return {
        "timestamp": utc_now(),
        "overall_status": "fail",
        "pre_pipeline": summarize_pipeline_steps(pre_steps),
        "stress_action": {
            "stress_mode": stress_mode,
            "status": "skipped",
            "details": reason,
        },
        "post_pipeline": {
            "total_steps": 0,
            "failed_steps": 0,
            "status": "skipped",
            "failed_step_names": [],
        },
        "precheck_pre": {
            "ready_for_stress": False,
            "overall_status": "skipped",
            "summary": {
                "physical_links": {},
                "ip_consistency": {},
                "bgp": {},
            }
        },
        "precheck_post": {
            "ready_for_stress": False,
            "overall_status": "skipped",
            "summary": {
                "physical_links": {},
                "ip_consistency": {},
                "bgp": {},
            }
        },
        "comparison": {
            "physical_links": {"pre": {}, "post": {}},
            "ip_consistency": {"pre": {}, "post": {}},
            "bgp": {"pre": {}, "post": {}},
            "ready_for_stress": {"pre": False, "post": False},
        },
        "verdict": {
            "precheck_before_stress": False,
            "precheck_after_stress": False,
            "fabric_stable_after_stress": False,
        }
    }


def _as_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def evaluate_pre_event_gate(pre_report):
    """
    Decide whether the fabric is clean enough BEFORE event injection.

    This is stronger than ready_for_stress:
    - topology must be healthy
    - BGP must be fully up
    - IP consistency should not already be degraded
    """
    summary = pre_report.get("summary", {}) or {}
    physical = summary.get("physical_links", {}) or {}
    bgp = summary.get("bgp", {}) or {}
    ip_consistency = summary.get("ip_consistency", {}) or {}

    missing_links = _as_int(
        physical.get("missing", physical.get("missing_links", 0)),
        0,
    )
    bgp_down = _as_int(
        bgp.get("down", bgp.get("down_sessions", 0)),
        0,
    )
    ip_mismatch = (
        _as_int(ip_consistency.get("mismatch", 0), 0)
        + _as_int(ip_consistency.get("partial", 0), 0)
    )

    ready_for_stress = pre_report.get("ready_for_stress") is True

    reasons = []
    if not ready_for_stress:
        reasons.append("precheck_not_ready")
    if missing_links > 0:
        reasons.append(f"physical_links_missing={missing_links}")
    if bgp_down > 0:
        reasons.append(f"bgp_down={bgp_down}")
    if ip_mismatch > 0:
        reasons.append(f"ip_consistency_mismatch={ip_mismatch}")

    return {
        "pass": len(reasons) == 0,
        "ready_for_stress": ready_for_stress,
        "missing_links": missing_links,
        "bgp_down": bgp_down,
        "ip_mismatch": ip_mismatch,
        "reasons": reasons,
        "summary": {
            "physical_links": physical,
            "bgp": bgp,
            "ip_consistency": ip_consistency,
        },
    }


def build_baseline_contamination_failure_report(
    *,
    run_id,
    archive_root,
    pre_steps,
    pre_report,
    pre_event_gate,
    baseline_gate,
    reason,
):
    return {
        "run_id": run_id,
        "timestamp": utc_now(),
        "archive_root": str(archive_root),
        "overall_status": "fail",
        "campaign": {
            "iterations_requested": 0,
            "iterations_completed": 0,
            "iterations_passed": 0,
            "iterations_failed": 0,
            "stop_on_failure": False,
        },
        "pre_pipeline": summarize_pipeline_steps(pre_steps),
        "precheck_pre": pre_report,
        "pre_event_gate": pre_event_gate,
        "pre_event_traffic_baseline": baseline_gate,
        "iteration_results": [],
        "precheck_post": {
            "ready_for_stress": False,
            "overall_status": "skipped",
            "summary": {
                "physical_links": {},
                "ip_consistency": {},
                "bgp": {},
            },
        },
        "comparison": {
            "physical_links": {
                "pre": pre_report.get("summary", {}).get("physical_links", {}),
                "post": {},
            },
            "ip_consistency": {
                "pre": pre_report.get("summary", {}).get("ip_consistency", {}),
                "post": {},
            },
            "bgp": {
                "pre": pre_report.get("summary", {}).get("bgp", {}),
                "post": {},
            },
            "ready_for_stress": {
                "pre": pre_report.get("ready_for_stress"),
                "post": False,
            },
        },
        "verdict": {
            "precheck_before_stress": pre_report.get("ready_for_stress"),
            "pre_event_gate_passed": pre_event_gate.get("pass"),
            "pre_event_traffic_baseline_passed": baseline_gate.get("pass"),
            "precheck_after_stress": False,
            "fabric_stable_after_stress": False,
        },
        "failure_reason": reason,
    }


def run_pre_event_traffic_baseline(
    *,
    run_id: str,
    ixia_inventory: str,
    ixia_session_id: Optional[int],
    baseline_profile: str,
    baseline_nodes: str,
    baseline_timeout: int,
    baseline_topology: str,
    stabilize_seconds: int,
) -> Dict[str, Any]:
    inv = load_json_file(Path(ixia_inventory))
    api_server = inv.get("ixnetwork_api_server")
    if not api_server:
        raise RuntimeError("ixnetwork_api_server not found in ixia inventory")

    ixia = IxiaClient(
        api_server=api_server,
        inventory_path=ixia_inventory,
        timeout=baseline_timeout,
        verify_tls=False,
    )
    sid = ixia.resolve_session_id(ixia_session_id)

    print("\n[PRE-EVENT-BASELINE] starting IXIA traffic for baseline validation ...")
    ixia.start_traffic(sid)

    print(
        f"[PRE-EVENT-BASELINE] sleeping {stabilize_seconds} seconds with traffic running "
        "before baseline telemetry snapshot ..."
    )
    time.sleep(stabilize_seconds)

    collect_snapshot(
        run_id=run_id,
        snapshot_name="pre_event_baseline",
        profile=baseline_profile,
        nodes=baseline_nodes,
        timeout=baseline_timeout,
        topology_path=baseline_topology,
    )

    snapshot_path = telemetry_json_path(run_id, "pre_event_baseline", baseline_profile)
    baseline_report = load_json_file(Path(snapshot_path))
    cleanliness = evaluate_pre_event_cleanliness(baseline_report)

    return {
        "pass": bool(cleanliness.get("pass")),
        "snapshot_path": snapshot_path,
        "profile": baseline_profile,
        "nodes": baseline_nodes,
        "ixia_session_id": sid,
        "cleanliness": cleanliness,
    }


def stop_pre_event_baseline_traffic(ixia_inventory: str, ixia_session_id: Optional[int], timeout: int = 30):
    inv = load_json_file(Path(ixia_inventory))
    api_server = inv.get("ixnetwork_api_server")
    if not api_server:
        return

    ixia = IxiaClient(
        api_server=api_server,
        inventory_path=ixia_inventory,
        timeout=timeout,
        verify_tls=False,
    )
    sid = ixia.resolve_session_id(ixia_session_id)
    print("\n[PRE-EVENT-BASELINE] stopping IXIA traffic ...")
    ixia.stop_traffic(sid)

def build_pre_event_gate_failure_report(
    *,
    run_id,
    archive_root,
    pre_steps,
    pre_report,
    pre_event_gate,
    reason,
):
    return {
        "run_id": run_id,
        "timestamp": utc_now(),
        "archive_root": str(archive_root),
        "overall_status": "fail",
        "campaign": {
            "iterations_requested": 0,
            "iterations_completed": 0,
            "iterations_passed": 0,
            "iterations_failed": 0,
            "stop_on_failure": False,
        },
        "pre_pipeline": summarize_pipeline_steps(pre_steps),
        "precheck_pre": pre_report,
        "pre_event_gate": pre_event_gate,
        "iteration_results": [],
        "precheck_post": {
            "ready_for_stress": False,
            "overall_status": "skipped",
            "summary": {
                "physical_links": {},
                "ip_consistency": {},
                "bgp": {},
            },
        },
        "comparison": {
            "physical_links": {
                "pre": pre_report.get("summary", {}).get("physical_links", {}),
                "post": {},
            },
            "ip_consistency": {
                "pre": pre_report.get("summary", {}).get("ip_consistency", {}),
                "post": {},
            },
            "bgp": {
                "pre": pre_report.get("summary", {}).get("bgp", {}),
                "post": {},
            },
            "ready_for_stress": {
                "pre": pre_report.get("ready_for_stress"),
                "post": False,
            },
        },
        "verdict": {
            "precheck_before_stress": pre_report.get("ready_for_stress"),
            "pre_event_gate_passed": pre_event_gate.get("pass"),
            "precheck_after_stress": False,
            "fabric_stable_after_stress": False,
        },
        "failure_reason": reason,
    }



def build_final_campaign_report(run_id, archive_root, pre_steps, pre_report, iteration_results, stop_on_failure):
    pre_pipeline = summarize_pipeline_steps(pre_steps)
    total_iterations = len(iteration_results)
    passed_iterations = sum(1 for x in iteration_results if x["status"] == "pass")
    failed_iterations = sum(1 for x in iteration_results if x["status"] == "fail")

    last_post_report = iteration_results[-1]["post_precheck"] if iteration_results else {
        "ready_for_stress": False,
        "summary": {"physical_links": {}, "ip_consistency": {}, "bgp": {}}
    }

    comparison = build_comparison(pre_report, last_post_report)

    overall_pass = (
        pre_pipeline["status"] == "pass" and
        pre_report.get("ready_for_stress") is True and
        failed_iterations == 0 and
        total_iterations > 0
    )

    return {
        "run_id": run_id,
        "timestamp": utc_now(),
        "archive_root": str(archive_root),
        "overall_status": "pass" if overall_pass else "fail",
        "campaign": {
            "iterations_requested": total_iterations,
            "iterations_completed": total_iterations,
            "iterations_passed": passed_iterations,
            "iterations_failed": failed_iterations,
            "stop_on_failure": stop_on_failure,
        },
        "pre_pipeline": pre_pipeline,
        "precheck_pre": pre_report,
        "iteration_results": iteration_results,
        "precheck_post": last_post_report,
        "comparison": comparison,
        "verdict": {
            "precheck_before_stress": pre_report.get("ready_for_stress"),
            "precheck_after_stress": last_post_report.get("ready_for_stress"),
            "fabric_stable_after_stress": last_post_report.get("ready_for_stress") is True,
        }
    }


def write_json_report(report, outfile: Path):
    #with open(outfile, "w") as f:
    #    json.dump(report, f, indent=2)
    atomic_write_json(outfile, report, indent=2)


def write_text_report(report, outfile: Path):
    with open(outfile, "w") as f:
        f.write("STRESS ORCHESTRATOR REPORT\n")
        f.write("==========================\n\n")

        f.write(f"Run ID         : {report.get('run_id', 'N/A')}\n")
        f.write(f"Timestamp      : {report['timestamp']}\n")
        f.write(f"Archive root   : {report.get('archive_root', 'N/A')}\n")
        f.write(f"Overall status : {report['overall_status']}\n\n")

        campaign = report.get("campaign", {})
        if campaign:
            f.write("CAMPAIGN SUMMARY\n")
            f.write("----------------\n")
            f.write(f"Iterations requested : {campaign.get('iterations_requested')}\n")
            f.write(f"Iterations completed : {campaign.get('iterations_completed')}\n")
            f.write(f"Iterations passed    : {campaign.get('iterations_passed')}\n")
            f.write(f"Iterations failed    : {campaign.get('iterations_failed')}\n")
            f.write(f"Stop on failure      : {campaign.get('stop_on_failure')}\n\n")

        f.write("PRE-PIPELINE\n")
        f.write("------------\n")
        f.write(f"Status         : {report['pre_pipeline']['status']}\n")
        f.write(f"Total steps    : {report['pre_pipeline']['total_steps']}\n")
        f.write(f"Failed steps   : {report['pre_pipeline']['failed_steps']}\n")
        failed_pre = report["pre_pipeline"].get("failed_step_names", [])
        if failed_pre:
            f.write(f"Failed names   : {', '.join(failed_pre)}\n")
        f.write("\n")

        pre_event_gate = report.get("pre_event_gate")
        if pre_event_gate:
            f.write("PRE-EVENT GATE\n")
            f.write("--------------\n")
            f.write(f"Pass            : {pre_event_gate.get('pass')}\n")
            f.write(f"Ready for stress: {pre_event_gate.get('ready_for_stress')}\n")
            f.write(f"Missing links   : {pre_event_gate.get('missing_links')}\n")
            f.write(f"BGP down        : {pre_event_gate.get('bgp_down')}\n")
            f.write(f"IP mismatch     : {pre_event_gate.get('ip_mismatch')}\n")
            reasons = pre_event_gate.get("reasons", [])
            if reasons:
                f.write(f"Reasons         : {', '.join(reasons)}\n")
            f.write("\n")

        iteration_results = report.get("iteration_results", [])
        if iteration_results:
            f.write("ITERATION RESULTS\n")
            f.write("-----------------\n")
            for item in iteration_results:
                f.write(
                    f"Iteration {item['iteration']} : status={item['status']} "
                    f"post_ready={item['post_precheck'].get('ready_for_stress')}\n"
                )
                stress = item.get("stress_action", {})
                f.write(
                    f"  stress_status={stress.get('status')} "
                    f"details={stress.get('details')}\n"
                )
                if "targets_total" in stress:
                    f.write(
                        f"  targets_total={stress.get('targets_total')} "
                        f"targets_passed={stress.get('targets_passed')} "
                        f"targets_failed={stress.get('targets_failed')}\n"
                    )
            f.write("\n")

        comparison = report.get("comparison", {})
        if comparison:
            f.write("COMPARISON\n")
            f.write("----------\n")
            f.write(f"Pre ready_for_stress  : {comparison.get('ready_for_stress', {}).get('pre')}\n")
            f.write(f"Post ready_for_stress : {comparison.get('ready_for_stress', {}).get('post')}\n\n")

            for section in ("physical_links", "ip_consistency", "bgp"):
                f.write(f"{section.upper()}\n")
                pre_data = comparison.get(section, {}).get("pre", {})
                post_data = comparison.get(section, {}).get("post", {})
                f.write(f"  pre : {json.dumps(pre_data, sort_keys=True)}\n")
                f.write(f"  post: {json.dumps(post_data, sort_keys=True)}\n\n")

        f.write("VERDICT\n")
        f.write("-------\n")
        f.write(f"Precheck before stress : {report['verdict']['precheck_before_stress']}\n")
        f.write(f"Precheck after stress  : {report['verdict']['precheck_after_stress']}\n")
        f.write(f"Fabric stable after    : {report['verdict']['fabric_stable_after_stress']}\n")


def print_summary(report, json_out, txt_out):
    print(f"\nOrchestrator JSON report : {json_out}")
    print(f"Orchestrator text report : {txt_out}")
    print("\nORCHESTRATOR SUMMARY")
    print(f"  Run ID                    : {report.get('run_id', 'N/A')}")
    print(f"  Overall status            : {report['overall_status']}")
    campaign = report.get("campaign", {})
    if campaign:
        print(f"  Iterations completed      : {campaign.get('iterations_completed')}")
        print(f"  Iterations passed         : {campaign.get('iterations_passed')}")
        print(f"  Iterations failed         : {campaign.get('iterations_failed')}")
    print(f"  Precheck before stress    : {report['verdict']['precheck_before_stress']}")
    print(f"  Precheck after stress     : {report['verdict']['precheck_after_stress']}")
    print(f"  Fabric stable after stress: {report['verdict']['fabric_stable_after_stress']}")
    archive_root = report.get("archive_root")
    if archive_root:
        print(f"  Archive root              : {archive_root}")

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
) -> None:
    files = {
        "pre_telemetry": telemetry_json_path(run_id, "pre", profile),
        "running_telemetry": telemetry_json_path(run_id, "running", profile),
        "post_telemetry": telemetry_json_path(run_id, "post", profile),
        "running_congestion": congestion_json_path(run_id, "running", profile),
        "running_fabric_hotspots": fabric_hotspot_json_path(run_id, "running", profile),
        "running_delta": delta_json_path(run_id, "running", profile),
    }

    if stress_orchestrator_report:
        files["stress_orchestrator_report"] = stress_orchestrator_report

    data = {
        "generated_at": utc_now_iso(),
        "run_id": run_id,
        "intent_name": intent_name,
        "src": src,
        "dst": dst,
        "profile": profile,
        "nodes": nodes,
        "files": files,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    #with open(out_path, "w") as f:
    #    json.dump(data, f, indent=2, sort_keys=False)
    atomic_write_json(out_path, data, indent=2, sort_keys=False)

def main():
    args = parse_args()

    if args.iterations < 1:
        print("ERROR: --iterations must be >= 1", file=sys.stderr)
        sys.exit(1)

    if args.parallel < 1:
        print("ERROR: --parallel must be >= 1", file=sys.stderr)
        sys.exit(1)

    run_id = args.run_id or default_run_id()
    archive_root = OUTPUT_DIR / run_id

    ensure_dir(OUTPUT_DIR)
    ensure_dir(archive_root)

    inventory = load_inventory_data()

    # Baseline pre-pipeline only once
    pre_steps = run_pipeline("pre")
    pre_pipeline_summary = summarize_pipeline_steps(pre_steps)

    if pre_pipeline_summary["status"] != "pass":
        final_report = build_failure_report(
            pre_steps=pre_steps,
            stress_mode=args.mode,
            reason="Skipped because pre-pipeline failed.",
        )
        final_report["run_id"] = run_id
        final_report["archive_root"] = str(archive_root)
    else:
        pre_snapshot_files = snapshot_artifacts(archive_root, "baseline_pre")
        if pre_snapshot_files:
            print("\n[SNAPSHOT] baseline pre artifacts archived")
            for item in pre_snapshot_files:
                print(f"  - {item}")

        pre_report = load_json_file(PRECHECK_JSON)

        if not pre_report.get("ready_for_stress", False):
            final_report = build_failure_report(
                pre_steps=pre_steps,
                stress_mode=args.mode,
                reason="Skipped because precheck did not pass.",
            )
            final_report["run_id"] = run_id
            final_report["archive_root"] = str(archive_root)
        else:
            # --------------------------------------------------------------
            # NEW: pre-event contamination gate
            # Make sure the issue is not already present before injecting chaos
            # --------------------------------------------------------------
            pre_event_gate_initial = evaluate_pre_event_gate(pre_report)

            if not pre_event_gate_initial["pass"]:
                final_report = build_pre_event_gate_failure_report(
                    run_id=run_id,
                    archive_root=archive_root,
                    pre_steps=pre_steps,
                    pre_report=pre_report,
                    pre_event_gate=pre_event_gate_initial,
                    reason=(
                        "Pre-event contamination detected before stress injection: "
                        + ", ".join(pre_event_gate_initial["reasons"])
                    ),
                )
            else:
                if args.pre_event_stabilize_seconds > 0:
                    print(
                        f"\n[PRE-EVENT-GATE] sleeping {args.pre_event_stabilize_seconds} seconds "
                        "before final clean confirmation"
                    )
                    time.sleep(args.pre_event_stabilize_seconds)

                confirm_steps = []
                confirm_steps.append(
                    run_cmd(
                        ["python", "-m", "controller.stress_precheck"],
                        "stress_precheck (pre_event_gate_confirm)",
                    )
                )

                confirm_report = load_json_file(PRECHECK_JSON)
                pre_event_gate_confirm = evaluate_pre_event_gate(confirm_report)

                if confirm_steps[-1]["returncode"] != 0 or not pre_event_gate_confirm["pass"]:
                    final_report = build_pre_event_gate_failure_report(
                        run_id=run_id,
                        archive_root=archive_root,
                        pre_steps=pre_steps,
                        pre_report=confirm_report,
                        pre_event_gate=pre_event_gate_confirm,
                        reason=(
                            "Pre-event confirmation gate failed: "
                            + ", ".join(pre_event_gate_confirm["reasons"])
                        ),
                    )
                else:
                    # ------------------------------------------------------
                    # NEW: true pre-event traffic baseline cleanliness gate
                    # ------------------------------------------------------
                    baseline_gate = {
                        "pass": True,
                        "status": "skipped",
                        "reason": "ixia/baseline args not provided",
                    }

                    if args.ixia_inventory and args.baseline_nodes:
                        baseline_gate = run_pre_event_traffic_baseline(
                            run_id=run_id,
                            ixia_inventory=args.ixia_inventory,
                            ixia_session_id=args.ixia_session_id,
                            baseline_profile=args.baseline_profile,
                            baseline_nodes=args.baseline_nodes,
                            baseline_timeout=args.baseline_timeout,
                            baseline_topology=args.baseline_topology,
                            stabilize_seconds=args.pre_event_stabilize_seconds,
                        )

                        if not baseline_gate.get("pass"):
                            # Stop traffic before aborting
                            try:
                                stop_pre_event_baseline_traffic(
                                    ixia_inventory=args.ixia_inventory,
                                    ixia_session_id=args.ixia_session_id,
                                    timeout=args.baseline_timeout,
                                )
                            except Exception as exc:
                                print(f"[PRE-EVENT-BASELINE] warning: failed to stop traffic: {exc}")

                            final_report = build_baseline_contamination_failure_report(
                                run_id=run_id,
                                archive_root=archive_root,
                                pre_steps=pre_steps,
                                pre_report=confirm_report,
                                pre_event_gate=pre_event_gate_confirm,
                                baseline_gate=baseline_gate,
                                reason=(
                                    "Pre-event traffic baseline contaminated: "
                                    + ", ".join(baseline_gate.get("cleanliness", {}).get("reasons", []))
                                ),
                            )
                        else:
                            print(
                                "\n[PRE-EVENT-BASELINE] pass: baseline traffic cleanliness gate passed "
                                "— proceeding to event injection"
                            )

                    if baseline_gate.get("pass"):
                        iteration_results = []

                        for iteration in range(1, args.iterations + 1):
                            print("\n" + "=" * 72)
                            print(f"[ITERATION] {iteration}/{args.iterations}")
                            print("=" * 72)

                            stress_result = run_stress_action(
                                stress_mode=args.mode,
                                settle_seconds=args.settle_seconds,
                                inventory=inventory,
                                node=args.node,
                                interface=args.interface,
                                targets_arg=args.targets,
                                parallel=args.parallel,
                                degraded_hold_seconds=args.degraded_hold_seconds,
                                restore_after_degraded_validation=args.restore_after_degraded_validation,
                                degraded_ecmp_sample_count=args.degraded_ecmp_sample_count,
                                degraded_ecmp_sample_interval=args.degraded_ecmp_sample_interval,
                                degraded_sample_start_delay=args.degraded_sample_start_delay,
                                degraded_ecmp_analysis_targets=args.degraded_ecmp_analysis_targets,
                                run_id=run_id,
                                phase_profile=getattr(args, "phase_profile", None) or "hotspot_congestion_qmon_phase",
                                topology=getattr(args, "baseline_topology", None) or "artifacts/topology/topology_full.json",
                                timeout=int(getattr(args, "baseline_timeout", 30) or 30),
                                flap_repeat=args.flap_repeat,
                                flap_down_seconds=args.flap_down_seconds,
                                flap_up_wait_seconds=args.flap_up_wait_seconds,
                            )

                            if stress_result["status"] != "pass":
                                post_steps = []
                                post_report = {
                                    "ready_for_stress": False,
                                    "overall_status": "skipped",
                                    "checks": {},
                                    "failure_reasons": [stress_result["details"]],
                                    "summary": {
                                        "physical_links": {},
                                        "ip_consistency": {},
                                        "bgp": {},
                                    }
                                }
                            else:
                                post_steps = run_pipeline(f"post_iter_{iteration}")
                                post_report = load_json_file(PRECHECK_JSON)

                            iter_report = build_iteration_report(
                                iteration=iteration,
                                stress_result=stress_result,
                                post_steps=post_steps,
                                post_report=post_report,
                            )
                            iteration_results.append(iter_report)

                            iter_dir = archive_root / f"iteration_{iteration:03d}"
                            ensure_dir(iter_dir)
                            iter_snapshot_files = snapshot_artifacts(iter_dir, "post")
                            if iter_snapshot_files:
                                print(f"\n[SNAPSHOT] iteration {iteration} artifacts archived")
                                for item in iter_snapshot_files:
                                    print(f"  - {item}")

                            #with open(iter_dir / "iteration_report.json", "w") as f:
                            #    json.dump(iter_report, f, indent=2)
                            atomic_write_json(iter_dir / "iteration_report.json", iter_report, indent=2)

                            if iter_report["status"] != "pass" and args.stop_on_failure:
                                print(f"\n[STOP] iteration {iteration} failed and --stop-on-failure is set")
                                break

                            if iteration < args.iterations and args.interval_seconds > 0:
                                print(f"\n[WAIT] sleeping {args.interval_seconds} seconds before next iteration")
                                time.sleep(args.interval_seconds)

                        final_report = build_final_campaign_report(
                            run_id=run_id,
                            archive_root=archive_root,
                            pre_steps=pre_steps,
                            pre_report=confirm_report,
                            iteration_results=iteration_results,
                            stop_on_failure=args.stop_on_failure,
                        )
                        final_report["pre_event_gate"] = pre_event_gate_confirm
                        final_report["pre_event_traffic_baseline"] = baseline_gate

                        # Optional cleanup: stop baseline traffic after event phase
                        if args.ixia_inventory and args.baseline_nodes:
                            try:
                                stop_pre_event_baseline_traffic(
                                    ixia_inventory=args.ixia_inventory,
                                    ixia_session_id=args.ixia_session_id,
                                    timeout=args.baseline_timeout,
                                )
                            except Exception as exc:
                                print(f"[PRE-EVENT-BASELINE] warning: failed to stop traffic after iteration: {exc}")

    json_out = archive_root / "stress_orchestrator_report.json"
    txt_out = archive_root / "stress_orchestrator_report.txt"
    final_report["report_files"] = {
    "json_report": str(json_out),
    "text_report": str(txt_out),
    }
    write_json_report(final_report, json_out)
    write_text_report(final_report, txt_out)
    print_summary(final_report, json_out, txt_out)
    print(f"Stress orchestrator report : {json_out}")
    print(f"STRESS_ORCHESTRATOR_REPORT={json_out}")

    sys.exit(0 if final_report["overall_status"] == "pass" else 1)

def initialize_stress_framework():
    """Initialize built-in stress action registry."""


if __name__ == "__main__":
    initialize_stress_framework()
    main()
