# 03. Execution Flow

**Architecture Version:** 2.0 Draft-1

**Platform:** Fabric Validation Platform (FVP)

**Status:** Living Architecture Document

---

# 1. Purpose

This document describes the end-to-end runtime execution flow of the Fabric Validation Platform (FVP).

It explains how a validation campaign progresses from user invocation to engineering analysis and executive reporting. The execution flow is designed to be deterministic, traceable, and extensible while preserving backward compatibility with existing workflows.

---

# 2. Execution Philosophy

FVP follows an evidence-driven execution model.

Rather than simply executing stress scenarios, the platform:

1. Validates the environment before any action.
2. Executes controlled engineering events.
3. Collects evidence throughout execution.
4. Compares expected versus observed behavior.
5. Performs engineering root-cause analysis.
6. Produces reports for engineers, technical leads, and executives.

Every stage generates artifacts that become inputs to later stages.

---

# 3. High-Level Execution Flow

```
User
 │
 ▼
Fault Injection Runner
 │
 ▼
Campaign Initialization
 │
 ▼
Scenario Resolution
 │
 ▼
Target Resolution
 │
 ▼
Pre-Event Validation
 │
 ▼
Stress Execution
 │
 ▼
Evidence Collection
 │
 ▼
Engineering Validation
 │
 ▼
Root Cause Analysis
 │
 ▼
Engineering Reasoning
 │
 ▼
UI Report Generation
 │
 ▼
Campaign Summary
 │
 ▼
Executive Release Report
```

---

# 4. Primary Entry Point

The standard entry point is:

```bash
python -m controller.fault_injection_runner
```

The Fault Injection Runner coordinates the entire execution lifecycle.

Its responsibilities include:

- Parsing command-line arguments
- Resolving scenario definitions
- Resolving execution targets
- Creating campaign artifacts
- Invoking the Stress Orchestrator
- Invoking the RCA pipeline
- Aggregating results
- Producing final PASS/FAIL status

---

# 5. Runtime Stages

## Stage 1 — Campaign Initialization

Purpose

Create a new execution context.

Activities

- Validate CLI arguments
- Generate Run ID
- Create campaign directories
- Initialize logging
- Load configuration
- Resolve topology
- Resolve inventory

Outputs

- Campaign directory
- Run metadata
- Initial execution context

---

## Stage 2 — Scenario Resolution

Purpose

Resolve the requested engineering scenario.

Activities

- Lookup scenario
- Validate parameters
- Determine stress mode
- Load scenario metadata
- Verify supported options

Outputs

- Scenario configuration
- Execution parameters

---

## Stage 3 — Target Resolution

Purpose

Determine which devices and interfaces participate.

Activities

- Resolve nodes
- Resolve interfaces
- Auto-select targets (when applicable)
- Validate topology

Outputs

- Target list
- Parallel execution groups

---

## Stage 4 — Pre-Event Validation

Purpose

Ensure the fabric is healthy before introducing stress.

Activities

- Device facts collection
- Topology discovery
- Topology validation
- Stress precheck

Outputs

- Device inventory
- Topology graph
- Fabric validation report
- Precheck report

Acceptance Criteria

- Physical links healthy
- BGP healthy
- IP consistency maintained
- Ready-for-stress = PASS

---

## Stage 5 — Stress Execution

Purpose

Execute the engineering scenario.

Current supported scenarios include:

### Interface Family

- Interface Bounce
- Interface Flap
- Interface Shutdown
- Interface Restore
- Interface Hold Restore

### Routing

- BGP Clear

Future families

- ISSU
- Platform
- Reboot
- Telemetry
- Process restart

Outputs

- Stress report
- Iteration summaries
- Execution logs

---

## Stage 6 — Evidence Collection

Purpose

Capture engineering evidence throughout execution.

Evidence sources include:

- Device facts
- Interface statistics
- Queue statistics
- Congestion metrics
- Telemetry
- RoCEv2 statistics
- IXIA traffic
- ECMP counters
- Validation snapshots

Evidence is collected during:

- Baseline
- Running
- Degraded
- Recovery
- Post-event

