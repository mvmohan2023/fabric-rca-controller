import copy
import unittest
from controller.rca.ui_qualification import qualify_ui_claims


class UIQualificationTest(unittest.TestCase):
    def test_baseline_claims_traceable_and_immutable(self):
        report = {'engineering_reasoning': {
            'event_reasoning': {'scenario': 'noop', 'status': 'Recovered'},
            'ecmp_reasoning': {'analysis_status': 'insufficient_data',
                               'regression_detected': False},
            'queue_reasoning': {'event_delta_classification': 'no_event_delta',
                                'tail_linger_trend': 'cleared'}}}
        before = copy.deepcopy(report)
        result = qualify_ui_claims(report, 'ui.json')
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(len(result['findings']), 3)
        for finding in result['findings']:
            self.assertEqual(finding['supporting_artifact'], 'ui.json')
            self.assertTrue(finding['json_pointer'].startswith('/engineering_reasoning/'))
        self.assertEqual(report, before)

    def test_no_selected_gap_is_not_full_qualification(self):
        result = qualify_ui_claims({'engineering_reasoning': {
            'event_reasoning': {'scenario': 'interface_bounce'},
            'ecmp_reasoning': {'analysis_status': 'ok'},
            'queue_reasoning': {'event_delta_classification': 'event_induced'}}})
        self.assertEqual(result['status'], 'no_selected_gap_detected')
        self.assertIn('does not qualify the entire UI', result['limitations'][0])

    def test_missing_source_and_malformed_sections(self):
        self.assertEqual(qualify_ui_claims(None)['status'], 'source_unavailable')
        result = qualify_ui_claims({'engineering_reasoning': {
            'event_reasoning': [], 'ecmp_reasoning': 'invalid', 'queue_reasoning': 1}})
        self.assertEqual(result['findings'], [])
