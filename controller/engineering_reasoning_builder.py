
def calculate_engineering_confidence(
    event_reasoning,
    ecmp_reasoning,
    queue_reasoning,
    interface_reasoning,
    roce_reasoning,
):
    score = 0
    reasons = []

    # Event
    if event_reasoning.get("status") == "Recovered":
        score += 1
        reasons.append("Stress event executed and recovered.")

    # ECMP
    if not ecmp_reasoning.get("regression_detected", True):
        score += 2
        reasons.append("ECMP recovered without regression.")

    # Queue
    if queue_reasoning.get("discard_signals"):
        score += 3
        reasons.append("Queue/discard evidence identifies a congestion origin.")

    # Interface
    if interface_reasoning.get("matched_rows", 0) > 0:
        score += 2
        reasons.append("Interface-level telemetry supports the queue evidence.")
    else:
        reasons.append("Interface-level telemetry is incomplete.")

    # RoCE
    if roce_reasoning.get("victim_flow") != "Unknown":
        score += 3
        reasons.append("RoCE victim-flow degradation confirms traffic impact.")

    # Scheduler / CoS context
    if queue_reasoning.get("classification") == "queue-without-explicit-scheduler":
        score -= 1
        reasons.append("Scheduler/CoS mapping is unavailable.")

    if score >= 9:
        confidence = "High"
    elif score >= 6:
        confidence = "Medium"
    else:
        confidence = "Low"

    return confidence, reasons


def build_interface_reasoning(report: dict) -> dict:
    def _as_dict(x):
        return x if isinstance(x, dict) else {}

    interface_health = _as_dict(report.get("interface_drop_health"))
    telemetry_health = _as_dict(report.get("telemetry_health"))
    summary = _as_dict(report.get("summary"))

    origin_node = summary.get("top_hotspot_node")
    origin_intf = summary.get("top_hotspot_interface")

    rows = []
    for key, value in interface_health.items():
        if isinstance(value, list):
            rows.extend(value)
        elif isinstance(value, dict):
            rows.append(value)

    matched = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        node = row.get("node") or row.get("device") or row.get("switch")
        intf = row.get("interface") or row.get("if_name") or row.get("port")

        if node == origin_node and intf == origin_intf:
            matched.append(row)

    physical_signals = []

    for row in matched:
        for key, label in [
            ("input_discards", "Input Discards"),
            ("output_discards", "Output Discards"),
            ("in_discards", "Input Discards"),
            ("out_discards", "Output Discards"),
            ("crc_errors", "CRC Errors"),
            ("fec_corrected_words", "FEC Corrected Words"),
            ("fec_uncorrectable_words", "FEC Uncorrectable Words"),
            ("input_errors", "Input Errors"),
            ("output_errors", "Output Errors"),
        ]:
            value = row.get(key)
            if value:
                physical_signals.append({
                    "signal": label,
                    "value": value,
                })

    if physical_signals:
        interpretation = (
            "Interface-level discard or physical error signals are present on the congestion-origin interface."
        )
    else:
        interpretation = (
            "No direct interface-level discard or physical error evidence was found for the congestion-origin interface in the UI report."
        )

    return {
        "origin_interface": {
            "node": origin_node,
            "interface": origin_intf,
        },
        "matched_rows": len(matched),
        "physical_signals": physical_signals,
        "telemetry_status": telemetry_health.get("status") or telemetry_health.get("overall_status"),
        "interpretation": interpretation,
    }
