"""BFD stress actions for the Fabric Validation Platform."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

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
    remote_cmd = f'cli -c "{cli_command}"'

    return run_remote_command(
        host,
        user,
        password,
        remote_cmd,
        step_name,
        timeout=timeout,
    )


def _bfd_session_state(
    *,
    host: str,
    user: str,
    password: str,
    peer_ip: str,
    timeout: int,
) -> tuple[str, Dict[str, Any]]:
    """Return normalized BFD state for one peer."""

    step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command=(
            f"show bfd session address {peer_ip}"
        ),
        step_name=(
            f"bfd verify peer={peer_ip}"
        ),
        timeout=timeout,
    )

    stdout = str(
        step.get("stdout") or ""
    )

    state = "unknown"

    for line in stdout.splitlines():
        if peer_ip not in line:
            continue

        parts = line.split()

        if len(parts) >= 2:
            candidate = parts[1].strip().lower()

            if candidate in {
                "up",
                "down",
                "admindown",
            }:
                state = candidate

        break

    return state, step


def _bgp_peer_state(
    *,
    host: str,
    user: str,
    password: str,
    peer_ip: str,
    timeout: int,
) -> tuple[str, Dict[str, Any]]:
    """Return normalized BGP state for one peer."""

    step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command=(
            f"show bgp neighbor {peer_ip}"
        ),
        step_name=(
            f"bfd verify bgp peer={peer_ip}"
        ),
        timeout=timeout,
    )

    stdout = str(
        step.get("stdout") or ""
    )

    match = re.search(
        r"\bState:\s*(\S+)",
        stdout,
        re.IGNORECASE,
    )

    state = (
        match.group(1).lower()
        if match
        else "unknown"
    )

    return state, step


def run_bfd_session_flap(
    *,
    node: str,
    inventory: Dict[str, Any],
    peer_ip: str,
    hold_seconds: int = 5,
    recovery_seconds: int = 10,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Validate one BFD-session flap lifecycle.

    V1 intentionally refuses destructive injection until a healthy
    BFD baseline and a safe per-neighbor mutation path are confirmed.
    """

    steps = []

    connection = get_node_connection(
        inventory,
        node,
    )

    host = connection["host"]
    user = connection["user"]
    password = connection["password"]

    bfd_state, bfd_step = (
        _bfd_session_state(
            host=host,
            user=user,
            password=password,
            peer_ip=peer_ip,
            timeout=timeout,
        )
    )

    steps.append(bfd_step)

    bgp_state, bgp_step = (
        _bgp_peer_state(
            host=host,
            user=user,
            password=password,
            peer_ip=peer_ip,
            timeout=timeout,
        )
    )

    steps.append(bgp_step)

    if bfd_state != "up":
        return {
            "stress_mode":
                "bfd_session_flap",
            "status":
                "blocked",
            "details": (
                "BFD session baseline is not Up; "
                "stress injection was not attempted."
            ),
            "target": {
                "node": node,
                "peer_ip": peer_ip,
            },
            "baseline_bfd_state":
                bfd_state,
            "baseline_bgp_state":
                bgp_state,
            "event_injected":
                False,
            "steps":
                steps,
        }

    if bgp_state != "established":
        return {
            "stress_mode":
                "bfd_session_flap",
            "status":
                "blocked",
            "details": (
                "BGP peer baseline is not Established; "
                "stress injection was not attempted."
            ),
            "target": {
                "node": node,
                "peer_ip": peer_ip,
            },
            "baseline_bfd_state":
                bfd_state,
            "baseline_bgp_state":
                bgp_state,
            "event_injected":
                False,
            "steps":
                steps,
        }

    return {
        "stress_mode":
            "bfd_session_flap",
        "status":
            "blocked",
        "details": (
            "Healthy BFD baseline detected, but "
            "per-neighbor BFD disruption is not yet enabled "
            "until the exact Junos mutation is validated."
        ),
        "target": {
            "node": node,
            "peer_ip": peer_ip,
        },
        "baseline_bfd_state":
            bfd_state,
        "baseline_bgp_state":
            bgp_state,
        "event_injected":
            False,
        "hold_seconds":
            hold_seconds,
        "recovery_seconds":
            recovery_seconds,
        "steps":
            steps,
    }
