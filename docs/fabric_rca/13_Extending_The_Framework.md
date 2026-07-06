# Fabric Controller
# Engineering Design Specification (EDS)

# 13. Extending the Framework

**Version:** 1.0

**Status:** Living Engineering Design Specification

---

# 1. Purpose

The Fabric Controller platform is designed to be extensible.

New validation scenarios, telemetry collectors, evidence sources, reasoning modules, and dashboard components should integrate into the existing framework with minimal disruption.

This document provides implementation guidance for extending the platform while preserving architectural consistency.

---

# 2. Design Philosophy

Every new capability should integrate into the existing execution pipeline.

```text
Scenario
      │
      ▼
Stress Execution
      │
      ▼
Evidence Collection
      │
      ▼
Evidence Correlation
      │
      ▼
RCA Framework
      │
      ▼
Engineering Reasoning
      │
      ▼
Web UI
```

The objective is to reuse existing framework layers whenever possible.

---

# 3. Before Adding Anything

Ask the following questions:

## Is this a new scenario?

Examples

- ISSU
- Reboot
- Route Churn
- SNMP Validation

If YES

Modify:

✓ Scenario Framework

✓ Stress Execution

---

## Is this a new evidence source?

Examples

- Syslog
- SNMP
- Core Files
- Hardware Alarms

If YES

Modify:

✓ Evidence Collection

Possibly:

✓ Evidence Correlation

---

## Is this a new engineering interpretation?

Examples

- Memory Leak Detection
- ISSU Success Analysis
- BFD Stability Analysis

Modify:

✓ Engineering Reasoning

---

## Is this a visualization enhancement?

Examples

- New dashboard section
- New chart
- New table

Modify:

✓ Web UI

---

# 4. Extension Workflow

Every enhancement should follow the same lifecycle.

```text
Engineering Requirement

↓

Scenario

↓

Stress

↓

Evidence

↓

Correlation

↓

RCA

↓

Reasoning

↓

UI

↓

Validation

↓

Documentation
```

---

# 5. Adding a New Scenario

Typical examples:

- ISSU
- Reboot
- Interface Flap
- Route Churn

Required changes:

## Scenario Framework

- Register scenario
- Define target policy
- Configure timing

---

## Stress Execution

Implement runtime execution.

Examples

- Reboot DUT
- Restart daemon
- Bounce interface

---

## Validation

Verify stress completed.

---

No changes should be required in:

- RCA
- Engineering Reasoning
- UI

unless new evidence is introduced.

---

# 6. Adding a New Stress Mode

Typical examples

- ISSU

- Daemon Restart

- Hardware Reset

Implementation steps

1.

Implement stress operation.

2.

Register dispatcher.

3.

Generate standard stress report.

4.

Validate execution.

No downstream changes should be required.

---

# 7. Adding a New Evidence Collector

Examples

- SNMP

- Syslog

- Hardware Alarm

- Memory Usage

Implementation

```
Collector

↓

Normalization

↓

Artifact

↓

Correlation
```

Collector responsibilities

- Gather facts

- Normalize

- Produce artifact

Collectors should never perform reasoning.

---

# 8. Adding New Correlation Logic

Examples

- Alarm correlation

- Route correlation

- Memory correlation

Responsibilities

- Combine evidence

- Produce findings

Never

- Generate verdicts

---

# 9. Adding Engineering Reasoning

Examples

- ISSU reasoning

- Memory reasoning

- Hardware reasoning

Responsibilities

- Interpret findings

- Produce explanations

- Build confidence

- Generate verdict

---

# 10. Adding Dashboard Components

Examples

- New card

- New table

- New summary

Implementation

```
Engineering Output

↓

rca_ui_report.json

↓

Renderer

↓

HTML
```

The UI should consume normalized data only.

---

# 11. Typical Extension Examples

## Example 1

ISSU Validation

```
Scenario

✓

Stress

✓

Evidence

Reuse

Correlation

Reuse

Reasoning

Optional

UI

Reuse
```

---

## Example 2

SNMP Validation

```
Scenario

✓

Stress

No

Evidence

✓

Correlation

Optional

Reasoning

Optional

UI

Optional
```

---

## Example 3

Memory Leak Detection

```
Scenario

Optional

Stress

Reuse

Evidence

✓

Correlation

✓

Reasoning

✓

UI

✓
```

---

## Example 4

New Dashboard

```
Scenario

No

Stress

No

Evidence

No

Reasoning

No

UI

✓
```

---

# 12. Decision Matrix

| Requirement | Scenario | Stress | Evidence | Correlation | Reasoning | UI |
|--------------|----------|---------|-----------|-------------|------------|----|
| New Scenario | ✓ | ✓ | Reuse | Reuse | Reuse | Reuse |
| New Stress Mode | No | ✓ | Reuse | Reuse | Reuse | Reuse |
| New Collector | No | No | ✓ | Optional | Optional | Optional |
| New Correlation | No | No | Reuse | ✓ | Optional | Optional |
| New Reasoning | No | No | Reuse | Reuse | ✓ | Optional |
| New Dashboard | No | No | No | No | No | ✓ |

---

# 13. Common Mistakes

Avoid placing engineering logic inside:

- Stress Execution

- Collectors

- Dashboard

Avoid:

- Duplicate artifacts

- Duplicate evidence

- Multiple producers for one artifact

- Dashboard calculations

- Hardcoded engineering conclusions

---

# 14. Extension Checklist

Before merging:

✓ Scenario documented

✓ Stress validated

✓ Artifacts updated

✓ Reasoning verified

✓ Dashboard reviewed

✓ Regression executed

✓ EDS updated

---

# 15. Future Architecture

Long-term improvements include:

## Scenario Registry

Move scenario definitions to structured configuration.

---

## Stress Plugin Registry

Replace dispatcher logic with plugin registration.

---

## Collector Registry

Automatically discover evidence collectors.

---

## Reasoning Registry

Register engineering reasoning modules dynamically.

---

## Dashboard Registry

Dynamic dashboard composition.

---

# 16. Design Principles

## Principle 1

Reuse existing framework layers.

---

## Principle 2

Keep responsibilities isolated.

---

## Principle 3

Avoid duplicate implementations.

---

## Principle 4

Prefer extending artifacts over creating new ones.

---

## Principle 5

Every extension should preserve backward compatibility.

---

# 17. Summary

The Fabric Controller platform is intentionally modular.

Most new engineering capabilities require changes to only one or two framework layers while reusing the remainder of the execution pipeline.

Maintaining this separation of responsibilities ensures the platform remains scalable, maintainable, and easy to extend.

---

## Related Documents

- 04_Scenario_Framework.md
- 05_Stress_Execution_Framework.md
- 06_Evidence_Collection_Framework.md
- 07_Evidence_Correlation_Framework.md
- 08_RCA_Framework.md
- 09_Engineering_Reasoning_Framework.md
- 10_WebUI_Framework.md
- 11_Artifact_Catalog.md
- 12_Engineering_Glossary.md

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial framework extension guide |
