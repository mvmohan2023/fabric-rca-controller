from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple



def short_intf_label(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        return "-"
    if "/" in s:
        return s.split("/")[-1]
    return s

def short_speed_label(speed: Any) -> str:
    s = str(speed or "").strip()
    if not s:
        return ""
    s = s.replace("Gbps", "G").replace("GE", "G").replace("gbps", "G")
    return s


def build_ixia_nodes_and_links(
    ixia_inventory_path: Optional[str],
    node_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not ixia_inventory_path:
        return [], []

    p = Path(ixia_inventory_path)
    if not p.exists():
        return [], []

    data = load_json(p)
    ports = data.get("ports", []) or []

    ixia_nodes: Dict[str, Dict[str, Any]] = {}
    ixia_links: List[Dict[str, Any]] = []

    for item in ports:
        switch = str(item.get("switch") or "").strip()
        switch_interface = str(item.get("switch_interface") or "").strip()
        ixia_port = str(item.get("ixia_port") or "").strip()
        port_name = str(item.get("port_name") or "").strip()
        line_speed = item.get("line_speed")
        expected_link_state = item.get("expected_link_state")

        if not switch or not switch_interface or not ixia_port:
            continue

        # Try to map inventory "switch" hostname back to topology node name
        topo_node = None
        for node_name, node_data in node_map.items():
            if str(node_data.get("hostname") or "").strip() == switch:
                topo_node = node_name
                break

        if not topo_node:
            topo_node = switch

        ixia_node_id = f"ixia::{port_name or ixia_port}"

        ixia_nodes[ixia_node_id] = {
            "id": ixia_node_id,
            "label": port_name or ixia_port,
            "ixia_port": ixia_port,
            "port_name": port_name,
            "line_speed": line_speed,
            "expected_link_state": expected_link_state,
        }

        ixia_links.append(
            {
                "local_node": topo_node,
                "local_intf": switch_interface,
                "peer_node": ixia_node_id,
                "peer_intf": port_name or ixia_port,
                "link_type": "ixia",
                "speed": line_speed or "unknown",
                "ixia_port": ixia_port,
                "port_name": port_name,
                "expected_link_state": expected_link_state,
                "ixia_mapped": True,
                "is_stressed": False,
                "is_stressed_peer": False,
                "has_hotspot": False,
                "local_ixia": {
                    "ixia_port": ixia_port,
                    "port_name": port_name,
                    "line_speed": line_speed,
                    "expected_link_state": expected_link_state,
                },
                "peer_ixia": {},
            }
        )

    return list(ixia_nodes.values()), ixia_links


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def safe(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def norm_role(role: Any) -> str:
    s = str(role or "").strip().lower()
    if "leaf" in s:
        return "leaf"
    if "spine" in s:
        return "spine"
    return s or "unknown"


def load_ixia_map(ixia_inventory_path: Optional[str]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not ixia_inventory_path:
        return {}

    p = Path(ixia_inventory_path)
    if not p.exists():
        return {}

    data = load_json(p)
    ports = data.get("ports", []) or []
    mapping: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for item in ports:
        switch = str(item.get("switch") or "").strip()
        switch_interface = str(item.get("switch_interface") or "").strip()
        if not switch or not switch_interface:
            continue
        mapping[(switch, switch_interface)] = {
            "ixia_port": item.get("ixia_port"),
            "port_name": item.get("port_name"),
            "line_speed": item.get("line_speed"),
            "expected_link_state": item.get("expected_link_state"),
        }

    return mapping


def extract_node_map(topology: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    nodes = topology.get("nodes", []) or []
    result: Dict[str, Dict[str, Any]] = {}

    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            node = str(item.get("node") or item.get("name") or item.get("hostname") or "").strip()
            if not node:
                continue
            result[node] = {
                "node": node,
                "hostname": item.get("hostname"),
                "mgmt_ip": item.get("mgmt_ip"),
                "role": norm_role(item.get("role")),
                "platform": item.get("platform"),
                "asn": item.get("asn"),
                "router_id": item.get("router_id"),
            }

    return result


def extract_fabric_links(topology: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = topology.get("links", []) or []
    result: List[Dict[str, Any]] = []

    for item in links:
        if not isinstance(item, dict):
            continue

        local_node = item.get("local_node")
        local_intf = item.get("local_intf") or item.get("local_interface")
        peer_node = item.get("peer_node") or item.get("remote_node")
        peer_intf = item.get("peer_intf") or item.get("remote_intf") or item.get("remote_interface")
        link_type = str(item.get("link_type") or "").strip().lower()

        if not local_node or not local_intf or not peer_node or not peer_intf:
            continue

        result.append(
            {
                "local_node": str(local_node),
                "local_intf": str(local_intf),
                "peer_node": str(peer_node),
                "peer_intf": str(peer_intf),
                "link_type": link_type or "unknown",
                "source": item.get("source"),
                "local_ipv4": item.get("local_ipv4"),
                "peer_ipv4": item.get("peer_ipv4"),
                "local_ipv6": item.get("local_ipv6"),
                "peer_ipv6": item.get("peer_ipv6"),
            }
        )

    return result


def extract_external_links(topology: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = topology.get("external_links", []) or []
    result: List[Dict[str, Any]] = []

    for item in links:
        if not isinstance(item, dict):
            continue

        local_node = item.get("local_node")
        local_intf = item.get("local_intf") or item.get("local_interface")
        peer_node = item.get("peer_node") or item.get("remote_node") or item.get("external_peer")
        peer_intf = item.get("peer_intf") or item.get("remote_intf") or item.get("remote_interface") or item.get("peer_interface")

        if not local_node or not local_intf:
            continue

        result.append(
            {
                "local_node": str(local_node),
                "local_intf": str(local_intf),
                "peer_node": safe(peer_node, "external"),
                "peer_intf": safe(peer_intf, "-"),
                "link_type": "external",
                "source": item.get("source"),
            }
        )

    return result


def build_peer_map(fabric_links: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Tuple[str, str]]:
    peer_map: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for link in fabric_links:
        a = (link["local_node"], link["local_intf"])
        b = (link["peer_node"], link["peer_intf"])
        peer_map[a] = b
        peer_map[b] = a
    return peer_map


def load_resolved_targets(validation: Dict[str, Any]) -> List[Dict[str, str]]:
    targets = validation.get("resolved_targets", []) or []
    result = []
    for item in targets:
        node = item.get("node")
        interface = item.get("interface")
        if node and interface:
            result.append({"node": str(node), "interface": str(interface)})
    return result


def load_top_hotspots(rca_ui_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    cos_health = rca_ui_report.get("cos_health", {}) or {}
    hotspots = cos_health.get("top_hotspots") or cos_health.get("hotspots") or []
    result = []
    for item in hotspots:
        result.append(
            {
                "node": item.get("node"),
                "interface": item.get("interface"),
                "queue": item.get("queue"),
                "classification": item.get("classification"),
                "forwarding_class": item.get("forwarding_class"),
                "score": item.get("score"),
                "tail_dropped_packets": item.get("tail_dropped_packets"),
                "ecn_ce_packets": item.get("ecn_ce_packets"),
                "is_suspicious": item.get("is_suspicious", False),
                "is_expected_ecn": item.get("is_expected_ecn", False),
            }
        )
    return result


def enrich_links(
    *,
    fabric_links: List[Dict[str, Any]],
    external_links: List[Dict[str, Any]],
    resolved_targets: List[Dict[str, Any]],
    top_hotspots: List[Dict[str, Any]],
    ixia_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    resolved_set = {
        (str(t.get("node") or ""), str(t.get("interface") or ""))
        for t in resolved_targets
        if t.get("node") and t.get("interface")
    }

    hotspot_set = {
        (str(h.get("node") or ""), str(h.get("interface") or ""))
        for h in top_hotspots
        if h.get("node") and h.get("interface")
    }

    def match_ixia(local_node: str, local_intf: str, peer_node: str, peer_intf: str) -> Dict[str, Any]:
        # direct interface-name match
        ctx = ixia_map.get(f"{local_node}|{local_intf}")
        if ctx:
            return ctx
        ctx = ixia_map.get(f"{peer_node}|{peer_intf}")
        if ctx:
            return ctx
        return {}

    enriched_fabric: List[Dict[str, Any]] = []
    for link in fabric_links:
        local_node = str(link.get("local_node") or "")
        local_intf = str(link.get("local_intf") or "")
        peer_node = str(link.get("peer_node") or "")
        peer_intf = str(link.get("peer_intf") or "")

        local_ep = (local_node, local_intf)
        peer_ep = (peer_node, peer_intf)

        ixia_ctx = match_ixia(local_node, local_intf, peer_node, peer_intf)

        enriched = dict(link)
        enriched["is_stressed"] = local_ep in resolved_set or peer_ep in resolved_set
        enriched["is_stressed_peer"] = False
        enriched["has_hotspot"] = local_ep in hotspot_set or peer_ep in hotspot_set
        enriched["ixia_mapped"] = bool(ixia_ctx)
        enriched["speed"] = ixia_ctx.get("line_speed") or link.get("speed") or "unknown"
        enriched["local_ixia"] = ixia_ctx if local_ep in resolved_set or local_ep in hotspot_set else {}
        enriched["peer_ixia"] = ixia_ctx if peer_ep in resolved_set or peer_ep in hotspot_set else {}
        enriched_fabric.append(enriched)

    enriched_external: List[Dict[str, Any]] = []
    for link in external_links:
        local_node = str(link.get("local_node") or "")
        local_intf = str(link.get("local_intf") or "")
        peer_node = str(link.get("peer_node") or "")
        peer_intf = str(link.get("peer_intf") or "")

        local_ep = (local_node, local_intf)
        peer_ep = (peer_node, peer_intf)

        ixia_ctx = match_ixia(local_node, local_intf, peer_node, peer_intf)

        enriched = dict(link)
        enriched["is_stressed"] = local_ep in resolved_set or peer_ep in resolved_set
        enriched["is_stressed_peer"] = False
        enriched["has_hotspot"] = local_ep in hotspot_set or peer_ep in hotspot_set
        enriched["ixia_mapped"] = bool(ixia_ctx)
        enriched["speed"] = ixia_ctx.get("line_speed") or link.get("speed") or "unknown"
        enriched["local_ixia"] = ixia_ctx
        enriched["peer_ixia"] = {}
        enriched_external.append(enriched)

    return enriched_fabric, enriched_external


def build_graph_payload(
    *,
    node_map: Dict[str, Dict[str, Any]],
    fabric_links: List[Dict[str, Any]],
    external_links: List[Dict[str, Any]],
    ixia_nodes: List[Dict[str, Any]],
    ixia_links: List[Dict[str, Any]],
) -> Dict[str, Any]:
    nodes_payload: List[Dict[str, Any]] = []

    # Regular topology nodes
    for node, data in sorted(node_map.items()):
        role = data.get("role")
        color = "#5aa9ff"
        level = 1

        if role == "spine":
            color = "#a56eff"
            level = 0
        elif role == "leaf":
            color = "#5aa9ff"
            level = 1
        else:
            color = "#7f8ea3"
            level = 1

        label = f"{node}"
        title = (
            f"Node: {safe(node)}<br>"
            f"Hostname: {safe(data.get('hostname'))}<br>"
            f"Role: {safe(role)}<br>"
            f"Platform: {safe(data.get('platform'))}<br>"
            f"Mgmt IP: {safe(data.get('mgmt_ip'))}"
        )

        nodes_payload.append(
            {
                "id": node,
                "label": label,
                "title": title,
                "color": color,
                "shape": "box",
                "level": level,
                "font": {"color": "#ffffff", "size": 16},
                "margin": 12,
            }
        )

    # IXIA pseudo-nodes
    for item in ixia_nodes:
        nodes_payload.append(
            {
                "id": item["id"],
                "label": safe(item.get("label")),
                "title": (
                    f"IXIA Port: {safe(item.get('ixia_port'))}<br>"
                    f"Port Name: {safe(item.get('port_name'))}<br>"
                    f"Speed: {safe(item.get('line_speed'))}<br>"
                    f"Expected Link State: {safe(item.get('expected_link_state'))}"
                ),
                "color": "#45c27a",
                "shape": "ellipse",
                "level": 2,
                "font": {"color": "#ffffff", "size": 14},
                "margin": 10,
            }
        )

    # External pseudo-nodes not already represented
    existing_node_ids = {n["id"] for n in nodes_payload}
    external_nodes = set()
    for link in external_links:
        peer = str(link.get("peer_node") or "")
        if peer and peer not in existing_node_ids:
            external_nodes.add(peer)

    for peer in sorted(external_nodes):
        nodes_payload.append(
            {
                "id": peer,
                "label": f"{peer}",
                "title": f"External Node: {peer}",
                "color": "#45c27a",
                "shape": "ellipse",
                "level": 2,
                "font": {"color": "#ffffff", "size": 14},
                "margin": 10,
            }
        )

    edges_payload: List[Dict[str, Any]] = []

    def edge_color(link: Dict[str, Any]) -> Dict[str, str]:
        if link.get("is_stressed"):
            return {"color": "#ff5c5c"}   # red
        if link.get("has_hotspot"):
            return {"color": "#f5c14d"}   # yellow
        if link.get("is_stressed_peer"):
            return {"color": "#ff9f43"}   # orange
        if link.get("ixia_mapped"):
            return {"color": "#45c27a"}   # green
        return {"color": "#7f8ea3"}       # grey

    # Fabric links
    for idx, link in enumerate(fabric_links, start=1):
        local_short = short_intf_label(link.get("local_intf"))
        peer_short = short_intf_label(link.get("peer_intf"))
        speed_label = short_speed_label(link.get("speed"))
        edge_label = f"{local_short}    {speed_label}    {peer_short}".strip()

        title = (
            f"{safe(link['local_node'])}:{safe(link['local_intf'])} ↔ "
            f"{safe(link['peer_node'])}:{safe(link['peer_intf'])}<br>"
            f"Type: {safe(link.get('link_type'))}<br>"
            f"Speed: {safe(link.get('speed'))}<br>"
            f"Stressed: {safe(link.get('is_stressed'))}<br>"
            f"Peer-of-Stressed: {safe(link.get('is_stressed_peer'))}<br>"
            f"Hotspot: {safe(link.get('has_hotspot'))}<br>"
            f"IXIA mapped: {safe(link.get('ixia_mapped'))}"
        )
        if link.get("is_stressed"):
            title += "<br><b>STRESSED LINK</b>"
        if link.get("has_hotspot"):
            title += "<br><b>HOTSPOT LINK</b>"

        edges_payload.append(
            {
                "id": f"fabric-{idx}",
                "from": link["local_node"],
                "to": link["peer_node"],
                "label": edge_label,
                "title": title,
                "color": edge_color(link),
                "width": 4 if link.get("is_stressed") else (3 if link.get("has_hotspot") else 2),
                "font": {"align": "middle", "size": 12, "color": "#d7e6fb", "strokeWidth": 0},
            }
        )

    # External links from topology file
    for idx, link in enumerate(external_links, start=1):
        local_short = short_intf_label(link.get("local_intf"))
        peer_short = safe(link.get("peer_intf"))
        speed_label = short_speed_label(link.get("speed"))
        edge_label = f"{local_short}    {speed_label}    {peer_short}".strip()

        title = (
            f"{safe(link['local_node'])}:{safe(link['local_intf'])} ↔ "
            f"{safe(link['peer_node'])}:{safe(link['peer_intf'])}<br>"
            f"Type: external<br>"
            f"Speed: {safe(link.get('speed'))}<br>"
            f"Stressed: {safe(link.get('is_stressed'))}<br>"
            f"Hotspot: {safe(link.get('has_hotspot'))}<br>"
            f"IXIA mapped: {safe(link.get('ixia_mapped'))}"
        )
        if link.get("is_stressed"):
            title += "<br><b>STRESSED LINK</b>"
        if link.get("has_hotspot"):
            title += "<br><b>HOTSPOT LINK</b>"

        edges_payload.append(
            {
                "id": f"external-{idx}",
                "from": link["local_node"],
                "to": link["peer_node"],
                "label": edge_label,
                "title": title,
                "color": edge_color(link),
                "dashes": True,
                "width": 4 if link.get("is_stressed") else (3 if link.get("has_hotspot") else 2),
                "font": {"align": "middle", "size": 12, "color": "#d7e6fb", "strokeWidth": 0},
            }
        )

    # IXIA inventory-derived links
    for idx, link in enumerate(ixia_links, start=1):
        local_short = short_intf_label(link.get("local_intf"))
        peer_short = safe(link.get("peer_intf"))
        speed_label = short_speed_label(link.get("speed"))
        edge_label = f"{local_short}    {speed_label}    {peer_short}".strip()

        title = (
            f"{safe(link['local_node'])}:{safe(link['local_intf'])} ↔ "
            f"{safe(link['peer_intf'])}<br>"
            f"Type: IXIA<br>"
            f"Speed: {safe(link.get('speed'))}<br>"
            f"IXIA Port: {safe(link.get('ixia_port'))}<br>"
            f"Port Name: {safe(link.get('port_name'))}<br>"
            f"Expected Link State: {safe(link.get('expected_link_state'))}<br>"
            f"Stressed: {safe(link.get('is_stressed'))}<br>"
            f"Hotspot: {safe(link.get('has_hotspot'))}"
        )
        if link.get("is_stressed"):
            title += "<br><b>STRESSED LINK</b>"
        if link.get("has_hotspot"):
            title += "<br><b>HOTSPOT LINK</b>"

        edges_payload.append(
            {
                "id": f"ixia-{idx}",
                "from": link["local_node"],
                "to": link["peer_node"],
                "label": edge_label,
                "title": title,
                "color": edge_color(link),
                "dashes": False,
                "width": 4 if link.get("is_stressed") else (3 if link.get("has_hotspot") else 2),
                "font": {"align": "middle", "size": 12, "color": "#d7e6fb", "strokeWidth": 0},
            }
        )

    return {"nodes": nodes_payload, "edges": edges_payload}


def build_topology_view_data(
    *,
    topology_path: str,
    validation_path: str,
    rca_ui_report_path: str,
    ixia_inventory_path: Optional[str],
) -> Dict[str, Any]:
    topology = load_json(topology_path)
    validation = load_json(validation_path)
    rca_ui_report = load_json(rca_ui_report_path)

    node_map = extract_node_map(topology)
    fabric_links = extract_fabric_links(topology)
    external_links = extract_external_links(topology)

    resolved_targets = load_resolved_targets(validation)
    top_hotspots = load_top_hotspots(rca_ui_report)

    ixia_nodes, ixia_links = build_ixia_nodes_and_links(ixia_inventory_path, node_map)

    resolved_set = {
        (str(t.get("node") or ""), str(t.get("interface") or ""))
        for t in resolved_targets
        if t.get("node") and t.get("interface")
    }
    hotspot_set = {
        (str(h.get("node") or ""), str(h.get("interface") or ""))
        for h in top_hotspots
        if h.get("node") and h.get("interface")
    }

    for link in ixia_links:
        ep = (str(link.get("local_node") or ""), str(link.get("local_intf") or ""))
        link["is_stressed"] = ep in resolved_set
        link["is_stressed_peer"] = False
        link["has_hotspot"] = ep in hotspot_set

    resolved_targets = load_resolved_targets(validation)
    top_hotspots = load_top_hotspots(rca_ui_report)
    ixia_map = load_ixia_map(ixia_inventory_path)

    enriched_fabric, enriched_external = enrich_links(
        fabric_links=fabric_links,
        external_links=external_links,
        resolved_targets=resolved_targets,
        top_hotspots=top_hotspots,
        ixia_map=ixia_map,
    )

    graph_payload = build_graph_payload(
        node_map=node_map,
        fabric_links=enriched_fabric,
        external_links=enriched_external,
        ixia_nodes=ixia_nodes,
        ixia_links=ixia_links,
    )

    run_metadata = {
        "run_id": validation.get("rca_run_id") or validation.get("run_id"),
        "scenario": validation.get("scenario"),
        "release_tag": validation.get("release_tag"),
        "final_status": validation.get("final_status"),
        "generated_at": validation.get("generated_at"),
        "src": rca_ui_report.get("run_metadata", {}).get("src"),
        "dst": rca_ui_report.get("run_metadata", {}).get("dst"),
        "resolved_target_count": len(resolved_targets),
    }

    return {
        "run_metadata": run_metadata,
        "nodes": list(node_map.values()),
        "resolved_targets": resolved_targets,
        "top_hotspots": top_hotspots,
        "fabric_links": enriched_fabric,
        "external_links": enriched_external,
        "ixia_nodes": ixia_nodes,
        "ixia_links": ixia_links,
        "graph": graph_payload,
    }


def render_html(data: Dict[str, Any]) -> str:
    payload_json = json.dumps(data)
    meta = data.get("run_metadata", {}) or {}

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Topology View - {html.escape(safe(meta.get("run_id")))}</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network@9.1.9/dist/vis-network.min.js"></script>
  <style>
    :root {{
      --bg: #08111f;
      --panel: #101b2f;
      --panel2: #14233a;
      --text: #e8f0fb;
      --muted: #9caec7;
      --border: rgba(255,255,255,0.08);
      --accent: #58b8ff;
      --danger: #ff5c5c;
      --warn: #ff9f43;
      --hotspot: #f5c14d;
      --ixia: #45c27a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: linear-gradient(135deg, #050b16 0%, #08111f 45%, #0c1628 100%);
      color: var(--text);
    }}
    .page {{
      padding: 20px;
      display: grid;
      gap: 16px;
    }}
    .card {{
      border: 1px solid var(--border);
      border-radius: 18px;
      background: rgba(255,255,255,0.04);
      overflow: hidden;
    }}
    .card-header {{
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      font-weight: 700;
      color: #fff;
    }}
    .card-body {{
      padding: 16px 18px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0,1fr));
      gap: 12px;
    }}
    .kv {{
      border: 1px solid var(--border);
      border-radius: 12px;
      background: rgba(255,255,255,0.03);
      padding: 12px;
    }}
    .kv .k {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .kv .v {{
      font-size: 16px;
      color: #fff;
      word-break: break-word;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255,255,255,0.03);
      color: var(--text);
      font-size: 13px;
    }}
    .swatch {{
      width: 12px;
      height: 12px;
      border-radius: 999px;
      display: inline-block;
    }}
    #graph {{
      width: 100%;
      height: 720px;
      border-radius: 14px;
      background: #091321;
      border: 1px solid var(--border);
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.08em;
    }}
    tr:hover {{
      background: rgba(255,255,255,0.03);
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .chip {{
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.04);
    }}
    .danger {{ background: rgba(255,92,92,0.16); border-color: rgba(255,92,92,0.35); }}
    .warn {{ background: rgba(255,159,67,0.16); border-color: rgba(255,159,67,0.35); }}
    .hotspot {{ background: rgba(245,193,77,0.16); border-color: rgba(245,193,77,0.35); }}
    .ixia {{ background: rgba(69,194,122,0.16); border-color: rgba(69,194,122,0.35); }}
    @media (max-width: 1200px) {{
      .grid {{ grid-template-columns: 1fr; }}
      #graph {{ height: 520px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="card">
      <div class="card-header">Topology View</div>
      <div class="card-body">
        <div class="grid">
          <div class="kv"><div class="k">Run ID</div><div class="v">{html.escape(safe(meta.get("run_id")))}</div></div>
          <div class="kv"><div class="k">Scenario</div><div class="v">{html.escape(safe(meta.get("scenario")))}</div></div>
          <div class="kv"><div class="k">Final Status</div><div class="v">{html.escape(safe(meta.get("final_status")))}</div></div>
          <div class="kv"><div class="k">Release Tag</div><div class="v">{html.escape(safe(meta.get("release_tag")))}</div></div>
          <div class="kv"><div class="k">Source</div><div class="v">{html.escape(safe(meta.get("src")))}</div></div>
          <div class="kv"><div class="k">Destination</div><div class="v">{html.escape(safe(meta.get("dst")))}</div></div>
          <div class="kv"><div class="k">Generated At</div><div class="v">{html.escape(safe(meta.get("generated_at")))}</div></div>
          <div class="kv"><div class="k">Resolved Target Count</div><div class="v">{html.escape(safe(meta.get("resolved_target_count")))}</div></div>
        </div>

        <div class="chips">
          <div class="chip"><span class="swatch" style="background:#5aa9ff;"></span> Leaf</div>
          <div class="chip"><span class="swatch" style="background:#a56eff;"></span> Spine</div>
          <div class="chip danger"><span class="swatch" style="background:#ff5c5c;"></span> Stressed Link</div>
          <div class="chip warn"><span class="swatch" style="background:#ff9f43;"></span> Peer of Stressed</div>
          <div class="chip hotspot"><span class="swatch" style="background:#f5c14d;"></span> Hotspot Link</div>
          <div class="chip ixia"><span class="swatch" style="background:#45c27a;"></span> IXIA / External</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header">Interactive Topology</div>
      <div class="card-body">
        <div class="chips" style="margin-bottom:12px;">
          <button class="chip" id="filterAllBtn" type="button">Show All</button>
          <button class="chip" id="filterStressedBtn" type="button">Stressed Only</button>
          <button class="chip" id="filterHotspotsBtn" type="button">Hotspots Only</button>
          <button class="chip" id="filterIxiaBtn" type="button">IXIA Only</button>
        </div>
        <div id="graph"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">Resolved Targets</div>
      <div class="card-body table-wrap">
        <table id="targetsTable"></table>
      </div>
    </div>

    <div class="card">
      <div class="card-header">Top CoS Hotspots</div>
      <div class="card-body table-wrap">
        <table id="hotspotsTable"></table>
      </div>
    </div>

    <div class="card">
      <div class="card-header">Fabric Links</div>
      <div class="card-body table-wrap">
        <table id="fabricLinksTable"></table>
      </div>
    </div>

    <div class="card">
      <div class="card-header">External / IXIA Links</div>
      <div class="card-body table-wrap">
        <table id="externalLinksTable"></table>
      </div>
    </div>
  </div>

  <script>
    const DATA = {payload_json};

    function esc(v) {{
      if (v === undefined || v === null || v === "") return "-";
      return String(v)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function renderTable(elId, headers, rows) {{
      const el = document.getElementById(elId);
      if (!rows.length) {{
        el.innerHTML = '<tr><td>No data</td></tr>';
        return;
      }}

      const head = `
        <thead>
          <tr>
            ${{headers.map(h => `<th>${{esc(h)}}</th>`).join("")}}
          </tr>
        </thead>
      `;

      const body = `
        <tbody>
          ${{rows.map(row => `
            <tr>
              ${{row.map(col => `<td>${{col}}</td>`).join("")}}
            </tr>
          `).join("")}}
        </tbody>
      `;

      el.innerHTML = head + body;
    }}

    let network = null;
    let graphNodes = null;
    let graphEdges = null;

    function buildGraph(filteredEdges = null) {{
      const container = document.getElementById("graph");

      if (!graphNodes) {{
        graphNodes = DATA.graph.nodes;
      }}
      if (!graphEdges) {{
        graphEdges = DATA.graph.edges;
      }}

      const nodes = new vis.DataSet(graphNodes);
      const edges = new vis.DataSet(filteredEdges || graphEdges);

      if (network) {{
        network.destroy();
      }}

      network = new vis.Network(container, {{ nodes, edges }}, {{
        layout: {{
          hierarchical: {{
            enabled: true,
            direction: "UD",
            sortMethod: "directed",
            levelSeparation: 180,
            nodeSpacing: 180,
            treeSpacing: 220,
            blockShifting: true,
            edgeMinimization: true,
            parentCentralization: true
          }}
        }},
        physics: false,
        edges: {{
          smooth: {{
            enabled: true,
            type: "cubicBezier",
            forceDirection: "vertical",
            roundness: 0.4
          }}
        }},
        interaction: {{
          hover: true,
          navigationButtons: true,
          keyboard: true,
          dragNodes: true,
          zoomView: true,
          dragView: true
        }}
      }});

      return network;
    }}

    function getFilteredEdges(mode) {{
      const allEdges = graphEdges || [];

      if (mode === "all") {{
        return allEdges;
      }}

      if (mode === "stressed") {{
        return allEdges.filter(e =>
          String(e.id || "").startsWith("fabric-") || String(e.id || "").startsWith("ixia-") || String(e.id || "").startsWith("external-")
        ).filter(e => {{
          const title = String(e.title || "");
          return title.includes("Stressed: True");
        }});
      }}

      if (mode === "hotspots") {{
        return allEdges.filter(e => {{
          const title = String(e.title || "");
          return title.includes("Hotspot: True");
        }});
      }}

      if (mode === "ixia") {{
        return allEdges.filter(e => String(e.id || "").startsWith("ixia-"));
      }}

      return allEdges;
    }}

    function bindGraphFilters() {{
      const allBtn = document.getElementById("filterAllBtn");
      const stressedBtn = document.getElementById("filterStressedBtn");
      const hotspotsBtn = document.getElementById("filterHotspotsBtn");
      const ixiaBtn = document.getElementById("filterIxiaBtn");

      if (allBtn) {{
        allBtn.addEventListener("click", () => buildGraph(getFilteredEdges("all")));
      }}
      if (stressedBtn) {{
        stressedBtn.addEventListener("click", () => buildGraph(getFilteredEdges("stressed")));
      }}
      if (hotspotsBtn) {{
        hotspotsBtn.addEventListener("click", () => buildGraph(getFilteredEdges("hotspots")));
      }}
      if (ixiaBtn) {{
        ixiaBtn.addEventListener("click", () => buildGraph(getFilteredEdges("ixia")));
      }}
    }}

    function initTables() {{
      renderTable(
        "targetsTable",
        ["Node", "Interface"],
        (DATA.resolved_targets || []).map(t => [
          esc(t.node),
          `<span class="mono">${{esc(t.interface)}}</span>`
        ])
      );

      renderTable(
        "hotspotsTable",
        ["Node", "Interface", "Queue", "FC", "Classification", "Score", "Tail Drop", "ECN-CE"],
        (DATA.top_hotspots || []).map(h => [
          esc(h.node),
          `<span class="mono">${{esc(h.interface)}}</span>`,
          esc(h.queue),
          esc(h.forwarding_class),
          esc(h.classification),
          esc(h.score),
          esc(h.tail_dropped_packets),
          esc(h.ecn_ce_packets)
        ])
      );

      renderTable(
        "fabricLinksTable",
        ["Local Node", "Local Intf", "Peer Node", "Peer Intf", "Type", "Speed", "Stressed", "Peer of Stressed", "Hotspot", "IXIA"],
        (DATA.fabric_links || []).map(l => [
          esc(l.local_node),
          `<span class="mono">${{esc(l.local_intf)}}</span>`,
          esc(l.peer_node),
          `<span class="mono">${{esc(l.peer_intf)}}</span>`,
          esc(l.link_type),
          esc(l.speed),
          esc(l.is_stressed),
          esc(l.is_stressed_peer),
          esc(l.has_hotspot),
          esc(l.ixia_mapped)
        ])
      );

      renderTable(
        "externalLinksTable",
        ["Local Node", "Local Intf", "Peer Node", "Peer Intf", "Speed", "IXIA Port", "Port Name"],
        (DATA.external_links || []).map(l => [
          esc(l.local_node),
          `<span class="mono">${{esc(l.local_intf)}}</span>`,
          esc(l.peer_node),
          `<span class="mono">${{esc(l.peer_intf)}}</span>`,
          esc(l.speed),
          esc((l.local_ixia || {{}}).ixia_port),
          esc((l.local_ixia || {{}}).port_name)
        ])
      );
    }}

    buildGraph();
    bindGraphFilters();
    initTables();

  </script>
</body>
</html>
"""


def build_topology_html_report(
    *,
    run_id: str,
    topology_path: str,
    validation_path: str,
    rca_ui_report_path: str,
    ixia_inventory_path: Optional[str] = None,
    output_html: Optional[str] = None,
    output_json: Optional[str] = None,
) -> Dict[str, str]:
    data = build_topology_view_data(
        topology_path=topology_path,
        validation_path=validation_path,
        rca_ui_report_path=rca_ui_report_path,
        ixia_inventory_path=ixia_inventory_path,
    )

    run_dir = Path("artifacts") / "campaigns" / run_id
    if output_html is None:
        output_html = str(run_dir / "topology_view.html")
    if output_json is None:
        output_json = str(run_dir / "topology_view.json")

    write_json(output_json, data)
    write_text(output_html, render_html(data))

    return {"html": output_html, "json": output_json}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HTML topology view for an RCA run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--rca-ui-report", required=True)
    parser.add_argument("--ixia-inventory")
    parser.add_argument("--output-html")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    outputs = build_topology_html_report(
        run_id=args.run_id,
        topology_path=args.topology,
        validation_path=args.validation,
        rca_ui_report_path=args.rca_ui_report,
        ixia_inventory_path=args.ixia_inventory,
        output_html=args.output_html,
        output_json=args.output_json,
    )

    print(outputs["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
