"""BFD-session target resolution for Fabric Validation Platform."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from controller.core import target_registry


BfdTarget = Dict[str, Any]


def _normalize_bfd_state(value: Any) -> str:
    """Normalize BFD operational state."""

    state = str(value or "").strip().lower()

    if state in {
        "up",
        "down",
        "admindown",
        "admin_down",
    }:
        return state

    return state or "unknown"


def _normalize_session_type(value: Any) -> str:
    """Normalize common BFD session-type strings."""

    value = str(value or "").strip().lower()

    if "single" in value and "hop" in value:
        return "single_hop"

    if "multi" in value and "hop" in value:
        return "multi_hop"

    return value.replace(" ", "_") or "unknown"


def _validate_peer_ip(peer_ip: str) -> str:
    """Validate and normalize an IPv4 or IPv6 BFD peer address."""

    normalized = str(peer_ip or "").strip()

    if not normalized:
        raise ValueError(
            "BFD peer IP must be non-empty"
        )

    try:
        return str(
            ipaddress.ip_address(normalized)
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid BFD peer IP address: {normalized}"
        ) from exc


def load_bfd_sessions(
    sessions_path: str | Path,
) -> List[BfdTarget]:
    """Load normalized BFD sessions from a JSON artifact.

    Expected artifact forms:

        {
            "bfd_sessions": [...]
        }

    or directly:

        [...]
    """

    path = Path(sessions_path)

    if not path.exists():
        raise FileNotFoundError(
            f"BFD session artifact does not exist: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        sessions = payload.get(
            "bfd_sessions",
            [],
        )
    elif isinstance(payload, list):
        sessions = payload
    else:
        raise ValueError(
            "BFD session artifact must contain "
            "a list or {'bfd_sessions': [...]}"
        )

    if not isinstance(sessions, list):
        raise ValueError(
            "BFD field 'bfd_sessions' must be a list"
        )

    normalized: List[BfdTarget] = []

    for index, session in enumerate(sessions):
        if not isinstance(session, dict):
            continue

        node = str(
            session.get("node") or ""
        ).strip()

        peer_ip = str(
            session.get("peer_ip")
            or session.get("address")
            or ""
        ).strip()

        if not node or not peer_ip:
            continue

        normalized.append(
            {
                "target_type": "bfd_session",
                "node": node,
                "peer_ip": _validate_peer_ip(
                    peer_ip
                ),
                "interface": str(
                    session.get("interface")
                    or ""
                ).strip(),
                "state": _normalize_bfd_state(
                    session.get("state")
                ),
                "client": str(
                    session.get("client")
                    or ""
                ).strip(),
                "session_type":
                    _normalize_session_type(
                        session.get(
                            "session_type"
                        )
                    ),
                "local_discriminator":
                    session.get(
                        "local_discriminator"
                    ),
                "remote_discriminator":
                    session.get(
                        "remote_discriminator"
                    ),
                "session_id":
                    session.get("session_id"),
                "source_index": index,
                "source": str(path),
            }
        )

    return normalized


def resolve_bfd_session(
    *,
    sessions_path: str | Path,
    node: Optional[str] = None,
    peer_ip: Optional[str] = None,
    up_only: bool = True,
) -> BfdTarget:
    """Resolve exactly one BFD session.

    Resolution rules:

    1. Filter by node when supplied.
    2. Filter by peer IP when supplied.
    3. By default, retain only Up sessions.
    4. Return exactly one session.
    5. Raise explicit errors for zero or ambiguous matches.
    """

    sessions = load_bfd_sessions(
        sessions_path
    )

    if node:
        requested_node = str(
            node
        ).strip()

        sessions = [
            session
            for session in sessions
            if session["node"]
            == requested_node
        ]

    if peer_ip:
        requested_peer = (
            _validate_peer_ip(
                peer_ip
            )
        )

        sessions = [
            session
            for session in sessions
            if session["peer_ip"]
            == requested_peer
        ]

    if up_only:
        sessions = [
            session
            for session in sessions
            if session["state"] == "up"
        ]

    if not sessions:
        raise ValueError(
            "No BFD session matched the "
            "requested selection"
        )

    if len(sessions) > 1:
        candidates = [
            (
                f"{session['node']}:"
                f"{session['peer_ip']}:"
                f"{session.get('interface')}"
            )
            for session in sessions[:10]
        ]

        raise ValueError(
            "BFD session selection is ambiguous. "
            f"Matched {len(sessions)} sessions: "
            f"{candidates}. "
            "Provide both node and peer_ip."
        )

    return sessions[0]


def resolve_bfd_sessions_for_node(
    *,
    sessions_path: str | Path,
    node: str,
    up_only: bool = True,
) -> List[BfdTarget]:
    """Resolve BFD sessions for one node."""

    requested_node = str(
        node or ""
    ).strip()

    if not requested_node:
        raise ValueError(
            "node must be non-empty"
        )

    sessions = [
        session
        for session in load_bfd_sessions(
            sessions_path
        )
        if session["node"]
        == requested_node
    ]

    if up_only:
        sessions = [
            session
            for session in sessions
            if session["state"] == "up"
        ]

    if not sessions:
        raise ValueError(
            f"No BFD sessions found for "
            f"node '{requested_node}'"
        )

    return sessions


def register_bfd_target_resolvers() -> None:
    """Register BFD target resolvers."""

    target_registry.register(
        "bfd_session",
        resolve_bfd_session,
        replace=True,
    )

    target_registry.register(
        "bfd_sessions_for_node",
        resolve_bfd_sessions_for_node,
        replace=True,
    )


register_bfd_target_resolvers()
