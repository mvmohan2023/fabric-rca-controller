# 04. Scenario Framework

**Architecture Version:** 2.0 Draft-1  
**Platform:** Fabric Validation Platform (FVP)  
**Status:** Living Architecture Specification

---

# 1. Purpose

The Scenario Framework defines how engineering validation scenarios are represented, selected, executed, validated, analyzed, and reported in the Fabric Validation Platform.

A scenario is not only a device action.

A complete FVP scenario includes:

- Engineering intent
- Target-selection policy
- Preconditions
- Stress or event execution
- Evidence collection
- Expected behavior
- Validation criteria
- Recovery expectations
- RCA integration
- Engineering reasoning
- Reporting metadata

The framework provides a consistent model for existing interface scenarios and future BGP, BFD, reboot, daemon-restart, telemetry, ISSU, platform-health, and RoCEv2 scenarios.

---

# 2. Current Scenario Implementation

The current platform already maintains scenario definitions in:

```text
controller/fault_injection_runner.py
```

The `SCENARIOS` catalog currently describes properties such as:

- Stress mode
- Target role
- Target count
- Target-selection policy
- Release tier
- Expected behavior
- Validation requirements

Scenario execution is coordinated through:

```text
fault_injection_runner.py
        ↓
stress_orchestrator.py
        ↓
run_rca_case.py
        ↓
rca_ui_report_builder.py
```

FVP v2 preserves this implementation and incrementally evolves it toward a centralized scenario registry and common scenario contract.

---

# 3. Scenario Definition

An FVP scenario is defined as:

> A controlled engineering event executed against one or more fabric entities, with explicit preconditions, expected outcomes, evidence requirements, validation rules, and reporting obligations.

A valid scenario must answer:

1. What event will be executed?
2. Why is the event valuable?
3. Which devices or interfaces are affected?
4. What behavior is expected?
5. What evidence must be collected?
6. How is success determined?
7. Is recovery expected?
8. What RCA should be generated?
9. How should the result be presented?

---

# 4. Scenario Lifecycle

Every scenario follows the same logical lifecycle:

```text
Scenario Selected
        ↓
Scenario Metadata Loaded
        ↓
Input Validation
        ↓
Target Resolution
        ↓
Precondition Validation
        ↓
Baseline Collection
        ↓
Event Execution
        ↓
Running / Degraded Evidence Collection
        ↓
Recovery or Restore
        ↓
Post-Event Evidence Collection
        ↓
Expected-versus-Observed Validation
        ↓
RCA and Engineering Reasoning
        ↓
Scenario Report
        ↓
Campaign / Release Aggregation
```

Not every scenario requires every phase.

For example:

- `interface_shutdown` intentionally leaves an interface disabled.
- `interface_restore` begins from an already degraded state.
- `normal_baseline_no_churn` executes no fault.
- `interface_hold_restore` includes a degraded sampling phase.
- ISSU scenarios may contain upgrade, switchover, reboot, and recovery phases.

The lifecycle therefore supports optional phases while preserving a common structure.

---

# 5. Scenario Contract

Every scenario should provide the following contract.

## 5.1 Identity

```text
scenario_name
scenario_id
display_name
family
description
version
```

## 5.2 Execution Metadata

```text
stress_mode
target_scope
target_roles
target_count
selection_policy
supports_parallel
supports_iterations
```

## 5.3 Preconditions

```text
topology_required
traffic_required
telemetry_required
clean_fabric_required
configuration_requirements
```

## 5.4 Expected Behavior

```text
expected_event
expected_control_plane_impact
expected_forwarding_impact
expected_traffic_impact
expected_recovery
expected_platform_health
```

## 5.5 Evidence Requirements

```text
baseline_evidence
running_evidence
degraded_evidence
recovery_evidence
post_event_evidence
```

## 5.6 Validation

```text
event_validation
impact_validation
recovery_validation
traffic_validation
telemetry_validation
platform_validation
```

## 5.7 Reporting

```text
engineering_category
executive_category
risk_level
release_blocking
required_artifacts
```

---

# 6. Scenario Metadata Model

A future centralized scenario definition may use a model similar to:

