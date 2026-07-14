"""Central artifact-management service for FVP."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from controller.core.exceptions import ArtifactError
from controller.core.models import ArtifactReference
from controller.core.utils import (
    ensure_directory,
    read_json,
    write_json,
    write_text,
)


class ArtifactManager:
    """Manage execution artifacts under one run-specific root directory."""

    def __init__(self, root: str | Path):
        self.root = ensure_directory(root)

    def category_dir(self, category: str) -> Path:
        normalized = str(category or "").strip()

        if not normalized:
            raise ArtifactError("Artifact category must be non-empty")

        return ensure_directory(self.root / normalized)

    def resolve(self, category: str, name: str) -> Path:
        normalized_name = str(name or "").strip()

        if not normalized_name:
            raise ArtifactError("Artifact name must be non-empty")

        return self.category_dir(category) / normalized_name

    def save_json(
        self,
        category: str,
        name: str,
        data: Mapping[str, Any],
        *,
        producer: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> ArtifactReference:
        try:
            path = write_json(self.resolve(category, name), data)
        except Exception as exc:
            raise ArtifactError(
                f"Failed to save JSON artifact {category}/{name}: {exc}"
            ) from exc

        return ArtifactReference(
            name=name,
            path=str(path),
            category=category,
            producer=producer,
            phase=phase,
            content_type="application/json",
        )

    def save_text(
        self,
        category: str,
        name: str,
        content: str,
        *,
        producer: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> ArtifactReference:
        try:
            path = write_text(self.resolve(category, name), content)
        except Exception as exc:
            raise ArtifactError(
                f"Failed to save text artifact {category}/{name}: {exc}"
            ) from exc

        return ArtifactReference(
            name=name,
            path=str(path),
            category=category,
            producer=producer,
            phase=phase,
            content_type="text/plain",
        )

    def load_json(self, category: str, name: str) -> Dict[str, Any]:
        try:
            return read_json(self.resolve(category, name))
        except Exception as exc:
            raise ArtifactError(
                f"Failed to load JSON artifact {category}/{name}: {exc}"
            ) from exc

    def archive(
        self,
        source: str | Path,
        category: str,
        *,
        destination_name: Optional[str] = None,
    ) -> ArtifactReference:
        source_path = Path(source)

        if not source_path.exists():
            raise ArtifactError(f"Artifact source does not exist: {source_path}")

        name = destination_name or source_path.name
        destination = self.resolve(category, name)

        try:
            if source_path.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source_path, destination)
            else:
                ensure_directory(destination.parent)
                shutil.copy2(source_path, destination)
        except Exception as exc:
            raise ArtifactError(
                f"Failed to archive {source_path} to {destination}: {exc}"
            ) from exc

        return ArtifactReference(
            name=name,
            path=str(destination),
            category=category,
        )

    def exists(self, category: str, name: str) -> bool:
        return self.resolve(category, name).exists()
