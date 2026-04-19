# Paper Intent Spec: Problem Framing And Claims

## 問題定位

本研究處理電子元件正投影圖中的高度語意幻覺風險。核心問題不是完整解決所有長寬高語意，而是：

```text
How to construct explainable height evidence from reliable low-level signals,
and use it to screen direct height answers from VLMs.
```

換句話說，本方法不要求模型再猜一次高度，而是：

1. 先抽取模型較穩定的低階 evidence。
2. 用 top-view-grounded rules 建構 height evidence。
3. 用 height evidence 篩檢 direct height answer。

## 研究動機

電子元件 datasheet/package drawing 的尺寸抽取有兩個關鍵風險：

- 長、寬、深等命名在不同封裝、廠商、資料表中不穩定。
- 高度語意相對穩定，且直接關係到裝配與工程風險。

因此本研究把範圍收斂到 z-axis grounding：若模型把非高度尺寸當成高度，系統需要有能力把答案標成 contradicted 或 insufficient evidence，而不是直接採信。

## 核心觀察

本研究假設並檢驗以下能力落差：

- VLM 對 OCR value、dimension line orientation、view slot layout、top-view slot 這類低階訊號較穩定。
- VLM 對完整跨視圖空間推理、三視圖身份、封裝面方向、旋轉與翻轉推理較不穩定。
- Top-view 本身不表達高度，但 top-view 與相鄰 views 的 slot adjacency 可提供 z-axis grounding。
- 一個非 top-view slot 的 z-axis orientation 被 grounding 後，相鄰非 top-view slot 可繼承同一 z-axis orientation。

## 可宣稱貢獻

可宣稱：

- 定義 package drawing 中 height evidence construction and answer screening 問題。
- 顯示 MLLM 在低階 evidence extraction 與跨視圖空間推理之間存在能力落差。
- 提出 top-view-grounded rule framework，不依賴完整三視圖身份理解，也能從三張圖面中建構 height supporting dimensions。
- 使用 supporting dimensions 推導 `overall_package_height / A`，並將 direct answer 分為 `Supported`、`Contradicted`、`Insufficient Evidence`。
- 提供 evidence audit report 透明化低階 evidence quality，支援錯誤歸因。
- 以 screening mechanism 降低高度錯誤答案被直接採信的風險。

## 不應宣稱

不應宣稱：

- 解決所有 dimension hallucination。
- 解決完整 length/width/height semantic understanding。
- 完整理解三視圖。
- 能穩定區分所有高度內部類別，例如 body height、stand-off height、total height。
- 能處理 mirror handedness 或 axis sign。
- `He` 這類尺寸語意是由本方法完整穩定解出。
- Stage 2 單獨判斷 direct height answer 正誤。

## 對讀者的主句

建議摘要與方法圖使用這個句子：

```text
We do not ask the model to guess height again. We first extract reliable
low-level signals, then construct height evidence from top-view-grounded rules,
and finally screen the model's direct height answer as Supported, Contradicted,
or Insufficient Evidence.
```

