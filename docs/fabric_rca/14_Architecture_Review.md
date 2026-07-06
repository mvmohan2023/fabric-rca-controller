# Fabric Controller
# Architecture Review Board (ARB)

# 14. Architecture Review

**Version:** 1.0

**Status:** Living Architecture Review

---

# 1. Purpose

This document captures periodic architectural reviews of the Fabric Controller platform.

Unlike the Engineering Design Specification (EDS), this document evaluates the current implementation, identifies technical debt, proposes architectural improvements, and records engineering decisions.

It serves as the long-term architecture governance document for the project.

---

# 2. Current Platform Assessment

Overall Architecture Rating

⭐⭐⭐⭐⭐ 9.5 / 10

---

Strengths

✓ Modular architecture

✓ Well-defined execution pipeline

✓ Strong framework separation

✓ Explainable Engineering Reasoning

✓ Artifact-driven pipeline

✓ Highly reusable downstream RCA

---

Improvement Areas

• Large orchestration modules

• Stress dispatcher extensibility

• Scenario registration

• Artifact lifecycle documentation

• Plugin architecture

---

# 3. Framework Health

| Framework | Status | Comments |
|-----------|--------|----------|
| Scenario | Healthy | Well isolated |
| Stress Execution | Healthy | Dispatcher can evolve |
| Evidence Collection | Healthy | Modular collectors |
| Evidence Correlation | Healthy | Good separation |
| RCA | Excellent | Canonical model established |
| Engineering Reasoning | Excellent | Major differentiator |
| Web UI | Healthy | Presentation-only architecture |

---

# 4. Module Ownership Review

## Scenario Framework

Primary modules

- suite_registry.py
- campaign_runner.py
- event_catalog.json

Status

Healthy

---

## Stress Execution Framework

Primary modules

- fault_injection_runner.py
- stress_orchestrator.py
- stress_live_runner.py
- progress_logger.py

Status

Needs future modularization

Observation

fault_injection_runner.py has grown significantly and contains orchestration, stress dispatch, validation, and reporting logic.

Recommendation

Split into smaller execution services over time.

---

## Evidence Collection Framework

Primary modules

- telemetry_monitor.py
- telemetry_analyzer.py
- telemetry_diff.py
- telemetry_targets.py
- telemetry_normalizers.py
- fabric_evidence_collector.py
- collect_device_facts.py
- ixia_live_monitor.py
- ixia_stats_collector.py
- ixia_rocev2_stats.py
- traffic_verifier.py

Status

Healthy

---

## Evidence Correlation Framework

Primary modules

- congestion_analyzer.py
- congestion_delta_analyzer.py
- congestion_inspector.py
- deep_congestion_inspector.py
- fabric_hotspot_ranker.py
- cos_hotspot_correlator.py
- path_congestion_correlator.py
- root_cause_correlator.py

Status

Healthy

---

## RCA Framework

Primary modules

- run_rca_case.py
- rca_ui_report_builder.py
- ui_summary_builder.py

Status

Excellent

---

## Engineering Reasoning Framework

Primary modules

- engineering_reasoning_builder.py

Status

Excellent

Observation

Engineering Reasoning is now the analytical core of the platform.

---

## Web UI Framework

Primary modules

- index.html
- app.js
- styles.css
- rca_ui_server.py

Status

Healthy

Observation

Presentation logic remains well separated from engineering computation.

---

# 5. Artifact Ownership Review

| Artifact | Producer | Consumer | Status |
|----------|----------|----------|--------|
| resolved_targets.json | Scenario | Stress | Healthy |
| stress_orchestrator_report.json | Stress | RCA | Healthy |
| telemetry snapshots | Evidence | Correlation | Healthy |
| congestion_origin_analysis.json | Correlation | RCA | Healthy |
| cos_hotspot_correlation.json | Correlation | RCA | Healthy |
| rca_case_summary.json | RCA | Reasoning/UI | Excellent |
| rca_ui_report.json | UI Builder | Dashboard | Excellent |

Observation

No major ownership issues identified.

---

# 6. Technical Debt Register

## High Priority

### Stress Plugin Registry

Current

Runtime dispatcher logic.

Future

Plugin registration model.

Status

Planned

---

### Scenario Registry

Current

Python implementation.

Future

YAML-driven scenarios.

Status

Planned

---

### Artifact Validation Framework

Current

Basic validation.

Future

Schema validation.

Status

Planned

---

## Medium Priority

### Confidence Scoring Engine

Current

Rule-based.

Future

Weighted evidence scoring.

Status

Future

---

### Dynamic Dashboard Registry

Current

Hardcoded rendering.

Future

Section registration.

Status

Future

---

### Multi-run Comparison

Current

Single run.

Future

Historical comparison.

Status

Future

---

## Low Priority

AI Recommendation Engine

Historical Trend Analysis

Predictive RCA

Release Readiness Dashboard

---

# 7. Current Architectural Risks

Risk

Large orchestration module.

Mitigation

Incremental decomposition.

---

Risk

Increasing number of scenarios.

Mitigation

Scenario registry.

---

Risk

Growing number of stress types.

Mitigation

Stress plugin registry.

---

Risk

Future dashboard complexity.

Mitigation

Component registry.

---

# 8. Architectural Decisions

Decision

Canonical RCA model remains the single source of truth.

Status

Accepted

---

Decision

Engineering Reasoning remains independent from RCA generation.

Status

Accepted

---

Decision

UI performs no engineering calculations.

Status

Accepted

---

Decision

Evidence collectors remain domain-specific.

Status

Accepted

---

# 9. Refactoring Candidates

Candidate

fault_injection_runner.py

Reason

Large orchestration module.

Priority

High

---

Candidate

Scenario registration

Reason

Improve scalability.

Priority

Medium

---

Candidate

Dashboard renderer registry

Reason

Improve maintainability.

Priority

Medium

---

# 10. Future Platform Vision

Fabric Controller continues evolving toward:

- Validation Platform
- RCA Platform
- Engineering Knowledge Platform
- Release Qualification Platform

Future capabilities include:

- ISSU validation
- Route churn validation
- SNMP validation
- Memory analysis
- AI-assisted recommendations
- Historical release analytics

---

# 11. Open Questions

- Should scenarios become fully declarative?
- Should stress execution become plugin-based?
- Should Engineering Confidence become weighted?
- Should dashboard sections become dynamically registered?
- Should RCA reports support multi-run comparison?

---

# 12. Action Items

Short-term

- Complete architecture documentation.
- Add new validation scenarios using existing framework.
- Preserve clean framework separation.

Mid-term

- Introduce scenario registry.
- Introduce stress plugin registry.
- Improve confidence scoring.

Long-term

- AI-assisted engineering reasoning.
- Release qualification automation.
- Historical trend analysis.

---

# Revision History

| Version | Date | Summary |
|----------|------|---------|
| 1.0 | 2026-06-29 | Initial architecture review |
