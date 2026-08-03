from __future__ import annotations

import time

from controller.stress_actions.common import (
    get_node_connection,
    run_remote_command,
)

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


def infer_bgp_group(peer_ip):
    """Infer the configured BGP group from the peer address family."""

    peer = str(peer_ip or "").strip()

    if not peer:
        raise ValueError("BGP peer IP must be non-empty")

    return "EBGP_IPV6" if ":" in peer else "EBGP"


def run_bgp_neighbor_admin_action(
    node,
    peer_ip,
    inventory,
    action,
    bgp_group=None,
    step_name="bgp_neighbor_admin",
):
    """Deactivate or activate one BGP neighbor."""

    if not node:
        return None, {
            "status": "fail",
            "details": "Missing required BGP target node",
            "target": {
                "node": node,
                "peer_ip": peer_ip,
            },
        }

    if not peer_ip:
        return None, {
            "status": "fail",
            "details": "Missing required BGP peer IP",
            "target": {
                "node": node,
                "peer_ip": peer_ip,
            },
        }

    try:
        conn = get_node_connection(node, inventory)
    except Exception as exc:
        return None, {
            "status": "fail",
            "details": str(exc),
            "target": {
                "node": node,
                "peer_ip": peer_ip,
            },
        }

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    group = str(
        bgp_group or infer_bgp_group(peer_ip)
    ).strip()

    config_path = (
        f"groups global protocols bgp "
        f"group {group} neighbor {peer_ip}"
    )

    if action == "deactivate":
        command = (
            f'cli -c "configure; '
            f'deactivate {config_path}; '
            f'commit and-quit"'
        )
    elif action == "activate":
        command = (
            f'cli -c "configure; '
            f'activate {config_path}; '
            f'commit and-quit"'
        )
    else:
        return conn, {
            "status": "fail",
            "details": (
                f"Unsupported BGP neighbor admin action: {action}"
            ),
            "target": {
                "node": node,
                "peer_ip": peer_ip,
                "bgp_group": group,
                "host": host,
            },
        }

    step = run_remote_command(
        host,
        user,
        password,
        command,
        (
            f"{step_name} {action} "
            f"{node}:{peer_ip} group={group}"
        ),
    )

    return conn, step


def run_bgp_neighbor_shutdown(
    node,
    peer_ip,
    inventory,
    bgp_group=None,
):
    print(
        f"\n[STRESS] mode=bgp_neighbor_shutdown "
        f"node={node} peer_ip={peer_ip}"
    )

    conn, step = run_bgp_neighbor_admin_action(
        node=node,
        peer_ip=peer_ip,
        inventory=inventory,
        action="deactivate",
        bgp_group=bgp_group,
        step_name="bgp_neighbor_shutdown",
    )

    if step.get("status") == "fail" and "returncode" not in step:
        return {
            "stress_mode": "bgp_neighbor_shutdown",
            "status": "fail",
            "details": step["details"],
            "target": step.get(
                "target",
                {
                    "node": node,
                    "peer_ip": peer_ip,
                },
            ),
            "steps": [],
        }

    host = conn["host"] if conn else None
    group = bgp_group or infer_bgp_group(peer_ip)
    success = step.get("returncode") == 0

    return {
        "stress_mode": "bgp_neighbor_shutdown",
        "status": "pass" if success else "fail",
        "details": (
            f"BGP neighbor shutdown completed on "
            f"{node}:{peer_ip}."
            if success
            else
            f"Failed to shutdown BGP neighbor "
            f"{node}:{peer_ip}."
        ),
        "target": {
            "target_type": "bgp_neighbor",
            "node": node,
            "peer_ip": peer_ip,
            "bgp_group": group,
            "host": host,
        },
        "steps": [step],
    }


def run_bgp_neighbor_restore(
    node,
    peer_ip,
    inventory,
    settle_seconds=60,
    bgp_group=None,
):
    print(
        f"\n[STRESS] mode=bgp_neighbor_restore "
        f"node={node} peer_ip={peer_ip}"
    )

    conn, step = run_bgp_neighbor_admin_action(
        node=node,
        peer_ip=peer_ip,
        inventory=inventory,
        action="activate",
        bgp_group=bgp_group,
        step_name="bgp_neighbor_restore",
    )

    if step.get("status") == "fail" and "returncode" not in step:
        return {
            "stress_mode": "bgp_neighbor_restore",
            "status": "fail",
            "details": step["details"],
            "target": step.get(
                "target",
                {
                    "node": node,
                    "peer_ip": peer_ip,
                },
            ),
            "steps": [],
        }

    host = conn["host"] if conn else None
    group = bgp_group or infer_bgp_group(peer_ip)
    success = step.get("returncode") == 0

    if success:
        wait_seconds = max(0, int(settle_seconds or 0))
        print(
            f"  Waiting {wait_seconds} seconds "
            "for BGP neighbor recovery..."
        )
        time.sleep(wait_seconds)

    return {
        "stress_mode": "bgp_neighbor_restore",
        "status": "pass" if success else "fail",
        "details": (
            f"BGP neighbor restore completed on "
            f"{node}:{peer_ip}."
            if success
            else
            f"Failed to restore BGP neighbor "
            f"{node}:{peer_ip}."
        ),
        "target": {
            "target_type": "bgp_neighbor",
            "node": node,
            "peer_ip": peer_ip,
            "bgp_group": group,
            "host": host,
        },
        "steps": [step],
    }


