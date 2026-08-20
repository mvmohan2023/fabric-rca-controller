"""Node reboot stress action for Fabric Validation Platform."""

from __future__ import annotations

import socket
import time
from typing import Any, Dict

from controller.stress_actions.common import (
    get_node_connection,
    run_remote_command,
)


def _run_cli(
    *,
    host: str,
    user: str,
    password: str,
    cli_command: str,
    step_name: str,
    timeout: int,
) -> Dict[str, Any]:
    return run_remote_command(
        host,
        user,
        password,
        f'cli -c "{cli_command}"',
        step_name,
        timeout=timeout,
    )


def _read_uptime(
    *,
    host: str,
    user: str,
    password: str,
    timeout: int,
) -> tuple[str, Dict[str, Any]]:
    step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command="show system uptime",
        step_name="node_reboot read uptime",
        timeout=timeout,
    )

    return str(step.get("stdout") or ""), step


def _ssh_port_open(
    host: str,
    port: int = 22,
    timeout: int = 5,
) -> bool:
    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout,
        ):
            return True
    except OSError:
        return False


def _wait_for_ssh_state(
    *,
    host: str,
    expected_up: bool,
    timeout_seconds: int,
    interval_seconds: int = 5,
) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        current = _ssh_port_open(host)

        if current is expected_up:
            return True

        time.sleep(interval_seconds)

    return False


def run_node_reboot(
    *,
    node: str,
    inventory: Dict[str, Any],
    down_timeout_seconds: int = 120,
    recovery_timeout_seconds: int = 600,
    settle_seconds: int = 30,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Reboot one node and verify SSH/uptime recovery."""

    steps = []

    conn = get_node_connection(
        node,
        inventory,
    )

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    target = {
        "target_type": "node",
        "node": node,
    }

    baseline_uptime, baseline_step = _read_uptime(
        host=host,
        user=user,
        password=password,
        timeout=timeout,
    )

    steps.append(baseline_step)

    if baseline_step.get("returncode") != 0:
        return {
            "stress_mode": "node_reboot",
            "status": "blocked",
            "details": "Unable to read baseline uptime.",
            "target": target,
            "event_injected": False,
            "steps": steps,
        }

    reboot_step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command="request system reboot",
        step_name="node_reboot request reboot",
        timeout=timeout,
    )

    steps.append(reboot_step)

    # Reboot commands may terminate the SSH session abruptly.
    # Do not require a clean CLI return as the sole proof of event.
    event_injected = True

    went_down = _wait_for_ssh_state(
        host=host,
        expected_up=False,
        timeout_seconds=down_timeout_seconds,
    )

    if not went_down:
        return {
            "stress_mode": "node_reboot",
            "status": "fail",
            "details": (
                "Node did not become unreachable "
                "within the reboot-down timeout."
            ),
            "target": target,
            "event_injected": event_injected,
            "baseline_uptime": baseline_uptime,
            "steps": steps,
        }

    recovered = _wait_for_ssh_state(
        host=host,
        expected_up=True,
        timeout_seconds=recovery_timeout_seconds,
    )

    if not recovered:
        return {
            "stress_mode": "node_reboot",
            "status": "fail",
            "details": (
                "Node did not recover SSH within "
                "the configured recovery timeout."
            ),
            "target": target,
            "event_injected": event_injected,
            "baseline_uptime": baseline_uptime,
            "steps": steps,
        }

    if settle_seconds:
        time.sleep(settle_seconds)

    recovery_uptime, recovery_step = _read_uptime(
        host=host,
        user=user,
        password=password,
        timeout=timeout,
    )

    steps.append(recovery_step)

    if recovery_step.get("returncode") != 0:
        return {
            "stress_mode": "node_reboot",
            "status": "fail",
            "details": (
                "Node recovered SSH but uptime "
                "verification failed."
            ),
            "target": target,
            "event_injected": event_injected,
            "baseline_uptime": baseline_uptime,
            "steps": steps,
        }

    return {
        "stress_mode": "node_reboot",
        "status": "pass",
        "details": (
            "Node rebooted and recovered successfully."
        ),
        "target": target,
        "event_injected": event_injected,
        "ssh_down_observed": True,
        "ssh_recovery_observed": True,
        "baseline_uptime": baseline_uptime,
        "recovery_uptime": recovery_uptime,
        "steps": steps,
    }