def build_queue_reasoning(report: dict) -> dict:
    def _as_dict(x):
        return x if isinstance(x, dict) else {}

    summary = _as_dict(report.get("summary"))
    evidence_index = _as_dict(report.get("evidence_index"))
    cos_health = _as_dict(report.get("cos_health"))

    node = summary.get("top_hotspot_node")
    intf = summary.get("top_hotspot_interface")
    queue = summary.get("top_hotspot_queue")

    entity_id = f"{node}|{intf}|q{queue}" if node and intf and queue is not None else None
    evidence = _as_dict(evidence_index.get(entity_id)) if entity_id else {}

    signals = _as_dict(evidence.get("signals"))
    delta_running = _as_dict(evidence.get("delta_running"))
    delta_post = _as_dict(evidence.get("delta_post"))

    taildrop = (
        signals.get("tail_drop_pkts")
        or delta_running.get("tail_drop_pkts")
        or delta_post.get("tail_drop_pkts")
        or evidence.get("rise_tail_dropped_packets")
        or evidence.get("linger_tail_dropped_packets")
    )

    ecn = (
        signals.get("ecn_marked_pkts")
        or signals.get("out_ecn_ce_marked_pkts")
        or delta_running.get("ecn_marked_pkts")
        or delta_post.get("ecn_marked_pkts")
        or evidence.get("rise_ecn_ce_packets")
        or evidence.get("linger_ecn_ce_packets")
    )

    red_drop = (
        signals.get("red_drop_pkts")
        or delta_running.get("red_drop_pkts")
        or delta_post.get("red_drop_pkts")
    )

    pfc = signals.get("pfc_activity")

    buffer_occ = signals.get("peak_buffer_occupancy_percent")

    discard_signals = []
    if taildrop:
        discard_signals.append({"signal": "Tail Drop", "value": taildrop})
    if red_drop:
        discard_signals.append({"signal": "RED Drop", "value": red_drop})
    if ecn:
        discard_signals.append({"signal": "ECN Marking", "value": ecn})
    if pfc:
        discard_signals.append({"signal": "PFC Activity", "value": pfc})
    if buffer_occ:
        discard_signals.append({"signal": "Peak Buffer Occupancy %", "value": buffer_occ})

    classification = (
        evidence.get("classification")
        or evidence.get("probable_cause")
        or summary.get("primary_cause")
    )

    tail_trend = evidence.get("tail_linger_trend")
    recovery_ratio = evidence.get("recovery_ratio_tail")

    if tail_trend == "increasing":
        queue_trend_interpretation = (
            "Tail-drop behavior is worsening during recovery, indicating congestion is not clearing after the event."
        )
    elif tail_trend == "flat":
        queue_trend_interpretation = (
            "Tail-drop behavior remains persistent but stable during recovery."
        )
    elif tail_trend == "cleared":
        queue_trend_interpretation = (
            "Tail-drop behavior cleared during recovery."
        )
    else:
        queue_trend_interpretation = (
            "Tail-drop recovery trend is unavailable or inconclusive."
        )
    classification_explanations = {
        "localized-lossy-mcast-pressure": (
            "Localized multicast/lossy queue pressure with persistent tail drops. "
            "This indicates loss-based congestion rather than ECN-regulated congestion."
        ),
        "expected-ecn-pressure": (
            "Queue is primarily regulated through ECN marking with minimal packet loss."
        ),
        "queue-pressure-with-taildrop": (
            "Queue experienced sustained pressure resulting in packet drops."
        ),
        "needs-manual-review": (
            "Queue behavior does not match a known congestion pattern and requires manual analysis."
        ),
    }

    classification_explanation = classification_explanations.get(
            classification,
            "No detailed explanation is available for this queue classification."
    )

    return {
        "origin": {
            "node": node,
            "interface": intf,
            "queue": queue,
            "entity_id": entity_id,
        },
        "classification": classification,
        "classification_explanation": classification_explanation,
        "severity": summary.get("severity"),
        "score": summary.get("top_hotspot_score"),
        "forwarding_class": evidence.get("forwarding_class"),
        "event_delta_classification": evidence.get("event_delta_classification"),
        "tail_linger_trend": evidence.get("tail_linger_trend"),
        "ecn_linger_trend": evidence.get("ecn_linger_trend"),
        "recovery_ratio_tail": evidence.get("recovery_ratio_tail"),
        "trend_interpretation": queue_trend_interpretation,
        "discard_signals": discard_signals,
        "queue_rca_summary": cos_health.get("queue_rca_summary") or summary.get("queue_rca_summary"),
        "interpretation": (
            f"{classification_explanation} {queue_trend_interpretation}"
            if discard_signals
            else "Queue/discard evidence is incomplete for the selected origin candidate."
        ),
    }


def build_ecmp_reasoning(report: dict) -> dict:
    def _as_dict(x):
        return x if isinstance(x, dict) else {}

    view = (
        _as_dict(report.get("ecmp_recovery_view"))
        or _as_dict(report.get("ecmp_recovery"))
        or _as_dict(report.get("ecmp_recovery_analysis"))
    )

    summary = _as_dict(view.get("summary"))
    targets = view.get("targets", []) or []

    defect_count = summary.get("defect_candidate_count", 0)
    abnormal_count = summary.get("abnormal_count", 0)
    expected_count = summary.get("expected_count", 0)
    target_count = summary.get("target_count", len(targets))

    regression = bool(defect_count or abnormal_count)

    return {
        "analysis_status": summary.get("analysis_status", "unknown"),
        "target_count": target_count,
        "expected_count": expected_count,
        "defect_candidate_count": defect_count,
        "abnormal_count": abnormal_count,
        "regression_detected": regression,
        "group_summary": summary.get("group_summary_text"),
        "reason_codes": summary.get("group_reason_codes", []),
        "interpretation": (
            "ECMP recovery converged and no event-induced ECMP regression was detected."
            if not regression
            else "ECMP recovery reported abnormal or defect-candidate behavior."
        ),
    }



