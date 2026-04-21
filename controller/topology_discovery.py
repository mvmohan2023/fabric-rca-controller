import os
import re
import json
from pathlib import Path


FACTS_DIR = Path("/root/fabric-controller/artifacts/device_facts")
OUTPUT_DIR = Path("/root/fabric-controller/artifacts/topology")

import re

def deduplicate_bgp_peers(peers):
    seen = set()
    result = []

    for peer in peers:
        key = (
            peer.get("node"),
            peer.get("peer_ip"),
            int(peer.get("peer_as")),
            peer.get("state"),
        )
        if key not in seen:
            seen.add(key)
            result.append(peer)

    return result

def build_discovered_topology(device_facts):
    topology = {
        "nodes": {},
        "links": [],
        "bgp_peers": [],
    }

    for node_name, facts in device_facts.items():
        topology["nodes"][node_name] = {
            "hostname": facts.get("hostname_expected") or facts.get("node_name") or node_name,
            "role": facts.get("role", ""),
            "platform": facts.get("platform", ""),
            "mgmt_ip": facts.get("mgmt_ip", ""),
        }

        # LLDP parsing
        lldp_text = facts.get("lldp_neighbors", "")
        topology["links"].extend(parse_lldp_neighbors(node_name, lldp_text))

        # BGP parsing
        bgp_text = facts.get("bgp_summary", "")
        topology["bgp_peers"].extend(parse_bgp_summary(node_name, bgp_text))

    return topology


def parse_bgp_summary(node_name: str, bgp_text: str):
    """
    Parse 'show bgp summary' output and return discovered BGP peers.

    Expected output entries like:
      2001::1:0:13:5   4200000013  ... Establ
      1.0.11.1         4200000011  ... Establ
      2.201.0.1        4200000201  ... Establ

    Returns:
        List[dict]
    """
    peers = []

    if not bgp_text:
        return peers

    for raw_line in bgp_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Skip non-peer lines
        if line.startswith("Warning:"):
            continue
        if line.startswith("Threading mode:"):
            continue
        if line.startswith("Default eBGP mode:"):
            continue
        if line.startswith("Groups:"):
            continue
        if line.startswith("Table"):
            continue
        if line.startswith("Peer"):
            continue
        if line.startswith("inet.0:"):
            continue
        if line.startswith("inet6.0:"):
            continue
        if line.startswith("bgp."):
            continue
        if line.startswith("Restart Complete"):
            continue

        # Match peer summary line
        #
        # Example:
        # 2001::1:0:13:5   4200000013      12345  67890  0  1  1w2d Establ
        # 1.0.11.1         4200000011      12345  67890  0  1  1w2d Establ
        #
        m = re.match(
            r"^(?P<peer>\S+)\s+"
            r"(?P<asn>\d+)\s+"
            r"\d+\s+\d+\s+\d+\s+\d+\s+"
            r".*?\s+"
            r"(?P<state>Establ|Idle|Active|Connect|OpenSent|OpenConfirm)$",
            line,
        )

        if not m:
            # Some Junos lines may contain state plus route counts on same line
            # Example:
            # 1.1.1.1 65001 ... Establ
            # or:
            # 1.1.1.1 65001 ... Connect
            tokens = line.split()
            if len(tokens) < 3:
                continue

            peer_ip = tokens[0]
            asn_token = tokens[1]
            state_token = tokens[-1]

            if not re.match(r"^\d+$", asn_token):
                continue

            if state_token not in {"Establ", "Idle", "Active", "Connect", "OpenSent", "OpenConfirm"}:
                continue

            peers.append(
                {
                    "node": node_name,
                    "peer_ip": peer_ip,
                    "peer_as": int(asn_token),
                    "state": state_token,
                }
            )
            continue

        peers.append(
            {
                "node": node_name,
                "peer_ip": m.group("peer"),
                "peer_as": int(m.group("asn")),
                "state": m.group("state"),
            }
        )

    return peers


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_fact_files():
    facts = {}
    if not FACTS_DIR.exists():
        raise FileNotFoundError(f"Facts directory not found: {FACTS_DIR}")

    for file in FACTS_DIR.glob("*_facts.json"):
        with open(file, "r") as f:
            data = json.load(f)
        node_name = data.get("node_name") or file.stem.replace("_facts", "")
        facts[node_name] = data
    return facts


