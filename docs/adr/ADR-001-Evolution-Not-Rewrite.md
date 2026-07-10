# ADR-001: Evolution, Not Rewrite

**Status:** Accepted  
**Date:** 2026-07-10  
**Decision Owner:** Mohan Kumar M V

## Context

Fabric Controller already contains mature and validated capabilities, including:

- Stress orchestration
- Fault injection
- Campaign and suite execution
- Telemetry collection
- Traffic validation
- ECMP and congestion analysis
- RoCEv2 deep inspection
- Root-cause correlation
- Engineering reasoning
- JSON and HTML reporting
- Web UI

Replacing these components would introduce unnecessary regression risk and discard significant engineering investment.

## Decision

Fabric Validation Platform v2 will evolve the existing framework incrementally.

The following must remain backward compatible:

- Existing CLI commands
- Existing scenario names
- Existing automation scripts
- Existing JSON artifacts
- Existing RCA reports
- Existing Web UI pages
- Existing campaign and suite execution workflows

New capabilities will be added around or underneath the existing implementation through reusable helpers, registries, validation contracts, and reporting layers.

## Consequences

### Positive

- Existing workflows continue to operate.
- Enhancements can be delivered incrementally.
- Regression risk is reduced.
- Existing RCA and UI investments are preserved.
- New scenarios can reuse mature framework components.

### Trade-offs

- Some legacy structure will remain during migration.
- Temporary adapters may be required.
- Refactoring must be performed in small, testable stages.
- New and legacy result schemas may coexist during transition.

## Implementation Principles

1. Extend before replacing.
2. Preserve existing external interfaces.
3. Add schema fields without removing existing fields.
4. Validate every refactoring through smoke and end-to-end tests.
5. Keep each change small enough to review and revert.
6. Update architecture and scenario documentation with each feature.

## Related Documents

- `docs/architecture/00_Project_Vision.md`
- `docs/architecture/01_System_Architecture.md`
- `docs/architecture/13_Backward_Compatibility.md`
- `docs/architecture/14_Roadmap.md`
