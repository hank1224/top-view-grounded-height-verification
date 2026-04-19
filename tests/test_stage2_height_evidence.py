from __future__ import annotations

import unittest

from helpers import canonical_payload, rotated_payload
from top_view_grounded_height_verification.stage2.fusion import build_evidence
from top_view_grounded_height_verification.stage2.height_evidence import build_height_evidence


class Stage2HeightEvidenceTests(unittest.TestCase):
    def test_vertical_direct_neighbor_supports_vertical_dimensions(self) -> None:
        height = build_height_evidence(build_evidence(canonical_payload()))
        self.assertEqual(height["height_evidence_status"], "constructed")
        self.assertEqual(height["verification_readiness"]["status"], "ready")
        supporting_values = {dimension["value"] for dimension in height["supporting_dimensions"]}
        self.assertIn(".22", supporting_values)
        self.assertIn("2.15", supporting_values)

    def test_horizontal_direct_neighbor_supports_horizontal_dimensions(self) -> None:
        height = build_height_evidence(build_evidence(rotated_payload()))
        supporting_by_slot = {
            (dimension["belongs_to_slot"], dimension["value"])
            for dimension in height["supporting_dimensions"]
        }
        self.assertIn(("upper_right", "2.15"), supporting_by_slot)
        self.assertEqual(height["z_orientation_by_slot"]["upper_right"], "horizontal")

    def test_top_view_dimensions_are_ruled_out(self) -> None:
        height = build_height_evidence(build_evidence(canonical_payload()))
        ruled_out_top_values = {
            dimension["value"]
            for dimension in height["ruled_out_dimensions"]
            if dimension["belongs_to_slot"] == "upper_left"
        }
        self.assertEqual(ruled_out_top_values, {"4.86", "3.55"})

    def test_diagonal_view_inherits_grounded_neighbor_orientation(self) -> None:
        height = build_height_evidence(build_evidence(canonical_payload()))
        self.assertEqual(height["z_orientation_by_slot"]["lower_right"], "vertical")
        supporting = [
            dimension
            for dimension in height["supporting_dimensions"]
            if dimension["belongs_to_slot"] == "lower_right" and dimension["value"] == "2.15"
        ]
        self.assertEqual(supporting[0]["grounding_type"], "propagated_from_non_top_view")
        self.assertEqual(supporting[0]["propagated_from_slot"], "lower_left")

    def test_orientation_mismatch_is_ruled_out(self) -> None:
        height = build_height_evidence(build_evidence(canonical_payload()))
        ruled_out_values = {dimension["value"] for dimension in height["ruled_out_dimensions"]}
        self.assertIn("5.3", ruled_out_values)
        self.assertIn("2", ruled_out_values)

    def test_invalid_dimension_becomes_unresolved_and_not_ready(self) -> None:
        payload = canonical_payload()
        payload["dimension_extraction"]["views"][1]["dimensions"][0]["value"] = "bad"
        payload["dimension_extraction"]["views"][1]["dimensions"][0]["numeric_value"] = None
        height = build_height_evidence(build_evidence(payload))
        self.assertEqual(height["height_evidence_status"], "constructed")
        self.assertEqual(height["verification_readiness"]["status"], "not_ready")
        self.assertEqual(height["unresolved_dimensions"][0]["rule"], "dimension_local_evidence_invalid")

    def test_no_supporting_dimensions_is_insufficient(self) -> None:
        payload = canonical_payload()
        for view in payload["dimension_extraction"]["views"]:
            if view["slot"] == "lower_left":
                for dimension in view["dimensions"]:
                    dimension["orientation"] = "horizontal"
            if view["slot"] == "lower_right":
                for dimension in view["dimensions"]:
                    dimension["orientation"] = "horizontal"
        height = build_height_evidence(build_evidence(payload))
        self.assertEqual(height["height_evidence_status"], "insufficient")
        self.assertNotEqual(height["verification_readiness"]["status"], "ready")
        self.assertNotEqual(height["height_evidence_status"], "rejected")


if __name__ == "__main__":
    unittest.main()

