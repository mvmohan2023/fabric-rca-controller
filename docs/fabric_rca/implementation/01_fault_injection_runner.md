# Fabric Controller
# Implementation Guide

# 01. fault_injection_runner.py

**Module:** `controller/fault_injection_runner.py`

**Status:** Living Implementation Guide

---

# 1. Purpose

`fault_injection_runner.py` is the master orchestration module of the Fabric Controller platform.

It is responsible for coordinating the complete execution lifecycle of a validation scenario. The module accepts user input through the command-line interface (CLI), resolves the execution targets, invokes stress execution, generates Root Cause Analysis (RCA), enriches engineering reports, validates generated artifacts, and produces the final execution results.

Rather than implementing domain-specific engineering logic, this module orchestrates the interaction between the Scenario Framework, Stress Execution Framework, Evidence Collection Framework, RCA Framework, Engineering Reasoning Framework, and Web UI Framework.

---

# 2. Responsibilities

The primary responsibilities of this module are:

- CLI argument parsing
- Scenario lookup and validation
- Target resolution
- Stress execution orchestration
- RCA case generation
- UI report generation
- Engineering evidence enrichment
- Validation of generated artifacts
- Scenario classification
- Suite execution

---

# 3. High-Level Call Flow

```text
main()
    │
    ▼
parse_args()
    │
    ▼
run_single_scenario() / run_suite()
    │
    ▼
resolve_targets_for_scenario()
    │
    ▼
run_stress_event()
    │
    ▼
run_rca_case()
    │
    ▼
build_ui_report()
    │
    ▼
run_cos_hotspot_correlation()
    │
    ▼
inject_congestion_origin_analysis_into_ui_report()
    │
    ▼
inject_ecmp_recovery_view_into_ui_report()
    │
    ▼
validate_stress_report()
    │
    ▼
validate_rca_summary()
    │
    ▼
validate_ui_report()
    │
    ▼
build_evidence_rollup()
    │
    ▼
classify_scenario_result()
    │
    ▼
fault_injection_validation.json
```

---

# 4. Major Function Groups

## Utility Helpers

- `utc_now_iso()`
- `ensure_dir()`
- `load_json()`
- `write_json()`
- `run_subprocess()`

---

## Target Resolution

Responsible for identifying the nodes and interfaces that participate in the stress event.

Primary functions:

- `extract_fabric_interfaces()`
- `parse_explicit_targets()`
- `pick_random_targets()`
- `resolve_targets_for_scenario()`
- `write_resolved_targets_artifacts()`

---

## Stress Execution

Responsible for initiating the stress event.

Primary functions:

- `build_stress_run_id()`
- `run_stress_event()`

---

## RCA Pipeline

Responsible for generating the canonical RCA model.

Primary functions:

- `run_rca_case()`
- `build_ui_report()`
- `run_cos_hotspot_correlation()`

---

## Report Enrichment

Responsible for enhancing the UI report with engineering-specific analysis.

Primary functions:

- `inject_congestion_origin_analysis_into_ui_report()`
- `inject_ecmp_recovery_view_into_ui_report()`

---

## Validation

Responsible for validating generated artifacts and determining the final scenario status.

Primary functions:

- `validate_stress_report()`
- `validate_rca_summary()`
- `validate_ui_report()`
- `build_evidence_rollup()`
- `classify_scenario_result()`

---

## Scenario Execution

Top-level orchestration functions.

Primary functions:

- `run_single_scenario()`
- `run_suite()`
- `main()`

---

# 5. Execution Stages

Although `run_single_scenario()` is a large orchestration function, its behavior can be understood as six logical stages.

---

## Stage 1 – Initialize Run

Responsibilities:

- Initialize progress logger
- Load scenario metadata
- Record execution timing
- Prepare runtime context

---

## Stage 2 – Resolve Targets

Primary function:

`resolve_targets_for_scenario()`

Responsibilities:

- Resolve nodes and interfaces
- Apply target selection policy
- Validate selected targets
- Generate target artifacts

Primary artifact:

`resolved_targets.json`

---

## Stage 3 – Execute Stress

