"""Additive cross-domain RCA correlation and confidence assessment.

This module consumes normalized EvidenceItem objects only. It does not alter
legacy RCA correlation, engineering reasoning, UI schemas, or source artifacts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from .models import EvidenceItem, RootCauseCandidate


def _confidence_for_group(items: List[EvidenceItem]) -> tuple[float, Dict[str, Any]]:
    """Return conservative evidence confidence in the range 0.0..1.0.

    Confidence is based on evidence diversity and traceability, not on whether
    an observed metric is good or bad. Metric thresholds remain owned by the
    existing feature-specific analyzers.
    """

    domains = {item.domain for item in items if item.domain}
    sources = {item.source for item in items if item.source}
    artifacts = {
        item.supporting_artifact
        for item in items
        if item.supporting_artifact
    }
    classified = sum(1 for item in items if item.classification)
    traced = sum(1 for item in items if item.supporting_artifact)

    # A single-source observation starts deliberately below "Medium".
    score = 0.30
    score += min(max(len(domains) - 1, 0) * 0.15, 0.30)
    score += min(max(len(sources) - 1, 0) * 0.10, 0.20)

    if items and traced == len(items):
        score += 0.10
    if items and classified == len(items):
        score += 0.05

    score = min(score, 0.95)

    return score, {
        "evidence_count": len(items),
        "domain_count": len(domains),
        "source_count": len(sources),
        "artifact_count": len(artifacts),
        "domains": sorted(domains),
        "sources": sorted(sources),
        "all_evidence_traceable": bool(items) and traced == len(items),
        "all_evidence_classified": bool(items) and classified == len(items),
    }


def confidence_label(confidence: float) -> str:
    """Map normalized confidence to the architecture's 0-100 bands."""

    score = float(confidence) * 100.0
    if score >= 95.0:
        return "Very High"
    if score >= 80.0:
        return "High"
    if score >= 60.0:
        return "Medium"
    if score >= 40.0:
        return "Low"
    return "Insufficient Evidence"


def correlate_by_entity(
    evidence: Iterable[EvidenceItem],
) -> List[RootCauseCandidate]:
    """Build evidence candidates by exact normalized entity.

    This is correlation, not diagnosis. Existing feature analyzers continue to
    own threshold interpretation and root-cause classification.
    """

    groups: Dict[str, List[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        if item.entity:
            groups[item.entity].append(item)

    candidates: List[RootCauseCandidate] = []
    for entity, items in sorted(groups.items()):
        confidence, assessment = _confidence_for_group(items)
        domains = assessment["domains"]
        sources = assessment["sources"]

        category = "cross_domain_observation" if len(domains) > 1 else "domain_observation"
        explanation = (
            f"Evidence for {entity} is correlated across "
            f"{len(domains)} domain(s) and {len(sources)} source(s)."
        )

        metadata = {
            "correlation_type": "exact_entity",
            "confidence_label": confidence_label(confidence),
            "confidence_assessment": assessment,
        }

        candidates.append(
            RootCauseCandidate(
                category=category,
                entity=entity,
                explanation=explanation,
                supporting_evidence=list(items),
                confidence=confidence,
                metadata=metadata,
            )
        )

    return candidates


def serialize_candidates(
    candidates: Iterable[RootCauseCandidate],
) -> List[Dict[str, Any]]:
    """Return JSON-compatible candidates without modifying evidence."""

    return [candidate.to_dict() for candidate in candidates]
