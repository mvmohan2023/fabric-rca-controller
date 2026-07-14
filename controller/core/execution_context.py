"""Execution context shared across FVP workflow stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from controller.core.artifact_manager import ArtifactManager
from controller.core.utils import ensure_directory, utc_timestamp


@dataclass
class ExecutionContext:
    """Shared runtime state for one scenario, campaign, or release run."""

    run_id: str
    output_root: str | Path

    scenario_name: Optional[str] = None
    topology: Optional[str] = None
    inventory: Optional[str] = None
    release_tag: Optional[str] = None

    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    created_at: str = field(default_factory=utc_timestamp)
    artifact_manager: ArtifactManager = field(init=False)

    def __post_init__(self) -> None:
        self.run_id = str(self.run_id or "").strip()

        if not self.run_id:
            raise ValueError("ExecutionContext.run_id must be non-empty")

        root = ensure_directory(Path(self.output_root) / self.run_id)
        self.output_root = root
        self.artifact_manager = ArtifactManager(root)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_name": self.scenario_name,
            "output_root": str(self.output_root),
            "topology": self.topology,
            "inventory": self.inventory,
            "release_tag": self.release_tag,
            "config": dict(self.config),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }
