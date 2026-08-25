"""Platform CPU and memory health collection for FVP."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from controller.stress_actions.common import (
    get_node_connection,
    run_remote_command,
)


def _parse_cpu_utilization(text: str) -> float | None:
    """Parse CPU utilization from Linux top output."""

    match = re.search(
        r"%Cpu\(s\):.*?([\d.]+)\s+id",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    idle_pct = float(match.group(1))

    return round(
        100.0 - idle_pct,
        2,
    )


def _parse_memory(text: str) -> Dict[str, float | None]:
    """Parse memory summary from Linux top output."""

    match = re.search(
        r"MiB Mem\s*:\s*"
        r"([\d.]+)\s+total,\s*"
        r"([\d.]+)\s+free,\s*"
        r"([\d.]+)\s+used,\s*"
        r"([\d.]+)\s+buff/cache",
        text,
        re.IGNORECASE,
    )

    if not match:
        return {
            "total_mib": None,
            "free_mib": None,
            "used_mib": None,
            "buff_cache_mib": None,
            "utilization_pct": None,
        }

    total = float(match.group(1))
    free = float(match.group(2))
    used = float(match.group(3))
    buff_cache = float(match.group(4))

    utilization_pct = (
        round(
            used / total * 100.0,
            2,
        )
        if total > 0
        else None
    )

    return {
        "total_mib": total,
        "free_mib": free,
        "used_mib": used,
        "buff_cache_mib": buff_cache,
        "utilization_pct": utilization_pct,
    }


def collect_node_platform_health(
    *,
    node: str,
    inventory: Dict[str, Any],
    cpu_threshold_pct: float = 90.0,
    memory_threshold_pct: float = 90.0,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Collect CPU and memory health for one node."""

    conn = get_node_connection(
        node,
        inventory,
    )

    host = conn["host"]
    user = conn["user"]
    password = conn["password"]

    step = run_remote_command(
        host,
        user,
        password,
        "top -b -n 1 | head -8",
        "platform_health cpu_memory",
        timeout=timeout,
    )

    stdout = str(
        step.get("stdout") or ""
    )

    evidence: List[str] = []
    failure_reasons: List[str] = []

    if step.get("returncode") != 0:
        return {
            "status": "fail",
            "node": node,
            "cpu": {
                "status": "unknown",
                "utilization_pct": None,
                "threshold_pct": cpu_threshold_pct,
            },
            "memory": {
                "status": "unknown",
                "utilization_pct": None,
                "threshold_pct": memory_threshold_pct,
            },
            "core_count": 0,
            "daemon_crash_count": 0,
            "unexpected_alarm_count": 0,
            "evidence": [
                "CPU/memory collection command failed."
            ],
            "collection_step": step,
        }

    cpu_pct = _parse_cpu_utilization(
        stdout
    )

    memory = _parse_memory(
        stdout
    )

    memory_pct = memory.get(
        "utilization_pct"
    )

    if cpu_pct is None:
        cpu_status = "unknown"
        failure_reasons.append(
            "Unable to parse CPU utilization."
        )
    elif cpu_pct > cpu_threshold_pct:
        cpu_status = "fail"
        failure_reasons.append(
            f"CPU utilization {cpu_pct}% exceeded "
            f"threshold {cpu_threshold_pct}%."
        )
    else:
        cpu_status = "pass"
        evidence.append(
            f"CPU utilization {cpu_pct}% <= "
            f"{cpu_threshold_pct}%."
        )

    if memory_pct is None:
        memory_status = "unknown"
        failure_reasons.append(
            "Unable to parse memory utilization."
        )
    elif memory_pct > memory_threshold_pct:
        memory_status = "fail"
        failure_reasons.append(
            f"Memory utilization {memory_pct}% exceeded "
            f"threshold {memory_threshold_pct}%."
        )
    else:
        memory_status = "pass"
        evidence.append(
            f"Memory utilization {memory_pct}% <= "
            f"{memory_threshold_pct}%."
        )


    # ------------------------------------------------------
    # Collect core-dump health.
    # ------------------------------------------------------

    core_step = run_remote_command(
        host,
        user,
        password,
        'cli -c "show system core-dumps | no-more"',
        "platform_health core_dumps",
        timeout=timeout,
    )

    core_stdout = str(
        core_step.get("stdout") or ""
    )

    core_count = (
        _parse_core_count(core_stdout)
        if core_step.get("returncode") == 0
        else None
    )

    if core_count is None:
        core_status = "unknown"
        failure_reasons.append(
            "Unable to determine core-dump count."
        )
    elif core_count > 0:
        core_status = "fail"
        failure_reasons.append(
            f"{core_count} core file(s) detected."
        )
    else:
        core_status = "pass"
        evidence.append(
            "No core files detected."
        )


    # ------------------------------------------------------
    # Collect active alarms.
    #
    # IMPORTANT:
    # Active alarms are evidence only at this stage.
    # Do not treat existing alarms as unexpected alarms.
    # ------------------------------------------------------

    alarm_step = run_remote_command(
        host,
        user,
        password,
        'cli -c "show system alarms | no-more"',
        "platform_health alarms",
        timeout=timeout,
    )

    alarm_stdout = str(
        alarm_step.get("stdout") or ""
    )

    alarms = (
        _parse_alarms(alarm_stdout)
        if alarm_step.get("returncode") == 0
        else []
    )

    # ------------------------------------------------------
    # Collect optics health.
    #
    # Raw optics alarms/warnings are snapshot evidence only.
    # PRE/POST comparison determines whether a new optics
    # problem was introduced by the scenario.
    # ------------------------------------------------------

    optics_step = run_remote_command(
        host,
        user,
        password,
        (
            'cli -c "show interfaces diagnostics '
            'optics | no-more"'
        ),
        "platform_health optics",
        timeout=timeout,
    )

    optics_stdout = str(
        optics_step.get("stdout") or ""
    )

    optics = (
        _parse_optics_health(
            optics_stdout
        )
        if optics_step.get("returncode") == 0
        else {
            "status": "unknown",
            "active_alarm_count": 0,
            "active_warning_count": 0,
            "active_alarms": [],
            "active_warnings": [],
            "alarm_lines_checked": 0,
            "warning_lines_checked": 0,
        }
    )

    # ------------------------------------------------------
    # Collect physical-interface error counters.
    #
    # Raw counters are snapshot evidence only.
    # PRE/POST delta determines whether the scenario
    # introduced new CRC/framing/FEC failures.
    # ------------------------------------------------------

    interface_error_step = run_remote_command(
        host,
        user,
        password,
        'cli -c "show interfaces extensive | no-more"',
        "platform_health interface_errors",
        timeout=max(timeout, 120),
    )

    interface_error_stdout = str(
        interface_error_step.get("stdout") or ""
    )

    interface_errors = (
        _parse_interface_error_health(
            interface_error_stdout
        )
        if interface_error_step.get("returncode") == 0
        else []
    )

    if (
        cpu_status == "fail"
        or memory_status == "fail"
        or core_status == "fail"
    ):
        overall_status = "fail"
    elif (
        cpu_status == "pass"
        and memory_status == "pass"
        and core_status == "pass"
    ):
        overall_status = "pass"
    else:
        overall_status = "inconclusive"

    evidence.extend(
        failure_reasons
    )

    return {
        "status": overall_status,
        "node": node,

        "cpu": {
            "status": cpu_status,
            "utilization_pct": cpu_pct,
            "threshold_pct": cpu_threshold_pct,
        },

        "memory": {
            **memory,
            "status": memory_status,
            "threshold_pct": memory_threshold_pct,
        },

        "cores": {
            "status": core_status,
            "count": (
                core_count
                if core_count is not None
                else 0
            ),
        },

        "alarms": {
            "active_count": len(alarms),
            "active": alarms,
        },

        "optics": optics,
        "interface_errors": interface_errors,

        "core_count": (
            core_count
            if core_count is not None
            else 0
        ),

        "daemon_crash_count": 0,
        "unexpected_alarm_count": 0,

        "evidence": evidence,

        "collection_steps": {
            "cpu_memory": step,
            "core_dumps": core_step,
            "alarms": alarm_step,
            "optics": optics_step,
            "interface_errors": interface_error_step,
        },
    }

