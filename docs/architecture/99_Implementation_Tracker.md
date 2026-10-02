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

🟨 Executive Release (existing provisional evaluator)

⬜ Engineering AI

Scenario Families
=================

✅ Interface

✅ ECMP

✅ BGP

🟨 Routing (controlled-prefix actions implemented)

🟨 Software (process restart + reboot primitive implemented)

🟨 Telemetry (code complete; qualification varies)

🟨 Platform (PRE/POST health monitoring implemented)

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

Engineering RCA Capability — real-campaign qualification of relevance and additive sidecar

Next Task

Run a new normal_baseline_no_churn campaign through fault_injection_runner; verify automatic sidecar creation and legacy validation/UI behavior

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
- Queue/CoS RCA UI evidence adapter implemented using existing evidence_index without changing legacy RCA/UI output
- Real queue evidence inspection: 11,241 normalized items across 747 entities; 9,388 zero/default values and 1,853 nonzero values
- Exact entity matching exposed node-identity and entity-granularity differences between traffic and queue evidence
- Inventory-backed canonical node identity and interface-to-queue hierarchical correlation implemented additively
- Real hierarchical qualification PASS on release_neg_007_leaf7_ecmp_degraded_100g
- Qualified entity: san-q5130-01|et-0/0/0
- Correlated child queues: leaf6|et-0/0/0|q2 and leaf6|et-0/0/0|q3
- Qualified domains: queue + traffic; sources: rca_ui_evidence_index + root_cause_correlation
- Result: cross_domain_observation with Medium evidence confidence
- Original EvidenceItem entity values remain unchanged for source traceability
- Zero values are not blindly discarded because zero can represent valid recovery evidence; evidence relevance remains the next refinement
- This historical next step is closed by the 2026-10-02 offline checkpoint below; real-campaign qualification is next.

---

# 9. Resume Point

When resuming project:

Read this tracker.

Read current sprint.

Continue from Current Task.

Do not change priorities.

## 2026-10-02 Canonical Checkpoint

Source branch: `feature/snmp-poll-validation`; starting commit: `40c6001`.
The commit containing this section records the code and documentation checkpoint.
No milestone priority changed. Current sprint remains Engineering RCA.

Completed in this checkpoint:

- Reconciled catalog, status, actual runner definitions and registered actions.
  See `97_Scenario_Status.md` for implementation vs qualification distinctions.
- Implemented non-destructive relevance in `controller/rca/relevance.py`.
- Context/default zeros and descriptive confidence/recovery-ratio metadata do not
  influence confidence diversity, completeness bonuses, or candidate category.
- Zero post deltas can support return to baseline only with matching nonzero
  running deltas on the same source/artifact/entity/metric.
- Defaultable/padded phase-aware series cannot independently prove recovery.
- All normalized observations remain in the new artifact, with ordered relevance
  decisions. Context-only entities do not generate candidates.
- Added `controller/rca/report.py`, producing only
  `engineering_rca_report.json` alongside existing campaign artifacts.
- Single-scenario runner invokes sidecar after final UI refresh. Sidecar failures
  are reported separately without changing existing validation or exit status.
- Missing/invalid sources are explicit; correlations are not causal diagnoses.
- Existing CLI arguments, schemas, RCA reasoning and UI sections remain intact.

Offline evidence:

- `python -m unittest discover -s tests -v`: 9/9 PASS.
- Includes 1,000-default-zero invariance, matching recovery evidence, invalid
  values, padded series, canonical queue hierarchy and source immutability.
- Sidecar integration test verifies existing input files remain byte-identical.
- `python -m controller.rca.report --help`: PASS.
- Python compilation of changed controller modules: PASS.
- `git diff --check`: PASS.
- Full runner help smoke was blocked by missing runtime dependency `requests`;
  no full runner or live device qualification is claimed in this workspace.
- Historical campaign artifacts are absent from this checkout.

Exact next action (lab repo root, after applying this checkpoint):

```bash
python -m controller.rca.report \
  --case-summary artifacts/campaigns/release_neg_007_leaf7_ecmp_degraded_100g/rca_case_summary.json \
  --inventory controller/inventory.json
```

Inspect `engineering_rca_report.json` for canonical entity
`san-q5130-01|et-0/0/0`, queue children q2/q3, relevant domain/source counts,
context counts, confidence label and every recovery-relevance decision.
Compare the legacy summary, UI, traffic and queue artifact hashes before/after.
Record the real counts and verdict here; do not reuse the earlier 11,241/9,388
counts as new qualification evidence. Then validate one normal runner campaign
produces the sidecar automatically without changing its legacy verdict/output.

