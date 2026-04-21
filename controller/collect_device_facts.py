import os
import json
import re
from controller.config_loader import load_inventory
from controller.device_client import DeviceClient
from controller.utils import ensure_dir


def normalize_interface_name(iface: str) -> str:
    """
    Normalize interface names to physical form.

    Examples:
        et-0/0/0.0   -> et-0/0/0
        et-0/0/0:0   -> et-0/0/0
        et-7/0/8.16386 -> et-7/0/8
    """
    if not iface:
        return iface
    iface = iface.strip()
    iface = re.sub(r"\.\d+$", "", iface)
    iface = re.sub(r":\d+$", "", iface)
    return iface


def add_interface_speed_aliases(speed_map: dict) -> dict:
    """
    Add harmless aliases for downstream consumers.

    For each physical interface:
      et-x/x/x -> also add et-x/x/x:0 and et-x/x/x.0

    For each channelized/member interface:
      et-x/x/x:y -> also add et-x/x/x
    """
    aliased = dict(speed_map)

    for iface, speed in list(speed_map.items()):
        base = normalize_interface_name(iface)
        aliased.setdefault(base, speed)
        aliased.setdefault(f"{base}:0", speed)
        aliased.setdefault(f"{base}.0", speed)

    return aliased


def derive_interface_speeds_from_terse(interfaces_terse: str) -> dict:
    """
    Derive interface speeds from breakout pattern.

    Returns:
        {
            "et-0/0/11:0": "400G",
            "et-0/0/40:0": "100G",
            ...
        }

    Notes:
    - Keeps existing legacy behavior.
    - This works best when breakout member interfaces (:0/:1/...) are visible.
    """
    from collections import defaultdict

    lane_map = defaultdict(list)

    for line in interfaces_terse.splitlines():
        line = line.strip()
        if not line.startswith("et-"):
            continue

        iface = line.split()[0]

        # skip logical units
        if "." in iface:
            continue

        m = re.match(r"(et-\d+/\d+/\d+)(?::(\d+))?", iface)
        if not m:
            continue

        parent = m.group(1)
        lane = m.group(2)

        if lane is not None:
            lane_map[parent].append(int(lane))

    speed_map = {}

    for parent, lanes in lane_map.items():
        lane_count = len(lanes)

        if lane_count == 2:
            speed = "400G"
        elif lane_count == 4:
            speed = "100G"
        elif lane_count == 8:
            speed = "100G"
        else:
            speed = "UNKNOWN"

        for lane in lanes:
            iface = f"{parent}:{lane}"
            speed_map[iface] = speed

    return speed_map


def derive_interface_speeds_from_chassis_hardware(chassis_hardware: str, interfaces_terse: str = "") -> dict:
    """
    Derive physical interface speeds from 'show chassis hardware'.

    Supports multi-FPC systems such as QFX5700 where ports may be:
      et-6/0/0..3   from '4x400G ...'
      et-7/0/0..15  from '16x100G ...'

    Example input lines:
      FPC 6            ... JNP-FPC-4CD
        PIC 0                   BUILTIN      BUILTIN           4x400G QSFP56-DD
      FPC 7            ... JNP-FPC-16C
        PIC 0                   BUILTIN      BUILTIN           16x100G-QSFP
    """
    speed_map = {}

    if not chassis_hardware:
        return speed_map

    present_ifaces = set()

    for line in interfaces_terse.splitlines():
        line = line.strip()
        if not line.startswith("et-"):
            continue
        iface = line.split()[0]
        iface = normalize_interface_name(iface)
        if re.match(r"^et-\d+/\d+/\d+$", iface):
            present_ifaces.add(iface)

    current_fpc = None
    fpc_pat = re.compile(r"^\s*FPC\s+(\d+)\b")
    speed_pat = re.compile(r"(\d+)\s*x\s*(\d+)\s*G\b", re.IGNORECASE)

    for raw_line in chassis_hardware.splitlines():
        line = raw_line.rstrip()

        m_fpc = fpc_pat.match(line)
        if m_fpc:
            current_fpc = int(m_fpc.group(1))
            continue

        if current_fpc is None:
            continue

        # Only care about PIC description lines that contain NxYG form
        m_speed = speed_pat.search(line)
        if not m_speed:
            continue

        port_count = int(m_speed.group(1))
        port_speed = f"{int(m_speed.group(2))}G"

        for port in range(port_count):
            iface = f"et-{current_fpc}/0/{port}"

            # If terse data exists, only keep interfaces that actually exist on the box
            if present_ifaces and iface not in present_ifaces:
                continue

            speed_map[iface] = port_speed

    return speed_map


