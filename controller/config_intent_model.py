from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _group_interfaces_by_parent(interface_names: List[str]) -> Dict[str, List[str]]:
    """
    Example:
      et-0/0/11:0 -> parent et-0/0/11
    """
    groups: Dict[str, List[str]] = {}
    for name in interface_names:
        m = re.match(r"^(et-\d+/\d+/\d+)(?::\d+)?$", name.strip())
        if not m:
            continue
        parent = m.group(1)
        groups.setdefault(parent, []).append(name.strip())

    for parent in groups:
        groups[parent] = sorted(groups[parent], key=_iface_sort_key)
    return groups


def _iface_sort_key(name: str) -> Tuple[int, int, int, int]:
    m = re.match(r"^et-(\d+)/(\d+)/(\d+)(?::(\d+))?$", name)
    if not m:
        return (999, 999, 999, 999)
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        int(m.group(4) or -1),
    )


def _extract_node_name(lines: List[str]) -> Optional[str]:
    patterns = [
        re.compile(r"^set groups global system host-name (\S+)$"),
        re.compile(r"^set groups member\d+ system host-name (\S+)$"),
    ]
    for line in lines:
        for pat in patterns:
            m = pat.match(line)
            if m:
                return m.group(1)
    return None


def _extract_router_id(lines: List[str]) -> Optional[str]:
    pat = re.compile(r"^set groups global routing-options router-id (\S+)$")
    for line in lines:
        m = pat.match(line)
        if m:
            return m.group(1)
    return None


def _extract_asn(lines: List[str]) -> Optional[str]:
    pat = re.compile(r"^set groups global routing-options autonomous-system (\S+)$")
    for line in lines:
        m = pat.match(line)
        if m:
            return m.group(1)
    return None


def _extract_ecmp_policy(lines: List[str]) -> Dict[str, Any]:
    model: Dict[str, Any] = {
        "forwarding_table_export_policy": None,
        "load_balance_mode": None,
        "dlb_enabled": False,
        "flowlet_enabled": False,
        "flowlet_inactivity_interval": None,
        "bgp_multipath_enabled": False,
        "bgp_multipath_mode": None,
        "global_load_balancing_configured": False,
        "global_load_balancing_active": False,
    }

    pat_export = re.compile(
        r"^set groups global routing-options forwarding-table export (\S+)$"
    )
    pat_lb_policy_per_flow = re.compile(
        r"^set groups global policy-options policy-statement (\S+) then load-balance per-flow$"
    )
    pat_lb_policy_per_packet = re.compile(
        r"^set groups global policy-options policy-statement (\S+) then load-balance per-packet$"
    )
    pat_flowlet = re.compile(
        r"^set groups global forwarding-options enhanced-hash-key ecmp-dlb flowlet inactivity-interval (\d+)$"
    )
    pat_bgp_multipath = re.compile(
        r"^set groups global protocols bgp multipath(?:\s+(\S+))?$"
    )
    pat_glb_set = re.compile(
        r"^set groups global protocols bgp global-load-balancing"
    )
    pat_glb_deactivate = re.compile(
        r"^deactivate groups global protocols bgp global-load-balancing$"
    )

    export_policy = None
    load_balance_mode = None

    for line in lines:
        m = pat_export.match(line)
        if m:
            export_policy = m.group(1)
            model["forwarding_table_export_policy"] = export_policy
            continue

        m = pat_lb_policy_per_flow.match(line)
        if m and export_policy and m.group(1) == export_policy:
            load_balance_mode = "per-flow"
            model["load_balance_mode"] = load_balance_mode
            continue

        m = pat_lb_policy_per_packet.match(line)
        if m and export_policy and m.group(1) == export_policy:
            load_balance_mode = "per-packet"
            model["load_balance_mode"] = load_balance_mode
            continue

        m = pat_flowlet.match(line)
        if m:
            model["dlb_enabled"] = True
            model["flowlet_enabled"] = True
            model["flowlet_inactivity_interval"] = _safe_int(m.group(1))
            continue

        m = pat_bgp_multipath.match(line)
        if m:
            model["bgp_multipath_enabled"] = True
            suffix = (m.group(1) or "").strip()
            model["bgp_multipath_mode"] = suffix or "default"
            continue

        if pat_glb_set.match(line):
            model["global_load_balancing_configured"] = True
            continue

        if pat_glb_deactivate.match(line):
            model["global_load_balancing_active"] = False
            continue

    if model["global_load_balancing_configured"] and not any(
        line == "deactivate groups global protocols bgp global-load-balancing"
        for line in lines
    ):
        model["global_load_balancing_active"] = True

    return model


