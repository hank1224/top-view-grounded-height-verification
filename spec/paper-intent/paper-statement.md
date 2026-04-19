# 論文表述

## 問題定位

本研究處理電子元件正投影圖中的高度語意幻覺風險。

現有多模態模型在讀取工程圖時，通常能穩定抽取部分低階資訊，例如 OCR 數值、尺寸線方向、圖面擺放順序與 top-view 位置；但在跨視圖空間推理時，模型容易把尺寸值綁定到錯誤的軸向，進而產生看似合理、但缺乏圖面支撐的高度答案。

本文不嘗試解決完整長、寬、高語意理解，也不宣稱能穩定判斷所有視圖身份。本文聚焦於一個較窄但高風險的子問題：

```text
How to construct explainable height evidence from reliable low-level signals,
and use it to screen direct height answers from VLMs.
```

也就是：

1. 給定多視圖圖面與模型抽取結果，利用 top-view、slot adjacency、尺寸線方向與 OCR 數值，建構一組可解釋的高度證據。
2. 使用這組高度證據，將模型直接回答的高度答案分成：
   - 有圖面支撐。
   - 與圖面證據衝突。
   - 證據不足，不應自動採信。

## 研究動機

電子元件資料表中的尺寸抽取常遇到兩類問題。

第一，長寬命名在不同廠商、不同封裝類型或不同資料表中不一定一致。即使模型正確讀到數值，也可能無法穩定判斷該數值應該稱為 length、width 或 depth。

第二，高度語意相對穩定，而且常與元件實際裝配風險直接相關。如果模型把非高度尺寸誤判為高度，後續工程流程很難自動攔截這類錯誤。

因此，本文不把目標設定為完整三視圖理解，而是把問題收斂成：

```text
如何利用模型較可靠的低階輸出，
建立一個可解釋的高度證據建構與答案篩檢框架。
```

這個框架的核心不是重新讓模型猜一次高度，而是：

1. 先萃取模型較穩定的低階證據。
2. 再利用規則建立高度證據集合。
3. 最後用該證據集合去篩檢模型原本的高度答案。

## 核心觀察

本研究建立在以下觀察上：

1. 模型對部分低階線索較穩定，包括 top-view 判定、視圖相對位置、OCR 尺寸值、尺寸線水平或垂直方向。
2. 模型對完整跨視圖空間推理較不穩定，包括三視圖完整身份、封裝面方向、視圖翻轉與旋轉推理。
3. Top-view 本身不直接表達高度，但 top-view 與相鄰視圖的關係可以提供高度軸向 grounding 線索。
4. 若某個非 top view 的高度軸方向已由 top-view 關係確定，其他相鄰的非 top view 可繼承同一高度軸方向。
5. 對 `overall_package_height` 或 `A` 而言，若高度證據集合足夠完整，則可由所有 supporting dimensions 中的最大值推導出總高度。

## 方法總覽

本研究方法分成三個階段。

### Stage 1：LLM 證據抽取

第一階段由外部 LLM / VLM API 產生三筆結構化輸入。

1. 模型直接提取的尺寸答案，例如 `body_long_side`、`body_short_side`、`maximum_terminal_to_terminal_span`、`overall_package_height`。
2. 模型提取的尺寸線證據，包括 `layout`、視圖 `slot`、bounding box、尺寸值、尺寸線方向，以及尺寸線所屬的視圖 slot。
3. 模型辨認 top-view 的結果，核心欄位是 `top_view_slot`。

這一階段不要求模型完成空間推理。模型只負責產生較低階、可檢查的證據。

### Stage 2：高度證據建構

第二階段是本文的核心方法。這一階段不直接判定模型高度答案對錯，而是把 Stage 1 的三份輸入整理成一組可供驗證使用的高度證據集合。

第二階段包含三個子步驟。

#### 2A. Evidence Fusion

系統先融合三筆輸入，檢查 `layout`、slot、尺寸線歸屬、尺寸線方向與 top-view 判定是否一致。

這一步的目的是建立可供規則引擎使用的 internal evidence object，而不是直接驗證高度答案。

#### 2B. Evidence Audit

若研究資料提供 ground truth，系統會額外產生一份旁路 evidence audit report，用來評估低階證據品質，例如 OCR value precision / recall / F1、尺寸線方向 accuracy、slot assignment accuracy、top-view detection accuracy。

這份報告只用於實驗透明化與錯誤歸因，不會進入主流程，也不會修正模型輸入。

#### 2C. Height Evidence Construction

完成一致性檢查後，規則引擎根據 top-view 與相鄰視圖關係推導高度證據。

規則核心如下：

1. 若某視圖與 top-view 水平相鄰，該視圖中的水平尺寸線可作為高度 supporting dimension。
2. 若某視圖與 top-view 垂直相鄰，該視圖中的垂直尺寸線可作為高度 supporting dimension。

若另一個非 top view 沒有直接與 top-view 相鄰，但與已被 grounding 的非 top view 相鄰，則它繼承相同的高度軸方向。這讓演算法能從三張圖面中建構出完整的高度證據，而不是只檢查 top-view 的直接鄰居。

第二階段輸出不是單一的三值判定，而是一份完整的 height evidence result。主要包含：

1. `supporting_dimensions`：所有可被規則支撐為高度證據的尺寸線。
2. `ruled_out_dimensions`：已可由規則排除為非高度的尺寸線。
3. `unresolved_dimensions`：證據不足，無法判定的尺寸線。
4. `z_orientation_by_slot`：每個非 top-view slot 對應的高度軸方向。
5. `verification_readiness`：目前證據集合是否足以進行最後的高度驗證。
6. `evidence_chain`：每個 supporting dimension 的推理證據鏈。
7. `height_evidence_status`：整體高度證據建構狀態。

