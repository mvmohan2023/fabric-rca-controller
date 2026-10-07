import json
import tempfile
import unittest
from pathlib import Path
from controller.rca.roce_qualification import build_roce_qualification
from controller.rca.report import write_engineering_rca_report


class RoceSidecarTest(unittest.TestCase):
    def test_saved_baseline_shape_traceable_and_source_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            files = {}
            paths = []
            for phase, seq, failed in [('pre', 82, 12), ('post', 74248, 11)]:
                p = folder / (phase + '.json')
                row = {'flow_name': 'Flow84', 'tx_port': '014', 'rx_port': '011',
                       'src_qp': 66, 'dest_qp': 66, 'seqerror': seq,
                       'message_failed': failed, 'first_timestamp': '00:00:00.455'}
                p.write_text(json.dumps({'session_id': 1, 'normalized_rows': [row] * 84}))
                files['rocev2_' + phase] = str(p)
                paths.append(p)
            case = folder / 'rca_case_summary.json'
            case.write_text(json.dumps({'files': files}))
            paths.append(case)
            before = [p.read_bytes() for p in paths]
            output = write_engineering_rca_report(str(case), inventory={})
            report = json.loads(Path(output).read_text())
            qualification = report['engineering_assessment']['roce_snapshot_qualification']
            self.assertEqual(qualification['status'], 'snapshot_differences_only')
            self.assertEqual(qualification['flow_count'], 1)
            flow = qualification['flows'][0]
            self.assertEqual(flow['snapshot_differences']['seqerror']['increase'], 74166)
            self.assertEqual(flow['source_row_indices']['pre'], list(range(84)))
            self.assertEqual(flow['comparison_coverage']['decreasing_counter_like_metrics'], ['message_failed'])
            self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_missing_and_invalid_do_not_block_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            invalid = folder / 'bad.json'
            invalid.write_text('{"normalized_rows": [5]}')
            result = build_roce_qualification(folder / 'case.json', {'rocev2_pre': str(invalid)})
            self.assertEqual(result['status'], 'insufficient_snapshot_coverage')
            self.assertEqual(result['source_availability']['pre']['status'], 'invalid')
            self.assertEqual(result['source_availability']['post']['status'], 'missing')

    def test_empty_snapshots_do_not_establish_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'empty.json'
            p.write_text('{"normalized_rows": []}')
            result = build_roce_qualification(Path(tmp) / 'case.json',
                                              {'rocev2_pre': str(p), 'rocev2_post': str(p)})
            self.assertEqual(result['status'], 'insufficient_snapshot_coverage')
            self.assertEqual(result['flows'], [])
