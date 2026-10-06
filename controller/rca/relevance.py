"""Evidence relevance without deleting or rewriting source observations.

Default zeros cannot establish an engineering observation. A zero post delta
with a matching running-phase change is retained for interpretation, not proof
of recovery.
Relevance is not a health threshold or a causal diagnosis.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Dict, Iterable, List

from .models import EvidenceItem


_DESCRIPTIVE_METRICS = {"classification_confidence", "recovery_ratio_tail"}


def _number(value: Any) -> float | None:
    # False is a state observation, not a numeric zero.
    if isinstance(value, bool):
        return None
    if isinstance(value, (Real, str)):
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            pass
    return None


def assess_relevance(items: Iterable[EvidenceItem]) -> List[Dict[str, Any]]:
    """Return one ordered decision per item, retaining exact-entity boundaries.

    The congestion producer computes post delta as POST minus RUNNING. Zero
    therefore means no reported change from RUNNING, not return to PRE.
    Phase-aware UI fields and series can be padded with zeros. They cannot
    prove recovery without independent measurement provenance. Classification
    and score alone are insufficient.
    """
    items = list(items)
    running = set()
    for item in items:
        value = _number(item.observed_value)
        if value is None or not math.isfinite(value) or value == 0:
            continue
        key = (item.entity, item.source, item.supporting_artifact)
        if item.phase == "delta_running":
            running.add((*key, item.metric))

    decisions = []
    for item in items:
        value = _number(item.observed_value)
        key = (item.entity, item.source, item.supporting_artifact)
        if item.metric in _DESCRIPTIVE_METRICS:
            relevant, reason = False, "descriptive_metadata"
        elif item.observed_value is None or item.observed_value == "":
            relevant, reason = False, "missing_value"
        elif value is not None and not math.isfinite(value):
            relevant, reason = False, "nonfinite_value"
        elif value == 0:
            recovered_delta = (
                item.phase == "delta_post" and (*key, item.metric) in running
            )
            relevant = recovered_delta
            # Retain the historical reason token for JSON/confidence compatibility.
            # It denotes phase-supported relevance, not an actual recovery verdict.
            reason = "phase_supported_recovery" if relevant else "zero_without_phase_support"
        elif value is not None:
            relevant, reason = True, "nonzero_observation"
        elif isinstance(item.observed_value, (bool, str)):
            relevant, reason = True, "state_observation"
        else:
            relevant, reason = False, "uninterpreted_value"
        decisions.append({"relevant": relevant, "reason": reason})
    return decisions


def relevant_evidence(items: Iterable[EvidenceItem]) -> List[EvidenceItem]:
    items = list(items)
    return [item for item, decision in zip(items, assess_relevance(items)) if decision["relevant"]]
