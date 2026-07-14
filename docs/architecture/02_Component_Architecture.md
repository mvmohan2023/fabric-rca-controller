# 02. Component Architecture

**Architecture Version:** 2.0 Draft-1

**Platform:** Fabric Validation Platform (FVP)

**Status:** Living Architecture Document

---

# 1. Purpose

The Fabric Validation Platform (FVP) is composed of multiple reusable software components that collectively execute engineering validation scenarios, collect evidence, perform validation, generate engineering root-cause analysis (RCA), and produce executive-ready reports.

Unlike a traditional test framework, FVP separates execution, validation, analysis, reasoning, and reporting into independent components. This modular design enables new scenario families to be added without changing the overall execution pipeline.

---

# 2. Architectural Principles

The component architecture follows these principles:

- Single Responsibility
- Separation of Concerns
- Backward Compatibility
- Evidence-Driven Processing
- Reusable Execution Pipeline
- Extensible Scenario Framework
- Layered Engineering Intelligence

Each component owns a clearly defined responsibility and communicates through well-defined artifacts rather than tightly coupled logic.

---

# 3. High-Level Component View

```
                                      User
                                        │
                                        ▼
                        fault_injection_runner.py
                                        │
                   ┌────────────────────┴─────────────────────┐
                   ▼                                          ▼
        stress_orchestrator.py                      run_rca_case.py
                   │                                          │
      ┌────────────┼────────────┐                ┌────────────┼────────────┐
      ▼            ▼            ▼                ▼            ▼            ▼
collect_device  topology     stress       telemetry      RCA Engine   Engineering
   _facts      discovery    precheck      Analysis                    Reasoning
      │            │            │                │            │            │
      └────────────┴────────────┴────────────────┴────────────┴────────────┘
                                        │
                                        ▼
                             rca_ui_report_builder.py
                                        │
                                        ▼
                                 Web UI / Reports
```

---

# 4. Component Responsibilities

## 4.1 Fault Injection Runner

### Module

```
controller/fault_injection_runner.py
```

### Purpose

Acts as the primary orchestration engine for the entire validation campaign.

### Responsibilities

- Parse CLI arguments
- Resolve scenarios
- Resolve execution targets
- Initialize campaign directories
- Invoke Stress Orchestrator
- Invoke RCA pipeline
- Aggregate results
- Generate campaign summary
- Produce overall PASS/FAIL status

### Inputs

- CLI parameters
- Scenario definition
- Topology
- Target nodes/interfaces

### Outputs

- Stress execution request
- Campaign artifacts
- Final validation report

### Called By

User

### Calls

- stress_orchestrator.py
- run_rca_case.py

---

## 4.2 Stress Orchestrator

### Module

```
controller/stress_orchestrator.py
```

### Purpose

Executes engineering stress scenarios while maintaining platform integrity.

### Responsibilities

- Execute interface events
- Execute BGP events
- Execute reboot events
- Execute platform events
- Run pre/post validation
- Archive execution artifacts
- Generate stress reports

### Current Supported Modes

- Interface Bounce
- Interface Flap
- Interface Shutdown
- Interface Restore
- Interface Hold Restore
- BGP Clear
- No-op

### Inputs

- Scenario
- Targets
- Timing parameters

### Outputs

- Stress report
- Validation artifacts

### Calls

- collect_device_facts.py
- topology_discovery.py
- topology_validator.py
- stress_precheck.py

---

## 4.3 Device Facts Collector

### Module

```
controller/collect_device_facts.py
```

### Purpose

Collect inventory and operational facts from every network device.

### Responsibilities

- Hardware inventory
- Software version
- Interface inventory
- Device capabilities

### Outputs

```
artifacts/device_facts/
```

---

## 4.4 Topology Discovery

### Module

```
controller/topology_discovery.py
```

### Purpose

Discover current fabric topology using LLDP and routing information.

### Responsibilities

- Discover links
- Discover neighbors
- Build topology graph

### Outputs

```
artifacts/topology/discovered_topology.json
```

---

## 4.5 Topology Validator

### Module

```
controller/topology_validator.py
```

### Purpose

Validate discovered topology against expected topology.

### Responsibilities

- Link validation
- IP consistency
- BGP validation
- Missing connection detection

### Outputs

