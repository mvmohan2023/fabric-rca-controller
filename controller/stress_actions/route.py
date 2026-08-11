"""Route-churn stress actions for the Fabric Validation Platform."""

from __future__ import annotations

import ipaddress
import time
from typing import Any, Dict, List, Optional

from controller.stress_actions.common import (
    get_node_connection,
    run_remote_command,
)


_ALLOWED_IPV4_EXPORT_NETWORKS = (
    ipaddress.ip_network("1.0.0.0/8"),
    ipaddress.ip_network("2.0.0.0/8"),
)


def _validate_route_churn_prefix(prefix: str) -> ipaddress.IPv4Interface:
    """Validate one safe IPv4 connected-prefix churn target."""

    value = str(prefix or "").strip()

    if not value:
        raise ValueError(
            "route_churn_prefix must be provided explicitly"
        )

    try:
        interface = ipaddress.ip_interface(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid route churn prefix: {value}"
        ) from exc

    if interface.version != 4:
        raise ValueError(
            "Route churn v1 supports IPv4 prefixes only"
        )

    if not any(
        interface.ip in network
        for network in _ALLOWED_IPV4_EXPORT_NETWORKS
    ):
        raise ValueError(
            "Route churn prefix must fall inside the current "
            "BGP_DIRECT export ranges 1.0.0.0/8 or 2.0.0.0/8"
        )

    return interface


def _run_cli(
    *,
    host: str,
    user: str,
    password: str,
    cli_command: str,
    step_name: str,
    timeout: int,
) -> Dict[str, Any]:
    """Execute one Junos operational/configuration command."""

    remote_cmd = f'cli -c "{cli_command}"'

    result = run_remote_command(
        host,
        user,
        password,
        remote_cmd,
        step_name,
        timeout=timeout,
    )

    # Junos CLI may return shell rc=0 even when a configuration
    # commit/check fails. Normalize known Junos configuration failures.
    combined_output = (
        str(result.get("stdout") or "")
        + "\n"
        + str(result.get("stderr") or "")
    ).lower()

    junos_failure_markers = (
        "configuration check-out failed",
        "commit failed",
        "commit check failed",
        "syntax error",
    )

    if (
        cli_command.strip().startswith("configure;")
        and any(
            marker in combined_output
            for marker in junos_failure_markers
        )
    ):
        result["returncode"] = 1
        result["status"] = "fail"
        result["junos_cli_error"] = True

    return result


def _route_present(
    *,
    host: str,
    user: str,
    password: str,
    network_prefix: str,
    step_name: str,
    timeout: int,
) -> tuple[bool, Dict[str, Any]]:
    """Check whether the connected route exists in the local RIB."""

    step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command=(
            f"show route {network_prefix} exact"
        ),
        step_name=step_name,
        timeout=timeout,
    )

    stdout = str(step.get("stdout") or "")

    present = (
        step.get("returncode") == 0
        and network_prefix in stdout
    )

    return present, step


def _route_advertised(
    *,
    host: str,
    user: str,
    password: str,
    peer_ip: str,
    network_prefix: str,
    step_name: str,
    timeout: int,
) -> tuple[bool, Dict[str, Any]]:
    """Check whether the prefix is advertised to one BGP peer."""

    step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command=(
            "show route advertising-protocol bgp "
            f"{peer_ip} {network_prefix} exact"
        ),
        step_name=step_name,
        timeout=timeout,
    )

    stdout = str(step.get("stdout") or "")

    advertised = (
        step.get("returncode") == 0
        and network_prefix in stdout
    )

    return advertised, step


def run_route_churn(
    *,
    node: str,
    inventory: Dict[str, Any],
    prefix: str,
    unit: int,
    repeat: int = 1,
    hold_seconds: int = 5,
    recovery_seconds: int = 5,
    peer_ip: Optional[str] = None,
    verify_bgp_advertisement: bool = True,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Advertise/withdraw one temporary connected prefix repeatedly.

    The temporary route is created as an address on lo0.<unit>.
    It is initially deactivated, activated for advertisement, then
    deactivated for withdrawal. The temporary unit is deleted in a
    finally block regardless of scenario outcome.
    """

    print(
        f"\n[STRESS] mode=route_churn "
        f"node={node} prefix={prefix} unit={unit} "
        f"repeat={repeat}"
    )

    steps: List[Dict[str, Any]] = []
    iterations: List[Dict[str, Any]] = []

    if not node:
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": "Missing required route churn node.",
            "target": {
                "node": node,
                "prefix": prefix,
                "unit": unit,
            },
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    try:
        address = _validate_route_churn_prefix(
            prefix
        )
    except ValueError as exc:
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": str(exc),
            "target": {
                "node": node,
                "prefix": prefix,
                "unit": unit,
            },
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    try:
        unit = int(unit)
    except (TypeError, ValueError):
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": (
                f"Invalid route churn loopback unit: {unit}"
            ),
            "target": {
                "node": node,
                "prefix": prefix,
                "unit": unit,
            },
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    if unit < 0:
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": (
                "route_churn_unit must be greater than or equal to zero"
            ),
            "target": {
                "node": node,
                "prefix": prefix,
                "unit": unit,
            },
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    repeat = max(1, int(repeat or 1))
    hold_seconds = max(
        0,
        int(hold_seconds or 0),
    )
    recovery_seconds = max(
        0,
        int(recovery_seconds or 0),
    )
    timeout = max(
        1,
        int(timeout or 120),
    )

    try:
        conn = get_node_connection(
            node,
            inventory,
        )
    except Exception as exc:
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": str(exc),
            "target": {
                "node": node,
                "prefix": str(address),
                "unit": unit,
            },
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    network_prefix = str(
        address.network
    )

    target = {
        "target_type": "route_prefix",
        "node": node,
        "host": host,
        "prefix": str(address),
        "network_prefix": network_prefix,
        "unit": unit,
        "interface": f"lo0.{unit}",
        "peer_ip": peer_ip,
    }

    cleanup_ok = False
    overall_status = "pass"
    failure_detail = ""

    # --------------------------------------------------------------
    # PRE-FLIGHT
    # --------------------------------------------------------------

    collision_step = _run_cli(
        host=host,
        user=user,
        password=password,
        cli_command=(
            "show configuration interfaces lo0 "
            f"unit {unit} family inet address {address} "
            "| display set"
        ),
        step_name=(
            f"route_churn preflight unit={unit}"
        ),
        timeout=timeout,
    )
    steps.append(collision_step)

    existing_config = str(
        collision_step.get("stdout") or ""
    ).strip()

    if existing_config:
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": (
                f"Refusing route churn because lo0.{unit} "
                "already has configuration."
            ),
            "target": target,
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    existing_route, route_pre_step = (
        _route_present(
            host=host,
            user=user,
            password=password,
            network_prefix=network_prefix,
            step_name=(
                "route_churn preflight route collision"
            ),
            timeout=timeout,
        )
    )
    steps.append(route_pre_step)

    if existing_route:
        return {
            "stress_mode": "route_churn",
            "status": "fail",
            "details": (
                f"Refusing route churn because "
                f"{network_prefix} already exists."
            ),
            "target": target,
            "steps": steps,
            "iterations": iterations,
            "cleanup_ok": False,
        }

    try:
        # ----------------------------------------------------------
        # CREATE TEMPORARY CONFIGURATION IN DEACTIVATED STATE
        # ----------------------------------------------------------

        prepare_command = (
            "configure; "
            f"set interfaces lo0 unit {unit} "
            f"family inet address {address}; "
            f"deactivate interfaces lo0 unit {unit} "
            f"family inet address {address}; "
            "commit and-quit"
        )

        prepare_step = _run_cli(
            host=host,
            user=user,
            password=password,
            cli_command=prepare_command,
            step_name="route_churn prepare",
            timeout=timeout,
        )
        steps.append(prepare_step)

        if prepare_step.get("returncode") != 0:
            overall_status = "fail"
            failure_detail = (
                f"Refusing route churn because {address} "
                f"is already configured on lo0.{unit}."
            )
            return {
                "stress_mode": "route_churn",
                "status": overall_status,
                "details": failure_detail,
                "target": target,
                "steps": steps,
                "iterations": iterations,
                "cleanup_ok": cleanup_ok,
            }

        # ----------------------------------------------------------
        # CHURN ITERATIONS
        # ----------------------------------------------------------

        for index in range(repeat):
            iteration = index + 1
            iteration_result: Dict[str, Any] = {
                "iteration": iteration,
                "advertised": False,
                "withdrawn": False,
                "bgp_advertised": None,
                "steps": [],
            }

            # ACTIVATE -> direct route appears.
            activate_step = _run_cli(
                host=host,
                user=user,
                password=password,
                cli_command=(
                    "configure; "
                    f"activate interfaces lo0 unit {unit} "
                    f"family inet address {address}; "
                    "commit and-quit"
                ),
                step_name=(
                    f"route_churn activate "
                    f"iteration={iteration}"
                ),
                timeout=timeout,
            )
            steps.append(activate_step)
            iteration_result["steps"].append(
                activate_step
            )

            if activate_step.get("returncode") != 0:
                overall_status = "fail"
                failure_detail = (
                    f"Failed to activate {network_prefix} "
                    f"on iteration {iteration}."
                )
                iterations.append(
                    iteration_result
                )
                break

            route_up, route_up_step = (
                _route_present(
                    host=host,
                    user=user,
                    password=password,
                    network_prefix=network_prefix,
                    step_name=(
                        "route_churn verify local advertise "
                        f"iteration={iteration}"
                    ),
                    timeout=timeout,
                )
            )
            steps.append(route_up_step)
            iteration_result["steps"].append(
                route_up_step
            )
            iteration_result["advertised"] = (
                route_up
            )

            if not route_up:
                overall_status = "fail"
                failure_detail = (
                    f"Connected route {network_prefix} "
                    "did not appear after activation."
                )
                iterations.append(
                    iteration_result
                )
                break

            # Optional BGP advertisement verification.
            if (
                peer_ip
                and verify_bgp_advertisement
            ):
                bgp_up, bgp_up_step = (
                    _route_advertised(
                        host=host,
                        user=user,
                        password=password,
                        peer_ip=peer_ip,
                        network_prefix=network_prefix,
                        step_name=(
                            "route_churn verify BGP advertise "
                            f"iteration={iteration}"
                        ),
                        timeout=timeout,
                    )
                )
                steps.append(bgp_up_step)
                iteration_result[
                    "steps"
                ].append(
                    bgp_up_step
                )
                iteration_result[
                    "bgp_advertised"
                ] = bgp_up

                if not bgp_up:
                    overall_status = "fail"
                    failure_detail = (
                        f"Route {network_prefix} was not "
                        f"advertised to BGP peer {peer_ip}."
                    )
                    iterations.append(
                        iteration_result
                    )
                    break

            if hold_seconds:
                print(
                    f"  Iteration {iteration}/{repeat}: "
                    f"holding advertised route for "
                    f"{hold_seconds}s"
                )
                time.sleep(
                    hold_seconds
                )

            # DEACTIVATE -> route withdrawn.
            deactivate_step = _run_cli(
                host=host,
                user=user,
                password=password,
                cli_command=(
                    "configure; "
                    f"deactivate interfaces lo0 unit {unit} "
                    f"family inet address {address}; "
                    "commit and-quit"
                ),
                step_name=(
                    f"route_churn deactivate "
                    f"iteration={iteration}"
                ),
                timeout=timeout,
            )
            steps.append(deactivate_step)
            iteration_result["steps"].append(
                deactivate_step
            )

            if deactivate_step.get(
                "returncode"
            ) != 0:
                overall_status = "fail"
                failure_detail = (
                    f"Failed to deactivate {network_prefix} "
                    f"on iteration {iteration}."
                )
                iterations.append(
                    iteration_result
                )
                break

            # Allow RIB/BGP withdrawal to settle before verification.
            if recovery_seconds:
                time.sleep(
                    recovery_seconds
                )

            route_down, route_down_step = (
                _route_present(
                    host=host,
                    user=user,
                    password=password,
                    network_prefix=network_prefix,
                    step_name=(
                        "route_churn verify withdrawal "
                        f"iteration={iteration}"
                    ),
                    timeout=timeout,
                )
            )
            steps.append(route_down_step)
            iteration_result["steps"].append(
                route_down_step
            )

            iteration_result["withdrawn"] = (
                not route_down
            )

            if route_down:
                overall_status = "fail"
                failure_detail = (
                    f"Connected route {network_prefix} "
                    "remained present after deactivation."
                )
                iterations.append(
                    iteration_result
                )
                break

            iterations.append(
                iteration_result
            )

    finally:
        # ----------------------------------------------------------
        # GUARANTEED CLEANUP
        # ----------------------------------------------------------

        cleanup_step = _run_cli(
            host=host,
            user=user,
            password=password,
            cli_command=(
                "configure; "
                f"delete interfaces lo0 unit {unit} "
                f"family inet address {address}; "
                "commit and-quit"
            ),
            step_name="route_churn cleanup",
            timeout=timeout,
        )
        steps.append(cleanup_step)

        cleanup_ok = (
            cleanup_step.get("returncode")
            == 0
        )

        if not cleanup_ok:
            overall_status = "fail"

            if failure_detail:
                failure_detail += (
                    " Cleanup also failed."
                )
            else:
                failure_detail = (
                    "Temporary route churn configuration "
                    "cleanup failed."
                )

    completed_iterations = sum(
        1
        for item in iterations
        if item.get("advertised")
        and item.get("withdrawn")
        and (
            item.get("bgp_advertised")
            in (True, None)
        )
    )

    if (
        overall_status == "pass"
        and completed_iterations != repeat
    ):
        overall_status = "fail"
        failure_detail = (
            f"Only {completed_iterations}/{repeat} "
            "route churn iterations completed."
        )

    if overall_status == "pass":
        details = (
            f"Route churn completed successfully on {node}: "
            f"{network_prefix}, iterations={repeat}."
        )
    else:
        details = (
            failure_detail
            or "Route churn failed."
        )

    return {
        "stress_mode": "route_churn",
        "status": overall_status,
        "details": details,
        "target": target,
        "iterations_requested": repeat,
        "iterations_completed": completed_iterations,
        "advertise_count": sum(
            1
            for item in iterations
            if item.get("advertised")
        ),
        "withdraw_count": sum(
            1
            for item in iterations
            if item.get("withdrawn")
        ),
        "cleanup_ok": cleanup_ok,
        "steps": steps,
        "iterations": iterations,
    }
