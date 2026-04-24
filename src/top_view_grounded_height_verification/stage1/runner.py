from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from top_view_grounded_height_verification.common.io_utils import (
    ROOT,
    detect_mime_type,
    load_env_file,
    parse_json_text,
    read_json,
    read_text,
    write_csv,
    write_json,
    write_text,
)
from top_view_grounded_height_verification.common.providers import (
    DEFAULT_OLLAMA_BASE_URL,
    ProviderClient,
    ProviderError,
    build_provider_client,
)
from top_view_grounded_height_verification.stage1.task_specs import Stage1TaskSpec, get_task_spec


SUPPORTED_PROVIDERS = ("openai", "gemini", "anthropic", "ollama")
DEFAULT_MODELS = {
    "openai": "gpt-5.4-2026-03-05",
    "gemini": "gemini-3-flash-preview",
    "anthropic": "claude-sonnet-4-6",
}
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_MAX_ATTEMPTS = 3
PACKAGE_CONTEXT_PLACEHOLDER = "{{PACKAGE_CONTEXT_BLOCK}}"
UNRESOLVED_PLACEHOLDER_RE = re.compile(r"{{[^{}]+}}")
SLOT_SYNTHETIC_BBOXES = {
    "upper_left": [0, 0, 500, 500],
    "upper_right": [0, 500, 500, 1000],
    "lower_left": [500, 0, 1000, 500],
    "lower_right": [500, 500, 1000, 1000],
}


class Stage1RunError(Exception):
    pass


class DryRunClient:
    def __init__(self, model: str) -> None:
        self.model = model


