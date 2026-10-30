# Offline Engineering Qualification Cases

Checkpoint: 2026-10-30. This is a test inventory, not an implementation dashboard.
The canonical position remains in `99_Implementation_Tracker.md`.

## Execution

From the repository root, with the project Python environment active:

```bash
python -m unittest discover -s tests -q
node tests/test_engineering_qualification_ui.js
node --check webui/app.js
```

Validated here: **77 Python tests and 5 JavaScript UI cases PASS**. No device,
IXIA session, live topology, service restart or stress scenario is invoked.
These checks qualify code contracts and fixtures, not live scenario behavior.

## New cases in this checkpoint

| Area | Cases implemented | Evidence |
|---|---|---|
| Scoped device identity | Same interface on two devices, inventory alias/case resolution, ambiguous alias exclusion | `tests/test_scoped_fabric_collector.py` |
| Interface identity | Prefix collisions, channelized interfaces, queue/priority-group children, conflicting labels/node identities | Same |
| Provenance | Zero retention, original phase, deep-copied source record, source JSON pointer, input immutability | Same |
| Anomalies | Exact device/interface match, missing-node exclusion, prefix exclusion, source pointer | Same |
| Collection coverage | Full totals with display cap, invalid limits, malformed node/record structures | Same |
| Artifact lifecycle | Separate output, idempotent repeat, changed-content refusal, source/output collision, source byte preservation | Same |
| Partial artifacts | Undeclared, missing and invalid phases, empty coverage | Same |
| Freshness | Input fingerprints, changed source, changed inventory, wrong campaign, malformed artifact | Same |
| Report integration | Optional collection, source/legacy preservation, identical pre-existing evidence counts and candidates | Same |
| Runner options | Default off, single-scenario opt-in, existing suite compatibility, explicit rejection of unsupported suite opt-in | `tests/test_scoped_runner_options.py` |
| Qualification UI | Coverage/zero counts, missing sidecar, HTML escaping, stale run response, RoCE values and source link | `tests/test_engineering_qualification_ui.js` |

The existing suite also covers relevance, exact/hierarchical correlation,
source discovery, zero-post semantics, intent gaps, aligned conflicts,
measurement provenance, read-only API behavior, RoCE comparison retention,
duplicates/decreases, sidecar preservation and scoped replay.

## Scoped collection integration

The legacy collector API and output are preserved. New exact-scoped collection
creates only `fabric_evidence_scoped.json` beside the case summary. It reads
explicit saved PRE/RUNNING/POST telemetry paths and root-correlation targets.
It records missing/invalid phases, exact match counts, source pointers and
source/inventory fingerprints. It does not contact the topology or create an
independent source of corroboration. Re-running unchanged inputs is idempotent;
existing content is never replaced when inputs or configuration change.

Offline collection and report generation can be requested together:

```bash
python -m controller.rca.report \
  --case-summary artifacts/campaigns/<run-id>/rca_case_summary.json \
  --inventory controller/inventory.json \
  --collect-scoped-fabric
```

Standalone collection is available through
`python -m controller.scoped_fabric_collector` with the same two required paths.
Future single-scenario runner executions may opt in with
`--collect-scoped-fabric-evidence`. The default is off. Suite opt-in is rejected
explicitly; saved suite cases can each use the offline collection command.
Collection failure warns without changing the existing runner verdict or exit
semantics. The engineering sidecar reads the separate artifact and reports
loaded/missing/invalid/stale coverage. Original `fabric_evidence.json` availability,
legacy normalized evidence counts and candidate confidence are preserved.

## Qualification still requiring artifacts or lab availability

- Replay new collection against actual saved baseline/negative snapshots.
- Browser rendering of the newest scoped collection coverage.
- Actual collector/device-source and anomaly qualification.
- Verified traffic IP-to-port mapping and nonempty intent corridor evidence.
- Independent aligned windows and real counter/reset epochs.
- Live gNMI, multi-node SNMP and routing/process scenario qualifications recorded
  as pending in `97_Scenario_Status.md`.
- Reboot scenario integration, ISSU/image operations, scale and soak remain
  separate documented scenario work; none is claimed implemented by unit tests.
