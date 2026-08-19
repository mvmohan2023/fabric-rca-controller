"""Process-restart stress actions for Fabric Validation Platform."""

from __future__ import annotations

import re
import time
from typing import Any, Dict

from controller.stress_actions.common import (
    get_node_connection,
    run_remote_command,
)


_ALLOWED_RESTART_PROCESSES = {
    "routing",
    "management",
    "snmp",
}


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


def _process_running(
    *,
    host: str,
    user: str,
    password: str,
    process: str,
    timeout: int,
) -> tuple[bool, Dict[str, Any]]:
    """Check whether the expected daemon is currently running."""

    unix_process = {
        "routing": "rpd",
        "management": "mgd",
        "snmp": "snmpd",
    }[process]

    step = run_remote_command(
        host,
        user,
        password,
        (
            "ps -ax -o pid=,comm= | "
            f"grep -E '[ /]{unix_process}$' | "
            "grep -v grep"
        ),
        f"process_restart verify {unix_process}",
        timeout=timeout,
    )

    stdout = str(step.get("stdout") or "")

    running = (
        step.get("returncode") == 0
        and unix_process in stdout
    )

    return running, step


def _extract_pid(step: Dict[str, Any]) -> int | None:
    stdout = str(step.get("stdout") or "")

    match = re.search(
        r"^\s*(\d+)\s+",
        stdout,
        re.MULTILINE,
    )

    if not match:
        return None

    return int(match.group(1))


def run_process_restart(
    *,
    node: str,
    inventory: Dict[str, Any],
    process: str,
    recovery_seconds: int = 30,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Restart one allowlisted Junos process and verify recovery."""

    process = str(process or "").strip().lower()

    steps = []

    if process not in _ALLOWED_RESTART_PROCESSES:
        return {
            "stress_mode": "process_restart",
            "status": "fail",
            "details": (
                f"Process '{process}' is not in the "
                "approved restart allowlist"
            ),
            "event_injected": False,
            "steps": steps,
        }

    conn = get_node_connection(
        node,
        inventory,
    )

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    target = {
        "target_type": "process",
        "node": node,
        "process": process,
    }

    baseline_running, baseline_step = (
        _process_running(
            host=host,
            user=user,
            password=password,
            process=process,
            timeout=timeout,
        )
    )

    steps.append(baseline_step)

    if not baseline_running:
        return {
            "stress_mode": "process_restart",
            "status": "blocked",
            "details": (
                f"Process '{process}' is not running "
                "at baseline; restart was not attempted"
            ),
            "target": target,
            "event_injected": False,
            "steps": steps,
        }

    baseline_pid = _extract_pid(
        baseline_step
    )

    restart_step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command=(
            f"restart {process}"
        ),
        step_name=(
            f"process_restart restart {process}"
        ),
        timeout=timeout,
    )

    steps.append(restart_step)

    if restart_step.get("returncode") != 0:
        return {
            "stress_mode": "process_restart",
            "status": "fail",
            "details": (
                f"Failed to restart process '{process}'"
            ),
            "target": target,
            "event_injected": True,
            "baseline_pid": baseline_pid,
            "steps": steps,
        }

    if recovery_seconds:
        time.sleep(
            recovery_seconds
        )

    recovered_running, recovery_step = (
        _process_running(
            host=host,
            user=user,
            password=password,
            process=process,
            timeout=timeout,
        )
    )

    steps.append(recovery_step)

    recovery_pid = _extract_pid(
        recovery_step
    )

    if not recovered_running:
        return {
            "stress_mode": "process_restart",
            "status": "fail",
            "details": (
                f"Process '{process}' did not recover "
                "after restart"
            ),
            "target": target,
            "event_injected": True,
            "baseline_pid": baseline_pid,
            "recovery_pid": recovery_pid,
            "steps": steps,
        }

    pid_changed = (
        baseline_pid is not None
        and recovery_pid is not None
        and baseline_pid != recovery_pid
    )

    return {
        "stress_mode": "process_restart",
        "status": "pass",
        "details": (
            f"Process '{process}' restarted and recovered "
            "successfully"
        ),
        "target": target,
        "event_injected": True,
        "baseline_pid": baseline_pid,
        "recovery_pid": recovery_pid,
        "pid_changed": pid_changed,
        "steps": steps,
    }
