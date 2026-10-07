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

Engineering RCA Capability — RoCE sidecar/UI qualification integrated; remaining source/path/epoch qualification open

Next Task

Qualify saved-campaign engineering assessment and raw measurement provenance when server/artifacts return; counter epoch/window semantics remain unverified

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

## 2026-10-02 Lab Evidence — Normal Runner Integration PASS

User provided the final lab runner output for:

- RCA run: `rca_sidecar_baseline_20261002_202431`.
- Stress run: `evt_normal_baseline_no_churn_20261002T202431Z`.
- Scenario: `normal_baseline_no_churn`; one iteration, 112 resolved targets.
- Validation and final status: PASS; runner exit: 0.
- Sidecar exists: True; `[ENGINEERING-RCA] written` occurs after the final
  ECMP-only UI refresh. Normal automatic sidecar integration is qualified.
- Legacy case summary, UI and validation artifact paths were reported.
- UI server reachable: NO; browser/UI rendering qualification remains open.
- Baseline/running-decay/settle/post windows: 300/15/30/300 seconds.
- Runtime: 3,730.27 seconds (62.17 minutes); do not shorten measurement windows
  or launch another long campaign solely for source-path qualification.
- Legacy primary cause: queue-pressure-with-taildrop; 225 hotspots; CoS has
  14 needs_manual_review observations. PASS is not proof these observations
  are harmless. No injected churn occurred, so do not assert event causality.

Source-discovery inspection:

- Existing fabric collector produces `traffic/fabric_evidence.json`.
- Existing final report embeds traffic-intent analysis at `/intent_rca` in
  `rca_final_report.json`, rather than requiring traffic_intent_rca.json.
- Additive sidecar now checks those existing locations when no explicit source
  path is configured and the primary conventional path is absent.
- Explicit source paths retain priority, even when missing; failed embedded
  intent analysis is marked invalid, never accepted as healthy evidence.
- Embedded evidence records retain supporting artifact plus JSON pointer.
- Offline checks: 12/12 PASS, including source-byte preservation for producer
  locations, explicit-path priority and failed-intent rejection; compilation
  and diff checks PASS. No legacy producer/schema/UI changes were made.

Exact next action: regenerate `engineering_rca_report.json` for saved run
`rca_sidecar_baseline_20261002_202431`, then inspect source availability,
relevance counts, embedded intent status and phase-aware UI JSON/CoS review
entries. This does not start telemetry, traffic, a fault, or a new campaign.
Record results before advancing architecture milestones. Recovery-zero live
qualification and browser rendering remain unverified; existing saved evidence
should be checked before scheduling another campaign.

## 2026-10-02 Lab Evidence — Saved Baseline Source Discovery

User regenerated the saved baseline sidecar using `e35718e`.
Run: `rca_sidecar_baseline_20261002_202431`; status OBSERVATIONS.

- Evidence total 4,584; relevant 967; context 3,617.
- Reasons: 3,167 zero_without_phase_support; 966 nonzero_observation;
  450 descriptive_metadata; one phase_supported_recovery.
- Loaded: traffic/root_cause_correlation.json, rca_final_report.json at
  /intent_rca, and rca_ui_report.json.
- Fabric source missing: neither default campaign path nor producer fallback
  provided an existing file. Do not synthesize or recollect it merely to mark
  source completeness; retain missing-source traceability.
- Embedded-intent file resolution is real-artifact verified. Loading the object
  is not yet proof of emitted meaningful evidence: inspect normalized source
  counts and values before declaring adapter qualification complete.
- The single zero has been accepted by the phase-matching policy. Its metric,
  matching running delta, classification and measurement interpretation remain
  uninspected. No fault was injected; do not claim fault recovery from this.

Exact next action: print normalized counts/representative intent observations,
and the one phase_supported_recovery item with all matching delta_running rows
(same entity/source/artifact/metric). Assess whether the metric truly supports
return to baseline; this is a saved-evidence inspection, not a new campaign.
Then inspect the existing CoS needs_manual_review observations. Browser rendering
remains unverified because the live runner reported UI server unreachable.