---

## Stage 7 — Engineering Validation

Purpose

Compare observed behavior against engineering expectations.

Validation categories include:

- Interface state
- Traffic behavior
- Telemetry consistency
- Congestion behavior
- ECMP recovery
- Routing stability
- Platform health

Outputs

PASS / FAIL assessment with supporting evidence.

---

## Stage 8 — Root Cause Analysis

Purpose

Determine what happened and why.

Current analysis includes:

- Congestion analysis
- Delta analysis
- ECMP analysis
- RoCEv2 analysis
- Root-cause correlation
- Intent correlation

Outputs

- RCA summary
- Correlation report
- Confidence indicators

---

## Stage 9 — Engineering Reasoning

Purpose

Translate engineering evidence into human-readable conclusions.

Responsibilities

- Summarize findings
- Explain failures
- Explain recovery
- Generate confidence statements
- Highlight engineering observations

Outputs

Engineering Reasoning Report

---

## Stage 10 — Report Generation

Purpose

Generate reports for different audiences.

Current outputs

- Stress Report
- Validation Report
- RCA Summary
- UI JSON
- Campaign Summary

Future outputs

- Executive Release Dashboard
- Historical Trend Report
- Feature Health Report
- Release Confidence Report

---

# 6. Runtime State Machine

Each campaign progresses through the following execution states.

```
CREATED
   │
   ▼
INITIALIZED
   │
   ▼
SCENARIO_RESOLVED
   │
   ▼
TARGETS_RESOLVED
   │
   ▼
PRE_VALIDATED
   │
   ▼
RUNNING
   │
   ▼
DEGRADED
   │
   ▼
RECOVERING
   │
   ▼
VALIDATING
   │
   ▼
RCA_RUNNING
   │
   ▼
REPORTING
   │
   ▼
COMPLETED
```

Future enhancements may expose these states through REST APIs or live dashboards.

---

# 7. Artifact Lifecycle

The execution pipeline generates a sequence of artifacts.

```
Scenario
   │
   ▼
Stress Orchestrator Report
   │
   ▼
Validation Report
   │
   ▼
RCA Case Summary
   │
   ▼
Engineering Reasoning
   │
   ▼
RCA UI Report
   │
   ▼
Campaign Summary
   │
   ▼
Executive Release Report
```

Each artifact remains available for traceability and debugging.

---

# 8. Failure Handling

Failures are handled at multiple levels.

### Validation Failures

Execution continues where safe, preserving evidence.

### Stress Failures

Scenario status recorded.

Recovery attempted when applicable.

### RCA Failures

Partial evidence retained.

Reason recorded.

### Report Generation Failures

Engineering artifacts remain available.

Report generation errors are isolated.

---

# 9. Parallel Execution

The platform supports parallel execution where appropriate.

Current examples include:

- Multiple interface targets
- Parallel stress groups
- Parallel evidence collection

Future enhancements may include distributed execution across multiple controllers.

---

# 10. Future Execution Enhancements

Planned enhancements include:

- Event-driven execution pipeline
- Workflow engine
- Resume from checkpoints
- Distributed execution
- Scenario dependency graph
- Dynamic scheduling
- Live execution dashboard
- Plugin execution model

These enhancements build on the current execution pipeline without replacing it.

---

# 11. Engineering Principles

The execution flow follows these principles.

### Deterministic

The same inputs should produce the same execution path.

### Evidence First

Every engineering decision must be supported by collected artifacts.

### Failure Isolation

Failures should not unnecessarily terminate the entire campaign.

### Traceability

Every report should link back to the artifacts that produced it.

### Backward Compatibility

Existing execution workflows remain unchanged while new capabilities are layered on top.

---

# 12. Summary

The execution flow defines the operational backbone of the Fabric Validation Platform.

Beginning with campaign initialization and ending with engineering and executive reporting, every stage contributes evidence that supports engineering validation and release qualification.

The architecture emphasizes modularity, traceability, and extensibility, allowing new scenario families, validation engines, analytics, and AI-assisted reasoning to be integrated without disrupting the existing execution pipeline.
