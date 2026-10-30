import json
import tempfile
import unittest
from pathlib import Path
from controller.rca.fabric_replay import build_fabric_replay
from controller.rca.report import write_engineering_rca_report


class FabricReplayTest(unittest.TestCase):
    inventory = {'nodes': [{'device': 'dut1', 'alias': 'leaf1'},
                           {'device': 'dut2', 'alias': 'leaf2'}]}
    root = {'summary': {'top_hotspots': [{'device': 'dut1', 'interface': 'et-0/0/1'}]}}

    def record(self, entity, value=0):
        return {'entity': entity, 'metric': 'ecn', 'value': value}

    def test_exact_device_interface_match_and_traceability(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pre.json'
            p.write_text(json.dumps({'nodes': [
                {'node_name': 'leaf1', 'normalized_records': [
                    self.record('et-0/0/1:queue3'), self.record('et-0/0/10:queue3', 9),
                    self.record('et-0/0/1:0:queue3', 8)]},
                {'node_name': 'leaf2', 'normalized_records': [self.record('et-0/0/1', 7)]}]}))
            before = p.read_bytes()
            result = build_fabric_replay(Path(tmp) / 'case.json', {'pre_telemetry': str(p)},
                                         self.root, self.inventory)
            self.assertEqual(result['matched_record_count'], 1)
            pre = result['interfaces'][0]['phases']['pre']
            self.assertEqual(pre['records'][0]['value'], 0)
            self.assertEqual(pre['records'][0]['json_pointer'], '/nodes/0/normalized_records/0')
            self.assertEqual(result['source_availability']['post']['status'], 'not_declared')
            self.assertEqual(p.read_bytes(), before)

    def test_ambiguous_alias_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pre.json'
            p.write_text(json.dumps({'nodes': [{'node_name': 'leaf1', 'normalized_records':
                                              [self.record('et-0/0/1')]}]}))
            inventory = {'nodes': self.inventory['nodes'] + [{'device': 'dut3', 'alias': 'leaf1'}]}
            result = build_fabric_replay(Path(tmp) / 'case.json', {'pre_telemetry': str(p)},
                                         self.root, inventory)
            self.assertEqual(result['matched_record_count'], 0)

    def test_limit_disclosed_without_losing_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pre.json'
            p.write_text(json.dumps({'nodes': [{'node_name': 'leaf1', 'normalized_records':
                                              [self.record('et-0/0/1')] * 60}]}))
            result = build_fabric_replay(Path(tmp) / 'case.json', {'pre_telemetry': str(p)},
                                         self.root, self.inventory)
            self.assertEqual(result['matched_record_count'], 60)
            self.assertEqual(len(result['interfaces'][0]['phases']['pre']['records']), 50)

    def test_missing_invalid_and_conflicting_scope_remain_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pre.json'
            p.write_text('[]')
            result = build_fabric_replay(Path(tmp) / 'case.json', {'pre_telemetry': str(p)},
                                         self.root, self.inventory)
            self.assertEqual(result['source_availability']['pre']['status'], 'invalid')
            self.assertEqual(result['status'], 'insufficient_scoped_coverage')

    def test_report_keeps_fabric_source_missing_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / 'root.json'
            root.write_text(json.dumps(self.root))
            pre = folder / 'pre.json'
            pre.write_text(json.dumps({'nodes': [{'node_name': 'leaf1', 'normalized_records':
                                                [self.record('et-0/0/1')]}]}))
            summary = folder / 'case.json'
            summary.write_text(json.dumps({'files': {'pre_telemetry': str(pre),
                                                     'root_cause_correlation': str(root)}}))
            before = [p.read_bytes() for p in (root, pre, summary)]
            result = json.loads(Path(write_engineering_rca_report(str(summary), inventory=self.inventory)).read_text())
            self.assertEqual(result['source_availability']['fabric_evidence']['status'], 'missing')
            self.assertEqual(result['engineering_assessment']['fabric_snapshot_replay']['matched_record_count'], 1)
            self.assertEqual(before, [p.read_bytes() for p in (root, pre, summary)])

    def test_sidecar_must_not_replace_a_declared_replay_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            output = folder / 'engineering_rca_report.json'
            output.write_text('{"nodes": []}')
            summary = folder / 'case.json'
            summary.write_text(json.dumps({'files': {'pre_telemetry': str(output)}}))
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                write_engineering_rca_report(str(summary), inventory={})
            self.assertEqual(output.read_bytes(), before)
