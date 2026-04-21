import argparse
import json
from collections import defaultdict


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize(value):
    if value is None:
        return None
    return str(value).strip().lower()


def norm_intf(value):
    if value is None:
        return None
    return str(value).strip()


def normalize_link_endpoints(link):
    """
    Return (node_a, intf_a, node_b, intf_b) for multiple possible topology schemas.
    Returns None if the link shape is not recognized.
    """

    # Schema 1: local/peer style
    if all(k in link for k in ("local_node", "local_intf", "peer_node", "peer_intf")):
        return (
            link.get("local_node"),
            link.get("local_intf"),
            link.get("peer_node"),
            link.get("peer_intf"),
        )

    # Schema 2: node/interface + peer_node/peer_interface
    if all(k in link for k in ("node", "interface", "peer_node", "peer_interface")):
        return (
            link.get("node"),
            link.get("interface"),
            link.get("peer_node"),
            link.get("peer_interface"),
        )

    # Schema 3: node1/interface1/node2/interface2
    if all(k in link for k in ("node1", "interface1", "node2", "interface2")):
        return (
            link.get("node1"),
            link.get("interface1"),
            link.get("node2"),
            link.get("interface2"),
        )

    # Schema 4: node1/intf1/node2/intf2
    if all(k in link for k in ("node1", "intf1", "node2", "intf2")):
        return (
            link.get("node1"),
            link.get("intf1"),
            link.get("node2"),
            link.get("intf2"),
        )

    # Schema 5: nested endpoint objects
    ep1 = link.get("endpoint1") or link.get("a") or link.get("src") or link.get("local")
    ep2 = link.get("endpoint2") or link.get("z") or link.get("dst") or link.get("remote")
    if isinstance(ep1, dict) and isinstance(ep2, dict):
        a_node = ep1.get("node") or ep1.get("device") or ep1.get("name") or ep1.get("hostname")
        a_intf = ep1.get("interface") or ep1.get("port") or ep1.get("name")
        b_node = ep2.get("node") or ep2.get("device") or ep2.get("name") or ep2.get("hostname")
        b_intf = ep2.get("interface") or ep2.get("port") or ep2.get("name")
        if a_node and a_intf and b_node and b_intf:
            return (a_node, a_intf, b_node, b_intf)

    return None


def load_hotspots(path):
    data = load_json(path)

    if isinstance(data, dict):
        if "top_queues" in data:
            return data["top_queues"]
        if "hotspots" in data:
            return data["hotspots"]

    if isinstance(data, list):
        return data

    return []


def resolve_ixia_endpoint(topology, ixia_port):
    """
    Resolve IXIA endpoint from topology external_links.
    Supports a few common field variations.
    """
    for e in topology.get("external_links", []):
        peer_name = (
            e.get("peer_name")
            or e.get("peer")
            or e.get("remote_name")
            or e.get("external_name")
        )
        if peer_name == ixia_port:
            node = e.get("node") or e.get("local_node") or e.get("device")
            intf = e.get("interface") or e.get("local_intf") or e.get("port")
            return normalize(node), norm_intf(intf)
    return None, None


def build_leaf_spine_links(topology):
    """
    Returns:
      uplinks[src_leaf] = [
        {
          "spine": "spine2",
          "leaf_intf": "et-0/0/12:0",
          "spine_intf": "et-0/0/16",
        },
        ...
      ]

      downlinks[dst_leaf] = [
        {
          "spine": "spine1",
          "spine_intf": "et-0/0/30:0",
          "leaf_intf": "et-0/0/50:0",
        },
        ...
      ]
    """
    uplinks = defaultdict(list)
    downlinks = defaultdict(list)

    links = topology.get("links") or topology.get("edges") or topology.get("connections") or []

    for l in links:
        if not isinstance(l, dict):
            continue

        endpoints = normalize_link_endpoints(l)
        if not endpoints:
            continue

        a_node, a_intf, b_node, b_intf = endpoints
        a = normalize(a_node)
        b = normalize(b_node)
        a_intf = norm_intf(a_intf)
        b_intf = norm_intf(b_intf)

        if not a or not b:
            continue

        # leaf -> spine
        if a.startswith("leaf") and b.startswith("spine"):
            uplinks[a].append({
                "spine": b,
                "leaf_intf": a_intf,
                "spine_intf": b_intf,
            })
            downlinks[a].append({
                "spine": b,
                "spine_intf": b_intf,
                "leaf_intf": a_intf,
            })

        # spine -> leaf
        elif a.startswith("spine") and b.startswith("leaf"):
            uplinks[b].append({
                "spine": a,
                "leaf_intf": b_intf,
                "spine_intf": a_intf,
            })
            downlinks[b].append({
                "spine": a,
                "spine_intf": a_intf,
                "leaf_intf": b_intf,
            })

    return uplinks, downlinks


