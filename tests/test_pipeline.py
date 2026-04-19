from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from helpers import canonical_payload, set_height_answer
from top_view_grounded_height_verification.common.io_utils import ROOT
from top_view_grounded_height_verification.pipeline import build_summary, run_bundle, run_pipeline


class PipelineTests(unittest.TestCase):
    def test_run_pipeline_single_case_schema(self) -> None:
        result = run_pipeline(canonical_payload())
        self.assertEqual(result["schema_version"], "tvghv-pipeline-result-v1.0")
        self.assertEqual(result["shape_class"], "unit_shape")
        self.assertEqual(result["height_evidence_result"]["height_evidence_status"], "constructed")
        self.assertEqual(result["screening_result"]["decision"], "supported")
        self.assertEqual(result["audit_report"]["audit_status"], "reported")

    def test_summary_counts_and_metrics(self) -> None:
        supported = run_pipeline(canonical_payload())
        contradicted = run_pipeline(set_height_answer(canonical_payload(), 5.3))
        insufficient = run_pipeline(set_height_answer(canonical_payload(), 9.99))
        summary = build_summary([supported, contradicted, insufficient])
        self.assertEqual(summary["supported_count"], 1)
        self.assertEqual(summary["contradicted_count"], 1)
        self.assertEqual(summary["insufficient_evidence_count"], 1)
        self.assertEqual(summary["raw_direct_height_correct_count"], 1)
        self.assertEqual(summary["risk_screening_metrics"]["raw_height_accuracy"], 1 / 3)
        self.assertEqual(summary["risk_screening_metrics"]["supported_precision"], 1.0)
        self.assertEqual(summary["risk_screening_metrics"]["wrong_answer_interception_rate"], 1.0)
        self.assertEqual(summary["screening_decision_by_gt_correctness"]["gt_wrong"]["contradicted"], 1)
        self.assertEqual(summary["screening_decision_by_gt_correctness"]["gt_wrong"]["insufficient_evidence"], 1)

    def test_summary_null_denominators(self) -> None:
        result = run_pipeline(canonical_payload())
        result["input_evidence"]["ground_truth"] = None
        summary = build_summary([result])
        self.assertIsNone(summary["risk_screening_metrics"]["raw_height_accuracy"])
        self.assertTrue(summary["notes"])

    def test_run_bundle_writes_case_and_summary_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_dir = tmp_path / "bundle"
            bundle_dir.mkdir()
            payload = canonical_payload()
            (bundle_dir / "evidence_by_image_id.json").write_text(
                json.dumps({payload["image_id"]: payload}),
                encoding="utf-8",
            )
            output_dir = tmp_path / "verification"
            run_dir = run_bundle(bundle_dir, output_dir=output_dir, run_name="unit-run")
            self.assertTrue((run_dir / "cases" / f"{payload['image_id']}.json").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "summary.csv").exists())
            with (run_dir / "summary.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["shape_class"], "unit_shape")

    def test_existing_provider_bundles_smoke(self) -> None:
        bundle_root = ROOT / "outputs" / "evidence_bundles"
        bundle_names = [
            "stage1-full-001-openai",
            "stage1-full-001-gemini",
            "stage1-full-001-anthropic",
        ]
        missing = [name for name in bundle_names if not (bundle_root / name).exists()]
        if missing:
            self.skipTest(f"Stage 1 smoke bundles are not present: {missing}")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for name in bundle_names:
                run_dir = run_bundle(bundle_root / name, output_dir=output_dir, run_name=name)
                summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    summary["supported_count"]
                    + summary["contradicted_count"]
                    + summary["insufficient_evidence_count"],
                    summary["case_count"],
                )


if __name__ == "__main__":
    unittest.main()
