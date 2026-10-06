import copy
import json
import tempfile
import unittest
from pathlib import Path

from controller.rca.assessment import assess_intent_coverage
from controller.rca.report import build_engineering_rca_report


class IntentCoverageTests(unittest.TestCase):
    def test_unresolved_success_is_not_path_assessment(self):
        intent = {'status': 'ok', 'src_leaf': None, 'dst_leaf': None,
                  'corridor': [], 'matched_hotspots': [], 'rca_summary': None}
        before = copy.deepcopy(intent)
        result = assess_intent_coverage(intent, {'src': '10.1.1.1', 'dst': '10.2.2.2'})
        self.assertEqual(result['status'], 'unassessed_path_coverage')
        self.assertEqual(result['reasons'], ['src_leaf_unresolved', 'dst_leaf_unresolved',
                                            'corridor_empty_or_invalid'])
        self.assertEqual(intent, before)

    def test_resolved_empty_hotspots_are_not_a_health_verdict(self):
        result = assess_intent_coverage({'src_leaf': 'leaf1', 'dst_leaf': 'leaf2',
                                        'corridor': [{'node': 'leaf1', 'interface': 'et-0/0/0'}],
                                        'matched_hotspots': []})
        self.assertEqual(result['status'], 'resolved_corridor_reported')
        self.assertEqual(result['matched_hotspot_count'], 0)
        self.assertIn('not a health verdict', result['interpretation'])

    def test_absent_and_incomplete_schema_are_explicit(self):
        self.assertEqual(assess_intent_coverage(None)['status'], 'source_unavailable')
        self.assertEqual(assess_intent_coverage({})['reasons'],
                         ['endpoint_or_corridor_fields_missing'])
        result = assess_intent_coverage({'src_leaf': 'leaf1', 'dst_leaf': 'leaf2',
                                        'corridor': [{'node': 'leaf1'}]})
        self.assertIn('corridor_entries_incomplete', result['reasons'])

    def test_embedded_source_traceability_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            summary = folder / 'rca_case_summary.json'
            summary.write_text(json.dumps({'src': '10.1.1.1', 'dst': '10.2.2.2'}))
            final = folder / 'rca_final_report.json'
            final.write_text(json.dumps({'intent_rca': {'status': 'ok', 'src_leaf': None,
                'dst_leaf': None, 'corridor': [], 'matched_hotspots': []}}))
            before = final.read_bytes(), summary.read_bytes()
            report = build_engineering_rca_report(str(summary), inventory={})
            result = report['engineering_assessment']['intent_path_coverage']
            self.assertEqual(result['status'], 'unassessed_path_coverage')
            self.assertEqual(result['supporting_artifact'], str(final))
            self.assertEqual(result['artifact_json_pointer'], '/intent_rca')
            self.assertEqual(result['requested_endpoints']['src'], '10.1.1.1')
            self.assertEqual(report['source_availability']['traffic_intent_rca']['status'], 'loaded')
            self.assertEqual(before, (final.read_bytes(), summary.read_bytes()))


if __name__ == '__main__':
    unittest.main()
