# Top-View Grounded Height Verification

本專案是一個針對電子元件正投影圖的高度語意驗證框架。核心目標不是讓模型重新猜高度，而是先抽取較可靠的低階圖面訊號，再用 top-view-grounded rules 建構 height evidence，最後篩檢模型原本的 direct height answer。

```text
Extract low-level visual evidence, construct explainable height evidence,
then screen direct height answers as Supported, Contradicted, or Insufficient Evidence.
```

## Reading Entry Points

建議依照目的閱讀：

- 論文問題定位與方法敘事：[`spec/paper-intent/paper-statement.md`](./spec/paper-intent/paper-statement.md)
- 現行實作規格與模組文件：[`spec/README.md`](./spec/README.md)
- 手動統整的論文實驗數據：[`experiment_results/README.md`](./experiment_results/README.md)
- 程式入口與模組實作：[`src/top_view_grounded_height_verification`](./src/top_view_grounded_height_verification)
- CLI scripts：[`scripts`](./scripts)
- 測試：[`tests`](./tests)

## Project Shape

```text
src/top_view_grounded_height_verification/
  core/        # slot geometry and numeric helpers
  common/      # I/O helpers and provider SDK wrappers
  stage1/      # low-level evidence acquisition and evidence bundles
  stage2/      # evidence fusion, audit, height evidence construction
  stage3/      # height answer screening
  pipeline.py  # Stage 2/3 batch runner
  reporting.py # report artifact builder

data/
  package_drawings/ # image manifest and package drawing images
  tasks/            # Stage 1 cases, ground truth, prompts

spec/               # current implementation and paper-intent specs
experiment_results/ # manually curated paper-facing experiment summaries
outputs/            # generated artifacts, ignored by git
runs/               # generated Stage 1 runs, ignored by git
```

## Pipeline Overview

The framework has three stages:

1. Stage 1: Low-Level Evidence Extraction
   - Runs `direct_extraction`, `dimension_extraction`, and `top_view_detection`.
   - Produces normalized evidence bundles per image.
   - Does not judge whether the height answer is correct.

2. Stage 2: Height Evidence Construction
   - Fuses low-level evidence.
   - Builds `supporting_dimensions`, `ruled_out_dimensions`, and `unresolved_dimensions`.
   - Produces `verification_readiness`.
   - Audit reports are evaluation side channels and do not modify the main flow.

3. Stage 3: Height Answer Screening
   - Screens `overall_package_height`.
   - Uses `max(supporting_dimensions.numeric_value)` only when evidence is ready.
   - Outputs `supported`, `contradicted`, or `insufficient_evidence`.

## Common Commands

Run tests:

```bash
PYTHONPATH=src:tests ./.venv/bin/python -m unittest discover -s tests
```

Run all Stage 1 tasks and build evidence bundles:

```bash
./.venv/bin/python scripts/stage1_run_all.py --run-name <run-name>
```

Run Stage 2/3 verification over an evidence bundle:

```bash
./.venv/bin/python scripts/run_pipeline.py \
  --input outputs/evidence_bundles/<bundle-name> \
  --run-name <verification-run-name>
```

Build report artifacts from verification runs:

```bash
./.venv/bin/python scripts/build_report.py \
  --run-dir outputs/verification_results/<verification-run-name> \
  --report-name <report-name>
```

Run the full analysis flow:

```bash
./.venv/bin/python scripts/run_full_analysis.py --run-name <run-name>
```

## Source Of Truth

- Current implementation truth: code under `src/` and tests under `tests/`.
- Paper intent truth: `spec/paper-intent/paper-statement.md`.
- Structured specs: `spec/`.
- Paper-facing experiment summaries: `experiment_results/`.
- Generated artifacts under `outputs/` and `runs/` are reproducible outputs, not hand-maintained docs.

舊的 root-level planning documents and draft docs have been removed from the active documentation surface. When in doubt, prefer `spec/paper-intent/paper-statement.md`, `spec/`, code, and tests.

## License

This repository is licensed under
[`CC-BY-SA-4.0 WITH KiCad-libraries-exception`](./LICENSE).
