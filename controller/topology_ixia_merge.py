# controller/topology_ixia_merge.py

import argparse
import json
import os
from typing import Any, Dict, List


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def build_hostname_to_alias_map(topology: Dict[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for node in topology.get("nodes", []):
        alias = node.get("node")
        hostname = node.get("hostname")
        if alias and hostname:
            result[hostname] = alias
    return result


def merge_ixia_links(topology: Dict[str, Any], ixia: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(topology)
    hostname_to_alias = build_hostname_to_alias_map(topology)

    external_links: List[Dict[str, Any]] = list(merged.get("external_links", []))

    for port in ixia.get("ports", []):
        switch_hostname = port.get("switch")
        switch_alias = hostname_to_alias.get(switch_hostname, switch_hostname)

        external_links.append(
            {
                "node": switch_alias,
                "hostname": switch_hostname,
                "interface": port.get("switch_interface"),
                "peer_type": "ixia",
                "peer_name": port.get("ixia_port"),
                "port_name": port.get("port_name"),
                "line_speed": port.get("line_speed"),
                "expected_link_state": port.get("expected_link_state"),
                "source": "ixia_inventory.json",
            }
        )

    merged["external_links"] = sorted(
        external_links,
        key=lambda x: ((x.get("node") or "").lower(), x.get("interface") or ""),
    )

    merged["ixia"] = {
        "api_helper_host": ixia.get("api_helper_host", {}),
        "ixnetwork_api_server": ixia.get("ixnetwork_api_server"),
        "total_external_links": len(external_links),
    }

    summary = dict(merged.get("summary", {}))
    summary["total_external_links"] = len(external_links)
    merged["summary"] = summary

    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge IXIA inventory into topology graph")
    parser.add_argument("--topology", required=True, help="Input topology_inventory.json")
    parser.add_argument("--ixia", required=True, help="Input ixia_inventory.json")
    parser.add_argument(
        "--output",
        default="artifacts/topology/topology_full.json",
        help="Output merged topology JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        topology = load_json(args.topology)
        ixia = load_json(args.ixia)

        merged = merge_ixia_links(topology=topology, ixia=ixia)
        write_json(args.output, merged)

        print(f"Merged topology JSON written: {args.output}")
        print("TOPOLOGY SUMMARY")
        print(f"  Nodes           : {merged.get('summary', {}).get('total_nodes')}")
        print(f"  Fabric links    : {merged.get('summary', {}).get('total_links')}")
        print(f"  External links  : {merged.get('summary', {}).get('total_external_links')}")
        print(f"  Dangling ifaces : {merged.get('summary', {}).get('total_dangling_interfaces')}")
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
