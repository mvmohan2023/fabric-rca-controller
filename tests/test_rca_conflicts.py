import copy
import unittest

from controller.rca.assessment import build_engineering_assessment
from controller.rca.conflicts import assess_aligned_conflicts
from controller.rca.correlation import correlate_by_entity
from controller.rca.evidence_normalizer import normalize_fabric_evidence
from controller.rca.models import EvidenceItem


class ConflictTest(unittest.TestCase):
    def item(self, source, value, **kwargs):
        context = dict(measured=True, window_start="2026-10-02T20:00:00Z",
                       window_end="2026-10-02T20:01:00Z", measurement_kind="gauge",
                       unit="percent", population="queue-q2", absolute_tolerance=0.1)
        context.update(kwargs.pop("context", {}))
        defaults = dict(domain="queue", source=source, entity="dut|port|q2",
                        metric="occupancy", observed_value=value, phase="running",
                        supporting_artifact=source + ".json", metadata={"comparison_context": context})
        defaults.update(kwargs)
        return EvidenceItem(**defaults)

    def test_aligned_disagreement_is_traceable_without_mutation(self):
        items = [self.item("a", 5), self.item("b", 10)]
        before = copy.deepcopy([e.to_dict() for e in items])
        result = assess_aligned_conflicts(items)
        self.assertEqual(result["status"], "disagreements_observed")
        self.assertEqual(result["disagreements"][0]["evidence_indices"], [0, 1])
        self.assertEqual(before, [e.to_dict() for e in items])

    def test_tolerance_agreement_does_not_imply_all_evidence_qualified(self):
        result = assess_aligned_conflicts([self.item("a", 5), self.item("b", 5.05),
                                         self.item("c", 50, metadata={})])
        self.assertEqual(result["status"], "no_disagreement_in_comparable_pairs")
        self.assertEqual(result["unqualified_evidence_indices"], [2])

    def test_different_scope_or_phase_is_not_compared(self):
        base = self.item("a", 5)
        variants = [self.item("b", 10, phase="post"),
                    self.item("b", 10, entity="dut|port|q3"),
                    self.item("b", 10, context={"unit": "bytes"}),
                    self.item("b", 10, context={"population": "interface"}),
                    self.item("b", 10, context={"window_end": "2026-10-02T20:02:00Z"})]
        for other in variants:
            with self.subTest(other=other.to_dict()):
                self.assertEqual(assess_aligned_conflicts([base, other])["comparable_pair_count"], 0)

    def test_missing_invalid_provenance_and_nonfinite_values_are_unknown(self):
        variants = [self.item("b", 10, metadata={}), self.item("b", 10, context={"measured": False}),
                    self.item("b", 10, context={"window_start": "2026-10-02T20:00:00"}),
                    self.item("b", 10, context={"window_end": "2026-10-02T19:00:00Z"}),
                    self.item("b", float("nan")), self.item("b", True),
                    self.item("b", 10, context={"absolute_tolerance": -1})]
        for other in variants:
            self.assertEqual(assess_aligned_conflicts([self.item("a", 5), other])["comparable_pair_count"], 0)

    def test_counter_reset_epochs_must_match(self):
        a = self.item("a", 5, context={"measurement_kind": "counter", "counter_epoch": "boot-a"})
        for epoch in (None, "boot-b"):
            b = self.item("b", 10, context={"measurement_kind": "counter", "counter_epoch": epoch})
            self.assertEqual(assess_aligned_conflicts([a, b])["comparable_pair_count"], 0)

    def test_timezone_equivalence_and_explicit_measured_zero(self):
        a = self.item("a", 0)
        b = self.item("b", 5, context={"window_start": "2026-10-02T13:00:00-07:00",
                                      "window_end": "2026-10-02T13:01:00-07:00"})
        self.assertEqual(assess_aligned_conflicts([a, b])["comparable_pair_count"], 1)
        self.assertEqual(assess_aligned_conflicts([a, b])["status"], "disagreements_observed")

    def test_same_source_is_not_a_cross_source_comparison(self):
        result = assess_aligned_conflicts([self.item("a", 5), self.item("a", 10)])
        self.assertEqual(result["comparable_pair_count"], 0)

    def test_candidate_assessment_preserves_original_confidence(self):
        items = [self.item("a", 5), self.item("b", 10)]
        candidates = correlate_by_entity(items)
        before = copy.deepcopy([c.to_dict() for c in candidates])
        result = build_engineering_assessment(items, candidates, {})
        self.assertEqual(result["candidate_assessments"][0]["conflict_assessment"], "disagreements_observed")
        self.assertEqual(before, [c.to_dict() for c in candidates])

    def test_fabric_adapter_preserves_optional_comparison_context(self):
        context = self.item("a", 1).metadata["comparison_context"]
        report = {"interfaces": [{"device": "dut", "interface": "port", "snapshot_records": [
            {"metric": "occupancy", "value": 1, "comparison_context": context}]}]}
        before = copy.deepcopy(report)
        normalized = normalize_fabric_evidence(report)
        self.assertEqual(normalized[0].metadata["comparison_context"], context)
        self.assertEqual(before, report)


if __name__ == "__main__":
    unittest.main()
