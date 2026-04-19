# Implementation Spec: Data And Task Contracts

## Dataset contract

`data/package_drawings/image_manifest.json` 是目前資料集入口。實作與測試假設：

- `image_count == 30`。
- 共有 15 個 `package_slug`。
- 每個 package 有兩種 value-only variant：`canonical-values` 與 `rotated-values`。
- 每張 image 有 `image_id`、`package_name`、`package_slug`、`kicad_model_name`、`shape_class`、`variant_name`、`variant_slug`、`image_path`。
- `shape_class` 目前為 `sot_like_smd`、`tabbed_power_smd`、`two_terminal_diode_smd`。
- `source_image_path` 不屬於目前 verifier pipeline consumption contract。

## Stage 1 task cases

`data/tasks/` 目前有三個 task：

- `direct_extraction`
- `dimension_extraction`
- `top_view_detection`

每個 task 的 `cases.json` 包含：

- `task_name`
- `schema_version`
- `case_count`
- `cases`

每個 case 至少提供：

- `case_id`
- `image_id`
- `answer_key`
- `task_name`
- `package_name`
- `package_slug`
- `shape_class`
- `variant_name`
- `variant_slug`
- `prompt_path`
- `image_path`

實作要求三個 task 的 `image_id` 集合一致。`stage1.evidence_bundle` 依 `image_id` 對齊三種 selected attempts。

## Ground truth contract

每個 task 的 `ground_truth.json` 包含 `answer_groups`。Stage 1 runner 透過 `answer_key` 找到對應 group，再讀取 `ground_truth` 作為 expected output。

目前 group count 行為：

- `direct_extraction`：15 groups，canonical/rotated 共用 package-level direct numeric answer。
- `dimension_extraction`：30 groups，每張圖一組。
- `top_view_detection`：30 groups，每張圖一組。

Ground truth 用於：

- Stage 1 compare metrics。
- Evidence bundle 的 `ground_truth` side data。
- Stage 2B audit。
- Pipeline/reporting 的 evaluation metrics。

Ground truth 不用於修正 Stage 2/3 主流程。

## Direct extraction output

`direct_extraction` raw prediction 必須是 JSON object，key 精確等於：

- `body_long_side`
- `body_short_side`
- `maximum_terminal_to_terminal_span`
- `overall_package_height`

每個值必須是 number 或 null。normalize 後轉成：

- `prompt_name`
- `schema_valid`
- `targets.<target>.value`
- `targets.<target>.raw_value`
- `parse_error`
- `validation_errors`

Stage 3 目前只讀取 `targets.overall_package_height.value`。

## Dimension extraction output

`dimension_extraction` raw prediction 描述 layout、view slots、bbox 與 OCR dimension lines：

- `layout`：四 slot 0/1 map，必須剛好三個 occupied slots。
- `views`：每個 occupied slot 一個 view。
- `views[].slot`：該 view 所在 slot。
- `views[].bounding_box_2d`：`[ymin, xmin, ymax, xmax]`，0 到 1000 normalized coordinates。
- `views[].dimensions[]`：dimension line evidence。
- `dimensions[].value`：非空字串，必須可 parse 成 number。
- `dimensions[].orientation`：`horizontal` 或 `vertical`。
- `dimensions[].belongs_to_slot`：必須等於 parent view slot。

Normalize 行為：

- 完整 schema valid 時輸出 `schema_valid == true`、`ocr_schema_valid == true`、`bbox_output_valid`。
- 若只有 bbox invalid，但 layout/OCR evidence valid，仍輸出 `schema_valid == false`、`ocr_schema_valid == true`，保留可用低階證據。
- `comparison` 會提供 layout、occupied slot、OCR value、slot assignment、orientation 等 metrics。

## Top-view detection output

`top_view_detection` raw prediction 描述 layout、view slots、bbox 與 top-view slot：

- `layout`：四 slot 0/1 map，必須剛好三個 occupied slots。
- `views`：每個 occupied slot 一個 view。
- `views[].slot`
- `views[].bounding_box_2d`
- `top_view_slot`：必須是 occupied slot。

Normalize 行為：

- 完整 schema valid 時輸出 `schema_valid == true`、`topology_schema_valid == true`、`bbox_output_valid`。
- 若只有 bbox invalid，但 topology valid，仍輸出 `schema_valid == false`、`topology_schema_valid == true`。

## Evidence bundle contract

`stage1.evidence_bundle` 將三個 selected attempts 合併為：

- `schema_version == tvghv-evidence-bundle-v0.2`
- `image_id`
- `image_path`
- `package_name`
- `package_slug`
- `shape_class`
- `variant_name`
- `variant_slug`
- `evidence_sources`
- `direct_extraction`
- `dimension_extraction`
- `top_view_detection`
- `ground_truth`

`evidence_sources` 保存每個 task 的 selected attempt metadata，例如 provider、model、run id、case id、attempt path、accepted、acceptance level。

輸出形狀：

- `outputs/evidence_bundles/<bundle>/cases/<image_id>.json`
- `outputs/evidence_bundles/<bundle>/evidence_by_image_id.json`
- `outputs/evidence_bundles/<bundle>/summary.json`

