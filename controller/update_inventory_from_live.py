import json
import re
from pathlib import Path
from copy import deepcopy

import yaml


INPUT_INVENTORY = Path("/root/fabric-controller/inventory/inventory.lldp.yaml")
FACTS_DIR = Path("/root/fabric-controller/artifacts/device_facts")
OUTPUT_INVENTORY = Path("/root/fabric-controller/inventory/final_inventory.yaml")
REPORT_DIR = Path("/root/fabric-controller/artifacts/reconciliation")
JSON_REPORT = REPORT_DIR / "update_inventory_from_live_report.json"
TXT_REPORT = REPORT_DIR / "update_inventory_from_live_report.txt"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, data):
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with open(path, "r") as f:
        return json.load(f)


def normalize_node_name(name: str) -> str:
    return (name or "").strip().lower()


def parse_interfaces_terse(output: str):
    """
    Parse 'show interfaces terse | no-more' output.

    Returns:
        {
          "et-0/0/20:0": {
              "ipv4": "1.0.13.4/31",
              "ipv6": "2001::1:0:13:4/127"
          },
          ...
        }
    """
    results = {}
    current_intf = None

    if not output:
        return results

    lines = output.splitlines()

    for raw_line in lines:
        line = raw_line.rstrip()

        if not line.strip():
            continue

        # top-level interface lines
        if not line.startswith(" ") and not line.startswith("\t"):
            # Example:
            # et-0/0/20:0.0           up    up   inet     1.0.13.4/31
            # et-0/0/20:0             up    up
            m = re.match(r"^(\S+)\s+\S+\s+\S+(?:\s+(\S+)\s+(\S+))?", line)
            if not m:
                current_intf = None
                continue

            full_if = m.group(1)
            proto = m.group(2)
            addr = m.group(3)

            # strip unit .0 if present
            if "." in full_if:
                base_if = full_if.split(".")[0]
            else:
                base_if = full_if

            if base_if not in results:
                results[base_if] = {}

            current_intf = base_if

            if proto == "inet" and addr:
                results[base_if]["ipv4"] = addr
            elif proto == "inet6" and addr and not addr.startswith("fe80::"):
                results[base_if]["ipv6"] = addr

            continue

        # indented continuation lines
        if current_intf:
            stripped = line.strip()

            m4 = re.match(r"^inet\s+(\S+)", stripped)
            if m4:
                results[current_intf]["ipv4"] = m4.group(1)
                continue

            m6 = re.match(r"^inet6\s+(\S+)", stripped)
            if m6:
                addr6 = m6.group(1)
                if not addr6.startswith("fe80::"):
                    results[current_intf]["ipv6"] = addr6
                continue

    return results


def build_live_interface_db():
    """
    Returns:
        {
          "spine1": {
              "et-0/0/20:0": {"ipv4": "...", "ipv6": "..."},
              ...
          },
          ...
        }
    """
    db = {}

    if not FACTS_DIR.exists():
        raise FileNotFoundError(f"Facts directory not found: {FACTS_DIR}")

    for facts_file in sorted(FACTS_DIR.glob("*_facts.json")):
        node_name = facts_file.stem.replace("_facts", "")
        facts = load_json(facts_file)
        terse = facts.get("interfaces_terse", "")
        db[node_name] = parse_interfaces_terse(terse)

    return db


def update_inventory_with_live(inventory, live_db):
    updated = deepcopy(inventory)
    changes = []
    missing_live_nodes = []
    missing_live_interfaces = []

    for node_name, node_data in updated.get("nodes", {}).items():
        node_live = live_db.get(node_name)
        if node_live is None:
            missing_live_nodes.append(node_name)
            continue

        interfaces = node_data.get("interfaces", {})
        for ifname, ifdata in interfaces.items():
            live_if = node_live.get(ifname)
            if live_if is None:
                missing_live_interfaces.append({
                    "node": node_name,
                    "interface": ifname,
                })
                continue

            old_ipv4 = ifdata.get("ipv4")
            old_ipv6 = ifdata.get("ipv6")
            new_ipv4 = live_if.get("ipv4")
            new_ipv6 = live_if.get("ipv6")

            changed = False

            if new_ipv4 and old_ipv4 != new_ipv4:
                ifdata["ipv4"] = new_ipv4
                changed = True

            if new_ipv6 and old_ipv6 != new_ipv6:
                ifdata["ipv6"] = new_ipv6
                changed = True

            if changed:
                changes.append({
                    "node": node_name,
                    "interface": ifname,
                    "old_ipv4": old_ipv4,
                    "new_ipv4": ifdata.get("ipv4"),
                    "old_ipv6": old_ipv6,
                    "new_ipv6": ifdata.get("ipv6"),
                })

    return updated, changes, missing_live_nodes, missing_live_interfaces


def write_text_report(changes, missing_live_nodes, missing_live_interfaces):
    with open(TXT_REPORT, "w") as f:
        f.write("UPDATE INVENTORY FROM LIVE REPORT\n")
        f.write("=================================\n\n")

        f.write("SUMMARY\n")
        f.write("-------\n")
        f.write(f"Nodes missing live facts      : {len(missing_live_nodes)}\n")
        f.write(f"Interfaces missing live facts : {len(missing_live_interfaces)}\n")
        f.write(f"Interfaces updated            : {len(changes)}\n\n")

        f.write("UPDATED INTERFACES\n")
        f.write("------------------\n")
        if not changes:
            f.write("None\n")
        else:
            for c in changes:
                f.write(
                    f"{c['node']} {c['interface']}: "
                    f"IPv4 {c['old_ipv4']} -> {c['new_ipv4']}, "
                    f"IPv6 {c['old_ipv6']} -> {c['new_ipv6']}\n"
                )

        f.write("\nNODES MISSING LIVE FACTS\n")
        f.write("------------------------\n")
        if not missing_live_nodes:
            f.write("None\n")
        else:
            for node in missing_live_nodes:
                f.write(f"{node}\n")

        f.write("\nINTERFACES MISSING LIVE FACTS\n")
        f.write("-----------------------------\n")
        if not missing_live_interfaces:
            f.write("None\n")
        else:
            for item in missing_live_interfaces:
                f.write(f"{item['node']} {item['interface']}\n")


def main():
    ensure_dir(REPORT_DIR)

    inventory = load_yaml(INPUT_INVENTORY)
    live_db = build_live_interface_db()

    updated_inventory, changes, missing_live_nodes, missing_live_interfaces = update_inventory_with_live(
        inventory, live_db
    )

    write_yaml(OUTPUT_INVENTORY, updated_inventory)

    report = {
        "summary": {
            "nodes_missing_live_facts": len(missing_live_nodes),
            "interfaces_missing_live_facts": len(missing_live_interfaces),
            "interfaces_updated": len(changes),
        },
        "changes": changes,
        "missing_live_nodes": missing_live_nodes,
        "missing_live_interfaces": missing_live_interfaces,
    }

    with open(JSON_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    write_text_report(changes, missing_live_nodes, missing_live_interfaces)

    print(f"Updated inventory written to : {OUTPUT_INVENTORY}")
    print(f"JSON report written to       : {JSON_REPORT}")
    print(f"Text report written to       : {TXT_REPORT}")
    print("\nSUMMARY")
    print(f"  nodes_missing_live_facts      : {len(missing_live_nodes)}")
    print(f"  interfaces_missing_live_facts : {len(missing_live_interfaces)}")
    print(f"  interfaces_updated            : {len(changes)}")


if __name__ == "__main__":
    main()
