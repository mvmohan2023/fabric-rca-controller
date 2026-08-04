"""Target serialization helpers for Fabric Validation Platform.

This module converts normalized target dictionaries into the CLI formats
accepted by controller.stress_orchestrator.
"""

from __future__ import annotations

from typing import Any, Dict


TargetDict = Dict[str, Any]


class TargetSerializationError(ValueError):
    """Raised when a target cannot be serialized safely."""


def _required_text(
    target: TargetDict,
    key: str,
    *,
    description: str | None = None,
) -> str:
    """Return one required, normalized target field."""

    value = str(target.get(key) or "").strip()

    if not value:
        label = description or key
        raise TargetSerializationError(
            f"Target is missing required field '{label}': {target}"
        )

    return value


def infer_target_type(
    stress_mode: str,
    target: TargetDict,
) -> str:
    """Infer a target type when legacy targets do not define one."""

    explicit_type = str(
        target.get("target_type") or ""
    ).strip()

    if explicit_type:
        return explicit_type

    mode = str(stress_mode or "").strip()

    if mode == "bgp_clear":
        return "node"

    if mode.startswith("bgp_neighbor_"):
        return "bgp_neighbor"

    if mode.startswith("interface_"):
        return "interface"

    if target.get("peer_ip"):
        return "bgp_neighbor"

    if target.get("interface"):
        return "interface"

    if target.get("process"):
        return "process"

    if target.get("node"):
        return "node"

    raise TargetSerializationError(
        f"Unable to infer target type for mode '{mode}': {target}"
    )


def serialize_generic_target(
    target_type: str,
    target: TargetDict,
) -> str:
    """Serialize one generic target for the orchestrator --target option."""

    node = _required_text(target, "node")

    if target_type == "interface":
        resource = _required_text(
            target,
            "interface",
        )

    elif target_type == "bgp_neighbor":
        resource = _required_text(
            target,
            "peer_ip",
        )

    elif target_type == "process":
        resource = _required_text(
            target,
            "process",
        )

    else:
        resource = _required_text(
            target,
            "resource",
        )

    return f"{target_type}|{node}|{resource}"


def serialize_target(
    stress_mode: str,
    target: TargetDict,
) -> str:
    """Serialize one target according to the selected stress mode.

    Returned formats:

    bgp_clear:
        leaf7

    interface modes:
        interface|leaf7|et-6/0/0

    BGP-neighbor modes:
        bgp_neighbor|leaf7|2001::1:0:17:0

    Future generic target:
        process|leaf7|rpd
    """

    if not isinstance(target, dict):
        raise TargetSerializationError(
            "Target must be a dictionary, "
            f"received {type(target).__name__}"
        )

    mode = str(stress_mode or "").strip()

    if not mode:
        raise TargetSerializationError(
            "stress_mode must be non-empty"
        )

    target_type = infer_target_type(
        mode,
        target,
    )

    # bgp_clear retains its existing node-only --targets contract.
    if mode == "bgp_clear":
        return _required_text(target, "node")

    return serialize_generic_target(
        target_type,
        target,
    )


def uses_generic_target_option(
    stress_mode: str,
) -> bool:
    """Return whether this mode should use repeated --target arguments."""

    return str(stress_mode or "").strip() != "bgp_clear"
