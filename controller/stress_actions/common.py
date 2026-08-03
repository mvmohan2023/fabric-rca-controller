"""Shared device execution helpers for FVP stress actions."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional, Tuple

import paramiko


ConnectionInfo = Dict[str, Any]
StepResult = Dict[str, Any]


def first_non_empty(*values):
    """Return the first value that is not empty."""

    for value in values:
        if value not in (None, "", {}):
            return value

    return None


def get_node_connection(node_name, inventory):
    """Resolve device connection details from the inventory."""

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
        raise ValueError(
            f"Management IP/host not found for node '{node_name}' "
            "in inventory"
        )

    if not password:
        raise ValueError(
            f"Password not found in inventory for node '{node_name}'. "
            "Checked node-level, nested auth/connection blocks, "
            "inventory defaults, and FABRIC_CONTROLLER_PASSWORD."
        )

    return {
        "host": host,
        "user": user,
        "password": password,
    }


def run_remote_command(
    host,
    user,
    password,
    remote_cmd,
    step_name,
    timeout=120,
):
    """Execute one command over SSH and return the existing step schema."""

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

        _stdin, stdout, stderr = client.exec_command(
            remote_cmd,
            timeout=timeout,
        )

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


def run_interface_admin_action(
    node,
    interface,
    inventory,
    action,
    step_name,
):
    """Disable or enable one interface using the existing Junos CLI flow."""

    if not node:
        return None, {
            "status": "fail",
            "details": "Missing required argument: --node",
            "target": {
                "node": node,
                "interface": interface,
            },
        }

    if not interface:
        return None, {
            "status": "fail",
            "details": "Missing required argument: --interface",
            "target": {
                "node": node,
                "interface": interface,
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
                "interface": interface,
            },
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
            "details": (
                f"Unsupported interface admin action: {action}"
            ),
            "target": {
                "node": node,
                "interface": interface,
                "host": host,
            },
        }

    step = run_remote_command(
        host,
        user,
        password,
        cmd,
        f"{step_name} {action} {node}:{interface}",
    )

    return conn, step
