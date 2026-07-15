"""BGP-neighbor target resolution for Fabric Validation Platform."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from controller.core import target_registry


BgpTarget = Dict[str, Any]


def _normalize_bgp_state(value: Any) -> str:
    """Normalize topology BGP states while preserving the original value."""

    state = str(value or "").strip()

    if state.lower() in {
        "establ",
        "established",
        "estab",
    }:
        return "established"

    return state.lower() or "unknown"


def _validate_peer_ip(peer_ip: str) -> str:
    """Validate and normalize an IPv4 or IPv6 BGP peer address."""

    normalized = str(peer_ip or "").strip()

    if not normalized:
        raise ValueError("BGP peer IP must be non-empty")

    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError as exc:
        raise ValueError(
            f"Invalid BGP peer IP address: {normalized}"
        ) from exc


def load_bgp_peers(topology_path: str | Path) -> List[BgpTarget]:
    """Load BGP peers from discovered_topology.json."""

    path = Path(topology_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Topology file does not exist: {path}"
        )

    with path.open("r", encoding="utf-8") as handle:
        topology = json.load(handle)

    peers = topology.get("bgp_peers", [])

    if not isinstance(peers, list):
        raise ValueError(
            "Topology field 'bgp_peers' must be a list"
        )

    normalized: List[BgpTarget] = []

    for index, peer in enumerate(peers):
        if not isinstance(peer, dict):
            continue

        node = str(peer.get("node") or "").strip()
        peer_ip = str(peer.get("peer_ip") or "").strip()

        if not node or not peer_ip:
            continue

        normalized.append({
            "target_type": "bgp_neighbor",
            "node": node,
            "peer_ip": _validate_peer_ip(peer_ip),
            "peer_as": peer.get("peer_as"),
            "state": _normalize_bgp_state(peer.get("state")),
            "source_index": index,
            "source": str(path),
        })

    return normalized


def resolve_bgp_neighbor(
    *,
    topology_path: str | Path,
    node: Optional[str] = None,
    peer_ip: Optional[str] = None,
    established_only: bool = True,
) -> BgpTarget:
    """Resolve exactly one BGP-neighbor target.

    Resolution rules:

    1. Filter by node when supplied.
    2. Filter by peer IP when supplied.
    3. By default, retain only established peers.
    4. Return exactly one peer.
    5. Raise an explicit error when no peer or multiple peers match.
    """

    peers = load_bgp_peers(topology_path)

    if node:
        requested_node = str(node).strip()
        peers = [
            peer
            for peer in peers
            if peer["node"] == requested_node
        ]

    if peer_ip:
        requested_peer = _validate_peer_ip(peer_ip)
        peers = [
            peer
            for peer in peers
            if peer["peer_ip"] == requested_peer
        ]

    if established_only:
        peers = [
            peer
            for peer in peers
            if peer["state"] == "established"
        ]

    if not peers:
        raise ValueError(
            "No BGP neighbor matched the requested selection"
        )

    if len(peers) > 1:
        candidates = [
            f"{peer['node']}:{peer['peer_ip']}"
            for peer in peers[:10]
        ]

        raise ValueError(
            "BGP neighbor selection is ambiguous. "
            f"Matched {len(peers)} peers: {candidates}. "
            "Provide both node and peer_ip."
        )

    return peers[0]


def resolve_bgp_neighbors_for_node(
    *,
    topology_path: str | Path,
    node: str,
    established_only: bool = True,
) -> List[BgpTarget]:
    """Resolve all BGP neighbors for one node."""

    requested_node = str(node or "").strip()

    if not requested_node:
        raise ValueError("node must be non-empty")

    peers = [
        peer
        for peer in load_bgp_peers(topology_path)
        if peer["node"] == requested_node
    ]

    if established_only:
        peers = [
            peer
            for peer in peers
            if peer["state"] == "established"
        ]

    if not peers:
        raise ValueError(
            f"No BGP neighbors found for node '{requested_node}'"
        )

    return peers


def register_bgp_target_resolvers() -> None:
    """Register BGP target resolvers."""

    target_registry.register(
        "bgp_neighbor",
        resolve_bgp_neighbor,
        replace=True,
    )

    target_registry.register(
        "bgp_neighbors_for_node",
        resolve_bgp_neighbors_for_node,
        replace=True,
    )


register_bgp_target_resolvers()
