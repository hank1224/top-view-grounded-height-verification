from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from top_view_grounded_height_verification.common.io_utils import ROOT, read_json, write_json
from top_view_grounded_height_verification.stage1.task_specs import TASK_SPECS


class EvidenceBundleError(Exception):
    pass


SELECTED_ATTEMPT_RE = re.compile(r"^run-\d{3}\.json$")


def path_for_record(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_cases(task_name: str) -> dict[str, dict[str, Any]]:
    payload = read_json(TASK_SPECS[task_name].cases_path)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise EvidenceBundleError(f"{TASK_SPECS[task_name].cases_path} must contain a cases array")
    return {case["image_id"]: case for case in cases if isinstance(case, dict)}


def load_ground_truth_groups(task_name: str) -> dict[str, dict[str, Any]]:
    payload = read_json(TASK_SPECS[task_name].ground_truth_path)
    groups = payload.get("answer_groups")
    if not isinstance(groups, list):
        raise EvidenceBundleError(f"{TASK_SPECS[task_name].ground_truth_path} must contain answer_groups")
    return {group["answer_key"]: group for group in groups if isinstance(group, dict)}


def load_attempts(run_dir: Path, *, provider: str | None, repeat_index: int) -> dict[str, dict[str, Any]]:
    if not run_dir.exists():
        raise EvidenceBundleError(f"Run directory does not exist: {run_dir}")
    attempts: dict[str, dict[str, Any]] = {}
    for attempt_path in sorted(run_dir.glob("attempts/*/*/run-*.json")):
        if not SELECTED_ATTEMPT_RE.match(attempt_path.name):
            continue
        attempt = read_json(attempt_path)
        if provider and attempt.get("provider") != provider:
            continue
        if attempt.get("repeat_index") != repeat_index:
            continue
        image_id = attempt.get("image_id")
        if not isinstance(image_id, str):
            continue
        if image_id in attempts:
            raise EvidenceBundleError(
                f"Multiple attempts matched image_id={image_id}. "
                "Pass a narrower --provider or --repeat-index."
            )
        attempt["_attempt_record_path"] = path_for_record(attempt_path)
        attempts[image_id] = attempt
    if not attempts:
        raise EvidenceBundleError(f"No attempts matched in {run_dir}")
    return attempts


def expected_for_case(case: dict[str, Any], answer_groups: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    group = answer_groups.get(case["answer_key"])
    if not group:
        return None
    ground_truth = group.get("ground_truth")
    return ground_truth if isinstance(ground_truth, dict) else None


def build_ground_truth(
    *,
    image_id: str,
    direct_cases: dict[str, dict[str, Any]],
    dimension_cases: dict[str, dict[str, Any]],
    top_view_cases: dict[str, dict[str, Any]],
    direct_gt: dict[str, dict[str, Any]],
    dimension_gt: dict[str, dict[str, Any]],
    top_view_gt: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    direct_case = direct_cases[image_id]
    dimension_case = dimension_cases[image_id]
    top_view_case = top_view_cases[image_id]
    direct_group = direct_gt.get(direct_case["answer_key"], {})
    return {
        "dimension_ground_truth": expected_for_case(dimension_case, dimension_gt),
        "top_view_ground_truth": expected_for_case(top_view_case, top_view_gt),
        "direct_ground_truth": expected_for_case(direct_case, direct_gt),
        "evaluation_metadata": direct_group.get("evaluation_metadata", {}),
    }


def source_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": attempt.get("run_name"),
        "provider": attempt.get("provider"),
        "model": attempt.get("model"),
        "case_id": attempt.get("case_id"),
        "attempt_id": f"run-{int(attempt.get('repeat_index', 1)):03d}",
        "attempt_record_path": attempt.get("_attempt_record_path"),
        "selected_attempt_index": attempt.get("selected_attempt_index", attempt.get("attempt_index")),
        "selected_source_attempt_record_path": attempt.get("selected_source_attempt_record_path"),
        "attempt_count": attempt.get("attempt_count", 1),
        "max_attempts": attempt.get("max_attempts", 1),
        "accepted": attempt.get("accepted", attempt.get("schema_valid")),
        "acceptance_level": attempt.get("acceptance_level"),
    }


def normalized_or_empty(attempt: dict[str, Any]) -> dict[str, Any]:
    normalized = attempt.get("normalized_contract")
    if isinstance(normalized, dict):
        return normalized
    task_name = attempt.get("task_name")
    raw_prediction = attempt.get("raw_prediction")
    if isinstance(task_name, str) and task_name in TASK_SPECS and raw_prediction is not None:
        recovered, _errors = TASK_SPECS[task_name].normalize_prediction(raw_prediction)
        if isinstance(recovered, dict):
            recovered["recovered_from_raw_prediction"] = True
            recovered["source_schema_valid"] = attempt.get("schema_valid")
            return recovered
    return {
        "schema_valid": False,
        "parse_error": attempt.get("parse_error"),
        "validation_errors": attempt.get("validation_errors", []),
    }


def build_bundle(args: argparse.Namespace) -> Path:
    direct_attempts = load_attempts(args.direct_run, provider=args.provider, repeat_index=args.repeat_index)
    dimension_attempts = load_attempts(args.dimension_run, provider=args.provider, repeat_index=args.repeat_index)
    top_view_attempts = load_attempts(args.top_view_run, provider=args.provider, repeat_index=args.repeat_index)

    direct_cases = load_cases("direct_extraction")
    dimension_cases = load_cases("dimension_extraction")
    top_view_cases = load_cases("top_view_detection")
    direct_gt = load_ground_truth_groups("direct_extraction")
    dimension_gt = load_ground_truth_groups("dimension_extraction")
    top_view_gt = load_ground_truth_groups("top_view_detection")

    image_ids = sorted(set(direct_attempts) & set(dimension_attempts) & set(top_view_attempts))
    if not image_ids:
        raise EvidenceBundleError("No shared image_ids across the three Stage 1 runs")

    bundle_name = args.bundle_name or f"evidence-bundle-{datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz')}"
    output_dir = args.output_dir / bundle_name
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    evidence_by_image_id: dict[str, dict[str, Any]] = {}
    for image_id in image_ids:
        case = direct_cases[image_id]
        evidence = {
            "schema_version": "tvghv-evidence-bundle-v0.2",
            "image_id": image_id,
            "image_path": case["image_path"],
            "package_name": case["package_name"],
            "package_slug": case["package_slug"],
            "shape_class": case.get("shape_class"),
            "variant_name": case["variant_name"],
            "variant_slug": case["variant_slug"],
            "evidence_sources": {
                "direct_extraction": source_summary(direct_attempts[image_id]),
                "dimension_extraction": source_summary(dimension_attempts[image_id]),
                "top_view_detection": source_summary(top_view_attempts[image_id]),
            },
            "direct_extraction": normalized_or_empty(direct_attempts[image_id]),
            "dimension_extraction": normalized_or_empty(dimension_attempts[image_id]),
            "top_view_detection": normalized_or_empty(top_view_attempts[image_id]),
            "ground_truth": build_ground_truth(
                image_id=image_id,
                direct_cases=direct_cases,
                dimension_cases=dimension_cases,
                top_view_cases=top_view_cases,
                direct_gt=direct_gt,
                dimension_gt=dimension_gt,
                top_view_gt=top_view_gt,
            ),
        }
        evidence_by_image_id[image_id] = evidence
        write_json(cases_dir / f"{image_id}.json", evidence)

    write_json(output_dir / "evidence_by_image_id.json", evidence_by_image_id)
    write_json(
        output_dir / "summary.json",
        {
            "schema_version": "tvghv-evidence-bundle-summary-v0.2",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "bundle_name": bundle_name,
            "case_count": len(image_ids),
            "provider": args.provider,
            "repeat_index": args.repeat_index,
            "direct_run": path_for_record(args.direct_run),
            "dimension_run": path_for_record(args.dimension_run),
            "top_view_run": path_for_record(args.top_view_run),
            "image_ids": image_ids,
        },
    )
    print(f"Wrote evidence bundle: {path_for_record(output_dir)}")
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build per-image Stage 1 evidence bundles.")
    parser.add_argument("--direct-run", type=Path, required=True)
    parser.add_argument("--dimension-run", type=Path, required=True)
    parser.add_argument("--top-view-run", type=Path, required=True)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--repeat-index", type=int, default=1)
    parser.add_argument("--bundle-name", default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "evidence_bundles")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        build_bundle(args)
    except (EvidenceBundleError, OSError, ValueError) as exc:
        print(f"Evidence bundle failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
