# Implementation Spec: Stage 1 Evidence Acquisition

## 職責

Stage 1 負責把 package drawing image 交給 VLM，取得三種結構化低階輸入：

- `direct_extraction`：模型直接回答的 package target dimensions。
- `dimension_extraction`：layout、view slots、bbox、dimension OCR values、dimension line orientation、belongs-to-slot。
- `top_view_detection`：layout、view slots、bbox、top-view slot。

Stage 1 不負責判斷高度答案正誤，也不負責建構 z-axis evidence。它只負責產生可檢查、可重跑、可 audit 的低階 evidence artifacts。

## Task specs

`stage1.task_specs` 用 `Stage1TaskSpec` 記錄每個 task 的：

- `task_name`
- `cases_path`
- `ground_truth_path`
- `output_root`
- `schema_module`

Schema module 以 dynamic import 提供三個函式：

- `normalize_prediction(data)`
- `compare_outputs(predicted, expected)`
- `load_answer_map(ground_truth_payload)`

目前支援 task：

- `direct_extraction`
- `dimension_extraction`
- `top_view_detection`

## Runner flow

`stage1.runner.run_stage1(args)` 是單一 task 的 runner：

1. 讀取 task spec、cases、ground truth、prompt templates。
2. 依 CLI filters 選 case：`case_id`、`image_id`、`package_slug`、`variant_slug`、`max_cases`。
3. 建立 provider clients，或在 `--dry-run` 時建立 synthetic client。
4. 每個 provider、case、repeat 執行最多 `max_attempts` 次。
5. 每次 attempt 寫入 raw response artifact、SDK JSON、attempt record。
6. 根據 acceptance policy 選出 selected attempt，寫成 `run-<repeat>.json`。
7. 輸出 `attempts.csv`、`provider_summary.csv`、`summary.json`。

Prompt rendering 只支援一個 placeholder：`{{PACKAGE_CONTEXT_BLOCK}}`。`--prompt-context-mode` 可為：

- `none`
- `package_name`

若 render 後仍有 unresolved `{{...}}`，runner 會報錯。

## Retry and acceptance policy

每個 attempt 都會被 `evaluate_attempt_acceptance` 分級：

- `parse_or_api_error`：不可用，但 retryable。
- `full_valid`：完整 schema valid，accepted。
- `ocr_valid_bbox_invalid`：dimension task 的 OCR/layout valid 但 bbox invalid。
- `topology_valid_bbox_invalid`：top-view task 的 topology valid 但 bbox invalid。
- `schema_invalid`：schema invalid，但 retryable。

`--no-retry-bbox-invalid` 會讓 bbox invalid 但 OCR/topology valid 的 attempt 被接受；預設會 retry bbox invalid。

`select_best_attempt` 以 `acceptance_rank` 與 attempt index 選出最佳 attempt。Selected attempt 會記錄：

- `selected_attempt_index`
- `selected_source_attempt_record_path`
- `all_attempt_record_paths`
- `retry_history`
- `accepted`
- `acceptance_level`
- `retry_reasons`

## Dry-run behavior

`--dry-run` 不呼叫 provider API，而是使用 ground truth 產生 synthetic prediction。對需要 bbox 的 task，runner 會用 slot-based synthetic bbox 補足輸出。

Dry-run 用途是檢查 pipeline、artifact writing、schema、summary 是否可跑通，不代表 provider model behavior。

## Schema modules

### Direct extraction

`stage1.direct_extraction.schema` 驗證 direct answer object。輸入 key 必須精確等於四個 target keys，值為 number 或 null。

Normalize 後輸出 `targets.<key>.value/raw_value`。Compare 產生 per-field match 與 exact match。

### Dimension extraction

`stage1.dimension_extraction.schema` 驗證 layout、views、bbox、dimensions。

特別行為：

- full schema valid 要求 bbox。
- OCR/layout schema 可在 bbox invalid 時仍成立。
- compare metrics 包含 layout accuracy、occupied slot precision/recall/F1、dimension value precision/recall/F1、dimension assignment accuracy、orientation accuracy。

### Top-view detection

`stage1.top_view_detection.schema` 驗證 layout、views、bbox、`top_view_slot`。

特別行為：

- full schema valid 要求 bbox。
- topology schema 可在 bbox invalid 時仍成立。
- compare metrics 包含 exact match、top-view slot match、bbox validation。

## Evidence bundle

`stage1.evidence_bundle.build_bundle(args)` 讀取三個 task run 的 selected attempts，依 `image_id` 取交集，輸出 provider-specific evidence bundle。

重要行為：

- 若同一 image id 有多個符合 provider/repeat 的 selected attempts，會報錯，要求使用更窄的 `--provider` 或 `--repeat-index`。
- 若 selected attempt 沒有 `normalized_contract`，會嘗試從 `raw_prediction` 重新 normalize。
- Bundle 內同時保存 normalized outputs 與 ground truth side data。

輸出：

- `cases/<image_id>.json`
- `evidence_by_image_id.json`
- `summary.json`

## Run-all orchestration

`stage1.run_all.run_all(args)` 依序執行三個 Stage 1 tasks，再對每個 provider 建立 evidence bundle。輸出 summary 到 `runs/stage1/all/<run>.json`。

這個 orchestrator 仍屬 Stage 1；Stage 2/3 要由 `pipeline.py` 或 `scripts/run_full_analysis.py` 後續執行。

