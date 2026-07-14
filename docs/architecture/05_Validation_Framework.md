# 05. Validation Framework

**Architecture Version:** 2.0 Draft-1

**Platform:** Fabric Validation Platform (FVP)

**Status:** Living Architecture Document

---

# 1. Purpose

The Validation Framework determines whether the observed behavior of the network matches engineering expectations after executing a validation scenario.

Unlike traditional test automation, validation in FVP is evidence-driven rather than command-driven.

A scenario is not considered successful simply because a command completed successfully.

Instead, FVP determines success by evaluating collected evidence against predefined engineering acceptance criteria.

---

# 2. Validation Philosophy

Validation answers a simple engineering question:

> Did the system behave as expected?

Execution alone is insufficient.

Every scenario must demonstrate:

- The intended event occurred.
- The expected impact occurred.
- Recovery occurred when expected.
- No unexpected side effects occurred.
- Supporting evidence exists.

---

# 3. Validation Pipeline

```
Scenario Execution
        │
        ▼
Evidence Collection
        │
        ▼
Expected Behaviour
        │
        ▼
Observed Behaviour
        │
        ▼
Evidence Comparison
        │
        ▼
Validation Rules
        │
        ▼
PASS / FAIL
```

---

# 4. Validation Levels

Validation is performed at multiple layers.

## Level 1 — Event Validation

Did the requested event occur?

Examples

- Interface disabled
- Interface restored
- BGP cleared
- Process restarted

---

## Level 2 — Impact Validation

Did the event produce the expected effect?

Examples

- Link went down
- Traffic rerouted
- ECMP redistributed
- BGP adjacency transitioned

---

## Level 3 — Recovery Validation

Did the system recover?

Examples

- Interface returned up
- Routing converged
- Traffic normalized
- Congestion disappeared

---

## Level 4 — Platform Validation

Did the platform remain healthy?

Examples

- No unexpected core files
- No daemon crashes
- Memory stable
- CPU within limits

---

## Level 5 — Telemetry Validation

Was telemetry available and consistent?

Examples

- gNMI streaming active
- Counters updated
- Queue metrics collected
- Interface state observed

---

# 5. Validation Categories

Current categories include:

- Physical Link Validation
- Interface State Validation
- Topology Validation
- BGP Validation
- Traffic Validation
- ECMP Validation
- Congestion Validation
- Queue Validation
- Telemetry Validation
- RoCEv2 Validation
- Platform Health Validation

Future categories include:

- Memory Leak Validation
- Process Restart Validation
- ISSU Validation
- Upgrade Rollback Validation
- AI Confidence Validation

---

# 6. Expected vs Observed Model

Every validation compares:

```
Expected Behaviour

↓

Observed Behaviour

↓

Engineering Assessment
```

Example

Expected

```
Interface shall transition DOWN then UP.
```

Observed

```
DOWN observed.
UP observed.
Traffic recovered.
```

Assessment

```
PASS
```

---

# 7. Evidence Sources

Validation consumes evidence from:

- Device Facts
- Topology Discovery
- Topology Validation
- Stress Precheck
- Interface Statistics
- Queue Counters
- Congestion Metrics
- ECMP Statistics
- Telemetry Streams
- IXIA Traffic
- RoCEv2 Statistics
- Platform Health
- Alarm Logs

Evidence remains immutable once collected.

---

# 8. Validation Rules

Every rule contains:

- Rule Identifier
- Description
- Evidence Source
- Expected Condition
- Observed Value
- Result
- Supporting Artifacts

Example

| Field | Value |
|------|------|
| Rule | IF-VAL-001 |
| Description | Interface transitioned DOWN |
| Expected | True |
| Observed | True |
| Result | PASS |

---

# 9. Validation Result Model

Each validation produces structured output.

```json
{
  "validation": {
    "event_ok": true,
    "impact_ok": true,
    "recovery_ok": true,
    "traffic_ok": true,
    "telemetry_ok": true,
    "platform_ok": true
  }
}
```

Additional validation fields may be added without removing existing fields.

---

# 10. Validation Phases

Validation occurs throughout execution.

## Pre-Validation

Fabric health before event.

## Event Validation

Immediate confirmation of the requested action.

## Running Validation

Behavior during stress.

## Degraded Validation

Behavior while the fault remains active.

## Recovery Validation

Behavior during restoration.

## Post Validation

Final stable state.

---

# 11. Acceptance Criteria

A scenario passes only when all mandatory criteria are satisfied.

Examples:

- Event executed.
- Target affected.
- Fabric recovered.
- Traffic within threshold.
- No unexpected platform failures.
- Required telemetry collected.

Scenario-specific rules may extend these criteria.

---

# 12. Negative Validation

Validation also checks that unexpected events did not occur.

Examples

- Unexpected reboot
- Additional interface failures
- BGP instability
- Packet loss beyond threshold
- Core files
- Telemetry interruption

Unexpected behavior contributes to engineering risk.

---

# 13. Validation Artifacts

Typical outputs include:

- Fabric Validation Report
- Stress Precheck Report
- Scenario Validation Summary
- RCA Validation Summary
- Campaign Validation Summary

These artifacts provide traceability between execution and release decisions.

---

# 14. Extensibility

New validation modules should integrate through reusable interfaces rather than modifying existing validation logic.

Examples:

- Memory Validation
- ISSU Validation
- Security Validation
- Environmental Sensor Validation

---

# 15. Relationship to RCA

Validation determines:

> Did the behavior satisfy engineering expectations?

RCA determines:

> Why did the observed behavior occur?

These responsibilities remain separate but complementary.

---

# 16. Relationship to Executive Reporting

Validation results feed higher-level reporting.

Scenario Validation
        ↓
Feature Health
        ↓
Release Readiness
        ↓
Executive Recommendation

Validation is therefore the foundation for release qualification.

---

# 17. Future Enhancements

Planned improvements include:

- Rule Registry
- Validation Plugins
- Dynamic Thresholds
- Historical Baseline Comparison
- AI-assisted Rule Suggestions
- Automatic Rule Generation
- Confidence Scoring

---

# 18. Summary

The Validation Framework transforms collected evidence into engineering decisions.

By separating execution from validation and using evidence-driven acceptance criteria, FVP provides deterministic, explainable, and extensible validation suitable for release qualification rather than simple test execution.
