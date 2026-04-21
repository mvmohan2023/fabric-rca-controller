import json
from pathlib import Path
from ipaddress import ip_interface

from controller.config_loader import load_inventory


TOPOLOGY_FILE = Path("/root/fabric-controller/artifacts/topology/discovered_topology.json")
OUTPUT_DIR = Path("/root/fabric-controller/artifacts/validation")
INVENTORY_FILE = Path("/root/fabric-controller/inventory/inventory.active.yaml")

# Supported values: "ipv4", "ipv6", "dual-stack"
BGP_TRANSPORT = "ipv6"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_discovered_topology():
    if not TOPOLOGY_FILE.exists():
        raise FileNotFoundError(f"Discovered topology file not found: {TOPOLOGY_FILE}")
    with open(TOPOLOGY_FILE, "r") as f:
        return json.load(f)


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


def build_discovered_link_set(discovered, hostname_to_node):
    discovered_links = set()

    for link in discovered.get("links", []):
        local_node = link.get("local_node", "")
        local_intf = link.get("local_interface", "")
        remote_raw = normalize_hostname(link.get("remote_node", ""))
        remote_intf = link.get("remote_interface", "")

        remote_node = hostname_to_node.get(remote_raw, remote_raw)

        key = tuple(sorted([
            f"{local_node}:{local_intf}",
            f"{remote_node}:{remote_intf}"
        ]))
        discovered_links.add(key)

    return discovered_links


def parse_expected_physical_links(inventory):
    expected_links = []
    seen = set()

    for node_name, node_data in inventory["nodes"].items():
        for intf_name, intf_data in node_data.get("interfaces", {}).items():
            peer_device = intf_data.get("peer_device")
            peer_interface = intf_data.get("peer_interface")

            if not peer_device or not peer_interface:
                continue

            key = tuple(sorted([
                f"{node_name}:{intf_name}",
                f"{peer_device}:{peer_interface}"
            ]))

            if key in seen:
                continue

            seen.add(key)
            expected_links.append({
                "a_node": node_name,
                "a_intf": intf_name,
                "b_node": peer_device,
                "b_intf": peer_interface,
            })

    return expected_links


def validate_physical_links(expected_links, discovered_link_set):
    results = []

    for link in expected_links:
        key = tuple(sorted([
            f"{link['a_node']}:{link['a_intf']}",
            f"{link['b_node']}:{link['b_intf']}"
        ]))

        results.append({
            "a_node": link["a_node"],
            "a_intf": link["a_intf"],
            "b_node": link["b_node"],
            "b_intf": link["b_intf"],
            "status": "present" if key in discovered_link_set else "missing"
        })

    return results


def safe_ip_interface(value):
    if not value:
        return None
    try:
        return ip_interface(value)
    except Exception:
        return None


def validate_ip_consistency(inventory, expected_links):
    results = []

    for link in expected_links:
        a_data = inventory["nodes"][link["a_node"]]["interfaces"].get(link["a_intf"], {})
        b_data = inventory["nodes"][link["b_node"]]["interfaces"].get(link["b_intf"], {})

        a_v4 = safe_ip_interface(a_data.get("ipv4"))
        b_v4 = safe_ip_interface(b_data.get("ipv4"))
        a_v6 = safe_ip_interface(a_data.get("ipv6"))
        b_v6 = safe_ip_interface(b_data.get("ipv6"))

        if a_v4 or b_v4:
            if a_v4 and b_v4:
                v4_status = "match" if a_v4.network == b_v4.network else "mismatch"
            else:
                v4_status = "partial"
        else:
            v4_status = "absent"

        if a_v6 or b_v6:
            if a_v6 and b_v6:
                v6_status = "match" if a_v6.network == b_v6.network else "mismatch"
            else:
                v6_status = "partial"
        else:
            v6_status = "absent"

        results.append({
            "a_node": link["a_node"],
            "a_intf": link["a_intf"],
            "a_ipv4": str(a_v4) if a_v4 else None,
            "a_ipv6": str(a_v6) if a_v6 else None,
            "b_node": link["b_node"],
            "b_intf": link["b_intf"],
            "b_ipv4": str(b_v4) if b_v4 else None,
            "b_ipv6": str(b_v6) if b_v6 else None,
            "ipv4_status": v4_status,
            "ipv6_status": v6_status,
        })

    return results


