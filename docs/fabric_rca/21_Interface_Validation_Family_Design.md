# Fabric Controller
# 21. Interface Validation Family Design

**Status:** Draft Design

---

# 1. Purpose

Define how interface-related validation scenarios plug into the existing Fabric Controller architecture.

---

# 2. Current Implementation

Existing stress modes in `stress_orchestrator.py`:

- `interface_bounce`
- `interface_hold_restore`
- `bgp_clear`
- `noop`

Current dispatch flow:

```text
parse_args()
  ↓
run_stress_action()
  ↓
run_parallel_stress_actions()
  ↓
run_single_stress_target()
  ↓
specific stress executor


Interface Scenario Family

Future scenarios:

Interface flap repeat
AE interface disable/enable
AE member flap
Remote interface flap
Local fault / remote fault
ECMP member multi-link flap
4. Design Decision

For now, extend the existing dispatcher pattern in stress_orchestrator.py.

Future direction: replace dispatcher with Stress Plugin Registry.

5. First Implementation Candidate

Recommended first scenario:

ecmp_member_multi_link_flap

Reason:

Close to existing degraded-hold workflow
Reuses target resolution
Reuses telemetry/RCA/UI
Validates ECMP programming after repeated flaps
6. Expected File Impact
File	Expected Change
stress_orchestrator.py	Add new stress mode and executor
fault_injection_runner.py	Minimal scenario wiring if needed
event_catalog.json	Add scenario metadata if applicable
RCA/UI	Reuse existing pipeline
7. Success Criteria
New scenario executes without changing RCA pipeline.
Stress report records each flap iteration.
ECMP recovery is captured.
UI report builds successfully.
Final validation report is generated.
