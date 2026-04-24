#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from top_view_grounded_height_verification.stage1.runner import DEFAULT_MODELS, SUPPORTED_PROVIDERS  # noqa: E402


def timestamp_run_name() -> str:
    return datetime.now(timezone.utc).strftime("analysis-%Y%m%dt%H%M%Sz")


def path_for_print(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def run_command(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def add_repeated_arg(command: list[str], flag: str, values: list[str] | None) -> None:
    for value in values or []:
        command.extend([flag, value])


def build_stage1_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "scripts/stage1_run_all.py",
        "--run-name",
        args.run_name,
        "--providers",
        *args.providers,
        "--repeats",
        str(args.repeats),
        "--max-attempts",
        str(args.max_attempts),
        "--bundle-repeat-index",
        str(args.bundle_repeat_index),
        "--env-path",
        args.env_path.as_posix(),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--temperature",
        str(args.temperature),
        "--prompt-context-mode",
        args.prompt_context_mode,
        "--bundle-output-dir",
        args.bundle_output_dir.as_posix(),
    ]
    if args.dry_run:
        command.append("--dry-run")
    if not args.retry_bbox_invalid:
        command.append("--no-retry-bbox-invalid")
    if args.max_cases is not None:
        command.extend(["--max-cases", str(args.max_cases)])
    for provider, model in args.models.items():
        if model is None:
            continue
        command.extend([f"--{provider}-model", model])
    for provider, base_url in args.base_urls.items():
        if base_url is None:
            continue
        command.extend([f"--{provider}-base-url", base_url])
    add_repeated_arg(command, "--case-id", args.case_id)
    add_repeated_arg(command, "--image-id", args.image_id)
    add_repeated_arg(command, "--package-slug", args.package_slug)
    add_repeated_arg(command, "--variant-slug", args.variant_slug)
    return command


def build_pipeline_command(args: argparse.Namespace, provider: str) -> list[str]:
    bundle_dir = args.bundle_output_dir / f"{args.run_name}-{provider}"
    return [
        sys.executable,
        "scripts/run_pipeline.py",
        "--input",
        bundle_dir.as_posix(),
        "--run-name",
        f"{args.run_name}-{provider}",
        "--output-dir",
        args.verification_output_dir.as_posix(),
    ]


def build_report_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "scripts/build_report.py",
        "--report-name",
        args.report_name or args.run_name,
        "--output-dir",
        args.report_output_dir.as_posix(),
    ]
    for provider in args.providers:
        command.extend(
            [
                "--run-dir",
                (args.verification_output_dir / f"{args.run_name}-{provider}").as_posix(),
            ]
        )
    return command


def run_full_analysis(args: argparse.Namespace) -> None:
    if not args.skip_stage1:
        run_command("Stage 1 evidence acquisition", build_stage1_command(args))
    else:
        print("\n== Stage 1 evidence acquisition ==", flush=True)
        print("Skipped; using existing evidence bundles.", flush=True)

    for provider in args.providers:
        run_command(f"Stage 2/3 verification ({provider})", build_pipeline_command(args, provider))

    run_command("Report artifacts", build_report_command(args))

    report_name = args.report_name or args.run_name
    print("\nAnalysis complete.", flush=True)
    print(f"Verification results: {path_for_print(args.verification_output_dir)}", flush=True)
    print(f"Report manifest: {path_for_print(args.report_output_dir / f'{report_name}-manifest.md')}", flush=True)
    print(f"Analysis JSON: {path_for_print(args.report_output_dir / f'{report_name}-analysis.json')}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Stage 1, Stage 2/3, and report artifact generation in one command."
    )
    parser.add_argument("--run-name", default=timestamp_run_name())
    parser.add_argument("--report-name", default=None)
    parser.add_argument("--providers", nargs="+", choices=SUPPORTED_PROVIDERS, default=list(SUPPORTED_PROVIDERS))
    parser.add_argument("--dry-run", action="store_true", help="Use Stage 1 ground truth as synthetic model output.")
    parser.add_argument("--skip-stage1", action="store_true", help="Reuse existing evidence bundles for this run name.")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--bundle-repeat-index", type=int, default=1)
    parser.add_argument(
        "--no-retry-bbox-invalid",
        dest="retry_bbox_invalid",
        action="store_false",
        help="Accept dimension OCR/layout evidence when only bbox validation failed.",
    )
    parser.set_defaults(retry_bbox_invalid=True)
    parser.add_argument("--env-path", type=Path, default=ROOT / ".env")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--prompt-context-mode", choices=("none", "package_name"), default="none")
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--image-id", action="append", default=None)
    parser.add_argument("--package-slug", action="append", default=None)
    parser.add_argument("--variant-slug", action="append", default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--bundle-output-dir", type=Path, default=ROOT / "outputs" / "evidence_bundles")
    parser.add_argument("--verification-output-dir", type=Path, default=ROOT / "outputs" / "verification_results")
    parser.add_argument("--report-output-dir", type=Path, default=ROOT / "outputs" / "reports")
    for provider, model in DEFAULT_MODELS.items():
        parser.add_argument(f"--{provider}-model", default=model)
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-base-url", default=None)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be >= 1")
    if args.bundle_repeat_index < 1 or args.bundle_repeat_index > args.repeats:
        parser.error("--bundle-repeat-index must be between 1 and --repeats")
    args.models = {
        "openai": args.openai_model,
        "gemini": args.gemini_model,
        "anthropic": args.anthropic_model,
        "ollama": args.ollama_model,
    }
    args.base_urls = {
        "ollama": args.ollama_base_url,
    }
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_full_analysis(args)
    except subprocess.CalledProcessError as exc:
        print(f"Full analysis failed during command: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode or 1
    except (OSError, ValueError) as exc:
        print(f"Full analysis failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
