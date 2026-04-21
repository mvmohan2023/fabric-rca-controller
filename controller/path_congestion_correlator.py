# controller/path_congestion_correlator.py

import argparse
import json
from collections import defaultdict, deque


def load_json(path):
    with open(path) as f:
        return json.load(f)


def normalize(s):
    return (s or "").strip().lower()


def norm_intf(s):
    return (s or "").strip()


def build_graph(topology):
    graph = defaultdict(list)

    # fabric links
    for link in topology.get("links", []):
        a_node = normalize(link.get("local_node"))
        a_intf = norm_intf(link.get("local_intf"))
        b_node = normalize(link.get("peer_node"))
        b_intf = norm_intf(link.get("peer_intf"))

        if a_node and b_node:
            graph[a_node].append({
                "peer": b_node,
                "local_intf": a_intf,
                "peer_intf": b_intf,
                "edge_type": "fabric",
            })
            graph[b_node].append({
                "peer": a_node,
                "local_intf": b_intf,
                "peer_intf": a_intf,
                "edge_type": "fabric",
            })

    # ixia external links
    for ext in topology.get("external_links", []):
        node = normalize(ext.get("node"))
        intf = norm_intf(ext.get("interface"))
        peer_name = ext.get("peer_name")
        ixia_node = f"ixia::{peer_name}"

        if node and peer_name:
            graph[ixia_node].append({
                "peer": node,
                "local_intf": peer_name,
                "peer_intf": intf,
                "edge_type": "ixia",
            })
            graph[node].append({
                "peer": ixia_node,
                "local_intf": intf,
                "peer_intf": peer_name,
                "edge_type": "ixia",
            })

    return graph


def resolve_endpoint(topology, value):
    """
    Accepts:
      - leaf1
      - spine1
      - ix020-ares.englab.juniper.net/1
      - ixia::ix020-ares.englab.juniper.net/1
    """
    raw = (value or "").strip()

    # exact ixia endpoint
    if raw.startswith("ixia::"):
        return raw
    for ext in topology.get("external_links", []):
        if raw == ext.get("peer_name"):
            return f"ixia::{raw}"

    # normal node alias
    return normalize(raw)


def shortest_path(graph, src, dst):
    q = deque([(src, [])])
    seen = {src}

    while q:
        node, path = q.popleft()
        if node == dst:
            return path

        for edge in graph.get(node, []):
            peer = edge["peer"]
            if peer in seen:
                continue
            seen.add(peer)
            q.append((
                peer,
                path + [{
                    "from_node": node,
                    "from_intf": edge["local_intf"],
                    "to_node": peer,
                    "to_intf": edge["peer_intf"],
                    "edge_type": edge["edge_type"],
                }]
            ))

    return []


def load_hotspots(path):
    data = load_json(path)

    if isinstance(data, dict) and "top_queues" in data:
        return data["top_queues"]

    if isinstance(data, dict) and "hotspots" in data:
        return data["hotspots"]

    if isinstance(data, list):
        return data

    return []


def correlate_path_hotspots(topology, hotspots, src, dst):
    graph = build_graph(topology)

    src_resolved = resolve_endpoint(topology, src)
    dst_resolved = resolve_endpoint(topology, dst)

    path = shortest_path(graph, src_resolved, dst_resolved)

    path_interfaces = set()
    path_nodes = set()

    for hop in path:
        from_node = normalize(hop["from_node"])
        to_node = normalize(hop["to_node"])
        from_intf = norm_intf(hop["from_intf"])
        to_intf = norm_intf(hop["to_intf"])

        path_nodes.add(from_node)
        path_nodes.add(to_node)

        if not from_node.startswith("ixia::") and from_intf:
            path_interfaces.add((from_node, from_intf))
        if not to_node.startswith("ixia::") and to_intf:
            path_interfaces.add((to_node, to_intf))

    matched = []
    for h in hotspots:
        node = normalize(h.get("node"))
        intf = norm_intf(h.get("interface"))
        if (node, intf) in path_interfaces:
            matched.append(h)

    matched.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "src": src,
        "dst": dst,
        "src_resolved": src_resolved,
        "dst_resolved": dst_resolved,
        "path": path,
        "matched_hotspots": matched,
    }


def render_text(result):
    lines = []
    lines.append("PATH CONGESTION CORRELATION")
    lines.append(f"  Source           : {result.get('src')}")
    lines.append(f"  Destination      : {result.get('dst')}")
    lines.append(f"  Source Resolved  : {result.get('src_resolved')}")
    lines.append(f"  Dest Resolved    : {result.get('dst_resolved')}")
    lines.append("")

    lines.append("PATH")
    for hop in result.get("path", []):
        lines.append(
            f"  [{hop['edge_type']}] {hop['from_node']}:{hop['from_intf']} -> {hop['to_node']}:{hop['to_intf']}"
        )
    lines.append("")

    lines.append("MATCHED HOTSPOTS")
    matched = result.get("matched_hotspots", [])
    if not matched:
        lines.append("  None")
    else:
        for i, h in enumerate(matched[:20], 1):
            lines.append(
                f"  {i}. node={h.get('node')} interface={h.get('interface')} "
                f"queue={h.get('queue')} score={h.get('score')} severity={h.get('severity')}"
            )
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Correlate congestion hotspots to a topology path.")
    parser.add_argument("--topology", required=True)
    parser.add_argument("--hotspots", required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    args = parser.parse_args()

    topology = load_json(args.topology)
    hotspots = load_hotspots(args.hotspots)

    result = correlate_path_hotspots(
        topology=topology,
        hotspots=hotspots,
        src=args.src,
        dst=args.dst,
    )

    print(render_text(result))


if __name__ == "__main__":
    main()
