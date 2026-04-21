import json
from pathlib import Path
from ipaddress import ip_interface, IPv4Interface, IPv6Interface

from controller.config_loader import load_inventory


INVENTORY_FILE = Path("/root/fabric-controller/inventory/inventory.yaml")
TOPOLOGY_FILE = Path("/root/fabric-controller/artifacts/topology/discovered_topology.json")
OUTPUT_DIR = Path("/root/fabric-controller/artifacts/reconciliation")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def normalize_hostname(name: str) -> str:
    if not name:
        return ""
    name = name.split(".")[0].strip().lower()
    if name.endswith("-re0"):
        name = name[:-4]
    return name


def build_hostname_to_node(inventory):
    mapping = {}
    for node_name, node_data in inventory["nodes"].items():
        hostname = normalize_hostname(node_data.get("hostname", ""))
        if hostname:
            mapping[hostname] = node_name
    return mapping


def load_discovered_topology():
    if not TOPOLOGY_FILE.exists():
        raise FileNotFoundError(f"Missing topology file: {TOPOLOGY_FILE}")
    return json.loads(TOPOLOGY_FILE.read_text())


def parse_inventory_links(inventory):
    nodes = inventory["nodes"]
    subnet_map_v4 = {}
    subnet_map_v6 = {}

    for node_name, node_data in nodes.items():
        for intf_name, intf_data in node_data.get("interfaces", {}).items():
            ipv4 = intf_data.get("ipv4")
            ipv6 = intf_data.get("ipv6")

            if ipv4:
                iface = ip_interface(ipv4)
                if isinstance(iface, IPv4Interface):
                    subnet_map_v4.setdefault(str(iface.network), []).append(
                        (node_name, intf_name, str(iface.ip))
                    )

            if ipv6:
                iface6 = ip_interface(ipv6)
                if isinstance(iface6, IPv6Interface):
                    subnet_map_v6.setdefault(str(iface6.network), []).append(
                        (node_name, intf_name, str(iface6.ip))
                    )

    links = []
    seen = set()

    for subnet, members in subnet_map_v4.items():
        if len(members) == 2:
            a, b = members
            key = tuple(sorted([f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}", "ipv4"]))
            if key not in seen:
                seen.add(key)
                links.append({
                    "type": "ipv4",
                    "subnet": subnet,
                    "a_node": a[0],
                    "a_intf": a[1],
                    "b_node": b[0],
                    "b_intf": b[1],
                })

    for subnet, members in subnet_map_v6.items():
        if len(members) == 2:
            a, b = members
            key = tuple(sorted([f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}", "ipv6"]))
            if key not in seen:
                seen.add(key)
                links.append({
                    "type": "ipv6",
                    "subnet": subnet,
                    "a_node": a[0],
                    "a_intf": a[1],
                    "b_node": b[0],
                    "b_intf": b[1],
                })

    return links


def build_discovered_links(discovered, hostname_to_node):
    result = []
    seen = set()

    for link in discovered.get("links", []):
        local_node = link.get("local_node", "")
        local_intf = link.get("local_interface", "")
        remote_raw = normalize_hostname(link.get("remote_node", ""))
        remote_node = hostname_to_node.get(remote_raw, remote_raw)
        remote_intf = link.get("remote_interface", "")

        key = tuple(sorted([
            f"{local_node}:{local_intf}",
            f"{remote_node}:{remote_intf}"
        ]))

        if key not in seen:
            seen.add(key)
            result.append({
                "a_node": local_node,
                "a_intf": local_intf,
                "b_node": remote_node,
                "b_intf": remote_intf,
                "raw_remote": link.get("remote_node", ""),
            })

    return result


def key_from_link(a_node, a_intf, b_node, b_intf):
    return tuple(sorted([f"{a_node}:{a_intf}", f"{b_node}:{b_intf}"]))


def main():
    ensure_dir(OUTPUT_DIR)

    inventory = load_inventory(str(INVENTORY_FILE))
    discovered = load_discovered_topology()
    hostname_to_node = build_hostname_to_node(inventory)

    expected_links = parse_inventory_links(inventory)
    discovered_links = build_discovered_links(discovered, hostname_to_node)

    expected_map = {}
    for item in expected_links:
        k = key_from_link(item["a_node"], item["a_intf"], item["b_node"], item["b_intf"])
        expected_map[k] = item

    discovered_map = {}
    for item in discovered_links:
        k = key_from_link(item["a_node"], item["a_intf"], item["b_node"], item["b_intf"])
        discovered_map[k] = item

    matched = []
    missing = []
    extra = []

    for k, item in expected_map.items():
        if k in discovered_map:
            matched.append(item)
        else:
            missing.append(item)

    for k, item in discovered_map.items():
        if k not in expected_map:
            extra.append(item)

    report = {
        "summary": {
            "expected_links": len(expected_links),
            "discovered_links": len(discovered_links),
            "matched_links": len(matched),
            "missing_links": len(missing),
            "extra_links": len(extra),
        },
        "matched_links": matched,
        "missing_links": missing,
        "extra_links": extra,
    }

    json_out = OUTPUT_DIR / "inventory_reconciliation.json"
    txt_out = OUTPUT_DIR / "inventory_reconciliation.txt"

    json_out.write_text(json.dumps(report, indent=2))

    with open(txt_out, "w") as f:
        f.write("INVENTORY RECONCILIATION REPORT\n")
        f.write("==============================\n\n")

        f.write("SUMMARY\n")
        f.write("-------\n")
        for k, v in report["summary"].items():
            f.write(f"{k}: {v}\n")

        f.write("\nMISSING LINKS (in inventory but not discovered)\n")
        f.write("----------------------------------------------\n")
        if not missing:
            f.write("None\n")
        else:
            for item in missing:
                f.write(
                    f"{item['a_node']}:{item['a_intf']} <-> "
                    f"{item['b_node']}:{item['b_intf']} "
                    f"({item['type']} {item['subnet']})\n"
                )

        f.write("\nEXTRA DISCOVERED LINKS (discovered but not modeled in inventory)\n")
        f.write("---------------------------------------------------------------\n")
        if not extra:
            f.write("None\n")
        else:
            for item in extra:
                f.write(
                    f"{item['a_node']}:{item['a_intf']} <-> "
                    f"{item['b_node']}:{item['b_intf']}\n"
                )

    print(f"Reconciliation JSON report: {json_out}")
    print(f"Reconciliation text report: {txt_out}")
    print("\nSUMMARY")
    for k, v in report["summary"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