```yaml
scenario:
  id: IF-003
  name: single_interface_flap
  display_name: Single Interface Flap
  family: interface
  description: >
    Repeatedly disable and restore one physical fabric interface
    and validate control-plane, forwarding, traffic, telemetry,
    and recovery behavior.

execution:
  stress_mode: interface_flap
  target_scope: single_interface
  target_roles:
    - leaf
    - spine
  target_count: 1
  supports_parallel: false
  supports_iterations: true

preconditions:
  clean_fabric_required: true
  traffic_required: optional
  telemetry_required: true
  topology_required: true

expected_behavior:
  interface_down_observed: true
  interface_restore_observed: true
  traffic_impact: transient
  routing_recovery: automatic
  fabric_stable_after_event: true
  unexpected_core: false

validation:
  event_executed: required
  target_recovered: required
  fabric_recovered: required
  traffic_threshold: scenario_defined
  telemetry_available: required
  no_unexpected_core: required

reporting:
  engineering_category: link_resiliency
  executive_category: fabric_stability
  risk_level: medium
  release_blocking: true
```

This example is a target design. Existing scenario dictionaries remain supported during migration.

---

# 7. Scenario Families

Scenarios are grouped into engineering families.

## 7.1 Interface and ECMP Link Faults

Current:

- `single_interface_bounce`
- `single_interface_flap`
- `interface_shutdown`
- `interface_restore`
- `ecmp_member_degraded_hold_restore`
- Random and parallel interface-bounce scenarios

Purpose:

Validate fabric resilience to physical-link and ECMP-member events.

## 7.2 BGP, BFD, and Route Churn

Current:

- BGP clear scenarios

Planned:

- BGP neighbor flap
- BGP neighbor shutdown
- BGP neighbor restore
- BFD flap validation
- Route advertise/withdraw loop
- Large-scale route churn

## 7.3 Reboot and Process Restart

Planned:

- Leaf reboot
- Spine reboot
- Routing-engine restart
- RPD restart
- PFE daemon restart
- SNMP daemon restart
- Agent daemon restart

## 7.4 Telemetry and Observability

Planned:

- gNMI state validation
- gNMI counter validation
- Streaming interruption and recovery
- SNMP polling
- Alarm validation
- Telemetry during stress

## 7.5 ISSU and Rollback

Planned:

- Upgrade A to B
- Upgrade B to A
- Rolling upgrade
- Upgrade rollback
- Hitless validation
- BGP and traffic continuity validation

## 7.6 Platform Health

Planned:

- Core detection
- Memory growth
- Disk utilization
- CRC errors
- Optics alarms
- PFE installation failures
- Platform daemon stability

## 7.7 RoCEv2 and Traffic Impact

Current:

- RoCEv2 pre/post validation
- Deep inspection
- Congestion hotspot analysis
- Victim-flow correlation
- Traffic-intent RCA

Planned:

- Traffic impact during route churn
- Traffic impact during reboot
- Traffic impact during ISSU
- Long-duration RoCE validation

---

# 8. Target Resolution

Target resolution determines where the event is executed.

Current target-selection mechanisms include:

- Explicit node and interface
- Explicit target list
- Selected-node filtering
- Role-based filtering
- Random target selection
- One target per node
- Single automatically selected target
- Speed-based target filtering
- Scenario-specific target policies

Target resolution must produce a canonical artifact:

```text
resolved_targets.json
```

This artifact records:

- Requested target policy
- Resolved nodes
- Resolved interfaces
- Device roles
- Interface speeds
- Selection rationale
- Excluded candidates

The resolved-target artifact is authoritative for downstream stress execution and RCA.

---

# 9. Preconditions

A scenario may define mandatory preconditions.

Examples:

- Fabric topology is healthy.
- No links are already missing.
- All expected BGP sessions are established.
- Required traffic endpoints are available.
- Required telemetry profiles exist.
- Target interface exists.
- Target interface is currently enabled.
- Required software image is available.
- No unexpected core files exist before execution.

Preconditions are evaluated before event injection.

A scenario must not execute when a mandatory precondition fails unless the scenario explicitly validates a pre-existing degraded condition.

---

# 10. Baseline Phase

The baseline phase establishes the pre-event reference.

Baseline evidence may include:

- Device facts
- Topology
- Physical link state
- BGP state
- Interface counters
- Queue counters
- Congestion metrics
- ECMP distribution
- RoCEv2 counters
- IXIA traffic statistics
- Memory and CPU utilization
- Core-file inventory
- Alarm state

