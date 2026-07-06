from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_TS_RE = re.compile(r"(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
_NH_RE = re.compile(r"(?:nhIndex|Nexthop: index|index)\s*[=: ]+\s*(?P<nh>\d+)", re.I)
_GUID_RE = re.compile(r"GUID[:= ]+\s*(?P<guid>\d+)", re.I)


def _safe_read_text(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(errors="ignore")


def _extract_ts(line: str) -> Optional[str]:
    m = _TS_RE.search(line)
    return m.group("ts") if m else None


def _extract_nh(line: str) -> Optional[str]:
    m = _NH_RE.search(line)
    return m.group("nh") if m else None


def _extract_guid(line: str) -> Optional[str]:
    m = _GUID_RE.search(line)
    return m.group("guid") if m else None


def analyze_ecmp_hierarchy_lifecycle(
    *,
    run_id: str,
    pfe_log_path: str,
    objmon_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:

    """
    Detects stale ECMP / route-NH hierarchy transition symptoms.

    Targets PR1873879-style issue:
      - route moves from old ECMP NH to new ECMP NH
      - old ECMP delete is attempted before route transition is safe
      - SDK delete/destroy fails
      - stale ECMP token/reference remains
    """

    pfe_text = _safe_read_text(pfe_log_path)
    objmon_text = _safe_read_text(objmon_path) if objmon_path else ""

    events: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []

    # --- PFE / controller trace signatures ---
    signatures = {
        "new_ecmp_add": [
            "BQAdd",
            "Nexthop",
            "unilist",
        ],
        "app_incomplete": [
            "set to app incomplete",
        ],
        "route_incomplete": [
            "Type:Route",
            "set to app incomplete",
        ],
        "link_deletion": [
            "NotifyLinkDeletion",
        ],
        "old_unilist_delete": [
            "OnDelete",
            "Nexthop",
        ],
        "sdk_ecmp_destroy_failure": [
            "bcm_l3_egress_ecmp_destroy",
        ],
        "operation_still_running": [
            "Operation still running",
        ],
        "entry_found_for_delete": [
            "EntryFoundForDelete",
        ],
        "remove_nh_from_ifd": [
            "Remove NH from IFD",
        ],
    }

    for lineno, line in enumerate(pfe_text.splitlines(), start=1):
        low = line.lower()

        for event_type, needles in signatures.items():
            if all(n.lower() in low for n in needles):
                events.append(
                    {
                        "source": "pfe_log",
                        "line": lineno,
                        "timestamp": _extract_ts(line),
                        "event_type": event_type,
                        "nh_index": _extract_nh(line),
                        "guid": _extract_guid(line),
                        "raw": line.strip()[:1000],
                    }
                )

    # --- Objmon object ordering signatures ---
    objmon_patterns = {
        "addr_resolve_req": "AddrResolveReq",
        "addr_resolve_resp": "AddrResolveResp",
        "route_modify": "object_type\": \"Route",
        "nexthop_modify": "object_type\": \"Nexthop",
        "object_delete": "operation_type\": \"Delete",
        "object_add_modify": "operation_type\": \"Add/Modify",
    }

    for lineno, line in enumerate(objmon_text.splitlines(), start=1):
        for event_type, needle in objmon_patterns.items():
            if needle in line:
                events.append(
                    {
                        "source": "objmon",
                        "line": lineno,
                        "timestamp": _extract_ts(line),
                        "event_type": event_type,
                        "nh_index": _extract_nh(line),
                        "guid": _extract_guid(line),
                        "raw": line.strip()[:1000],
                    }
                )

    event_types = {e["event_type"] for e in events}

    has_destroy_failure = (
        "sdk_ecmp_destroy_failure" in event_types
        or "operation_still_running" in event_types
    )

    has_incomplete = (
        "app_incomplete" in event_types
        or "route_incomplete" in event_types
    )

    has_link_delete = "link_deletion" in event_types
    has_old_delete = "old_unilist_delete" in event_types or "object_delete" in event_types
    has_addr_resp = "addr_resolve_resp" in event_types

    if has_destroy_failure:
        findings.append(
            {
                "type": "sdk_ecmp_destroy_failure",
                "severity": "high",
                "reason": "PFE/SDK reported ECMP destroy failure, matching stale ECMP token symptom.",
            }
        )

    if has_incomplete and has_link_delete:
        findings.append(
            {
                "type": "incomplete_hierarchy_with_link_delete",
                "severity": "high",
                "reason": "Route/NH hierarchy was marked incomplete while link deletion notification was processed.",
            }
        )

    if has_old_delete and has_addr_resp and has_incomplete:
        findings.append(
            {
                "type": "possible_out_of_order_ecmp_transition",
                "severity": "high",
                "reason": "Old ECMP delete appears in same transition window as incomplete NH/route and later address resolution.",
            }
        )

    if has_destroy_failure and has_old_delete:
        verdict = "fail"
        root_cause = "stale_ecmp_reference_or_out_of_order_delete"
        confidence = "high"
    elif findings:
        verdict = "warn"
        root_cause = "possible_ecmp_hierarchy_transition_risk"
        confidence = "medium"
    else:
        verdict = "pass"
        root_cause = "no_stale_ecmp_lifecycle_signal_detected"
        confidence = "low"

    report = {
        "run_id": run_id,
        "analysis_type": "ecmp_hierarchy_lifecycle",
        "verdict": verdict,
        "root_cause": root_cause,
        "confidence": confidence,
        "summary": {
            "total_events": len(events),
            "finding_count": len(findings),
            "has_sdk_destroy_failure": has_destroy_failure,
            "has_incomplete_hierarchy": has_incomplete,
            "has_link_deletion": has_link_delete,
            "has_old_ecmp_delete": has_old_delete,
            "has_addr_resolve_resp": has_addr_resp,
        },
        "findings": findings,
        "events": events[:500],
        "source_files": {
            "pfe_trace": pfe_log_path,
            "objmon": objmon_path,
        },
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))

    return report
