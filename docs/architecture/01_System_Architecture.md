# 01. System Architecture

**Document Version:** 2.0 Draft-1

**Platform:** Fabric Validation Platform (FVP)

**Status:** Living Architecture Document

---

# 1. Introduction

The Fabric Validation Platform (FVP) is a unified engineering validation framework designed for validating modern IP CLOS data-center fabrics.

Unlike traditional automation frameworks that execute isolated test cases, FVP executes engineering scenarios, validates system behavior, performs engineering root-cause analysis, and ultimately determines release readiness using evidence collected throughout execution.

The architecture has evolved from a stress automation framework into a release qualification platform while preserving backward compatibility with existing execution workflows.

---

# 2. System Overview

The platform is organized into multiple logical layers.

```

```
                           Fabric Validation Platform

                     Executive Release Validation Center
                                      │
                                      ▼
                          Engineering Reporting Layer
                                      │
                                      ▼
                        Engineering Reasoning Framework
                                      │
                                      ▼
                              RCA & Correlation Layer
                                      │
                                      ▼
                           Validation & Analysis Layer
                                      │
                                      ▼
                     Telemetry / Traffic Evidence Layer
                                      │
                                      ▼
                          Stress Execution Framework
                                      │
                                      ▼
                           Scenario Execution Layer
                                      │
                                      ▼
                          Device Control & Inventory
```

---

# 3. Current Implementation

The current implementation already contains the following major subsystems.

## Execution

- Fault Injection Runner
- Stress Orchestrator
- Campaign Execution
- Suite Execution
- Parallel Target Execution

---

## Validation

- Device Fact Collection
- Topology Discovery
- Topology Validation
- Stress Precheck
- Expected vs Observed Validation

---

## Telemetry

- gNMI Collection
- Queue Statistics
- Interface Statistics
- Congestion Metrics
- IXIA Statistics
- RoCEv2 Statistics

---

## Engineering RCA

- Congestion Origin Analysis
- ECMP Recovery Analysis
- ECMP Hierarchy Analysis
- Delta Analysis
- Root Cause Correlation
- Engineering Reasoning

---

## Reporting

- Stress Reports
- RCA Summary
- Campaign Reports
- HTML UI
- JSON Artifacts

---

# 4. Primary Entry Point

The primary entry point into the platform is

```

python -m controller.fault_injection_runner

```

The Fault Injection Runner is responsible for coordinating an entire validation campaign.

It performs:

- Scenario Resolution
- Target Resolution
- Campaign Setup
- Stress Execution
- RCA Execution
- Report Generation
- Validation
- Final Result Aggregation

It serves as the orchestration layer between stress execution and engineering analysis.

---

# 5. End-to-End Execution Flow

The current execution flow is illustrated below.

```

User

↓

Fault Injection Runner

↓

Stress Orchestrator

↓

Device Actions

↓

Telemetry Collection

↓

Validation

↓

RCA Engine

↓

Engineering Reasoning

↓

Report Builder

↓

Web UI

↓

Executive Summary

