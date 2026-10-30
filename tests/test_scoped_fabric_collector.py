"""Offline collection contracts; never invoke devices or a stress runner."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from controller.scoped_fabric_collector import (
    OUTPUT_NAME, build_scoped_report, collect_campaign_fabric, inspect_scoped_collection)
from controller.rca.report import build_engineering_rca_report


class ScopedCollectorTest(unittest.TestCase):
    inventory = {'nodes': [{'device': 'dut1', 'alias': 'leaf1'},
                           {'device': 'dut2', 'alias': 'leaf2'}]}

    def root(self):
        return {'summary': {'top_hotspots': [
            {'device': 'dut1', 'interface': 'et-0/0/1', 'rx_port': 'rx1'},
            {'device': 'dut2', 'interface': 'et-0/0/1', 'rx_port': 'rx2'}]}}

    def record(self, value=0, entity='et-0/0/1:queue3', **extra):
        return dict(entity=entity, metric='ecn_marked_pkts', value=value, **extra)

    def build(self, snapshot, anomalies=None, **kwargs):
        return build_scoped_report(self.root(), snapshot, anomalies or {},
            inventory=self.inventory, phase='running', snapshot_path='running.json',
            anomaly_path='anomaly.json', **kwargs)

    def test_same_interface_two_devices_never_mix(self):
        result = self.build({'nodes': [
            {'node_name': 'leaf1', 'normalized_records': [self.record(11)]},
            {'node_name': 'leaf2', 'normalized_records': [self.record(22)]}]})
        self.assertEqual([[r['value'] for r in item['snapshot_records']]
                          for item in result['interfaces']], [[11], [22]])

    def test_prefix_and_channel_are_distinct(self):
        result = self.build({'nodes': [{'node_name': 'leaf1', 'normalized_records': [
            self.record(1, 'et-0/0/10:queue3'), self.record(2, 'et-0/0/1:0:queue3'),
            self.record(3, 'et-0/0/1:pg3')]}]})
        self.assertEqual(result['interfaces'][0]['snapshot_record_count'], 1)
        self.assertEqual(result['interfaces'][0]['snapshot_records'][0]['value'], 3)

    def test_conflicting_labels_and_record_node_are_excluded(self):
        result = self.build({'nodes': [{'node_name': 'leaf1', 'normalized_records': [
            self.record(labels={'interface': 'et-0/0/2'}), self.record(node='leaf2'),
            self.record(labels=['invalid']), self.record(entity={'invalid': True})]}]})
        self.assertEqual(result['interfaces'][0]['snapshot_record_count'], 0)

    def test_alias_case_and_ambiguous_inventory(self):
        snapshot = {'nodes': [{'node_name': 'LEAF1', 'normalized_records': [self.record()]}]}
        self.assertEqual(self.build(snapshot)['interfaces'][0]['snapshot_record_count'], 1)
        inv = {'nodes': self.inventory['nodes'] + [{'device': 'dut3', 'alias': 'leaf1'}]}
        result = build_scoped_report(self.root(), snapshot, {}, inventory=inv, phase='pre')
        self.assertTrue(all(item['snapshot_record_count'] == 0 for item in result['interfaces']))

    def test_provenance_zero_and_input_immutability(self):
        snapshot = {'nodes': [{'node_name': 'leaf1', 'normalized_records': [
            self.record(labels={'queue': 3}, phase='signals',
                        measurement_provenance={'payload_timestamps': {'timestamp': 5}})]}]}
        before = copy.deepcopy(snapshot)
        row = self.build(snapshot)['interfaces'][0]['snapshot_records'][0]
        self.assertEqual(row['value'], 0)
        self.assertEqual(row['source_phase'], 'signals')
        self.assertEqual(row['json_pointer'], '/nodes/0/normalized_records/0')
        row['provenance']['labels']['queue'] = 8
        self.assertEqual(snapshot, before)

    def test_anomalies_require_node_and_exact_interface(self):
        anomalies = {'anomalies': [
            {'node': 'leaf1', 'entity': 'et-0/0/1:queue3', 'type': 'counter_delta'},
            {'node': 'leaf2', 'entity': 'et-0/0/1:queue3', 'type': 'gauge_jump'},
            {'entity': 'et-0/0/1:queue3', 'type': 'missing_node'},
            {'node': 'leaf1', 'entity': 'et-0/0/10:queue3', 'type': 'prefix'}]}
        result = self.build({'nodes': []}, anomalies)
        self.assertEqual([i['anomaly_count'] for i in result['interfaces']], [1, 1])
        self.assertEqual(result['interfaces'][1]['anomalies'][0]['json_pointer'], '/anomalies/1')

    def test_counts_survive_display_limits(self):
        result = self.build({'nodes': [{'node_name': 'leaf1', 'normalized_records':
                                       [self.record()] * 60}]}, limit=2)
        item = result['interfaces'][0]
        self.assertEqual(item['snapshot_record_count'], 60)
        self.assertEqual(len(item['snapshot_records']), 2)
        self.assertEqual(sum(item['snapshot_summary'].values()), 60)

    def test_invalid_limits_and_structure(self):
        for limit in (0, -1, True, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.build({'nodes': []}, limit=limit)
        for data in ({'nodes': {}}, {'nodes': [2]},
                     {'nodes': [{'normalized_records': [2]}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.build(data)


class CampaignCollectionTest(unittest.TestCase):
    def prepare(self, folder):
        root = folder / 'root.json'
        root.write_text(json.dumps({'summary': {'top_hotspots': [
            {'device': 'leaf1', 'interface': 'et-0/0/1'}]}}))
        snapshot = folder / 'running.json'
        snapshot.write_text(json.dumps({'nodes': [{'node_name': 'leaf1', 'normalized_records': [
            {'entity': 'et-0/0/1:queue3', 'metric': 'ecn', 'value': 5}]}]}))
        case = folder / 'case.json'
        case.write_text(json.dumps({'files': {'root_cause_correlation': str(root),
                                             'running_telemetry': str(snapshot)}}))
        return case, root, snapshot

    def test_no_overwrite_idempotence_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            case, root, snapshot = self.prepare(Path(tmp))
            legacy = Path(tmp) / 'fabric_evidence.json'
            legacy.write_text('{"legacy": true}')
            before = [p.read_bytes() for p in (case, root, snapshot, legacy)]
            output = collect_campaign_fabric(case, inventory={})
            self.assertEqual(collect_campaign_fabric(case, inventory={}), output)
            self.assertEqual([p.read_bytes() for p in (case, root, snapshot, legacy)], before)
            Path(output).write_text('existing unrelated content')
            with self.assertRaises(FileExistsError):
                collect_campaign_fabric(case, inventory={})
            self.assertEqual(Path(output).read_text(), 'existing unrelated content')

    def test_missing_invalid_and_empty_phase_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, root, snapshot = self.prepare(folder)
            snapshot.write_text('[]')
            data = json.loads(case.read_text())
            data['files']['pre_telemetry'] = str(folder / 'missing.json')
            case.write_text(json.dumps(data))
            output = collect_campaign_fabric(case, inventory={})
            result = json.loads(Path(output).read_text())
            self.assertEqual(result['source_availability']['pre']['status'], 'missing')
            self.assertEqual(result['source_availability']['running']['status'], 'invalid')
            self.assertEqual(result['source_availability']['post']['status'], 'not_declared')
            self.assertEqual(result['status'], 'insufficient_scoped_coverage')

    def test_declared_output_collision_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, root, snapshot = self.prepare(folder)
            output = folder / OUTPUT_NAME
            output.write_text(snapshot.read_text())
            data = json.loads(case.read_text())
            data['files']['running_telemetry'] = str(output)
            case.write_text(json.dumps(data))
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                collect_campaign_fabric(case, inventory={})
            self.assertEqual(output.read_bytes(), before)

    def test_sidecar_reads_supplement_without_counting_independent_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            case, _, _ = self.prepare(Path(tmp))
            before = build_engineering_rca_report(str(case), inventory={})
            collect_campaign_fabric(case, inventory={})
            after = build_engineering_rca_report(str(case), inventory={})
            coverage = after['engineering_assessment']['scoped_fabric_collection']
            self.assertEqual(coverage['status'], 'loaded')
            self.assertEqual(coverage['phase_record_counts'], {'running': 1})
            before.pop('engineering_assessment')
            after.pop('engineering_assessment')
            self.assertEqual(before, after)

    def test_mismatched_case_and_invalid_artifact_are_not_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, _, _ = self.prepare(folder)
            output = folder / OUTPUT_NAME
            output.write_text('{}')
            self.assertEqual(inspect_scoped_collection(case)['status'], 'invalid')
            output.write_text('[]')
            self.assertEqual(inspect_scoped_collection(case)['status'], 'invalid')

    def test_offline_cli_creates_only_separate_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, root, snapshot = self.prepare(folder)
            inventory = folder / 'inventory.json'
            inventory.write_text('{}')
            before = [p.read_bytes() for p in (case, root, snapshot)]
            result = subprocess.run([sys.executable, '-m', 'controller.scoped_fabric_collector',
                                     '--case-summary', str(case), '--inventory', str(inventory)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(folder / OUTPUT_NAME))
            self.assertEqual(before, [p.read_bytes() for p in (case, root, snapshot)])

    def test_changed_inputs_mark_scoped_collection_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, _, snapshot = self.prepare(folder)
            collect_campaign_fabric(case, inventory={})
            snapshot.write_text('{"nodes": []}')
            self.assertEqual(inspect_scoped_collection(case)['status'], 'stale')

    def test_report_cli_opt_in_preserves_default_evidence_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, root, snapshot = self.prepare(folder)
            inventory = folder / 'inventory.json'
            inventory.write_text('{}')
            baseline = build_engineering_rca_report(str(case), inventory={})
            before = [p.read_bytes() for p in (case, root, snapshot)]
            result = subprocess.run([sys.executable, '-m', 'controller.rca.report',
                                     '--case-summary', str(case), '--inventory', str(inventory),
                                     '--collect-scoped-fabric'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            sidecar = json.loads((folder / 'engineering_rca_report.json').read_text())
            self.assertEqual(sidecar['engineering_assessment']['scoped_fabric_collection']['status'], 'loaded')
            self.assertEqual(sidecar['evidence_summary'], baseline['evidence_summary'])
            self.assertEqual(sidecar['candidates'], baseline['candidates'])
            self.assertEqual(before, [p.read_bytes() for p in (case, root, snapshot)])

    def test_changed_inventory_scope_is_marked_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            case, _, _ = self.prepare(Path(tmp))
            collect_campaign_fabric(case, inventory={})
            self.assertEqual(inspect_scoped_collection(case, inventory={})['status'], 'loaded')
            self.assertEqual(inspect_scoped_collection(case, inventory={'nodes': []})['status'], 'stale')

    def test_previously_missing_phase_becoming_available_marks_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            case, _, snapshot = self.prepare(folder)
            missing = folder / 'pre.json'
            data = json.loads(case.read_text())
            data['files']['pre_telemetry'] = str(missing)
            case.write_text(json.dumps(data))
            collect_campaign_fabric(case, inventory={})
            self.assertEqual(inspect_scoped_collection(case)['status'], 'loaded')
            missing.write_text(snapshot.read_text())
            self.assertEqual(inspect_scoped_collection(case)['status'], 'stale')
