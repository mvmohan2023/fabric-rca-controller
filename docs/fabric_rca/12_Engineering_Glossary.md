# Fabric Controller
# Engineering Design Specification (EDS)

# 12. Engineering Glossary

**Version:** 1.0

---

# 1. Purpose

This glossary defines the standard terminology used throughout the Fabric Controller platform.

Every architecture document, implementation guide, engineering report, and dashboard should use these definitions consistently.

---

# 2. Core Platform Terms

## Fabric Controller

The complete engineering validation and RCA platform.

---

## Campaign

A collection of one or more scenario executions.

---

## Run

A single execution instance within a campaign.

---

## Scenario

An engineering validation objective.

A scenario defines *what* should be validated.

Examples:

- ECMP Degraded Hold
- ISSU Validation
- Route Churn
- SNMP Validation

---

## Scenario Family

A logical grouping of related scenarios.

Examples

- Interface
- Routing
- Software
- Telemetry
- Traffic

---

## Stress Mode

The implementation mechanism used to exercise the system.

Examples

- Interface Hold
- Interface Bounce
- Reboot
- Restart Daemon

---

## Stress Event

The actual runtime execution of a stress mode.

---

## Event Target

The node or interface intentionally affected by a stress event.

---

## Runtime Context

Execution metadata generated before stress begins.

Includes

- Run ID
- Scenario
- Timing
- Target list

---

# 3. Evidence Terms

## Evidence

Raw or normalized engineering observations collected during execution.

Examples

- Queue counters
- Telemetry
- ECMP state
- Traffic statistics

---

## Evidence Collector

A component responsible for gathering engineering evidence.

Collectors never produce conclusions.

---

## Finding

A correlated engineering observation derived from one or more pieces of evidence.

---

## Evidence Correlation

The process of combining multiple evidence sources into meaningful findings.

---

# 4. RCA Terms

## RCA

Root Cause Analysis.

The structured explanation of observed behavior.

---

## Congestion Origin

The queue or interface most likely responsible for congestion.

---

## Hotspot

A queue, interface, or resource exhibiting abnormal behavior.

---

## Queue Classification

Classification describing queue behavior.

Examples

- localized-lossy-mcast-pressure
- queue-without-explicit-scheduler
- queue-pressure-with-ecn

---

## Victim Flow

A traffic flow affected by congestion.

---

## Primary Cause

The strongest engineering explanation supported by available evidence.

---

## Alternative Explanation

A competing hypothesis evaluated during engineering reasoning.

---

# 5. Engineering Reasoning Terms

## Engineering Reasoning

The process of interpreting evidence to produce engineering conclusions.

---

## Evidence Chain

The ordered sequence of observations supporting the engineering verdict.

---

## Engineering Confidence

A qualitative measure of how strongly the available evidence supports the engineering conclusion.

Engineering Confidence **does not** indicate:

- Severity
- Customer impact
- Software defect probability

Typical values

- High
- Medium
- Low

---

## Engineering Verdict

The final engineering conclusion.

Examples

- Event amplified pre-existing congestion
- Transient congestion with delayed RoCE recovery
- Event-induced congestion
- ECMP recovery anomaly

---

## Executive Summary

A concise summary intended for management and release reviews.

---

# 6. Platform Components

## Scenario Framework

Responsible for defining engineering objectives.

---

## Stress Execution Framework

Responsible for executing runtime events.

---

## Evidence Collection Framework

Responsible for collecting engineering observations.

---

## Evidence Correlation Framework

Responsible for combining observations into findings.

---

## RCA Framework

Responsible for generating normalized RCA models.

---

## Engineering Reasoning Framework

Responsible for interpreting evidence.

---

## Visualization Framework

Responsible for presenting engineering results.

---

# 7. Dashboard Terms

## Executive Dashboard

High-level management-oriented summary.

---

## Engineering Investigation Console

Detailed engineering investigation.

---

## Entity Evidence

Evidence associated with a selected node, interface, queue, or traffic flow.

---

## Confidence Breakdown

Explanation of why a confidence level was assigned.

---

# 8. Design Principles

- Scenarios define intent.
- Stress modes define execution.
- Evidence collectors gather facts.
- Correlation derives findings.
- Reasoning produces conclusions.
- Dashboards present information.

Each layer has a single responsibility.

---

# 9. Abbreviations

| Abbreviation | Meaning |
|-------------|---------|
| RCA | Root Cause Analysis |
| ECMP | Equal Cost Multi-Path |
| CoS | Class of Service |
| RoCE | RDMA over Converged Ethernet |
| gNMI | gRPC Network Management Interface |
| SNMP | Simple Network Management Protocol |
| DUT | Device Under Test |
| IXIA | Traffic Generator Platform |
| CLI | Command Line Interface |
| FPC | Flexible PIC Concentrator |
| PFE | Packet Forwarding Engine |
| ISSU | In-Service Software Upgrade |

---

# 10. Future Terms

As the platform evolves, this glossary should be updated before introducing new terminology into architecture documents.

---

## Revision History

| Version | Date | Summary |
|----------|------|---------|
| 1.0 | 2026-06-29 | Initial engineering glossary |
