# Fabric Controller
# Engineering Design Specification (EDS)

# 16. Fault Injection Runner Architecture

**Version:** 1.0

---

# 1. Purpose

`controller/fault_injection_runner.py` is the master orchestration entry point for Fabric Controller scenario execution.

It coordinates the end-to-end lifecycle of a validation run:

```text
Scenario
  ↓
Target Resolution
  ↓
Stress Execution
  ↓
RCA Case Generation
  ↓
UI Report Generation
  ↓
Evidence Enrichment
  ↓
Validation
  ↓
Final Scenario Result


This file acts as the bridge between user intent, stress orchestration, RCA generation, engineering reasoning, and final validation output.

2. Why This File Exists

The runner exists to provide one deterministic execution path for scenario-based validation.

Instead of each scenario manually invoking telemetry, traffic, stress, RCA, and UI generation, this runner ensures every scenario follows the same lifecycle.

This provides:

Consistent artifact generation
Reproducible scenario execution
Shared RCA pipeline
Shared UI pipeline
Shared validation and classification
Clear extension model for future scenarios


3. Major Responsibility Blocks

fault_injection_runner.py currently owns several responsibility blocks.


Scenario Registry
Target Resolution
Stress Event Invocation
RCA Case Execution
UI Report Build
Phase-aware Telemetry Injection
CoS Hotspot Correlation
Congestion Origin Injection
ECMP Recovery View Injection
Validation and Classification
Suite Execution
CLI Entry Point


4. Function Ownership Map
Utility Helpers
Function	Responsibility
utc_now_iso()	Generate timestamp
ensure_dir()	Ensure directory exists
write_json()	Write JSON artifact
load_json()	Load JSON artifact
read_json()	Load JSON helper
run_subprocess()	Run external command
sanitize_name()	Normalize names
normalize_role()	Normalize topology role
Phase / Telemetry Helpers
Function	Responsibility
phase_samples_dir()	Build phase sample directory
phase_samples_path()	Build phase sample path
collect_queue_snapshot_for_phase()	Capture queue snapshot
collect_phase_window()	Collect phase telemetry window
_extract_interface_counter_summary()	Extract interface counters
Scenario and Target Resolution
Function	Responsibility
get_release_gate_scenarios()	Return release gate scenarios
get_scenarios_by_tier()	Filter scenarios by tier
extract_node_roles()	Extract node roles from topology
extract_link_endpoints()	Parse topology links
extract_fabric_interfaces()	Discover fabric interfaces
filter_targets_by_roles()	Apply role filters
pick_single_auto_target()	Auto-select one target
parse_explicit_targets()	Parse user-supplied targets
pick_random_targets()	Select random targets
load_device_facts_for_node()	Load device facts
extract_fabric_interfaces_from_device_facts()	Resolve live fabric interfaces
resolve_targets_for_scenario()	Main target resolution function
write_resolved_targets_artifacts()	Write resolved target artifacts
Stress Execution
Function	Responsibility
build_stress_run_id()	Build stress run identifier
run_stress_event()	Invoke stress orchestration

run_stress_event() bridges the runner and stress_orchestrator.py.

RCA Pipeline
Function	Responsibility
run_rca_case()	Execute RCA case generation
run_cos_hotspot_correlation()	Execute CoS hotspot correlation
build_ui_report()	Generate UI report
inject_ecmp_recovery_view_into_ui_report()	Inject ECMP recovery sidecar
inject_congestion_origin_analysis_into_ui_report()	Inject congestion origin analysis
Validation
Function	Responsibility
validate_stress_report()	Validate stress output
validate_rca_summary()	Validate RCA summary
validate_ui_report()	Validate UI report
build_evidence_rollup()	Build evidence summary
classify_scenario_result()	Classify final scenario result
maybe_replay_bug_candidate()	Replay suspected bug candidates
RoCE / Traffic Correlation Helpers
Function	Responsibility
_load_ixia_port_map()	Load IXIA port mapping
_load_resolved_targets_for_run()	Load target artifacts
_build_roce_victim_flows()	Build RoCE victim flow view
_load_roce_snapshot()	Load RoCE snapshot
_iter_roce_flow_rows()	Iterate RoCE rows
_flow_key_from_row()	Build flow key
_index_roce_snapshot_by_flow()	Index RoCE snapshot
_extract_pre_post_for_victim_flow()	Compare victim flow pre/post
_build_congestion_origin_analysis()	Build congestion origin relationship
Scenario and Suite Execution
Function	Responsibility
run_single_scenario()	Master single scenario pipeline
run_suite()	Execute scenario suite
parse_args()	CLI parsing
main()	CLI entry point
5. End-to-End Call Flow

The primary execution path is:

main()
  ↓
parse_args()
  ↓
run_single_scenario()
  ↓
resolve_targets_for_scenario()
  ↓
write_resolved_targets_artifacts()
  ↓
run_stress_event()
  ↓
run_rca_case()
  ↓
build_ui_report()
  ↓
inject_phase_delta_into_ui_report()
  ↓
run_cos_hotspot_correlation()
  ↓
build_ui_report()
  ↓
inject_congestion_origin_analysis_into_ui_report()
  ↓
inject_ecmp_recovery_view_into_ui_report()
  ↓
validate_stress_report()
  ↓
validate_rca_summary()
  ↓
validate_ui_report()
  ↓
build_evidence_rollup()
  ↓
classify_scenario_result()
  ↓
fault_injection_validation.json
6. Primary Orchestration Function
run_single_scenario()

run_single_scenario() is the central execution pipeline.

It owns the complete scenario lifecycle.

Major stages:

Load scenario definition.
Initialize progress logging.
Normalize phase timing.
Resolve targets.
Write target artifacts.
Build stress run ID.
Execute stress event.
Generate RCA case summary.
Build initial UI report.
Inject phase-aware telemetry.
Run CoS hotspot correlation.
Rebuild UI report.
Inject congestion origin analysis.
Inject ECMP recovery view.
Validate all generated artifacts.
Build evidence rollup.
Classify scenario result.
Generate topology view.
Write validation and runtime summaries.

This function is the current orchestration hub of the platform.

7. Artifact Ownership
Artifact	Produced By	Purpose
resolved_targets.json	write_resolved_targets_artifacts()	Target contract
stress_orchestrator_report.json	run_stress_event() / stress orchestrator	Stress execution result
rca_case_summary.json	run_rca_case()	Canonical RCA model
cos_hotspot_correlation.json	run_cos_hotspot_correlation()	Queue/CoS correlation
rca_ui_report.json	build_ui_report()	UI report model
fault_injection_validation.json	run_single_scenario()	Final validation result
runtime_summary.json	run_single_scenario()	Runtime metadata
8. Current Special-Case Logic

The runner currently contains scenario-specific handling for:

ecmp_member_degraded_hold_restore

Special behavior includes:

Filtering targets by degraded target speed.
Creating degraded_member_hold_event.json.
Preserving degraded hold metadata.
Passing degraded ECMP sampling controls.

This is acceptable for the current implementation but should be generalized in the future.

9. Extension Points

New scenarios may require changes in:

Scenario Registry

Add scenario metadata.

Target Resolution

Add target selection logic if existing policies are insufficient.

Stress Execution

Add new stress mode through run_stress_event() and stress_orchestrator.py.

Evidence Enrichment

Add collectors or correlation modules if new evidence is required.

Validation

Extend classify_scenario_result() if new pass/fail semantics are needed.

RCA/UI

Usually reusable unless new evidence domains are introduced.

10. Refactoring Candidates
Candidate 1: Split Orchestration

run_single_scenario() is large and coordinates many layers.

Future split:

ScenarioExecutor
TargetResolver
StressRunner
RcaPipelineRunner
ValidationRunner
ArtifactManager
Candidate 2: Scenario Registry

Current scenario definitions live in Python.

Future direction:

Scenario YAML / JSON Registry
Candidate 3: Stress Plugin Registry

Current stress modes are dispatched through code.

Future direction:

StressPluginRegistry
Candidate 4: Artifact Schema Validation

Current validation is logical.

Future direction:

JSON schema validation for major artifacts
11. Design Principles
Principle 1

The runner coordinates frameworks; it should not own domain-specific reasoning.

Principle 2

Scenario-specific behavior should be minimized.

Principle 3

Every major stage should produce inspectable artifacts.

Principle 4

Downstream RCA and UI should remain reusable across scenarios.

Principle 5

The runner should eventually become thinner as framework services mature.

12. Summary

fault_injection_runner.py is the current master orchestration module for Fabric Controller.

It connects scenario intent, stress execution, RCA generation, engineering reasoning, validation, and UI output into one repeatable execution pipeline.

As Fabric Controller grows, this file should gradually evolve from a monolithic runner into a thinner orchestrator that delegates to dedicated framework services.

Related Documents
03_Execution_Pipeline.md
04_Scenario_Framework.md
05_Stress_Execution_Framework.md
08_RCA_Framework.md
11_Artifact_Catalog.md
14_Architecture_Review.md
Revision History
Version	Date	Author	Summary
1.0	2026-06-29	Mohan Kumar M V	Initial fault injection runner architecture