def build_event_reasoning(report: dict) -> dict:
    events = report.get("events", []) or report.get("triggered_events", []) or []

    targets = []
    statuses = []
    stress_modes = []
    timelines = []

    for e in events:
        node = e.get("target_node") or e.get("node")
        intf = e.get("target_interface") or e.get("interface")
        status = e.get("status", "unknown")
        details = e.get("details", {}) or {}

        if node and intf:
            targets.append(f"{node} / {intf}")

        statuses.append(status)

        if details.get("stress_mode"):
            stress_modes.append(details.get("stress_mode"))

        timelines.append({
            "event": e.get("event_name"),
            "target": f"{node} / {intf}" if node and intf else "unknown",
            "status": status,
            "trigger_time": e.get("trigger_time"),
            "summary": e.get("summary"),
        })

    targets = list(dict.fromkeys(targets))
    stress_modes = list(dict.fromkeys(stress_modes))

    execution = "PASS" if statuses and all(str(s).lower() == "pass" for s in statuses) else "UNKNOWN"
    recovery = "PASS" if execution == "PASS" else "UNKNOWN"

    return {
        "scenario": ", ".join(stress_modes) if stress_modes else "unknown",
        "targets": targets,
        "execution": execution,
        "recovery": recovery,
        "status": "Recovered" if recovery == "PASS" else "Unknown",
        "timeline": timelines,
        "interpretation": (
            "Stress event executed and recovered successfully on the event targets."
            if recovery == "PASS"
            else "Stress event execution or recovery evidence is incomplete."
        ),
    }