## 2026-10-02 Lab Evidence — Baseline-Return Interpretation Verified

Saved baseline source counts supplied by user: root_cause_correlation 4,
rca_ui_evidence_index 4,580; traffic_intent_rca normalized observations 0.
Intent loading is verified; nonempty adapter normalization remains unqualified.
Inspect the intent summary/status/matched-hotspot shape before interpreting
zero output as a bug, lack of evidence, or a healthy path.

The sole phase_supported_recovery observation is:

- Entity: spine2|et-0/0/33|q3.
- Metric: peak-buffer-occupancy-percent.
- delta_running: +3.0; delta_post: 0; same source, artifact, entity and metric.
- Classification: queue-pressure; event_delta_classification: no_event_delta.
- Interpretation: return to the reported baseline difference. Not zero absolute
  occupancy, proven fault recovery, or proof of taildrop/ECN recovery. The
  defaultable cleared linger fields/zero series do not establish that claim.
- Real-artifact phase-matching policy is verified; raw measurement completeness
  and causal interpretation remain distinct from matching stored deltas.

Additive report diagnostics now expose normalized_evidence_count,
relevant_evidence_count and observation_status per source. A loaded empty source
is explicitly no_normalized_observations; status loaded is preserved.
Sidecar limitations explicitly distinguish zero post delta from zero absolute
value or fault recovery. Offline tests: 13/13 PASS, including loaded-empty-intent
semantics; diff check PASS. No existing CLI, legacy RCA or UI changes.

Exact next action: inspect rca_final_report.json's intent_rca status, summary
keys, signal keys and matched-hotspot count, plus the saved CoS summary and
needs-manual-review hotspot rows. Use saved artifacts; no new campaign needed.
Normal runner integration and source preservation are closed checkpoints;
full RCA milestone remains open for interpretation/coverage gaps and UI review.

## 2026-10-02 Lab Evidence — Intent and CoS Review Assessment

Evidence: user attachment `Pasted text(20261002-221307).txt` containing lab
inspection of saved baseline `rca_sidecar_baseline_20261002_202431`.
All 14 JSON hotspot rows were parsed and checked against classifier code.

Intent:
- status ok, error None, matched_hotspots 0, rca_summary null.
- Zero normalized intent evidence is consistent with the adapter contract:
  it normalizes a selected rca_summary, not invented path observations.
- Empty result does not distinguish healthy/no matching congestion from empty
  corridor or node/interface mismatch. Check src_leaf/dst_leaf/corridor before
  promoting the adapter to meaningful nonempty real-artifact qualification.

CoS:
- 15 interfaces collected, 0 failed, phase_aware; 14 needs-manual-review.
- 13 rows: spine2 q7, network_control, no_loss false, scheduler sc7,
  transmit/buffer allocation 1% each, ECN disabled. Historical tail counters
  range 4..11 packets; all carry historical_counter_only and score 1.
  These are cumulative row observations, not event-drop counts.
- One row: spine2|et-0/0/20:0|q2, rdma_storage, no_loss true, ECN enabled,
  scheduler sc2, transmit/buffer allocation 40% each. Occupancy signal 3%,
  tail/RED/queue-ECN counters 0; queued == transmitted == 22,622,152,421.
  pause-induced-congestion remains a suspicion: interface PFC activity
  128,618,451 is not a queue-priority-specific event delta or proof of RoCE
  service impact. Interface out-ECN=5 is not the queue ECN counter.
- All 14 rows have reported no_event_delta, baseline_or_historical_only,
  zero rise/linger/drop deltas; cleared linger labels are not independent
  evidence of recovery. Retain original manual-review classifications.
- Classifier implementation intentionally falls back to needs-manual-review
  when no specific policy branch applies; flags/scoring explain the output.

