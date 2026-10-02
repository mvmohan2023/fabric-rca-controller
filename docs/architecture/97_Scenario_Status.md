# Scenario Status

Legend

✅ Complete

🟨 In Progress

⬜ Planned

⚪ Platform Dependent

---

## Interface Family

| Scenario | Code | Validation | RCA | Report | Status |
|----------|------|------------|------|----------|---------|
| Bounce | ✅ | ✅ | ✅ | ✅ | Complete |
| Flap | ✅ | ✅ | ✅ | ✅ | Complete |
| Shutdown | ✅ | ✅ | ✅ | ✅ | Complete |
| Restore | ✅ | ✅ | ✅ | ✅ | Complete |
| Hold Restore | ✅ | ✅ | ✅ | ✅ | Complete |

---

## ECMP Family

| Scenario | Status |
|----------|---------|
| Hold Restore | ✅ |

---

## BGP Family

| Scenario | Status |
|----------|---------|
| BGP Clear | ✅ |
| Neighbor Shutdown | ✅ |
| Neighbor Restore | ✅ |
| Neighbor Flap | ✅ |

---

## Routing Family

| Scenario | Status |
|----------|---------|
| Route Churn | Implemented: `route_churn_single`; controlled-prefix scope; live evidence not recorded |
| BFD | Implemented: `bfd_session_flap_single`; live evidence not recorded |
| Route Withdraw | Implemented: `route_withdraw_single`; live evidence not recorded |

---

## Software Family

ISSU

Rollback

Reboot

Daemon Restart

---

## Telemetry Family

gNMI Poll

Status: Code and offline validation complete; live qualification pending

Evidence:
- b769076 — Add strict gNMI poll validation
- ba55fbe — Add validation domain policy for gNMI poll

gNMI Subscribe

Status: Code and offline validation complete; live qualification pending

Evidence:
- Bounded gNMI stream command and subscription primitive validated offline
- Multi-node stream health aggregation validated offline
- Stream-mode Engineering Validation PASS/FAIL/INCONCLUSIVE semantics validated offline
- Runner collector and artifact plumbing validated offline

SNMP Poll

Status: Single-node live qualification complete on leaf2; broader multi-node qualification pending

Evidence:
- SNMPv2c scalar polling executed from telemetry server to leaf2 (10.83.6.4)
- 1/1 selected node passed
- 3/3 required SNMP scalar objects received
- PRE/POST platform validation passed
- Engineering Validation overall status PASS
- Live run: snmp_poll_leaf2_20260928_202919
- Juniper jnxOperatingTable collection live-qualified on leaf2
- 6/6 Juniper operating-health metric walks passed: temperature, CPU, installed memory, CPU 1/5/15-minute averages
- Full integration regression PASS: snmp_jnx_leaf2_20260928_214226
- Scalar health remained 3/3 and Juniper operating-health collection remained 6/6
- Juniper operating-health collection-completeness policy validated offline
- Positive policy test: scalar 3/3 + Juniper 6/6 => telemetry PASS
- Negative policy test: simulated cpu_5min_pct walk failure => telemetry FAIL (5/6)
- CPU/temperature threshold verdicts remain intentionally separate; collection PASS is not a device-health threshold verdict

Streaming

---

## Platform Family

Memory

CPU

Hardware Alarm

Core

Optics

---

## Scale Family

Large Scale

Burn-in

Long Duration


## Reconciliation — 2026-10-02

Inspected branch: `feature/snmp-poll-validation`, source checkpoint `40c6001`.
Code evidence: `controller/fault_injection_runner.py::SCENARIOS`,
`controller/stress_orchestrator.py::register_builtin_stress_actions`,
`controller/stress_actions/`, `controller/validation/`,
`controller/executive_release/`, and `controller/engineering_reasoning_builder.py`.

| Capability | Actual implementation | Qualification / remaining gap |
|---|---|---|
| Interface / ECMP / BGP | Runner definitions and action handlers present | Existing tracker records completed families; no new live claim |
| Route churn / withdraw | Runner, parameter plumbing, registered actions, target resolution present | Controlled connected prefix; not large-scale churn; live evidence not recorded in current tracker |
| BFD flap | Runner, peer target resolver, registered action present | Live qualification not recorded in current tracker |
| Daemon restart | `daemon_restart_single` → `process_restart` handler | Live qualification not recorded in current tracker |
| Reboot | `node_reboot` registered stress action and runner parameter plumbing | No `SCENARIOS` entry selects it; top-level scenario incomplete |
| ISSU / image rollback | No runner definition or registered action found | Missing implementation; image/platform/lab prerequisites required |
| gNMI poll / subscribe | Runner policies, collectors and validation present | Prior offline completion documented; live qualification pending |
| SNMP poll | Collector, scalar + Juniper health validation present | Single-node live complete; multi-node pending |
| Platform health | PRE/POST CPU, memory, cores, alarms and optics comparison present | Monitoring is not a standalone memory-leak/burn-in/optics fault scenario |
| Executive release | Models/evaluator and suite engineering aggregation present | Provisional score; planned coverage, RCA aggregate and historical inputs missing |
| Engineering reasoning | Queue/interface/ECMP/event builders present | Does not close historical retrieval / Engineering AI milestones |
| AE/LACP | Excluded by architecture 04 §23 in current lab | Do not add as current required scenario |
| Remote flap / long-duration / scale | No dedicated complete scenario found | Generic repeated/parallel stress is not proof of those scenario contracts |

28 runner scenario definitions reference 14 distinct modes. Twelve modes have
registered actions. `bgp_evpn_flap` and `combined_queue_pressure_bounce` are
planned definitions without registered actions. `node_reboot`,
`interface_shutdown`, and `interface_restore` are registered actions without
corresponding top-level runner scenario selections. These primitive actions
must not be counted as missing execution code or complete runner scenarios.
EVPN/VXLAN definitions are excluded from current qualification by architecture.

The old Software/Platform/Scale lists above describe intended coverage rather
than verified implementation or production qualification.
