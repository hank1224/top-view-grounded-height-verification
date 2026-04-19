from __future__ import annotations

import copy
import unittest

from helpers import canonical_payload, set_height_answer
from top_view_grounded_height_verification.stage2.fusion import build_evidence
from top_view_grounded_height_verification.stage2.height_evidence import build_height_evidence
from top_view_grounded_height_verification.stage3.height_screening import screen_height_answer


def ready_height_result() -> dict:
    return build_height_evidence(build_evidence(canonical_payload()))


class Stage3HeightScreeningTests(unittest.TestCase):
    def test_correct_height_is_supported(self) -> None:
        result = screen_height_answer(canonical_payload()["direct_extraction"], ready_height_result())
        self.assertEqual(result["decision"], "supported")
        self.assertEqual(result["derived_height_value"], 2.15)
        self.assertEqual(result["matched_supporting_dimension_values"], ["2.15"])

    def test_ruled_out_nuisance_value_is_contradicted(self) -> None:
        payload = set_height_answer(canonical_payload(), 5.3)
        result = screen_height_answer(payload["direct_extraction"], ready_height_result())
        self.assertEqual(result["decision"], "contradicted")
        self.assertTrue(result["contradicting_dimension_uids"])

    def test_smaller_supporting_value_is_contradicted(self) -> None:
        payload = set_height_answer(canonical_payload(), 0.22)
        result = screen_height_answer(payload["direct_extraction"], ready_height_result())
        self.assertEqual(result["decision"], "contradicted")
        self.assertEqual(result["rejecting_evidence"][0]["rule"], "model_value_is_supporting_dimension_but_not_maximum")

    def test_missing_or_non_numeric_model_value_is_insufficient(self) -> None:
        payload = set_height_answer(canonical_payload(), None)
        result = screen_height_answer(payload["direct_extraction"], ready_height_result())
        self.assertEqual(result["decision"], "insufficient_evidence")
        self.assertTrue(any("not numeric" in reason for reason in result["failure_reasons"]))

    def test_model_value_not_in_ocr_evidence_is_insufficient(self) -> None:
        payload = set_height_answer(canonical_payload(), 9.99)
        result = screen_height_answer(payload["direct_extraction"], ready_height_result())
        self.assertEqual(result["decision"], "insufficient_evidence")
        self.assertIn("model_value_not_found_in_ocr_dimension_values", result["failure_reasons"])

    def test_not_ready_height_evidence_is_insufficient(self) -> None:
        height = copy.deepcopy(ready_height_result())
        height["verification_readiness"] = {"status": "not_ready", "reasons": ["unit_comparability_unknown"]}
        result = screen_height_answer(canonical_payload()["direct_extraction"], height)
        self.assertEqual(result["decision"], "insufficient_evidence")
        self.assertIn("verification_not_ready", result["failure_reasons"])


if __name__ == "__main__":
    unittest.main()

