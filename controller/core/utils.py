"""Utility helpers for the Fabric Validation Platform core framework."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping


def utc_timestamp() -> str:
    """Return a timezone-aware UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).isoformat()


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_json(path: str | Path) -> Dict[str, Any]:
    """Read and return a JSON object."""

    file_path = Path(path)

    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected JSON object in {file_path}, "
            f"received {type(data).__name__}"
        )

    return data


def write_json(
    path: str | Path,
    data: Mapping[str, Any],
    *,
    indent: int = 2,
    sort_keys: bool = False,
) -> Path:
    """Write a JSON object atomically."""

    file_path = Path(path)
    ensure_directory(file_path.parent)

    temporary_path = file_path.with_suffix(file_path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            dict(data),
            handle,
            indent=indent,
            sort_keys=sort_keys,
            default=str,
        )
        handle.write("\n")

    temporary_path.replace(file_path)
    return file_path


def write_text(path: str | Path, content: str) -> Path:
    """Write text atomically."""

    file_path = Path(path)
    ensure_directory(file_path.parent)

    temporary_path = file_path.with_suffix(file_path.suffix + ".tmp")
    temporary_path.write_text(str(content), encoding="utf-8")
    temporary_path.replace(file_path)

    return file_path


def deep_merge(
    base: Mapping[str, Any],
    update: Mapping[str, Any],
) -> Dict[str, Any]:
    """Recursively merge two dictionaries without mutating either input."""

    merged: Dict[str, Any] = dict(base)

    for key, value in update.items():
        existing = merged.get(key)

        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = value

    return merged
