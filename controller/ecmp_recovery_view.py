from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple
import re
import json
from pathlib import Path
from collections import defaultdict
import traceback


# ============================================================
# Conservative enums / constants
# ============================================================

ANALYSIS_COMPLETE = "complete"
ANALYSIS_PARTIAL = "partial_data"
ANALYSIS_INSUFFICIENT = "insufficient_data"

BASELINE_HEALTHY_SPEED_WEIGHTED = "healthy_speed_weighted"
BASELINE_HEALTHY_MINOR_SKEW = "healthy_minor_skew"
BASELINE_UNHEALTHY_PREEXISTING = "unhealthy_preexisting_skew"
BASELINE_UNKNOWN = "unknown"

RECOVERY_CONVERGED = "converged"
RECOVERY_PARTIAL = "partial"
RECOVERY_NOT_CONVERGED = "not_converged"
RECOVERY_OSCILLATING = "oscillating"
RECOVERY_UNKNOWN = "unknown"

SPEED_ALIGNED = "aligned"
SPEED_MILDLY_MISALIGNED = "mildly_misaligned"
SPEED_MISALIGNED = "misaligned"
SPEED_ALIGNMENT_UNKNOWN = "unknown"

DOMINANT_NONE = "none"
DOMINANT_TRANSIENT = "transient"
DOMINANT_PERSISTENT = "persistent"
DOMINANT_UNKNOWN = "unknown"

DELTA_IMPROVED = "improved"
DELTA_UNCHANGED = "unchanged"
DELTA_DEGRADED = "degraded"
DELTA_RECOVERED_FROM_EVENT = "recovered_from_event"
DELTA_WORSENED_VS_BASELINE = "worsened_vs_baseline"
DELTA_UNKNOWN = "unknown"

VERDICT_EXPECTED = "expected"
VERDICT_ACCEPTABLE = "acceptable"
VERDICT_WATCH = "watch"
VERDICT_ABNORMAL = "abnormal"
VERDICT_DEFECT = "defect_candidate"

CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"


DEFAULT_CONFIG: Dict[str, Any] = {
    "min_baseline_samples": 1,
    "min_recovery_samples": 2,
    "same_speed_minor_skew_ratio": 1.50,
    "same_speed_unhealthy_skew_ratio": 2.00,
    "group_alignment_minor_tolerance": 0.20,
    "group_alignment_major_tolerance": 0.35,
    "dominant_member_share_threshold": 0.55,
    "dominant_member_persistence_fraction": 0.60,
    "oscillation_dominant_change_threshold": 2,
    "require_baseline_healthy_for_defect": True,
    "same_speed_balanced_spread_ratio": 1.25,
    "same_speed_mild_skew_spread_ratio": 1.75,
}


# ============================================================
# Models
# ============================================================

@dataclass
class QueueEvidence:
    queue_name: str
    severity: str = "unknown"
    behavior: str = "unknown"
    role: str = "unknown"
    dlb_relevance: str = "weak"
    summary: str = ""


@dataclass
class MemberPressureSummary:
    member: str
    dlb_signal_strength: str = "none"
    member_pressure_state: str = "healthy"
    member_pressure_summary: str = ""
    queue_evidence: List[QueueEvidence] = field(default_factory=list)


@dataclass
class TargetRecoveryResult:
    target_id: str
    analysis_status: str = ANALYSIS_INSUFFICIENT
    baseline_state: str = BASELINE_UNKNOWN
    recovery_convergence_state: str = RECOVERY_UNKNOWN
    speed_alignment_state: str = SPEED_ALIGNMENT_UNKNOWN
    dominant_port_state: str = DOMINANT_UNKNOWN
    delta_outcome: str = DELTA_UNKNOWN
    recovery_verdict: str = VERDICT_WATCH
    confidence: str = CONF_LOW
    member_pressure_summary: str = ""
    reason_codes: List[str] = field(default_factory=list)

    target_port_speed_gbps: Optional[float] = None
    target_port_speed_label: str = "unknown"

    expected_group_shares: Dict[str, float] = field(default_factory=dict)
    baseline_group_shares: Dict[str, float] = field(default_factory=dict)
    recovery_group_shares: Dict[str, float] = field(default_factory=dict)
    baseline_members: List[Dict[str, Any]] = field(default_factory=list)
    recovery_members: List[Dict[str, Any]] = field(default_factory=list)
    member_pressure: List[Dict[str, Any]] = field(default_factory=list)
    baseline_same_speed_group_view: List[Dict[str, Any]] = field(default_factory=list)
    recovery_same_speed_group_view: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================
# Generic helpers
# ============================================================

