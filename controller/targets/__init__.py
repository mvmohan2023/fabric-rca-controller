"""Target resolvers provided by Fabric Validation Platform."""

from controller.targets.bgp_neighbor import (
    load_bgp_peers,
    register_bgp_target_resolvers,
    resolve_bgp_neighbor,
    resolve_bgp_neighbors_for_node,
)

__all__ = [
    "load_bgp_peers",
    "register_bgp_target_resolvers",
    "resolve_bgp_neighbor",
    "resolve_bgp_neighbors_for_node",
]