def parse_lldp_neighbors(lldp_text):
    """
    Parse output of:
      show lldp neighbors | no-more

    Expected columns:
      Local Interface    Parent Interface    Chassis Id    Port info    System Name
    """
    neighbors = []

    if not lldp_text:
        return neighbors

    lines = lldp_text.splitlines()

    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("Local Interface"):
            continue

        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue

        local_intf = parts[0]
        parent_intf = parts[1]
        chassis_id = parts[2]
        port_info = parts[3]
        system_name = parts[4]

        neighbors.append({
            "local_interface": local_intf,
            "parent_interface": parent_intf,
            "chassis_id": chassis_id,
            "remote_port": port_info,
            "remote_system": system_name,
        })

    return neighbors


def parse_bgp_neighbors(bgp_text):
    """
    Parse summary lines from:
      show bgp summary | no-more

    We extract peer IP, peer AS, and state.
    """
    peers = []

    if not bgp_text:
        return peers

    lines = bgp_text.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match lines like:
        # 2001::1:0:21:1   4200000011 ... Establ
        m = re.match(r"^(\S+)\s+(\d+)\s+.+\s+(Establ|Idle|Active|Connect|OpenSent|OpenConfirm)$", line)
        if m:
            peer_ip = m.group(1)
            peer_as = int(m.group(2))
            state = m.group(3)
            peers.append({
                "peer_ip": peer_ip,
                "peer_as": peer_as,
                "state": state,
            })

    return peers


def build_topology(facts):
    topology = {
        "nodes": {},
        "links": [],
        "bgp_peers": []
    }

    link_seen = set()

    for node_name, data in facts.items():
        topology["nodes"][node_name] = {
            "hostname": data.get("hostname_expected", ""),
            "mgmt_ip": data.get("mgmt_ip", ""),
            "role": data.get("role", ""),
            "platform": data.get("platform", ""),
            "asn": data.get("asn", ""),
            "router_id": data.get("router_id", ""),
        }

        # LLDP parsing
        lldp_neighbors = parse_lldp_neighbors(data.get("lldp_neighbors", ""))
        for nbr in lldp_neighbors:
            remote_system = nbr["remote_system"].split(".")[0]
            link_key = tuple(sorted([
                f"{node_name}:{nbr['local_interface']}",
                f"{remote_system}:{nbr['remote_port']}"
            ]))
            if link_key not in link_seen:
                link_seen.add(link_key)
                topology["links"].append({
                    "local_node": node_name,
                    "local_interface": nbr["local_interface"],
                    "remote_node": remote_system,
                    "remote_interface": nbr["remote_port"],
                    "remote_system_raw": nbr["remote_system"],
                    "chassis_id": nbr["chassis_id"],
                })

        # BGP parsing
        bgp_peers = parse_bgp_neighbors(data.get("bgp_summary", ""))
        for peer in bgp_peers:
            topology["bgp_peers"].append({
                "node": node_name,
                "peer_ip": peer["peer_ip"],
                "peer_as": peer["peer_as"],
                "state": peer["state"],
            })

    return topology


def main():
    ensure_dir(OUTPUT_DIR)

    facts = load_fact_files()
    topology = build_topology(facts)
    topology["bgp_peers"] = deduplicate_bgp_peers(topology["bgp_peers"])
    out_file = OUTPUT_DIR / "discovered_topology.json"
    with open(out_file, "w") as f:
        json.dump(topology, f, indent=2)

    print(f"Discovered topology written to: {out_file}")
    print(f"Nodes     : {len(topology['nodes'])}")
    print(f"LLDP links: {len(topology['links'])}")
    print(f"BGP peers : {len(topology['bgp_peers'])}")


if __name__ == "__main__":
    main()
