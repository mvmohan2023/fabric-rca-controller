
from controller.stress_actions.common import (
    run_interface_admin_action,
    run_remote_command,
    get_node_connection,
)

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
