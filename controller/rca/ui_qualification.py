"""Read-only qualification of selected legacy UI reasoning claims."""


def qualify_ui_claims(report, artifact=None):
    if not isinstance(report, dict):
        return {'status': 'source_unavailable', 'findings': []}
    reasoning = report.get('engineering_reasoning') or {}
    if not isinstance(reasoning, dict):
        reasoning = {}
    findings = []

    def add(section, reason, observations, interpretation):
        findings.append({'section': section, 'reason': reason,
                         'supporting_artifact': artifact,
                         'json_pointer': '/engineering_reasoning/' + section,
                         'observations': observations, 'interpretation': interpretation})

    event = reasoning.get('event_reasoning') or {}
    if isinstance(event, dict):
        scenario = str(event.get('scenario') or '').strip().lower()
        if scenario in {'noop', 'stress_noop', 'normal_baseline_no_churn'}:
            add('event_reasoning', 'noop_is_not_fault_recovery',
                {k: event.get(k) for k in ('scenario', 'status', 'interpretation')},
                'Noop execution can establish execution success; it does not establish recovery from an injected fault. Verify scenario metadata before applying degraded-hold narratives.')
    ecmp = reasoning.get('ecmp_reasoning') or {}
    if isinstance(ecmp, dict) and str(ecmp.get('analysis_status') or '').lower() in {
        'insufficient_data', 'unknown', 'missing', 'skipped', 'failed'}:
        add('ecmp_reasoning', 'ecmp_coverage_does_not_establish_convergence',
            {k: ecmp.get(k) for k in ('analysis_status', 'target_count', 'expected_count',
                                     'regression_detected', 'interpretation')},
            'Insufficient or unsuccessful ECMP analysis cannot establish convergence or absence of regression. Zero detected candidates is not an acceptance verdict.')
    queue = reasoning.get('queue_reasoning') or {}
    if isinstance(queue, dict) and queue.get('event_delta_classification') in {
        'no_event_delta', 'baseline_or_historical_only', 'historical_counter_only'}:
        add('queue_reasoning', 'non_event_queue_context_does_not_establish_recovery',
            {k: queue.get(k) for k in ('event_delta_classification', 'classification',
                                     'tail_linger_trend', 'recovery_ratio_tail', 'trend_interpretation')},
            'Non-event/historical queue context and cleared trend labels do not independently establish event-induced congestion or recovery. Inspect measured phase increments and raw metric presence.')
    return {'status': 'review_required' if findings else 'no_selected_gap_detected',
            'findings': findings,
            'limitations': ['These checks cover selected reasoning fields only; no detected finding does not qualify the entire UI or establish device health.',
                            'Legacy verdicts, observations and confidence are preserved.']}
