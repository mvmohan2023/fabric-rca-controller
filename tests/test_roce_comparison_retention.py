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