Qualification limit found in code: _extract_qmon_queue_counters initializes
missing metrics to zero, while delta-aware scoring uses zero defaults.
The pasted phase-derived zeros alone cannot establish raw measurement
completeness or no new loss. This is a coverage/interpretation gap, not yet a
proven device defect or justification to rewrite legacy output.

Exact next action: inspect raw PRE/RUNNING/POST record coverage for the reported
spine2 interfaces/queues (first q7 and q2 on et-0/0/20:0), plus final-report
src_leaf/dst_leaf/corridor. Determine whether phases contain actual tail/ECN
measurements and consistent entity names before claiming historical-only or
no-path-congestion closure. Use existing artifacts; no new campaign required.

## 2026-10-05 Server Outage — Offline Engineering Assessment Checkpoint

User explicitly directed continuation to the next pending implementation item
while lab server is down. This authorizes proceeding with the already-listed
RCA reasoning/missing-evidence work without closing the pending lab gates.
Architecture 06 (confidence/engineering reasoning/traceability) remains source
of truth; no scenario or architecture reprioritization is implied.

Implemented:
- New `controller/rca/assessment.py` deterministic engineering assessment.
- Additive `engineering_assessment` section in the separate sidecar only.
- Source gaps distinguish missing/invalid artifacts, loaded empty observations,
  and context-only evidence; coverage is not a scenario acceptance verdict.
- Per-candidate relevant facts link to normalized evidence indices and source
  artifacts, retaining original queue entity identities and phase/value data.
- Interpretation limits distinguish correlated observations, expectedness,
  event causality and evidence confidence.
- Baseline-return zeros explicitly do not prove zero absolute values or fault
  recovery. Signal/cumulative counters do not prove new event increments.
- Recommended checks cover raw metric/phase completeness, temporal alignment,
  independent-domain observations, latency baseline/SLO and RoCE evidence,
  and PFC direction/priority/queue-specific traffic impact.
- Conflict assessment is explicitly unassessed without aligned windows;
  differing values across phases are not asserted as contradictions.
- Existing candidate fields/confidence, CLI, legacy validation/RCA/reasoning,
  UI and source artifacts remain unchanged.

Validation: 17/17 offline tests PASS, Python compilation PASS, diff check PASS.
Report-level comparison against the previous committed reporter on a fixture
with a phase-supported baseline return and empty intent: all pre-existing
sidecar fields identical after excluding only engineering_assessment; PASS.
New tests cover missing/empty/context-only sources, traceable baseline return,
confidence/input immutability, context exclusion and phase-difference limits.
No live qualification is claimed. Full RCA milestone remains open.

Deferred lab checks remain pending (not failed or completed):
- Raw PRE/RUNNING/POST coverage on saved spine2 queue review observations.
- Intent endpoints/corridor and nonempty intent adapter evidence.
- Real fabric-evidence adapter qualification where artifact exists.
- Browser/UI qualification; prior run reported UI server unreachable.
- Saved-campaign qualification of the new engineering_assessment section.

Report-level offline integration and earlier-sidecar-field preservation checks
are complete. Exact next action: qualify engineering_assessment on the saved
baseline and negative campaigns once artifacts/server are available. Further
causal/conflict ranking requires measured aligned evidence;
retain explicit limitations rather than fabricate conclusions. When lab returns,
regenerate existing saved sidecars and inspect engineering_assessment before
resuming the recorded raw-phase/corridor checks; no new campaign is required.


## 2026-10-05 — aligned conflict assessment (offline checkpoint)

Continued the documented architecture 06 reasoning/conflict work during the
lab outage. Added `controller/rca/conflicts.py` and integrated its assessment
inside the additive engineering_assessment sidecar section. No legacy verdict,
candidate confidence, CLI, UI or source artifact is modified.

