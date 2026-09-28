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
| Route Churn | ⬜ |
| BFD | ⬜ |
| Route Withdraw | ⬜ |

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
- Juniper operational-health MIB expansion remains pending

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

