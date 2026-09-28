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

# JUNIPER-MIB jnxOperatingTable columns. Numeric OIDs intentionally avoid
# runtime dependency on local MIB loading on the telemetry server.
JNX_OPERATING_BASE_OID = "1.3.6.1.4.1.2636.3.1.13.1"
JNX_OPERATING_COLUMNS = {
    "temperature_c": {
        "column": 30,
        "unit": "celsius",
    },
    "cpu_pct": {
        "column": 8,
        "unit": "percent",
    },
    "memory_mb": {
        "column": 15,
        "unit": "megabytes",
    },
    "cpu_1min_pct": {
        "column": 23,
        "unit": "percent",
    },
    "cpu_5min_pct": {
        "column": 24,
        "unit": "percent",
    },
    "cpu_15min_pct": {
        "column": 25,
        "unit": "percent",
    },
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




def build_snmpwalk_command(
    telemetry_server: str,
    target: str,
    oid: str,
    timeout: int,
    ssh_user: str,
    community: str = DEFAULT_SNMP_COMMUNITY,
) -> str:
    """Build a numeric-OID SNMP walk executed from the telemetry server."""
    if not community:
        raise ValueError("SNMP community is not configured; set SNMP_COMMUNITY")
    args = [
        "snmpwalk",
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
        oid,
    ]
    inner_cmd = " ".join(shlex.quote(str(arg)) for arg in args)
    return (
        f"ssh -o StrictHostKeyChecking=no "
        f"-o ConnectTimeout={max(1, int(timeout))} "
        f"{shlex.quote(ssh_user)}@{shlex.quote(telemetry_server)} "
        f"{shlex.quote(inner_cmd)}"
    )


def _parse_numeric_walk(stdout_text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw_line in (stdout_text or "").splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        oid_text, value_text = [part.strip() for part in line.split("=", 1)]
        typed_value = value_text
        value: Any = value_text
        if ":" in value_text:
            _, raw_value = value_text.split(":", 1)
            raw_value = raw_value.strip()
            try:
                value = int(raw_value)
            except ValueError:
                value = raw_value
        rows.append(
            {
                "oid": oid_text.lstrip("."),
                "typed_value": typed_value,
                "value": value,
            }
        )
    return rows


def collect_juniper_operating_health(
    *,
    telemetry_server: str,
    target: str,
    timeout: int,
    ssh_user: str,
    community: str = DEFAULT_SNMP_COMMUNITY,
) -> Dict[str, Any]:
    """Collect raw Juniper jnxOperatingTable health columns.

    Zero is retained because JUNIPER-MIB defines it as unavailable or
    inapplicable for these objects. Threshold policy is intentionally not
    applied here; this collector records evidence only.
    """
    metrics: Dict[str, Any] = {}
    overall_status = "pass"
    for name, spec in JNX_OPERATING_COLUMNS.items():
        oid = f"{JNX_OPERATING_BASE_OID}.{spec['column']}"
        cmd = build_snmpwalk_command(
            telemetry_server=telemetry_server,
            target=target,
            oid=oid,
            timeout=timeout,
            ssh_user=ssh_user,
            community=community,
        )
        proc = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(int(timeout) * 2 + 15, 30),
        )
        rows = _parse_numeric_walk(proc.stdout or "")
        populated = [
            row
            for row in rows
            if isinstance(row.get("value"), int) and row.get("value") != 0
        ]
        metric_status = "pass" if proc.returncode == 0 and rows else "fail"
        if metric_status == "fail":
            overall_status = "fail"
        metrics[name] = {
            "status": metric_status,
            "oid": oid,
            "unit": spec["unit"],
            "rows_total": len(rows),
            "rows_populated": len(populated),
            "rows": rows,
            "stderr": (proc.stderr or "").strip(),
        }

    return {
        "status": overall_status,
        "source": "JUNIPER-MIB::jnxOperatingTable",
        "base_oid": JNX_OPERATING_BASE_OID,
        "target": target,
        "metrics": metrics,
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
        juniper_operating_health: Dict[str, Any] = {}
        if result.get("status") == "pass":
            juniper_operating_health = collect_juniper_operating_health(
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
            "juniper_operating_health": juniper_operating_health,
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

    # Missing credentials/configuration means the SNMP test did not
    # execute. Preserve that distinction from an executed SNMP timeout,
    # authentication failure, or missing required object, which is FAIL.
    if not str(community or "").strip():
        report["status"] = "inconclusive"
        report["error"] = (
            "SNMP community is not configured; set SNMP_COMMUNITY"
        )
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
