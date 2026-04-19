from __future__ import annotations

import unittest

from top_view_grounded_height_verification.common.io_utils import ROOT, read_json


VALUE_VARIANTS = {"canonical-values", "rotated-values"}
TASKS = ("direct_extraction", "dimension_extraction", "top_view_detection")


class DatasetIntegrityTests(unittest.TestCase):
    def test_manifest_is_value_only_shape_class_dataset(self) -> None:
        manifest = read_json(ROOT / "data" / "package_drawings" / "image_manifest.json")
        images = manifest["images"]
        self.assertEqual(manifest["image_count"], 30)
        self.assertEqual(len(images), 30)
        self.assertEqual({image["variant_slug"] for image in images}, VALUE_VARIANTS)
        self.assertEqual(len({image["package_slug"] for image in images}), 15)
        self.assertEqual(
            {image["shape_class"] for image in images},
            {"sot_like_smd", "tabbed_power_smd", "two_terminal_diode_smd"},
        )
        for image in images:
            self.assertNotIn("source_image_path", image)
            self.assertTrue((ROOT / image["image_path"]).exists(), image["image_path"])

    def test_task_cases_are_aligned_and_shape_classed(self) -> None:
        image_id_sets: list[set[str]] = []
        for task_name in TASKS:
            payload = read_json(ROOT / "data" / "tasks" / task_name / "cases.json")
            cases = payload["cases"]
            self.assertEqual(payload["case_count"], 30)
            self.assertEqual(len(cases), 30)
            self.assertEqual({case["variant_slug"] for case in cases}, VALUE_VARIANTS)
            self.assertTrue(all(case.get("shape_class") for case in cases))
            self.assertFalse(any("source_image_path" in case for case in cases))
            image_id_sets.append({case["image_id"] for case in cases})
        self.assertEqual(image_id_sets[0], image_id_sets[1])
        self.assertEqual(image_id_sets[0], image_id_sets[2])

    def test_ground_truth_matches_cases(self) -> None:
        expected_group_counts = {
            "direct_extraction": 15,
            "dimension_extraction": 30,
            "top_view_detection": 30,
        }
        for task_name, expected_count in expected_group_counts.items():
            cases_payload = read_json(ROOT / "data" / "tasks" / task_name / "cases.json")
            gt_payload = read_json(ROOT / "data" / "tasks" / task_name / "ground_truth.json")
            case_answer_keys = {case["answer_key"] for case in cases_payload["cases"]}
            groups = gt_payload["answer_groups"]
            self.assertEqual(len(groups), expected_count)
            self.assertTrue(all(group.get("shape_class") for group in groups))
            self.assertFalse(any("source_image_path" in group for group in groups))
            group_answer_keys = {group["answer_key"] for group in groups}
            self.assertTrue(case_answer_keys <= group_answer_keys)


if __name__ == "__main__":
    unittest.main()