Comparisons require the same entity, metric, phase, measurement window, kind,
unit, population, counter epoch (where applicable), and tolerance. Only distinct
sources are compared. Disagreements retain evidence indices, source artifacts,
original values and comparison context. Matching values mean only agreement
within those comparable pairs, not complete coverage or a healthy verdict.
Missing provenance stays unassessed; differing phases are not conflicts.

Optional metadata contract: `comparison_context` must contain `measured: true`,
timezone-aware ISO `window_start` and `window_end` with start before end,
`measurement_kind` (gauge/counter/delta/rate), nonempty `unit` and `population`.
Counter/delta observations additionally require a nonempty `counter_epoch`.
Optional `absolute_tolerance` defaults to zero and must be finite/nonnegative.
Values must be finite numeric observations, excluding booleans. Explicitly
measured zeros may be compared; legacy default zeros do not gain provenance.
Fabric snapshot adapter preserves explicitly supplied comparison_context;
existing producers are not assumed to provide this contract. No alias, unit
conversion or queue aggregation is inferred.

Validation: 26/26 offline tests PASS; Python compilation and diff check PASS.
Nine new tests cover aligned disagreement, tolerance, incompatible scope,
invalid provenance, counter epochs, timezone equivalence, measured zeros,
same-source exclusion, immutability/confidence preservation and adapter pass-through.
No live qualification or scenario completion is claimed.

Exact next offline action: inspect producer raw measurement provenance and
identify where trustworthy validity, window, unit, population and counter epoch
can be carried additively; do not synthesize these from legacy aggregate/default
fields. Saved baseline/negative sidecar qualification and all recorded lab
raw-phase/corridor/UI checks remain deferred until the server is restored.


## 2026-10-05 — collector measurement provenance retention

Inspected telemetry normalizers, telemetry monitor, fabric evidence collector
and engineering evidence adapter. The monitor retains raw payloads, but the
normalizer previously discarded payload timestamps. The fabric collector then
retained only node/entity/metric/value/category, dropping source metric scope.
Neither path establishes verified units, counter reset epoch, measurement
window or population for the aligned comparison contract. Metric type labels
are classifier output, not independent proof of measurement semantics.

Implemented additive retention:
- Telemetry payload `timestamp` and `time`, when present, are retained verbatim
  as measurement_provenance with explicitly unverified timestamp semantics.
  No timestamp units, validity, clock alignment, interval or epoch is inferred.
- Fabric snapshot records retain supplied raw_value, node/path, labels/type,
  source_prefix/update_path and existing measurement_provenance.
- Explicit per-record phase and comparison_context survive collection and the
  engineering adapter. Missing phase/context remain missing; no contract is
  synthesized. Original record entity is retained in adapter metadata.
- Existing collected values, classifications, summaries and text output remain
  unchanged. No CLI options, candidate confidence or legacy verdict changed.

Validation: 30/30 offline tests PASS; touched modules compile; scoped diff
check PASS. Tests verify timestamp/legacy field preservation, end-to-end raw
scope/phase/context retention, input immutability and refusal to promote a
sample timestamp or incomplete context into a comparable measurement.
An unrelated existing local stress_orchestrator.py edit is excluded.

This completes the documented producer inspection and provenance retention
checkpoint, not the full RCA milestone. Exact next action: when saved artifacts
are available, inspect raw payload timestamp units/clock and phase metric
coverage, establish real counter-reset epochs/windows/populations and qualify
baseline/negative engineering sidecars. Independent-source conflict comparison
remains unassessed for legacy observations without that provenance. Existing
intent corridor/fabric adapter/UI lab gates remain pending. No lab scenario
is newly completed by these offline tests.


## 2026-10-05 — saved baseline delta semantics qualification and correction

Server restored; user regenerated saved baseline/negative engineering sidecars.
Negative source preservation PASS; evidence remains 11245/1839/9406
(total/relevant/context). Both campaigns have loaded intent with zero normalized
observations, missing fabric evidence, and no comparable aligned conflict pairs.
This is explicit insufficient comparison provenance, not evidence agreement.