def _extract_interface_breakout_and_speed(lines: List[str]) -> Dict[str, Any]:
    """
    Builds parent-level breakout and speed, plus child-interface membership.
    """
    pat_num_subports = re.compile(
        r"^set groups global interfaces (et-\d+/\d+/\d+) number-of-sub-ports (\d+)$"
    )
    pat_speed = re.compile(
        r"^set groups global interfaces (et-\d+/\d+/\d+) speed (\S+)$"
    )
    pat_child_iface = re.compile(
        r"^set groups global interfaces (et-\d+/\d+/\d+:\d+) "
    )

    parent_map: Dict[str, Dict[str, Any]] = {}
    child_ifaces: List[str] = []

    for line in lines:
        m = pat_num_subports.match(line)
        if m:
            parent = m.group(1)
            parent_map.setdefault(parent, {})
            parent_map[parent]["number_of_sub_ports"] = _safe_int(m.group(2), 0)
            continue

        m = pat_speed.match(line)
        if m:
            parent = m.group(1)
            parent_map.setdefault(parent, {})
            parent_map[parent]["configured_speed"] = m.group(2)
            continue

        m = pat_child_iface.match(line)
        if m:
            child_ifaces.append(m.group(1))

    child_ifaces = _dedupe_keep_order(child_ifaces)
    grouped = _group_interfaces_by_parent(child_ifaces)

    for parent, members in grouped.items():
        parent_map.setdefault(parent, {})
        parent_map[parent]["child_interfaces"] = members

    return {
        "parent_interfaces": parent_map,
        "child_interfaces": child_ifaces,
    }


def _extract_l3_fabric_interfaces(lines: List[str]) -> Dict[str, Any]:
    """
    Infer likely routed fabric-facing interfaces from et-* unit 0 family inet address ...
    """
    pat_inet = re.compile(
        r"^set groups global interfaces (et-\d+/\d+/\d+(?::\d+)?) unit 0 family inet address (\S+) primary$"
    )
    pat_inet6 = re.compile(
        r"^set groups global interfaces (et-\d+/\d+/\d+(?::\d+)?) unit 0 family inet6 address (\S+) primary$"
    )

    ipv4: Dict[str, str] = {}
    ipv6: Dict[str, str] = {}

    for line in lines:
        m = pat_inet.match(line)
        if m:
            ipv4[m.group(1)] = m.group(2)
            continue

        m = pat_inet6.match(line)
        if m:
            ipv6[m.group(1)] = m.group(2)
            continue

    routed_ifaces = sorted(set(ipv4.keys()) | set(ipv6.keys()), key=_iface_sort_key)

    return {
        "routed_interfaces": routed_ifaces,
        "ipv4_addresses": ipv4,
        "ipv6_addresses": ipv6,
    }


def _build_speed_groups(
    breakout_model: Dict[str, Any],
    routed_model: Dict[str, Any],
) -> Dict[str, Any]:
    parent_interfaces = breakout_model.get("parent_interfaces", {}) or {}
    routed_ifaces = set(routed_model.get("routed_interfaces", []) or [])

    speed_groups: Dict[str, List[str]] = {}

    for parent, data in parent_interfaces.items():
        speed = str(data.get("configured_speed") or "").upper()
        members = data.get("child_interfaces", []) or []

        routed_members = [m for m in members if m in routed_ifaces]
        if not speed or not routed_members:
            continue

        speed_groups.setdefault(speed, []).extend(routed_members)

    for speed in list(speed_groups.keys()):
        speed_groups[speed] = sorted(
            _dedupe_keep_order(speed_groups[speed]),
            key=_iface_sort_key,
        )

    return speed_groups


def _infer_mixed_speed_ecmp(speed_groups: Dict[str, List[str]]) -> bool:
    non_empty = [speed for speed, members in speed_groups.items() if members]
    return len(non_empty) >= 2


def _infer_risk_flags(
    ecmp_policy: Dict[str, Any],
    speed_groups: Dict[str, List[str]],
) -> List[str]:
    flags: List[str] = []

    mixed_speed = _infer_mixed_speed_ecmp(speed_groups)
    flowlet_enabled = bool(ecmp_policy.get("flowlet_enabled"))
    inactivity = _safe_int(ecmp_policy.get("flowlet_inactivity_interval"), 0) or 0
    lb_mode = ecmp_policy.get("load_balance_mode")

    if mixed_speed:
        flags.append("mixed_speed_ecmp_present")

    if flowlet_enabled and inactivity >= 10000:
        flags.append("high_flowlet_stickiness")

    if mixed_speed and lb_mode == "per-flow":
        flags.append("mixed_speed_ecmp_without_explicit_weighting")

    if mixed_speed and flowlet_enabled:
        flags.append("mixed_speed_ecmp_with_flowlet_dlb")

    return _dedupe_keep_order(flags)


