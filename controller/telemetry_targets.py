# controller/telemetry_targets.py

import json
import os
from typing import Any, Dict, List, Set, Optional
import re


DEFAULT_TOPOLOGY_PATH = os.path.join("artifacts", "topology", "topology_discovery.json")



def _load_device_facts_for_node(
    node: str,
    device_facts_dir: str = os.path.join("artifacts", "device_facts"),
) -> Dict[str, Any]:
    candidates = [
        os.path.join(device_facts_dir, f"{node}_facts.json"),
        os.path.join(device_facts_dir, f"{node.lower()}_facts.json"),
        os.path.join(device_facts_dir, f"{node.upper()}_facts.json"),
    ]

    for path in candidates:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)

    # fallback: scan node_name field
    if os.path.isdir(device_facts_dir):
        for name in os.listdir(device_facts_dir):
            if not name.endswith("_facts.json"):
                continue
            path = os.path.join(device_facts_dir, name)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if normalize_node(str(data.get("node_name", ""))) == normalize_node(node):
                    return data
            except Exception:
                continue

    raise FileNotFoundError(
        f"device facts not found for node={node} under {device_facts_dir}"
    )


def _parse_lldp_local_interfaces_from_facts(output: str) -> List[str]:
    """
    Parse local et-* interfaces from stored 'show lldp neighbors' output.
    """
    interfaces: List[str] = []
    pattern = re.compile(r"^(et-\d+/\d+/\d+(?::\d+)?)\s+")

    for line in output.splitlines():
        line = line.rstrip()
        m = pattern.match(line)
        if not m:
            continue
        iface = m.group(1)
        interfaces.append(iface)

    deduped: List[str] = []
    seen = set()
    for iface in interfaces:
        if iface not in seen:
            deduped.append(iface)
            seen.add(iface)

    return deduped


def _sort_interface_names(interfaces: List[str]) -> List[str]:
    def key_func(name: str):
        m = re.match(r"et-(\d+)/(\d+)/(\d+)(?::(\d+))?$", name)
        if not m:
            return (999, 999, 999, 999, name)
        fpc = int(m.group(1))
        pic = int(m.group(2))
        port = int(m.group(3))
        lane = int(m.group(4)) if m.group(4) is not None else -1
        return (fpc, pic, port, lane, name)

    return sorted(interfaces, key=key_func)


def _run_cli_show_lldp_neighbors(node: str, host: str, ssh_user: str = "root", timeout: int = 30) -> str:
    print(f"[LLDP] collecting neighbors from node={node} host={host}")
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", f"ConnectTimeout={timeout}",
        f"{ssh_user}@{host}",
        'cli -c "show lldp neighbors"',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to collect LLDP neighbors from host={host}, rc={result.returncode}, stderr={result.stderr.strip()}"
        )
    return result.stdout


def _parse_lldp_local_interfaces(output: str) -> List[str]:
    """
    Parse Junos 'show lldp neighbors' output and return local et-* interfaces.
    Example lines:
      et-0/0/12:0        -   xx:xx:...   et-0/0/16        peer
      et-0/0/60:3        -   xx:xx:...   et-0/0/60:3      peer
    """
    interfaces: List[str] = []
    pattern = re.compile(r"^(et-\d+/\d+/\d+:\d+)\s+")

    for line in output.splitlines():
        line = line.rstrip()
        m = pattern.match(line)
        if not m:
            continue
        iface = m.group(1)
        interfaces.append(iface)

    # de-dup preserve order
    deduped: List[str] = []
    seen = set()
    for iface in interfaces:
        if iface not in seen:
            deduped.append(iface)
            seen.add(iface)

    return deduped


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def normalize_node(value: str) -> str:
    return (value or "").strip().lower()