def build_expected_bgp_sessions_from_links(inventory, expected_links, bgp_transport="ipv6"):
    sessions = []

    for link in expected_links:
        a_node = link["a_node"]
        b_node = link["b_node"]
        a_intf = link["a_intf"]
        b_intf = link["b_intf"]

        a_node_data = inventory["nodes"][a_node]
        b_node_data = inventory["nodes"][b_node]

        a_if = a_node_data["interfaces"].get(a_intf, {})
        b_if = b_node_data["interfaces"].get(b_intf, {})

        a_as = a_node_data.get("asn")
        b_as = b_node_data.get("asn")

        a_v4 = safe_ip_interface(a_if.get("ipv4"))
        b_v4 = safe_ip_interface(b_if.get("ipv4"))
        a_v6 = safe_ip_interface(a_if.get("ipv6"))
        b_v6 = safe_ip_interface(b_if.get("ipv6"))

        if bgp_transport in ("ipv4", "dual-stack") and a_v4 and b_v4:
            sessions.append({
                "node": a_node,
                "peer_ip": str(b_v4.ip),
                "peer_as": b_as,
                "subnet_type": "ipv4",
                "local_intf": a_intf,
                "remote_intf": b_intf,
            })
            sessions.append({
                "node": b_node,
                "peer_ip": str(a_v4.ip),
                "peer_as": a_as,
                "subnet_type": "ipv4",
                "local_intf": b_intf,
                "remote_intf": a_intf,
            })

        if bgp_transport in ("ipv6", "dual-stack") and a_v6 and b_v6:
            sessions.append({
                "node": a_node,
                "peer_ip": str(b_v6.ip),
                "peer_as": b_as,
                "subnet_type": "ipv6",
                "local_intf": a_intf,
                "remote_intf": b_intf,
            })
            sessions.append({
                "node": b_node,
                "peer_ip": str(a_v6.ip),
                "peer_as": a_as,
                "subnet_type": "ipv6",
                "local_intf": b_intf,
                "remote_intf": a_intf,
            })

    return sessions


def build_discovered_bgp_map(discovered):
    bgp_map = {}
    for peer in discovered.get("bgp_peers", []):
        key = (peer.get("node"), str(peer.get("peer_ip")), int(peer.get("peer_as")))
        bgp_map[key] = peer.get("state")
    return bgp_map


def validate_bgp(expected_sessions, discovered_bgp_map):
    results = []

    for sess in expected_sessions:
        key = (sess["node"], str(sess["peer_ip"]), int(sess["peer_as"]))
        state = discovered_bgp_map.get(key)

        if state is None:
            status = "missing"
        elif state == "Establ":
            status = "up"
        else:
            status = f"down({state})"

        results.append({
            "node": sess["node"],
            "peer_ip": sess["peer_ip"],
            "peer_as": sess["peer_as"],
            "subnet_type": sess["subnet_type"],
            "local_intf": sess["local_intf"],
            "remote_intf": sess["remote_intf"],
            "status": status,
        })

    return results


def summarize(link_results, ip_results, bgp_results):
    link_present = sum(1 for x in link_results if x["status"] == "present")
    link_missing = sum(1 for x in link_results if x["status"] == "missing")

    ipv4_match = sum(1 for x in ip_results if x["ipv4_status"] == "match")
    ipv4_mismatch = sum(1 for x in ip_results if x["ipv4_status"] == "mismatch")
    ipv4_partial = sum(1 for x in ip_results if x["ipv4_status"] == "partial")

    ipv6_match = sum(1 for x in ip_results if x["ipv6_status"] == "match")
    ipv6_mismatch = sum(1 for x in ip_results if x["ipv6_status"] == "mismatch")
    ipv6_partial = sum(1 for x in ip_results if x["ipv6_status"] == "partial")

    bgp_up = sum(1 for x in bgp_results if x["status"] == "up")
    bgp_down = sum(1 for x in bgp_results if x["status"].startswith("down("))
    bgp_missing = sum(1 for x in bgp_results if x["status"] == "missing")

    return {
        "physical_links": {
            "present": link_present,
            "missing": link_missing,
            "total_expected": len(link_results),
        },
        "ip_consistency": {
            "ipv4_match": ipv4_match,
            "ipv4_mismatch": ipv4_mismatch,
            "ipv4_partial": ipv4_partial,
            "ipv6_match": ipv6_match,
            "ipv6_mismatch": ipv6_mismatch,
            "ipv6_partial": ipv6_partial,
            "total_links_checked": len(ip_results),
        },
        "bgp": {
            "up": bgp_up,
            "down": bgp_down,
            "missing": bgp_missing,
            "total_expected": len(bgp_results),
        }
    }


