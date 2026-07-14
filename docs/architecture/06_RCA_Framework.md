# 06. Root Cause Analysis (RCA) Framework

**Architecture Version:** 2.0 Draft-1

**Platform:** Fabric Validation Platform (FVP)

**Status:** Living Architecture Specification

---

# 1. Purpose

The Root Cause Analysis (RCA) Framework transforms raw execution evidence into engineering conclusions.

Unlike traditional validation systems that simply indicate PASS or FAIL, the RCA Framework explains:

- What happened?
- Why did it happen?
- Was it expected?
- What evidence supports the conclusion?
- What is the confidence level?
- What should an engineer investigate next?

The RCA Framework is a reusable analysis layer shared across all scenario families.

---

# 2. RCA Philosophy

Execution determines **what was executed**.

Validation determines **whether expectations were met**.

RCA determines **why the observed behavior occurred**.

Engineering reasoning then explains those findings in language suitable for engineers and technical leads.

---

# 3. RCA Pipeline

```
Scenario Execution
        │
        ▼
Evidence Collection
        │
        ▼
Evidence Normalization
        │
        ▼
Feature-Specific Analysis
        │
        ▼
Cross-Domain Correlation
        │
        ▼
Root Cause Candidates
        │
        ▼
Confidence Assessment
        │
        ▼
Engineering Reasoning
        │
        ▼
Executive Summary
```

---

# 4. Engineering Evidence

The RCA engine consumes evidence from multiple domains.

Current evidence sources include:

## Fabric

- Physical topology
- Interface state
- Link health
- Device inventory

## Routing

- BGP state
- Route convergence
- ECMP distribution

## Telemetry

- gNMI
- Queue statistics
- Interface counters
- System counters

## Traffic

- IXIA
- RoCEv2
- Packet loss
- Throughput

## Platform

- CPU
- Memory
- Core files
- Alarms

## Validation

- Scenario results
- Event status
- Recovery status

Every evidence source remains immutable.

---

# 5. RCA Stages

## Stage 1 — Evidence Collection

Collect all available engineering artifacts.

Examples:

- Device facts
- Validation reports
- Queue statistics
- ECMP metrics
- Congestion reports
- Traffic statistics

---

## Stage 2 — Evidence Normalization

Different collectors produce different formats.

Normalization converts them into a common engineering model.

Examples

```
Queue utilization

↓

Queue object
```

```
BGP adjacency

↓

Routing object
```

```
Interface state

↓

Fabric object
```

---

## Stage 3 — Feature Analysis

Each engineering domain performs specialized analysis.

Current analysis modules include:

- Congestion Analysis
- ECMP Analysis
- RoCEv2 Analysis
- Traffic Analysis
- Fabric Analysis
- Delta Analysis

Future modules include:

- Memory Analysis
- Process Health
- ISSU Analysis
- Sensor Analysis

---

# 6. Cross-Domain Correlation

The RCA engine correlates observations across domains.

Example

```
Interface Down

↓

Traffic Loss

↓

ECMP Redistribution

↓

Queue Pressure

↓

RoCE Latency

↓

Congestion Hotspot
```

Rather than reporting independent observations, FVP produces one engineering explanation.

---

# 7. Root Cause Generation

The RCA engine generates one or more hypotheses.

Example

```
Candidate 1

Interface Failure

Confidence 96%

Evidence

- Interface DOWN
- Traffic reroute
- ECMP rebalance

---------------------

Candidate 2

Congestion

Confidence 55%

Evidence

- Queue utilization

---------------------

Candidate 3

Traffic Burst

Confidence 22%
```

The highest-confidence candidate becomes the primary RCA.

---

# 8. Current RCA Modules

The current platform includes:

### Congestion Origin Analysis

Identifies congestion hotspots.

---

### ECMP Recovery Analysis

Validates ECMP redistribution and recovery.

---

### ECMP Hierarchy Analysis

Determines affected ECMP members.

---

### Telemetry Delta Analysis

Compares baseline and post-event telemetry.

---

### Root Cause Correlation

Combines observations across domains.

---

### Engineering Reasoning

Produces engineer-readable conclusions.

---

### RoCEv2 Deep Inspection

Analyzes:

