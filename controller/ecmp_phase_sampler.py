from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parents[1]


def encode_iface_for_snapshot(interface: str) -> str:
    return str(interface).replace("/", "_").replace(":", "~")


def collect_ecmp_phase_snapshot(
    *,
    run_id: str,
    snapshot_name: str,
    profile: str,
    node: str,
    interface: str,
    topology: str,
    timeout: int = 30,
) -> str:
    """
    Collect one ECMP/qmon telemetry snapshot.

    This helper intentionally shells into the existing telemetry collection path
    instead of duplicating collector internals.

    Output:
      artifacts/campaigns/<run_id>/telemetry/<snapshot_name>_<profile>.json
    """

    telemetry_dir = BASE_DIR / "artifacts" / "campaigns" / run_id / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    out_path = telemetry_dir / f"{snapshot_name}_{profile}.json"

    cmd = [
        "python",
        "-m",
        "controller.telemetry_monitor",
        "--run-id",
        run_id,
        "--snapshot-name",
        snapshot_name,
        "--profile",
        profile,
        "--nodes",
        node,
        "--topology",
        topology,
        "--timeout",
        str(timeout),
    ]

    print(f"  [ECMP-PHASE-SAMPLE] CMD: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        text=True,
        capture_output=True,
        timeout=max(timeout + 30, 60),
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ECMP phase snapshot failed "
            f"snapshot={snapshot_name} rc={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )

    if not out_path.exists():
        raise RuntimeError(f"ECMP phase snapshot output missing: {out_path}")

    return str(out_path)
