# Fabric Validation Platform (FVP)
# Master Implementation Tracker

Version: 1.0
Owner: Mohan Kumar
Project: Fabric Validation Platform (FVP)
Status: Active

---

# 1. Project Goal

Build a production-grade Fabric Validation Platform capable of:

- Executing fault scenarios
- Collecting telemetry
- Validating expected behaviour
- Performing Engineering RCA
- Producing Executive Release Qualification
- Supporting Engineering AI reasoning

Target Completion: 10 Days

---

# 2. Source of Truth

Architecture

docs/architecture/
00_Project_Vision.md
01_System_Architecture.md
02_Component_Architecture.md
03_Execution_Flow.md
04_Scenario_Framework.md
05_Validation_Framework.md
06_RCA_Framework.md
07_Executive_Release_Validation.md
08_Engineering_AI.md

Scenario Catalog

docs/fabric_rca/
15_Test_Scenario_Catalog.md

This tracker is the only implementation dashboard.

---

# 3. Overall Progress

Foundation
===========

✅ Core Framework

✅ Scenario Framework

✅ Target Framework

✅ Stress Framework

Engineering Capability
======================

🟨 Validation Framework

🟨 RCA Framework

⬜ Executive Release

⬜ Engineering AI

Scenario Families
=================

✅ Interface

✅ ECMP

✅ BGP

⬜ Routing

⬜ Software

⬜ Telemetry

⬜ Platform

⬜ Scale

⬜ Stability

---

# 4. Current Sprint

Milestone

Validation Framework

Goal

Create common engineering validation capability.

Files

controller/validators/

Deliverables

✔ Event Validation

✔ Impact Validation

✔ Recovery Validation

✔ Platform Validation

✔ Telemetry Validation

✔ Traffic Validation

---

# 5. Current Position

Completed

Core Framework

Scenario Framework

Target Framework

Stress Framework

Interface Family

ECMP Family

BGP Family

Current Task

Engineering RCA Capability — cross-domain evidence adapters

Next Task

Normalize queue/CoS evidence into the reusable RCA model and validate same-entity correlation

---

# 6. Completed Milestones

Milestone 1

Core Framework

Status

COMPLETE

Milestone 2

Scenario Framework

Status

COMPLETE

Milestone 3

Target Framework

Status

COMPLETE

Milestone 4

Stress Framework

Status

COMPLETE

Milestone 5

Interface Family

Status

COMPLETE

Milestone 6

ECMP Family

Status

COMPLETE

Milestone 7

BGP Family

Status

COMPLETE

---

# 7. Completed Commits

26164b7
Improve resolved target reporting

3ec07e3
Integrate BGP neighbor scenarios

10f17a0
Peer-specific BGP actions

---

# 8. Project Rules

Never break backward compatibility.

Never change existing CLI.

Never change existing JSON.

Never overwrite RCA.

Only additive changes.

Always update tracker before next milestone.

---

# 8.1 Current Validation Evidence

SNMP Poll

- Single-node live qualification PASS on leaf2 (10.83.6.4)
- SNMP telemetry: 1/1 node, 3/3 required scalar objects
- Platform PRE/POST validation: PASS
- Overall Engineering Validation: PASS
- Run ID: snmp_poll_leaf2_20260928_202919
- Juniper jnxOperatingTable collector live-qualified on leaf2
- 6/6 Juniper metric walks passed: temperature, CPU, installed memory, CPU 1/5/15-minute averages
- Full integration regression PASS: snmp_jnx_leaf2_20260928_214226
- Integrated artifact: scalar 3/3, Juniper operating-health 6/6
- Collection success is distinct from device-health threshold verdict
- Juniper collection-completeness validation policy implemented
- Positive offline validation: scalar 3/3 + Juniper 6/6 => telemetry PASS
- Negative offline validation: simulated cpu_5min_pct walk failure => telemetry FAIL (5/6)
- CPU/temperature value thresholds remain separate from collection validation
- SNMP telemetry milestone closed for framework progression
- Broader multi-node SNMP qualification remains pending as a lab/device qualification item
- CPU/temperature threshold rules remain a separate future rule-registry/dynamic-threshold item

Engineering RCA

- Current architecture source: docs/architecture/06_RCA_Framework.md
- Reusable additive EvidenceItem and RootCauseCandidate models implemented under controller/rca/
- Existing root_cause_correlation artifact normalized successfully: 4 evidence items, 1 entity, 4 traffic metrics
- Real artifact qualification: release_neg_007_leaf7_ecmp_degraded_100g
- Entity correlation implemented without changing legacy RCA, engineering reasoning, or RCA UI schemas
- Correlation qualification PASS: san-q5130-01|et-0/0/0 produced one domain_observation candidate
- Confidence assessment correctly remained Low for one-domain/one-source evidence; metric count alone does not inflate confidence
- fabric_evidence and traffic_intent_rca adapters are implemented but historical qualification artifacts were not present on the lab server
- Preserve existing RCA artifacts and UI outputs; do not overwrite existing RCA
- Next implementation step: normalize existing queue/CoS evidence and prove same-entity cross-domain correlation

---

# 9. Resume Point

When resuming project:

Read this tracker.

Read current sprint.

Continue from Current Task.

Do not change priorities.