User supplied raw spine2 et-0/0/33 queue3 peak-buffer-occupancy-percent:
initial PRE=0, RUNNING=3, POST=3; PRE samples=4,0,3; recovery samples=2,2
and phase POST=3. Traced congestion_delta_analyzer.compute_delta and UI evidence
index: delta_running=RUNNING-PRE; delta_post=POST-RUNNING. Therefore 3/0
running/post deltas do not establish return to PRE. Earlier tracker entries
claiming baseline return for this observation are superseded by this finding.
Peak metric reset/window semantics remain unverified; persistence alone does
not establish ongoing congestion or failed recovery.

Corrected engineering fact interpretation and report limitation text. Kept the
historical phase_supported_recovery relevance token for existing JSON and
confidence compatibility; it is a relevance label, not a recovery verdict.
Source values, legacy CLI/UI/RCA outputs and candidate confidence unchanged.
Validation: 31/31 tests PASS including regression through real delta producer
for PRE=0/RUNNING=3/POST=3 with immutable candidate serialization. Compilation
and scoped diff check PASS. No new campaign required for this correction.

Exact next action: pull correction and regenerate saved baseline sidecar,
printing only the zero-post fact interpretation. Then inspect intent endpoints/
corridor and raw source timestamps/counter epoch coverage; fabric adapter and
browser/UI qualification remain pending. Full RCA milestone remains open.


## 2026-10-05 — saved intent endpoint qualification and additive diagnostic

User inspected both baseline and negative final report intent_rca objects:
status=ok, error=None, src_leaf=None, dst_leaf=None, corridor=[], matched=[]
and no rca_summary. Saved src/dst inputs are 10.1.1.1/10.2.2.2. Both carry
intent_name=ecmp_degraded_member_hold_restore; the baseline name is a recorded
metadata mismatch pending producer/configuration review.

Current topology has 16 external links with IXIA peer names such as
ix020-ares.englab.juniper.net/1 and /5. resolve_ixia_endpoint uses exact endpoint
name lookup, not traffic IP resolution. User inventory samples show physical
port mappings only. No verified mapping of saved IPs to IXIA ports is available;
do not select ports by guess or reinterpret empty corridor as healthy.

Added engineering_assessment.intent_path_coverage: requested and resolved
endpoints, explicit missing/unresolved/incomplete corridor reasons, corridor
and matched-hotspot counts, source artifact and JSON pointer, interpretation
limits and mapping guidance. Existing source availability, legacy status=ok,
intent outputs, CLI/UI behavior and candidate confidence are preserved.
A resolved corridor with no hotspots is not a health verdict or proof of the
observed traffic path. Missing schema is explicitly unassessed.

Validation: 35/35 tests PASS, compilation/scoped diff check PASS. New tests
cover unresolved successful producer output, resolved empty hotspots, missing/
incomplete schemas, embedded final-report traceability and source preservation.

Exact next action: pull and regenerate baseline engineering sidecar; print only
engineering_assessment.intent_path_coverage. Verified traffic IP-to-port mapping
is required before IP corridor analysis can be qualified. Continue raw timestamp/
epoch and missing fabric artifact coverage inspection, then browser/UI checks.
This completes the additive intent diagnostic, not full RCA qualification.


## 2026-10-06 — additive UI engineering qualification

User confirmed existing fabric-rca-ui.service active/enabled on port8080.
Root and saved baseline API return HTTP200. Uploaded Fabric RCA UI.pdf
(19 pages) confirms baseline browser rendering. Technical qualification remains
open: noop baseline receives degraded-hold recovery narrative; ECMP reports
insufficient_data alongside convergence claim; historical/no_event_delta q7
receives cleared wording; interface-wide PFC appears as queue evidence; high
causality/delayed RoCE recovery exceed verified phase/path evidence.