def extract_topology_links(topology_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expected flexible formats:
    {
      "links": [
        {
          "local_node": "leaf1",
          "local_intf": "et-0/0/4",
          "peer_node": "spine1",
          "peer_intf": "et-0/0/0"
        }
      ]
    }

    or similar variants using:
      node / interface / peer / peer_interface
    """
    links = topology_data.get("links", [])
    if not isinstance(links, list):
        return []
    return [item for item in links if isinstance(item, dict)]


def normalize_interface_name(interface_name: str) -> str:
    """
    For now, convert physical et-* to channelized :1 if not already present.
    Adjust later if topology/facts already contain logical lane names.
    """
    name = (interface_name or "").strip()
    if not name:
        return name

    if ":" in name:
        return name

    if name.startswith("et-"):
        return f"{name}:1"

    return name


def build_fabric_interface_map(
    topology_data: Dict[str, Any],
    selected_nodes: List[str],
) -> Dict[str, List[str]]:
    selected = {normalize_node(node) for node in selected_nodes}
    result: Dict[str, Set[str]] = {normalize_node(node): set() for node in selected_nodes}

    for link in extract_topology_links(topology_data):
        local_node = normalize_node(
            link.get("local_node") or link.get("node") or link.get("device")
        )
        local_intf = (
            link.get("local_intf")
            or link.get("interface")
            or link.get("local_interface")
        )

        peer_node = normalize_node(
            link.get("peer_node") or link.get("peer") or link.get("remote_node")
        )
        peer_intf = (
            link.get("peer_intf")
            or link.get("peer_interface")
            or link.get("remote_interface")
        )

        if local_node in selected and local_intf:
            result.setdefault(local_node, set()).add(normalize_interface_name(local_intf))

        if peer_node in selected and peer_intf:
            result.setdefault(peer_node, set()).add(normalize_interface_name(peer_intf))

    return {
        node: sorted(list(interfaces))
        for node, interfaces in result.items()
        if interfaces
    }


def load_topology(topology_path: str) -> Dict[str, Any]:
    if not topology_path or not os.path.exists(topology_path):
        return {}
    return load_json_file(topology_path)


def resolve_interfaces_for_nodes(
    topology_path: str,
    selected_nodes: List[str],
) -> Dict[str, List[str]]:
    topology_data = load_topology(topology_path)
    if not topology_data:
        return {}
    return build_fabric_interface_map(topology_data=topology_data, selected_nodes=selected_nodes)

from typing import Dict, List, Optional


def resolve_recovery_interfaces_for_bounce(
    topology_path: str,
    selected_nodes: List[str],
    bounced_node: Optional[str] = None,
    bounced_interface: Optional[str] = None,
    node_host_map: Optional[Dict[str, Dict[str, str]]] = None,
    ssh_user: str = "root",
    device_facts_dir: str = os.path.join("artifacts", "device_facts"),
) -> Dict[str, List[str]]:
    """
    Recovery interface resolution policy:
    - bounced node: return all fabric-facing interfaces from prebuilt device facts
    - non-bounced nodes: return []
    - no runtime SSH / LLDP calls
    - preserve current return type to avoid collateral breakage
    """
    narrowed: Dict[str, List[str]] = {}

    bounced_node_n = normalize_node(bounced_node or "")
    bounced_interface = (bounced_interface or "").strip()

    for node in selected_nodes:
        narrowed[node] = []

        if not bounced_node_n or normalize_node(node) != bounced_node_n:
            continue

        related: List[str] = []

        try:
            facts = _load_device_facts_for_node(
                node=node,
                device_facts_dir=device_facts_dir,
            )

            lldp_output = facts.get("lldp_neighbors", "") or ""
            speed_map = facts.get("interface_speeds", {}) or {}

            related = _parse_lldp_local_interfaces_from_facts(lldp_output)
            related = _sort_interface_names(related)

            if bounced_interface:
                if bounced_interface not in related:
                    related.insert(0, bounced_interface)
                else:
                    related = [bounced_interface] + [x for x in related if x != bounced_interface]

            deduped: List[str] = []
            seen = set()
            for iface in related:
                if iface not in seen:
                    deduped.append(iface)
                    seen.add(iface)

            narrowed[node] = deduped

            print(
                f"[RECOVERY-IF-RESOLVE] node={node} "
                f"artifact_lldp_interfaces={narrowed[node]}"
            )

            for iface in narrowed[node]:
                print(
                    f"[RECOVERY-IF-RESOLVE] node={node} iface={iface} "
                    f"speed={speed_map.get(iface, 'UNKNOWN')}"
                )

        except Exception as exc:
            print(
                f"[RECOVERY-IF-RESOLVE] node={node} artifact-based recovery resolution failed: {exc}"
            )

            # safest fallback: still include bounced interface if present
            if bounced_interface:
                narrowed[node] = [bounced_interface]
                print(
                    f"[RECOVERY-IF-RESOLVE] node={node} fallback_to_bounced_interface="
                    f"{narrowed[node]}"
                )

    return narrowed


def is_related_recovery_interface(
    reference_interface: str,
    candidate_interface: str,
) -> bool:
    """
    Minimal safe heuristic for first version.

    Today:
    - keep interfaces of the same high-speed family (for example et-*)
    - exclude the exact same interface check handled by caller

    Later:
    - replace with exact ECMP-member discovery using richer topology metadata
    """
    if not reference_interface or not candidate_interface:
        return False

    ref_prefix = reference_interface.split("-")[0]
    cand_prefix = candidate_interface.split("-")[0]

    if ref_prefix != cand_prefix:
        return False

    return True
