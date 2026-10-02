"""Read existing campaign evidence and write a separate Engineering RCA artifact.

Legacy summary, validation, reasoning and UI artifacts are never rewritten.
This artifact describes evidence correlation, not proven fault causality.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict

from controller.utils import atomic_write_json
from .correlation import correlate_hierarchical_by_entity, serialize_candidates
from .evidence_normalizer import normalize_evidence, serialize_evidence
from .relevance import assess_relevance


def _read_object(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def build_engineering_rca_report(case_summary_path: str, *, inventory: Dict[str, Any]) -> Dict[str, Any]:
    case_path = Path(case_summary_path).resolve()
    summary = _read_object(case_path)
    files = summary.get("files") or {}
    if not isinstance(files, dict):
        raise ValueError("Case summary files must be an object")
    inputs, paths, availability = {}, {}, {}
    sources = {
        "root_cause_correlation": ("root_cause_correlation", "root_cause_correlation.json"),
        "traffic_intent_rca": ("traffic_intent_rca", "traffic_intent_rca.json"),
        "fabric_evidence": ("fabric_evidence", "fabric_evidence.json"),
        "queue_cos_evidence": ("rca_ui_report", "rca_ui_report.json"),
    }
    for name, (file_key, filename) in sources.items():
        explicit = files.get(file_key)
        path = case_path.parent / filename
        if isinstance(explicit, str) and explicit:
            path = Path(explicit)
            if not path.is_absolute() and not path.exists():
                path = case_path.parent / explicit
        path = path.resolve()
        paths[name] = str(path)
        if not path.is_file():
            availability[name] = {"status": "missing", "path": str(path)}
            continue
        try:
            inputs[name] = _read_object(path)
            availability[name] = {"status": "loaded", "path": str(path)}
        except (OSError, ValueError) as exc:
            availability[name] = {"status": "invalid", "path": str(path), "error": str(exc)}

    evidence = normalize_evidence(**inputs, artifact_paths=paths)
    decisions = assess_relevance(evidence)
    candidates = correlate_hierarchical_by_entity(evidence, inventory=inventory)
    return {
        "schema_version": "1.0",
        "run_id": summary.get("run_id"),
        "analysis_type": "evidence_correlation",
        "status": "OBSERVATIONS" if candidates else "INSUFFICIENT_EVIDENCE",
        "source_case_summary": str(case_path),
        "source_availability": availability,
        "evidence_summary": {
            "total": len(evidence),
            "relevant": sum(d["relevant"] for d in decisions),
            "context": sum(not d["relevant"] for d in decisions),
            "relevance_reasons": dict(Counter(d["reason"] for d in decisions)),
        },
        "evidence": serialize_evidence(evidence),
        "evidence_relevance": decisions,
        "candidates": serialize_candidates(candidates),
        "limitations": [
            "Correlation does not establish event causality or a device-health verdict.",
            "Confidence describes relevant evidence diversity and traceability.",
            "Defaultable zeros require matching phase evidence to support recovery.",
            "Missing or invalid sources remain explicit; they are not healthy observations.",
        ],
    }


def write_engineering_rca_report(case_summary_path: str, *, inventory: Dict[str, Any]) -> str:
    """Write only the dedicated sidecar in the campaign directory."""
    case_path = Path(case_summary_path).resolve()
    output = case_path.parent / "engineering_rca_report.json"
    if output == case_path:
        raise ValueError("Engineering RCA output must not replace the case summary")
    report = build_engineering_rca_report(str(case_path), inventory=inventory)
    input_paths = {Path(entry["path"]) for entry in report["source_availability"].values()}
    if output in input_paths:
        raise ValueError("Engineering RCA output must not replace source evidence")
    atomic_write_json(str(output), report, indent=2, sort_keys=False)
    return str(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-summary", required=True)
    parser.add_argument("--inventory", required=True)
    args = parser.parse_args()
    output = write_engineering_rca_report(args.case_summary, inventory=_read_object(Path(args.inventory)))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
