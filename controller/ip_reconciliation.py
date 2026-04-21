import json
import re
from pathlib import Path
from ipaddress import ip_interface

from controller.config_loader import load_inventory


INVENTORY_FILE = Path("/root/fabric-controller/inventory/inventory.active.yaml")
FACTS_DIR = Path("/root/fabric-controller/artifacts/device_facts")
OUTPUT_DIR = Path("/root/fabric-controller/artifacts/reconciliation")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path):
    with open(path, "r") as f:
        return json.load(f)


def parse_interfaces_terse(text: str):
    """
    Parse 'show interfaces terse | no-more'
    Return:
      {
        "et-0/0/20:0": {
            "ipv4": "1.0.13.5/31",
            "ipv6": "2001::1:0:13:5/127"
        },
        ...
      }
    """
    interfaces = {}
    current_intf = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        # start of interface block
        m = re.match(r"^([a-zA-Z0-9:\-\/\.]+)\s+\S+\s+\S+(?:\s+\S+)?(?:\s+(.*))?$", line)
        if m and not line.strip().startswith(("inet ", "inet6 ", "multiservice", "iso ")):
            first = m.group(1)
            if first.endswith(".0"):
                base = first[:-2]
                current_intf = base
                interfaces.setdefault(current_intf, {})
                proto_tail = m.group(2) or ""
                if "inet " in line:
                    addr_match = re.search(r"inet\s+([0-9\.]+/\d+)", line)
                    if addr_match:
                        interfaces[current_intf]["ipv4"] = addr_match.group(1)
                if "inet6 " in line:
                    addr6_match = re.search(r"inet6\s+([0-9a-fA-F:]+/\d+)", line)
                    if addr6_match:
                        interfaces[current_intf]["ipv6"] = addr6_match.group(1)
            else:
                current_intf = first
                interfaces.setdefault(current_intf, {})
            continue

        if current_intf:
            v4 = re.search(r"\binet\s+([0-9\.]+/\d+)", line)
            if v4:
                interfaces[current_intf]["ipv4"] = v4.group(1)

            v6 = re.search(r"\binet6\s+([0-9a-fA-F:]+/\d+)", line)
            if v6:
                interfaces[current_intf]["ipv6"] = v6.group(1)

    return interfaces


def load_live_interface_data(inventory):
    live = {}

    for node_name in inventory["nodes"]:
        facts_file = FACTS_DIR / f"{node_name}_facts.json"
        if not facts_file.exists():
            continue

        facts = load_json(facts_file)
        terse_text = facts.get("interfaces_terse", "")
        live[node_name] = parse_interfaces_terse(terse_text)

    return live


def networks_match(addr1, addr2):
    if not addr1 or not addr2:
        return False
    try:
        return ip_interface(addr1).network == ip_interface(addr2).network
    except Exception:
        return False


def reconcile_links(inventory, live):
    results = []

    for node_name, node_data in inventory["nodes"].items():
        for intf_name, intf_data in node_data.get("interfaces", {}).items():
            peer_device = intf_data.get("peer_device")
            peer_interface = intf_data.get("peer_interface")

            if not peer_device or not peer_interface:
                continue

            # avoid duplicates by ordering
            if node_name > peer_device:
                continue
            if node_name == peer_device and intf_name > peer_interface:
                continue

            local_cfg = intf_data
            peer_cfg = inventory["nodes"].get(peer_device, {}).get("interfaces", {}).get(peer_interface, {})

            local_live = live.get(node_name, {}).get(intf_name, {})
            peer_live = live.get(peer_device, {}).get(peer_interface, {})

            cfg_v4_match = networks_match(local_cfg.get("ipv4"), peer_cfg.get("ipv4"))
            cfg_v6_match = networks_match(local_cfg.get("ipv6"), peer_cfg.get("ipv6"))

            live_v4_match = networks_match(local_live.get("ipv4"), peer_live.get("ipv4"))
            live_v6_match = networks_match(local_live.get("ipv6"), peer_live.get("ipv6"))

            results.append({
                "a_node": node_name,
                "a_intf": intf_name,
                "b_node": peer_device,
                "b_intf": peer_interface,

                "cfg_a_ipv4": local_cfg.get("ipv4"),
                "cfg_b_ipv4": peer_cfg.get("ipv4"),
                "cfg_a_ipv6": local_cfg.get("ipv6"),
                "cfg_b_ipv6": peer_cfg.get("ipv6"),

                "live_a_ipv4": local_live.get("ipv4"),
                "live_b_ipv4": peer_live.get("ipv4"),
                "live_a_ipv6": local_live.get("ipv6"),
                "live_b_ipv6": peer_live.get("ipv6"),

                "cfg_ipv4_match": cfg_v4_match,
                "cfg_ipv6_match": cfg_v6_match,
                "live_ipv4_match": live_v4_match,
                "live_ipv6_match": live_v6_match,
            })

    return results


def summarize(results):
    return {
        "total_links_checked": len(results),
        "cfg_ipv4_match": sum(1 for x in results if x["cfg_ipv4_match"]),
        "cfg_ipv4_mismatch": sum(1 for x in results if not x["cfg_ipv4_match"]),
        "cfg_ipv6_match": sum(1 for x in results if x["cfg_ipv6_match"]),
        "cfg_ipv6_mismatch": sum(1 for x in results if not x["cfg_ipv6_match"]),
        "live_ipv4_match": sum(1 for x in results if x["live_ipv4_match"]),
        "live_ipv4_mismatch": sum(1 for x in results if not x["live_ipv4_match"]),
        "live_ipv6_match": sum(1 for x in results if x["live_ipv6_match"]),
        "live_ipv6_mismatch": sum(1 for x in results if not x["live_ipv6_match"]),
    }


def write_text_report(summary, results, outfile: Path):
    with open(outfile, "w") as f:
        f.write("IP RECONCILIATION REPORT\n")
        f.write("========================\n\n")

        for k, v in summary.items():
            f.write(f"{k}: {v}\n")

        f.write("\nLINK DETAILS\n")
        f.write("------------\n")
        for item in results:
            f.write(
                f"{item['a_node']}:{item['a_intf']} <-> {item['b_node']}:{item['b_intf']}\n"
                f"  CFG  IPv4: {item['cfg_a_ipv4']} <-> {item['cfg_b_ipv4']}  match={item['cfg_ipv4_match']}\n"
                f"  CFG  IPv6: {item['cfg_a_ipv6']} <-> {item['cfg_b_ipv6']}  match={item['cfg_ipv6_match']}\n"
                f"  LIVE IPv4: {item['live_a_ipv4']} <-> {item['live_b_ipv4']}  match={item['live_ipv4_match']}\n"
                f"  LIVE IPv6: {item['live_a_ipv6']} <-> {item['live_b_ipv6']}  match={item['live_ipv6_match']}\n\n"
            )


def main():
    ensure_dir(OUTPUT_DIR)

    inventory = load_inventory(str(INVENTORY_FILE))
    live = load_live_interface_data(inventory)

    results = reconcile_links(inventory, live)
    summary = summarize(results)

    json_out = OUTPUT_DIR / "ip_reconciliation_report.json"
    txt_out = OUTPUT_DIR / "ip_reconciliation_report.txt"

    with open(json_out, "w") as f:
        json.dump({
            "summary": summary,
            "results": results,
        }, f, indent=2)

    write_text_report(summary, results, txt_out)

    print(f"IP reconciliation JSON report: {json_out}")
    print(f"IP reconciliation text report: {txt_out}")
    print("\nSUMMARY")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
