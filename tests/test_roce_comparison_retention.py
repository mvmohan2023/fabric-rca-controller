import copy
import unittest
from controller.rocev2_deep_inspector import compare_pre_post, normalize_for_ui, top_n


class RoceComparisonRetentionTest(unittest.TestCase):
    def row(self, seq):
        return {'tx_port': 'Ethernet - 014', 'rx_port': 'Ethernet - 011',
                'flow_name': 'RoCEv2 Flow Group 84', 'src_qp': 66, 'dest_qp': 66,
                'seqerror': seq, 'frames_delta': 353179}

    def test_rank_retains_arithmetic_and_inputs(self):
        pre, post = [self.row(70000)], [self.row(74248)]
        before = copy.deepcopy((pre, post))
        result = top_n(compare_pre_post(pre, post), 'seqerror_increase')[0]
        self.assertEqual([result[k] for k in ('seqerror_pre', 'seqerror_post', 'seqerror_increase')],
                         [70000, 74248, 4248])
        self.assertTrue(result['comparison_coverage']['metric_presence']['seqerror']['pre'])
        self.assertEqual((pre, post), before)

    def test_snapshot_has_no_invented_comparison(self):
        result = normalize_for_ui(self.row(74248))
        self.assertNotIn('seqerror_increase', result)
        self.assertNotIn('comparison_coverage', result)

    def test_missing_phase_is_not_measured_zero(self):
        row = top_n(compare_pre_post([], [self.row(10)]), 'seqerror_increase')[0]
        self.assertFalse(row['comparison_coverage']['pre_flow_present'])
        self.assertFalse(row['comparison_coverage']['metric_presence']['seqerror']['pre'])
        self.assertEqual(row['seqerror_pre'], 0)  # unchanged legacy arithmetic


class RoceProvenanceDiagnosticsTest(unittest.TestCase):
    def test_repeated_baseline_rows_and_counter_decrease(self):
        pre = {'flow_name': 'flow', 'message_failed': 12, 'seqerror': 82,
               'first_timestamp': '00:00:00.455', 'last_timestamp': '00:18:10.524'}
        post = dict(pre, message_failed=11, seqerror=74248,
                    first_timestamp='00:00:00.484', last_timestamp='00:18:10.433')
        before = copy.deepcopy((pre, post))
        row = compare_pre_post([pre] * 84, [post] * 84)[0]
        coverage = row['comparison_coverage']
        self.assertEqual(coverage['duplicate_coverage']['pre'],
                         {'row_count': 84, 'distinct_checked_value_sets': 1})
        self.assertEqual(coverage['duplicate_coverage']['post']['row_count'], 84)
        self.assertEqual(coverage['decreasing_counter_like_metrics'], ['message_failed'])
        self.assertEqual(coverage['counter_continuity'], 'unverified')
        self.assertEqual(row['seqerror_increase'], 74166)
        self.assertEqual((pre, post), before)
        self.assertEqual(normalize_for_ui(row)['comparison_coverage'], coverage)

    def test_distinct_duplicate_values_preserve_last_row_selection(self):
        first = {'flow_name': 'flow', 'seqerror': 1}
        last = dict(first, seqerror=10)
        row = compare_pre_post([first, last], [dict(last, seqerror=20)])[0]
        self.assertEqual(row['seqerror_pre'], 10)
        self.assertEqual(row['comparison_coverage']['duplicate_coverage']['pre']
                         ['distinct_checked_value_sets'], 2)

    def test_absent_invalid_or_nonfinite_values_do_not_prove_decrease(self):
        row = compare_pre_post([{'flow_name': 'flow', 'retx': 'invalid', 'ecn': float('inf')}],
                               [{'flow_name': 'flow', 'retx': 0, 'ecn': 0}])[0]
        self.assertEqual(row['comparison_coverage']['decreasing_counter_like_metrics'], [])