def parse_interface_speeds(media_output):
    """
    Parse 'show interfaces media' output into a per-interface speed map.

    Returns:
        {
            "et-0/0/11:0": "400G",
            "et-0/0/40:0": "100G",
            ...
        }

    Notes:
    - Keeps this parser intentionally tolerant because output format can vary
      a bit by platform / Junos flavor.
    - We only care about et- interfaces for the fabric/ECMP use case.
    """
    speed_map = {}

    if not media_output:
        return speed_map

    current_interface = None

    speed_patterns = [
        re.compile(r"\bSpeed\s*:\s*([0-9]+\s*[GM]bps)\b", re.IGNORECASE),
        re.compile(r"\bSpeed\s*:\s*([0-9]+\s*[GM])\b", re.IGNORECASE),
        re.compile(r"\bLink-speed\s*:\s*([0-9]+\s*[GM]bps)\b", re.IGNORECASE),
        re.compile(r"\bLink-speed\s*:\s*([0-9]+\s*[GM])\b", re.IGNORECASE),
        re.compile(r"\b([0-9]+)\s*Gbps\b", re.IGNORECASE),
        re.compile(r"\b([0-9]+)\s*G\b", re.IGNORECASE),
    ]

    def normalize_speed(raw):
        if not raw:
            return None
        s = str(raw).strip().upper().replace(" ", "")
        s = s.replace("GBPS", "G").replace("MBPS", "M")
        if re.fullmatch(r"[0-9]+[GM]", s):
            return s
        if re.fullmatch(r"[0-9]+", s):
            return f"{s}G"
        return s

    for raw_line in media_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Common first token style:
        # et-0/0/11:0 ...
        m_if = re.match(r"^(et-\d+/\d+/\d+(?::\d+)?)\b", line)
        if m_if:
            current_interface = m_if.group(1)

            # Speed may appear on the same line
            detected = None
            for pattern in speed_patterns:
                m_speed = pattern.search(line)
                if m_speed:
                    detected = normalize_speed(m_speed.group(1))
                    break

            if current_interface and detected:
                speed_map[current_interface] = detected
            continue

        if not current_interface:
            continue

        # Speed may appear on subsequent lines for the current interface block
        detected = None
        for pattern in speed_patterns:
            m_speed = pattern.search(line)
            if m_speed:
                detected = normalize_speed(m_speed.group(1))
                break

        if detected and current_interface.startswith("et-"):
            speed_map[current_interface] = detected

    return speed_map


def collect_facts(client):
    facts = {}

    commands = {
        "hostname": "show configuration system host-name | display set | no-more",
        "version": "show version | no-more",
        "chassis_hardware": "show chassis hardware | no-more",
        "interfaces_terse": "show interfaces terse | no-more",
        "bgp_summary": "show bgp summary | no-more",
        "lldp_neighbors": "show lldp neighbors | no-more",
        "route_summary": "show route summary | no-more",
    }

    client.connect()
    try:
        for key, cmd in commands.items():
            facts[key] = client.run_command(cmd)
    finally:
        client.close()

    # 1) Chassis-hardware derived speeds first (best source for multi-FPC platforms)
    chassis_speed_map = derive_interface_speeds_from_chassis_hardware(
        facts.get("chassis_hardware", ""),
        facts.get("interfaces_terse", ""),
    )

    # 2) Legacy terse-derived speeds as fallback
    terse_speed_map = derive_interface_speeds_from_terse(
        facts.get("interfaces_terse", "")
    )

    # 3) Merge without breaking legacy behavior:
    #    chassis map wins for physical ports; terse map still fills breakout/member cases
    merged_speed_map = {}
    merged_speed_map.update(terse_speed_map)
    merged_speed_map.update(chassis_speed_map)

    # 4) Add aliases so downstream lookups can resolve physical/member/unit names safely
    facts["interface_speeds"] = add_interface_speed_aliases(merged_speed_map)

    return facts


def main():
    inventory = load_inventory("inventory/inventory.yaml")
    defaults = inventory.get("defaults", {})
    nodes = inventory.get("nodes", {})

    output_dir = "artifacts/device_facts"
    ensure_dir(output_dir)

    for node_name, node_data in nodes.items():
        device = {**defaults, **node_data}
        host = device.get("mgmt_ip")

        print(f"\n[{node_name}] collecting facts from {host} ...")

        client = DeviceClient(
            host=host,
            username=device["username"],
            password=device["password"],
            port=device.get("port", 22),
            timeout=device.get("timeout", 30),
        )

        try:
            facts = collect_facts(client)
            facts["node_name"] = node_name
            facts["hostname_expected"] = device.get("hostname")
            facts["mgmt_ip"] = host
            facts["role"] = device.get("role")
            facts["platform"] = device.get("platform")
            facts["asn"] = device.get("asn")
            facts["router_id"] = device.get("router_id")

            output_file = os.path.join(output_dir, f"{node_name}_facts.json")
            with open(output_file, "w") as fh:
                json.dump(facts, fh, indent=2)

            print(f"  OK: wrote {output_file}")

        except Exception as exc:
            print(f"  FAIL: {exc}")


if __name__ == "__main__":
    main()
