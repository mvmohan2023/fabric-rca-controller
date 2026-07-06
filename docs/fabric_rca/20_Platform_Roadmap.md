# Fabric Controller
# Platform Roadmap

**Version:** 1.0

**Status:** Living Vision & Roadmap

---

# 1. Vision

Fabric Controller is evolving from a fault injection and RCA automation tool into a comprehensive Data Center Validation Platform.

The long-term vision is to provide a single engineering platform capable of:

- Validation automation
- Stress orchestration
- Evidence collection
- Root Cause Analysis
- Engineering reasoning
- Executive reporting
- Release qualification
- AI-assisted investigation

The platform should support both automated regression testing and customer issue reproduction while maintaining a reusable architecture across all validation domains.

---

# 2. Platform Evolution

## Phase 1 — Foundation (Completed)

Objectives

- Scenario execution framework
- Stress orchestration
- Telemetry collection
- RCA generation
- Engineering reasoning
- Executive dashboard
- Web UI
- Architecture documentation

Status

✅ Completed

---

## Phase 2 — Platform Expansion (Current)

Objectives

- Expand supported validation scenarios
- Introduce scenario families
- Increase framework reuse
- Standardize execution model

Status

🚧 In Progress

---

## Phase 3 — Engineering Intelligence

Objectives

- Evidence-weighted confidence scoring
- AI-assisted investigation
- Historical comparison
- Predictive failure detection
- Automated release qualification

Status

Planned

---

# 3. Platform Architecture

```text
Scenario
      │
      ▼
Stress Execution
      │
      ▼
Evidence Collection
      │
      ▼
Evidence Correlation
      │
      ▼
RCA
      │
      ▼
Engineering Reasoning
      │
      ▼
Web UI
```

This execution pipeline remains common across all validation domains.

---

# 4. Scenario Families

## Interface Validation

Purpose

Validate interface state transitions and resiliency.

Examples

- Interface Down
- Interface Up
- Interface Bounce
- Interface Flap
- AE Member Flap
- Remote Interface Flap
- Local Fault
- Remote Fault
- ECMP Member Flap
- Optics Pull / Insert

---

## Software Validation

Purpose

Validate software lifecycle operations.

Examples

- ISSU
- Rollback
- Reboot
- FPC Restart
- Daemon Restart
- GRES
- NSR

---

## Routing Validation

Purpose

Validate routing stability and convergence.

Examples

- Route Churn
- BGP Restart
- BGP Neighbor Loss
- BFD Restart
- EVPN Withdraw
- LACP Events

---

## Telemetry Validation

Purpose

Validate management and telemetry services.

Examples

- gNMI Polling
- gNMI Subscribe
- SNMP Polling
- Alarm Monitoring
- JTI Streaming

---

## Platform Health Validation

Purpose

Validate hardware and software health.

Examples

- Memory Leak
- CPU Utilization
- Core Detection
- CRC Errors
- Optics Temperature
- PSU Failure
- Fan Failure

---

## Traffic Validation

Purpose

Validate forwarding behavior under load.

Examples

- RoCEv2
- ECMP
- Congestion
- Packet Loss
- Latency
- Flow Recovery
- DLB

---

## Scale Validation

Purpose

Validate behavior under scale.

Examples

- 200K Route Churn
- Large ECMP
- High Interface Scale
- Massive Telemetry
- Large VLAN Scale

---

## Longevity Validation

Purpose

Validate long-duration stability.

Examples

- 24-hour runs
- 72-hour runs
- Multi-day traffic
- Memory growth
- Resource leakage

---

# 5. Framework Reuse Strategy

Every scenario should reuse the existing execution pipeline.

```text
Scenario
    ↓
Stress
    ↓
Evidence
    ↓
Correlation
    ↓
RCA
    ↓
Reasoning
    ↓
UI
```

Only the stress mechanism or evidence source should change.

The remaining framework layers should remain reusable.

---

# 6. Engineering Principles

The platform follows these principles:

- Reuse existing frameworks whenever possible.
- Keep responsibilities isolated.
- Preserve artifact-driven execution.
- Avoid scenario-specific code.
- Keep engineering reasoning independent from RCA generation.
- Keep UI independent from engineering computation.

---

# 7. Engineering Backlog

## High Priority

- Interface Validation Family
- Software Validation Family
- Scenario Registry
- Stress Plugin Registry

---

## Medium Priority

- Telemetry Validation Family
- Routing Validation Family
- Platform Health Validation
- Evidence-weighted Confidence Engine

---

## Long-Term

- AI Recommendation Engine
- Historical Run Comparison
- Predictive RCA
- Release Qualification Dashboard
- Multi-Fabric Validation

---

# 8. Scenario Family Priorities

| Priority | Family | Status |
|----------|--------|--------|
| 1 | Interface Validation | Next |
| 2 | Software Validation | Planned |
| 3 | Telemetry Validation | Planned |
| 4 | Routing Validation | Planned |
| 5 | Platform Health Validation | Planned |
| 6 | Scale Validation | Planned |
| 7 | Longevity Validation | Planned |

---

# 9. Success Criteria

The platform should eventually support:

✓ Multiple stress families

✓ Multiple evidence sources

✓ Reusable RCA pipeline

✓ Explainable engineering reasoning

✓ Executive dashboards

✓ Engineering dashboards

✓ Historical run comparison

✓ AI-assisted investigation

✓ Automated release qualification

---

# 10. Long-Term Vision

Fabric Controller is envisioned as an engineering platform rather than a single-purpose automation tool.

Its long-term goal is to provide a unified validation ecosystem capable of reproducing customer issues, validating software releases, performing engineering analysis, and delivering explainable root cause insights across multiple networking platforms and technologies.

---

# Related Documents

- 02_System_Architecture.md
- 03_Execution_Pipeline.md
- 04_Scenario_Framework.md
- 13_Extending_The_Framework.md
- 14_Architecture_Review.md
- 15_Test_Scenario_Catalog.md

---

# Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-30 | Mohan Kumar M V | Initial platform roadmap and vision |
