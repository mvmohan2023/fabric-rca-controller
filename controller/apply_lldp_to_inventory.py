import json
import copy
from pathlib import Path

import yaml

from controller.config_loader import load_inventory


INVENTORY_FILE = Path("/root/fabric-controller/inventory/inventory.yaml")
TOPOLOGY_FILE = Path("/root/fabric-controller/artifacts/topology/discovered_topology.json")
OUTPUT_FILE = Path("/root/fabric-controller/inventory/inventory.lldp.yaml")
REPORT_FILE = Path("/root/fabric-controller/artifacts/reconciliation/inventory_lldp_patch_report.json")


def normalize_hostname(name: str) -> str:
    if not name:
        return ""
    name = name.split(".")[0].strip().lower()
    if name.endswith("-re0"):
        name = name[:-4]
    return name


def is_fabric_interface(ifname: str) -> bool:
    return ifname.startswith("et-")


def load_topology():
    if not TOPOLOGY_FILE.exists():
        raise FileNotFoundError(f"Topology file not found: {TOPOLOGY_FILE}")
    return json.loads(TOPOLOGY_FILE.read_text())


def build_hostname_to_node(inventory):
    mapping = {}
    for node_name, node_data in inventory["nodes"].items():
        hostname = normalize_hostname(node_data.get("hostname", ""))
        if hostname:
            mapping[hostname] = node_name
    return mapping


def dedup_links(discovered, hostname_to_node, inventory_nodes):
    dedup = {}
    for link in discovered.get("links", []):
        local_node = link.get("local_node", "")
        local_intf = link.get("local_interface", "")
        remote_raw = normalize_hostname(link.get("remote_node", ""))
        remote_intf = link.get("remote_interface", "")

        remote_node = hostname_to_node.get(remote_raw, remote_raw)

        if local_node not in inventory_nodes:
            continue
        if remote_node not in inventory_nodes:
            continue
        if not is_fabric_interface(local_intf):
            continue
        if not is_fabric_interface(remote_intf):
            continue

        key = tuple(sorted([
            f"{local_node}:{local_intf}",
            f"{remote_node}:{remote_intf}",
        ]))

        if key not in dedup:
            dedup[key] = {
                "a_node": local_node,
                "a_intf": local_intf,
                "b_node": remote_node,
                "b_intf": remote_intf,
            }

    return list(dedup.values())


def ensure_interface_exists(inv, node, intf):
    return node in inv["nodes"] and intf in inv["nodes"][node].get("interfaces", {})


def main():
    inventory = load_inventory(str(INVENTORY_FILE))
    discovered = load_topology()

    hostname_to_node = build_hostname_to_node(inventory)
    inventory_nodes = set(inventory["nodes"].keys())

    patched = copy.deepcopy(inventory)
    lldp_links = dedup_links(discovered, hostname_to_node, inventory_nodes)

    report = {
        "summary": {
            "lldp_links_considered": 0,
            "patched_interface_pairs": 0,
            "skipped_missing_interface": 0,
        },
        "patched_links": [],
        "skipped_links": [],
    }

    for link in lldp_links:
        a_node = link["a_node"]
        a_intf = link["a_intf"]
        b_node = link["b_node"]
        b_intf = link["b_intf"]

        report["summary"]["lldp_links_considered"] += 1

        a_exists = ensure_interface_exists(patched, a_node, a_intf)
        b_exists = ensure_interface_exists(patched, b_node, b_intf)

        if not a_exists or not b_exists:
            report["summary"]["skipped_missing_interface"] += 1
            report["skipped_links"].append({
                "a_node": a_node,
                "a_intf": a_intf,
                "b_node": b_node,
                "b_intf": b_intf,
                "reason": "interface missing in inventory"
            })
            continue

        patched["nodes"][a_node]["interfaces"][a_intf]["peer_device"] = b_node
        patched["nodes"][a_node]["interfaces"][a_intf]["peer_interface"] = b_intf

        patched["nodes"][b_node]["interfaces"][b_intf]["peer_device"] = a_node
        patched["nodes"][b_node]["interfaces"][b_intf]["peer_interface"] = a_intf

        report["summary"]["patched_interface_pairs"] += 1
        report["patched_links"].append({
            "a_node": a_node,
            "a_intf": a_intf,
            "b_node": b_node,
            "b_intf": b_intf,
        })

    OUTPUT_FILE.write_text(
        yaml.safe_dump(patched, sort_keys=False, default_flow_style=False)
    )

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2))

    print(f"Patched inventory written to: {OUTPUT_FILE}")
    print(f"Patch report written to     : {REPORT_FILE}")
    print("\nSUMMARY")
    for k, v in report["summary"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