def build_config_intent_model_from_text(config_text: str) -> Dict[str, Any]:
    lines = [
        line.strip()
        for line in config_text.splitlines()
        if line.strip()
    ]

    node_name = _extract_node_name(lines)
    router_id = _extract_router_id(lines)
    asn = _extract_asn(lines)

    ecmp_policy = _extract_ecmp_policy(lines)
    breakout_model = _extract_interface_breakout_and_speed(lines)
    routed_model = _extract_l3_fabric_interfaces(lines)
    speed_groups = _build_speed_groups(breakout_model, routed_model)
    risk_flags = _infer_risk_flags(ecmp_policy, speed_groups)

    intent = {
        "node": node_name,
        "router_id": router_id,
        "autonomous_system": asn,
        "ecmp": {
            "enabled": bool(ecmp_policy.get("forwarding_table_export_policy"))
            or bool(ecmp_policy.get("bgp_multipath_enabled")),
            "forwarding_table_export_policy": ecmp_policy.get("forwarding_table_export_policy"),
            "load_balance_mode": ecmp_policy.get("load_balance_mode"),
            "dlb_enabled": ecmp_policy.get("dlb_enabled"),
            "flowlet_enabled": ecmp_policy.get("flowlet_enabled"),
            "flowlet_inactivity_interval": ecmp_policy.get("flowlet_inactivity_interval"),
            "bgp_multipath_enabled": ecmp_policy.get("bgp_multipath_enabled"),
            "bgp_multipath_mode": ecmp_policy.get("bgp_multipath_mode"),
            "global_load_balancing_configured": ecmp_policy.get("global_load_balancing_configured"),
            "global_load_balancing_active": ecmp_policy.get("global_load_balancing_active"),
            "mixed_speed_ecmp_present": _infer_mixed_speed_ecmp(speed_groups),
        },
        "interfaces": {
            "parent_interfaces": breakout_model.get("parent_interfaces", {}),
            "routed_interfaces": routed_model.get("routed_interfaces", []),
            "speed_groups": speed_groups,
            "ipv4_addresses": routed_model.get("ipv4_addresses", {}),
            "ipv6_addresses": routed_model.get("ipv6_addresses", {}),
        },
        "risk_flags": risk_flags,
        "interpretation_hints": _build_interpretation_hints(
            ecmp_policy=ecmp_policy,
            speed_groups=speed_groups,
            risk_flags=risk_flags,
        ),
    }

    return intent


def _build_interpretation_hints(
    *,
    ecmp_policy: Dict[str, Any],
    speed_groups: Dict[str, List[str]],
    risk_flags: List[str],
) -> List[str]:
    hints: List[str] = []

    if ecmp_policy.get("bgp_multipath_enabled"):
        mode = ecmp_policy.get("bgp_multipath_mode") or "default"
        hints.append(f"BGP multipath is enabled ({mode}).")

    if ecmp_policy.get("load_balance_mode"):
        hints.append(
            f"Forwarding-table export policy uses {ecmp_policy.get('load_balance_mode')} load balancing."
        )

    if ecmp_policy.get("flowlet_enabled"):
        inactivity = ecmp_policy.get("flowlet_inactivity_interval")
        hints.append(
            f"ECMP DLB flowlet mode is configured with inactivity interval {inactivity}."
        )

    if _infer_mixed_speed_ecmp(speed_groups):
        present_speeds = ", ".join(sorted(speed_groups.keys()))
        hints.append(f"Mixed-speed routed ECMP members are present ({present_speeds}).")

    if "high_flowlet_stickiness" in risk_flags:
        hints.append("High flowlet inactivity interval may increase post-event stickiness.")

    if "mixed_speed_ecmp_without_explicit_weighting" in risk_flags:
        hints.append(
            "Mixed-speed ECMP is present with generic per-flow load balancing and no explicit capacity weighting visible in config."
        )

    return hints


def build_config_intent_model_from_file(input_path: Path) -> Dict[str, Any]:
    return build_config_intent_model_from_text(_load_text(input_path))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a normalized config intent model from Junos 'display set' config."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to raw config text file (show | display set | no-more output).",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path. Default: artifacts/config_intent/<node>_config_intent.json",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    model = build_config_intent_model_from_file(input_path)

    node = model.get("node") or input_path.stem
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path("artifacts") / "config_intent" / f"{node}_config_intent.json"

    write_json(output_path, model)
    print(f"Config intent model written to: {output_path}")


if __name__ == "__main__":
    main()
