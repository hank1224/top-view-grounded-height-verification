# Implementation Spec: Architecture Overview

## 目的

本專案實作一個三階段的 top-view grounded height verification pipeline。它不是讓模型重新回答高度，而是把 VLM 較可靠的低階輸出整理成可解釋的 height evidence，再用這些證據篩檢模型原本的 direct height answer。

## 模組結構

主要 package 位於 `src/top_view_grounded_height_verification/`：

- `core/`：slot geometry、layout、orientation、數值解析與容差比較。
- `common/`：repo I/O、JSON/text/CSV helper、env loader、provider SDK wrapper。
- `stage1/`：三個 evidence acquisition task 的 schema、runner、retry、attempt artifacts、evidence bundle builder。
- `stage2/`：evidence fusion、ground-truth audit side channel、height evidence construction。
- `stage3/`：height answer screening。
- `pipeline.py`：將 evidence bundle case 串成 Stage 2/3 verification result，並輸出 run summary。
- `reporting.py`：從 verification runs 建立資料優先的 report artifacts。

外層目錄：

- `data/package_drawings/`：30 張 value-only package drawing images 與 manifest。
- `data/tasks/`：Stage 1 三個 task 的 cases、ground truth、prompts。
- `scripts/`：CLI wrapper 與整體分析流程。
- `tests/`：目前 implementation behavior 的主要可信規格。

## 執行資料流

1. `data/tasks/*/cases.json` 定義每個 Stage 1 task 要跑的 image case。
2. `stage1.runner` 讀取 prompt、圖片與 provider config，呼叫 OpenAI/Gemini/Anthropic/Ollama 或 dry-run client。
3. 每次 provider 回覆先被 parse 成 JSON，再交給該 task 的 schema module normalize 與 compare。
4. Stage 1 attempt artifacts 寫入 `runs/stage1/<task>/<run>/attempts/<provider>/<case>/`。
5. `stage1.evidence_bundle` 選定每個 task 的 selected attempt，把三份 normalized outputs 合併成 per-image evidence bundle。
6. `pipeline.run_pipeline` 對單一 bundle case 執行 Stage 2 fusion、Stage 2 audit、Stage 2 height evidence construction、Stage 3 screening。
7. `pipeline.run_bundle` 對 bundle 目錄批次執行，輸出 `outputs/verification_results/<run>/cases/*.json`、`summary.json`、`summary.csv`。
8. `reporting.build_report` 整合一個或多個 verification runs，輸出 provider、case、audit、dimension bucket、rule count、notable case 等 CSV/JSON/manifest artifacts。

## 關鍵資料契約

系統內部使用多個 JSON contract：

- Stage 1 selected attempt：記錄 provider/model/case、raw prediction、normalized contract、comparison、retry history、acceptance。
- Evidence bundle：`schema_version == tvghv-evidence-bundle-v0.2`，包含三個 Stage 1 normalized outputs、source summaries、ground truth side data。
- Pipeline result：`schema_version == tvghv-pipeline-result-v1.0`，包含 `evidence`、`audit_report`、`height_evidence_result`、`screening_result`。
- Height evidence result：`schema_version == tvghv-height-evidence-result-v1.0`，包含 `supporting_dimensions`、`ruled_out_dimensions`、`unresolved_dimensions`、`z_orientation_by_slot`、`verification_readiness`。
- Screening result：`schema_version == tvghv-screening-result-v1.0`，輸出 `supported`、`contradicted` 或 `insufficient_evidence`。
- Report analysis：`schema_version == tvghv-report-analysis-v1.0`，整合 run-level 與 group-level metrics。

## 實作不變式

- Slot 只允許 `upper_left`、`upper_right`、`lower_left`、`lower_right`。
- Layout 必須是四個 slot key，值為 `0` 或 `1`，且目前資料模型要求剛好三個 occupied slots。
- Dimension orientation 只允許 `horizontal` 或 `vertical`。
- Stage 2 fusion 接受 bbox invalid 但 OCR/topology valid 的資料，並以 warning 表達，不直接丟棄低階證據。
- Audit 使用 ground truth 只做評估，不改變 `evidence`、`height_evidence_result` 或 `screening_result`。

## 測試對應

- `tests/test_dataset_integrity.py`：資料集、task cases、ground truth alignment。
- `tests/test_stage2_fusion.py`：fusion validation、warnings、dimension normalization。
- `tests/test_stage2_audit.py`：audit side channel 與 metric behavior。
- `tests/test_stage2_height_evidence.py`：z-axis orientation propagation、bucket classification、readiness。
- `tests/test_stage3_height_screening.py`：三分類決策。
- `tests/test_pipeline.py`：single case pipeline、bundle output、summary metrics。
- `tests/test_reporting.py`：report artifacts 與禁止生成 narrative report 的行為。
