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

Status: Pending

SNMP

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

