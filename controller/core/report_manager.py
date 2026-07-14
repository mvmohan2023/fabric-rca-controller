"""Report generation and persistence helpers for FVP."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Mapping, Optional

from controller.core.artifact_manager import ArtifactManager
from controller.core.exceptions import ReportError
from controller.core.models import ArtifactReference


class ReportManager:
    """Persist structured and text reports through ArtifactManager."""

    def __init__(self, artifact_manager: ArtifactManager):
        self.artifacts = artifact_manager

    @staticmethod
    def normalize_report(report: Any) -> Dict[str, Any]:
        if hasattr(report, "to_dict") and callable(report.to_dict):
            data = report.to_dict()
        elif is_dataclass(report):
            data = asdict(report)
        elif isinstance(report, Mapping):
            data = dict(report)
        else:
            raise ReportError(
                "Report must be a mapping, dataclass, or expose to_dict()"
            )

        if not isinstance(data, dict):
            raise ReportError("Normalized report must be a dictionary")

        return data

    def save_json_report(
        self,
        category: str,
        name: str,
        report: Any,
        *,
        producer: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> ArtifactReference:
        try:
            data = self.normalize_report(report)
            return self.artifacts.save_json(
                category,
                name,
                data,
                producer=producer,
                phase=phase,
            )
        except Exception as exc:
            if isinstance(exc, ReportError):
                raise

            raise ReportError(
                f"Failed to save report {category}/{name}: {exc}"
            ) from exc

    def save_text_report(
        self,
        category: str,
        name: str,
        content: str,
        *,
        producer: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> ArtifactReference:
        try:
            return self.artifacts.save_text(
                category,
                name,
                content,
                producer=producer,
                phase=phase,
            )
        except Exception as exc:
            raise ReportError(
                f"Failed to save text report {category}/{name}: {exc}"
            ) from exc