The baseline must be stored as immutable campaign evidence.

---

# 11. Event Execution

The event phase invokes the scenario-specific action.

Examples:

```text
interface_bounce
interface_flap
interface_shutdown
interface_restore
interface_hold_restore
bgp_clear
```

The Stress Orchestrator owns event execution.

A scenario-specific handler must return structured results containing at minimum:

```json
{
  "stress_mode": "interface_flap",
  "status": "pass",
  "details": "Interface flap completed.",
  "target": {
    "node": "leaf7",
    "interface": "et-6/0/0"
  },
  "steps": []
}
```

Additional scenario-specific fields may be added without removing existing fields.

---

# 12. Evidence Phases

FVP recognizes the following evidence phases:

## Baseline

Fabric state before event injection.

## Running

State while normal traffic or workload is active.

## Event

Immediate state around event execution.

## Degraded

State while the fault remains active.

## Recovery

State after restoration begins.

## Post-Event

Stabilized state after the event.

Each evidence artifact should include:

- Run ID
- Scenario
- Phase
- Timestamp
- Target
- Source
- Collection status
- Artifact path

---

# 13. Recovery Model

Scenarios fall into one of three recovery classes.

## Automatic Recovery

The scenario action restores the system automatically.

Examples:

- Interface bounce
- Interface flap
- Hold and restore

## Explicit Recovery

A separate scenario or operation performs restoration.

Examples:

- Interface shutdown followed by interface restore
- BGP neighbor shutdown followed by restore

## No Recovery Expected

The scenario intentionally ends in a degraded state for manual or extended validation.

Recovery class must be included in scenario metadata.

---

# 14. Scenario Validation

Every scenario must define validation at multiple levels.

## 14.1 Event Validation

Did the intended action occur?

Examples:

- Interface was disabled.
- BGP session was cleared.
- Daemon restarted.
- Software upgrade began.

## 14.2 Impact Validation

Did the expected impact occur?

Examples:

- ECMP member count changed.
- BGP adjacency transitioned.
- Traffic rerouted.
- Telemetry recorded the event.

## 14.3 Recovery Validation

Did the system recover?

Examples:

- Interface returned up.
- BGP sessions re-established.
- Traffic returned to threshold.
- Fabric health returned to baseline.

## 14.4 Negative Validation

Did anything unexpected occur?

Examples:

- Core file generated
- Additional links failed
- Unexpected BGP sessions reset
- Persistent packet loss
- Telemetry stopped
- Memory leak detected

## 14.5 Final Validation

The final result should distinguish:

```text
event_ok
impact_ok
recovery_ok
platform_ok
traffic_ok
telemetry_ok
```

The scenario's overall status is derived from its validation contract.

---

# 15. Scenario Result Model

Existing result fields remain valid.

FVP v2 may incrementally add a normalized result section:

```json
{
  "scenario": "single_interface_flap",
  "family": "interface",
  "status": "pass",
  "details": "Scenario completed successfully.",
  "target": {
    "node": "leaf7",
    "interface": "et-6/0/0"
  },
  "execution": {
    "start_time": "2026-07-10T10:00:00Z",
    "end_time": "2026-07-10T10:01:00Z",
    "duration_seconds": 60
  },
  "validation": {
    "event_ok": true,
    "impact_ok": true,
    "recovery_ok": true,
    "traffic_ok": true,
    "platform_ok": true
  },
  "artifacts": [],
  "metrics": {},
  "steps": []
}
```

This normalized section must be additive and backward compatible.

---

# 16. RCA Integration

Scenario metadata guides RCA behavior.

Examples:

- Interface scenarios emphasize link state, ECMP, routing, and traffic recovery.
- Route churn scenarios emphasize control-plane scale, convergence, memory, and cores.
- Reboot scenarios emphasize service restoration and traffic continuity.
- ISSU scenarios emphasize hitlessness, mixed-version behavior, and rollback.
- RoCE scenarios emphasize latency, retransmission, ECN, CNP, queue, and congestion behavior.

The RCA engine remains reusable, while scenario metadata identifies relevant evidence domains.

---

# 17. Engineering Reasoning

Every scenario should produce an engineering assessment answering:

