"""Normalized Engineering RCA models.

These models provide a reusable, additive representation for evidence and
root-cause candidates. They do not replace existing RCA artifact schemas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvidenceItem:
    """One normalized, traceable engineering observation."""

    domain: str
    source: str
    entity: Optional[str] = None
    metric: Optional[str] = None
    observed_value: Any = None
    phase: Optional[str] = None
    severity: Optional[str] = None
    classification: Optional[str] = None
    supporting_artifact: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.domain = str(self.domain or "").strip().lower()
        self.source = str(self.source or "").strip()
        if not self.domain:
            raise ValueError("EvidenceItem domain is required")
        if not self.source:
            raise ValueError("EvidenceItem source is required")

        self.confidence = float(self.confidence)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("EvidenceItem confidence must be between 0.0 and 1.0")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RootCauseCandidate:
    """Evidence-backed root-cause hypothesis."""

    category: str
    explanation: str
    entity: Optional[str] = None
    supporting_evidence: List[EvidenceItem] = field(default_factory=list)
    conflicting_evidence: List[EvidenceItem] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.category = str(self.category or "").strip()
        self.explanation = str(self.explanation or "").strip()
        if not self.category:
            raise ValueError("RootCauseCandidate category is required")
        if not self.explanation:
            raise ValueError("RootCauseCandidate explanation is required")

        self.confidence = float(self.confidence)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("RootCauseCandidate confidence must be between 0.0 and 1.0")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["supporting_evidence"] = [item.to_dict() for item in self.supporting_evidence]
        data["conflicting_evidence"] = [item.to_dict() for item in self.conflicting_evidence]
        return data
