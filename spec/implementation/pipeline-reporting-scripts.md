# Implementation Spec: Pipeline, Reporting, And Scripts

## Pipeline

`pipeline.py` 負責把 evidence bundle case 串成完整 Stage 2/3 result。

`run_pipeline(input_payload)` 執行：

1. `build_evidence(input_payload)`
2. `build_evidence_audit_report(evidence, input_payload.get("ground_truth"))`
3. `build_height_evidence(evidence)`
4. `screen_height_answer(input_payload.get("direct_extraction", {}), height_evidence_result)`

回傳 `tvghv-pipeline-result-v1.0`：

- image/package metadata
- `input_evidence`
- `evidence`
- `audit_report`
- `height_evidence_result`
- `screening_result`

`load_bundle_cases(input_path)` 支援三種輸入：

- 單一 case JSON，包含 `image_id`。
- map JSON，key 為 image id，value 為 case object。
- bundle directory，包含 `evidence_by_image_id.json` 或 `cases/*.json`。

`run_bundle(input_path, output_dir, run_name)` 對所有 cases 執行 pipeline，輸出：

- `cases/<image_id>.json`
- `summary.json`
- `summary.csv`

## Pipeline summary metrics

`build_summary(results)` 產生：

- `case_count`
- `evaluated_case_count`
- `supported_count`
- `contradicted_count`
- `insufficient_evidence_count`
- `raw_direct_height_correct_count`
- `gt_wrong_count`
- `risk_screening_metrics`
- `screening_decision_by_gt_correctness`
- `notes`

`risk_screening_metrics` 包含：

- `raw_height_accuracy`
- `supported_precision`
- `unsafe_support_rate`
- `coverage`
- `wrong_answer_interception_rate`

若 denominator 為 0，metric 回傳 `None`，並在 `notes` 記錄原因。

## Reporting

`reporting.py` 建立資料優先的 report artifacts，不生成 narrative report。

`build_report(run_dirs, output_dir, report_name)` 讀取一個或多個 verification runs，輸出：

- `<report>-manifest.md`
- `<report>-analysis.json`
- `<report>-provider_metrics.csv`
- `<report>-shape_class_metrics.csv`
- `<report>-shape_class_provider_metrics.csv`
- `<report>-case_metrics.csv`
- `<report>-audit_metrics.csv`
- `<report>-dimension_buckets.csv`
- `<report>-rule_counts.csv`
- `<report>-notable_cases.csv`

Report layers：

- provider-level risk screening metrics。
- shape-class grouping metrics。
- case-level diagnostic rows。
- audit side-channel metrics。
- classified dimension bucket rows。
- rule count rows。
- notable case rows。

`notable_cases.csv` 使用 structured category：

- `unsafe_support`
- `wrong_answer_intercepted`
- `correct_answer_not_supported`

## Scripts

Scripts 主要是 thin CLI wrapper，將 `src/` 加入 `sys.path` 後呼叫 package 內 main function。

Stage 1 scripts：

- `scripts/stage1_run_direct_extraction.py`
- `scripts/stage1_run_dimension_extraction.py`
- `scripts/stage1_run_top_view_detection.py`
- `scripts/stage1_run_all.py`
- `scripts/stage1_build_evidence_bundle.py`

Stage 2/3 and reporting scripts：

- `scripts/run_pipeline.py`
- `scripts/build_report.py`

End-to-end orchestration：

- `scripts/run_full_analysis.py`

`run_full_analysis.py` 依序執行：

1. Stage 1 run-all，除非指定 `--skip-stage1`。
2. 每個 provider 的 Stage 2/3 pipeline。
3. Report artifact generation。

常用選項包含 provider list、model overrides、dry-run、repeats、max attempts、bbox retry policy、case filters、output dirs。

## 測試對應

- `tests/test_pipeline.py` 驗證 single-case pipeline、summary、bundle output。
- `tests/test_reporting.py` 驗證 report artifacts、manifest、analysis JSON、notable cases，以及不生成 narrative report。

