"""SNMP polling health collection for FVP telemetry validation."""

from __future__ import annotations

import os
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List

from controller.telemetry_monitor import build_inventory_indexes, resolve_inventory_record


DEFAULT_SNMP_COMMUNITY = os.environ.get("SNMP_COMMUNITY", "")
DEFAULT_SNMP_OIDS = {
    "sys_name": "1.3.6.1.2.1.1.5.0",
    "sys_uptime": "1.3.6.1.2.1.1.3.0",
    "sys_descr": "1.3.6.1.2.1.1.1.0",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_snmp_command(
    telemetry_server: str,
    target: str,
    timeout: int,
    ssh_user: str,
    community: str = DEFAULT_SNMP_COMMUNITY,
    oids: Dict[str, str] | None = None,
) -> str:
    """Build an SNMPv2c command executed from the telemetry server."""
    oid_map = dict(oids or DEFAULT_SNMP_OIDS)
    if not community:
        raise ValueError("SNMP community is not configured; set SNMP_COMMUNITY")
    args = [
        "snmpget",
        "-v2c",
        "-c",
        community,
        "-t",
        str(max(1, int(timeout))),
        "-r",
        "1",
        "-On",
        "-Oe",
        target,
        *oid_map.values(),
    ]
    inner_cmd = " ".join(shlex.quote(str(arg)) for arg in args)
    return (
        f"ssh -o StrictHostKeyChecking=no "
        f"-o ConnectTimeout={max(1, int(timeout))} "
        f"{shlex.quote(ssh_user)}@{shlex.quote(telemetry_server)} "
        f"{shlex.quote(inner_cmd)}"
    )


def run_snmpget(
    telemetry_server: str,
    target: str,
    timeout: int,
    ssh_user: str,
    community: str = DEFAULT_SNMP_COMMUNITY,
    oids: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Run one deterministic SNMPv2c health query."""
    oid_map = dict(oids or DEFAULT_SNMP_OIDS)
    cmd = build_snmp_command(
        telemetry_server=telemetry_server,
        target=target,
        timeout=timeout,
        ssh_user=ssh_user,
        community=community,
        oids=oid_map,
    )
    started_at = utc_now_iso()
    proc = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=max(int(timeout) * 2 + 15, 30),
    )
    completed_at = utc_now_iso()
    stdout_text = (proc.stdout or "").strip()
    stderr_text = (proc.stderr or "").strip()
    lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
    values: Dict[str, str] = {}
    for name, line in zip(oid_map.keys(), lines):
        values[name] = line.split("=", 1)[1].strip() if "=" in line else line

    complete = proc.returncode == 0 and len(values) == len(oid_map)
    return {
        "status": "pass" if complete else "fail",
        "target": target,
        "started_at": started_at,
        "completed_at": completed_at,
        "returncode": proc.returncode,
        "oids_requested": list(oid_map.keys()),
        "oids_received": len(values),
        "values": values,
        "stderr": stderr_text,
    }


def _collect_snmp_node(
    *,
    node: str,
    telemetry_server: str,
    ssh_user: str,
    inventory_indexes: Dict[str, Any],
    timeout: int,
    community: str,
) -> Dict[str, Any]:
    try:
        record = resolve_inventory_record(node=node, inventory_indexes=inventory_indexes)
        target = str(record.get("mgt_ip") or "").strip()
        if not target:
            raise ValueError(f"inventory record for {node} has no management IP")
        result = run_snmpget(
            telemetry_server=telemetry_server,
            target=target,
            timeout=timeout,
            ssh_user=ssh_user,
            community=community,
        )
        return {
            "node": node,
            "device": record.get("device"),
            "target": target,
            **result,
        }
    except Exception as exc:
        return {
            "node": node,
            "status": "fail",
            "error": str(exc),
            "oids_requested": list(DEFAULT_SNMP_OIDS.keys()),
            "oids_received": 0,
        }


def collect_snmp_health(
    *,
    telemetry_server: str,
    ssh_user: str,
    nodes: List[str],
    inventory: Dict[str, Any],
    timeout: int,
    run_id: str | None = None,
    community: str = DEFAULT_SNMP_COMMUNITY,
) -> Dict[str, Any]:
    """Collect and aggregate basic SNMP agent health across selected nodes."""
    report: Dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "source_type": "snmp_v2c",
        "run_id": run_id,
        "telemetry_server": telemetry_server,
        "status": "fail",
        "nodes": [],
        "nodes_total": len(nodes),
        "nodes_passed": 0,
        "nodes_failed": 0,
        "oids_requested": len(DEFAULT_SNMP_OIDS) * len(nodes),
        "oids_received": 0,
    }
    if not nodes:
        report["error"] = "no nodes supplied for SNMP validation"
        return report

    indexes = build_inventory_indexes(inventory)
    with ThreadPoolExecutor(max_workers=min(6, len(nodes))) as pool:
        futures = {
            pool.submit(
                _collect_snmp_node,
                node=node,
                telemetry_server=telemetry_server,
                ssh_user=ssh_user,
                inventory_indexes=indexes,
                timeout=timeout,
                community=community,
            ): node
            for node in nodes
        }
        for future in as_completed(futures):
            result = future.result()
            report["nodes"].append(result)
            report["oids_received"] += int(result.get("oids_received") or 0)
            if result.get("status") == "pass":
                report["nodes_passed"] += 1
            else:
                report["nodes_failed"] += 1

    report["nodes"].sort(key=lambda item: str(item.get("node") or ""))
    report["status"] = (
        "pass"
        if report["nodes_passed"] == report["nodes_total"]
        and report["nodes_failed"] == 0
        and report["oids_received"] == report["oids_requested"]
        else "fail"
    )
    return report
