# Fabric Controller
# Engineering Design Specification (EDS)

# 06. Evidence Collection Framework

**Version:** 1.0

---

# 1. Purpose

The Evidence Collection Framework is responsible for collecting all engineering observations generated during a validation run.

Unlike traditional testing systems that collect only pass/fail information, Fabric Controller captures evidence from multiple independent sources to support engineering-grade root cause analysis.

Collected evidence is intentionally separated from engineering interpretation.

Evidence collectors gather facts.

Engineering Reasoning interprets those facts.

---

# 2. Responsibilities

The Evidence Collection Framework is responsible for:

- Collecting telemetry
- Capturing queue statistics
- Monitoring ECMP state
- Collecting traffic statistics
- Recording interface health
- Capturing RoCEv2 metrics
- Recording device facts
- Capturing topology information
- Producing normalized evidence artifacts

The framework is not responsible for:

- Root cause analysis
- Engineering reasoning
- Dashboard rendering
- Executive summaries

---

# 3. Position within the Platform

```text
Stress Execution
        │
        ▼
Evidence Collection
        │
        ▼
Evidence Correlation
        │
        ▼
RCA Framework
```

Evidence Collection forms the bridge between runtime execution and engineering analysis.

---

# 4. Architecture

```text
                    Evidence Collection Framework

                 ┌─────────────────────────────┐
                 │ Telemetry Collectors        │
                 └─────────────┬───────────────┘
                               │
                 ┌─────────────▼───────────────┐
                 │ Queue / CoS Collectors      │
                 └─────────────┬───────────────┘
                               │
                 ┌─────────────▼───────────────┐
                 │ ECMP Collectors             │
                 └─────────────┬───────────────┘
                               │
                 ┌─────────────▼───────────────┐
                 │ Traffic / RoCE Collectors   │
                 └─────────────┬───────────────┘
                               │
                 ┌─────────────▼───────────────┐
                 │ Interface Collectors        │
                 └─────────────┬───────────────┘
                               │
                 ┌─────────────▼───────────────┐
                 │ Device Fact Collectors      │
                 └─────────────┬───────────────┘
                               │
                               ▼
                    Normalized Evidence
```

---

# 5. Major Components

## Telemetry

Primary modules

```
telemetry_monitor.py

telemetry_analyzer.py

telemetry_diff.py

telemetry_targets.py

telemetry_normalizers.py
```

Responsibilities

- gNMI collection
- Streaming telemetry
- Phase snapshots
- Path normalization
- Delta generation

---

## Queue / CoS Collection

Modules

```
cos_state_collector.py

cos_parsers.py
```

Responsibilities

- Queue statistics
- Buffer occupancy
- Scheduler state
- Tail drop
- ECN

---

## ECMP Collection

Modules

```
ecmp_phase_sampler.py

ecmp_recovery_analyzer.py
```

Responsibilities

- ECMP member state
- Recovery timing
- Member utilization
- Phase comparisons

---

## Traffic Collection

Modules

```
traffic_verifier.py

ixia_live_monitor.py

ixia_stats_collector.py
```

Responsibilities

- Traffic health
- Frame counters
- Throughput
- Loss
- Recovery

---

## RoCEv2 Collection

Modules

```
ixia_rocev2_stats.py

rocev2_deep_inspector.py
```

Responsibilities

- Sequence Error
- Message Failed
- Retransmissions
- ECN
- CNP
- Latency

---

## Device Collection

Modules

```
collect_device_facts.py

device_client.py
```

Responsibilities

- Interface inventory
- Platform information
- Hardware facts

---

# 6. Phase-aware Collection

Evidence is collected at multiple execution phases.

```text
Baseline

↓

Pre-event

↓

Event

↓

Hold

↓

Recovery

↓

Post
```

This enables delta analysis rather than relying on single snapshots.

---

# 7. Evidence Types

Current evidence sources include:

✓ Telemetry

✓ Queue Counters

✓ CoS State

✓ ECMP State

✓ Interface Health

✓ Traffic Statistics

✓ RoCEv2 Statistics

✓ Device Facts

✓ Topology

Future additions

- SNMP

- Syslog

- Core files

- Hardware alarms

- Process health

---

# 8. Produced Artifacts

Typical artifacts include:

```
Phase telemetry snapshots

telemetry_diff.json

queue_snapshot.json

ecmp_recovery.json

traffic_verdict.json

roce_deep_inspection.json
```

Refer to **11_Artifact_Catalog.md** for complete artifact definitions.

---

# 9. Design Principles

## Principle 1

Collectors gather observations.

---

## Principle 2

Collectors never determine engineering conclusions.

---

## Principle 3

Each collector owns a single evidence domain.

---

## Principle 4

Evidence should be normalized before downstream analysis.

---

## Principle 5

Evidence should be independently inspectable.

---

# 10. Code Mapping

| Module | Responsibility |
|---------|----------------|
| telemetry_monitor.py | Streaming telemetry |
| telemetry_analyzer.py | Snapshot analysis |
| telemetry_diff.py | Phase comparison |
| telemetry_targets.py | Target definitions |
| telemetry_normalizers.py | Normalize telemetry |
| fabric_evidence_collector.py | Aggregate evidence |
| cos_state_collector.py | Queue statistics |
| ecmp_phase_sampler.py | ECMP snapshots |
| traffic_verifier.py | Traffic health |
| ixia_live_monitor.py | Live IXIA polling |
| ixia_rocev2_stats.py | RoCE statistics |
| collect_device_facts.py | Device inventory |

---

# 11. Future Enhancements

Future evidence sources may include:

- SNMP polling
- Hardware alarms
- Syslog
- Process monitoring
- Memory tracking
- AI-generated evidence enrichment

---

# 12. Summary

The Evidence Collection Framework provides the factual foundation for the entire Fabric Controller platform.

Every downstream component—including Evidence Correlation, RCA Generation, Engineering Reasoning, and the Executive Dashboard—depends on the quality and completeness of the evidence collected here.

---

## Related Documents

- 05_Stress_Execution_Framework.md
- 07_Evidence_Correlation_Framework.md
- 11_Artifact_Catalog.md
- 12_Engineering_Glossary.md

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial Evidence Collection Framework |
