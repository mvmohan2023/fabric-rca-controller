"""Deterministic, evidence-linked engineering assessment, without diagnosis.

Adds interpretation limits and investigation guidance to the new RCA sidecar.
Does not change correlation confidence, candidate models or legacy reasoning.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .models import EvidenceItem, RootCauseCandidate
from .relevance import assess_relevance
from .conflicts import assess_aligned_conflicts


def build_engineering_assessment(
    evidence: List[EvidenceItem],
    candidates: List[RootCauseCandidate],
    source_availability: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Describe source coverage and candidate facts without inventing causality."""
    gaps = []
    for source, entry in sorted(source_availability.items()):
        status = entry.get("status")
        reason = None
        if status != "loaded":
            reason = "invalid_source" if status == "invalid" else "source_unavailable"
        elif not entry.get("normalized_evidence_count", 0):
            reason = "loaded_without_observations"
        elif not entry.get("relevant_evidence_count", 0):
            reason = "context_only_observations"
        if reason:
            action = "Locate or inspect the existing source artifact; do not infer device health from its absence."
            if source == "traffic_intent_rca" and reason == "loaded_without_observations":
                action = "Inspect resolved endpoints, corridor and matched-hotspot selection before interpreting an empty intent summary."
            gaps.append({"source": source, "reason": reason,
                         "supporting_artifact": entry.get("path"), "recommended_check": action})

    indices = {id(item): index for index, item in enumerate(evidence)}
    conflicts = assess_aligned_conflicts(evidence)
    assessments = []
    for candidate in candidates:
        items = candidate.supporting_evidence
        decisions = assess_relevance(items)
        facts = []
        checks = ["Verify collection completeness and raw metric presence for each cited phase.",
                  "Align timestamps and event/traffic windows before attributing a cause."]
        limits = ["Entity correlation is not proof of causality or a health threshold violation.",
                  "Evidence confidence is not the probability that a proposed cause is correct."]
        if len({item.domain for item, decision in zip(items, decisions) if decision["relevant"]}) < 2:
            checks.append("Collect or locate an independent domain observation for this entity.")
        for item, decision in zip(items, decisions):
            if not decision["relevant"]:
                continue
            fact = {"evidence_index": indices.get(id(item)), "entity": item.entity,
                    "metric": item.metric, "observed_value": item.observed_value,
                    "phase": item.phase, "source": item.source,
                    "supporting_artifact": item.supporting_artifact,
                    "interpretation": "Reported source observation; expectedness has not been assessed."}
            if decision["reason"] == "phase_supported_recovery":
                fact["interpretation"] = "Zero post delta with a matching nonzero running delta: return to the reported baseline difference, not zero absolute value or proven fault recovery."
            if item.phase == "signals":
                limits.append("Unphased signal/cumulative counters cannot establish new event increments.")
            if "pfc" in str(item.metric).lower() or "pause" in str(item.metric).lower():
                checks.append("Verify PFC direction, priority, phase delta and traffic impact; interface-wide activity does not establish queue-specific RoCE impairment.")
            if "latency" in str(item.metric).lower():
                checks.append("Compare latency with the matching flow baseline/SLO and RoCE loss, ECN/CNP and retransmission evidence.")
            facts.append(fact)
        candidate_indices = {indices.get(id(item)) for item in items}
        candidate_conflicts = [conflict for conflict in conflicts["disagreements"]
                               if set(conflict["evidence_indices"]) <= candidate_indices]
        compared = sum(set(pair) <= candidate_indices for pair in conflicts["compared_evidence_pairs"])
        conflict_status = ("disagreements_observed" if candidate_conflicts else
                           "no_disagreement_in_comparable_pairs" if compared else
                           "not_assessed_without_aligned_measurement_windows")
        assessments.append({
            "entity": candidate.entity,
            "conclusion": "Relevant observations are correlated; expectedness and event causality remain unverified.",
            "facts": facts,
            "evidence_confidence": candidate.confidence,
            "confidence_label": candidate.metadata.get("confidence_label"),
            "interpretation_limits": list(dict.fromkeys(limits)),
            "recommended_checks": list(dict.fromkeys(checks)),
            "conflict_assessment": conflict_status,
            "conflicting_observations": candidate_conflicts,
        })
    return {
        "policy_version": "evidence_assessment_v1",
        "method": "deterministic_evidence_assessment",
        "source_coverage": "gaps_present" if gaps else "normalized_sources_available",
        "source_gaps": gaps,
        "candidate_assessments": assessments,
        "aligned_conflict_assessment": conflicts,
        "limitations": ["Source coverage describes the supported adapters, not mandatory scenario coverage or a validation verdict.",
                        "Missing sources, context-only evidence and defaultable zeros are not proof of healthy behavior.",
                        "No conflict is asserted merely because observations differ across phases or sources."],
    }