- ECN
- CNP
- Retransmissions
- Latency
- Victim flows
- Congestion hotspots

---

# 9. Evidence Correlation

Current evidence correlation includes:

- Interface ↔ Traffic
- Interface ↔ ECMP
- ECMP ↔ Queue
- Queue ↔ Congestion
- Congestion ↔ RoCE
- Traffic ↔ Intent
- Platform ↔ Validation

Future correlation may include:

- Memory ↔ Process Restart
- ISSU ↔ Traffic
- Temperature ↔ Performance

---

# 10. Confidence Assessment

Every RCA should include confidence.

Example

| Confidence | Interpretation |
|------------|----------------|
| 95–100% | Very High |
| 80–94% | High |
| 60–79% | Medium |
| 40–59% | Low |
| Below 40% | Insufficient Evidence |

Confidence is influenced by:

- Number of evidence sources
- Evidence consistency
- Correlation strength
- Missing telemetry
- Conflicting observations

---

# 11. Engineering Reasoning

Engineering reasoning transforms technical evidence into engineering conclusions.

Example

Instead of

```
Queue 5 utilization exceeded threshold.
```

Produce

```
The congestion hotspot was triggered after interface failure
forced traffic redistribution across the remaining ECMP members.
Queue pressure increased on the surviving links, resulting in
higher RoCE latency. The fabric recovered automatically after
the interface was restored.
```

This becomes the engineering narrative.

---

# 12. RCA Artifact Model

Current artifacts include:

- RCA Summary
- Congestion Analysis
- ECMP Analysis
- Telemetry Diff
- Engineering Reasoning
- UI JSON

Future artifacts include:

- AI Explanation
- Similar Historical Cases
- Recommended Debug Commands

---

# 13. Engineering Categories

RCA findings are grouped into categories.

Examples

- Link Failure
- Routing Instability
- Congestion
- Queue Pressure
- Traffic Loss
- Telemetry Failure
- Platform Failure
- Configuration Error

These categories support executive reporting.

---

# 14. Relationship to Validation

Validation asks:

> Did the system behave as expected?

RCA asks:

> Why did the observed behavior occur?

Validation may PASS while RCA still identifies engineering observations worth investigating.

---

# 15. Relationship to Executive Reporting

Executive reports consume RCA outputs.

Examples

- Primary Root Cause
- Confidence
- Risk
- Affected Features
- Recommended Action

The Executive Report should not repeat raw telemetry.

It summarizes engineering conclusions.

---

# 16. Future AI Enhancements

Planned capabilities include:

- Similar historical failures
- Knowledge-base search
- Recommended debug commands
- Automated hypothesis ranking
- Predictive failure detection
- AI-assisted engineering summaries

These enhancements extend the existing RCA pipeline rather than replacing it.

---

# 17. RCA Design Principles

The RCA framework follows these principles.

### Evidence First

No conclusion without supporting artifacts.

### Explainability

Every conclusion must be understandable.

### Modularity

New analyzers integrate through reusable interfaces.

### Traceability

Every engineering statement links back to evidence.

### Backward Compatibility

Existing RCA outputs remain valid while new fields are added incrementally.

---

# 18. Future RCA Plugin Architecture

Future analyzers may be implemented as plugins.

Examples:

- BGP Analyzer
- Memory Analyzer
- ISSU Analyzer
- Sensor Analyzer
- Power Analyzer
- AI Recommendation Analyzer

Plugins should register with a common RCA interface.

---

# 19. Long-Term Vision

The long-term vision is an RCA engine capable of combining:

- Current execution evidence
- Historical executions
- Release history
- Topology knowledge
- Validation results
- Engineering rules
- AI-assisted reasoning

to answer:

- What happened?
- Why?
- How confident are we?
- Has this happened before?
- What should I check next?
- Should this release ship?

---

# 20. Summary

The Root Cause Analysis Framework is the engineering intelligence layer of the Fabric Validation Platform.

It transforms evidence into understanding by combining telemetry, topology, traffic, platform health, validation results, and engineering rules into coherent, explainable conclusions.

This architecture enables FVP to evolve from an automation framework into a release qualification platform that not only validates network behavior but also explains it with confidence and traceable engineering evidence.
