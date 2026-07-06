# Fabric Controller
# Engineering Design Specification (EDS)

# 04. Scenario Framework

**Version:** 1.0

---

# 1. Purpose

The Scenario Framework defines **what** Fabric Controller validates.

A scenario represents an engineering validation objective rather than a specific implementation or stress action.

The Scenario Framework provides a consistent mechanism for defining, executing, validating, and extending engineering test scenarios while allowing downstream RCA, engineering reasoning, and visualization to remain reusable.

---

# 2. What is a Scenario?

A scenario represents a validation objective.

It answers:

- What engineering behavior should be validated?
- What event should be executed?
- Which targets participate?
- What evidence should be collected?
- What success criteria are expected?

A scenario **does not** describe how stress is executed internally.

---

## Scenario vs Stress Action

One of the most important architectural principles is separating engineering intent from implementation.

```text
Scenario
────────

ECMP Degraded Hold Validation

↓

Stress Action

Interface Hold / Restore
```

Another example:

```text
Scenario

Route Churn Validation

↓

Stress Action

Advertise / Withdraw Routes
```

Multiple scenarios may reuse the same stress action.

Likewise, one scenario may execute multiple stress actions.

---

# 3. Objectives of the Scenario Framework

The framework is designed to:

- Separate engineering objectives from implementation
- Allow scenario reuse
- Reuse the common RCA pipeline
- Keep stress execution independent
- Support future scenario families
- Produce consistent artifacts

---

# 4. Scenario Lifecycle

Every scenario follows the same execution lifecycle.

```text
Scenario Definition
        │
        ▼
Scenario Resolution
        │
        ▼
Target Resolution
        │
        ▼
Campaign Initialization
        │
        ▼
Stress Execution
        │
        ▼
Evidence Collection
        │
        ▼
RCA Generation
        │
        ▼
Engineering Reasoning
        │
        ▼
Dashboard Generation
```

Notice that only one stage performs the actual stress.

Everything after stress execution is generic.

---

# 5. Current Scenario Architecture

Each scenario contains logical information such as:

```text
Scenario Name

Description

Stress Mode

Target Policy

Validation Policy

Timing Configuration

Supported Platforms

Expected Outputs
```

The Scenario Framework converts these logical definitions into executable runtime context.

---

# 6. Scenario Resolution

Primary Responsibility

Convert a scenario identifier into a complete runtime configuration.

Typical activities include:

- Locate scenario
- Validate supported platform
- Apply defaults
- Resolve timing
- Resolve target policy
- Generate execution context

---

# 7. Target Resolution

Target resolution is independent from stress execution.

Responsibilities include:

- Read inventory
- Discover interfaces
- Filter by platform
- Filter by speed
- Select ECMP members
- Apply node selection policy
- Validate availability

Generated artifact:

```
resolved_targets.json
```

This artifact becomes the contract between scenario management and stress execution.

---

# 8. Campaign Initialization

Each execution creates a unique campaign.

Responsibilities:

- Generate run ID
- Create artifact directory
- Initialize logging
- Store metadata
- Prepare execution environment

Typical outputs:

```
runtime_summary.json

progress.log

resolved_targets.json
```

---

# 9. Scenario Categories

Current

```text
ECMP Validation

Interface Validation

Traffic Validation
```

Future

```text
ISSU Validation

Route Churn

SNMP

Telemetry Validation

Daemon Restart

Reboot Validation

Rollback Validation

Memory Validation

Scale Validation

Long Duration Validation

Hardware Alarm Validation
```

Each category should reuse the common execution pipeline.

---

# 10. Scenario Families

Scenarios naturally group into engineering domains.

Example:

```text
Interface Family

• Interface Bounce

• Interface Hold

• AE Flap

• Member Flap
```

```text
Routing Family

• Route Churn

• BGP Restart

• BFD Validation

• ECMP Recovery
```

```text
Software Family

• ISSU

• Rollback

• Daemon Restart

• Process Crash Recovery
```

```text
Telemetry Family

• gNMI Validation

• SNMP Validation

• Streaming Validation
```

```text
Traffic Family

• RoCE Validation

• Congestion Validation

• Queue Validation
```

---

# 11. Extension Model

Adding a new scenario should follow a standard process.

```text
Engineering Requirement
        │
        ▼
Scenario Definition
        │
        ▼
Stress Mode
        │
        ▼
Target Resolution
        │
        ▼
Validators
        │
        ▼
(Optional)

New Evidence
        │
        ▼
(Optional)

New Reasoning
        │
        ▼
(Optional)

New Dashboard
```

Most scenarios should stop after the Validator stage.

---

# 12. Design Principles

## Principle 1

Scenarios represent engineering intent.

---

## Principle 2

Stress actions represent implementation.

---

## Principle 3

One stress action may support multiple scenarios.

---

## Principle 4

Scenarios should maximize reuse of downstream RCA.

---

## Principle 5

Scenarios should not contain engineering reasoning.

Reasoning belongs to the Engineering Reasoning Framework.

---

## Principle 6

Scenarios should generate reusable artifacts.

Artifacts become the interface between framework layers.

---

# 13. Current Scenario Family

Validated scenarios include:

✓ Leaf1 ECMP Degraded Hold

✓ Leaf2 ECMP Degraded Hold

✓ Leaf3 ECMP Degraded Hold

✓ Leaf4 ECMP Degraded Hold

✓ Leaf5 ECMP Degraded Hold

✓ Leaf6 ECMP Degraded Hold

✓ Leaf7 ECMP Degraded Hold

These scenarios currently validate:

- Stress execution
- ECMP recovery
- Queue hotspot analysis
- Congestion origin
- RoCEv2 traffic impact
- Engineering reasoning
- Executive dashboard

---

# 14. Future Roadmap

Planned scenario families:

- ISSU
- Route Churn
- SNMP
- Telemetry Health
- Reboot
- Rollback
- Daemon Restart
- Long-duration Stability
- Hardware Fault Injection
- Scale & Performance Validation

The objective is that each new scenario family reuses the existing RCA and Engineering Reasoning pipeline.

---

# 15. Frequently Asked Questions

### Can multiple scenarios use the same stress action?

Yes.

Stress actions are implementation primitives.

Scenarios define engineering objectives.

---

### Does every new scenario require new RCA logic?

No.

Most scenarios should reuse the existing RCA framework.

---

### Does every scenario require new UI components?

No.

Only scenarios introducing new engineering evidence should require UI changes.

---

### Does every scenario require new telemetry collectors?

No.

Existing collectors should be reused whenever possible.

---

### Where should new engineering conclusions be implemented?

Inside the Engineering Reasoning Framework.

Not inside the Scenario Framework.

---

# 16. Summary

The Scenario Framework is the entry point into the Fabric Controller platform.

It transforms engineering objectives into executable validation workflows while remaining independent of telemetry collection, RCA generation, engineering reasoning, and dashboard visualization.

This separation allows Fabric Controller to continuously grow by adding new scenario families without redesigning the core architecture.

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial Scenario Framework specification |

---

## Related Documents

- 02_System_Architecture.md
- 03_Execution_Pipeline.md
- 05_Stress_Execution_Framework.md
- 07_Engineering_Reasoning_Framework.md