def build_corridor(topology, src_ixia, dst_ixia):
    src_leaf, src_ixia_intf = resolve_ixia_endpoint(topology, src_ixia)
    dst_leaf, dst_ixia_intf = resolve_ixia_endpoint(topology, dst_ixia)

    uplinks, downlinks = build_leaf_spine_links(topology)

    corridor = []
    seen = set()

    def add(node, intf):
        if not node:
            return
        key = (normalize(node), norm_intf(intf) if intf else None)
        if key not in seen:
            seen.add(key)
            corridor.append((normalize(node), norm_intf(intf) if intf else None))

    # ingress ixia-facing interface
    add(src_leaf, src_ixia_intf)

    # all source leaf uplinks + corresponding spine-side uplinks
    src_uplinks = uplinks.get(src_leaf, [])
    for link in src_uplinks:
        add(src_leaf, link["leaf_intf"])
        add(link["spine"], link["spine_intf"])

    # all destination leaf downlinks + corresponding spine-side downlinks
    dst_downlinks = downlinks.get(dst_leaf, [])
    for link in dst_downlinks:
        add(link["spine"], link["spine_intf"])
        add(dst_leaf, link["leaf_intf"])

    # egress ixia-facing interface
    add(dst_leaf, dst_ixia_intf)

    return corridor, src_leaf, dst_leaf


def correlate_hotspots(corridor, hotspots):
    matched = []

    for h in hotspots:
        node = normalize(h.get("node"))
        intf = norm_intf(h.get("interface"))

        for cnode, cintf in corridor:
            if node == cnode:
                if cintf is None or cintf == intf:
                    matched.append(h)
                    break

    matched.sort(key=lambda x: x.get("score", 0), reverse=True)
    return matched


def classify_cause(h):
    sig = h.get("signals", {}) or {}

    ecn = sig.get("ecn_marked_pkts", 0)
    tail = sig.get("tail_drop_pkts", 0)
    red = sig.get("red_drop_pkts", 0)
    peak = sig.get("peak_buffer_occupancy_percent", 0)

    if tail > 0:
        return "tail-drop congestion"
    if red > 0:
        return "WRED congestion"
    if ecn > 0:
        return "ECN queue pressure"
    if peak > 0:
        return "buffer pressure"

    return "unknown"


def render(intent, src, dst, corridor, matched):
    print("TRAFFIC INTENT ECMP RCA")
    print("  Intent:", intent)
    print("  Source:", src)
    print("  Destination:", dst)
    print()

    print("FABRIC CORRIDOR")
    if corridor:
        for n, i in corridor:
            if i:
                print(f"  {n} {i}")
            else:
                print(f"  {n}")
    else:
        print("  None")

    print()

    if not matched:
        print("No congestion detected in corridor")
        return

    print("TOP HOTSPOTS")
    for i, h in enumerate(matched[:10], 1):
        print(
            f" {i}. node={h.get('node')} interface={h.get('interface')} "
            f"queue={h.get('queue')} score={h.get('score')} severity={h.get('severity')}"
        )

    top = matched[0]

    print()
    print("RCA SUMMARY")
    print(
        f"  Most Likely Hop : {top.get('node')} {top.get('interface')} queue {top.get('queue')}"
    )
    print("  Severity        :", top.get("severity"))
    print("  Score           :", top.get("score"))
    print("  Cause           :", classify_cause(top))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", required=True)
    parser.add_argument("--hotspots", required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--intent-name", default="traffic_intent")
    args = parser.parse_args()

    topology = load_json(args.topology)
    hotspots = load_hotspots(args.hotspots)

    corridor, src_leaf, dst_leaf = build_corridor(topology, args.src, args.dst)
    matched = correlate_hotspots(corridor, hotspots)

    render(args.intent_name, src_leaf, dst_leaf, corridor, matched)


if __name__ == "__main__":
    main()
