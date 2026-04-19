from __future__ import annotations

import copy
import unittest

from helpers import canonical_payload
from top_view_grounded_height_verification.stage2.fusion import build_evidence


class Stage2FusionTests(unittest.TestCase):
    def test_valid_payload_builds_internal_evidence(self) -> None:
        evidence = build_evidence(canonical_payload())
        self.assertEqual(evidence["status"], "valid")
        self.assertEqual(evidence["top_view_slot"], "upper_left")
        self.assertEqual(evidence["occupied_slots"], ["upper_left", "lower_left", "lower_right"])
        self.assertEqual([dimension["dimension_uid"] for dimension in evidence["dimensions"][:2]], ["upper_left_d1", "upper_left_d2"])

    def test_layout_mismatch_invalidates_evidence(self) -> None:
        payload = canonical_payload()
        payload["top_view_detection"]["layout"]["upper_right"] = 1
        payload["top_view_detection"]["layout"]["lower_right"] = 0
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "invalid")
        self.assertIn("dimension_extraction.layout does not match top_view_detection.layout", evidence["failure_reasons"])

    def test_invalid_l_shape_invalidates_evidence(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["layout"]["upper_right"] = 1
        payload["top_view_detection"]["layout"]["upper_right"] = 1
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "invalid")
        self.assertTrue(any("exactly three occupied" in reason for reason in evidence["failure_reasons"]))

    def test_top_view_slot_must_be_occupied(self) -> None:
        payload = canonical_payload()
        payload["top_view_detection"]["top_view_slot"] = "upper_right"
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "invalid")
        self.assertIn("top_view_detection.top_view_slot must be one of the occupied slots", evidence["failure_reasons"])

    def test_duplicate_or_missing_view_slot_invalidates_evidence(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["views"][2]["slot"] = "lower_left"
        for dimension in payload["dimension_extraction"]["views"][2]["dimensions"]:
            dimension["belongs_to_slot"] = "lower_left"
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "invalid")
        self.assertTrue(any("appears more than once" in reason for reason in evidence["failure_reasons"]))
        self.assertTrue(any("missing occupied slots" in reason for reason in evidence["failure_reasons"]))

    def test_dimension_slot_mismatch_is_local_invalid_dimension(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["views"][1]["dimensions"][0]["belongs_to_slot"] = "lower_right"
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "valid")
        invalid = [dimension for dimension in evidence["dimensions"] if not dimension["valid"]]
        self.assertEqual(len(invalid), 1)
        self.assertIn("belongs_to_slot_mismatch", invalid[0]["invalid_reasons"])

    def test_invalid_dimension_value_is_local_invalid_dimension(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["views"][1]["dimensions"][0]["value"] = "not-a-number"
        payload["dimension_extraction"]["views"][1]["dimensions"][0]["numeric_value"] = None
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "valid")
        invalid = [dimension for dimension in evidence["dimensions"] if not dimension["valid"]]
        self.assertEqual(len(invalid), 1)
        self.assertIn("dimension_value_not_numeric", invalid[0]["invalid_reasons"])

    def test_bbox_invalid_does_not_discard_ocr_layout_evidence(self) -> None:
        payload = copy.deepcopy(canonical_payload())
        payload["dimension_extraction"]["schema_valid"] = False
        payload["dimension_extraction"]["bbox_output_valid"] = False
        payload["dimension_extraction"]["validation_errors"] = ["bad bbox"]
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "valid")
        self.assertIn("dimension_extraction_bbox_output_invalid", evidence["warnings"])

    def test_top_view_bbox_invalid_does_not_discard_topology_evidence(self) -> None:
        payload = copy.deepcopy(canonical_payload())
        payload["top_view_detection"]["schema_valid"] = False
        payload["top_view_detection"]["topology_schema_valid"] = True
        payload["top_view_detection"]["bbox_output_valid"] = False
        payload["top_view_detection"]["validation_errors"] = ["bad bbox"]
        payload["top_view_detection"]["bbox_validation_errors"] = ["bad bbox"]
        evidence = build_evidence(payload)
        self.assertEqual(evidence["status"], "valid")
        self.assertIn("top_view_detection_schema_invalid_but_topology_valid", evidence["warnings"])
        self.assertIn("top_view_detection_bbox_output_invalid", evidence["warnings"])


if __name__ == "__main__":
    unittest.main()
