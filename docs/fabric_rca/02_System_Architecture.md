# Fabric Controller - System Architecture

**Document:** 02_System_Architecture.md
**Version:** 1.0
**Status:** Living Engineering Design Specification

---

# 1. Purpose

This document describes the high-level system architecture of the Fabric Controller RCA platform.

Fabric Controller is not only a fault-injection tool. It is an end-to-end engineering validation and RCA platform that combines:

* Scenario execution
* Stress orchestration
* Telemetry collection
* Traffic validation
* Evidence correlation
* RCA report generation
* Engineering reasoning
* Executive and engineering UI visualization

The purpose of this architecture is to allow new validation scenarios to plug into the existing RCA pipeline without rebuilding telemetry collection, analysis, report generation, or UI logic.

---

# 2. Architectural Vision

Fabric Controller is designed as a reusable fabric validation platform.

The core idea is:

```text
Scenario
    ↓
Stress/Event
    ↓
Evidence Collection
    ↓
Correlation
    ↓
RCA Report
    ↓
Engineering Reasoning
    ↓
Executive Dashboard + Engineering Investigation UI
```

This enables the same framework to support multiple validation domains:

* ECMP degraded-hold validation
* Interface / AE flap validation
* gNMI telemetry validation
* SNMP validation
* Daemon restart validation
* Route churn validation
* Reboot / ISSU / rollback validation
* Long-running traffic and hardware alarm validation

---

# 3. High-Level Architecture

```text
                            Fabric Controller Platform
================================================================================

                            User / CLI / Campaign
                                     |
                                     v
                         Scenario Management Layer
                                     |
                                     v
                       Execution Orchestration Layer
                                     |
                                     v
                            Stress Execution Layer
                                     |
                                     v
                         Evidence Collection Layer
                                     |
                                     v
                    Evidence Correlation / Analysis Layer
                                     |
                                     v
                              RCA Framework
                                     |
                                     v
                    Engineering Reasoning Framework
                                     |
                                     v
                         Web UI / Dashboard Layer
```

Each layer has a clear responsibility and should remain loosely coupled from the others.

---

# 4. Architecture Layers

## 4.1 Scenario Management Layer

### Responsibility

The Scenario Management Layer owns the logical test intent.

It is responsible for:

* Scenario selection
* Scenario metadata
* Suite / campaign execution
* Run ID generation
* Target resolution
* Target artifact generation
* Passing scenario context to downstream execution stages

### Primary Files

```text
controller/fault_injection_runner.py
controller/campaign_runner.py
controller/suite_registry.py
campaigns/
suites/
```

### Key Concept

A scenario is not the same thing as a stress action.

A scenario describes the validation objective.

A stress action is only the event used to exercise the network.

Example:

```text
Scenario:
    ecmp_member_degraded_hold_restore

Stress mode:
    interface_hold_restore

Validation objective:
    Hold selected ECMP members down, validate degraded-state behavior, restore, and validate recovery.
```

### Extension Point

To add a new scenario, the framework should define:

* Scenario name
* Description
* Stress mode
* Target selection policy
* Expected behavior
* RCA/validation expectations

---

## 4.2 Execution Orchestration Layer

### Responsibility

The Execution Orchestration Layer coordinates the full lifecycle of one scenario execution.

It controls the order of operations:

```text
Target resolution
    ↓
Stress execution
    ↓
RCA case execution
    ↓
UI report generation
    ↓
Post-processing / enrichment
    ↓
Validation and classification
```

### Primary File

```text
controller/fault_injection_runner.py
```

### Central Function

```text
run_single_scenario()
```

### Key Responsibilities of run_single_scenario()

`run_single_scenario()` acts as the master pipeline driver for a single scenario.

It performs:

1. Scenario lookup
2. Target resolution
3. Resolved target artifact generation
4. Stress run ID creation
5. Stress event execution
6. RCA case generation
7. UI report generation
8. Phase-aware telemetry injection
9. CoS hotspot correlation
10. Congestion origin injection
11. ECMP recovery view injection
12. Validation and classification
13. Topology visualization generation
14. Final result artifact generation

### Design Rationale

The orchestration layer exists so that every scenario follows a consistent lifecycle.

This prevents each new scenario from building its own unique execution flow.

---

## 4.3 Stress Execution Layer

### Responsibility

The Stress Execution Layer performs the actual disruptive or observational action against the fabric.

Examples:

* Interface bounce
* Interface hold/restore
* BGP clear
* Future daemon restart
* Future reboot
* Future ISSU
* Future route churn

### Primary File

```text
controller/stress_orchestrator.py
```

### Key Functions

```text
run_stress_action()
run_parallel_stress_actions()
run_single_stress_target()
run_interface_bounce()
run_interface_hold_restore()
run_bgp_clear()
```

### Current Dispatch Model

Current stress execution uses a stress-mode dispatcher.

Conceptually:

