# controller/traffic_intent_rca.py

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
    raw = (value or "").strip()
    if raw.startswith("ixia::"):
        return raw

    for ext in topology.get("external_links", []):
        if raw == ext.get("peer_name"):
            return f"ixia::{raw}"

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


def classify_intent_cause(h):
    signals = h.get("signals", {}) or {}

    tail = signals.get("tail_drop_pkts", 0) or 0
    red = signals.get("red_drop_pkts", 0) or 0
    ecn = signals.get("ecn_marked_pkts", 0) or 0
    peak = signals.get("peak_buffer_occupancy_percent", 0) or 0

    if tail > 0:
        return "tail-drop congestion on path"
    if red > 0:
        return "wred/red congestion on path"
    if ecn > 0 and peak >= 20:
        return "ecn-driven queue pressure on path"
    if ecn > 0:
        return "ecn activity on path"
    if peak > 0:
        return "buffer pressure on path"
    return "no strong congestion signal"


def correlate_hotspots_to_path(path, hotspots):
    path_interfaces = set()

    for hop in path:
        from_node = normalize(hop["from_node"])
        to_node = normalize(hop["to_node"])
        from_intf = norm_intf(hop["from_intf"])
        to_intf = norm_intf(hop["to_intf"])

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
    return matched


def build_rca(topology, hotspots, src, dst, intent_name=None):
    graph = build_graph(topology)
    src_resolved = resolve_endpoint(topology, src)
    dst_resolved = resolve_endpoint(topology, dst)

    path = shortest_path(graph, src_resolved, dst_resolved)
    matched = correlate_hotspots_to_path(path, hotspots)

    top = matched[0] if matched else None

    result = {
        "intent_name": intent_name or f"{src}_to_{dst}",
        "src": src,
        "dst": dst,
        "src_resolved": src_resolved,
        "dst_resolved": dst_resolved,
        "path": path,
        "matched_hotspots": matched,
        "top_path_hotspot": top,
        "rca_summary": None,
    }

    if top:
        result["rca_summary"] = {
            "node": top.get("node"),
            "interface": top.get("interface"),
            "queue": top.get("queue"),
            "severity": top.get("severity"),
            "score": top.get("score"),
            "probable_cause": top.get("probable_cause"),
            "intent_cause": classify_intent_cause(top),
            "signals": top.get("signals", {}),
        }

    return result


def render_text(result):
    lines = []
    lines.append("TRAFFIC INTENT RCA")
    lines.append(f"  Intent            : {result.get('intent_name')}")
    lines.append(f"  Source            : {result.get('src')}")
    lines.append(f"  Destination       : {result.get('dst')}")
    lines.append(f"  Source Resolved   : {result.get('src_resolved')}")
    lines.append(f"  Dest Resolved     : {result.get('dst_resolved')}")
    lines.append("")

    lines.append("PATH")
    for hop in result.get("path", []):
        lines.append(
            f"  [{hop['edge_type']}] {hop['from_node']}:{hop['from_intf']} -> {hop['to_node']}:{hop['to_intf']}"
        )
    lines.append("")

    lines.append("PATH HOTSPOTS")
    matched = result.get("matched_hotspots", [])
    if not matched:
        lines.append("  None")
    else:
        for i, h in enumerate(matched[:10], 1):
            lines.append(
                f"  {i}. node={h.get('node')} interface={h.get('interface')} "
                f"queue={h.get('queue')} score={h.get('score')} severity={h.get('severity')}"
            )
    lines.append("")

    lines.append("RCA SUMMARY")
    rca = result.get("rca_summary")
    if not rca:
        lines.append("  No path-aligned congestion hotspot detected.")
    else:
        sig = rca.get("signals", {})
        lines.append(
            f"  Most Likely Hop   : {rca.get('node')} {rca.get('interface')} queue {rca.get('queue')}"
        )
        lines.append(f"  Severity          : {rca.get('severity')}")
        lines.append(f"  Score             : {rca.get('score')}")
        lines.append(f"  Cause             : {rca.get('intent_cause')}")
        lines.append(
            f"  Signals           : peak_buffer%={sig.get('peak_buffer_occupancy_percent')} "
            f"ecn={sig.get('ecn_marked_pkts')} tail_drop={sig.get('tail_drop_pkts')} "
            f"red_drop={sig.get('red_drop_pkts')}"
        )
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Traffic-intent-aware congestion RCA")
    parser.add_argument("--topology", required=True)
    parser.add_argument("--hotspots", required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--intent-name", default=None)
    args = parser.parse_args()

    topology = load_json(args.topology)
    hotspots = load_hotspots(args.hotspots)

    result = build_rca(
        topology=topology,
        hotspots=hotspots,
        src=args.src,
        dst=args.dst,
        intent_name=args.intent_name,
    )

    print(render_text(result))


if __name__ == "__main__":
    main()
