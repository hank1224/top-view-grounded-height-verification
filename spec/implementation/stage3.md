# Implementation Spec: Stage 3 Height Answer Screening

## 職責

Stage 3 使用 Stage 2 的 `height_evidence_result` 篩檢模型 direct answer。它不重新抽取 dimension、不重新推理 top-view，也不使用 ground truth 修正答案。

目前唯一 verified target：

- `overall_package_height`

對外 decision：

- `supported`
- `contradicted`
- `insufficient_evidence`

## 輸入

`screen_height_answer(direct_extraction, height_evidence_result)` 需要：

- Stage 1 direct extraction normalized contract。
- Stage 2 height evidence result。

Direct value 讀取位置：

- `direct_extraction.targets.overall_package_height.value`

若 target missing 或 value 無法 parse 成 number，decision 為 `insufficient_evidence`。

## 前置條件

進入實際比較前，Stage 3 要求：

- `height_evidence_status == constructed`
- `verification_readiness.status == ready`

若任一條件不滿足，decision 為 `insufficient_evidence`，failure reasons 會包含：

- `height_evidence_not_constructed`
- `verification_not_ready`
- readiness 原因，例如 `no_supporting_dimensions`、`unresolved_dimensions_present`、`unit_comparability_unknown`

## Derived height

`derive_height_from_supporting_dimensions(supporting_dimensions)` 使用：

```text
derived_height_value = max(supporting_dimensions.numeric_value)
```

只有 numeric supporting dimensions 參與推導。若沒有 numeric supporting dimensions，decision 為 `insufficient_evidence`。

若有多個 supporting dimensions 等於 max value，全部視為 matched supporting dimensions，並合併 evidence chain。

## Decision rules

### `supported`

條件：

- Stage 2 constructed。
- Verification ready。
- Model height value numeric。
- Derived height value 存在。
- Model value 等於 derived height value。
- Matched supporting dimension 至少有 evidence chain。

輸出會包含：

- `derived_height_value`
- `matched_supporting_dimension_uids`
- `matched_supporting_dimension_values`
- `evidence_chain`

### `contradicted`

條件之一成立即可：

- Model value 出現在 `ruled_out_dimensions.numeric_value`。
- Model value 出現在 `supporting_dimensions.numeric_value`，但不是 supporting max value。

第一種情況的 rejecting evidence rule：

- `model_value_matches_ruled_out_dimension`

第二種情況的 rejecting evidence rule：

- `model_value_is_supporting_dimension_but_not_maximum`

### `insufficient_evidence`

常見原因：

- Direct answer missing 或 non-numeric。
- Stage 2 not constructed。
- Verification not ready。
- 沒有 numeric supporting dimensions。
- Model value 不存在於任何 OCR dimension buckets。
- Model value 無法被 classified against height evidence。
- Matched supporting dimension 缺 evidence chain。

`insufficient_evidence` 表示目前證據不足，不代表模型答案必然錯。

## Output contract

Screening result 欄位：

- `schema_version == tvghv-screening-result-v1.0`
- `screening_status == reported`
- `decision`
- `verified_target == overall_package_height`
- `model_value`
- `derived_height_value`
- `derivation_rule`
- `matched_supporting_dimension_uids`
- `matched_supporting_dimension_values`
- `contradicting_dimension_uids`
- `rejecting_evidence`
- `evidence_chain`
- `failure_reasons`

## 測試對應

`tests/test_stage3_height_screening.py` 覆蓋：

- 正確高度被 supported。
- ruled-out nuisance value 被 contradicted。
- smaller supporting value 被 contradicted。
- missing/non-numeric model value 被 insufficient。
- model value 不在 OCR evidence 時被 insufficient。
- height evidence not ready 時被 insufficient。