其中，第二階段的 case-level 狀態只分成兩類：

1. `constructed`：已建立可靠的高度證據集合。
2. `insufficient`：目前證據不足，無法建立可靠的高度證據集合。

本版不把 `rejected` 作為 Stage 2 的 case-level 主狀態。被規則排除的尺寸線以 `ruled_out_dimensions` 表達，而不是讓整個 case 進入 rejected 狀態。

### Stage 3：高度答案篩檢

第三階段使用第二階段產生的 `supporting_dimensions` 檢查模型直接提取的高度答案。

若驗證目標是 `overall_package_height` 或 `A`，系統使用：

```text
derived_height_value = max(supporting_dimensions.numeric_value)
```

但這個推導只在 `verification_readiness.status == ready` 時成立。

第三階段不再使用 `accept / reject / abstain` 作為論文主要對外表述，而是把模型高度答案分成三類：

1. `Supported`：模型答案有圖面高度證據支撐。
2. `Contradicted`：模型答案與圖面高度證據衝突。
3. `Insufficient Evidence`：目前證據不足，不應自動採信答案。

三類定義如下。

#### Supported

輸出 `Supported` 的條件：

1. `height_evidence_status == constructed`。
2. `verification_readiness.status == ready`。
3. 模型提供 numeric `overall_package_height`。
4. 至少一個 supporting dimension 有 numeric value。
5. 模型值等於 `max(supporting_dimensions.numeric_value)`。
6. 被採用的 supporting dimension 具有 evidence chain。

#### Contradicted

輸出 `Contradicted` 的條件：

1. `height_evidence_status == constructed`。
2. `verification_readiness.status == ready`。
3. 模型高度值出現在 `ruled_out_dimensions.numeric_value`。
4. 或模型高度值是 supporting dimension，但不是最大的 supporting value。

#### Insufficient Evidence

輸出 `Insufficient Evidence` 的條件：

1. Stage 2 `height_evidence_status == insufficient`。
2. `verification_readiness.status != ready`。
3. 模型沒有提供 `overall_package_height`。
4. 模型高度答案無法解析為數值。
5. 模型答案不在 OCR dimension values 中。
6. 無 numeric supporting dimension。
7. 單位無法比較。

## 結果呈現方式

本研究建議把結果分成三層呈現，而不是把三個 stage 都寫成狀態分類器。

### 第一層：Low-level Evidence Quality

此層對應 Stage 1 與 Stage 2B audit，主要回答：

```text
模型提供的低階證據是否可靠？
```

建議指標包括：

1. OCR value precision / recall / F1
2. 尺寸線方向 accuracy
3. slot assignment accuracy
4. top-view detection accuracy
5. layout consistency

### 第二層：Height Evidence Construction Quality

此層對應 Stage 2，主要回答：

```text
規則引擎能否從低階證據中建構出可用的高度證據？
```

建議指標包括：

1. Height-supporting dimension precision / recall / F1
2. constructed rate
3. verification_ready rate
4. insufficient rate

### 第三層：Height Answer Screening Effect

此層對應 Stage 3，主要回答：

```text
框架是否能把錯誤高度答案攔下來，
同時保留部分可安全放行的答案？
```

建議指標包括：

1. Raw direct-answer height accuracy
2. Supported precision
3. Wrong-answer interception rate
4. Unsafe support rate
5. Coverage
6. Contradicted / Insufficient Evidence distribution

這樣的呈現方式比單純報 Stage 2 tri-state 更能一眼看出框架成效。

## 框架一句話表述

建議用於摘要、方法圖、口頭報告：

```text
We do not ask the model to guess height again. We first extract reliable
low-level signals, then construct height evidence from top-view-grounded rules,
and finally screen the model's direct height answer as Supported, Contradicted,
or Insufficient Evidence.
```

## 可宣稱的貢獻

本文可宣稱以下貢獻：

1. 定義電子元件正投影圖中的 height evidence construction and answer screening 問題。
2. 證明 MLLM 在低階證據抽取與跨視圖空間推理之間存在能力落差。
3. 提出一個 top-view-grounded 規則框架，可從三張圖面中建構高度 supporting dimensions，而不依賴完整三視圖身份理解。
4. 使用 supporting dimensions 推導 `overall_package_height / A`，並將模型高度答案分成 `Supported`、`Contradicted`、`Insufficient Evidence`。
5. 提供 evidence audit report，用 GT 透明化低階證據品質並支援錯誤歸因。
6. 透過答案篩檢機制降低高度相關錯誤答案被直接採信的風險。

## 不應宣稱的貢獻

本文不應宣稱：

1. 解決所有 dimension hallucination。
2. 解決完整長寬高語意。
3. 完整理解三視圖。
4. 能穩定區分所有高度內部尺寸類別，例如本體高、離板高、總高度。
5. 能處理 mirror handedness 或軸向正負方向。
6. `He` 是由本方法完整解出的穩定尺寸語意。
7. Stage 2 單獨就能判斷模型高度答案正誤。Stage 2 的職責是建構高度證據，不是直接拒絕答案。

## 給 Coding Agent 的一句話需求總結

Stage 2 要做的是：

```text
把 Stage 1 的證據轉成 supporting / ruled-out / unresolved dimensions，
以及 verification-ready 與否。
```

Stage 3 要做的是：

```text
用 supporting dimensions 的最大值去篩檢模型高度答案，
最後只輸出 Supported / Contradicted / Insufficient Evidence。
```