Added separate Engineering Qualification section above existing dashboard,
loaded from read-only /api/rca/cases/{run_id}/engineering endpoint. Displays
sidecar intent/source gaps, aligned comparison status and pair count,
limitations and zero-post facts. Explicit caution covers noop recovery,
insufficient ECMP, PFC scope and cumulative traffic/error causal limits.
Existing report routes, JSON artifacts, verdicts, graphs and UI sections are
preserved. Missing/invalid sidecar shows unavailable coverage without blocking
legacy report loading. Run-switch guards prevent stale qualification display.

Validation: 37/37 Python tests PASS; JS syntax and Python compilation PASS;
scoped diff check PASS. Endpoint-body tests cover read-only loading, missing,
invalid and traversal cases. FastAPI is not installed in this workspace;
HTTP integration and browser qualification of the new section remain lab gates.
Existing local stress_orchestrator.py edit excluded.

Exact next action: pull, restart existing fabric-rca-ui.service, check saved
baseline /engineering API, hard-refresh UI and confirm Engineering Qualification
renders above dashboard. Do not rebuild/overwrite legacy UI artifacts.
Verified IP-to-port mapping, counter epochs/aligned windows, fabric adapter and
section-by-section technical review remain open; full RCA milestone not closed.


## 2026-10-06 — qualification browser PASS and legacy section checks

User service active and engineering API HTTP200 after restart readiness retry.
Uploaded Fabric RCA UI(1).pdf verifies new qualification section above preserved
dashboard, unresolved intent reasons, missing fabric, zero comparable pairs,
and corrected spine2 et-0/0/33 q3 zero-post interpretation. Browser rendering
of this additive section PASS; full technical RCA qualification remains open.

Continued documented section-by-section evidence review. Added read-only
ui_claim_qualification inside engineering_assessment, using existing loaded
rca_ui_report.json. Selected checks flag noop execution versus fault recovery,
ECMP insufficient/unknown/unsuccessful analysis versus convergence, and
non-event/historical queue context versus recovery. Findings retain original
field values and source artifact/JSON pointers; UI qualification displays these
findings. No findings means only no selected gap detected, not healthy or full
qualification. No legacy verdict/score/source or CLI result is rewritten.

Validation: 40/40 tests PASS, Python compilation and JS syntax PASS, scoped
diff check PASS. Tests cover all three saved-baseline gap shapes, traceability,
input immutability, non-acceptance semantics and malformed/missing sections.

Exact next action: pull and regenerate saved baseline engineering sidecar;
print ui_claim_qualification status and finding reasons. Hard-refresh browser
to confirm legacy section findings. Continue remaining traffic phase/path and
counter epoch coverage qualification; no new campaign needed for this check.


## 2026-10-07 — RoCE ranked comparison provenance correction

