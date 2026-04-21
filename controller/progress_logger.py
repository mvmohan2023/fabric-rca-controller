# controller/progress_logger.py

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressLogger:
    def __init__(self, log_path: str | Path, echo: bool = True) -> None:
        self.log_path = Path(log_path)
        self.echo = echo
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, message: str) -> None:
        line = f"{utc_now_iso()} [{level}] {message}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.echo:
            print(line)

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def stage(self, title: str) -> None:
        sep = "=" * 100
        self._write("STAGE", sep)
        self._write("STAGE", title)
        self._write("STAGE", sep)

    def step(self, message: str) -> None:
        self._write("STEP", message)
