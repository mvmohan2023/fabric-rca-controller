# Fabric Controller
# Engineering Design Specification (EDS)

# 11. Artifact Catalog

**Version:** 1.0

---

# 1. Purpose

Fabric Controller is an artifact-driven engineering platform.

Every major execution stage produces one or more artifacts that are consumed by downstream stages. These artifacts act as contracts between framework layers and provide complete traceability of an execution.

Unlike a traditional testing framework where only pass/fail results are retained, Fabric Controller preserves intermediate artifacts to support:

- Debugging
- Engineering investigation
- RCA reproducibility
- Dashboard visualization
- Historical analysis
- Future AI-assisted reasoning

This document serves as the authoritative reference for every execution artifact.

---

# 2. Artifact Lifecycle

```text
User
 │
 ▼
Scenario
 │
 ▼
resolved_targets.json
 │
 ▼
stress_orchestrator_report.json
 │
 ▼
Phase Telemetry Snapshots
 │
 ▼
rca_case_summary.json
 │
 ▼
cos_hotspot_correlation.json
 │
 ▼
rca_ui_report.json
 │
 ▼
Engineering Reasoning
 │
 ▼
Executive Dashboard
```

Each stage enriches the previous stage rather than replacing it.

---

# 3. Artifact Catalog

---

## resolved_targets.json

### Producer

Scenario Framework

### Consumer

Stress Execution Framework

### Purpose

Stores the final resolved execution targets.

### Generated During

Scenario Resolution

### Typical Contents

- Node
- Interface
- Speed
- Platform
- Target policy
- Selection metadata

### Used By

- Stress execution
- Validation
- Dashboard

### Lifetime

Entire campaign

---

## runtime_summary.json

### Producer

Execution Orchestrator

### Consumer

Campaign Summary

### Purpose

Stores execution metadata.

### Typical Contents

- Run ID
- Start time
- End time
- Scenario
- Platform
- Duration
- Overall result

---

## progress.log

### Producer

Progress Logger

### Consumer

Operator

### Purpose

Runtime execution progress.

---

## stress_orchestrator_report.json

### Producer

Stress Orchestrator

### Consumer

RCA Framework

### Purpose

Records the outcome of stress execution.

### Typical Contents

- Event executed
- Event targets
- Success/failure
- Timing
- Recovery status

---

## phase telemetry snapshots

### Producer

Telemetry Framework

### Consumer

Telemetry Analyzer

### Purpose

Capture telemetry at different execution phases.

Typical phases include

- Baseline
- Pre-event
- During-event
- Recovery
- Post-event

---

## telemetry_diff.json

### Producer

Telemetry Analyzer

### Consumer

Evidence Correlation Framework

### Purpose

Stores differences between execution phases.

---

## queue_snapshot.json

### Producer

Queue Collector

### Consumer

Congestion Analysis

### Purpose

Queue statistics captured for RCA.

---

## ecmp_recovery.json

### Producer

ECMP Recovery Analyzer

### Consumer

Engineering Reasoning

### Purpose

Summarizes ECMP recovery behavior.

Typical fields

- recovered
- regression_detected
- member_changes
- recovery_time

---

## congestion_origin_analysis.json

### Producer

Congestion Origin Analyzer

### Consumer

Engineering Reasoning

### Purpose

Identifies the highest confidence congestion origin candidate.

Typical fields

- origin node
- interface
- queue
- classification
- severity
- hotspot score

---

## cos_hotspot_correlation.json

### Producer

CoS Hotspot Correlator

### Consumer

UI Report Builder

### Purpose

Maps queue hotspots into forwarding classes and scheduler behavior.

---

## roce_deep_inspection.json

### Producer

RoCE Deep Inspector

### Consumer

Engineering Reasoning

### Purpose

Provides detailed victim-flow analysis.

Typical fields

- Flow
- Sequence Error
- Message Failed
- Retransmission
- ECN
- CNP
- Latency

---

## traffic_verdict.json

### Producer

Traffic Verifier

### Consumer

Engineering Reasoning

### Purpose

Summarizes traffic health.

---

## rca_case_summary.json

### Producer

RCA Framework

### Consumer

UI Report Builder

### Purpose

Canonical RCA model.

Everything downstream consumes this artifact.

Contains

- Stress report
- Queue analysis
- ECMP
- Traffic
- Interface
- Telemetry
- Congestion origin
- Correlation
- Executive summary

---

## rca_ui_report.json

### Producer

UI Report Builder

### Consumer

Web UI

### Purpose

Normalized dashboard model.

Contains

- Dashboard sections
- Tables
- Executive summary
- Entity evidence
- Engineering reasoning
- Metadata

---

## topology_view.html

### Producer

Topology Builder

### Consumer

User

### Purpose

Interactive topology visualization.

---

## fault_injection_validation.json

### Producer

Validation Framework

### Consumer

Operator

### Purpose

Verifies artifact completeness.

Typical checks

- Required files
- Consistency
- Validation status

---

# 4. Artifact Dependency Graph

```text
Scenario
    │
    ▼
resolved_targets.json
    │
    ▼
stress_orchestrator_report.json
    │
    ▼
Telemetry Artifacts
    │
    ▼
Evidence Correlation
    │
    ▼
rca_case_summary.json
    │
    ▼
rca_ui_report.json
    │
    ▼
Dashboard
```

---

# 5. Design Principles

## Principle 1

Artifacts are immutable.

Later stages enrich rather than overwrite.

---

## Principle 2

Artifacts represent contracts between framework layers.

---

## Principle 3

Every artifact should have a single producer.

---

## Principle 4

Artifacts should be independently inspectable.

---

## Principle 5

Artifacts should remain human-readable.

JSON is preferred whenever practical.

---

# 6. Extension Guidelines

When introducing new functionality:

✓ Prefer extending existing artifacts.

✓ Avoid creating unnecessary top-level artifacts.

✓ Maintain backward compatibility.

✓ Preserve downstream consumers.

---

# 7. Future Artifacts

Planned additions

- Historical trend database
- AI recommendation report
- Multi-run comparison report
- Release readiness report
- Performance baseline report
- Campaign analytics

---

## Revision History

| Version | Date | Summary |
|----------|------|---------|
| 1.0 | 2026-06-29 | Initial artifact catalog |
