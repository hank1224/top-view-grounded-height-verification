from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from top_view_grounded_height_verification.common.io_utils import ROOT, read_json, write_csv, write_json, write_text
from top_view_grounded_height_verification.core.numeric import parse_dimension_value, values_equal
from top_view_grounded_height_verification.stage3.height_screening import VERIFIED_TARGET


class ReportingError(Exception):
    pass


DECISIONS = ("supported", "contradicted", "insufficient_evidence")


def path_for_record(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def num(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(num(item) for item in row) + " |")
    return "\n".join(lines)


def provider_from_run_name(run_dir: Path) -> str:
    name = run_dir.name
    for provider in ("openai", "gemini", "anthropic"):
        if name.endswith(f"-{provider}") or provider in name:
            return provider
    return name


def load_run(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    cases_dir = run_dir / "cases"
    if not summary_path.exists():
        raise ReportingError(f"Missing summary.json: {run_dir}")
    if not cases_dir.exists():
        raise ReportingError(f"Missing cases directory: {run_dir}")
    summary = read_json(summary_path)
    cases = []
    for case_path in sorted(cases_dir.glob("*.json")):
        case = read_json(case_path)
        if not isinstance(case, dict):
            raise ReportingError(f"Invalid case JSON: {case_path}")
        cases.append(case)
    return {
        "run_dir": run_dir,
        "run_name": summary.get("run_name", run_dir.name),
        "provider": provider_from_run_name(run_dir),
        "summary": summary,
        "cases": cases,
    }


def raw_gt_height(case: dict[str, Any]) -> float | None:
    ground_truth = case.get("input_evidence", {}).get("ground_truth")
    if not isinstance(ground_truth, dict):
        return None
    direct_gt = ground_truth.get("direct_ground_truth")
    if not isinstance(direct_gt, dict):
        return None
    return parse_dimension_value(direct_gt.get(VERIFIED_TARGET))


def raw_model_height(case: dict[str, Any]) -> float | None:
    direct = case.get("input_evidence", {}).get("direct_extraction")
    if not isinstance(direct, dict):
        return None
    target = direct.get("targets", {}).get(VERIFIED_TARGET)
    if not isinstance(target, dict):
        return None
    return parse_dimension_value(target.get("value"))


def raw_height_correct(case: dict[str, Any]) -> bool | None:
    model_value = raw_model_height(case)
    gt_value = raw_gt_height(case)
    if model_value is None or gt_value is None:
        return None
    return values_equal(model_value, gt_value)


def case_metric_row(run: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    evidence = case.get("evidence", {})
    audit = case.get("audit_report", {})
    height = case.get("height_evidence_result", {})
    screening = case.get("screening_result", {})
    readiness = height.get("verification_readiness", {}) if isinstance(height, dict) else {}
    ocr_metrics = audit.get("ocr_value_metrics", {}) if isinstance(audit, dict) else {}
    completeness = audit.get("evidence_completeness", {}) if isinstance(audit, dict) else {}
    model_value = raw_model_height(case)
    gt_value = raw_gt_height(case)
    correct = raw_height_correct(case)
    return {
        "provider": run["provider"],
        "run_name": run["run_name"],
        "image_id": case.get("image_id"),
        "package_slug": case.get("package_slug"),
        "shape_class": case.get("shape_class"),
        "variant_slug": case.get("variant_slug"),
        "decision": screening.get("decision"),
        "raw_height_correct": correct,
        "model_value": model_value,
        "derived_height_value": screening.get("derived_height_value"),
        "ground_truth_height": gt_value,
        "evidence_status": evidence.get("status"),
        "height_evidence_status": height.get("height_evidence_status"),
        "verification_readiness": readiness.get("status") if isinstance(readiness, dict) else None,
        "readiness_reasons": ";".join(readiness.get("reasons", [])) if isinstance(readiness, dict) else "",
        "top_view_slot": evidence.get("top_view_slot"),
        "top_view_correct": audit.get("top_view_correct") if isinstance(audit, dict) else None,
        "layout_correct": audit.get("layout_correct") if isinstance(audit, dict) else None,
        "layout_consistent": audit.get("layout_consistent") if isinstance(audit, dict) else None,
        "ocr_precision": ocr_metrics.get("precision"),
        "ocr_recall": ocr_metrics.get("recall"),
        "ocr_f1": ocr_metrics.get("f1"),
        "ocr_false_positive_values": json.dumps(ocr_metrics.get("false_positive_values", []), ensure_ascii=False),
        "ocr_missing_gt_values": json.dumps(ocr_metrics.get("missing_gt_values", []), ensure_ascii=False),
        "orientation_accuracy": audit.get("orientation_accuracy") if isinstance(audit, dict) else None,
        "slot_assignment_accuracy": audit.get("slot_assignment_accuracy") if isinstance(audit, dict) else None,
        "expected_dimension_count": completeness.get("expected_dimension_count"),
        "predicted_dimension_count": completeness.get("predicted_dimension_count"),
        "supporting_dimension_count": len(height.get("supporting_dimensions", [])),
        "ruled_out_dimension_count": len(height.get("ruled_out_dimensions", [])),
        "unresolved_dimension_count": len(height.get("unresolved_dimensions", [])),
        "z_orientation_by_slot": json.dumps(height.get("z_orientation_by_slot", {}), ensure_ascii=False),
        "screening_failure_reasons": ";".join(screening.get("failure_reasons", [])),
        "height_failure_reasons": ";".join(height.get("failure_reasons", [])),
        "evidence_failure_reasons": ";".join(evidence.get("failure_reasons", [])),
        "evidence_warnings": ";".join(evidence.get("warnings", [])),
    }


def audit_metric_row(run: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    row = case_metric_row(run, case)
    return {
        key: row[key]
        for key in (
            "provider",
            "run_name",
            "image_id",
            "package_slug",
            "variant_slug",
            "audit_status",
        )
        if key in row
    } | {
        "provider": run["provider"],
        "run_name": run["run_name"],
        "image_id": case.get("image_id"),
        "package_slug": case.get("package_slug"),
        "shape_class": row["shape_class"],
        "variant_slug": case.get("variant_slug"),
        "audit_status": case.get("audit_report", {}).get("audit_status"),
        "layout_consistent": row["layout_consistent"],
        "layout_correct": row["layout_correct"],
        "top_view_correct": row["top_view_correct"],
        "ocr_precision": row["ocr_precision"],
        "ocr_recall": row["ocr_recall"],
        "ocr_f1": row["ocr_f1"],
        "orientation_accuracy": row["orientation_accuracy"],
        "slot_assignment_accuracy": row["slot_assignment_accuracy"],
        "expected_dimension_count": row["expected_dimension_count"],
        "predicted_dimension_count": row["predicted_dimension_count"],
        "ocr_false_positive_values": row["ocr_false_positive_values"],
        "ocr_missing_gt_values": row["ocr_missing_gt_values"],
        "audit_notes": ";".join(case.get("audit_report", {}).get("notes", [])),
    }


def dimension_bucket_rows(run: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    height = case.get("height_evidence_result", {})
    for bucket in ("supporting_dimensions", "ruled_out_dimensions", "unresolved_dimensions"):
        label = bucket.replace("_dimensions", "")
        for dimension in height.get(bucket, []):
            rows.append(
                {
                    "provider": run["provider"],
                    "run_name": run["run_name"],
                    "image_id": case.get("image_id"),
                    "package_slug": case.get("package_slug"),
                    "shape_class": case.get("shape_class"),
                    "variant_slug": case.get("variant_slug"),
                    "bucket": label,
                    "dimension_uid": dimension.get("dimension_uid"),
                    "value": dimension.get("value"),
                    "numeric_value": dimension.get("numeric_value"),
                    "belongs_to_slot": dimension.get("belongs_to_slot"),
                    "dimension_line_orientation": dimension.get("dimension_line_orientation"),
                    "z_axis_orientation_for_slot": dimension.get("z_axis_orientation_for_slot"),
                    "grounding_type": dimension.get("grounding_type"),
                    "propagated_from_slot": dimension.get("propagated_from_slot"),
                    "rule": dimension.get("rule"),
                    "valid": dimension.get("valid"),
                    "invalid_reasons": ";".join(dimension.get("invalid_reasons", [])),
                    "evidence_chain": json.dumps(dimension.get("evidence_chain", []), ensure_ascii=False),
                }
            )
    return rows


def provider_metric_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        summary = run["summary"]
        metrics = summary.get("risk_screening_metrics", {})
        rows.append(
            {
                "provider": run["provider"],
                "run_name": run["run_name"],
                "case_count": summary.get("case_count"),
                "evaluated_case_count": summary.get("evaluated_case_count"),
                "raw_direct_height_correct_count": summary.get("raw_direct_height_correct_count"),
                "gt_wrong_count": summary.get("gt_wrong_count"),
                "supported_count": summary.get("supported_count"),
                "contradicted_count": summary.get("contradicted_count"),
                "insufficient_evidence_count": summary.get("insufficient_evidence_count"),
                "raw_height_accuracy": metrics.get("raw_height_accuracy"),
                "supported_precision": metrics.get("supported_precision"),
                "unsafe_support_rate": metrics.get("unsafe_support_rate"),
                "coverage": metrics.get("coverage"),
                "wrong_answer_interception_rate": metrics.get("wrong_answer_interception_rate"),
            }
        )
    return rows


def metric_row_for_group(group_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = aggregate_metrics(rows)
    package_slugs = sorted({row["package_slug"] for row in rows})
    return {
        "group": group_name,
        "package_count": len(package_slugs),
        "package_slugs": ";".join(package_slugs),
        "case_count": aggregate["case_count"],
        "evaluated_case_count": aggregate["evaluated_case_count"],
        "raw_direct_height_correct_count": aggregate["raw_direct_height_correct_count"],
        "gt_wrong_count": aggregate["gt_wrong_count"],
        "supported_count": aggregate["supported_count"],
        "contradicted_count": aggregate["contradicted_count"],
        "insufficient_evidence_count": aggregate["insufficient_evidence_count"],
        "raw_height_accuracy": aggregate["raw_height_accuracy"],
        "supported_precision": aggregate["supported_precision"],
        "unsafe_support_rate": aggregate["unsafe_support_rate"],
        "coverage": aggregate["coverage"],
        "wrong_answer_interception_rate": aggregate["wrong_answer_interception_rate"],
    }


def shape_class_metric_rows(case_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows:
        grouped[row["shape_class"] or "unknown"].append(row)
    return [
        metric_row_for_group(shape_class, rows)
        for shape_class, rows in sorted(grouped.items())
    ]


def shape_class_provider_metric_rows(case_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows:
        grouped[(row["shape_class"] or "unknown", row["provider"])].append(row)
    output: list[dict[str, Any]] = []
    for (shape_class, provider), rows in sorted(grouped.items()):
        metric = metric_row_for_group(shape_class, rows)
        metric["provider"] = provider
        output.append(metric)
    return output


def shape_class_macro_metrics(shape_class_rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric in (
        "raw_height_accuracy",
        "supported_precision",
        "unsafe_support_rate",
        "coverage",
        "wrong_answer_interception_rate",
    ):
        values = [
            row[metric]
            for row in shape_class_rows
            if isinstance(row.get(metric), (int, float))
        ]
        output[f"shape_class_macro_{metric}"] = safe_ratio(sum(values), len(values))
    return output


def aggregate_metrics(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [row for row in case_rows if row["ground_truth_height"] is not None]
    correct = [row for row in evaluated if row["raw_height_correct"] is True]
    wrong = [row for row in evaluated if row["raw_height_correct"] is False]
    supported = [row for row in case_rows if row["decision"] == "supported"]
    supported_correct = [row for row in supported if row["raw_height_correct"] is True]
    supported_wrong = [row for row in supported if row["raw_height_correct"] is False]
    intercepted_wrong = [
        row
        for row in wrong
        if row["decision"] in {"contradicted", "insufficient_evidence"}
    ]
    decisions = Counter(row["decision"] for row in case_rows)
    return {
        "case_count": len(case_rows),
        "evaluated_case_count": len(evaluated),
        "raw_direct_height_correct_count": len(correct),
        "gt_wrong_count": len(wrong),
        "supported_count": decisions["supported"],
        "contradicted_count": decisions["contradicted"],
        "insufficient_evidence_count": decisions["insufficient_evidence"],
        "unsafe_support_count": len(supported_wrong),
        "raw_height_accuracy": safe_ratio(len(correct), len(evaluated)),
        "supported_precision": safe_ratio(len(supported_correct), len(supported)),
        "unsafe_support_rate": safe_ratio(len(supported_wrong), len(wrong)),
        "coverage": safe_ratio(len(supported), len(evaluated)),
        "wrong_answer_interception_rate": safe_ratio(len(intercepted_wrong), len(wrong)),
        "screening_decision_by_gt_correctness": {
            "gt_correct": {decision: sum(1 for row in correct if row["decision"] == decision) for decision in DECISIONS},
            "gt_wrong": {decision: sum(1 for row in wrong if row["decision"] == decision) for decision in DECISIONS},
        },
    }


def audit_aggregates(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    def bool_rate(key: str) -> float | None:
        values = [row[key] for row in case_rows if isinstance(row.get(key), bool)]
        return safe_ratio(sum(1 for value in values if value), len(values))

    def macro_avg(key: str) -> float | None:
        values = [row[key] for row in case_rows if isinstance(row.get(key), (int, float))]
        return safe_ratio(sum(values), len(values))

    return {
        "layout_consistent_rate": bool_rate("layout_consistent"),
        "layout_correct_rate": bool_rate("layout_correct"),
        "top_view_correct_rate": bool_rate("top_view_correct"),
        "macro_ocr_precision": macro_avg("ocr_precision"),
        "macro_ocr_recall": macro_avg("ocr_recall"),
        "macro_ocr_f1": macro_avg("ocr_f1"),
        "macro_orientation_accuracy": macro_avg("orientation_accuracy"),
        "macro_slot_assignment_accuracy": macro_avg("slot_assignment_accuracy"),
    }


def construction_aggregates(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    constructed = [row for row in case_rows if row["height_evidence_status"] == "constructed"]
    ready = [row for row in case_rows if row["verification_readiness"] == "ready"]
    return {
        "constructed_count": len(constructed),
        "insufficient_construction_count": sum(1 for row in case_rows if row["height_evidence_status"] == "insufficient"),
        "verification_ready_count": len(ready),
        "constructed_rate": safe_ratio(len(constructed), len(case_rows)),
        "verification_ready_rate": safe_ratio(len(ready), len(case_rows)),
        "avg_supporting_dimensions": safe_ratio(sum(row["supporting_dimension_count"] for row in case_rows), len(case_rows)),
        "avg_ruled_out_dimensions": safe_ratio(sum(row["ruled_out_dimension_count"] for row in case_rows), len(case_rows)),
        "avg_unresolved_dimensions": safe_ratio(sum(row["unresolved_dimension_count"] for row in case_rows), len(case_rows)),
    }


def rule_count_rows(dimension_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in dimension_rows:
        counts[(row["provider"], row["bucket"], row["rule"])] += 1
    return [
        {
            "provider": provider,
            "bucket": bucket,
            "rule": rule,
            "count": count,
        }
        for (provider, bucket, rule), count in sorted(counts.items())
    ]


def notable_case_rows(case_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in case_rows:
        category = None
        if row["decision"] == "supported" and row["raw_height_correct"] is False:
            category = "unsafe_support"
        elif row["decision"] in {"contradicted", "insufficient_evidence"} and row["raw_height_correct"] is False:
            category = "wrong_answer_intercepted"
        elif row["decision"] != "supported" and row["raw_height_correct"] is True:
            category = "correct_answer_not_supported"
        if category:
            item = dict(row)
            item["analysis_category"] = category
            rows.append(item)
    return rows


def render_manifest(analysis: dict[str, Any]) -> str:
    created_at = analysis["created_at_utc"]
    source_table = markdown_table(
        ["Provider", "Run Name", "Run Directory"],
        [
            [run["provider"], run["run_name"], run["run_dir"]]
            for run in analysis["source_runs"]
        ],
    )
    artifact_table = markdown_table(
        ["Artifact", "Path"],
        [
            [artifact_name, artifact_path]
            for artifact_name, artifact_path in analysis["artifact_paths"].items()
        ],
    )
    return f"""# Stage 2/3 Height Screening Report Artifacts

Generated at: `{created_at}`

This manifest lists data artifacts generated from Stage 2 Height Evidence Construction and Stage 3 Height Answer Screening verification results.

## Source Runs

{source_table}

## Generated Artifacts

{artifact_table}

## Data Grain

- `provider_metrics_csv`: one row per provider run.
- `shape_class_metrics_csv`: one row per package shape class.
- `shape_class_provider_metrics_csv`: one row per shape class and provider.
- `case_metrics_csv`: one row per provider-case.
- `audit_metrics_csv`: one row per provider-case audit side channel.
- `dimension_buckets_csv`: one row per classified dimension.
- `rule_counts_csv`: one row per provider, bucket, and rule.
- `notable_cases_csv`: one row per provider-case selected by structured category flags.
- `analysis_json`: machine-readable aggregate of the same report artifacts.

## Field Notes

- Audit fields that compare predictions with ground truth are evaluation side channels.
- Audit fields do not modify `height_evidence_result` or `screening_result`.
- `notable_cases_csv` uses structured fields such as `analysis_category`, `top_view_correct`, `ocr_f1`, `screening_failure_reasons`, and `evidence_failure_reasons`.
"""


def build_report(
    run_dirs: list[Path],
    *,
    output_dir: Path,
    report_name: str,
) -> dict[str, Path]:
    runs = [load_run(run_dir) for run_dir in run_dirs]
    output_dir.mkdir(parents=True, exist_ok=True)

    case_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    dimension_rows: list[dict[str, Any]] = []
    for run in runs:
        for case in run["cases"]:
            case_rows.append(case_metric_row(run, case))
            audit_rows.append(audit_metric_row(run, case))
            dimension_rows.extend(dimension_bucket_rows(run, case))

    provider_rows = provider_metric_rows(runs)
    shape_class_rows = shape_class_metric_rows(case_rows)
    shape_class_provider_rows = shape_class_provider_metric_rows(case_rows)
    rule_rows = rule_count_rows(dimension_rows)
    notable_rows = notable_case_rows(case_rows)

    artifact_paths = {
        "manifest_md": output_dir / f"{report_name}-manifest.md",
        "analysis_json": output_dir / f"{report_name}-analysis.json",
        "provider_metrics_csv": output_dir / f"{report_name}-provider_metrics.csv",
        "shape_class_metrics_csv": output_dir / f"{report_name}-shape_class_metrics.csv",
        "shape_class_provider_metrics_csv": output_dir / f"{report_name}-shape_class_provider_metrics.csv",
        "case_metrics_csv": output_dir / f"{report_name}-case_metrics.csv",
        "audit_metrics_csv": output_dir / f"{report_name}-audit_metrics.csv",
        "dimension_buckets_csv": output_dir / f"{report_name}-dimension_buckets.csv",
        "rule_counts_csv": output_dir / f"{report_name}-rule_counts.csv",
        "notable_cases_csv": output_dir / f"{report_name}-notable_cases.csv",
    }

    analysis = {
        "schema_version": "tvghv-report-analysis-v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_runs": [
            {
                "provider": run["provider"],
                "run_name": run["run_name"],
                "run_dir": path_for_record(run["run_dir"]),
            }
            for run in runs
        ],
        "provider_metrics": provider_rows,
        "shape_class_metrics": shape_class_rows,
        "shape_class_provider_metrics": shape_class_provider_rows,
        "shape_class_macro_metrics": shape_class_macro_metrics(shape_class_rows),
        "aggregate_metrics": aggregate_metrics(case_rows),
        "audit_aggregates": audit_aggregates(case_rows),
        "construction_aggregates": construction_aggregates(case_rows),
        "notable_cases": notable_rows,
        "artifact_paths": {
            key: path_for_record(path)
            for key, path in artifact_paths.items()
        },
    }

    write_csv(artifact_paths["provider_metrics_csv"], provider_rows)
    write_csv(artifact_paths["shape_class_metrics_csv"], shape_class_rows)
    write_csv(artifact_paths["shape_class_provider_metrics_csv"], shape_class_provider_rows)
    write_csv(artifact_paths["case_metrics_csv"], case_rows)
    write_csv(artifact_paths["audit_metrics_csv"], audit_rows)
    write_csv(artifact_paths["dimension_buckets_csv"], dimension_rows)
    write_csv(artifact_paths["rule_counts_csv"], rule_rows)
    write_csv(artifact_paths["notable_cases_csv"], notable_rows)
    write_json(artifact_paths["analysis_json"], analysis)
    write_text(artifact_paths["manifest_md"], render_manifest(analysis))

    print(f"Wrote report artifacts: {path_for_record(artifact_paths['manifest_md'])}")
    return artifact_paths


def default_run_dirs() -> list[Path]:
    return [
        ROOT / "outputs" / "verification_results" / "stage1-full-001-openai",
        ROOT / "outputs" / "verification_results" / "stage1-full-001-gemini",
        ROOT / "outputs" / "verification_results" / "stage1-full-001-anthropic",
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build report artifacts from verification results.")
    parser.add_argument("--run-dir", action="append", type=Path, default=None)
    parser.add_argument("--report-name", default="stage2-stage3-stage1-full-001")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "reports")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_dirs = args.run_dir or default_run_dirs()
    try:
        build_report(run_dirs, output_dir=args.output_dir, report_name=args.report_name)
    except (ReportingError, OSError, ValueError) as exc:
        print(f"Report artifact generation failed: {exc}", file=sys.stderr)
        return 1
    return 0
