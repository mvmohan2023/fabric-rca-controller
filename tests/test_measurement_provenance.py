import copy
import unittest

from controller.fabric_evidence_collector import build_report
from controller.telemetry_normalizers import normalize_telemetry_payload
from controller.rca.evidence_normalizer import normalize_fabric_evidence
from controller.rca.conflicts import assess_aligned_conflicts


class MeasurementProvenanceTests(unittest.TestCase):
    def payload(self):
        return {'prefix': 'interfaces/interface[name=et-0/0/0]',
                'updates': [{'Path': 'state/counters/in-pkts', 'values': {'in-pkts': 0}}]}

    def report(self, record):
        return build_report({'summary': {'top_hotspots': [
            {'device': 'leaf1', 'interface': 'et-0/0/0', 'rx_port': 'rx1'}]}},
            {'nodes': [{'node_name': 'leaf1', 'normalized_records': [record]}]}, {})

    def test_payload_timestamps_preserved_without_semantic_inference(self):
        payload = self.payload()
        legacy = normalize_telemetry_payload(payload, 'leaf1', '/interfaces')
        payload.update(timestamp=123456789, time='source-clock-text')
        original = copy.deepcopy(payload)
        records = normalize_telemetry_payload(payload, 'leaf1', '/interfaces')
        self.assertTrue(records)
        for new, old in zip(records, legacy):
            provenance = new.pop('measurement_provenance')
            self.assertEqual(new, old)
            self.assertEqual(provenance['payload_timestamps'],
                             {'timestamp': 123456789, 'time': 'source-clock-text'})
        self.assertEqual(payload, original)

    def test_collector_adapter_preserve_supplied_context_phase_and_raw_scope(self):
        record = {'node': 'leaf1', 'entity': 'et-0/0/0:queue2', 'metric': 'ecn',
                  'value': 0, 'raw_value': '0', 'path': '/cos', 'type': 'counter',
                  'labels': {'queue': 2}, 'phase': 'running',
                  'measurement_provenance': {'payload_timestamps': {'timestamp': 123}},
                  'comparison_context': {'measured': True, 'unit': 'packets'}}
        original = copy.deepcopy(record)
        report = self.report(record)
        item = normalize_fabric_evidence(report, supporting_artifact='fabric.json')[0]
        self.assertEqual(item.phase, 'running')
        self.assertEqual(item.metadata['record_entity'], 'et-0/0/0:queue2')
        self.assertEqual(item.metadata['comparison_context'], record['comparison_context'])
        self.assertEqual(item.metadata['measurement_provenance']['labels'], {'queue': 2})
        self.assertEqual(record, original)
        report['interfaces'][0]['snapshot_records'][0]['comparison_context']['unit'] = 'changed'
        self.assertEqual(record, original)
        self.assertEqual(assess_aligned_conflicts([item])['comparable_pair_count'], 0)

    def test_timestamp_alone_does_not_create_measurement_contract(self):
        payload = self.payload()
        payload['timestamp'] = 123
        record = normalize_telemetry_payload(payload, 'leaf1', '/interfaces')[0]
        item = normalize_fabric_evidence(self.report(record), supporting_artifact='fabric.json')[0]
        self.assertNotIn('comparison_context', item.metadata)
        self.assertIsNone(item.phase)
        self.assertEqual(assess_aligned_conflicts([item])['unqualified_evidence_indices'], [0])

    def test_legacy_collector_fields_are_preserved(self):
        record = {'entity': 'et-0/0/0', 'metric': 'ecn', 'value': 0}
        row = self.report(record)['interfaces'][0]['snapshot_records'][0]
        row.pop('measurement_provenance')
        self.assertEqual(row, {'node': 'leaf1', 'entity': 'et-0/0/0',
                              'metric': 'ecn', 'value': 0, 'category': 'ecn_pfc_pause'})


if __name__ == '__main__':
    unittest.main()