def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_member_list(members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure every member entry has:
      member, speed_gbps, share/raw_rate
    If share missing and raw_rate present, derive normalized share.
    """
    out: List[Dict[str, Any]] = []
    for m in members or []:
        item = dict(m)
        item["member"] = str(
            item.get("member")
            or item.get("interface")
            or item.get("port")
            or "unknown"
        )
        if "speed_gbps" not in item:
            item["speed_gbps"] = _safe_float(
                item.get("speed")
                or item.get("member_speed_gbps")
                or item.get("link_speed_gbps")
            )
        else:
            item["speed_gbps"] = _safe_float(item.get("speed_gbps"))

        if "share" in item:
            item["share"] = _safe_float(item.get("share"))
        if "raw_rate" in item:
            item["raw_rate"] = _safe_float(item.get("raw_rate"))
        out.append(item)

    missing_share = any(x.get("share") is None for x in out)
    if missing_share:
        total_rate = sum((_safe_float(x.get("raw_rate")) or 0.0) for x in out)
        if total_rate > 0:
            for x in out:
                if x.get("share") is None:
                    rr = _safe_float(x.get("raw_rate")) or 0.0
                    x["share"] = rr / total_rate
    return out

def _split_target_id(target_id: str) -> tuple[str, str]:
    s = str(target_id or "").strip()
    if ":" in s:
        node, iface = s.split(":", 1)
        return node.strip(), iface.strip()
    if "|" in s:
        node, iface = s.split("|", 1)
        return node.strip(), iface.strip()
    return s, ""


def _lookup_member_speed_gbps(
    interface_speed_map: Dict[str, Dict[str, float]],
    target_node: str,
    iface: str,
) -> Optional[float]:
    """
    Exact-match speed lookup for ECMP members, scoped to target node.
    """
    target_node = str(target_node or "").strip()
    iface = _normalize_ecmp_member_name(iface)

    node_map = interface_speed_map.get(target_node, {})
    if iface in node_map:
        return node_map[iface]

    # Never fall back from et-x/y/z:n to parent et-x/y/z
    if ":" in iface:
        return None

    return node_map.get(iface)


def _normalize_speed_to_gbps(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    try:
        if s.endswith("G"):
            return float(s[:-1])
        return float(s)
    except Exception:
        return None


def _build_interface_speed_map(case_summary: Dict[str, Any]) -> Dict[str, float]:
    """
    Build a flat interface -> speed_gbps map from device facts.
    We only need interface-level lookup, not per-node keys, because the
    same interface names used in ECMP target/member sets are already node-scoped
    by allowed_members filtering.
    """
    speed_map: Dict[str, float] = {}

    facts_dir = Path("artifacts") / "device_facts"
    if not facts_dir.exists():
        return speed_map

    for facts_file in facts_dir.glob("*_facts.json"):
        try:
            data = json.loads(facts_file.read_text())
        except Exception:
            continue

        iface_speeds = data.get("interface_speeds", {}) or {}
        for iface, speed in iface_speeds.items():
            gbps = _normalize_speed_to_gbps(speed)
            if gbps is not None:
                speed_map[str(iface).strip()] = gbps

    return speed_map

def _group_key_for_speed(speed_gbps: Optional[float]) -> str:
    if speed_gbps is None:
        return "unknown"
    if float(speed_gbps).is_integer():
        return f"{int(speed_gbps)}G"
    return f"{speed_gbps}G"


def _build_speed_groups(members: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for m in members:
        gk = _group_key_for_speed(_safe_float(m.get("speed_gbps")))
        groups.setdefault(gk, []).append(m)
    return groups


def _expected_group_shares(groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
    caps: Dict[str, float] = {}
    total = 0.0
    for gk, gmembers in groups.items():
        cap = sum((_safe_float(x.get("speed_gbps")) or 0.0) for x in gmembers)
        caps[gk] = cap
        total += cap
    if total <= 0:
        return {gk: 0.0 for gk in groups.keys()}
    return {gk: cap / total for gk, cap in caps.items()}


def _actual_group_shares(groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
    return {
        gk: sum((_safe_float(x.get("share")) or 0.0) for x in gmembers)
        for gk, gmembers in groups.items()
    }


def _same_speed_spread_ratio(groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[float]]:
    ratios: Dict[str, Optional[float]] = {}
    for gk, gmembers in groups.items():
        shares = [(_safe_float(x.get("share")) or 0.0) for x in gmembers]
        shares = [s for s in shares if s > 0]
        if len(shares) < 2:
            ratios[gk] = None
            continue
        mn = min(shares)
        mx = max(shares)
        ratios[gk] = (mx / mn) if mn > 0 else None
    return ratios


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


# ============================================================
# Input adapter
# ============================================================

def _extract_targets(case_summary: Dict[str, Any], ui_report: Dict[str, Any]) -> List[str]:
    """
    Prefer normalized ECMP interface targets if already built.
    Fall back to case summary only when ECMP input is absent.
    """
    ecmp_input = ui_report.get("ecmp_recovery_input") or {}
    targets_map = ecmp_input.get("targets") or {}
    if isinstance(targets_map, dict) and targets_map:
        return list(targets_map.keys())

    raw = (
        case_summary.get("resolved_targets")
        or case_summary.get("targets")
        or case_summary.get("nodes")
        or []
    )

    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                node = item.get("node")
                interface = item.get("interface")
                if node and interface:
                    out.append(f"{node}:{interface}")
                elif node:
                    out.append(str(node))
            else:
                val = str(item).strip()
                if val:
                    out.append(val)
        if out:
            return out

    if isinstance(raw, str):
        vals = [x.strip() for x in raw.split(",") if x.strip()]
        if vals:
            return vals

    return []

def _normalize_sample_item(sample_item: Any) -> List[Dict[str, Any]]:
    """
    Supports:
      [ {...}, {...} ]
      { "members": [ {...}, {...} ] }
    """
    if isinstance(sample_item, list):
        return _normalize_member_list(sample_item)
    if isinstance(sample_item, dict):
        members = sample_item.get("members")
        if isinstance(members, list):
            return _normalize_member_list(members)
    return []


def _extract_target_samples(ui_report: Dict[str, Any], target_id: str) -> Tuple[List[List[Dict[str, Any]]], List[List[Dict[str, Any]]]]:
    """
    Reads from ui_report["ecmp_recovery_input"]["targets"][target_id]
    """
    ecmp_input = ui_report.get("ecmp_recovery_input") or {}
    per_target = (ecmp_input.get("targets") or {}).get(target_id, {})

    baseline_samples: List[List[Dict[str, Any]]] = []
    recovery_samples: List[List[Dict[str, Any]]] = []

    for item in per_target.get("baseline_samples") or []:
        normalized = _normalize_sample_item(item)
        if normalized:
            baseline_samples.append(normalized)

    for item in per_target.get("recovery_samples") or []:
        normalized = _normalize_sample_item(item)
        if normalized:
            recovery_samples.append(normalized)

    if not baseline_samples and not recovery_samples:
        # fallback generic samples list
        for item in per_target.get("samples") or []:
            phase = str(item.get("phase") or "").lower()
            normalized = _normalize_sample_item(item)
            if not normalized:
                continue
            if phase == "baseline":
                baseline_samples.append(normalized)
            elif phase in ("recovery", "recover", "post"):
                recovery_samples.append(normalized)

    return baseline_samples, recovery_samples


def _extract_target_hotspots(ui_report: Dict[str, Any], target_id: str) -> List[Dict[str, Any]]:
    """
    Reuse existing hotspot evidence, but do not mutate it.
    """
    out: List[Dict[str, Any]] = []

    ecmp_input = ui_report.get("ecmp_recovery_input") or {}
    per_target = (ecmp_input.get("targets") or {}).get(target_id, {})
    out.extend(per_target.get("member_hotspots") or [])

    for h in ui_report.get("all_hotspots") or []:
        hid = str(
            h.get("target_id")
            or h.get("entity_id")
            or h.get("interface")
            or ""
        )
        if target_id and hid and (target_id in hid or hid in target_id):
            out.append(h)

    cos_health = ui_report.get("cos_health") or {}
    for h in cos_health.get("hotspots") or []:
        hid = str(
            h.get("target_id")
            or h.get("entity_id")
            or h.get("interface")
            or ""
        )
        if target_id and hid and (target_id in hid or hid in target_id):
            out.append(h)

    return out



def _extract_interface_tx_bytes(
    file_path: Path,
    *,
    target_node: str,
    allowed_members: set[str],
) -> dict:
    """
    Parse one ECMP telemetry file and return:
      { interface_name: tx_bytes }

    Scope strictly to:
    - target node
    - allowed member interfaces
    """
    data = json.loads(file_path.read_text())
    interface_bytes = defaultdict(int)

    target_node = str(target_node or "").strip()
    allowed_members = set(
        _normalize_ecmp_member_name(x)
        for x in (allowed_members or set())
    )

    for node in data.get("nodes", []):
        node_name = str(
            node.get("node")
            or node.get("name")
            or node.get("hostname")
            or ""
        ).strip()

        if target_node and node_name and node_name != target_node:
            continue

        for sub in node.get("subscriptions", []):
            for entry in sub.get("raw", []):
                prefix = entry.get("prefix", "")

                m = re.search(r"interface\[name=(.*?)\]", prefix)
                if not m:
                    continue
                iface = _normalize_ecmp_member_name(m.group(1))

                if allowed_members and iface not in allowed_members:
                    continue
                for upd in entry.get("updates", []):
                    if upd.get("Path") == "txBytes":
                        val = upd.get("values", {}).get("txBytes", 0)
                        try:
                            interface_bytes[iface] += int(val)
                        except Exception:
                            try:
                                interface_bytes[iface] += int(float(val))
                            except Exception:
                                pass

    return dict(interface_bytes)

def _normalize_ecmp_member_name(name: str) -> str:
    """
    Normalize ECMP interface/member names so both telemetry and artifact naming
    can be compared safely.

    Example:
      et-0/0/11:0 <-> et-0/0/11~0
    """
    return str(name or "").strip().replace("~", ":")


def _build_samples_from_files(
    file_list,
    *,
    target_node: str,
    allowed_members: set[str],
    interface_speed_map: Dict[str, Dict[str, float]],
):
    """
    Convert list of files -> list of ECMP samples.
    Each sample is a list of members with:
      member, share, speed_gbps

    Only include interfaces that are part of the target node's allowed member set.
    """
    samples = []

    for f in file_list:
        iface_bytes = _extract_interface_tx_bytes(
            f,
            target_node=target_node,
            allowed_members=allowed_members,
        )

        total = sum(iface_bytes.values())
        if total == 0:
            continue

        members = []
        for iface, val in sorted(iface_bytes.items()):

            normalized_iface = _normalize_ecmp_member_name(iface)

            members.append({
                "member": normalized_iface,
                "share": val / total,
                "speed_gbps": _lookup_member_speed_gbps(
                    interface_speed_map,
                    target_node,
                    normalized_iface,
                ),
            })

        samples.append(members)

    return samples

def _extract_interface_from_target_id(target_id: str) -> str:
    if not target_id:
        return ""
    if ":" in target_id:
        parts = target_id.split(":", 1)
        if len(parts) == 2:
            return str(parts[1]).strip().replace("~", ":")
    if "|" in target_id:
        parts = target_id.split("|", 1)
        if len(parts) == 2:
            return str(parts[1]).strip().replace("~", ":")
    return ""


def _infer_target_port_speed(
    target_id: str,
    baseline_members: List[Dict[str, Any]],
    recovery_members: List[Dict[str, Any]],
) -> Tuple[Optional[float], str]:
    target_iface = _extract_interface_from_target_id(target_id)
    if not target_iface:
        return None, "unknown"

    for member in (recovery_members or []) + (baseline_members or []):
        member_name = str(member.get("member") or "").strip().replace("~", ":")
        if member_name == target_iface:
            speed = _safe_float(member.get("speed_gbps"))
            if speed is None:
                return None, "unknown"
            if float(speed).is_integer():
                return speed, f"{int(speed)}G"
            return speed, f"{speed}G"

    return None, "unknown"

def _normalize_ecmp_member_name(name: str) -> str:
    return str(name or "").strip().replace("~", ":")

def _build_interface_speed_map(case_summary: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Build node-scoped interface speed map:
      {
        "leaf1": {"et-0/0/11:0": 400.0, ...},
        "leaf7": {"et-6/0/0": 400.0, ...},
      }
    """
    facts_dir = Path("artifacts") / "device_facts"
    speed_map: Dict[str, Dict[str, float]] = {}

    for facts_file in facts_dir.glob("*_facts.json"):
        try:
            data = json.loads(facts_file.read_text())
        except Exception:
            continue

        # infer node name from filename like leaf1_facts.json
        node_name = facts_file.name.replace("_facts.json", "").strip()
        if not node_name:
            continue

        node_map = speed_map.setdefault(node_name, {})

        iface_speeds = data.get("interface_speeds", {}) or {}
        for iface, speed in iface_speeds.items():
            key = _normalize_ecmp_member_name(iface)
            s = str(speed).upper().strip()
            if s.endswith("G"):
                try:
                    node_map[key] = float(s[:-1])
                except Exception:
                    pass

    return speed_map

def build_ecmp_recovery_input_from_existing_artifacts(case_summary, ui_report):
    """
    Build ECMP input dynamically from telemetry files.

    Critical fix:
    - scope samples to the target node
    - scope members to the discovered target set for that node
    """
    run_id = case_summary.get("run_id")
    base = Path("artifacts") / "campaigns" / run_id / "telemetry"

    if not base.exists():
        return {"targets": {}}

    grouped = defaultdict(lambda: {"pre": [], "recover": []})

    for f in base.glob("ecmp_*_hotspot_congestion_qmon_phase.json"):
        name = f.name

        # Match both:
        #   ecmp_pre_leaf1_et-0_0_12_0_1_hotspot_congestion_qmon_phase.json
        #   ecmp_pre_leaf7_et-7_0_14_1_hotspot_congestion_qmon_phase.json
        m = re.match(
            r"ecmp_(pre|recover)_(leaf\d+)_(et-[^_]+(?:_[^_]+)+)_(\d+)_hotspot_congestion_qmon_phase\.json$",
            name,
        )
        if not m:
            continue

        phase, node, iface_raw, sample_idx = m.groups()
        parts = iface_raw.split("_")

        if len(parts) < 3:
            continue

        base_iface = f"{parts[0]}/{parts[1]}/{parts[2]}"

        # old channelized/member style:
        # et-0_0_12_0 -> et-0/0/12:0
        # new physical style:
        # et-7_0_14 -> et-7/0/14
        if len(parts) == 4:
            iface = f"{base_iface}:{parts[3]}"
        elif len(parts) == 3:
            iface = base_iface
        else:
            # unexpected shape; skip instead of inventing bad interface
            continue

        target_id = f"{node}:{iface}"
        grouped[target_id][phase].append(f)

    if not grouped:
        return {"targets": {}}

    # Build node -> allowed member set from discovered targets
    allowed_members_by_node: Dict[str, set[str]] = defaultdict(set)
    for target_id in grouped.keys():
        node, iface = _split_target_id(target_id)
        if node and iface:
            allowed_members_by_node[node].add(iface)

    interface_speed_map = _build_interface_speed_map(case_summary)
    targets = {}

    for target_id, files in grouped.items():
        target_node, _target_iface = _split_target_id(target_id)
        allowed_members = allowed_members_by_node.get(target_node, set())

        baseline_files = sorted(files["pre"])
        recovery_files = sorted(files["recover"])

        baseline_samples = _build_samples_from_files(
            baseline_files,
            target_node=target_node,
            allowed_members=allowed_members,
            interface_speed_map=interface_speed_map,
        )
        recovery_samples = _build_samples_from_files(
            recovery_files,
            target_node=target_node,
            allowed_members=allowed_members,
            interface_speed_map=interface_speed_map,
        )

        targets[target_id] = {
            "baseline_samples": baseline_samples,
            "recovery_samples": recovery_samples,
            "allowed_members": sorted(_normalize_ecmp_member_name(x) for x in allowed_members),
        }

    return {"targets": targets}

def _safe_pct(value: Optional[float]) -> float:
    try:
        return float(value or 0.0) * 100.0
    except Exception:
        return 0.0


def _classify_same_speed_fairness(
    *,
    member_count: int,
    expected_equal_member_share: float,
    min_member_share: float,
    max_member_share: float,
    spread_ratio: Optional[float],
    cfg: Dict[str, Any],
) -> str:
    """
    Classify fairness within same-speed members.

    Suggested defaults:
      balanced    -> spread_ratio <= 1.25
      mild_skew   -> spread_ratio <= 1.75
      skewed      -> otherwise
    """
    if member_count <= 1:
        return "not_applicable"

    if spread_ratio is None:
        return "unknown"

    balanced_thr = float(cfg.get("same_speed_balanced_spread_ratio", 1.25))
    mild_thr = float(cfg.get("same_speed_mild_skew_spread_ratio", 1.75))

    if spread_ratio <= balanced_thr:
        return "balanced"
    if spread_ratio <= mild_thr:
        return "mild_skew"
    return "skewed"


def _build_same_speed_group_view(
    members: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Build fairness view within same-speed groups.

    members example:
      [
        {"member": "et-0/0/11:0", "share": 0.082, "speed_gbps": 400},
        ...
      ]
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for m in members or []:
        speed = m.get("speed_gbps")
        if speed is None:
            speed_label = "unknown"
        else:
            try:
                speed_val = float(speed)
                speed_label = f"{int(speed_val)}G" if speed_val.is_integer() else f"{speed_val}G"
            except Exception:
                speed_label = "unknown"

        groups.setdefault(speed_label, []).append(m)

    result: List[Dict[str, Any]] = []

    def _sort_key(label: str):
        if label == "unknown":
            return -1
        try:
            return int(label.rstrip("G"))
        except Exception:
            return -1

    for speed_label in sorted(groups.keys(), key=_sort_key, reverse=True):
        group_members = groups[speed_label]
        shares = [float(m.get("share") or 0.0) for m in group_members]
        member_count = len(group_members)
        group_total_share = sum(shares)

        if member_count > 0:
            expected_equal_member_share = group_total_share / member_count
        else:
            expected_equal_member_share = 0.0

        min_member_share = min(shares) if shares else 0.0
        max_member_share = max(shares) if shares else 0.0

        spread_ratio = None
        if shares and min_member_share > 0:
            spread_ratio = max_member_share / min_member_share

        verdict = _classify_same_speed_fairness(
            member_count=member_count,
            expected_equal_member_share=expected_equal_member_share,
            min_member_share=min_member_share,
            max_member_share=max_member_share,
            spread_ratio=spread_ratio,
            cfg=cfg,
        )

        result.append({
            "speed_label": speed_label,
            "member_count": member_count,
            "group_total_share": group_total_share,
            "expected_equal_member_share": expected_equal_member_share,
            "min_member_share": min_member_share,
            "max_member_share": max_member_share,
            "spread_ratio": spread_ratio,
            "fairness_verdict": verdict,
            "members": [
                {
                    "member": m.get("member"),
                    "share": m.get("share"),
                    "speed_gbps": m.get("speed_gbps"),
                    "deviation_from_equal_share": abs(float(m.get("share") or 0.0) - expected_equal_member_share),
                }
                for m in sorted(group_members, key=lambda x: str(x.get("member") or ""))
            ],
        })

    return result

# ============================================================
# Queue -> DLB evidence mapping
# ============================================================

def _infer_queue_role(queue_name: str, hotspot: Dict[str, Any]) -> str:
    qn = (queue_name or "").lower()
    text = " ".join(
        [
            str(hotspot.get("classification", "")),
            str(hotspot.get("probable_cause", "")),
            str(hotspot.get("queue_role", "")),
            str(hotspot.get("interpretation", "")),
        ]
    ).lower()

    if "mcast" in text or "broadcast" in text or "lossy" in text:
        return "multicast-lossy"
    if "unicast" in text:
        return "unicast-data"
    if qn in ("q8", "queue8", "8"):
        return "multicast-lossy"
    return "unknown"


def _infer_dlb_relevance(queue_role: str, severity: str, behavior: str) -> str:
    if queue_role == "unicast-data":
        if severity in ("high", "critical") or "persistent" in behavior:
            return "primary"
        return "supporting"
    if queue_role == "multicast-lossy":
        if severity in ("high", "critical") and "persistent" in behavior:
            return "supporting"
        return "weak"
    return "weak"


def _member_pressure_state_from_queue_evidence(queue_evidence: List[QueueEvidence]) -> Tuple[str, str]:
    if not queue_evidence:
        return "healthy", "no_significant_queue_pressure"

    has_primary = any(q.dlb_relevance == "primary" for q in queue_evidence)
    has_supporting = any(q.dlb_relevance == "supporting" for q in queue_evidence)
    has_critical = any(q.severity == "critical" for q in queue_evidence)
    has_high = any(q.severity == "high" for q in queue_evidence)

    if has_primary and has_critical:
        return "severely_pressured", "persistent_primary_queue_pressure"
    if has_primary or has_high:
        return "pressured", "primary_queue_pressure_present"
    if has_supporting:
        return "mildly_pressured", "supporting_queue_pressure_present"
    return "healthy", "only_weak_queue_signals"


def _build_member_pressure_from_hotspots(hotspots: List[Dict[str, Any]]) -> List[MemberPressureSummary]:
    by_member: Dict[str, List[Dict[str, Any]]] = {}
    for h in hotspots:
        member = str(
            h.get("member")
            or h.get("interface")
            or h.get("target_member")
            or "unknown"
        )
        by_member.setdefault(member, []).append(h)

    results: List[MemberPressureSummary] = []

    for member, hs in by_member.items():
        qev: List[QueueEvidence] = []
        for h in hs:
            queue_name = str(h.get("queue") or h.get("queue_name") or "unknown")
            severity = str(h.get("severity") or "unknown").lower()
            behavior = " ".join(
                [
                    str(h.get("temporal_pattern", "")),
                    str(h.get("recovery_trend", "")),
                    str(h.get("classification", "")),
                ]
            ).lower().strip() or "unknown"

            role = _infer_queue_role(queue_name, h)
            dlb_relevance = _infer_dlb_relevance(role, severity, behavior)

            qev.append(
                QueueEvidence(
                    queue_name=queue_name,
                    severity=severity,
                    behavior=behavior,
                    role=role,
                    dlb_relevance=dlb_relevance,
                    summary=str(h.get("interpretation") or h.get("probable_cause") or ""),
                )
            )

        pressure_state, pressure_summary = _member_pressure_state_from_queue_evidence(qev)

        signal_strength = "none"
        if any(q.dlb_relevance == "primary" for q in qev):
            signal_strength = "primary"
        elif any(q.dlb_relevance == "supporting" for q in qev):
            signal_strength = "supporting"
        elif any(q.dlb_relevance == "weak" for q in qev):
            signal_strength = "weak"

        results.append(
            MemberPressureSummary(
                member=member,
                dlb_signal_strength=signal_strength,
                member_pressure_state=pressure_state,
                member_pressure_summary=pressure_summary,
                queue_evidence=qev,
            )
        )

    return results


# ============================================================
# Classification logic
# ============================================================

def _classify_baseline_state(
    baseline_members: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Tuple[str, List[str], Dict[str, float]]:
    reasons: List[str] = []
    if not baseline_members:
        return BASELINE_UNKNOWN, ["baseline_missing"], {}

    groups = _build_speed_groups(baseline_members)
    expected = _expected_group_shares(groups)
    actual = _actual_group_shares(groups)
    spread = _same_speed_spread_ratio(groups)

    major_misalignment = False
    minor_misalignment = False

    for gk, expected_share in expected.items():
        actual_share = actual.get(gk, 0.0)
        if expected_share <= 0:
            continue
        rel_err = abs(actual_share - expected_share) / expected_share
        if rel_err > cfg["group_alignment_major_tolerance"]:
            major_misalignment = True
        elif rel_err > cfg["group_alignment_minor_tolerance"]:
            minor_misalignment = True

    unhealthy_spread = False
    minor_spread = False
    for ratio in spread.values():
        if ratio is None:
            continue
        if ratio >= cfg["same_speed_unhealthy_skew_ratio"]:
            unhealthy_spread = True
        elif ratio >= cfg["same_speed_minor_skew_ratio"]:
            minor_spread = True

    if major_misalignment or unhealthy_spread:
        reasons.append("baseline_already_skewed")
        return BASELINE_UNHEALTHY_PREEXISTING, reasons, actual

    if minor_misalignment or minor_spread:
        reasons.append("baseline_minor_skew")
        return BASELINE_HEALTHY_MINOR_SKEW, reasons, actual

    reasons.append("baseline_healthy")
    return BASELINE_HEALTHY_SPEED_WEIGHTED, reasons, actual


def _classify_speed_alignment(
    recovery_members: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Tuple[str, List[str], Dict[str, float], Dict[str, float]]:
    reasons: List[str] = []
    if not recovery_members:
        return SPEED_ALIGNMENT_UNKNOWN, ["recovery_missing"], {}, {}

    groups = _build_speed_groups(recovery_members)
    expected = _expected_group_shares(groups)
    actual = _actual_group_shares(groups)

    major = False
    minor = False
    for gk, expected_share in expected.items():
        actual_share = actual.get(gk, 0.0)
        if expected_share <= 0:
            continue
        rel_err = abs(actual_share - expected_share) / expected_share
        if rel_err > cfg["group_alignment_major_tolerance"]:
            major = True
        elif rel_err > cfg["group_alignment_minor_tolerance"]:
            minor = True

    if major:
        reasons.append("persistent_mixed_speed_skew")
        return SPEED_MISALIGNED, reasons, expected, actual
    if minor:
        reasons.append("mild_speed_group_misalignment")
        return SPEED_MILDLY_MISALIGNED, reasons, expected, actual

    reasons.append("speed_group_aligned")
    return SPEED_ALIGNED, reasons, expected, actual


def _dominant_member_state_from_recovery_samples(
    recovery_samples: List[List[Dict[str, Any]]],
    cfg: Dict[str, Any],
) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if not recovery_samples:
        return DOMINANT_UNKNOWN, ["recovery_samples_missing"]

    dominant_sequence: List[str] = []

    for sample in recovery_samples:
        best_member = "none"
        best_share = -1.0
        for m in sample:
            share = _safe_float(m.get("share")) or 0.0
            if share > best_share:
                best_share = share
                best_member = str(m.get("member") or "unknown")
        if best_share >= cfg["dominant_member_share_threshold"]:
            dominant_sequence.append(best_member)
        else:
            dominant_sequence.append("none")

    non_none = [x for x in dominant_sequence if x != "none"]
    if not non_none:
        reasons.append("no_dominant_member")
        return DOMINANT_NONE, reasons

    counts: Dict[str, int] = {}
    for item in non_none:
        counts[item] = counts.get(item, 0) + 1

    dominant_member, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    frac = dominant_count / len(dominant_sequence)

    changes = 0
    prev = None
    for item in dominant_sequence:
        if prev is None:
            prev = item
            continue
        if item != prev:
            changes += 1
            prev = item

    if changes >= cfg["oscillation_dominant_change_threshold"] and frac < cfg["dominant_member_persistence_fraction"]:
        reasons.append("recovery_oscillation")
        return DOMINANT_TRANSIENT, reasons

    if frac >= cfg["dominant_member_persistence_fraction"]:
        reasons.append("dominant_port_persistence")
        return DOMINANT_PERSISTENT, reasons

    reasons.append("transient_dominance_only")
    return DOMINANT_TRANSIENT, reasons


def _classify_recovery_convergence(
    recovery_samples: List[List[Dict[str, Any]]],
    cfg: Dict[str, Any],
) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    reasons: List[str] = []
    if len(recovery_samples) < cfg["min_recovery_samples"]:
        return RECOVERY_UNKNOWN, ["recovery_insufficient_samples"], []

    prev_sample = recovery_samples[-2]
    last_sample = recovery_samples[-1]

    prev_map = {str(m.get("member")): (_safe_float(m.get("share")) or 0.0) for m in prev_sample}
    last_map = {str(m.get("member")): (_safe_float(m.get("share")) or 0.0) for m in last_sample}

    all_keys = sorted(set(prev_map.keys()) | set(last_map.keys()))
    drift = sum(abs(last_map.get(k, 0.0) - prev_map.get(k, 0.0)) for k in all_keys)

    dominant_state, dom_reasons = _dominant_member_state_from_recovery_samples(recovery_samples, cfg)
    if "recovery_oscillation" in dom_reasons:
        reasons.extend(dom_reasons)
        return RECOVERY_OSCILLATING, reasons, last_sample

    if drift <= 0.10:
        reasons.append("recovery_distribution_stable")
        return RECOVERY_CONVERGED, reasons, last_sample
    if drift <= 0.25:
        reasons.append("recovery_partial_stabilization")
        return RECOVERY_PARTIAL, reasons, last_sample

    reasons.append("post_resume_non_convergence")
    return RECOVERY_NOT_CONVERGED, reasons, last_sample


def _classify_delta_outcome(
    baseline_state: str,
    recovery_convergence_state: str,
    speed_alignment_state: str,
) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if baseline_state == BASELINE_UNHEALTHY_PREEXISTING:
        if recovery_convergence_state == RECOVERY_CONVERGED and speed_alignment_state in (SPEED_ALIGNED, SPEED_MILDLY_MISALIGNED):
            reasons.append("improved_from_bad_baseline")
            return DELTA_IMPROVED, reasons
        reasons.append("baseline_remained_problematic")
        return DELTA_UNCHANGED, reasons

    if recovery_convergence_state == RECOVERY_CONVERGED and speed_alignment_state == SPEED_ALIGNED:
        reasons.append("recovered_from_event")
        return DELTA_RECOVERED_FROM_EVENT, reasons

    if recovery_convergence_state == RECOVERY_PARTIAL and speed_alignment_state in (SPEED_ALIGNED, SPEED_MILDLY_MISALIGNED):
        reasons.append("minor_post_event_residual")
        return DELTA_DEGRADED, reasons

    if recovery_convergence_state in (RECOVERY_NOT_CONVERGED, RECOVERY_OSCILLATING) or speed_alignment_state == SPEED_MISALIGNED:
        reasons.append("worsened_post_event")
        return DELTA_WORSENED_VS_BASELINE, reasons

    return DELTA_UNKNOWN, reasons


def _fuse_verdict(
    baseline_state: str,
    recovery_convergence_state: str,
    speed_alignment_state: str,
    dominant_port_state: str,
    delta_outcome: str,
    pressure_strength: str,
    cfg: Dict[str, Any],
) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []

    baseline_healthy = baseline_state in (BASELINE_HEALTHY_SPEED_WEIGHTED, BASELINE_HEALTHY_MINOR_SKEW)

    if recovery_convergence_state == RECOVERY_CONVERGED and speed_alignment_state == SPEED_ALIGNED:
        reasons.append("recovery_good")
        return VERDICT_EXPECTED, CONF_HIGH, reasons

    if recovery_convergence_state == RECOVERY_PARTIAL and speed_alignment_state in (SPEED_ALIGNED, SPEED_MILDLY_MISALIGNED):
        reasons.append("recovery_partially_good")
        return VERDICT_ACCEPTABLE, CONF_MEDIUM, reasons

    if recovery_convergence_state == RECOVERY_OSCILLATING:
        reasons.append("oscillating_recovery")
        if baseline_healthy and pressure_strength in ("primary", "supporting"):
            return VERDICT_ABNORMAL, CONF_MEDIUM, reasons
        return VERDICT_WATCH, CONF_LOW, reasons

    # Existing event-induced defect path
    if (
        baseline_healthy
        and recovery_convergence_state == RECOVERY_NOT_CONVERGED
        and speed_alignment_state == SPEED_MISALIGNED
        and dominant_port_state == DOMINANT_PERSISTENT
        and pressure_strength in ("primary", "supporting")
    ):
        reasons.append("strong_defect_signal")
        return VERDICT_DEFECT, CONF_HIGH, reasons

    # New persistent-defect path
    if (
        baseline_state == BASELINE_UNHEALTHY_PREEXISTING
        and recovery_convergence_state == RECOVERY_CONVERGED
        and speed_alignment_state == SPEED_MISALIGNED
        and delta_outcome == DELTA_UNCHANGED
    ):
        reasons.append("persistent_ecmp_misalignment")
        if pressure_strength in ("primary", "supporting"):
            reasons.append("persistent_ecmp_misalignment_with_pressure")
            return VERDICT_DEFECT, CONF_HIGH, reasons
        return VERDICT_DEFECT, CONF_MEDIUM, reasons

    if recovery_convergence_state == RECOVERY_NOT_CONVERGED or speed_alignment_state == SPEED_MISALIGNED:
        reasons.append("recovery_abnormal_but_not_strong_enough")
        if baseline_state == BASELINE_UNHEALTHY_PREEXISTING and cfg["require_baseline_healthy_for_defect"]:
            return VERDICT_WATCH, CONF_LOW, reasons
        return VERDICT_ABNORMAL, CONF_MEDIUM, reasons

    return VERDICT_WATCH, CONF_LOW, reasons


# ============================================================
# Per-target analyzer
# ============================================================

def _analyze_target(
    target_id: str,
    ui_report: Dict[str, Any],
    cfg: Dict[str, Any],
) -> TargetRecoveryResult:
    result = TargetRecoveryResult(target_id=target_id)

    baseline_samples, recovery_samples = _extract_target_samples(ui_report, target_id)
    baseline_samples = [_normalize_member_list(x) for x in baseline_samples]
    recovery_samples = [_normalize_member_list(x) for x in recovery_samples]

    hotspots = _extract_target_hotspots(ui_report, target_id)
    member_pressure = _build_member_pressure_from_hotspots(hotspots)

    pressure_strength = "none"
    if any(x.dlb_signal_strength == "primary" for x in member_pressure):
        pressure_strength = "primary"
    elif any(x.dlb_signal_strength == "supporting" for x in member_pressure):
        pressure_strength = "supporting"
    elif any(x.dlb_signal_strength == "weak" for x in member_pressure):
        pressure_strength = "weak"

    result.member_pressure = [
        {
            "member": x.member,
            "dlb_signal_strength": x.dlb_signal_strength,
            "member_pressure_state": x.member_pressure_state,
            "member_pressure_summary": x.member_pressure_summary,
            "queue_evidence": [asdict(q) for q in x.queue_evidence],
        }
        for x in member_pressure
    ]
    result.member_pressure_summary = (
        ", ".join(
            f"{x.member}:{x.member_pressure_state}/{x.dlb_signal_strength}"
            for x in member_pressure
        )
        if member_pressure
        else "no_member_pressure_evidence"
    )

    if not baseline_samples or not recovery_samples:
        result.analysis_status = ANALYSIS_INSUFFICIENT
        result.reason_codes = _dedupe_keep_order(
            ["missing_baseline_or_recovery_samples"]
        )
        return result

    baseline_last = baseline_samples[-1]
    recovery_last = recovery_samples[-1]

    result.baseline_members = baseline_last
    result.recovery_members = recovery_last
    result.baseline_same_speed_group_view = _build_same_speed_group_view(baseline_last, cfg)
    result.recovery_same_speed_group_view = _build_same_speed_group_view(recovery_last, cfg)


    target_speed_gbps, target_speed_label = _infer_target_port_speed(
        target_id=target_id,
        baseline_members=baseline_last,
        recovery_members=recovery_last,
    )
    result.target_port_speed_gbps = target_speed_gbps
    result.target_port_speed_label = target_speed_label

    baseline_state, baseline_reasons, baseline_actual = _classify_baseline_state(baseline_last, cfg)
    result.baseline_state = baseline_state
    result.baseline_group_shares = baseline_actual

    recovery_state, recovery_reasons, _ = _classify_recovery_convergence(recovery_samples, cfg)
    result.recovery_convergence_state = recovery_state

    speed_alignment_state, speed_reasons, expected_group, actual_group = _classify_speed_alignment(recovery_last, cfg)
    result.speed_alignment_state = speed_alignment_state
    result.expected_group_shares = expected_group
    result.recovery_group_shares = actual_group



    dominant_state, dominant_reasons = _dominant_member_state_from_recovery_samples(recovery_samples, cfg)
    result.dominant_port_state = dominant_state

    delta_outcome, delta_reasons = _classify_delta_outcome(
        baseline_state=baseline_state,
        recovery_convergence_state=recovery_state,
        speed_alignment_state=speed_alignment_state,
    )
    result.delta_outcome = delta_outcome

    verdict, confidence, verdict_reasons = _fuse_verdict(
        baseline_state=baseline_state,
        recovery_convergence_state=recovery_state,
        speed_alignment_state=speed_alignment_state,
        dominant_port_state=dominant_state,
        delta_outcome=delta_outcome,
        pressure_strength=pressure_strength,
        cfg=cfg,
    )
    result.recovery_verdict = verdict
    result.confidence = confidence

    result.reason_codes = _dedupe_keep_order(
        baseline_reasons
        + recovery_reasons
        + speed_reasons
        + dominant_reasons
        + delta_reasons
        + verdict_reasons
    )

    result.analysis_status = ANALYSIS_COMPLETE
    if len(baseline_samples) < cfg["min_baseline_samples"] or len(recovery_samples) < cfg["min_recovery_samples"]:
        result.analysis_status = ANALYSIS_PARTIAL
        result.reason_codes = _dedupe_keep_order(result.reason_codes + ["limited_sample_depth"])

    return result


# ============================================================
# Public builder
# ============================================================

def build_ecmp_recovery_view(
    case_summary: Dict[str, Any],
    ui_report: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    output: Dict[str, Any] = {
        "version": "v1",
        "enabled": True,
        "summary": {
            "analysis_status": ANALYSIS_COMPLETE,
            "target_count": 0,
            "expected_count": 0,
            "acceptable_count": 0,
            "watch_count": 0,
            "abnormal_count": 0,
            "defect_candidate_count": 0,
            "partial_count": 0,
            "insufficient_count": 0,
        },
        "targets": [],
        "errors": [],
    }

    try:
        target_ids = _extract_targets(case_summary, ui_report)
        if not target_ids:
            output["summary"]["analysis_status"] = ANALYSIS_INSUFFICIENT
            output["errors"].append("no_targets_found_for_ecmp_recovery_view")
            return output

        results: List[TargetRecoveryResult] = []

        for target_id in target_ids:
            try:
                results.append(_analyze_target(target_id, ui_report, cfg))
            except Exception as exc:
                output["errors"].append(
                    f"target={target_id} analysis_error={type(exc).__name__}: {exc}"
                )
                results.append(
                    TargetRecoveryResult(
                        target_id=target_id,
                        analysis_status=ANALYSIS_INSUFFICIENT,
                        recovery_verdict=VERDICT_WATCH,
                        confidence=CONF_LOW,
                        reason_codes=["target_analysis_exception"],
                    )
                )

        output["targets"] = [asdict(x) for x in results]
        output["summary"]["target_count"] = len(results)

        for r in results:
            if r.analysis_status == ANALYSIS_PARTIAL:
                output["summary"]["partial_count"] += 1
            if r.analysis_status == ANALYSIS_INSUFFICIENT:
                output["summary"]["insufficient_count"] += 1

            if r.recovery_verdict == VERDICT_EXPECTED:
                output["summary"]["expected_count"] += 1
            elif r.recovery_verdict == VERDICT_ACCEPTABLE:
                output["summary"]["acceptable_count"] += 1
            elif r.recovery_verdict == VERDICT_WATCH:
                output["summary"]["watch_count"] += 1
            elif r.recovery_verdict == VERDICT_ABNORMAL:
                output["summary"]["abnormal_count"] += 1
            elif r.recovery_verdict == VERDICT_DEFECT:
                output["summary"]["defect_candidate_count"] += 1


        # ------------------------------------------------------------
        # Group-level ECMP interpretation
        # ------------------------------------------------------------
        total = len(results)
        misaligned = sum(1 for r in results if r.speed_alignment_state == SPEED_MISALIGNED)
        converged = sum(1 for r in results if r.recovery_convergence_state == RECOVERY_CONVERGED)
        improved = sum(1 for r in results if r.delta_outcome in (DELTA_IMPROVED, DELTA_RECOVERED_FROM_EVENT))
        unchanged = sum(1 for r in results if r.delta_outcome == DELTA_UNCHANGED)
        abnormal = sum(1 for r in results if r.recovery_verdict in (VERDICT_ABNORMAL, VERDICT_DEFECT))
        preexisting = sum(1 for r in results if r.baseline_state == BASELINE_UNHEALTHY_PREEXISTING)

        group_reason_codes: List[str] = []
        group_summary_text = "ECMP group behavior is mixed."

        if total > 0:
            if misaligned == total and converged == total and unchanged == total and preexisting == total:
                group_reason_codes = [
                    "group_baseline_preexisting_skew",
                    "group_recovery_stable",
                    "group_persistent_mixed_speed_skew",
                    "group_no_post_recovery_improvement",
                ]
                group_summary_text = (
                    "All monitored ECMP targets were already skewed in baseline and "
                    "converged after recovery, but remained misaligned relative to link speeds. "
                    "Recovery returned the group to a stable but still imbalanced state."
                )
            elif improved == total and converged == total and misaligned == 0:
                group_reason_codes = [
                    "group_recovered_cleanly",
                    "group_speed_aligned_after_recovery",
                ]
                group_summary_text = (
                    "All monitored ECMP targets converged and aligned with speed-weighted expectations after recovery."
                )
            elif abnormal > 0:
                group_reason_codes = [
                    "group_contains_abnormal_targets",
                ]
                group_summary_text = (
                    "Some ECMP targets show abnormal post-recovery behavior and should be investigated individually."
                )

        output["summary"]["group_reason_codes"] = group_reason_codes
        output["summary"]["group_summary_text"] = group_summary_text

        if output["summary"]["insufficient_count"] == len(results):
            output["summary"]["analysis_status"] = ANALYSIS_INSUFFICIENT
        elif output["summary"]["partial_count"] > 0 or output["errors"]:
            output["summary"]["analysis_status"] = ANALYSIS_PARTIAL

        return output

    except Exception as exc:
        output["summary"]["analysis_status"] = ANALYSIS_INSUFFICIENT
        output["errors"].append(f"builder_exception={type(exc).__name__}: {exc}")
        output["errors"].append(traceback.format_exc())
        return output
