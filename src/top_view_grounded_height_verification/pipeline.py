from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from top_view_grounded_height_verification.common.io_utils import ROOT, read_json, write_csv, write_json
from top_view_grounded_height_verification.core.numeric import parse_dimension_value, values_equal
from top_view_grounded_height_verification.stage2.audit import build_evidence_audit_report
from top_view_grounded_height_verification.stage2.fusion import build_evidence
from top_view_grounded_height_verification.stage2.height_evidence import build_height_evidence
from top_view_grounded_height_verification.stage3.height_screening import VERIFIED_TARGET, screen_height_answer


class PipelineError(Exception):
    pass


def path_for_record(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("verification-%Y%m%dt%H%M%Sz")


def run_pipeline(input_payload: dict[str, Any]) -> dict[str, Any]:
    evidence = build_evidence(input_payload)
    audit_report = build_evidence_audit_report(
        evidence,
        input_payload.get("ground_truth"),
    )
    height_evidence_result = build_height_evidence(evidence)
    screening_result = screen_height_answer(
        input_payload.get("direct_extraction", {}),
        height_evidence_result,
    )
    return {
        "schema_version": "tvghv-pipeline-result-v1.0",
        "image_id": input_payload.get("image_id"),
        "image_path": input_payload.get("image_path"),
        "package_name": input_payload.get("package_name"),
        "package_slug": input_payload.get("package_slug"),
        "shape_class": input_payload.get("shape_class"),
        "variant_name": input_payload.get("variant_name"),
        "variant_slug": input_payload.get("variant_slug"),
        "input_evidence": input_payload,
        "evidence": evidence,
        "audit_report": audit_report,
        "height_evidence_result": height_evidence_result,
        "screening_result": screening_result,
    }


def load_bundle_cases(input_path: Path) -> dict[str, dict[str, Any]]:
    if input_path.is_file():
        payload = read_json(input_path)
        if isinstance(payload, dict) and "image_id" in payload:
            return {payload["image_id"]: payload}
        if isinstance(payload, dict) and all(isinstance(value, dict) for value in payload.values()):
            return {
                image_id: case
                for image_id, case in payload.items()
                if isinstance(image_id, str) and isinstance(case, dict)
            }
        raise PipelineError(f"Unsupported input JSON shape: {input_path}")

    if not input_path.is_dir():
        raise PipelineError(f"Input path does not exist: {input_path}")

    evidence_by_image_id = input_path / "evidence_by_image_id.json"
    if evidence_by_image_id.exists():
        return load_bundle_cases(evidence_by_image_id)

    cases_dir = input_path / "cases"
    if not cases_dir.exists():
        raise PipelineError(f"Input directory must contain evidence_by_image_id.json or cases/: {input_path}")
    cases: dict[str, dict[str, Any]] = {}
    for case_path in sorted(cases_dir.glob("*.json")):
        payload = read_json(case_path)
        if not isinstance(payload, dict) or not isinstance(payload.get("image_id"), str):
            raise PipelineError(f"Case file has unsupported shape: {case_path}")
        cases[payload["image_id"]] = payload
    if not cases:
        raise PipelineError(f"No case JSON files found in: {cases_dir}")
    return cases


def _safe_ratio(numerator: int, denominator: int, metric_name: str, notes: list[str]) -> float | None:
    if denominator == 0:
        notes.append(f"{metric_name} denominator is 0")
        return None
    return numerator / denominator


def _raw_height_gt(result: dict[str, Any]) -> float | None:
    ground_truth = result.get("input_evidence", {}).get("ground_truth")
    if not isinstance(ground_truth, dict):
        return None
    direct_gt = ground_truth.get("direct_ground_truth")
    if not isinstance(direct_gt, dict):
        return None
    return parse_dimension_value(direct_gt.get(VERIFIED_TARGET))


def _raw_model_height(result: dict[str, Any]) -> float | None:
    direct = result.get("input_evidence", {}).get("direct_extraction")
    if not isinstance(direct, dict):
        return None
    target = direct.get("targets", {}).get(VERIFIED_TARGET)
    if not isinstance(target, dict):
        return None
    return parse_dimension_value(target.get("value"))


def _source_provider(result: dict[str, Any]) -> str | None:
    sources = result.get("input_evidence", {}).get("evidence_sources")
    if not isinstance(sources, dict):
        return None
    direct_source = sources.get("direct_extraction")
    if not isinstance(direct_source, dict):
        return None
    provider = direct_source.get("provider")
    return provider if isinstance(provider, str) else None


def _case_summary_row(result: dict[str, Any]) -> dict[str, Any]:
    screening = result.get("screening_result", {})
    height = result.get("height_evidence_result", {})
    readiness = height.get("verification_readiness", {}) if isinstance(height, dict) else {}
    model_value = _raw_model_height(result)
    gt_value = _raw_height_gt(result)
    raw_height_correct = (
        values_equal(model_value, gt_value)
        if model_value is not None and gt_value is not None
        else None
    )
    return {
        "image_id": result.get("image_id"),
        "package_slug": result.get("package_slug"),
        "shape_class": result.get("shape_class"),
        "variant_slug": result.get("variant_slug"),
        "provider": _source_provider(result),
        "decision": screening.get("decision"),
        "height_evidence_status": height.get("height_evidence_status"),
        "verification_readiness": readiness.get("status") if isinstance(readiness, dict) else None,
        "model_value": screening.get("model_value"),
        "derived_height_value": screening.get("derived_height_value"),
        "ground_truth_height": gt_value,
        "raw_height_correct": raw_height_correct,
        "failure_reasons": ";".join(screening.get("failure_reasons", [])),
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    notes: list[str] = []
    decisions = ("supported", "contradicted", "insufficient_evidence")
    counts = {decision: 0 for decision in decisions}
    evaluated_results: list[dict[str, Any]] = []
    gt_correct: list[dict[str, Any]] = []
    gt_wrong: list[dict[str, Any]] = []

    for result in results:
        decision = result.get("screening_result", {}).get("decision")
        if decision in counts:
            counts[decision] += 1
        gt_value = _raw_height_gt(result)
        model_value = _raw_model_height(result)
        if gt_value is None:
            continue
        evaluated_results.append(result)
        if model_value is not None and values_equal(model_value, gt_value):
            gt_correct.append(result)
        else:
            gt_wrong.append(result)

    def count_decision(rows: list[dict[str, Any]], decision: str) -> int:
        return sum(1 for row in rows if row.get("screening_result", {}).get("decision") == decision)

    supported_and_gt_correct = count_decision(gt_correct, "supported")
    supported_and_gt_wrong = count_decision(gt_wrong, "supported")
    contradicted_and_gt_wrong = count_decision(gt_wrong, "contradicted")
    insufficient_and_gt_wrong = count_decision(gt_wrong, "insufficient_evidence")
    raw_direct_height_correct_count = len(gt_correct)
    evaluated_case_count = len(evaluated_results)
    gt_wrong_count = len(gt_wrong)

    stacked = {
        "gt_correct": {
            decision: count_decision(gt_correct, decision)
            for decision in decisions
        },
        "gt_wrong": {
            decision: count_decision(gt_wrong, decision)
            for decision in decisions
        },
    }

    supported_count = counts["supported"]
    return {
        "schema_version": "tvghv-verification-summary-v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(results),
        "evaluated_case_count": evaluated_case_count,
        "supported_count": counts["supported"],
        "contradicted_count": counts["contradicted"],
        "insufficient_evidence_count": counts["insufficient_evidence"],
        "raw_direct_height_correct_count": raw_direct_height_correct_count,
        "gt_wrong_count": gt_wrong_count,
        "risk_screening_metrics": {
            "raw_height_accuracy": _safe_ratio(
                raw_direct_height_correct_count,
                evaluated_case_count,
                "raw_height_accuracy",
                notes,
            ),
            "supported_precision": _safe_ratio(
                supported_and_gt_correct,
                supported_count,
                "supported_precision",
                notes,
            ),
            "unsafe_support_rate": _safe_ratio(
                supported_and_gt_wrong,
                gt_wrong_count,
                "unsafe_support_rate",
                notes,
            ),
            "coverage": _safe_ratio(
                supported_count,
                evaluated_case_count,
                "coverage",
                notes,
            ),
            "wrong_answer_interception_rate": _safe_ratio(
                contradicted_and_gt_wrong + insufficient_and_gt_wrong,
                gt_wrong_count,
                "wrong_answer_interception_rate",
                notes,
            ),
        },
        "screening_decision_by_gt_correctness": stacked,
        "notes": notes,
    }


def run_bundle(
    input_path: Path,
    *,
    output_dir: Path,
    run_name: str | None = None,
) -> Path:
    cases = load_bundle_cases(input_path)
    actual_run_name = run_name or now_stamp()
    run_dir = output_dir / actual_run_name
    cases_dir = run_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for image_id, payload in sorted(cases.items()):
        result = run_pipeline(payload)
        results.append(result)
        write_json(cases_dir / f"{image_id}.json", result)

    summary = build_summary(results)
    summary.update(
        {
            "run_name": actual_run_name,
            "input_path": path_for_record(input_path),
            "output_dir": path_for_record(run_dir),
        }
    )
    write_json(run_dir / "summary.json", summary)
    write_csv(run_dir / "summary.csv", [_case_summary_row(result) for result in results])
    print(f"Wrote verification results: {path_for_record(run_dir)}")
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Stage 2/3 height answer screening over evidence bundles.")
    parser.add_argument("--input", type=Path, required=True, help="Evidence bundle directory or JSON file.")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "verification_results")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_bundle(args.input, output_dir=args.output_dir, run_name=args.run_name)
    except (PipelineError, OSError, ValueError) as exc:
        print(f"Verification pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0