```text
stress_mode
    ↓
run_stress_action()
    ↓
parse_targets()
    ↓
run_parallel_stress_actions()
    ↓
run_single_stress_target()
    ↓
specific stress implementation
```

Example:

```text
interface_hold_restore
    ↓
run_interface_hold_restore()
```

### Extension Point

To add a new stress type:

1. Add new stress mode.
2. Add target parsing support if needed.
3. Implement a stress function.
4. Add dispatcher mapping in `run_single_stress_target()`.
5. Ensure returned result follows the standard stress result schema.

---

## 4.4 Evidence Collection Layer

### Responsibility

The Evidence Collection Layer gathers raw facts from the system.

Evidence can come from:

* gNMI telemetry
* CLI output
* IXIA traffic statistics
* RoCEv2 traffic counters
* Queue / CoS telemetry
* ECMP state
* Interface health
* Logs
* Core files
* Alarms
* Topology

### Representative Files

```text
controller/telemetry_monitor.py
controller/telemetry_analyzer.py
controller/telemetry_diff.py
controller/fabric_evidence_collector.py
controller/cos_state_collector.py
controller/ecmp_phase_sampler.py
controller/traffic_verifier.py
controller/ixia_rocev2_stats.py
controller/ixia_live_monitor.py
controller/ixia_stats_collector.py
```

### Design Rationale

Evidence collection is intentionally separated from engineering reasoning.

Collectors should collect facts.

They should not decide final root cause.

This separation allows reasoning logic to evolve independently from data collection.

---

## 4.5 Evidence Correlation and Analysis Layer

### Responsibility

The Evidence Correlation Layer converts raw evidence into structured findings.

It performs:

* Delta analysis
* Hotspot ranking
* Queue classification
* CoS correlation
* Congestion origin detection
* ECMP recovery analysis
* RoCEv2 impact analysis
* Traffic flow correlation

### Representative Files

```text
controller/congestion_analyzer.py
controller/congestion_delta_analyzer.py
controller/congestion_inspector.py
controller/deep_congestion_inspector.py
controller/cos_hotspot_correlator.py
controller/fabric_hotspot_ranker.py
controller/root_cause_correlator.py
controller/ecmp_recovery_analyzer.py
controller/ecmp_recovery_view.py
controller/rocev2_deep_inspector.py
controller/rocev2_hotspot_report.py
```

### Key Output

This layer produces structured evidence that can be consumed by the RCA framework and engineering reasoning engine.

Examples:

```text
top hotspot
queue classification
tail-drop trend
ECMP recovery status
RoCE victim flow
congestion origin candidate
```

---

## 4.6 RCA Framework

### Responsibility

The RCA Framework builds the unified report consumed by the UI.

It takes scenario artifacts, telemetry artifacts, traffic artifacts, and analysis artifacts, then normalizes them into:

```text
rca_case_summary.json
rca_ui_report.json
```

### Primary Files

```text
controller/run_rca_case.py
controller/rca_ui_report_builder.py
```

### rca_ui_report_builder.py Responsibilities

The UI report builder creates a UI-friendly report containing:

* Summary
* Root cause
* Events
* Evidence index
* Topology entities
* Traffic health
* Interface health
* Telemetry health
* CoS health
* ECMP recovery view
* Engineering reasoning
* Bug candidate signals
* Stress classification

### Design Rationale

The RCA report is built as a normalized JSON document so that downstream systems do not need to understand every raw artifact format.

The UI and reasoning engine consume a stable report structure.

---

## 4.7 Engineering Reasoning Framework

### Responsibility

The Engineering Reasoning Framework converts technical findings into engineering explanations.

It answers:

* What happened?
* Did the event execute?
* Did ECMP recover?
* Where is the congestion origin?
* Was traffic impacted?
* What evidence supports the conclusion?
* Could there be another explanation?
* How confident is the conclusion?

### Primary File

```text
controller/engineering_reasoning_builder.py
```

### Current Reasoning Modules

```text
Event Reasoning
ECMP Reasoning
Queue / Discard Reasoning
Interface / Physical Reasoning
RoCEv2 Reasoning
Evidence Reasoning Chain
Causality Reasoning
Confidence Breakdown
Engineering Verdict
```

### Engineering Confidence

Engineering Confidence measures the strength and completeness of supporting evidence.

It does not mean:

* Severity
* Customer impact
* Probability of software defect

It means:

```text
How strongly does available evidence support the engineering conclusion?
```

### Design Rationale

Engineering reasoning is separated from RCA report construction.

This allows the framework to improve reasoning without changing telemetry collection or UI generation.

---

## 4.8 Visualization Framework

### Responsibility

The Visualization Framework presents the RCA in a form usable by both executives and engineers.

### Primary Files

```text
controller/rca_ui_server.py
webui/index.html
webui/app.js
webui/styles.css
controller/topology_html_report.py
```

### UI Structure

The UI currently contains:

