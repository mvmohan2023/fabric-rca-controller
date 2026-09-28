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
                    metadata={"record_entity": record.get("entity")},
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


def normalize_evidence(
    *,
    root_cause_correlation: Optional[Dict[str, Any]] = None,
    traffic_intent_rca: Optional[Dict[str, Any]] = None,
    fabric_evidence: Optional[Dict[str, Any]] = None,
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

    return items


def serialize_evidence(items: Iterable[EvidenceItem]) -> List[Dict[str, Any]]:
    """Return JSON-compatible normalized evidence without mutating inputs."""

    return [item.to_dict() for item in items]
