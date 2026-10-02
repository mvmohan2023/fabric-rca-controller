"""Offline qualification for additive RCA relevance and campaign integration."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from controller.rca.correlation import correlate_by_entity, correlate_hierarchical_by_entity
from controller.rca.evidence_normalizer import normalize_queue_cos_evidence
from controller.rca.models import EvidenceItem
from controller.rca.relevance import assess_relevance
from controller.rca.report import build_engineering_rca_report, write_engineering_rca_report


class EngineeringRCATest(unittest.TestCase):
    def item(self, **kwargs):
        defaults = dict(domain="traffic", source="traffic", entity="dut|et-0/0/0",
                        metric="loss", observed_value=5, classification="observation",
                        supporting_artifact="traffic.json")
        defaults.update(kwargs)
        return EvidenceItem(**defaults)

    def test_default_volume_neither_dilutes_nor_inflates_confidence(self):
        traffic = self.item()
        baseline = correlate_by_entity([traffic])[0]
        zeros = [self.item(domain="queue", source="queue", observed_value=0,
                           classification=None, supporting_artifact=None) for _ in range(1000)]
        result = correlate_by_entity([traffic, *zeros])[0]
        self.assertEqual(result.confidence, baseline.confidence)
        self.assertEqual(result.category, "domain_observation")
        self.assertEqual(len(result.supporting_evidence), 1001)
        self.assertEqual(result.metadata["confidence_assessment"]["context_evidence_count"], 1000)
        self.assertEqual(correlate_by_entity(zeros), [])

    def test_recovery_requires_matching_entity_source_metric_and_phase(self):
        running = self.item(domain="queue", source="queue", phase="delta_running")
        post = self.item(domain="queue", source="queue", phase="delta_post", observed_value=0)
        unrelated = self.item(domain="queue", source="queue", entity="dut|et-0/0/0|q3",
                              phase="delta_post", observed_value=0)
        wrong_source = self.item(source="other", phase="delta_post", observed_value=0)
        wrong_metric = self.item(domain="queue", source="queue", metric="ecn",
                                 phase="delta_post", observed_value=0)
        decisions = assess_relevance([running, post, unrelated, wrong_source, wrong_metric])
        self.assertEqual([d["relevant"] for d in decisions], [True, True, False, False, False])
        self.assertEqual(decisions[1]["reason"], "phase_supported_recovery")

    def test_padded_series_and_scores_do_not_prove_recovery(self):
        rise = self.item(metric="rise_tail_dropped_packets", observed_value=5)
        linger = self.item(metric="linger_tail_dropped_packets", observed_value=0,
                           metadata={"post_tail_linger_series": [0, 0, 0], "score": 100})
        confidence = self.item(domain="queue", source="queue", metric="classification_confidence",
                               observed_value=0.99)
        decisions = assess_relevance([rise, linger, confidence])
        self.assertEqual([d["relevant"] for d in decisions], [True, False, False])

    def test_states_numeric_strings_and_invalid_values(self):
        items = [self.item(observed_value=v) for v in [False, "DOWN", "0.0", "5", float("nan"), float("inf"), None, {}]]
        self.assertEqual([d["relevant"] for d in assess_relevance(items)],
                         [True, True, False, True, False, False, False, False])

    def test_hierarchy_keeps_source_entities_and_qualifies_diversity(self):
        traffic = self.item()
        queue = self.item(domain="queue", source="queue", entity="leaf6|et-0/0/0|q2")
        before = copy.deepcopy([traffic.to_dict(), queue.to_dict()])
        candidates = correlate_hierarchical_by_entity([traffic, queue], inventory={"nodes": [{"device": "dut", "alias": "leaf6"}]})
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].category, "cross_domain_observation")
        self.assertEqual(candidates[0].metadata["confidence_label"], "Medium")
        self.assertEqual(before, [traffic.to_dict(), queue.to_dict()])

    def test_adapter_is_immutable(self):
        report = {"evidence_index": {"leaf6|et-0/0/0|q2": {"signals": {"ecn": 0}, "post_tail_linger_series": [0, 0, 0]}}}
        before = copy.deepcopy(report)
        normalize_queue_cos_evidence(report)
        self.assertEqual(report, before)

    def test_sidecar_preserves_all_inputs_and_reports_missing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "rca_case_summary.json"
            summary.write_text(json.dumps({"run_id": "offline", "files": {}}))
            traffic = root / "root_cause_correlation.json"
            traffic.write_text(json.dumps({"summary": {"top_hotspots": [{"device": "dut", "interface": "et-0/0/0", "frame_delta": 5}]}}))
            ui = root / "rca_ui_report.json"
            ui.write_text(json.dumps({"evidence_index": {"leaf6|et-0/0/0|q2": {"signals": {"ecn": 4}}}, "ecmp_recovery": {"expected_mode": "equal_member"}}))
            inputs = {p: p.read_bytes() for p in [summary, traffic, ui]}
            output = Path(write_engineering_rca_report(str(summary), inventory={"nodes": [{"device": "dut", "alias": "leaf6"}]}))
            report = json.loads(output.read_text())
            self.assertEqual(report["candidates"][0]["category"], "cross_domain_observation")
            self.assertEqual(report["source_availability"]["fabric_evidence"]["status"], "missing")
            self.assertEqual(inputs, {p: p.read_bytes() for p in inputs})

    def test_empty_or_invalid_inputs_cannot_become_a_healthy_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "rca_case_summary.json"
            summary.write_text('{"run_id": "empty"}')
            (root / "rca_ui_report.json").write_text('broken')
            report = build_engineering_rca_report(str(summary), inventory={})
            self.assertEqual(report["status"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(report["source_availability"]["queue_cos_evidence"]["status"], "invalid")
            self.assertEqual(report["candidates"], [])

    def test_output_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "rca_case_summary.json"
            output = root / "engineering_rca_report.json"
            output.write_text('{}')
            summary.write_text(json.dumps({"files": {"fabric_evidence": str(output)}}))
            with self.assertRaises(ValueError):
                write_engineering_rca_report(str(summary), inventory={})
            self.assertEqual(output.read_text(), '{}')

    def test_existing_producer_locations_and_embedded_intent_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "traffic").mkdir()
            summary = root / "rca_case_summary.json"
            summary.write_text('{"run_id": "producer_paths"}')
            final = root / "rca_final_report.json"
            final.write_text(json.dumps({"intent_rca": {"status": "ok", "rca_summary": {
                "node": "dut", "interface": "et-0/0/0", "signals": {"ecn": 5},
                "intent_cause": "queue-pressure"}}}))
            fabric = root / "traffic" / "fabric_evidence.json"
            fabric.write_text(json.dumps({"interfaces": [{"device": "dut", "interface": "et-0/0/0",
                "snapshot_records": [{"metric": "oper_status", "value": "UP"}]}]}))
            inputs = {p: p.read_bytes() for p in [summary, final, fabric]}
            path = Path(write_engineering_rca_report(str(summary), inventory={}))
            report = json.loads(path.read_text())
            self.assertEqual(report["source_availability"]["fabric_evidence"]["status"], "loaded")
            self.assertEqual(report["source_availability"]["traffic_intent_rca"]["json_pointer"], "/intent_rca")
            intent = next(e for e in report["evidence"] if e["source"] == "traffic_intent_rca")
            self.assertEqual(intent["supporting_artifact"], str(final))
            self.assertEqual(intent["metadata"]["artifact_json_pointer"], "/intent_rca")
            self.assertEqual(inputs, {p: p.read_bytes() for p in inputs})

    def test_explicit_missing_path_is_not_replaced_by_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "traffic").mkdir()
            (root / "traffic" / "fabric_evidence.json").write_text('{}')
            summary = root / "rca_case_summary.json"
            summary.write_text('{"files": {"fabric_evidence": "missing.json"}}')
            report = build_engineering_rca_report(str(summary), inventory={})
            self.assertEqual(report["source_availability"]["fabric_evidence"]["status"], "missing")

    def test_failed_embedded_intent_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "rca_case_summary.json"
            summary.write_text('{}')
            (root / "rca_final_report.json").write_text(json.dumps({"intent_rca": {"status": "failed",
                "rca_summary": {"node": "dut", "signals": {"ecn": 5}}}}))
            report = build_engineering_rca_report(str(summary), inventory={})
            self.assertEqual(report["source_availability"]["traffic_intent_rca"]["status"], "invalid")
            self.assertEqual(report["evidence"], [])


if __name__ == "__main__":
    unittest.main()