- What event occurred?
- What behavior was expected?
- What behavior was observed?
- Was the impact within acceptable limits?
- Did the system recover?
- Were there unexpected side effects?
- What evidence supports the conclusion?
- What is the confidence level?

Example:

```text
The selected fabric interface was disabled and restored as expected.
Traffic redistributed across the remaining ECMP members.
No persistent packet loss, unexpected BGP reset, congestion hotspot,
or platform instability was observed. The fabric returned to its
pre-event health state within the configured recovery window.
```

---

# 18. Reporting Integration

Scenario results feed multiple reporting levels.

## Scenario Report

Detailed execution, evidence, RCA, and validation.

## Campaign Report

Aggregates multiple iterations or related scenarios.

## Suite Report

Aggregates a named group of scenarios.

## Release Report

Aggregates all scenarios executed for a software release.

Scenario metadata provides:

- Feature family
- Priority
- Risk level
- Release-blocking status
- Executive category
- Coverage classification

---

# 19. Scenario Status Model

Each scenario definition and execution uses standardized states.

## Definition Status

```text
Planned
Designed
Implemented
Smoke Validated
RCA Validated
Production Ready
Deprecated
```

## Execution Status

```text
Pending
Running
Pass
Fail
Blocked
Skipped
Error
```

These states support both engineering and executive reporting.

---

# 20. Scenario Maturity

A scenario becomes Production Ready only when:

1. Requirement is documented.
2. Scenario metadata is defined.
3. Target resolution is implemented.
4. Event execution is implemented.
5. Structured result is produced.
6. Smoke test passes.
7. End-to-end RCA test passes.
8. Validation criteria are verified.
9. UI/report output is verified.
10. Documentation is updated.
11. Code and documentation are committed.

---

# 21. Scenario Registry Evolution

Current scenario metadata exists primarily in the `SCENARIOS` dictionary.

FVP v2 will evolve this incrementally toward a centralized registry.

Potential future module:

```text
controller/scenario_registry.py
```

The registry may provide:

- Scenario lookup
- Family lookup
- Capability discovery
- Parameter validation
- CLI choice generation
- Suite membership
- Release-tier classification
- Documentation generation
- UI metadata

Migration must preserve existing scenario names and command-line behavior.

---

# 22. Extension Model

Adding a new scenario should eventually require:

1. Define scenario metadata.
2. Implement or reuse an action handler.
3. Define target-resolution requirements.
4. Define validation rules.
5. Register RCA evidence requirements.
6. Add documentation.
7. Add smoke and end-to-end tests.

The execution, artifact, RCA, reasoning, UI, and release-reporting frameworks should remain reusable.

---

# 23. Constraints

Scenario definitions must reflect the actual lab and topology.

Current exclusions include:

- EVPN/VXLAN scenarios
- VTEP, VNI, and IRB scenarios
- AE/LACP member scenarios where no AE configuration exists

Unsupported scenarios must not be listed as production-ready simply because they are theoretically valuable.

---

# 24. Backward Compatibility

The Scenario Framework must preserve:

- Existing scenario names
- Existing CLI arguments
- Existing target syntax
- Existing stress modes
- Existing JSON fields
- Existing report locations
- Existing suite and campaign behavior

New metadata and normalized result fields are additive.

---

# 25. Future Enhancements

Potential enhancements include:

- Scenario plugins
- YAML-based scenario definitions
- Auto-generated CLI
- Automatic documentation generation
- Scenario dependency graphs
- Precondition auto-remediation
- Dynamic target selection
- Distributed execution
- Scenario replay
- Historical comparison
- Risk-based scheduling
- AI-assisted scenario recommendation

These enhancements must evolve from the existing framework incrementally.

---

# 26. Summary

The Scenario Framework converts individual stress actions into consistent engineering validation scenarios.

It standardizes:

- Scenario identity
- Target resolution
- Preconditions
- Execution
- Evidence collection
- Recovery
- Validation
- RCA
- Reasoning
- Reporting
- Maturity

This contract allows the Fabric Validation Platform to expand from the current interface and ECMP scenarios into BGP, BFD, route churn, reboot, telemetry, platform-health, ISSU, and RoCEv2 families without duplicating the surrounding execution and analysis pipeline.

The framework preserves all existing workflows while establishing the architectural foundation required for a scalable scenario library and release-qualification platform.