def path_for_record(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sanitize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")


def build_package_context_block(case: dict[str, Any], prompt_context_mode: str) -> str:
    if prompt_context_mode == "none":
        return ""
    if prompt_context_mode == "package_name":
        return (
            "Known package context:\n"
            f"- Package name: {case['package_name']}\n\n"
            "Use this package context only to identify the package family and interpret the drawing.\n"
            "If a requested dimension cannot be determined from the image, return null."
        )
    raise Stage1RunError(f"Unsupported prompt context mode: {prompt_context_mode}")


def render_prompt(prompt_template: str, *, case: dict[str, Any], prompt_context_mode: str) -> str:
    rendered = prompt_template.replace(
        PACKAGE_CONTEXT_PLACEHOLDER,
        build_package_context_block(case, prompt_context_mode),
    )
    unresolved = sorted(set(UNRESOLVED_PLACEHOLDER_RE.findall(rendered)))
    if unresolved:
        raise Stage1RunError(
            f"Prompt for `{case['case_id']}` contains unresolved placeholders: {unresolved}"
        )
    rendered = re.sub(r"\n{3,}", "\n\n", rendered).strip()
    return rendered + "\n"


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise Stage1RunError(f"Cases file must contain a `cases` array: {path}")
    return cases


def filter_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    case_ids = set(args.case_id or [])
    image_ids = set(args.image_id or [])
    package_slugs = set(args.package_slug or [])
    variant_slugs = set(args.variant_slug or [])
    for case in cases:
        if case_ids and case["case_id"] not in case_ids:
            continue
        if image_ids and case["image_id"] not in image_ids:
            continue
        if package_slugs and case["package_slug"] not in package_slugs:
            continue
        if variant_slugs and case["variant_slug"] not in variant_slugs:
            continue
        selected.append(case)
    if args.max_cases is not None:
        selected = selected[: args.max_cases]
    if not selected:
        raise Stage1RunError("No cases matched the requested filters")
    return selected


def build_prompt_template_cache(cases: list[dict[str, Any]]) -> dict[str, str]:
    cache: dict[str, str] = {}
    for case in cases:
        prompt_path = ROOT / case["prompt_path"]
        cache.setdefault(case["prompt_path"], read_text(prompt_path))
    return cache


def expected_for_case(case: dict[str, Any], answer_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    answer_group = answer_map.get(case["answer_key"])
    if answer_group is None:
        raise Stage1RunError(f"Missing answer_key in ground truth: {case['answer_key']}")
    ground_truth = answer_group.get("ground_truth")
    if not isinstance(ground_truth, dict):
        raise Stage1RunError(f"Ground truth is not complete for answer_key: {case['answer_key']}")
    return ground_truth


def make_dry_run_prediction(expected_output: dict[str, Any]) -> dict[str, Any]:
    prediction = json.loads(json.dumps(expected_output))
    for view in prediction.get("views", []):
        if not isinstance(view, dict) or "bounding_box_2d" in view:
            continue
        slot = view.get("slot")
        if slot in SLOT_SYNTHETIC_BBOXES:
            view["bounding_box_2d"] = SLOT_SYNTHETIC_BBOXES[slot]
    return prediction


def write_response_artifacts(
    *,
    run_dir: Path,
    provider: str,
    case_id: str,
    artifact_stem: str,
    response_text: Any,
    raw_response_text: Any,
    response_json: Any,
) -> dict[str, str]:
    attempt_dir = run_dir / "attempts" / provider / case_id
    artifact_paths: dict[str, str] = {}
    if isinstance(response_text, str):
        response_text_path = attempt_dir / f"{artifact_stem}.response.txt"
        write_text(response_text_path, response_text)
        artifact_paths["response_text"] = path_for_record(response_text_path)
    if isinstance(raw_response_text, str):
        raw_response_path = attempt_dir / f"{artifact_stem}.raw.txt"
        write_text(raw_response_path, raw_response_text)
        artifact_paths["raw_response_text"] = path_for_record(raw_response_path)
    if response_json is not None:
        response_json_path = attempt_dir / f"{artifact_stem}.sdk.json"
        write_json(response_json_path, response_json)
        artifact_paths["response_json"] = path_for_record(response_json_path)
    return artifact_paths


def execute_provider_attempt(
    *,
    spec: Stage1TaskSpec,
    provider: str,
    client: ProviderClient,
    case: dict[str, Any],
    prompt_text: str,
    image_path: Path,
) -> tuple[dict[str, Any], Any | None, str | None]:
    try:
        provider_result = client.run(prompt_text=prompt_text, image_path=image_path)
        request_summary = provider_result.get("request_summary")
        if isinstance(request_summary, dict):
            request_summary["task_name"] = spec.task_name
            request_summary["case_id"] = case["case_id"]
            request_summary["image_id"] = case["image_id"]
        response_text = provider_result.get("response_text") or ""
        raw_prediction, parse_error = (
            parse_json_text(response_text) if response_text else (None, "Empty response text")
        )
        return provider_result, raw_prediction, parse_error
    except Exception as exc:  # pragma: no cover - defensive against SDK/network/runtime failures
        error_text = f"{exc.__class__.__name__}: {exc}"
        provider_result = {
            "status_code": getattr(exc, "status_code", None),
            "raw_response_text": str(exc),
            "response_json": None,
            "response_text": None,
            "request_summary": {
                "transport": f"{provider} SDK",
                "endpoint": "request_failed_before_response",
                "model": client.model,
                "image_path": image_path.relative_to(ROOT).as_posix(),
                "mime_type": detect_mime_type(image_path),
                "task_name": spec.task_name,
                "case_id": case["case_id"],
                "image_id": case["image_id"],
                "shape_class": case.get("shape_class"),
            },
            "api_error": error_text,
        }
        return provider_result, None, error_text


def build_provider_clients(args: argparse.Namespace) -> dict[str, ProviderClient | DryRunClient]:
    if not hasattr(args, "base_urls"):
        args.base_urls = {}
    env = load_env_file(args.env_path)
    for provider in SUPPORTED_PROVIDERS:
        model_override = env.get(f"{provider.upper()}_MODEL")
        if model_override:
            args.models[provider] = model_override
    ollama_base_url = (
        args.base_urls.get("ollama")
        or env.get("OLLAMA_BASE_URL")
        or DEFAULT_OLLAMA_BASE_URL
    )
    args.base_urls["ollama"] = ollama_base_url

    for provider in args.providers:
        if args.models.get(provider):
            continue
        if args.dry_run:
            args.models[provider] = f"{provider}-dry-run"
            continue
        raise Stage1RunError(
            f"Missing model for provider `{provider}`. "
            f"Set {provider.upper()}_MODEL or pass --{provider}-model."
        )

    if args.dry_run:
        return {
            provider: DryRunClient(args.models[provider])
            for provider in args.providers
        }

    clients: dict[str, ProviderClient] = {}
    for provider in args.providers:
        api_key_name = f"{provider.upper()}_API_KEY"
        api_key = "" if provider == "ollama" else env.get(api_key_name)
        if provider != "ollama" and not api_key:
            raise Stage1RunError(f"Missing {api_key_name}. Add it to {args.env_path}.")
        try:
            clients[provider] = build_provider_client(
                provider,
                model=args.models[provider],
                api_key=api_key or "",
                timeout_seconds=args.timeout_seconds,
                temperature=args.temperature,
                base_url=args.base_urls.get(provider),
            )
        except ProviderError as exc:
            raise Stage1RunError(str(exc)) from exc
    return clients


def process_attempt(
    *,
    spec: Stage1TaskSpec,
    run_dir: Path,
    provider: str,
    model: str,
    client: ProviderClient | DryRunClient,
    case: dict[str, Any],
    expected_output: dict[str, Any],
    prompt_text: str,
    repeat_index: int,
    attempt_index: int,
    dry_run: bool,
) -> dict[str, Any]:
    image_path = ROOT / case["image_path"]
    started_at = datetime.now(timezone.utc).isoformat()
    if dry_run:
        raw_prediction = make_dry_run_prediction(expected_output)
        response_text = json.dumps(raw_prediction, ensure_ascii=False, indent=2)
        provider_result = {
            "status_code": 200,
            "raw_response_text": response_text,
            "response_json": None,
            "response_text": response_text,
            "request_summary": {
                "transport": "dry-run",
                "model": model,
                "image_path": case["image_path"],
                "task_name": spec.task_name,
                "case_id": case["case_id"],
                "image_id": case["image_id"],
                "shape_class": case.get("shape_class"),
            },
        }
        parse_error = None
    else:
        provider_result, raw_prediction, parse_error = execute_provider_attempt(
            spec=spec,
            provider=provider,
            client=client,  # type: ignore[arg-type]
            case=case,
            prompt_text=prompt_text,
            image_path=image_path,
        )

    artifact_paths = write_response_artifacts(
        run_dir=run_dir,
        provider=provider,
        case_id=case["case_id"],
        artifact_stem=f"run-{repeat_index:03d}-attempt-{attempt_index:03d}",
        response_text=provider_result.get("response_text"),
        raw_response_text=provider_result.get("raw_response_text"),
        response_json=provider_result.get("response_json"),
    )

    if parse_error:
        comparison = spec.compare_outputs(None, expected_output)
        comparison["parse_error"] = parse_error
    else:
        comparison = spec.compare_outputs(raw_prediction, expected_output)

    normalized_contract = None
    normalized_errors: list[str] = []
    if raw_prediction is not None and not parse_error:
        normalized_contract, normalized_errors = spec.normalize_prediction(raw_prediction)

    completed_at = datetime.now(timezone.utc).isoformat()
    attempt = {
        "task_name": spec.task_name,
        "run_name": run_dir.name,
        "provider": provider,
        "model": model,
        "case_id": case["case_id"],
        "image_id": case["image_id"],
        "answer_key": case["answer_key"],
        "package_name": case["package_name"],
        "package_slug": case["package_slug"],
        "shape_class": case.get("shape_class"),
        "variant_name": case["variant_name"],
        "variant_slug": case["variant_slug"],
        "repeat_index": repeat_index,
        "attempt_index": attempt_index,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "dry_run": dry_run,
        "prompt_path": case["prompt_path"],
        "image_path": case["image_path"],
        "expected_output": expected_output,
        "raw_prediction": raw_prediction,
        "normalized_output": comparison.get("normalized_output"),
        "normalized_contract": normalized_contract,
        "schema_valid": bool(comparison.get("schema_valid")),
        "exact_match": bool(comparison.get("exact_match")),
        "parse_error": parse_error,
        "validation_errors": comparison.get("validation_errors", normalized_errors),
        "comparison": comparison,
        "provider_status_code": provider_result.get("status_code"),
        "request_summary": provider_result.get("request_summary"),
        "artifact_paths": artifact_paths,
    }
    attempt_record_path = (
        run_dir
        / "attempts"
        / provider
        / case["case_id"]
        / f"run-{repeat_index:03d}-attempt-{attempt_index:03d}.json"
    )
    write_json(attempt_record_path, attempt)
    attempt["attempt_record_path"] = path_for_record(attempt_record_path)
    return attempt


def evaluate_attempt_acceptance(
    attempt: dict[str, Any],
    *,
    retry_bbox_invalid: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    comparison = attempt.get("comparison", {})
    parse_error = attempt.get("parse_error")
    task_name = attempt.get("task_name")

    if parse_error:
        reasons.append("parse_or_api_error")
        return {
            "accepted": False,
            "retryable": True,
            "acceptance_level": "parse_or_api_error",
            "acceptance_rank": 0,
            "retry_reasons": reasons,
        }

    if attempt.get("schema_valid"):
        return {
            "accepted": True,
            "retryable": False,
            "acceptance_level": "full_valid",
            "acceptance_rank": 3,
            "retry_reasons": [],
        }

    if task_name == "dimension_extraction" and comparison.get("ocr_schema_valid"):
        if not comparison.get("bbox_output_valid"):
            reasons.append("bbox_output_invalid")
        else:
            reasons.append("schema_invalid")
        return {
            "accepted": not retry_bbox_invalid,
            "retryable": retry_bbox_invalid,
            "acceptance_level": "ocr_valid_bbox_invalid",
            "acceptance_rank": 2,
            "retry_reasons": reasons,
        }

    if task_name == "top_view_detection" and comparison.get("topology_schema_valid"):
        if not comparison.get("bbox_output_valid"):
            reasons.append("bbox_output_invalid")
        else:
            reasons.append("schema_invalid")
        return {
            "accepted": not retry_bbox_invalid,
            "retryable": retry_bbox_invalid,
            "acceptance_level": "topology_valid_bbox_invalid",
            "acceptance_rank": 2,
            "retry_reasons": reasons,
        }

    reasons.append("schema_invalid")
    return {
        "accepted": False,
        "retryable": True,
        "acceptance_level": "schema_invalid",
        "acceptance_rank": 1,
        "retry_reasons": reasons,
    }


def select_best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if not attempts:
        raise Stage1RunError("Cannot select from an empty attempt list")
    return max(
        attempts,
        key=lambda attempt: (
            int(attempt.get("acceptance", {}).get("acceptance_rank", 0)),
            int(attempt.get("attempt_index", 1)),
        ),
    )


def write_selected_attempt(
    *,
    run_dir: Path,
    provider: str,
    case_id: str,
    repeat_index: int,
    attempts: list[dict[str, Any]],
    max_attempts: int,
) -> dict[str, Any]:
    selected = json.loads(json.dumps(select_best_attempt(attempts), ensure_ascii=False))
    selected_path = run_dir / "attempts" / provider / case_id / f"run-{repeat_index:03d}.json"
    all_attempt_record_paths = [attempt["attempt_record_path"] for attempt in attempts]
    retry_history = [
        {
            "attempt_index": attempt.get("attempt_index"),
            "attempt_record_path": attempt.get("attempt_record_path"),
            **attempt.get("acceptance", {}),
        }
        for attempt in attempts
    ]
    acceptance = selected.get("acceptance", {})
    selected.update(
        {
            "selected": True,
            "attempt_count": len(attempts),
            "max_attempts": max_attempts,
            "selected_attempt_index": selected.get("attempt_index"),
            "selected_source_attempt_record_path": selected.get("attempt_record_path"),
            "all_attempt_record_paths": all_attempt_record_paths,
            "retry_history": retry_history,
            "accepted": acceptance.get("accepted", False),
            "acceptance_level": acceptance.get("acceptance_level", "unknown"),
            "retry_reasons": acceptance.get("retry_reasons", []),
        }
    )
    selected["attempt_record_path"] = path_for_record(selected_path)
    write_json(selected_path, selected)
    return selected


def process_attempt_with_retries(
    *,
    spec: Stage1TaskSpec,
    run_dir: Path,
    provider: str,
    model: str,
    client: ProviderClient | DryRunClient,
    case: dict[str, Any],
    expected_output: dict[str, Any],
    prompt_text: str,
    repeat_index: int,
    dry_run: bool,
    max_attempts: int,
    retry_bbox_invalid: bool,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt_index in range(1, max_attempts + 1):
        print(
            f"[{spec.task_name}] {provider} {case['case_id']} "
            f"run-{repeat_index:03d} attempt-{attempt_index:03d}"
        )
        attempt = process_attempt(
            spec=spec,
            run_dir=run_dir,
            provider=provider,
            model=model,
            client=client,
            case=case,
            expected_output=expected_output,
            prompt_text=prompt_text,
            repeat_index=repeat_index,
            attempt_index=attempt_index,
            dry_run=dry_run,
        )
        acceptance = evaluate_attempt_acceptance(
            attempt,
            retry_bbox_invalid=retry_bbox_invalid,
        )
        attempt["acceptance"] = acceptance
        write_json(ROOT / attempt["attempt_record_path"], attempt)
        attempts.append(attempt)
        if acceptance["accepted"] or not acceptance["retryable"]:
            break
        if attempt_index < max_attempts:
            print(
                f"[{spec.task_name}] retrying {provider} {case['case_id']} "
                f"because {', '.join(acceptance['retry_reasons'])}"
            )

    return write_selected_attempt(
        run_dir=run_dir,
        provider=provider,
        case_id=case["case_id"],
        repeat_index=repeat_index,
        attempts=attempts,
        max_attempts=max_attempts,
    )


def summarize_attempts(attempts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    task_name = attempts[0]["task_name"] if attempts else ""
    dimension_metric_names = [
        "schema_valid",
        "ocr_schema_valid",
        "layout_exact_match",
        "layout_slot_accuracy",
        "occupied_slot_precision",
        "occupied_slot_recall",
        "occupied_slot_f1",
        "bbox_output_valid",
        "dimension_value_precision",
        "dimension_value_recall",
        "dimension_value_f1",
        "dimension_assignment_accuracy",
        "orientation_accuracy",
        "exact_match",
    ]
    dimension_count_names = [
        "layout_slot_correct_count",
        "layout_slot_total_count",
        "occupied_slot_matched_count",
        "expected_occupied_slot_count",
        "predicted_occupied_slot_count",
        "dimension_value_matched_count",
        "dimension_value_slot_matched_count",
        "expected_dimension_count",
        "predicted_dimension_count",
        "matched_dimension_count",
        "dimension_full_matched_count",
    ]

    attempt_rows = []
    for attempt in attempts:
        row = {
            "task_name": attempt["task_name"],
            "provider": attempt["provider"],
            "model": attempt["model"],
            "case_id": attempt["case_id"],
            "image_id": attempt["image_id"],
            "shape_class": attempt.get("shape_class"),
            "variant_slug": attempt["variant_slug"],
            "repeat_index": attempt["repeat_index"],
            "schema_valid": attempt["schema_valid"],
            "exact_match": attempt["exact_match"],
            "parse_error": attempt["parse_error"] or "",
            "validation_errors": json.dumps(attempt["validation_errors"], ensure_ascii=False),
            "attempt_record_path": attempt["attempt_record_path"],
            "selected_attempt_index": attempt.get("selected_attempt_index", attempt.get("attempt_index", 1)),
            "attempt_count": attempt.get("attempt_count", 1),
            "max_attempts": attempt.get("max_attempts", 1),
            "accepted": attempt.get("accepted", attempt.get("schema_valid", False)),
            "acceptance_level": attempt.get("acceptance_level", "full_valid" if attempt.get("schema_valid") else "schema_invalid"),
            "retry_reasons": json.dumps(attempt.get("retry_reasons", []), ensure_ascii=False),
            "all_attempt_record_paths": json.dumps(
                attempt.get("all_attempt_record_paths", [attempt["attempt_record_path"]]),
                ensure_ascii=False,
            ),
        }
        if task_name == "dimension_extraction":
            comparison = attempt.get("comparison", {})
            for metric in dimension_metric_names:
                row[metric] = comparison.get(metric, attempt.get(metric, False if metric.endswith("_valid") or metric.endswith("_match") else 0.0))
            for count_name in dimension_count_names:
                row[count_name] = comparison.get(count_name, 0)
            row["bbox_validation_errors"] = json.dumps(
                comparison.get("bbox_validation_errors", []),
                ensure_ascii=False,
            )
        attempt_rows.append(row)

    provider_rows = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for attempt in attempts:
        grouped.setdefault((attempt["provider"], attempt["model"]), []).append(attempt)
    for (provider, model), rows in sorted(grouped.items()):
        count = len(rows)
        if task_name != "dimension_extraction":
            provider_rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "attempt_count": count,
                    "api_call_count": sum(int(row.get("attempt_count", 1) or 1) for row in rows),
                    "retried_case_count": sum(1 for row in rows if int(row.get("attempt_count", 1) or 1) > 1),
                    "accepted_count": sum(1 for row in rows if row.get("accepted", row["schema_valid"])),
                    "max_attempts_exhausted_count": sum(
                        1
                        for row in rows
                        if int(row.get("attempt_count", 1) or 1) >= int(row.get("max_attempts", 1) or 1)
                        and not row.get("accepted", row["schema_valid"])
                    ),
                    "schema_valid_count": sum(1 for row in rows if row["schema_valid"]),
                    "exact_match_count": sum(1 for row in rows if row["exact_match"]),
                    "schema_valid_rate": sum(1 for row in rows if row["schema_valid"]) / count if count else 0.0,
                    "exact_match_rate": sum(1 for row in rows if row["exact_match"]) / count if count else 0.0,
                }
            )
            continue

        summary: dict[str, Any] = {
            "provider": provider,
            "model": model,
            "attempt_count": count,
            "case_count": len({row["case_id"] for row in rows}),
            "api_call_count": sum(int(row.get("attempt_count", 1) or 1) for row in rows),
            "retried_case_count": sum(1 for row in rows if int(row.get("attempt_count", 1) or 1) > 1),
            "accepted_count": sum(1 for row in rows if row.get("accepted", row["schema_valid"])),
            "max_attempts_exhausted_count": sum(
                1
                for row in rows
                if int(row.get("attempt_count", 1) or 1) >= int(row.get("max_attempts", 1) or 1)
                and not row.get("accepted", row["schema_valid"])
            ),
        }
        for metric in dimension_metric_names:
            summary[f"case_macro_{metric}"] = round(
                sum(float(row.get("comparison", {}).get(metric, row.get(metric, 0)) or 0) for row in rows)
                / count,
                4,
            ) if count else 0.0
        summary["case_exact_match_count"] = sum(1 for row in rows if row["exact_match"])
        summary["case_schema_valid_count"] = sum(1 for row in rows if row["schema_valid"])
        summary["case_ocr_schema_valid_count"] = sum(
            1 for row in rows if row.get("comparison", {}).get("ocr_schema_valid")
        )
        summary["case_bbox_output_valid_count"] = sum(
            1 for row in rows if row.get("comparison", {}).get("bbox_output_valid")
        )
        for count_name in dimension_count_names:
            summary[count_name] = sum(
                int(row.get("comparison", {}).get(count_name, 0) or 0)
                for row in rows
            )

        occupied_matched = summary["occupied_slot_matched_count"]
        occupied_expected = summary["expected_occupied_slot_count"]
        occupied_predicted = summary["predicted_occupied_slot_count"]
        dimension_value_matched = summary["dimension_value_matched_count"]
        dimension_value_slot_matched = summary["dimension_value_slot_matched_count"]
        dimension_full_matched = summary["dimension_full_matched_count"]
        expected_dimensions = summary["expected_dimension_count"]
        predicted_dimensions = summary["predicted_dimension_count"]

        def ratio(numerator: float, denominator: float) -> float:
            return round(numerator / denominator, 4) if denominator else 0.0

        summary["answer_micro_layout_slot_accuracy"] = ratio(
            summary["layout_slot_correct_count"],
            summary["layout_slot_total_count"],
        )
        summary["answer_micro_occupied_slot_precision"] = ratio(occupied_matched, occupied_predicted)
        summary["answer_micro_occupied_slot_recall"] = ratio(occupied_matched, occupied_expected)
        occupied_precision = summary["answer_micro_occupied_slot_precision"]
        occupied_recall = summary["answer_micro_occupied_slot_recall"]
        summary["answer_micro_occupied_slot_f1"] = (
            round(2 * occupied_precision * occupied_recall / (occupied_precision + occupied_recall), 4)
            if occupied_precision + occupied_recall
            else 0.0
        )
        summary["answer_micro_dimension_value_precision"] = ratio(
            dimension_value_matched,
            predicted_dimensions,
        )
        summary["answer_micro_dimension_value_recall"] = ratio(
            dimension_value_matched,
            expected_dimensions,
        )
        summary["answer_micro_dimension_value_accuracy"] = summary[
            "answer_micro_dimension_value_recall"
        ]
        dimension_value_precision = summary["answer_micro_dimension_value_precision"]
        dimension_value_recall = summary["answer_micro_dimension_value_recall"]
        summary["answer_micro_dimension_value_f1"] = (
            round(
                2
                * dimension_value_precision
                * dimension_value_recall
                / (dimension_value_precision + dimension_value_recall),
                4,
            )
            if dimension_value_precision + dimension_value_recall
            else 0.0
        )
        summary["answer_micro_dimension_assignment_accuracy"] = ratio(
            dimension_value_slot_matched,
            dimension_value_matched,
        )
        summary["answer_micro_orientation_accuracy"] = ratio(
            dimension_full_matched,
            dimension_value_slot_matched,
        )
        summary["answer_micro_dimension_full_accuracy"] = ratio(
            dimension_full_matched,
            expected_dimensions,
        )
        provider_rows.append(summary)
    return attempt_rows, provider_rows


def run_stage1(args: argparse.Namespace) -> Path:
    spec = get_task_spec(args.task_name)
    cases = filter_cases(load_cases(args.cases_path or spec.cases_path), args)
    ground_truth_payload = read_json(args.ground_truth_path or spec.ground_truth_path)
    answer_map = spec.load_answer_map(ground_truth_payload)
    prompt_cache = build_prompt_template_cache(cases)
    clients = build_provider_clients(args)

    run_name = args.run_name or f"{spec.task_name}-{now_stamp()}"
    run_dir = (args.output_root or spec.output_root) / sanitize_slug(run_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task_name": spec.task_name,
        "run_name": run_name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "providers": args.providers,
        "models": {provider: args.models[provider] for provider in args.providers},
        "base_urls": {
            provider: args.base_urls[provider]
            for provider in args.providers
            if args.base_urls.get(provider)
        },
        "case_count": len(cases),
        "repeats": args.repeats,
        "max_attempts": args.max_attempts,
        "retry_policy": {
            "retry_api_or_parse_error": True,
            "retry_schema_invalid": True,
            "retry_dimension_bbox_invalid": args.retry_bbox_invalid,
        },
        "dry_run": args.dry_run,
        "prompt_context_mode": args.prompt_context_mode,
        "cases_path": path_for_record(args.cases_path or spec.cases_path),
        "ground_truth_path": path_for_record(args.ground_truth_path or spec.ground_truth_path),
    }
    write_json(run_dir / "config.json", config)

    attempts: list[dict[str, Any]] = []
    for provider in args.providers:
        client = clients[provider]
        for case in cases:
            expected_output = expected_for_case(case, answer_map)
            prompt_text = render_prompt(
                prompt_cache[case["prompt_path"]],
                case=case,
                prompt_context_mode=args.prompt_context_mode,
            )
            for repeat_index in range(1, args.repeats + 1):
                attempts.append(
                    process_attempt_with_retries(
                        spec=spec,
                        run_dir=run_dir,
                        provider=provider,
                        model=args.models[provider],
                        client=client,
                        case=case,
                        expected_output=expected_output,
                        prompt_text=prompt_text,
                        repeat_index=repeat_index,
                        dry_run=args.dry_run,
                        max_attempts=args.max_attempts,
                        retry_bbox_invalid=args.retry_bbox_invalid,
                    )
                )

    attempt_rows, provider_rows = summarize_attempts(attempts)
    write_csv(run_dir / "attempts.csv", attempt_rows)
    write_csv(run_dir / "provider_summary.csv", provider_rows)
    write_json(
        run_dir / "summary.json",
        {
            "task_name": spec.task_name,
            "run_name": run_name,
            "attempt_count": len(attempts),
            "api_call_count": sum(int(attempt.get("attempt_count", 1) or 1) for attempt in attempts),
            "max_attempts": args.max_attempts,
            "providers": provider_rows,
        },
    )
    print(f"Wrote Stage 1 run: {path_for_record(run_dir)}")
    return run_dir


def build_parser(default_task_name: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Stage 1 evidence acquisition task.")
    parser.add_argument("--task-name", default=default_task_name, choices=("direct_extraction", "dimension_extraction", "top_view_detection"))
    parser.add_argument("--cases-path", type=Path, default=None)
    parser.add_argument("--ground-truth-path", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--providers", nargs="+", choices=SUPPORTED_PROVIDERS, default=["openai"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--no-retry-bbox-invalid",
        dest="retry_bbox_invalid",
        action="store_false",
        help="Accept main image-level answer evidence when only bbox validation failed.",
    )
    parser.set_defaults(retry_bbox_invalid=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--prompt-context-mode", choices=("none", "package_name"), default="none")
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--image-id", action="append", default=None)
    parser.add_argument("--package-slug", action="append", default=None)
    parser.add_argument("--variant-slug", action="append", default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    for provider, model in DEFAULT_MODELS.items():
        parser.add_argument(f"--{provider}-model", default=model)
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-base-url", default=None)
    return parser


def parse_args(default_task_name: str | None = None, argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser(default_task_name)
    args = parser.parse_args(argv)
    if not args.task_name:
        parser.error("--task-name is required")
    args.models = {
        "openai": args.openai_model,
        "gemini": args.gemini_model,
        "anthropic": args.anthropic_model,
        "ollama": args.ollama_model,
    }
    args.base_urls = {
        "ollama": args.ollama_base_url,
    }
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be >= 1")
    return args


def main(default_task_name: str | None = None, argv: list[str] | None = None) -> int:
    args = parse_args(default_task_name, argv)
    try:
        run_stage1(args)
    except (Stage1RunError, OSError, ValueError) as exc:
        print(f"Stage 1 run failed: {exc}", file=sys.stderr)
        return 1
    return 0
