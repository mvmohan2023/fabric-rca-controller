from __future__ import annotations

from datetime import datetime
from pathlib import Path

import json
import os
import tempfile

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


    
def atomic_write_json(path, data, indent=2, sort_keys=False):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
        dir=directory,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, sort_keys=sort_keys)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, path)

    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
