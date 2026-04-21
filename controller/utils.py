from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def timestamp_string() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_text_file(path: str, content: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
