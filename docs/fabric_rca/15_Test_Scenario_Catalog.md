# Fabric Controller
# Engineering Design Specification (EDS)

# 15. Test Scenario Catalog

**Version:** 1.0

**Status:** Living Scenario Catalog

---

# 1. Purpose

This document provides the complete catalog of validation scenarios supported by the Fabric Controller platform.

Unlike the Scenario Framework document, which describes how scenarios are executed, this catalog describes **what scenarios exist**, their implementation status, supported platforms, engineering objectives, evidence collected, and downstream framework integration.

It serves as the master planning and tracking document for validation coverage.

---

# 2. Scenario Lifecycle

Every scenario progresses through the following lifecycle.

```text
Proposed

↓

Planned

↓

In Development

↓

Validated

↓

Production Ready

↓

Deprecated (if applicable)
```

---

# 3. Scenario Categories

The platform currently organizes scenarios into the following engineering domains.

| Category | Description |
|----------|-------------|
| Interface | Interface state changes and recovery validation |
| ECMP | Load balancing and recovery validation |
| Routing | Route convergence and stability |
| Software | ISSU, reboot, rollback, daemon restart |
| Telemetry | gNMI, SNMP, streaming validation |
| Traffic | IXIA, RoCEv2, congestion validation |
| Platform | Hardware alarms, optics, memory, cores |
| Scale | Large-scale route and topology validation |
| Stability | Long-duration soak and endurance testing |

---

# 4. Current Scenario Catalog

## ECMP Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| ECMP Degraded Hold - Leaf1 | ✅ Production | QFX5240 | Degrade ECMP member on Leaf1 and validate recovery |
| ECMP Degraded Hold - Leaf2 | ✅ Production | QFX5240 | Degrade ECMP member on Leaf2 and validate recovery |
| ECMP Degraded Hold - Leaf3 | ✅ Production | QFX5240 | Degrade ECMP member on Leaf3 and validate recovery |
| ECMP Degraded Hold - Leaf4 | ✅ Production | QFX5240 | Degrade ECMP member on Leaf4 and validate recovery |
| ECMP Degraded Hold - Leaf5 | ✅ Production | QFX5240 | Degrade ECMP member on Leaf5 and validate recovery |
| ECMP Degraded Hold - Leaf6 | ✅ Production | QFX5130 | Degrade ECMP member on Leaf6 and validate recovery |
| ECMP Degraded Hold - Leaf7 | ✅ Production | QFX5240 | Degrade ECMP member on Leaf7 and validate recovery |

Engineering Coverage

- ECMP recovery
- Queue hotspot detection
- Congestion origin analysis
- RoCEv2 traffic impact
- Engineering reasoning
- Executive dashboard

---

## Interface Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| Interface Hold / Restore | ✅ | All | Validate interface recovery |
| Interface Bounce | Planned | All | Repeated interface bounce |
| AE Member Flap | Planned | All | Validate AE resilience |
| Remote Interface Flap | Planned | All | Remote-side recovery |

---

## Routing Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| Route Churn | Planned | All | Inject large-scale routing updates |
| BGP Restart | Planned | All | Restart BGP and validate convergence |
| BFD Recovery | Planned | All | Validate BFD recovery |

---

## Software Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| ISSU Upgrade | Planned | EVO | Validate A→B upgrade |
| ISSU Rollback | Planned | EVO | Validate B→A downgrade |
| Daemon Restart | Planned | EVO | Restart routing/system daemons |
| System Reboot | Planned | All | Validate reboot recovery |
| Rollback Image | Planned | EVO | Validate software rollback |

---

## Telemetry Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| gNMI Polling | Planned | All | Validate telemetry polling |
| gNMI Subscribe | Planned | All | Validate streaming telemetry |
| SNMP Polling | Planned | All | Validate SNMP counters |
| Alarm Monitoring | Planned | All | Validate system alarms |

---

## Traffic Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| RoCEv2 Validation | ✅ | IXIA | Validate RoCEv2 traffic |
| Congestion Validation | ✅ | IXIA | Validate congestion behavior |
| Long Duration Traffic | Planned | IXIA | Multi-day traffic soak |

---

## Platform Validation

| Scenario | Status | Platform | Description |
|----------|--------|----------|-------------|
| Memory Leak | Planned | All | Monitor process memory growth |
| Core Detection | Planned | All | Detect unexpected cores |
| Hardware Alarm | Planned | All | Validate hardware alarms |
| Optics Health | Planned | All | Validate optics behavior |

---

# 5. Scenario Capability Matrix

| Scenario | Stress | Telemetry | Queue | ECMP | RoCE | RCA | Reasoning | UI |
|----------|---------|-----------|-------|------|------|-----|-----------|----|
| ECMP Degraded Hold | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Interface Bounce | ✓ | ✓ | ✓ | Optional | Optional | ✓ | ✓ | ✓ |
| Route Churn | ✓ | ✓ | Optional | ✓ | Optional | ✓ | ✓ | ✓ |
| ISSU | ✓ | ✓ | Optional | Optional | Optional | ✓ | ✓ | ✓ |
| SNMP Polling | No | ✓ | No | No | No | Optional | Optional | Optional |
| Reboot | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

# 6. Engineering Coverage Matrix

| Capability | Current Coverage |
|------------|------------------|
| Stress Execution | ✅ |
| Queue Analysis | ✅ |
| ECMP Recovery | ✅ |
| Congestion Origin | ✅ |
| Traffic Correlation | ✅ |
| RoCEv2 Analysis | ✅ |
| Engineering Confidence | ✅ |
| Executive Dashboard | ✅ |
| Multi-run Comparison | Planned |
| Historical Trends | Planned |

---

# 7. Future Scenario Backlog

High Priority

- ISSU Validation
- Route Churn
- SNMP Polling
- Daemon Restart
- Interface Bounce
- AE Member Flap

Medium Priority

- Memory Leak Detection
- Hardware Alarm Validation
- Optics Validation
- Process Restart Validation

Long-Term

- AI-driven Failure Injection
- Chaos Engineering Scenarios
- Multi-Fabric Validation
- Historical Release Qualification

---

# 8. Adding a New Scenario

Every new scenario should provide:

- Engineering objective
- Stress mode
- Target policy
- Evidence requirements
- Correlation requirements
- Reasoning updates (if needed)
- UI changes (if needed)
- Validation criteria

Refer to **13_Extending_The_Framework.md** for the implementation workflow.

---

# 9. Release Readiness

A scenario is considered production ready when:

- Stress execution is validated.
- Evidence collection is complete.
- RCA generation is validated.
- Engineering reasoning is implemented.
- Dashboard visualization is available.
- Regression testing passes.

---

# 10. Summary

The Test Scenario Catalog is the master inventory of engineering validation scenarios supported by the Fabric Controller platform.

It provides a centralized view of implementation status, engineering coverage, framework integration, and future roadmap, enabling systematic expansion of the platform.

---

## Related Documents

- 04_Scenario_Framework.md
- 13_Extending_The_Framework.md
- 14_Architecture_Review.md

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial Test Scenario Catalog |
