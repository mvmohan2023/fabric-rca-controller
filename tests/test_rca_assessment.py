import copy
import unittest

from controller.rca.assessment import build_engineering_assessment
from controller.rca.correlation import correlate_by_entity
from controller.rca.models import EvidenceItem


class AssessmentTest(unittest.TestCase):
    def item(self, **kwargs):
        return EvidenceItem(domain="queue", source="queue", entity="dut|port|q2",
                            supporting_artifact="ui.json", **kwargs)

    def test_missing_and_empty_sources_are_not_healthy(self):
        sources = {"fabric_evidence": {"status": "missing", "path": "fabric.json"},
                   "traffic_intent_rca": {"status": "loaded", "normalized_evidence_count": 0},
                   "queue_cos_evidence": {"status": "loaded", "normalized_evidence_count": 2,
                                          "relevant_evidence_count": 0}}
        result = build_engineering_assessment([], [], sources)
        self.assertEqual(result["source_coverage"], "gaps_present")
        self.assertEqual({g["reason"] for g in result["source_gaps"]},
                         {"source_unavailable", "loaded_without_observations", "context_only_observations"})
        intent = next(g for g in result["source_gaps"] if g["source"] == "traffic_intent_rca")
        self.assertIn("corridor", intent["recommended_check"])

    def test_zero_post_delta_is_not_fault_recovery_and_facts_are_traceable(self):
        items = [self.item(metric="occupancy", observed_value=3, phase="delta_running"),
                 self.item(metric="occupancy", observed_value=0, phase="delta_post")]
        candidates = correlate_by_entity(items)
        result = build_engineering_assessment(items, candidates, {})
        facts = result["candidate_assessments"][0]["facts"]
        self.assertEqual([f["evidence_index"] for f in facts], [0, 1])
        self.assertIn("not zero absolute value or proven fault recovery", facts[1]["interpretation"])

    def test_saved_baseline_zero_post_delta_means_unchanged_running(self):
        from controller.congestion_delta_analyzer import compute_delta
        key = ("spine2", "et-0/0/33", 3)
        metric = "peak-buffer-occupancy-percent"
        row = compute_delta({key: {metric: 0}}, {key: {metric: 3}},
                            {key: {metric: 3}})[0]
        self.assertEqual(row["delta_running"][metric], 3)
        self.assertEqual(row["delta_post"][metric], 0)
        items = [self.item(metric=metric, observed_value=row[phase][metric], phase=phase)
                 for phase in ("delta_running", "delta_post")]
        candidates = correlate_by_entity(items)
        before = copy.deepcopy([c.to_dict() for c in candidates])
        result = build_engineering_assessment(items, candidates, {})
        fact = result["candidate_assessments"][0]["facts"][1]
        self.assertIn("no reported change from RUNNING", fact["interpretation"])
        self.assertIn("return to PRE is not established", fact["interpretation"])
        self.assertEqual(before, [c.to_dict() for c in candidates])

    def test_context_is_excluded_and_input_confidence_is_unchanged(self):
        items = [self.item(metric="pfc_activity", observed_value=10, phase="signals"),
                 self.item(metric="drops", observed_value=0, phase="signals")]
        candidates = correlate_by_entity(items)
        before = copy.deepcopy([c.to_dict() for c in candidates])
        result = build_engineering_assessment(items, candidates, {})
        assessment = result["candidate_assessments"][0]
        self.assertEqual(len(assessment["facts"]), 1)
        self.assertTrue(any("priority" in c for c in assessment["recommended_checks"]))
        self.assertEqual(before, [c.to_dict() for c in candidates])

    def test_phase_difference_is_not_a_conflict(self):
        items = [self.item(metric="latency_ns", observed_value=100, phase="delta_running"),
                 self.item(metric="latency_ns", observed_value=20, phase="delta_post")]
        result = build_engineering_assessment(items, correlate_by_entity(items), {})
        assessment = result["candidate_assessments"][0]
        self.assertEqual(assessment["conflict_assessment"], "not_assessed_without_aligned_measurement_windows")
        self.assertTrue(any("SLO" in c for c in assessment["recommended_checks"]))


if __name__ == "__main__":
    unittest.main()
