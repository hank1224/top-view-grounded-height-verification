# Paper Intent Spec: Stage 1 Low-Level Evidence

## 階段意圖

Stage 1 的論文角色是 low-level evidence extraction。它不是最終答案判斷器，也不是空間推理器。

這個階段刻意把模型任務拆成三份較低階、可檢查的輸出：

- Direct dimension answer。
- Dimension OCR/layout evidence。
- Top-view localization evidence。

拆分目的在於觀察並利用 VLM 較可靠的能力，而不是把所有 reasoning 壓在單一 prompt 中。

## 三種輸入的研究意義

### Direct extraction

Direct extraction 保存模型原本會給出的目標尺寸答案。這是 Stage 3 要篩檢的對象。

它代表：

- 模型在一般 end-to-end 尺寸抽取任務下的直接表現。
- 可能含有高度 hallucination 或 z-axis binding error。

它不代表：

- 已經被圖面 evidence 支撐。
- 已經完成可靠的三視圖推理。

### Dimension extraction

Dimension extraction 取得 OCR value、dimension line orientation、belongs-to-slot 與 layout。

它代表：

- 模型是否能穩定讀出圖面上可見的低階 dimension evidence。
- 後續 rule engine 可使用的主要 evidence pool。

它不代表：

- 每個 dimension 的語意名稱已被正確理解。
- 某個 value 已經被判定為 height。

### Top-view detection

Top-view detection 取得 layout 與 `top_view_slot`。

它代表：

- 建構 z-axis grounding rule 所需的 anchor。
- 讓系統可以用 top-view adjacency 推導相鄰 view 中哪個 orientation 對應高度。

它不代表：

- Top-view 本身有 height dimension。
- 系統已知道完整 front/side/back view identity。

## 為什麼保留 bbox 但不讓 bbox 主導方法

Stage 1 schema 要求 bbox，是為了保存 localization artifact 與檢查模型是否真的指出 view 位置。

但論文方法的核心不是 bbox geometry，而是：

- slot layout
- top-view slot
- dimension line orientation
- dimension belongs-to-slot
- OCR numeric value

因此實作允許 bbox invalid 但 OCR/topology valid 的資料保留到主流程，並用 warning 記錄。這符合論文意圖：不要因為非核心 artifact 失敗，就丟掉可用的低階 evidence。

## Stage 1 成果可以代表什麼

Stage 1 成果可用於回答：

- 模型是否能抽出圖面上的 numeric dimensions？
- 模型是否能判斷 dimension line orientation？
- 模型是否能把 dimensions 分配到正確 slot？
- 模型是否能找出 top-view slot？

Stage 1 成果不能直接回答：

- 模型高度答案是否正確？
- 某個 dimension 是否是 overall package height？
- 規則引擎是否有足夠 evidence 支撐 direct answer？

這些問題分別由 Stage 2 construction 與 Stage 3 screening 回答。

