# Spec 文件入口

本目錄是本專案新的規格文件區。文件分成兩組，對應兩種不同讀者需求：

- `implementation/`：以目前程式碼與測試為準，描述模組責任、資料契約、輸入輸出、錯誤條件與測試對應。
- `paper-intent/`：以 `paper-intent/paper-statement.md` 為準，描述研究問題、設計理由、每個階段成果能代表什麼，以及論文宣稱邊界。

## 可信來源

本次文件重構採用以下可信順序：

1. 目前實作與測試是 implementation truth。
2. `paper-intent/paper-statement.md` 是 paper-intent truth。
3. `archive/legacy-docs/` 內的舊文件只作背景參考，不直接採信。

## 文件地圖

Implementation specs：

- `implementation/architecture-overview.md`
- `implementation/data-and-task-contracts.md`
- `implementation/core-common-utilities.md`
- `implementation/stage1.md`
- `implementation/stage2.md`
- `implementation/stage3.md`
- `implementation/pipeline-reporting-scripts.md`

Paper-intent specs：

- `paper-intent/problem-framing-and-claims.md`
- `paper-intent/paper-statement.md`
- `paper-intent/stage1-low-level-evidence.md`
- `paper-intent/stage2-height-evidence.md`
- `paper-intent/stage3-answer-screening.md`
- `paper-intent/result-interpretation-and-metrics.md`

## 核心邊界

- Stage 1 負責低階證據抽取，不要求模型完成完整三視圖空間推理。
- Stage 2 負責建構 height evidence，不判斷 direct height answer 正誤。
- Stage 2B audit 是 evaluation side channel，不回寫或修正主流程。
- `height_evidence_status == constructed` 不等於可驗證；必須同時滿足 `verification_readiness.status == ready`。
- Stage 3 目前只篩檢 `overall_package_height`，並使用 `max(supporting_dimensions.numeric_value)` 作為 derived height。