Primary function:

`run_stress_event()`

Responsibilities:

- Execute stress event
- Pass execution parameters
- Produce stress execution report

Primary artifact:

`stress_orchestrator_report.json`

---

## Stage 4 – Generate RCA

Primary function:

`run_rca_case()`

Responsibilities:

- Execute RCA pipeline
- Correlate collected evidence
- Produce canonical RCA summary

Primary artifact:

`rca_case_summary.json`

---

## Stage 5 – Build & Enrich UI

Primary functions:

- `build_ui_report()`
- `run_cos_hotspot_correlation()`
- `inject_congestion_origin_analysis_into_ui_report()`
- `inject_ecmp_recovery_view_into_ui_report()`

Responsibilities:

- Generate initial UI report
- Enrich engineering evidence
- Inject congestion analysis
- Inject ECMP recovery analysis
- Produce final engineering dashboard

Primary artifact:

`rca_ui_report.json`

---

## Stage 6 – Validate & Finalize

Responsibilities:

- Validate generated artifacts
- Build evidence rollup
- Classify scenario result
- Write runtime summaries
- Generate final validation report

Primary artifacts:

- `fault_injection_validation.json`
- `runtime_summary.json`

---

# 6. Primary Artifacts

| Artifact | Purpose |
|----------|---------|
| `resolved_targets.json` | Final selected stress targets |
| `stress_orchestrator_report.json` | Stress execution results |
| `rca_case_summary.json` | Canonical RCA model |
| `cos_hotspot_correlation.json` | Queue and CoS correlation |
| `rca_ui_report.json` | Final engineering dashboard |
| `fault_injection_validation.json` | Overall scenario validation |
| `runtime_summary.json` | Runtime metadata |

---

# 7. Extension Points

Most new validation scenarios require modifications in one or more of the following areas:

## Scenario Registration

Register new scenario metadata.

---

## Target Resolution

Add new target selection policies if required.

---

## Stress Execution

Extend `run_stress_event()` with new stress modes.

---

## Validation

Extend `classify_scenario_result()` when new validation semantics are introduced.

---

## Report Enrichment

Add engineering evidence injection only if the new scenario introduces additional evidence domains.

In most cases, downstream RCA generation and Web UI remain reusable.

---

# 8. Refactoring Opportunities

Although functionally well organized, this module has grown into a large orchestration component.

Potential future decomposition:

```text
ScenarioExecutor
        │
        ├── TargetResolutionService
        ├── StressPipelineRunner
        ├── RcaPipelineRunner
        ├── UiEnrichmentPipeline
        ├── ValidationPipeline
        └── ArtifactManager
```

This decomposition would reduce module size while preserving the existing execution pipeline.

---

# 9. Related Modules

This module interacts closely with:

| Module | Responsibility |
|---------|----------------|
| `stress_orchestrator.py` | Stress execution engine |
| `run_rca_case.py` | RCA generation |
| `engineering_reasoning_builder.py` | Engineering reasoning |
| `rca_ui_report_builder.py` | UI report generation |
| `telemetry_monitor.py` | Telemetry collection |
| `telemetry_diff.py` | Telemetry comparison |
| `congestion_analyzer.py` | Congestion analysis |

---

# 10. Related EDS Documents

- `03_Execution_Pipeline.md`
- `04_Scenario_Framework.md`
- `05_Stress_Execution_Framework.md`
- `08_RCA_Framework.md`
- `09_Engineering_Reasoning_Framework.md`
- `11_Artifact_Catalog.md`
- `13_Extending_The_Framework.md`
- `16_Fault_Injection_Runner_Architecture.md`

---

# Summary

`fault_injection_runner.py` is the orchestration hub of the Fabric Controller platform. It does not implement domain-specific engineering analysis; instead, it coordinates scenario execution, stress injection, RCA generation, engineering report enrichment, artifact validation, and final scenario classification through a structured, artifact-driven execution pipeline.

This document intentionally describes the module at an implementation level without duplicating source code. As the implementation evolves, this guide should remain focused on responsibilities, execution stages, extension points, and interactions with the surrounding framework.
