from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from helpers import canonical_payload, set_height_answer
from top_view_grounded_height_verification.pipeline import run_bundle
from top_view_grounded_height_verification.reporting import build_report


class ReportingTests(unittest.TestCase):
    def test_build_report_writes_data_first_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_dir = tmp_path / "bundle"
            bundle_dir.mkdir()
            payload = set_height_answer(canonical_payload(), 5.3)
            (bundle_dir / "evidence_by_image_id.json").write_text(
                json.dumps({payload["image_id"]: payload}),
                encoding="utf-8",
            )

            verification_dir = tmp_path / "verification"
            run_dir = run_bundle(bundle_dir, output_dir=verification_dir, run_name="unit-openai")
            output_dir = tmp_path / "reports"
            artifact_paths = build_report([run_dir], output_dir=output_dir, report_name="unit-report")

            manifest_path = output_dir / "unit-report-manifest.md"
            analysis_path = output_dir / "unit-report-analysis.json"
            notable_path = output_dir / "unit-report-notable_cases.csv"

            self.assertEqual(artifact_paths["manifest_md"], manifest_path)
            self.assertTrue(manifest_path.exists())
            self.assertTrue(analysis_path.exists())
            self.assertTrue(notable_path.exists())
            self.assertFalse((output_dir / "unit-report-report.md").exists())

            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            self.assertEqual(analysis["schema_version"], "tvghv-report-analysis-v1.0")
            self.assertIn("manifest_md", analysis["artifact_paths"])
            self.assertNotIn("report_md", analysis["artifact_paths"])

            manifest = manifest_path.read_text(encoding="utf-8")
            blocked_text = (
                "Hu" + "man Report",
                "Suggested Claims",
                "Recommended Caveats",
                "Interpretation",
                "top-view incorrect",
            )
            for text in blocked_text:
                self.assertNotIn(text, manifest)

            with notable_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)
            self.assertIn("top_view_correct", rows[0])
            self.assertNotIn("Audit note", rows[0])


if __name__ == "__main__":
    unittest.main()
