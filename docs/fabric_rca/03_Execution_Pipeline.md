# Fabric Controller
# Engineering Design Specification (EDS)

# 03. Execution Pipeline

**Version:** 1.0

---

# 1. Purpose

This document describes the complete execution lifecycle of a Fabric Controller scenario, from user invocation through stress execution, telemetry collection, RCA generation, engineering reasoning, and final dashboard visualization.

Unlike a traditional test framework where execution stops after a PASS/FAIL decision, Fabric Controller continues through multiple post-processing stages to generate engineering-grade root cause analysis.

This document serves as the primary reference for understanding how every subsystem interacts during execution.

---

# 2. High-Level Pipeline

```text
                          User
                            │
                            ▼
                    CLI / Campaign
                            │
                            ▼
                  Scenario Resolution
                            │
                            ▼
                  Target Resolution
                            │
                            ▼
                Campaign Initialization
                            │
                            ▼
                 Stress Event Execution
                            │
                            ▼
              Phase-aware Telemetry Collection
                            │
                            ▼
                 RCA Case Generation
                            │
                            ▼
                 RCA UI Report Builder
                            │
                            ▼
             Engineering Reasoning Engine
                            │
                            ▼
           Validation & Result Classification
                            │
                            ▼
             Executive & Engineering Dashboard
```

---

# 3. Execution Stages

The Fabric Controller execution pipeline is composed of multiple independent stages.

Each stage has a clearly defined responsibility and communicates with downstream stages using generated artifacts.

---

# Stage 1 – User Invocation

Purpose

Receive the user's validation request.

Typical command

```bash
python3 -m controller.fault_injection_runner \
    --scenario ecmp_member_degraded_hold_restore \
    ...
```

Primary File

```
controller/fault_injection_runner.py
```

Output

Scenario configuration.

---

# Stage 2 – Scenario Resolution

Purpose

Locate the requested scenario definition.

The scenario definition describes:

• Scenario name

• Stress mode

• Validation policy

• Timing configuration

• Target selection policy

• Metadata

Output

Internal scenario configuration object.

---

# Stage 3 – Target Resolution

Primary Function

```
resolve_targets_for_scenario()
```

Purpose

Identify the exact nodes and interfaces participating in the validation.

Activities

• Read inventory

• Apply target policy

• Filter interfaces

• Validate platform support

• Build target list

Generated Artifact

```
resolved_targets.json
```

Why this stage exists

Target selection is isolated from stress execution so that new scenarios can reuse the same resolution logic.

---

# Stage 4 – Campaign Initialization

Purpose

Create the runtime context.

Activities

• Generate run ID

• Create artifact directories

• Initialize progress logging

• Store runtime metadata

Artifacts

```
runtime_summary.json
progress.log
```

---

# Stage 5 – Stress Execution

Primary Component

```
stress_orchestrator.py
```

Primary Functions

```
run_stress_action()

run_parallel_stress_actions()

run_single_stress_target()
```

Purpose

Execute the requested stress event.

Examples

• Interface Hold

• Interface Bounce

• BGP Clear

• Daemon Restart

• Future ISSU

• Future Route Churn

Generated Artifact

```
stress_orchestrator_report.json
```

---

# Stage 6 – Phase-aware Evidence Collection

Purpose

Collect engineering evidence before, during and after stress execution.

Evidence Sources

• Telemetry

• CLI

• Queue Statistics

• ECMP State

• CoS

• Interface Health

• IXIA Traffic

• RoCEv2 Statistics

• Device Logs

• Alarms

Design Principle

Collectors gather facts.

They do not generate engineering conclusions.

---

# Stage 7 – RCA Case Generation

Primary Component

```
run_rca_case.py
```

Purpose

Merge collected evidence into a normalized RCA model.

Generated Artifact

```
rca_case_summary.json
```

This becomes the canonical input for downstream analysis.

---

# Stage 8 – RCA UI Report Generation

Primary Component

```
rca_ui_report_builder.py
```

Purpose

Transform the RCA case summary into a UI-friendly data model.

Generated Artifact

```
rca_ui_report.json
```

This report contains:

• Queue Analysis

• ECMP Recovery

• Interface Health

• Congestion Origin

• Traffic Analysis

• Executive Summary

• Entity Mapping

• Metadata

---

# Stage 9 – Engineering Reasoning

Primary Component

```
engineering_reasoning_builder.py
```

Purpose

Convert technical observations into engineering conclusions.

Reasoning Modules

• Event Reasoning

• Queue Reasoning

• ECMP Reasoning

• Interface Reasoning

• RoCEv2 Reasoning

• Evidence Chain

• Alternative Explanations

• Engineering Confidence

• Engineering Verdict

Unlike the RCA framework, this stage interprets evidence rather than collecting it.

---

# Stage 10 – Validation & Classification

Purpose

Validate generated artifacts.

Typical checks

• Required files exist

• RCA completeness

• UI consistency

• Stress report validation

• Scenario classification

Generated Artifacts

```
fault_injection_validation.json

runtime_summary.json
```

---

# Stage 11 – Dashboard Generation

Primary Components

```
webui/

app.js

index.html
```

Purpose

Render engineering investigation results.

The dashboard provides two complementary views.

Executive View

High-level outcome intended for management.

Engineering View

Detailed telemetry, queue, ECMP, traffic, reasoning, and RCA investigation.

---

# 4. Artifact Lifecycle

The execution pipeline is artifact-driven.

```text
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

Every stage enriches the execution rather than replacing previous results.

---

# 5. Extension Points

The execution pipeline is intentionally designed to support new validation scenarios.

Typical extension path

```text
New Scenario
        │
        ▼
Target Resolution
        │
        ▼
Stress Mode
        │
        ▼
Evidence Collection
        │
        ▼
Optional Analysis
        │
        ▼
Engineering Reasoning
        │
        ▼
Dashboard
```

Most new validation features should only require changes in the early stages of the pipeline while reusing the downstream RCA framework.

---

# 6. Pipeline Design Principles

## Principle 1

Evidence is collected before engineering conclusions are generated.

---

## Principle 2

Artifacts are enriched progressively.

Downstream stages extend previous artifacts rather than recreating them.

---

## Principle 3

Stress execution is independent of RCA generation.

This allows multiple validation scenarios to share the same RCA framework.

---

## Principle 4

Engineering reasoning is isolated from telemetry collection.

Collectors gather facts.

Reasoning interprets those facts.

---

## Principle 5

Every scenario should converge into the same RCA pipeline.

This enables consistent reporting regardless of the scenario type.

---

# 7. Current Pipeline Status

Current validated execution flow

✓ Scenario Resolution

✓ Target Resolution

✓ Stress Execution

✓ Phase-aware Telemetry

✓ RCA Case Generation

✓ RCA UI Report

✓ Engineering Reasoning

✓ Executive Dashboard

Validated Scenarios

• Leaf1 Degraded Hold

• Leaf2 Degraded Hold

• Leaf3 Degraded Hold

• Leaf4 Degraded Hold

• Leaf5 Degraded Hold

• Leaf6 Degraded Hold

• Leaf7 Degraded Hold

---

# 8. Future Enhancements

The execution pipeline is designed to support future capabilities without architectural redesign.

Planned integrations include:

• ISSU Validation

• Route Churn Validation

• SNMP Validation

• Reboot Validation

• Daemon Restart Validation

• Long-running Campaign Mode

• Historical RCA Learning

• AI-assisted Engineering Recommendations

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial execution pipeline specification |
