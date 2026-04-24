# Implementation Spec: Core And Common Utilities

## `core.geometry`

`core.geometry` 定義所有 slot 與 adjacency 規則，是 Stage 2 z-axis grounding 的基礎。

固定 slot：

- `upper_left`
- `upper_right`
- `lower_left`
- `lower_right`

重要 helper：

- `is_valid_slot(slot)`：確認 slot 是否為四個合法值之一。
- `ordered_slots(slots)`：依固定 slot order 排序，確保輸出穩定。
- `occupied_slots_from_layout(layout)`：從四 slot layout 取出 occupied slots。
- `validate_l_shaped_layout(layout, context)`：驗證 layout 是四個 slot key、0/1 值、剛好三個 occupied slots。
- `adjacency_relation(slot_a, slot_b)`：回傳 `same`、`horizontal`、`vertical`、`diagonal` 或 `invalid`。
- `are_adjacent(slot_a, slot_b)`：只在 relation 是 `horizontal` 或 `vertical` 時為 true。

目前 `horizontal` 與 `vertical` 同時用於：

- view slot adjacency relation。
- dimension line orientation。
- inferred z-axis orientation in a slot。

這是刻意的簡化契約：系統不處理 mirror handedness、軸向正負方向，也不嘗試建立完整三維座標系。

## `core.numeric`

`core.numeric` 是所有尺寸值比較的共用入口。

- `parse_dimension_value(value)` 接受 int、float、或可直接 `float(...)` 的字串。
- bool 被明確排除。
- 空字串、非 numeric 字串、非 scalar object 會回傳 `None`。
- `values_equal(a, b, tolerance=1e-6)` 使用絕對差比較。
- `value_in(value, candidates, tolerance=1e-6)` 檢查候選值中是否有容差內相等項。

限制：目前不解析單位、範圍、上下限、公差符號或 mixed unit。Stage 2/3 因此以 `unit_comparability == dataset_default_consistent` 表達目前資料集假設。

## `common.io_utils`

`common.io_utils` 提供 repo-local I/O 與 provider response serialization。

重要責任：

- `ROOT`：repo root，透過 package file path 往上三層取得。
- `load_env_file(env_path)`：讀取 `.env`，支援簡單 `KEY=VALUE` 與 quote stripping，並同步寫入 `os.environ.setdefault`。
- `read_json` / `write_json`：UTF-8 JSON I/O，write 時 `ensure_ascii=False`、indent 2。
- `read_text` / `write_text`。
- `write_csv`：以第一列 key 決定欄位順序；空 rows 寫空檔。
- `extract_json_candidate` / `parse_json_text`：從 provider response text 中抽出 fenced JSON 或第一段 object/array candidate。
- `detect_mime_type` / `encode_image_to_base64`。
- `sanitize_for_json` / `dump_sdk_response`：把 SDK object 轉成可寫入 JSON 的結構。

`parse_json_text` 是 Stage 1 對 provider response 的第一道解析，不保證 schema valid；schema validation 由各 task schema module 負責。

## `common.providers`

`common.providers` 包裝 hosted provider SDK 與本機 Ollama REST API，對 Stage 1 runner 提供一致的 `ProviderClient.run(prompt_text, image_path)` 介面。

支援 provider：

- `openai`
- `gemini`
- `anthropic`
- `ollama`

每個 provider client 回傳 dict：

- `status_code`
- `raw_response_text`
- `response_json`
- `response_text`
- `request_summary`

`request_summary` 至少包含 transport、endpoint、model、image path、MIME type、temperature。Ollama request summary 也會記錄 normalized base URL。Stage 1 runner 會再補上 task name、case id、image id 等欄位。

Provider wrapper 不要求 structured output；目前 prompt 要求模型回 JSON，Stage 1 再以 `parse_json_text` 與 schema module 做容錯解析與驗證。

Ollama 使用 `POST <base_url>/chat`，預設 base URL 是 `http://localhost:11434/api`。Real run 需要 `OLLAMA_MODEL` 或 `--ollama-model`，但不需要 API key；使用者需先啟動 `ollama serve` 並 pull vision-capable model。

## 測試與風險

目前 core/common 多數行為透過 Stage 1/2/3/pipeline tests 間接覆蓋。最重要的風險邊界：

- `parse_dimension_value` 僅支援直接 numeric string，因此 prompt/schema 應避免輸出單位。
- `write_csv` 使用第一列欄位，後續 row 若有額外 key 不會自動納入。
- Provider SDK 呼叫是 network side effect，單元測試主要透過 dry-run 或 helper payload 驗證下游行為。
