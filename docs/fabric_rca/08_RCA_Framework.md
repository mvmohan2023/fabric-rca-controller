# Fabric Controller
# Engineering Design Specification (EDS)

# 08. RCA Framework

**Version:** 1.0

---

# 1. Purpose

The Root Cause Analysis (RCA) Framework is responsible for transforming correlated engineering findings into a unified engineering investigation model.

The RCA Framework is the central integration point of the Fabric Controller platform.

It receives normalized findings from multiple framework layers and produces a single canonical Root Cause Analysis consumed by Engineering Reasoning and the Web UI.

Unlike the Evidence Collection Framework, the RCA Framework does not collect observations.

Unlike the Engineering Reasoning Framework, it does not interpret observations.

Its responsibility is to organize, normalize, and prepare engineering findings for downstream consumers.

---

# 2. Responsibilities

The RCA Framework is responsible for:

- Aggregating evidence
- Organizing findings
- Building the canonical RCA model
- Preparing dashboard data
- Producing engineering-ready artifacts
- Maintaining consistent report schema

The framework is **not** responsible for:

- Executing stress
- Collecting telemetry
- Producing engineering conclusions
- Rendering dashboards

---

# 3. Position within the Platform

```text
Evidence Collection
        │
        ▼
Evidence Correlation
        │
        ▼
RCA Framework
        │
        ▼
Engineering Reasoning
        │
        ▼
Visualization
```

---

# 4. Architecture

```text
                    RCA Framework

           Evidence Correlation Results
                      │
                      ▼
              run_rca_case.py
                      │
        Build Canonical RCA Model
                      │
                      ▼
            rca_case_summary.json
                      │
                      ▼
         rca_ui_report_builder.py
                      │
                      ▼
              rca_ui_report.json
                      │
                      ▼
        Engineering Reasoning Framework
                      │
                      ▼
               Executive Dashboard
```

---

# 5. Major Components

## RCA Case Generator

Primary Module

```
controller/run_rca_case.py
```

Responsibilities

- Merge evidence
- Normalize findings
- Build RCA model
- Organize engineering data

Primary Output

```
rca_case_summary.json
```

---

## RCA UI Report Builder

Primary Module

```
controller/rca_ui_report_builder.py
```

Responsibilities

- Convert RCA model into UI representation
- Build executive summary
- Prepare engineering sections
- Organize entity evidence
- Inject Engineering Reasoning

Primary Output

```
rca_ui_report.json
```

---

# 6. RCA Processing Pipeline

```text
Telemetry Findings
        │
Queue Findings
        │
Traffic Findings
        │
Interface Findings
        │
ECMP Findings
        │
Congestion Origin
        │
        ▼
run_rca_case.py
        │
        ▼
rca_case_summary.json
        │
        ▼
rca_ui_report_builder.py
        │
        ▼
rca_ui_report.json
```

---

# 7. Canonical RCA Model

The canonical RCA model provides a single normalized representation of a validation run.

Typical sections include:

```
Stress Execution

Telemetry

Traffic

Queue

ECMP

Interface

Congestion Origin

CoS Correlation

Metadata

Summary
```

This artifact becomes the primary input to Engineering Reasoning.

---

# 8. UI Report Model

The UI report extends the canonical RCA model.

Typical sections include:

- Executive Summary
- Investigation Summary
- Queue Health
- Traffic Health
- ECMP Recovery
- Congestion Origin
- Entity Evidence
- Metadata
- Engineering Reasoning

---

# 9. Produced Artifacts

Primary artifacts include:

```
rca_case_summary.json

rca_ui_report.json
```

Additional enrichment may include:

```
congestion_origin_analysis.json

cos_hotspot_correlation.json

traffic_verdict.json

topology_view.html
```

Refer to **11_Artifact_Catalog.md** for detailed definitions.

---

# 10. Data Organization

The RCA Framework groups evidence by engineering domains.

Typical organization includes:

```text
Stress
    │
Telemetry
    │
Traffic
    │
Queue
    │
ECMP
    │
Interface
    │
Congestion
    │
Engineering
```

This organization allows downstream consumers to navigate the RCA consistently.

---

# 11. Normalization

One of the primary responsibilities of the RCA Framework is normalization.

Normalization ensures:

- Consistent naming
- Stable schema
- Unified evidence representation
- Backward compatibility
- Predictable dashboard rendering

Without normalization, every downstream consumer would need to understand multiple evidence formats.

---

# 12. Integration with Engineering Reasoning

The RCA Framework provides structured engineering findings.

Engineering Reasoning consumes these findings and produces:

- Evidence Chain
- Alternative Explanations
- Confidence
- Engineering Verdict
- Executive Assessment

The RCA Framework intentionally does not perform reasoning.

---

# 13. Integration with Visualization

The Web UI consumes only:

```
rca_ui_report.json
```

The dashboard never reads raw telemetry or correlation outputs directly.

This separation isolates visualization from internal implementation changes.

---

# 14. Code Mapping

| Module | Responsibility |
|----------|----------------|
| run_rca_case.py | Build canonical RCA model |
| rca_ui_report_builder.py | Generate UI report |
| ui_summary_builder.py | Executive summaries |
| topology_html_report.py | Interactive topology |
| traffic_intent_rca.py | Traffic RCA integration |
| traffic_intent_rca_ecmp.py | ECMP traffic correlation |

---

# 15. Design Principles

## Principle 1

The RCA Framework aggregates findings.

It does not generate conclusions.

---

## Principle 2

The canonical RCA model is the single source of truth.

---

## Principle 3

Visualization should consume normalized data only.

---

## Principle 4

Engineering Reasoning should consume the canonical RCA model rather than raw evidence.

---

## Principle 5

Schema stability is preferred over implementation convenience.

---

# 16. Future Enhancements

Future improvements may include:

- Historical RCA comparison
- Multi-run RCA
- AI-assisted RCA summarization
- Release health reports
- RCA export APIs
- Historical trend visualization

---

# 17. Summary

The RCA Framework is the integration hub of Fabric Controller.

It transforms correlated engineering findings into a stable, normalized representation that supports Engineering Reasoning, visualization, historical analysis, and future AI-assisted recommendations.

---

## Related Documents

- 06_Evidence_Collection_Framework.md
- 07_Evidence_Correlation_Framework.md
- 09_Engineering_Reasoning_Framework.md
- 10_WebUI_Framework.md
- 11_Artifact_Catalog.md
- 12_Engineering_Glossary.md

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | 2026-06-29 | Mohan Kumar M V | Initial RCA Framework specification |
