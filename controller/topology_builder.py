# controller/topology_builder.py

import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import yaml


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def normalize_name(value: str) -> str:
    return (value or "").strip().lower()


def link_key(a_node: str, a_intf: str, b_node: str, b_intf: str) -> Tuple[str, str, str, str]:
    left = (normalize_name(a_node), a_intf or "")
    right = (normalize_name(b_node), b_intf or "")
    return (*left, *right) if left <= right else (*right, *left)


def build_topology_from_inventory(data: Dict[str, Any]) -> Dict[str, Any]:
    nodes_data = data.get("nodes", {}) or {}

    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    dangling_interfaces: List[Dict[str, Any]] = []

    seen_links = set()

    for node_name, node_info in nodes_data.items():
        hostname = node_info.get("hostname")
        mgmt_ip = node_info.get("mgmt_ip")
        role = node_info.get("role")
        platform = node_info.get("platform")
        asn = node_info.get("asn")
        router_id = node_info.get("router_id")

        nodes.append(
            {
                "node": node_name,
                "hostname": hostname,
                "mgmt_ip": mgmt_ip,
                "role": role,
                "platform": platform,
                "asn": asn,
                "router_id": router_id,
            }
        )

        interfaces = node_info.get("interfaces", {}) or {}
        for intf_name, intf_info in interfaces.items():
            peer_device = intf_info.get("peer_device")
            peer_interface = intf_info.get("peer_interface")

            if peer_device and peer_interface:
                key = link_key(node_name, intf_name, peer_device, peer_interface)
                if key in seen_links:
                    continue
                seen_links.add(key)

                links.append(
                    {
                        "local_node": node_name,
                        "local_intf": intf_name,
                        "peer_node": peer_device,
                        "peer_intf": peer_interface,
                        "link_type": "fabric",
                        "source": "inventory.active.yaml",
                        "local_ipv4": intf_info.get("ipv4"),
                        "local_ipv6": intf_info.get("ipv6"),
                    }
                )
            else:
                dangling_interfaces.append(
                    {
                        "node": node_name,
                        "interface": intf_name,
                        "ipv4": intf_info.get("ipv4"),
                        "ipv6": intf_info.get("ipv6"),
                        "reason": "no_peer_mapping",
                    }
                )

    return {
        "lab": data.get("lab", {}),
        "defaults": data.get("defaults", {}),
        "nodes": sorted(nodes, key=lambda x: x["node"]),
        "links": sorted(
            links,
            key=lambda x: (normalize_name(x["local_node"]), x["local_intf"], normalize_name(x["peer_node"]), x["peer_intf"]),
        ),
        "dangling_interfaces": sorted(
            dangling_interfaces,
            key=lambda x: (normalize_name(x["node"]), x["interface"]),
        ),
        "summary": {
            "total_nodes": len(nodes),
            "total_links": len(links),
            "total_dangling_interfaces": len(dangling_interfaces),
        },
    }


def build_alias_maps(topology: Dict[str, Any]) -> Dict[str, Any]:
    alias_to_hostname = {}
    hostname_to_alias = {}
    alias_to_mgmt_ip = {}

    for node in topology.get("nodes", []):
        alias = node.get("node")
        hostname = node.get("hostname")
        mgmt_ip = node.get("mgmt_ip")

        if alias:
            alias_to_hostname[alias] = hostname
            alias_to_mgmt_ip[alias] = mgmt_ip
        if hostname:
            hostname_to_alias[hostname] = alias

    return {
        "alias_to_hostname": alias_to_hostname,
        "hostname_to_alias": hostname_to_alias,
        "alias_to_mgmt_ip": alias_to_mgmt_ip,
    }


def write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build topology graph from inventory.active.yaml")
    parser.add_argument("--input", required=True, help="Path to inventory.active.yaml")
    parser.add_argument(
        "--output",
        default="artifacts/topology/topology_inventory.json",
        help="Output topology JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        data = load_yaml(args.input)
        topology = build_topology_from_inventory(data)
        topology["alias_maps"] = build_alias_maps(topology)
        write_json(args.output, topology)

        print(f"Topology JSON written: {args.output}")
        print("TOPOLOGY SUMMARY")
        print(f"  Nodes               : {topology['summary']['total_nodes']}")
        print(f"  Fabric links        : {topology['summary']['total_links']}")
        print(f"  Dangling interfaces : {topology['summary']['total_dangling_interfaces']}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