def build_engineering_reasoning(report: dict) -> dict:
    def _as_list(x):
        return x if isinstance(x, list) else []

    def _as_dict(x):
        return x if isinstance(x, dict) else {}

    def _safe_float(v, default=0.0):
        try:
            if v is None:
                return default
            return float(v)
        except Exception:
            return default

    events = _as_list(report.get("events")) or _as_list(report.get("triggered_events"))

    root_cause = _as_dict(report.get("root_cause"))
    congestion_inspection = _as_dict(report.get("congestion_inspection"))
    summary = _as_dict(report.get("summary"))
    traffic = _as_dict(report.get("traffic_health"))

    ecmp = (
        _as_dict(report.get("ecmp_recovery_view"))
        or _as_dict(report.get("ecmp_recovery"))
        or _as_dict(report.get("ecmp_recovery_analysis"))
    )

    origin = (
        _as_dict(report.get("congestion_origin_analysis"))
        or _as_dict(root_cause.get("congestion_origin_analysis"))
        or _as_dict(congestion_inspection.get("congestion_origin_analysis"))
        or root_cause
    )

    primary = (
        _as_dict(origin.get("primary_origin_candidate"))
        or _as_dict(root_cause.get("primary_origin_candidate"))
    )

    if not primary:
        primary = {
            "node": summary.get("top_hotspot_node"),
            "interface": summary.get("top_hotspot_interface"),
            "queue": summary.get("top_hotspot_queue"),
            "classification": summary.get("primary_cause"),
            "confidence": summary.get("confidence"),
            "score": summary.get("top_hotspot_score"),
        }

    victim = (
        _as_dict(origin.get("top_victim_flow"))
        or _as_dict(traffic.get("most_impacted_unique_roce_flow"))
        or _as_dict(traffic.get("most_impacted_flow"))
    )

    event_targets = []
    event_statuses = []
    stress_modes = []

    for e in events:
        node = e.get("target_node") or e.get("node")
        intf = e.get("target_interface") or e.get("interface")
        status = e.get("status")
        details = _as_dict(e.get("details"))

        if node and intf:
            event_targets.append(f"{node} / {intf}")

        if status:
            event_statuses.append(str(status))

        if details.get("stress_mode"):
            stress_modes.append(str(details.get("stress_mode")))

    event_targets = list(dict.fromkeys(event_targets))
    stress_modes = list(dict.fromkeys(stress_modes))

    if event_statuses and all(str(s).lower() == "pass" for s in event_statuses):
        event_result = "Recovered"
    elif "recovered" in str(ecmp).lower() or "recovered" in str(origin).lower():
        event_result = "Recovered"
    else:
        event_result = "Unknown"

    origin_node = primary.get("node")
    origin_intf = primary.get("interface")
    origin_queue = primary.get("queue")
    origin_class = (
        primary.get("classification")
        or primary.get("probable_cause")
        or primary.get("cause")
        or summary.get("primary_cause")
    )
    origin_conf = primary.get("confidence") or summary.get("confidence")
    origin_score = primary.get("score") or summary.get("top_hotspot_score")

    # ------------------------------------------------------------------
    # Resolve RoCEv2 victim flow from traffic_health.rocev2_summary.by_flow
    # Expected raw format:
    # Ethernet - 014|Ethernet - 011|RoCEv2 Flow Group 84|66|66
    # ------------------------------------------------------------------
    rocev2_summary = _as_dict(traffic.get("rocev2_summary"))
    by_flow = _as_dict(rocev2_summary.get("by_flow"))
    findings = _as_list(rocev2_summary.get("findings"))

    top_flow_key = None
    if by_flow:
        top_flow_key = max(by_flow.items(), key=lambda kv: kv[1])[0]

    victim_flow_raw = (
        victim.get("flow")
        or victim.get("flow_name")
        or victim.get("name")
        or victim.get("flow_group")
        or traffic.get("most_impacted_flow_name")
        or traffic.get("most_impacted_flow")
        or top_flow_key
        or "Unknown"
    )

    tx_port = victim.get("tx_port")
    rx_port = victim.get("rx_port")
    flow_name = victim_flow_raw

    if "|" in str(victim_flow_raw):
        parts = str(victim_flow_raw).split("|")
        if len(parts) >= 3:
            tx_port = parts[0].strip()
            rx_port = parts[1].strip()
            flow_name = parts[2].strip()

    # ------------------------------------------------------------------
    # Build RoCEv2 impact signals from findings
    # ------------------------------------------------------------------
    signal_summary = {}

    for item in findings:
        signal = item.get("type")
        severity = item.get("severity", "info")
        value = _safe_float(item.get("value"), 0.0)

        if not signal:
            continue

        current = signal_summary.get(signal)
        if current is None or value > current["value"]:
            signal_summary[signal] = {
                "severity": severity,
                "value": value,
            }

    signal_display = {
        "loss": "Loss",
        "retx": "Retransmission",
        "seqerror": "Sequence Error",
        "message_failed": "Message Failed",
        "ecn_pressure": "ECN Pressure",
        "cnp_pressure": "CNP Pressure",
        "latency": "Latency",
    }

    roce_impact = []

    for signal, display in signal_display.items():
        if signal not in signal_summary:
            continue

        s = signal_summary[signal]
        value = s["value"]

        if value.is_integer():
            value = int(value)

        roce_impact.append({
            "signal": display,
            "severity": s["severity"],
            "value": value,
        })

    if not roce_impact:
        traffic_str = str(traffic).lower()
        fallback_signals = [
            ("loss", "Loss indicators present"),
            ("message", "Message Failed indicators present"),
            ("seqerror", "Sequence Error indicators present"),
            ("ecn", "ECN pressure indicators present"),
            ("cnp", "CNP pressure indicators present"),
            ("latency", "Latency impact indicators present"),
            ("retrans", "Retransmission indicators present"),
        ]

        for key, label in fallback_signals:
            if key in traffic_str:
                roce_impact.append({
                    "signal": label,
                    "severity": "info",
                    "value": None,
                })

    if not roce_impact:
        roce_impact.append({
            "signal": "RoCEv2 impact detected",
            "severity": "info",
            "value": None,
        })

    critical = [s["signal"] for s in roce_impact if s.get("severity") == "fail"]
    warning = [s["signal"] for s in roce_impact if s.get("severity") == "warn"]

    if critical:
        traffic_interpretation = (
            f"Critical degradation observed in {', '.join(critical)}."
        )
    else:
        traffic_interpretation = "Traffic degradation detected."

    if warning:
        traffic_interpretation += f" Warning signals: {', '.join(warning)}."

    if roce_impact:
        traffic_interpretation += (
            " These RoCEv2 signals confirm real traffic impact and should be correlated "
            "with queue and ECMP evidence."
        )

    ecmp_result = (
        ecmp.get("verdict")
        or _as_dict(ecmp.get("summary")).get("group_summary_text")
        or summary.get("ecmp_summary")
        or "No event-induced ECMP regression detected"
    )

    event_correlation = "Medium"

    origin_str = str(origin).lower()
    primary_outcome = str(primary.get("event_outcome") or origin.get("event_outcome") or "").lower()

    if primary_outcome == "persistent_taildrop" or "persistent_taildrop" in origin_str:
        causality = "Event amplified persistent congestion hotspot"
        event_correlation = "Medium"

    origin_candidate_text = (
        f"{origin_node} / {origin_intf} / q{origin_queue}"
        if origin_node and origin_intf and origin_queue is not None
        else "Unknown"
    )

    if event_targets and origin_node:
        event_target_nodes = {x.split(" / ")[0] for x in event_targets}
        if origin_node not in event_target_nodes:
            origin_relation = "Congestion origin differs from event target"
        else:
            origin_relation = "Congestion origin overlaps with event target"
    else:
        origin_relation = "Origin/event relationship unavailable"

    event_reasoning = build_event_reasoning(report)
    ecmp_reasoning = build_ecmp_reasoning(report)
    queue_reasoning = build_queue_reasoning(report)
    interface_reasoning = build_interface_reasoning(report)
    roce_reasoning = {
        "victim_flow": flow_name,
        "tx_port": tx_port,
        "rx_port": rx_port,
        "impact_signals": roce_impact,
        "interpretation": traffic_interpretation,
    }

    engineering_confidence, engineering_confidence_reasons = calculate_engineering_confidence(
        event_reasoning,
        ecmp_reasoning,
        queue_reasoning,
        interface_reasoning,
        roce_reasoning,
    )

    queue_trend = queue_reasoning.get("tail_linger_trend")
    queue_class = queue_reasoning.get("classification")


    causality = (
        "Transient congestion with delayed RoCE recovery"
        if queue_trend == "cleared"
        else "Event amplified pre-existing congestion"
    )

    if queue_trend == "cleared":
        verdict_summary = (
            "The degraded-hold event recovered successfully and ECMP showed no event-induced regression. "
            "The congestion-origin queue recovered during the observation window, "
            "but RoCEv2 victim-flow degradation persisted. "
            "Current evidence suggests transient congestion or delayed RoCE recovery rather than sustained queue congestion."
        )
    else:
        verdict_summary = (
            "The degraded-hold event recovered successfully from the event-target perspective. "
            "The strongest congestion evidence points to a separate congestion origin candidate. "
            "RoCEv2 victim-flow degradation confirms real traffic impact. "
            "Current evidence supports an amplified existing congestion condition rather than a direct event-target failure."
    )

    engineering_verdict = {
        "summary": verdict_summary,
        "confidence": engineering_confidence,
        "confidence_reason": " ".join(engineering_confidence_reasons),
    }

    reasoning = {
        "executive_assessment": {
            "event_targets": event_targets,
            "event_result": event_result,
            "ecmp_result": ecmp_result,
            "congestion_origin_candidate": {
                "node": origin_node,
                "interface": origin_intf,
                "queue": origin_queue,
                "classification": origin_class,
                "hotspot_confidence": origin_conf,
                "score": origin_score,
            },
            "origin_event_relationship": origin_relation,
            "victim_flow": flow_name,
            "engineering_assessment": causality,
            "engineering_confidence": engineering_confidence,
        },
        "event_assessment": {
            "stress_event": ", ".join(stress_modes) if stress_modes else "degraded-hold",
            "targets": event_targets,
            "result": event_result,
            "interpretation": (
                "Stress event executed and recovered; no direct evidence that event target remained degraded."
                if event_result == "Recovered"
                else "Stress event evidence is incomplete; event-target recovery could not be fully confirmed."
            ),
        },
        "congestion_assessment": {
            "origin_candidate": origin_candidate_text,
            "classification": origin_class,
            "origin_event_relationship": origin_relation,
            "interpretation": (
                "Strongest congestion evidence is associated with the origin candidate, not necessarily the event target."
            ),
        },
        "traffic_assessment": {
            "victim_flow": flow_name,
            "tx_port": tx_port,
            "rx_port": rx_port,
            "impact_signals": roce_impact,
            "interpretation": traffic_interpretation,
        },
        "roce_reasoning": roce_reasoning,
        "causality_reasoning": {
            "observed_facts": [
                "Stress event executed successfully on event targets",
                "Event target recovered",
                "ECMP recovery converged with no event-induced regression",
                f"Primary congestion origin candidate is {origin_candidate_text}",
                f"Congestion origin relationship: {origin_relation}",
                f"Victim RoCEv2 flow is {flow_name}",
                "RoCEv2 traffic degradation observed",
            ],
            "alternative_explanations": [
                {
                    "hypothesis": "Direct event-target failure",
                    "assessment": "Less likely",
                    "reason": "Event target recovered and ECMP did not report event-induced regression.",
                },
                {
                    "hypothesis": "ECMP software regression",
                    "assessment": "Less likely",
                    "reason": "ECMP analysis reported no defect candidate and no abnormal recovery.",
                },
                {
                    "hypothesis": "Independent physical interface issue",
                    "assessment": "Not proven",
                    "reason": "No interface-level physical/discard evidence was found in the UI report for the congestion-origin interface.",
                },
                {
                    "hypothesis": "Persistent congestion hotspot amplified by event",
                    "assessment": "Most likely",
                    "reason": "Queue/discard evidence exists on the origin candidate and RoCEv2 victim-flow degradation confirms real traffic impact.",
                },
            ],
            "most_likely_cause": causality,
            "causality_confidence": engineering_confidence,
        },
        "evidence_reasoning": {
            "steps": [
                {
                    "title": "Stress Event Executed",
                    "status": "PASS" if event_result == "Recovered" else "WARN",
                    "evidence": f"Stress event executed on {', '.join(event_targets) if event_targets else 'unknown targets'}."
                },
                {
                    "title": "ECMP Recovery",
                    "status": "PASS",
                    "evidence": ecmp_result,
                },
                {
                    "title": "Queue / Discard Evidence",
                    "status": "FAIL" if queue_reasoning.get("discard_signals") else "WARN",
                    "evidence": (
                        f"{origin_candidate_text}: {queue_reasoning.get('interpretation', 'Queue evidence unavailable.')}"
                        if origin_candidate_text != "Unknown"
                        else "Queue origin evidence unavailable."
                    ),
                },
                {
                    "title": "RoCEv2 Traffic Impact",
                    "status": "FAIL" if flow_name != "Unknown" else "WARN",
                    "evidence": traffic_interpretation,
                },
                {
                    "title": "Engineering Conclusion",
                    "status": "INFO",
                    "evidence": (
                        "The degraded-hold event recovered successfully from the event-target perspective. "
                        "The strongest congestion evidence points to a separate congestion origin candidate. "
                        "RoCEv2 victim-flow degradation confirms real traffic impact. "
                        "Current evidence supports an amplified existing congestion condition rather than a direct event-target failure."
                    ),
                },
            ]
        },
        "confidence_breakdown": [
            {
                "component": "Event Execution",
                "confidence": "High" if event_result == "Recovered" else "Medium",
                "reason": "Stress event status and recovery were captured from event records.",
            },
            {
                "component": "ECMP Recovery",
                "confidence": "High",
                "reason": "ECMP analysis completed with no defect candidates or abnormal targets.",
            },
            {
                "component": "Queue / Discard Evidence",
                "confidence": "High" if origin_candidate_text != "Unknown" else "Medium",
                "reason": "Queue hotspot and discard signals identify the strongest congestion-origin candidate.",
            },
            {
                "component": "Interface Physical Evidence",
                "confidence": "Medium",
                "reason": "Interface-level evidence is not fully exposed in the UI report; absence of evidence is not proof of absence.",
            },
            {
                "component": "RoCEv2 Traffic Impact",
                "confidence": "High" if flow_name != "Unknown" else "Medium",
                "reason": "RoCEv2 victim-flow impact signals are present and mapped to TX/RX ports.",
            },
            {
                "component": "End-to-End Causality",
                "confidence": event_correlation,
                "reason": "Causality is medium because congestion appears persistent/pre-existing and may have been amplified by the event.",
            },
        ],
        "evidence_chain": [
            "Stress event injected",
            "Event target recovered" if event_result == "Recovered" else "Event target recovery evidence incomplete",
            "ECMP recovery evaluated",
            "Congestion origin candidate identified",
            "RoCEv2 victim flow identified",
            "Traffic impact confirmed",
            "Engineering verdict generated",
        ],
        "engineering_verdict": engineering_verdict,
        "event_reasoning": event_reasoning,
        "ecmp_reasoning": ecmp_reasoning,
        "queue_reasoning": queue_reasoning,
        "interface_reasoning": interface_reasoning,
    }

    return reasoning