Remaining current RCA work:

1. Real-campaign relevance/sidecar qualification and normal-runner regression.
2. Qualify fabric-evidence and traffic-intent adapters when those real artifacts
   are available (previous tracker already identified this gap).
3. Continue architecture 06 reasoning/conflict/missing-evidence improvements only
   after qualification; correlation alone does not close the full RCA milestone.

Other implementation/qualification gaps remain recorded in scenario status.
Do not reprioritize ISSU, scale, history, or unrelated refactoring ahead of the
canonical RCA action. A same-day full-project completion claim requires their
actual scope and lab evidence; this checkpoint does not imply that claim.

## 2026-10-02 Lab Evidence — RCA Relevance Checkpoint

User executed commit `8fa39e7` on `san-hp-srv05` under `/root/fabric-controller`.
Campaign: `release_neg_007_leaf7_ecmp_degraded_100g`.
The generated sidecar and printed output establish real-artifact execution;
this is not an independent live fault run or a full RCA milestone closure.

- Status: `OBSERVATIONS`.
- Total normalized evidence: 11,245; relevant: 1,839; context: 9,406.
- Reasons: 7,912 zero_without_phase_support; 1,839 nonzero_observation;
  1,494 descriptive_metadata. No phase_supported_recovery occurred in this run.
- Loaded sources: `traffic/root_cause_correlation.json`, `rca_ui_report.json`.
- Missing: `traffic_intent_rca.json`, `fabric_evidence.json` at resolved paths.
  Their absence is an input-availability gap, not a healthy device observation.
- Target `san-q5130-01|et-0/0/0`: exactly one cross_domain_observation.
- Three relevant observations among 34 retained observations; 31 context items.
- Domains queue + traffic; two sources and two artifacts; all relevant evidence
  traceable and classified. Evidence confidence: 0.70, Medium.
- Child entities: `leaf6|et-0/0/0|q2`, `leaf6|et-0/0/0|q3`.
  Child listing includes context; the output does not yet prove both queues
  independently contributed relevant evidence.

Result: real-artifact correlation and relevance counts verified. Confidence is
confidence in evidence correlation, not 70% confidence in a proven root cause.

Exact next action:

1. Print the target candidate's relevant metric/value/phase/source/artifact rows
   using assess_relevance on its retained supporting evidence.
2. Hash case summary and all loaded source files before and after regeneration;
   confirm byte preservation. Offline source-preservation tests already pass,
   but lab source hashes have not yet been provided.
3. Complete a normal-runner regression that automatically produces the sidecar
   while preserving legacy validation/verdict and phase-aware UI behavior.
4. Record the above results here before progressing to the next milestone.

Recovery-zero behavior remains offline-qualified only because this real
campaign contained no phase-supported recovery zeros. Fabric-evidence and
traffic-intent adapter real-artifact qualification remains pending.

## 2026-10-02 Lab Evidence — Source Preservation and Relevant Metrics

User-provided lab output verifies the three target observations:

| Entity | Metric | Value | Phase | Existing classification |
|---|---|---:|---|---|
| san-q5130-01\|et-0/0/0 | max_latency_ns | 1,434,220 ns | unspecified | receiver_hotspot |
| leaf6\|et-0/0/0\|q2 | ecn_marked_pkts | 5,036 | signals | queue-pressure-with-ecn |
| leaf6\|et-0/0/0\|q3 | ecn_marked_pkts | 284 | signals | queue-pressure-with-ecn |

Both queues contribute relevant evidence. Latency equals 1.43422 ms. These are
retained source observations, not measured event deltas or a causal chain.
No latency baseline/SLO, ECN denominator, temporal alignment, CNP response or
packet-loss result was supplied by this inspection; do not infer defect,
recovery, or RoCE impact from the three values alone.

The lab check hashed the case summary and every loaded source before and after
sidecar regeneration and reported `SOURCE PRESERVATION: PASS`.

Closed: real-campaign relevance inspection, canonical queue/traffic correlation,
and lab byte-preservation check for loaded sources.
Pending: automatic sidecar generation through the normal runner; legacy
validation/verdict and phase-aware UI regression; missing adapter artifacts;
real recovery-zero qualification (this campaign had no such observations).

Exact next action: execute a new `normal_baseline_no_churn` single-scenario run
with a unique run ID and the existing campaign's src/dst/intent/nodes/profile.
Use normal phase windows and inspect the sidecar plus legacy validation/UI.
No new fault is required to check the integration point. Do not overwrite the
qualified historical campaign or promote another milestone before recording
the regression evidence.