def _optics_identity(
    item: Dict[str, Any],
) -> tuple:
    return (
        str(
            item.get("interface")
            or ""
        ).strip(),
        item.get("lane"),
        str(
            item.get("signal")
            or ""
        ).strip().lower(),
    )


def _find_new_optics_alarms(
    *,
    baseline: List[Dict[str, Any]],
    current: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    baseline_ids = {
        _optics_identity(item)
        for item in baseline
    }

    return [
        item
        for item in current
        if _optics_identity(item)
        not in baseline_ids
    ]



def _parse_core_count(text: str) -> int | None:
    """Parse Junos EVO core-dump count."""

    match = re.search(
        r"total\s+files:\s*(\d+)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def _parse_alarms(
    text: str,
) -> list[dict[str, str]]:
    """Parse active Junos alarm rows."""

    alarms = []

    for line in str(text or "").splitlines():
        line = line.strip()

        if not line:
            continue

        match = re.match(
            r"^"
            r"(\d{4}-\d{2}-\d{2}\s+"
            r"\d{2}:\d{2}:\d{2}\s+\S+)"
            r"\s+"
            r"(Major|Minor)"
            r"\s+"
            r"(.+)"
            r"$",
            line,
            re.IGNORECASE,
        )

        if not match:
            continue

        alarms.append(
            {
                "time": match.group(1),
                "class": match.group(2),
                "description": match.group(3).strip(),
            }
        )

    return alarms


def _alarm_identity(
    alarm: dict[str, str],
) -> tuple[str, str]:
    return (
        str(alarm.get("class") or "").lower(),
        str(alarm.get("description") or "").strip(),
    )


def _find_new_alarms(
    *,
    baseline: list[dict[str, str]],
    current: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return alarms present now but absent at baseline."""

    baseline_ids = {
        _alarm_identity(alarm)
        for alarm in baseline
    }

    return [
        alarm
        for alarm in current
        if _alarm_identity(alarm)
        not in baseline_ids
    ]

def compare_platform_health(
    *,
    baseline: Dict[str, Any],
    current: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare pre/post platform-health snapshots."""

    baseline_alarms = (
        (baseline.get("alarms") or {}).get("active")
        or []
    )

    current_alarms = (
        (current.get("alarms") or {}).get("active")
        or []
    )

    new_alarms = _find_new_alarms(
        baseline=baseline_alarms,
        current=current_alarms,
    )


    baseline_optics = (
        baseline.get("optics")
        or {}
    )

    current_optics = (
        current.get("optics")
        or {}
    )

    new_optics_alarms = (
        _find_new_optics_alarms(
            baseline=(
                baseline_optics.get(
                    "active_alarms"
                )
                or []
            ),
            current=(
                current_optics.get(
                    "active_alarms"
                )
                or []
            ),
        )
    )

    interface_error_delta = (
        compare_interface_error_health(
            baseline=(
                baseline.get(
                    "interface_errors"
                )
                or []
            ),
            current=(
                current.get(
                    "interface_errors"
                )
                or []
            ),
        )
    )

    baseline_core_count = int(
        baseline.get("core_count") or 0
    )

    current_core_count = int(
        current.get("core_count") or 0
    )

    new_core_count = max(
        0,
        current_core_count - baseline_core_count,
    )

    baseline_memory_pct = (
        (baseline.get("memory") or {}).get(
            "utilization_pct"
        )
    )

    current_memory_pct = (
        (current.get("memory") or {}).get(
            "utilization_pct"
        )
    )

    memory_delta_pct = None

    if (
        baseline_memory_pct is not None
        and current_memory_pct is not None
    ):
        memory_delta_pct = round(
            current_memory_pct
            - baseline_memory_pct,
            2,
        )

    status = "pass"

    if (
        new_core_count > 0
        or new_alarms
        or new_optics_alarms
        or interface_error_delta.get(
            "status"
        ) == "fail"
    ):
        status = "fail"

    return {
        "status": status,

        "baseline": baseline,
        "current": current,

        "new_alarms": new_alarms,
        "unexpected_alarm_count": len(
            new_alarms
        ),

        "baseline_core_count":
            baseline_core_count,

        "current_core_count":
            current_core_count,

        "new_core_count":
            new_core_count,

        "memory_delta_pct":
            memory_delta_pct,

        "new_optics_alarms":
            new_optics_alarms,

        "new_optics_alarm_count":
            len(new_optics_alarms),

        "interface_error_delta":
            interface_error_delta,

        "interface_error_failure_count":
            interface_error_delta.get(
                "failure_interface_count",
                0,
            ),

        "interface_error_failure_interfaces":
            interface_error_delta.get(
                "failure_interfaces",
                [],
            ),
    }


def _parse_interface_error_health(
    text: str,
) -> list[dict[str, Any]]:
    """Parse physical-interface error counters from Junos EVO output."""

    interfaces = []
    current = None

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()

        match = re.match(
            r"Physical interface:\s*([^,\s]+)",
            line,
            re.IGNORECASE,
        )

        if match:
            if current:
                interfaces.append(current)

            current = {
                "interface": match.group(1),
                "input_errors": 0,
                "framing_errors": 0,
                "output_errors": 0,
                "hs_link_crc_errors": 0,
                "fec_corrected_errors": 0,
                "fec_uncorrected_errors": 0,
                "rx_crc_align_errors": 0,
                "tx_crc_align_errors": 0,
            }

            continue

        if current is None:
            continue

        if line.startswith("Errors:"):
            match = re.search(
                r"Errors:\s*(\d+).*?"
                r"Framing errors:\s*(\d+)",
                line,
            )

            if match:
                current["input_errors"] = int(
                    match.group(1)
                )
                current["framing_errors"] = int(
                    match.group(2)
                )

            continue

        if line.startswith("Carrier transitions:"):
            match = re.search(
                r"Errors:\s*(\d+).*?"
                r"HS link CRC errors:\s*(\d+)",
                line,
            )

            if match:
                current["output_errors"] = int(
                    match.group(1)
                )
                current["hs_link_crc_errors"] = int(
                    match.group(2)
                )

            continue

        match = re.match(
            r"FEC Corrected Errors\s+(\d+)$",
            line,
        )

        if match:
            current["fec_corrected_errors"] = int(
                match.group(1)
            )
            continue

        match = re.match(
            r"FEC Uncorrected Errors\s+(\d+)$",
            line,
        )

        if match:
            current["fec_uncorrected_errors"] = int(
                match.group(1)
            )
            continue

        match = re.match(
            r"CRC/Align errors\s+(\d+)\s+(\d+)",
            line,
        )

        if match:
            current["rx_crc_align_errors"] = int(
                match.group(1)
            )
            current["tx_crc_align_errors"] = int(
                match.group(2)
            )

    if current:
        interfaces.append(current)

    return interfaces


def compare_interface_error_health(
    *,
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> Dict[str, Any]:
    """Compare PRE/POST physical-interface error counters."""

    baseline_by_interface = {
        item["interface"]: item
        for item in baseline
        if item.get("interface")
    }

    deltas = []
    failure_interfaces = []

    counters = (
        "input_errors",
        "framing_errors",
        "output_errors",
        "hs_link_crc_errors",
        "fec_corrected_errors",
        "fec_uncorrected_errors",
        "rx_crc_align_errors",
        "tx_crc_align_errors",
    )

    for current_item in current:
        interface = current_item.get("interface")

        if not interface:
            continue

        baseline_item = baseline_by_interface.get(
            interface,
            {},
        )

        delta = {
            "interface": interface,
        }

        for counter in counters:
            pre_value = int(
                baseline_item.get(counter) or 0
            )
            post_value = int(
                current_item.get(counter) or 0
            )

            delta[counter] = max(
                0,
                post_value - pre_value,
            )

        #
        # Strong physical-error failure signals.
        #
        hard_failure = any(
            delta[counter] > 0
            for counter in (
                "framing_errors",
                "hs_link_crc_errors",
                "fec_uncorrected_errors",
                "rx_crc_align_errors",
                "tx_crc_align_errors",
            )
        )

        #
        # Generic input/output errors are retained as
        # evidence but are not independently promoted here,
        # because they may include broader non-CRC causes.
        #
        delta["hard_failure"] = hard_failure

        if hard_failure:
            failure_interfaces.append(
                interface
            )

        deltas.append(delta)

    return {
        "status": (
            "fail"
            if failure_interfaces
            else "pass"
        ),
        "interface_count": len(deltas),
        "failure_interface_count":
            len(failure_interfaces),
        "failure_interfaces":
            failure_interfaces,
        "deltas": deltas,
    }




def _parse_optics_health(text: str) -> Dict[str, Any]:
    """Parse active optics alarms/warnings from Junos diagnostics output."""

    current_interface = None
    current_lane = None

    active_alarms = []
    active_warnings = []

    alarm_lines_checked = 0
    warning_lines_checked = 0

    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()

        interface_match = re.match(
            r"^Physical interface:\s+(\S+)",
            line,
        )

        if interface_match:
            current_interface = interface_match.group(1)
            current_lane = None
            continue

        lane_match = re.match(
            r"^\s*Lane\s+(\d+)",
            line,
        )

        if lane_match:
            current_lane = int(
                lane_match.group(1)
            )
            continue

        state_match = re.match(
            r"^\s*(.+?(?:alarm|warning))\s*:\s*(On|Off)\s*$",
            line,
            re.IGNORECASE,
        )

        if not state_match:
            continue

        name = state_match.group(1).strip()
        state = state_match.group(2).lower()

        entry = {
            "interface": current_interface,
            "lane": current_lane,
            "signal": name,
            "state": state,
        }

        if "warning" in name.lower():
            warning_lines_checked += 1

            if state == "on":
                active_warnings.append(
                    entry
                )
        else:
            alarm_lines_checked += 1

            if state == "on":
                active_alarms.append(
                    entry
                )

    if active_alarms:
        status = "fail"
    elif active_warnings:
        status = "warn"
    elif (
        alarm_lines_checked > 0
        or warning_lines_checked > 0
    ):
        status = "pass"
    else:
        status = "unknown"

    return {
        "status": status,
        "active_alarm_count": len(
            active_alarms
        ),
        "active_warning_count": len(
            active_warnings
        ),
        "active_alarms": active_alarms,
        "active_warnings": active_warnings,
        "alarm_lines_checked":
            alarm_lines_checked,
        "warning_lines_checked":
            warning_lines_checked,
    }
