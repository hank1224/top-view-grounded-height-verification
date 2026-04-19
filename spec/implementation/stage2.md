# Implementation Spec: Stage 2 Evidence Construction And Audit

## 職責

Stage 2 把 Stage 1 的三份輸入整理成 height evidence。它的重點是建立可解釋的證據集合，而不是判斷 direct height answer 正誤。

Stage 2 包含三個子模組：

- `fusion.py`：融合與驗證低階 evidence。
- `audit.py`：使用 ground truth 產生 evaluation side-channel report。
- `height_evidence.py`：依 top-view-grounded rules 建構 height evidence。

## 2A: Evidence fusion

`stage2.fusion.build_evidence(input_payload)` 讀取 evidence bundle case，輸出 internal evidence object。

輸出基本欄位：

- `status`
- `image_id`
- `image_path`
- `layout`
- `occupied_slots`
- `top_view_slot`
- `views`
- `top_view_views`
- `dimensions`
- `warnings`
- `failure_reasons`

Fusion validation：

- `dimension_extraction` 與 `top_view_detection` 必須是 object。
- `dimension_extraction.ocr_schema_valid == false` 會使 fusion invalid。
- `top_view_detection.schema_valid == false` 但 `topology_schema_valid == true` 時可接受。
- 兩份輸入的 layout 必須都是 valid three-occupied-slot layout，且彼此相同。
- `dimension_extraction.views` 與 `top_view_detection.views` 都必須剛好覆蓋 occupied slots。
- `top_view_slot` 必須是合法且 occupied 的 slot。

Fusion 對 bbox 的態度：

- dimension bbox invalid 不會丟掉 OCR/layout evidence，只加入 `dimension_extraction_bbox_output_invalid` warning。
- top-view bbox invalid 不會丟掉 topology evidence，只加入 `top_view_detection_bbox_output_invalid` warning。

Dimension flatten 行為：

- 每個 dimension 會得到 stable `dimension_uid`，格式為 `<slot>_d<index>`。
- `numeric_value` 優先讀 raw dimension 的 `numeric_value`，失敗時 fallback parse `value`。
- invalid dimension 不會使整個 evidence invalid；會標記 `valid == false` 與 `invalid_reasons`。
- local invalid reasons 包含 `dimension_value_not_numeric`、`invalid_dimension_orientation`、`invalid_belongs_to_slot`、`belongs_to_slot_mismatch`。

## 2B: Evidence audit

`stage2.audit.build_evidence_audit_report(evidence, ground_truth)` 是 evaluation side channel。

若 ground truth 不存在或缺少 dimension/top-view ground truth，回傳：

- `audit_status == not_available`
- `notes`

若可 audit，輸出：

- `audit_status == reported`
- `layout_consistent`
- `layout_correct`
- `top_view_correct`
- `ocr_value_metrics`
- `orientation_accuracy`
- `slot_assignment_accuracy`
- `evidence_completeness`
- `notes`

Audit metric 行為：

- OCR value precision/recall/F1 以 multiset counter 比對 numeric-parsed values。
- slot assignment accuracy 以 `(value, belongs_to_slot)` 在 value matched 的基礎上計算。
- orientation accuracy 以 `(value, belongs_to_slot, orientation)` 在 slot matched 的基礎上計算。

Audit 不修改輸入 evidence，也不影響 Stage 2 height evidence 或 Stage 3 screening。

## 2C: Height evidence construction

`stage2.height_evidence.build_height_evidence(evidence)` 輸出 `tvghv-height-evidence-result-v1.0`。

前置條件：

- fusion evidence 必須 `status == valid`。
- `top_view_slot` 必須存在且在 occupied slots 中。

Z-axis orientation inference：

- 對每個非 top-view slot，若與 top-view 水平相鄰，該 slot 的 `z_orientation` 為 `horizontal`。
- 若與 top-view 垂直相鄰，該 slot 的 `z_orientation` 為 `vertical`。
- 若非 top-view slot 沒有直接與 top-view 相鄰，但與已 grounded 的非 top-view slot 相鄰，會繼承該 neighbor 的 `z_orientation`。
- 每個 inferred orientation 保存 evidence chain。

Dimension bucket classification：

- Top-view slot 內的 dimensions 進入 `ruled_out_dimensions`，rule 為 `top_view_dimensions_are_excluded_from_z_axis_grounding`。
- Local invalid dimensions 進入 `unresolved_dimensions`，rule 為 `dimension_local_evidence_invalid`。
- Slot orientation unresolved 時，dimension 進入 `unresolved_dimensions`，rule 為 `slot_z_orientation_unresolved`。
- Dimension line orientation 等於該 slot 的 z-axis orientation 時，進入 `supporting_dimensions`。
- 不相等時，進入 `ruled_out_dimensions`，rule 為 `dimension_orientation_inconsistent_with_slot_z_axis`。

每筆 bucket record 包含：

- `dimension_uid`
- `value`
- `numeric_value`
- `belongs_to_slot`
- `dimension_line_orientation`
- `z_axis_orientation_for_slot`
- `grounding_type`
- `propagated_from_slot`
- `rule`
- `evidence_chain`
- `valid`
- `invalid_reasons`

## Status and readiness

Case-level `height_evidence_status` 目前只使用：

- `constructed`
- `insufficient`

沒有 case-level `rejected`。被排除的 dimension 以 `ruled_out_dimensions` 表達。

`verification_readiness` 是另一層狀態：

- `ready`
- `not_ready`

`constructed` 不等於 `ready`。以下情況會使 readiness not ready：

- `height_evidence_status != constructed`
- 沒有 supporting dimensions
- 沒有 numeric supporting dimensions
- 有非 top-view slot 未推得 z orientation
- 有 unresolved dimensions
- `unit_comparability == unknown`

目前成功建構時 `unit_comparability` 為 `dataset_default_consistent`。

## Output contract

Height evidence result 欄位：

- `schema_version == tvghv-height-evidence-result-v1.0`
- `height_evidence_status`
- `top_view_slot`
- `z_orientation_by_slot`
- `supporting_dimensions`
- `ruled_out_dimensions`
- `unresolved_dimensions`
- `verification_readiness`
- `global_evidence_chain`
- `failure_reasons`
- `expected_non_top_slots`
- `unit_comparability`

## 測試對應

- Fusion 行為由 `tests/test_stage2_fusion.py` 覆蓋。
- Audit side channel 由 `tests/test_stage2_audit.py` 覆蓋。
- Height evidence rules 由 `tests/test_stage2_height_evidence.py` 覆蓋。

