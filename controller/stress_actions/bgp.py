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

