# Fabric Validation Platform
# 00. Project Vision

**Architecture Version:** 2.0  
**Status:** Living Design Specification  
**Owner:** Mohan Kumar M V

---

## 1. Vision

Fabric Validation Platform, or FVP, is an engineering validation and release-qualification platform for modern IP CLOS data-center fabrics.

It unifies:

- Scenario execution
- Fault and stress injection
- Traffic orchestration
- Telemetry collection
- Expected-versus-observed validation
- Engineering root-cause analysis
- Engineering reasoning
- Scenario and campaign reporting
- Executive release qualification

The platform's North Star is:

> Given a software release, automatically determine whether it is ready for production and explain the decision using traceable engineering evidence.

---

## 2. Mission

Enable engineering teams to validate complex network software releases with confidence by combining automated execution, traffic evidence, telemetry analysis, root-cause reasoning, and executive-ready reporting in one extensible platform.

---

## 3. Current Platform

FVP v2 starts from an existing, working Fabric Controller framework.

The current implementation already provides:

### Execution

- Fault Injection Runner
- Stress Orchestrator
- Campaign execution
- Suite execution
- Parallel target execution
- Repeated stress iterations
- Pre-event and post-event health gates

### Interface Validation

- Interface bounce
- Interface flap
- Interface shutdown
- Interface restore
- Interface degraded hold and restore

### Evidence Collection

- Device facts
- Topology discovery
- Fabric validation
- gNMI telemetry
- Interface counters
- Queue and congestion evidence
- IXIA and RoCEv2 statistics
- Pre-event, running, degraded, and post-event snapshots

### RCA and Engineering Intelligence

- Telemetry delta analysis
- Fabric hotspot ranking
- Congestion inspection
- Congestion-origin analysis
- ECMP hierarchy and recovery analysis
- RoCEv2 deep inspection
- Traffic-intent correlation
- Root-cause correlation
- Engineering reasoning
- Confidence assessment

### Reporting

- Stress orchestrator reports
- RCA case summaries
- Validation reports
- Engineering and executive-oriented UI sections
- JSON and HTML artifacts
- Campaign and suite-level reporting

FVP v2 therefore does not begin as a new implementation. It enhances and organizes the existing platform.

---

## 4. FVP v2 Objectives

FVP v2 will add:

1. A centralized scenario registry.
2. A consistent scenario metadata model.
3. A common but backward-compatible result contract.
4. Scenario-specific validation contracts.
5. Family-based scenario organization.
6. Executive release validation reports.
7. Feature-health and risk aggregation.
8. Release readiness and confidence scoring.
9. Historical release comparison.
10. A scalable path toward an AI engineering assistant.

---

## 5. Scope

The current platform scope is based on the available lab and topology:

- IP CLOS fabric
- Leaf and spine devices
- ECMP
- BGP and BFD
- Route churn
- Interface and fabric-link events
- RoCEv2 and IXIA traffic
- Congestion and queue analysis
- gNMI telemetry
- SNMP
- Alarms
- Reboot and daemon restart
- ISSU and rollback
- Platform health, memory, core, optics, and CRC validation

The following are excluded until supported by the actual topology:

- EVPN/VXLAN
- VTEP, VNI, IRB, and EVPN route-type scenarios
- AE/LACP member scenarios where no AE configuration exists

---

## 6. Primary Users

### Engineers

Need detailed evidence, telemetry, RCA, logs, timelines, and recommended debugging actions.

### Technical Leads and Architects

Need feature health, scenario coverage, regression summaries, and engineering-risk assessment.

### Release Managers

Need release blockers, execution coverage, failed scenarios, readiness status, and open risks.

### Executives

Need a clear answer to:

> Is the release ready, what risk remains, and why?

---

## 7. Product Principles

### Evolution, Not Rewrite

The existing framework is preserved and enhanced incrementally.

### Backward Compatibility

Existing commands, reports, artifacts, UI, and automation remain supported.

### Evidence-Driven Decisions

Every conclusion must link back to measurable artifacts.

### Explainability

The platform must explain why a scenario or release passed or failed.

### Reuse Before Duplication

New scenario families reuse existing execution, telemetry, RCA, reasoning, and UI components.

### Scenario Validation Contracts

Every scenario defines expected behavior, observed behavior, acceptance criteria, and final assessment.

### Documentation as Code

Architecture, decisions, scenarios, and roadmaps are maintained in Git with the implementation.

---

## 8. Target Platform Layers

```text
Executive Release Validation
            ↓
Release and Feature Health
            ↓
Engineering Reasoning and RCA
            ↓
Validation Engine
            ↓
Telemetry and Traffic Evidence
            ↓
Stress and Scenario Execution
            ↓
Scenario Registry
            ↓
Device, Inventory, and Lab Infrastructure