* Executive RCA Dashboard
* Engineering Investigation Report
* Event Investigation
* ECMP Investigation
* Queue / Discard Investigation
* Interface / Physical Investigation
* RoCEv2 Investigation
* Evidence Reasoning Chain
* Causality Analysis
* Confidence Breakdown
* Final Engineering Verdict
* Topology View
* Traffic / RoCE health
* CoS hotspot details
* Metadata

### Design Rationale

The UI separates audiences:

* Executive dashboard gives high-level outcome.
* Engineering investigation gives detailed evidence and reasoning.

---

# 5. End-to-End Data Flow

```text
CLI / User
    ↓
fault_injection_runner.py
    ↓
run_single_scenario()
    ↓
resolve_targets_for_scenario()
    ↓
run_stress_event()
    ↓
stress_orchestrator.py
    ↓
stress_orchestrator_report.json
    ↓
run_rca_case()
    ↓
rca_case_summary.json
    ↓
rca_ui_report_builder.py
    ↓
rca_ui_report.json
    ↓
engineering_reasoning_builder.py
    ↓
engineering_reasoning
    ↓
webui/app.js
    ↓
Executive RCA Dashboard + Engineering Investigation UI
```

---

# 6. Artifact Flow

The system is artifact-driven.

Important artifacts include:

```text
resolved_targets.json
stress_orchestrator_report.json
degraded_member_hold_event.json
rca_case_summary.json
cos_hotspot_correlation.json
rca_ui_report.json
fault_injection_validation.json
runtime_summary.json
topology_view.html
```

Each stage writes artifacts that can be inspected independently.

This improves:

* Debuggability
* Reproducibility
* RCA traceability
* Future automation

---

# 7. Core Architectural Principles

## Principle 1: Evidence Before Conclusions

The framework should not produce a conclusion only because a fault was injected.

A conclusion must be based on evidence such as:

* Event execution
* ECMP recovery
* Queue behavior
* Interface health
* RoCE traffic impact
* Telemetry deltas
* Logs / alarms / cores

---

## Principle 2: Separate Collection from Reasoning

Telemetry collectors collect facts.

Reasoning modules interpret facts.

This avoids mixing data collection logic with engineering interpretation.

---

## Principle 3: Common RCA Pipeline for All Scenarios

Different scenarios should converge into the same RCA pipeline.

Whether the scenario is interface flap, ISSU, SNMP, reboot, or route churn, the framework should still produce:

```text
case summary
UI report
engineering reasoning
validation result
```

---

## Principle 4: Scenario-Specific Triggers, Shared RCA

New tests should primarily add:

* New scenario metadata
* New stress mode
* New validators if required

They should not require a new RCA pipeline.

---

## Principle 5: Engineering Explainability

The platform must explain why it reached a conclusion.

This is why the system includes:

* Evidence chain
* Alternative explanations
* Confidence breakdown
* Engineering verdict

---

# 8. Extension Model

New capabilities should be added through defined extension points.

## New Scenario

Add scenario metadata and target selection policy.

## New Stress Mode

Add new stress mode in the stress execution layer.

## New Evidence Type

Add collector and normalize output into RCA artifacts.

## New Analysis

Add correlation/analyzer module.

## New Reasoning

Add or extend engineering reasoning module.

## New UI Section

Render new report fields in the Web UI.

---

# 9. Current Validated Scenario Family

The current validated family is:

```text
ECMP degraded-hold restore validation
```

Validated across:

```text
Leaf1
Leaf2
Leaf3
Leaf4
Leaf5
Leaf6
Leaf7
```

Key observed patterns:

* Leaf2/3/4: recurring leaf1 q8 multicast/lossy queue pressure
* Leaf5/6/7: q0 queue-without-explicit-scheduler pattern
* RoCEv2 Flow Group 84 repeatedly observed as impacted victim flow
* ECMP recovery generally reported no event-induced regression
* Engineering confidence varies based on event evidence, scheduler mapping, and telemetry completeness

---

# 10. Known Architectural Gaps

Current known gaps:

* Engineering conclusion still contains some rule-based wording.
* Inference engine is not yet fully separated.
* Interface telemetry may be incomplete for some RCA runs.
* Scheduler/CoS mapping is not always available.
* Some long-running scenarios need dedicated campaign mode.
* ISSU, reboot, route churn, SNMP, and longevity workflows are not fully integrated yet.

---

# 11. Future Architecture Enhancements

Planned improvements:

* Dedicated engineering inference engine
* Generic stress plugin registry
* Scenario YAML/JSON schema
* Standard validator registry
* Timeline-aware causality engine
* Multi-scenario comparison dashboard
* Historical RCA learning
* Automated recommendations
* Long-running campaign mode
* Release readiness scoring

---

# 12. Summary

Fabric Controller is evolving into a modular, evidence-driven, AI-assisted RCA platform.

Its strongest architectural property is that new scenarios can reuse the same downstream RCA and reasoning pipeline.

The long-term goal is to make every validation scenario produce not just pass/fail output, but an engineering-grade RCA explaining what happened, why it happened, what evidence supports the conclusion, and how confident the framework is in that conclusion.

