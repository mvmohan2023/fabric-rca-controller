"""Normalize existing RCA artifacts into reusable evidence items.

The normalizer is intentionally non-destructive: it reads existing report
shapes and emits additive EvidenceItem objects without changing source data.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .models import EvidenceItem


def _entity(node: Any = None, interface: Any = None, queue: Any = None) -> Optional[str]:
    parts = []
    if node not in (None, ""):
        parts.append(str(node))
    if interface not in (None, ""):
        parts.append(str(interface))
    if queue not in (None, ""):
        parts.append(f"q{queue}")
    return "|".join(parts) or None


def normalize_root_cause_correlation(
    report: Dict[str, Any],
    *,
    supporting_artifact: Optional[str] = None,
) -> List[EvidenceItem]:
    """Normalize top hotspot observations from root_cause_correlation.json."""

    items: List[EvidenceItem] = []
    hotspots = (report or {}).get("summary", {}).get("top_hotspots", []) or []

    for hotspot in hotspots:
        if not isinstance(hotspot, dict):
            continue

        node = hotspot.get("device") or hotspot.get("node")
        interface = hotspot.get("interface")
        entity = _entity(node, interface)

        for metric in (
            "frame_delta",
            "retransmissions",
            "sequence_errors",
            "max_latency_ns",
        ):
            value = hotspot.get(metric)
            if value is None:
                continue
            items.append(
                EvidenceItem(
                    domain="traffic",
                    source="root_cause_correlation",
                    entity=entity,
                    metric=metric,
                    observed_value=value,
                    severity=hotspot.get("highest_severity"),
                    classification=hotspot.get("classification"),
                    supporting_artifact=supporting_artifact,
                    metadata={
                        "rx_port": hotspot.get("rx_port"),
                        "tags": hotspot.get("tags", []),
                    },
                )
            )

    return items


def normalize_traffic_intent_rca(
    report: Dict[str, Any],
    *,
    supporting_artifact: Optional[str] = None,
) -> List[EvidenceItem]:
    """Normalize the selected path-aligned hotspot from traffic-intent RCA."""

    summary = (report or {}).get("rca_summary")
    if not isinstance(summary, dict):
        return []

    node = summary.get("node")
    interface = summary.get("interface")
    queue = summary.get("queue")
    entity = _entity(node, interface, queue)
    items: List[EvidenceItem] = []

    signals = summary.get("signals", {}) or {}
    if isinstance(signals, dict):
        for metric, value in signals.items():
            if value is None:
                continue
            items.append(
                EvidenceItem(
                    domain="traffic",
                    source="traffic_intent_rca",
                    entity=entity,
                    metric=str(metric),
                    observed_value=value,
                    severity=summary.get("severity"),
                    classification=summary.get("intent_cause"),
                    supporting_artifact=supporting_artifact,
                    metadata={
                        "intent_name": report.get("intent_name"),
                        "score": summary.get("score"),
                        "probable_cause": summary.get("probable_cause"),
                    },
                )
            )

    return items


def normalize_fabric_evidence(
    report: Dict[str, Any],
    *,
    supporting_artifact: Optional[str] = None,
) -> List[EvidenceItem]:
    """Normalize DUT-side snapshot and anomaly evidence."""

    items: List[EvidenceItem] = []

    for interface_entry in (report or {}).get("interfaces", []) or []:
        if not isinstance(interface_entry, dict):
            continue

        entity = _entity(
            interface_entry.get("device"),
            interface_entry.get("interface"),
        )

        for record in interface_entry.get("snapshot_records", []) or []:
            if not isinstance(record, dict):
                continue
            items.append(
                EvidenceItem(
                    domain="fabric",
                    source="fabric_evidence",
                    entity=entity,
                    metric=record.get("metric"),
                    observed_value=record.get("value"),
                    classification=record.get("category"),
                    supporting_artifact=supporting_artifact,
                    metadata={
                        "record_entity": record.get("entity"),
                        **({"comparison_context": record["comparison_context"]}
                           if isinstance(record.get("comparison_context"), dict) else {}),
                    },
                )
            )

        for anomaly in interface_entry.get("anomalies", []) or []:
            if not isinstance(anomaly, dict):
                continue
            items.append(
                EvidenceItem(
                    domain="fabric",
                    source="fabric_evidence",
                    entity=entity,
                    metric=anomaly.get("metric") or anomaly.get("type"),
                    observed_value=anomaly.get("value"),
                    severity=anomaly.get("severity"),
                    classification=anomaly.get("type") or "anomaly",
                    supporting_artifact=supporting_artifact,
                    metadata=dict(anomaly),
                )
            )

    return items



def normalize_queue_cos_evidence(
    report: Dict[str, Any],
    *,
    supporting_artifact: Optional[str] = None,
) -> List[EvidenceItem]:
    """Normalize queue/CoS hotspot evidence from an RCA UI report.

    The adapter consumes the existing evidence_index shape. Feature-specific
    classification, scoring, and threshold semantics remain owned by the
    existing congestion/CoS analyzers.
    """

    items: List[EvidenceItem] = []
    evidence_index = (report or {}).get("evidence_index", {}) or {}
    if not isinstance(evidence_index, dict):
        return items

    for entity_id, entry in evidence_index.items():
        if not isinstance(entry, dict):
            continue

        node = entry.get("node")
        interface = entry.get("interface")
        queue = entry.get("queue")
        entity = str(entity_id or _entity(node, interface, queue) or "").strip() or None

        common = {
            "domain": "queue",
            "source": "rca_ui_evidence_index",
            "entity": entity,
            "severity": entry.get("severity"),
            "classification": (
                entry.get("classification")
                or entry.get("probable_cause")
                or entry.get("event_delta_classification")
            ),
            "supporting_artifact": supporting_artifact,
        }

        metadata_base = {
            "node": node,
            "interface": interface,
            "queue": queue,
            "forwarding_class": entry.get("forwarding_class"),
            "score": entry.get("score"),
            "probable_cause": entry.get("probable_cause"),
            "event_delta_classification": entry.get("event_delta_classification"),
            "tail_linger_trend": entry.get("tail_linger_trend"),
            "ecn_linger_trend": entry.get("ecn_linger_trend"),
            "recovery_ratio_tail": entry.get("recovery_ratio_tail"),
            "classification_confidence": entry.get("classification_confidence"),
            "pre_tail_baseline_series": entry.get("pre_tail_baseline_series", []),
            "post_tail_linger_series": entry.get("post_tail_linger_series", []),
        }

        for bucket_name, bucket in (
            ("signals", entry.get("signals", {}) or {}),
            ("delta_running", entry.get("delta_running", {}) or {}),
            ("delta_post", entry.get("delta_post", {}) or {}),
            ("running_metrics", entry.get("running_metrics", {}) or {}),
        ):
            if not isinstance(bucket, dict):
                continue
            for metric, value in bucket.items():
                if value is None:
                    continue
                items.append(
                    EvidenceItem(
                        **common,
                        metric=str(metric),
                        observed_value=value,
                        phase=bucket_name,
                        metadata={**metadata_base, "evidence_bucket": bucket_name},
                    )
                )

        for metric in (
            "rise_tail_dropped_packets",
            "linger_tail_dropped_packets",
            "rise_ecn_ce_packets",
            "linger_ecn_ce_packets",
            "recovery_ratio_tail",
            "classification_confidence",
        ):
            value = entry.get(metric)
            if value is None:
                continue
            items.append(
                EvidenceItem(
                    **common,
                    metric=metric,
                    observed_value=value,
                    phase="phase_aware",
                    metadata={**metadata_base, "evidence_bucket": "phase_aware"},
                )
            )

    return items

def normalize_evidence(
    *,
    root_cause_correlation: Optional[Dict[str, Any]] = None,
    traffic_intent_rca: Optional[Dict[str, Any]] = None,
    fabric_evidence: Optional[Dict[str, Any]] = None,
    queue_cos_evidence: Optional[Dict[str, Any]] = None,
    artifact_paths: Optional[Dict[str, str]] = None,
) -> List[EvidenceItem]:
    """Normalize supported existing RCA artifacts into one evidence list."""

    paths = artifact_paths or {}
    items: List[EvidenceItem] = []

    if root_cause_correlation:
        items.extend(
            normalize_root_cause_correlation(
                root_cause_correlation,
                supporting_artifact=paths.get("root_cause_correlation"),
            )
        )

    if traffic_intent_rca:
        items.extend(
            normalize_traffic_intent_rca(
                traffic_intent_rca,
                supporting_artifact=paths.get("traffic_intent_rca"),
            )
        )

    if fabric_evidence:
        items.extend(
            normalize_fabric_evidence(
                fabric_evidence,
                supporting_artifact=paths.get("fabric_evidence"),
            )
        )

    if queue_cos_evidence:
        items.extend(
            normalize_queue_cos_evidence(
                queue_cos_evidence,
                supporting_artifact=paths.get("queue_cos_evidence"),
            )
        )

    return items


def serialize_evidence(items: Iterable[EvidenceItem]) -> List[Dict[str, Any]]:
    """Return JSON-compatible normalized evidence without mutating inputs."""

    return [item.to_dict() for item in items]
