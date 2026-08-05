"""Helpers for loading lightweight engineering-validation evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _count_items(value: Any) -> int:
    """Return a stable count for lists, dictionaries, or numeric values."""

    if isinstance(value, (list, dict)):
        return len(value)

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def load_post_sample_health(
    sample_paths: Iterable[str],
) -> List[Dict[str, Any]]:
    """Load lightweight health metadata from post-window samples.

    This helper intentionally avoids returning full telemetry payloads.
    Missing, unreadable, or invalid artifacts are represented as failed
    sample-health entries so the validators never manufacture a PASS.
    """

    results: List[Dict[str, Any]] = []

    for raw_path in sample_paths or []:
        path_text = str(raw_path or "").strip()

        if not path_text:
            continue

        path = Path(path_text)

        if not path.exists():
            results.append(
                {
                    "path": path_text,
                    "available": False,
                    "load_ok": False,
                    "error": "sample artifact does not exist",
                    "generated_at": None,
                    "snapshot_name": None,
                    "failed_nodes": 1,
                    "ok_nodes": 0,
                    "total_nodes": 0,
                }
            )
            continue

        try:
            with path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except Exception as exc:
            results.append(
                {
                    "path": path_text,
                    "available": True,
                    "load_ok": False,
                    "error": str(exc),
                    "generated_at": None,
                    "snapshot_name": None,
                    "failed_nodes": 1,
                    "ok_nodes": 0,
                    "total_nodes": 0,
                }
            )
            continue

        if not isinstance(payload, dict):
            results.append(
                {
                    "path": path_text,
                    "available": True,
                    "load_ok": False,
                    "error": "sample artifact root is not an object",
                    "generated_at": None,
                    "snapshot_name": None,
                    "failed_nodes": 1,
                    "ok_nodes": 0,
                    "total_nodes": 0,
                }
            )
            continue

        failed_nodes = payload.get("failed_nodes", [])
        ok_nodes = payload.get("ok_nodes", [])
        nodes = payload.get("nodes", {})
        total_nodes = payload.get("total_nodes")

        if total_nodes is None:
            total_nodes = _count_items(nodes)

        results.append(
            {
                "path": path_text,
                "available": True,
                "load_ok": True,
                "error": None,
                "generated_at": (
                    payload.get("generated_at")
                    or payload.get("timestamp")
                ),
                "snapshot_name": (
                    payload.get("snapshot_name")
                    or payload.get("phase_name")
                    or payload.get("phase")
                ),
                "profile": payload.get("profile"),
                "source_type": payload.get("source_type"),
                "failed_nodes": failed_nodes,
                "ok_nodes": ok_nodes,
                "failed_node_count": _count_items(failed_nodes),
                "ok_node_count": _count_items(ok_nodes),
                "total_nodes": _count_items(total_nodes),
            }
        )

    return results