User saved baseline ui_claim_qualification returns review_required and all
three expected event/ECMP/queue reasons (saved artifact validation PASS).
RoCE victim Flow Group84 TX014/RX011/QP66 shows TX393642523/RX393995702:
RX exceeds TX by353179, so displayed Loss353179 is a discrepancy, not proven
lost packets. Saved top_by_delta ranks snapshot discrepancies, not increments.
User top_by_seqerror_increase row lacks all *_pre/*_post/*_increase fields.

Traced real inspector: compare_pre_post computes differences; top_n selects
positive increases but normalize_for_ui drops comparison arithmetic. Added
retention of explicitly present PRE/POST/increase fields for five compared
metrics, plus additive flow/metric presence coverage. Snapshot rows unchanged;
ranking, thresholds, legacy zero-default arithmetic, scores/verdicts unchanged.
Missing fields are marked absent, not measured zeros. Counter-reset epochs,
windows, validity and event causality remain unverified.

Validation:43/43 tests PASS; compilation and scoped diff check PASS. New tests
exercise ranking with retained increments, snapshot compatibility, missing
phase coverage and input preservation. Existing local orchestrator edit excluded.
Exact next action: pull and recompute comparison in memory from saved raw PRE/
POST paths; print only Flow84 QP66 comparison and coverage. Do not overwrite
legacy deep/UI artifacts. Then qualify actual increments and remaining scope/
clock/reset limitations before asserting delayed RoCE recovery.


## 2026-10-07 — RoCE duplicate/time/counter continuity diagnostics

User recomputed Flow84 TX014/RX011 QP66 comparison: frame discrepancy
394080->353179 (-40901), retx83->74638 (+74555), seqerror82->74248
(+74166), message_failed12->11 (-1), ECN193616->279109 (+85493).
All five metrics and flow present in both phases; retention lab check PASS.
Both session1/view RoCEv2 Flow Statistics. 84 matching rows each phase agree
on checked metric/timestamp signatures. PRE relative times00:00:00.455 to
00:18:10.524; POST00:00:00.484 to00:18:10.433. These are not verified wall-clock
windows; session identity does not establish counter continuity.

Added read-only comparison_coverage diagnostics: row multiplicity/distinct
checked-field sets, legacy last-row selection disclosure, original timestamps,
explicit unverified timestamp semantics, decreasing counter-like metrics and
unverified continuity. Repetitions are not independent evidence; agreement
covers checked fields only. Decreases are provenance flags, not proven resets
or recovery. Existing arithmetic, ranking, scores and verdicts preserved.

Validation:46/46 tests PASS; compilation/scoped diff check PASS. New cases
cover84 agreeing repeats, differing duplicates with unchanged last-row policy,
source timestamp retention, negative message failure difference and invalid/
nonfinite values. Existing local orchestrator edit excluded.
Exact next action: pull and repeat in-memory saved comparison, printing only
comparison_coverage duplicate/time/decrease/continuity diagnostics. Do not
rewrite saved raw/deep/UI artifacts. Interval increments and delayed recovery
remain unqualified until real counter semantics/reset epochs/windows are known.


## 2026-10-07 — RoCE sidecar and qualification UI integration

User saved-run duplicate/time/decrease diagnostics match expected84 agreeing
checked signatures each phase, original relative timestamps, message_failed
decrease and unverified continuity: lab checkpoint PASS. User explicitly asks
autonomous implementation without waiting for step-by-step confirmation.

Added read-only controller/rca/roce_qualification.py. Engineering assessment
roce_snapshot_qualification reads declared raw PRE/POST snapshots (or existing
standard fallback paths) and computes comparisons in memory. It retains source
availability/session/view fields, per-flow identity, source row indices,
snapshot differences, duplicate/timestamp/decrease/metric presence diagnostics
and explicit continuity/causality limits. Missing/invalid/empty artifacts remain
insufficient coverage; legacy evidence counts/confidence/verdicts unchanged.
No raw/deep/UI source artifacts are rebuilt or overwritten.

Engineering Qualification displays RoCE status, PRE/POST artifact links, flow
count and limits, with expandable first10 flow details. Backend retains all
flow comparisons. Snapshot differences are not interval increments; RX>TX
frame discrepancy is not proven loss; delayed recovery remains unqualified.

Validation:49/49 tests PASS; compilation and JS syntax PASS; scoped diff check
PASS. Integration test writes real sidecar from84-row baseline-shaped raw
snapshots, verifies source indices, seqerror+74166, message_failed decrease and
source byte preservation. Tests also cover missing/invalid/empty snapshots.
Existing local stress_orchestrator.py change excluded.

Exact next action: regenerate saved baseline sidecar with latest branch and
hard-refresh UI (no service restart needed). Source fixture integration is
complete; lab/browser validation of the new RoCE details remains pending.
Continue autonomously on architecture-aligned items; verified traffic IP/port
mapping, reset epochs/aligned windows, fabric evidence source qualification and
remaining section technical review are still gates. Full project not claimed
complete merely because qualification diagnostics are implemented.
