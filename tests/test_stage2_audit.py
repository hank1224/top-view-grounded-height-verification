from __future__ import annotations

import copy
import unittest

from helpers import canonical_payload
from top_view_grounded_height_verification.stage2.audit import build_evidence_audit_report
from top_view_grounded_height_verification.stage2.fusion import build_evidence


class Stage2AuditTests(unittest.TestCase):
    def test_no_ground_truth_reports_not_available(self) -> None:
        evidence = build_evidence(canonical_payload())
        audit = build_evidence_audit_report(evidence, None)
        self.assertEqual(audit["audit_status"], "not_available")

    def test_perfect_ground_truth_metrics(self) -> None:
        payload = canonical_payload()
        evidence = build_evidence(payload)
        audit = build_evidence_audit_report(evidence, payload["ground_truth"])
        self.assertEqual(audit["audit_status"], "reported")
        self.assertTrue(audit["layout_consistent"])
        self.assertTrue(audit["layout_correct"])
        self.assertTrue(audit["top_view_correct"])
        self.assertEqual(audit["ocr_value_metrics"]["precision"], 1.0)
        self.assertEqual(audit["ocr_value_metrics"]["recall"], 1.0)
        self.assertEqual(audit["ocr_value_metrics"]["f1"], 1.0)
        self.assertEqual(audit["orientation_accuracy"], 1.0)
        self.assertEqual(audit["slot_assignment_accuracy"], 1.0)

    def test_extra_and_missing_ocr_values_are_reported(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["views"][2]["dimensions"][0]["value"] = "9.99"
        payload["dimension_extraction"]["views"][2]["dimensions"][0]["numeric_value"] = 9.99
        evidence = build_evidence(payload)
        audit = build_evidence_audit_report(evidence, payload["ground_truth"])
        self.assertIn(9.99, audit["ocr_value_metrics"]["false_positive_values"])
        self.assertIn(2.15, audit["ocr_value_metrics"]["missing_gt_values"])
        self.assertLess(audit["ocr_value_metrics"]["f1"], 1.0)

    def test_top_view_error_is_reported_without_mutating_evidence(self) -> None:
        payload = canonical_payload()
        payload["top_view_detection"]["top_view_slot"] = "lower_left"
        evidence = build_evidence(payload)
        original = copy.deepcopy(evidence)
        audit = build_evidence_audit_report(evidence, payload["ground_truth"])
        self.assertFalse(audit["top_view_correct"])
        self.assertEqual(evidence, original)

    def test_orientation_and_slot_accuracy_drop(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["views"][2]["dimensions"][0]["orientation"] = "horizontal"
        payload["dimension_extraction"]["views"][1]["dimensions"][1]["belongs_to_slot"] = "lower_right"
        evidence = build_evidence(payload)
        audit = build_evidence_audit_report(evidence, payload["ground_truth"])
        self.assertLess(audit["orientation_accuracy"], 1.0)
        self.assertLess(audit["slot_assignment_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()

