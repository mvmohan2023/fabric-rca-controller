# Fabric Controller
# Engineering Design Specification (EDS)

**Version:** 1.0 (Living Document)

**Owner:** Mohan Kumar M V

---

# 1. Purpose

Fabric Controller is an AI-driven Data Center Fabric Validation and Root Cause Analysis (RCA) platform designed to automate fault injection, telemetry collection, traffic validation, engineering reasoning, and executive RCA reporting for large-scale Clos network fabrics.

Unlike traditional test automation frameworks that stop after pass/fail validation, Fabric Controller is designed to answer engineering questions such as:

- What happened?
- Where did it happen?
- Why did it happen?
- Was traffic impacted?
- Did the network recover?
- What evidence supports the conclusion?
- What should an engineer investigate next?

The long-term vision is to build an engineering assistant capable of automatically executing complex network validation scenarios and producing human-readable engineering RCA without manual investigation.

---

# 2. Vision

The project is evolving from a traditional fault-injection framework into an intelligent engineering validation platform.

Current capabilities include:

• Fault Injection
• Fabric Stress Validation
• Telemetry Collection
• ECMP Recovery Analysis
• Queue / Congestion Analysis
• RoCEv2 Traffic Analysis
• Engineering Reasoning
• Executive RCA Dashboard
• Interactive Web UI

Future capabilities include:

• ISSU Validation
• Route Churn Analysis
• SNMP Validation
• Telemetry Health Validation
• Reboot / Restart Validation
• Multi-day Longevity Campaigns
• AI-assisted Root Cause Recommendation
• Intelligent Scenario Recommendation

---

# 3. System Overview

Fabric Controller consists of five major subsystems.

1. Scenario Framework
2. Stress Execution Framework
3. Evidence Collection Framework
4. RCA Framework
5. Engineering Reasoning Framework

These subsystems work together to execute validation scenarios, collect evidence, correlate telemetry, perform root cause analysis, and present engineering-friendly RCA reports.

---

# 4. High-Level Architecture

User
    │
    ▼
Scenario Selection
    │
    ▼
Scenario Framework
    │
    ▼
Stress Execution
    │
    ▼
Telemetry / Traffic Collection
    │
    ▼
Evidence Collection
    │
    ▼
RCA Generation
    │
    ▼
Engineering Reasoning
    │
    ▼
Executive Dashboard
    │
    ▼
Engineering Investigation UI

---

# 5. Primary Design Goals

The architecture was designed around the following principles:

• Modular
• Extensible
• Phase-aware
• Data-driven
• Platform Independent
• Telemetry First
• RCA Focused
• Engineering Explainability

The objective is to make new validation scenarios reusable without redesigning the RCA pipeline.

---

# 6. Current Implementation Status

Completed

✓ Scenario execution framework

✓ Parallel stress orchestration

✓ Target resolution

✓ Phase-aware telemetry collection

✓ ECMP recovery analysis

✓ Queue hotspot correlation

✓ Congestion origin analysis

✓ RoCEv2 Deep Inspection

✓ Engineering reasoning engine

✓ Executive RCA Summary

✓ Interactive Web Dashboard

✓ Leaf1–Leaf7 degraded-hold validation scenarios

In Progress

• Engineering Design Specification

• Framework documentation

Planned

• Generic scenario extension framework

• ISSU validation

• Route churn validation

• SNMP validation

• Reboot validation

• Telemetry validation

• AI-assisted scenario recommendation

---

# 7. Document Map

This Engineering Design Specification is organized as follows:

01_Executive_Summary.md

High-level overview of the project.

02_System_Architecture.md

Overall architecture and subsystem relationships.

03_Execution_Pipeline.md

Complete execution flow from scenario to dashboard.

04_Scenario_Framework.md

Scenario registry, target resolution, campaign execution.

05_Stress_Execution_Framework.md

Stress execution architecture and event orchestration.

06_Evidence_Collection_Framework.md

Telemetry, traffic, queue, ECMP, and evidence collection.

07_RCA_Framework.md

Artifact generation, RCA report construction, report lifecycle.

08_Engineering_Reasoning_Framework.md

Engineering reasoning, confidence model, evidence chain, executive summary.

09_WebUI_Framework.md

Dashboard architecture and visualization.

10_Extending_The_Framework.md

Developer guide for adding new scenarios.

11_Current_Scenarios.md

Supported scenarios and validation coverage.

12_Design_Decisions.md

Important architectural decisions and rationale.

13_Known_Limitations.md

Current limitations and future improvements.

14_Future_Roadmap.md

Long-term vision.

15_TODO_Backlog.md

Outstanding engineering tasks.

---

# 8. Development Philosophy

Every new feature added to Fabric Controller follows the lifecycle below.

Design

↓

Architecture Review

↓

Implementation

↓

Validation

↓

Documentation

↓

Release

The Engineering Design Specification is considered part of the product itself and is updated whenever major functionality or architecture changes are introduced.

---

# 9. Current Focus

The current focus of the project is to evolve Fabric Controller into a reusable engineering validation platform capable of supporting multiple validation domains while preserving a common RCA and engineering reasoning pipeline.

The immediate priority is documenting the existing architecture before expanding the framework with additional scenario types such as ISSU, Route Churn, SNMP, Reboot, Telemetry Validation, and Longevity Testing.


---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | YYYY-MM-DD | Mohan Kumar M V | Initial version |

---

## Related Documents

- 02_System_Architecture.md
- 03_Execution_Pipeline.md