Fabric Validation Report

---

## 4.6 Stress Precheck

### Module

```
controller/stress_precheck.py
```

### Purpose

Determine whether the fabric is healthy before stress execution.

### Responsibilities

- Physical health
- Routing health
- Link health
- BGP health

### Output

PASS / FAIL readiness assessment

---

## 4.7 RCA Engine

### Module

```
controller/run_rca_case.py
```

### Purpose

Coordinate engineering root-cause analysis.

### Responsibilities

- Telemetry analysis
- Delta analysis
- Congestion analysis
- ECMP analysis
- Traffic validation
- Root cause correlation

### Outputs

RCA Summary

---

## 4.8 Engineering Reasoning

### Module

```
controller/engineering_reasoning_builder.py
```

### Purpose

Convert engineering evidence into human-readable reasoning.

### Responsibilities

- Explain failures
- Explain recovery
- Build confidence statements
- Summarize engineering conclusions

### Outputs

Engineering reasoning section

---

## 4.9 UI Report Builder

### Module

```
controller/rca_ui_report_builder.py
```

### Purpose

Transform engineering evidence into visualization-friendly JSON.

### Responsibilities

- UI report generation
- Dashboard population
- HTML support
- Executive summaries

---

# 5. Artifact Ownership

| Artifact | Producer | Consumer |
|-----------|----------|----------|
| Device Facts | collect_device_facts | Validation |
| Topology | topology_discovery | topology_validator |
| Validation Report | topology_validator | stress_precheck |
| Stress Report | stress_orchestrator | run_rca_case |
| RCA Summary | run_rca_case | UI Builder |
| Engineering Reasoning | engineering_reasoning_builder | UI Builder |
| UI JSON | rca_ui_report_builder | Web UI |
| Campaign Summary | fault_injection_runner | Executive Reports |

---

# 6. Component Interaction

The platform follows a pipeline architecture.

```
User
 │
 ▼
Fault Injection Runner
 │
 ▼
Stress Orchestrator
 │
 ▼
Evidence Collection
 │
 ▼
Validation
 │
 ▼
RCA
 │
 ▼
Engineering Reasoning
 │
 ▼
UI Builder
 │
 ▼
Executive Report
```

Every stage consumes artifacts generated by the previous stage, ensuring complete traceability.

---

# 7. Extension Points

The architecture is intentionally designed for extension.

Future components can be added without modifying the execution pipeline.

Examples include:

- ISSU Validation
- BGP Validation
- Platform Health
- Memory Leak Detection
- Telemetry Health
- AI Recommendation Engine
- Historical Analytics
- Release Trend Analysis

---

# 8. Error Handling Strategy

Each component is responsible for:

- Input validation
- Exception isolation
- Structured logging
- Artifact preservation
- Graceful failure reporting

Failures are propagated with sufficient context to allow RCA generation rather than terminating execution prematurely.

---

# 9. Component Dependency Rules

To maintain modularity:

- Execution components must not depend on reporting components.
- Validation components must remain independent of UI rendering.
- Engineering reasoning consumes analysis results but does not modify them.
- UI builders consume finalized artifacts only.
- Executive reporting must never directly invoke device operations.

This layering prevents circular dependencies and simplifies future enhancements.

---

# 10. Planned Component Enhancements (FVP v2)

The following architectural enhancements are planned:

| Component | Enhancement |
|-----------|-------------|
| Scenario Registry | Centralized scenario metadata |
| Validation Engine | Common validation contracts |
| RCA Engine | Unified RCA plugin interface |
| Reporting | Executive release dashboards |
| Engineering Reasoning | AI-assisted recommendations |
| Historical Analytics | Multi-release comparison |
| Executive Reporting | Release confidence scoring |
| Plugin Framework | Third-party scenario support |

---

# 11. Summary

The component architecture separates execution, validation, analysis, reasoning, and reporting into reusable software modules. This organization enables the Fabric Validation Platform to evolve incrementally while preserving backward compatibility with the existing implementation.

The current architecture already provides a strong foundation for interface validation, telemetry analysis, congestion inspection, ECMP analysis, and engineering RCA. Version 2 extends this foundation with scenario registries, executive reporting, historical analytics, and AI-assisted engineering without requiring disruptive architectural changes.
