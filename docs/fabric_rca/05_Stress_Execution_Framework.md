# Fabric Controller
# Engineering Design Specification (EDS)

# 05. Stress Execution Framework

**Version:** 1.0

---

# 1. Purpose

The Stress Execution Framework is responsible for executing engineering validation events against the fabric.

It provides a common execution engine capable of performing disruptive and non-disruptive operations while remaining independent of telemetry collection, RCA generation, engineering reasoning, and dashboard visualization.

The framework is designed so that new stress operations can be added without changing downstream RCA components.

---

# 2. Responsibilities

The Stress Execution Framework is responsible for:

- Executing runtime stress events
- Dispatching stress operations
- Supporting parallel execution
- Managing execution timing
- Recording execution results
- Producing execution artifacts
- Reporting execution progress

The framework is **not** responsible for:

- Telemetry collection
- Root cause analysis
- Engineering reasoning
- Dashboard rendering
- Pass/fail determination

---

# 3. Position within the Platform

```text
Scenario Framework
        │
        ▼
Stress Execution Framework
        │
        ▼
Evidence Collection
        │
        ▼
Evidence Correlation
        │
        ▼
RCA Framework
```

Stress execution is intentionally isolated from downstream engineering analysis.

---

# 4. Major Components

Primary implementation files include:

```
controller/fault_injection_runner.py

controller/stress_orchestrator.py

controller/progress_logger.py
```

Supporting modules include:

```
device_client.py

telemetry_monitor.py

traffic_verifier.py

fabric_evidence_collector.py
```

---

# 5. Execution Lifecycle

Every scenario follows the same stress execution lifecycle.

```text
Scenario
    │
    ▼
Resolve Targets
    │
    ▼
Prepare Runtime
    │
    ▼
Execute Stress
    │
    ▼
Wait / Hold
    │
    ▼
Restore
    │
    ▼
Verify Recovery
    │
    ▼
Generate Stress Report
```

---

# 6. Execution Flow

The execution entry point is:

```
run_single_scenario()
```

Typical flow:

```text
run_single_scenario()

        │

        ▼

resolve_targets_for_scenario()

        │

        ▼

run_stress_event()

        │

        ▼

stress_orchestrator

        │

        ▼

stress_orchestrator_report.json
```

---

# 7. Stress Dispatcher

The framework dispatches execution based on the configured stress mode.

Conceptually:

```text
Stress Mode

        │

        ▼

run_stress_action()

        │

        ▼

run_single_stress_target()

        │

        ▼

Specific Stress Implementation
```

Examples include:

- Interface Hold / Restore
- Interface Bounce
- BGP Clear
- Future ISSU
- Future Reboot
- Future Route Churn

---

# 8. Parallel Execution

The framework supports multiple execution targets.

Execution model:

```text
Target 1

Target 2

Target 3

...

Target N
```

↓

Parallel Dispatch

↓

Execution Monitoring

↓

Result Aggregation

This minimizes total campaign execution time while preserving independent execution records.

---

# 9. Timing Model

Typical execution phases include:

```text
Baseline

↓

Pre-event

↓

Event

↓

Hold

↓

Recovery

↓

Post-validation
```

Timing parameters are scenario-dependent.

Examples include:

- Hold duration
- Settle time
- Recovery wait
- Baseline window
- Post window

---

# 10. Runtime Artifacts

The Stress Execution Framework produces:

```
resolved_targets.json

stress_orchestrator_report.json

runtime_summary.json

progress.log
```

These artifacts are consumed by downstream frameworks.

---

# 11. Validation

Stress execution validates:

- Target availability
- Interface existence
- Platform compatibility
- Event execution success
- Recovery completion

The framework reports execution results but does not determine engineering conclusions.

---

# 12. Error Handling

Typical runtime failures include:

- Device unreachable
- Invalid interface
- Unsupported platform
- CLI failure
- Timeout
- Partial execution

Execution failures are recorded in runtime artifacts for later RCA analysis.

---

# 13. Extension Model

Adding a new stress type should require only:

1. Define new stress mode.
2. Implement execution logic.
3. Register dispatcher.
4. Generate standard execution report.

No downstream framework should require modification unless new evidence is introduced.

---

# 14. Design Principles

## Principle 1

Stress execution performs actions.

It does not interpret results.

---

## Principle 2

Stress execution is reusable across scenarios.

---

## Principle 3

Stress execution produces standardized artifacts.

---

## Principle 4

Execution failures are recorded rather than hidden.

---

## Principle 5

Downstream frameworks consume artifacts rather than runtime state.

---

# 15. Current Stress Modes

Current validated stress operations include:

- Interface Hold / Restore
- Interface Bounce
- ECMP Degraded Hold
- Parallel Interface Operations

Future planned operations include:

- ISSU
- Reboot
- Route Churn
- Daemon Restart
- SNMP Restart
- Hardware Fault Injection
- Rollback
- AE Member Flap

---

# 16. Future Enhancements

Potential architectural improvements include:

## Stress Plugin Registry

Current implementation dispatches stress operations through runtime logic.

Future architecture may introduce a plugin registry.

Example:

```text
interface_hold_restore

↓

InterfaceHoldPlugin

--------------------------------

reboot

↓

RebootPlugin

--------------------------------

issu

↓

ISSUPlugin
```

This would simplify adding new stress operations.

---

## Scenario-driven Stress Configuration

Long-term, stress behavior may be driven through structured scenario definitions rather than code-based configuration.

---

# 17. Summary

The Stress Execution Framework forms the execution engine of Fabric Controller.

It is responsible for reliably executing engineering validation events while remaining independent of evidence collection, RCA generation, engineering reasoning, and visualization.

Its standardized execution model enables new validation scenarios to reuse the same downstream RCA pipeline.

---

## Related Documents

- 02_System_Architecture.md
- 03_Execution_Pipeline.md
- 04_Scenario_Framework.md
- 06_Evidence_Collection_Framework.md
- 11_Artifact_Catalog.md
- 12_Engineering_Glossary.md

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial Stress Execution Framework |