def run_bgp_neighbor_flap(
    node,
    peer_ip,
    inventory,
    down_seconds=10,
    up_wait_seconds=60,
    repeat=1,
    bgp_group=None,
):
    print(
        f"\n[STRESS] mode=bgp_neighbor_flap "
        f"node={node} peer_ip={peer_ip} "
        f"repeat={repeat}"
    )

    steps = []
    host = None
    group = bgp_group or infer_bgp_group(peer_ip)

    repeat = max(1, int(repeat or 1))
    down_seconds = max(0, int(down_seconds or 0))
    up_wait_seconds = max(0, int(up_wait_seconds or 0))

    for index in range(repeat):
        iteration = index + 1

        conn, down_step = run_bgp_neighbor_admin_action(
            node=node,
            peer_ip=peer_ip,
            inventory=inventory,
            action="deactivate",
            bgp_group=group,
            step_name=(
                f"bgp_neighbor_flap iteration={iteration}"
            ),
        )

        if down_step.get("status") == "fail" and (
            "returncode" not in down_step
        ):
            return {
                "stress_mode": "bgp_neighbor_flap",
                "status": "fail",
                "details": down_step["details"],
                "target": down_step.get(
                    "target",
                    {
                        "node": node,
                        "peer_ip": peer_ip,
                    },
                ),
                "iteration": iteration,
                "steps": steps,
            }

        host = conn["host"] if conn else host
        steps.append(down_step)

        if down_step.get("returncode") != 0:
            return {
                "stress_mode": "bgp_neighbor_flap",
                "status": "fail",
                "details": (
                    f"Failed to deactivate BGP neighbor "
                    f"{node}:{peer_ip} on iteration {iteration}"
                ),
                "target": {
                    "target_type": "bgp_neighbor",
                    "node": node,
                    "peer_ip": peer_ip,
                    "bgp_group": group,
                    "host": host,
                },
                "iteration": iteration,
                "steps": steps,
            }

        print(
            f"  Iteration {iteration}/{repeat}: "
            f"waiting {down_seconds}s while neighbor is down"
        )
        time.sleep(down_seconds)

        conn, up_step = run_bgp_neighbor_admin_action(
            node=node,
            peer_ip=peer_ip,
            inventory=inventory,
            action="activate",
            bgp_group=group,
            step_name=(
                f"bgp_neighbor_flap iteration={iteration}"
            ),
        )

        if up_step.get("status") == "fail" and (
            "returncode" not in up_step
        ):
            return {
                "stress_mode": "bgp_neighbor_flap",
                "status": "fail",
                "details": up_step["details"],
                "target": up_step.get(
                    "target",
                    {
                        "node": node,
                        "peer_ip": peer_ip,
                    },
                ),
                "iteration": iteration,
                "steps": steps,
            }

        host = conn["host"] if conn else host
        steps.append(up_step)

        if up_step.get("returncode") != 0:
            return {
                "stress_mode": "bgp_neighbor_flap",
                "status": "fail",
                "details": (
                    f"Failed to activate BGP neighbor "
                    f"{node}:{peer_ip} on iteration {iteration}"
                ),
                "target": {
                    "target_type": "bgp_neighbor",
                    "node": node,
                    "peer_ip": peer_ip,
                    "bgp_group": group,
                    "host": host,
                },
                "iteration": iteration,
                "steps": steps,
            }

        print(
            f"  Iteration {iteration}/{repeat}: "
            f"waiting {up_wait_seconds}s for recovery"
        )
        time.sleep(up_wait_seconds)

    return {
        "stress_mode": "bgp_neighbor_flap",
        "status": "pass",
        "details": (
            f"BGP neighbor flap completed on "
            f"{node}:{peer_ip}; repeat={repeat}, "
            f"down_seconds={down_seconds}, "
            f"up_wait_seconds={up_wait_seconds}."
        ),
        "target": {
            "target_type": "bgp_neighbor",
            "node": node,
            "peer_ip": peer_ip,
            "bgp_group": group,
            "host": host,
        },
        "repeat": repeat,
        "down_seconds": down_seconds,
        "up_wait_seconds": up_wait_seconds,
        "steps": steps,
    }
