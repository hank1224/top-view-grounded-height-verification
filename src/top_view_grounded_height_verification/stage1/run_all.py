from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from top_view_grounded_height_verification.common.io_utils import ROOT, write_json
from top_view_grounded_height_verification.stage1.evidence_bundle import build_bundle
from top_view_grounded_height_verification.stage1.runner import (
    DEFAULT_ENV_PATH,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MODELS,
    Stage1RunError,
    SUPPORTED_PROVIDERS,
    run_stage1,
)


TASK_RUN_SUFFIXES = {
    "direct_extraction": "direct",
    "dimension_extraction": "dimension",
    "top_view_detection": "top-view",
}


class Stage1RunAllError(Exception):
    pass


def timestamp_run_name() -> str:
    return datetime.now(timezone.utc).strftime("stage1-%Y%m%dt%H%M%Sz")


def path_for_record(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def namespace_for_task(args: argparse.Namespace, task_name: str, run_name: str) -> argparse.Namespace:
    return argparse.Namespace(
        task_name=task_name,
        cases_path=None,
        ground_truth_path=None,
        output_root=None,
        run_name=run_name,
        providers=args.providers,
        repeats=args.repeats,
        max_attempts=args.max_attempts,
        retry_bbox_invalid=args.retry_bbox_invalid,
        dry_run=args.dry_run,
        env_path=args.env_path,
        timeout_seconds=args.timeout_seconds,
        temperature=args.temperature,
        prompt_context_mode=args.prompt_context_mode,
        case_id=args.case_id,
        image_id=args.image_id,
        package_slug=args.package_slug,
        variant_slug=args.variant_slug,
        max_cases=args.max_cases,
        models=dict(args.models),
        base_urls=dict(args.base_urls),
    )


def namespace_for_bundle(
    args: argparse.Namespace,
    *,
    provider: str,
    bundle_name: str,
    task_run_dirs: dict[str, Path],
) -> argparse.Namespace:
    return argparse.Namespace(
        direct_run=task_run_dirs["direct_extraction"],
        dimension_run=task_run_dirs["dimension_extraction"],
        top_view_run=task_run_dirs["top_view_detection"],
        provider=provider,
        repeat_index=args.bundle_repeat_index,
        bundle_name=bundle_name,
        output_dir=args.bundle_output_dir,
    )


def run_all(args: argparse.Namespace) -> dict[str, Any]:
    if args.repeats < 1:
        raise Stage1RunAllError("--repeats must be >= 1")
    if args.bundle_repeat_index < 1 or args.bundle_repeat_index > args.repeats:
        raise Stage1RunAllError("--bundle-repeat-index must be between 1 and --repeats")

    base_run_name = args.run_name or timestamp_run_name()
    task_run_dirs: dict[str, Path] = {}
    for task_name, suffix in TASK_RUN_SUFFIXES.items():
        task_run_name = f"{base_run_name}-{suffix}"
        task_args = namespace_for_task(args, task_name, task_run_name)
        task_run_dirs[task_name] = run_stage1(task_args)

    bundle_dirs: dict[str, Path] = {}
    for provider in args.providers:
        bundle_name = f"{base_run_name}-{provider}"
        bundle_args = namespace_for_bundle(
            args,
            provider=provider,
            bundle_name=bundle_name,
            task_run_dirs=task_run_dirs,
        )
        bundle_dirs[provider] = build_bundle(bundle_args)

    summary = {
        "schema_version": "tvghv-stage1-run-all-summary-v0.2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_name": base_run_name,
        "providers": args.providers,
        "repeats": args.repeats,
        "max_attempts": args.max_attempts,
        "bundle_repeat_index": args.bundle_repeat_index,
        "retry_policy": {
            "retry_api_or_parse_error": True,
            "retry_schema_invalid": True,
            "retry_dimension_bbox_invalid": args.retry_bbox_invalid,
        },
        "dry_run": args.dry_run,
        "task_runs": {
            task_name: path_for_record(path)
            for task_name, path in task_run_dirs.items()
        },
        "evidence_bundles": {
            provider: path_for_record(path)
            for provider, path in bundle_dirs.items()
        },
    }
    summary_dir = ROOT / "runs" / "stage1" / "all"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{base_run_name}.json"
    write_json(summary_path, summary)
    print(f"Wrote Stage 1 all-run summary: {path_for_record(summary_path)}")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run all Stage 1 evidence acquisition tasks and build provider evidence bundles."
    )
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--providers", nargs="+", choices=SUPPORTED_PROVIDERS, default=list(SUPPORTED_PROVIDERS))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--bundle-repeat-index", type=int, default=1)
    parser.add_argument(
        "--no-retry-bbox-invalid",
        dest="retry_bbox_invalid",
        action="store_false",
        help="Accept dimension OCR/layout evidence when only bbox validation failed.",
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
    parser.add_argument("--bundle-output-dir", type=Path, default=ROOT / "outputs" / "evidence_bundles")
    for provider, model in DEFAULT_MODELS.items():
        parser.add_argument(f"--{provider}-model", default=model)
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-base-url", default=None)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.models = {
        "openai": args.openai_model,
        "gemini": args.gemini_model,
        "anthropic": args.anthropic_model,
        "ollama": args.ollama_model,
    }
    args.base_urls = {
        "ollama": args.ollama_base_url,
    }
    if args.max_attempts < 1:
        parser.error("--max-attempts must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_all(args)
    except (Stage1RunAllError, Stage1RunError, OSError, ValueError) as exc:
        print(f"Stage 1 all-run failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