def write_text_report(summary, link_results, ip_results, bgp_results, outfile: Path):
    with open(outfile, "w") as f:
        f.write("FABRIC VALIDATION REPORT\n")
        f.write("========================\n\n")

        f.write("PHYSICAL LINK SUMMARY\n")
        f.write("---------------------\n")
        f.write(f"Expected links : {summary['physical_links']['total_expected']}\n")
        f.write(f"Present links  : {summary['physical_links']['present']}\n")
        f.write(f"Missing links  : {summary['physical_links']['missing']}\n\n")

        f.write("IP CONSISTENCY SUMMARY\n")
        f.write("----------------------\n")
        f.write(f"IPv4 match     : {summary['ip_consistency']['ipv4_match']}\n")
        f.write(f"IPv4 mismatch  : {summary['ip_consistency']['ipv4_mismatch']}\n")
        f.write(f"IPv4 partial   : {summary['ip_consistency']['ipv4_partial']}\n")
        f.write(f"IPv6 match     : {summary['ip_consistency']['ipv6_match']}\n")
        f.write(f"IPv6 mismatch  : {summary['ip_consistency']['ipv6_mismatch']}\n")
        f.write(f"IPv6 partial   : {summary['ip_consistency']['ipv6_partial']}\n\n")

        f.write("BGP SUMMARY\n")
        f.write("-----------\n")
        f.write(f"Expected sessions : {summary['bgp']['total_expected']}\n")
        f.write(f"Up sessions       : {summary['bgp']['up']}\n")
        f.write(f"Down sessions     : {summary['bgp']['down']}\n")
        f.write(f"Missing sessions  : {summary['bgp']['missing']}\n\n")

        f.write("MISSING PHYSICAL LINKS\n")
        f.write("----------------------\n")
        missing_links = [x for x in link_results if x["status"] == "missing"]
        if not missing_links:
            f.write("None\n")
        else:
            for item in missing_links:
                f.write(f"{item['a_node']}:{item['a_intf']} <-> {item['b_node']}:{item['b_intf']}\n")

        f.write("\nIP MISMATCHES\n")
        f.write("-------------\n")
        mismatches = [
            x for x in ip_results
            if x["ipv4_status"] == "mismatch" or x["ipv6_status"] == "mismatch"
        ]
        if not mismatches:
            f.write("None\n")
        else:
            for item in mismatches:
                f.write(
                    f"{item['a_node']}:{item['a_intf']} <-> {item['b_node']}:{item['b_intf']} | "
                    f"IPv4={item['ipv4_status']} IPv6={item['ipv6_status']}\n"
                )

        f.write("\nBGP NOT UP\n")
        f.write("----------\n")
        not_up = [x for x in bgp_results if x["status"] != "up"]
        if not not_up:
            f.write("None\n")
        else:
            for item in not_up:
                f.write(
                    f"{item['node']} -> {item['peer_ip']} AS{item['peer_as']} "
                    f"[{item['subnet_type']}] {item['local_intf']}->{item['remote_intf']} : {item['status']}\n"
                )


def main():
    ensure_dir(OUTPUT_DIR)

    inventory = load_inventory(str(INVENTORY_FILE))
    discovered = load_discovered_topology()

    hostname_to_node = build_hostname_to_node(inventory)
    discovered_link_set = build_discovered_link_set(discovered, hostname_to_node)

    expected_links = parse_expected_physical_links(inventory)
    link_results = validate_physical_links(expected_links, discovered_link_set)
    ip_results = validate_ip_consistency(inventory, expected_links)

    expected_bgp = build_expected_bgp_sessions_from_links(
        inventory,
        expected_links,
        bgp_transport=BGP_TRANSPORT,
    )
    discovered_bgp_map = build_discovered_bgp_map(discovered)
    bgp_results = validate_bgp(expected_bgp, discovered_bgp_map)

    summary = summarize(link_results, ip_results, bgp_results)

    json_report = {
        "summary": summary,
        "link_results": link_results,
        "ip_results": ip_results,
        "bgp_results": bgp_results,
    }

    json_out = OUTPUT_DIR / "fabric_validation_report.json"
    txt_out = OUTPUT_DIR / "fabric_validation_report.txt"

    with open(json_out, "w") as f:
        json.dump(json_report, f, indent=2)

    write_text_report(summary, link_results, ip_results, bgp_results, txt_out)

    print(f"Validation JSON report : {json_out}")
    print(f"Validation text report : {txt_out}")
    print("\nSUMMARY")
    print(
        f"  Physical Links - expected: {summary['physical_links']['total_expected']}, "
        f"present: {summary['physical_links']['present']}, "
        f"missing: {summary['physical_links']['missing']}"
    )
    print(
        f"  IP Consistency - IPv4 match: {summary['ip_consistency']['ipv4_match']}, "
        f"IPv4 mismatch: {summary['ip_consistency']['ipv4_mismatch']}, "
        f"IPv6 match: {summary['ip_consistency']['ipv6_match']}, "
        f"IPv6 mismatch: {summary['ip_consistency']['ipv6_mismatch']}"
    )
    print(
        f"  BGP - expected: {summary['bgp']['total_expected']}, "
        f"up: {summary['bgp']['up']}, "
        f"down: {summary['bgp']['down']}, "
        f"missing: {summary['bgp']['missing']}"
    )


if __name__ == "__main__":
    main()
