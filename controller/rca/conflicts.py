"""Compare explicitly measured observations with identical comparison scope.

No timestamps, units, counter epochs or measurement validity are inferred from
legacy defaults. A disagreement describes source values, not device causality.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Dict, List

from .models import EvidenceItem


def _instant(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return None
        return instant.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _comparison(item: EvidenceItem):
    context = item.metadata.get("comparison_context")
    if not isinstance(context, dict) or context.get("measured") is not True:
        return None
    if not all((item.entity, item.metric, item.phase, item.supporting_artifact)):
        return None
    start, end = _instant(context.get("window_start")), _instant(context.get("window_end"))
    if not start or not end or start >= end:
        return None
    kind = context.get("measurement_kind")
    if kind not in {"gauge", "counter", "delta", "rate"}:
        return None
    if not all(isinstance(context.get(k), str) and context[k].strip()
               for k in ("unit", "population")):
        return None
    epoch = context.get("counter_epoch")
    if kind in {"counter", "delta"} and not (isinstance(epoch, str) and epoch.strip()):
        return None
    # Explicit scope is required even for rate/gauge values. No alias/unit
    # conversion or queue-parent aggregation is attempted here.
    value = item.observed_value
    tolerance = context.get("absolute_tolerance", 0)
    if isinstance(value, bool) or isinstance(tolerance, bool):
        return None
    try:
        value, tolerance = float(value), float(tolerance)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or not math.isfinite(tolerance) or tolerance < 0:
        return None
    key = (item.entity, item.metric, item.phase, start, end, kind,
           context["unit"], context["population"], epoch, tolerance)
    if epoch is not None and not isinstance(epoch, str):
        return None
    return key, value, tolerance


def assess_aligned_conflicts(evidence: List[EvidenceItem]) -> Dict[str, Any]:
    """Return index-linked pair comparisons; unqualified observations stay unknown."""
    groups = defaultdict(list)
    skipped = []
    for index, item in enumerate(evidence):
        comparison = _comparison(item)
        if comparison is None:
            skipped.append(index)
            continue
        key, value, tolerance = comparison
        groups[key].append((index, item, value, tolerance))
    comparable_pairs = 0
    compared_indices = []
    disagreements = []
    for group in groups.values():
        for left, right in combinations(group, 2):
            li, le, lv, tolerance = left
            ri, re, rv, _ = right
            if le.source == re.source:
                continue
            comparable_pairs += 1
            compared_indices.append([li, ri])
            if abs(lv - rv) <= tolerance:
                continue
            disagreements.append({
                "type": "aligned_value_disagreement", "evidence_indices": [li, ri],
                "entity": le.entity, "metric": le.metric, "phase": le.phase,
                "sources": [le.source, re.source],
                "supporting_artifacts": [le.supporting_artifact, re.supporting_artifact],
                "observed_values": [le.observed_value, re.observed_value],
                "comparison_context": dict(le.metadata["comparison_context"]),
                "interpretation": "Aligned reported values differ beyond the supplied tolerance; verify collector semantics and provenance before diagnosis.",
            })
    return {
        "policy_version": "aligned_comparison_v1", "comparable_pair_count": comparable_pairs,
        "compared_evidence_pairs": compared_indices,
        "status": "disagreements_observed" if disagreements else (
            "no_disagreement_in_comparable_pairs" if comparable_pairs else "not_assessed_without_aligned_measurement_windows"),
        "disagreements": disagreements, "unqualified_evidence_indices": skipped,
        "limitations": ["Unqualified observations and unmatched scopes are not agreements.",
                        "Comparison requires explicit measured validity, timezone-aware windows, units, population, phase and counter epoch where applicable.",
                        "Disagreements do not change legacy verdicts or candidate confidence."],
    }
