# Paper Intent Spec: Stage 3 Answer Screening

## 階段意圖

Stage 3 是 height answer screening。它使用 Stage 2 的 `supporting_dimensions` 檢查模型 direct answer，而不是重新讓模型推理。

它回答：

```text
Given constructed and ready height evidence, should the model's direct
overall package height answer be treated as Supported, Contradicted,
or Insufficient Evidence?
```

## 為什麼使用 `max(supporting_dimensions.numeric_value)`

對 `overall_package_height / A` 而言，若 height evidence set 足夠完整，總高度可由 supporting dimensions 的最大 numeric value 推導。

因此 Stage 3 的 derived height rule 是：

```text
derived_height_value = max(supporting_dimensions.numeric_value)
```

這個 rule 只在 `verification_readiness.status == ready` 時成立。若 evidence 不 ready，系統必須回到 `Insufficient Evidence`，不能用 partial evidence 強行 support 或 contradict。

## 三種篩檢結果

### Supported

`Supported` 表示 direct height answer 有圖面 height evidence 支撐。

必要條件：

- Stage 2 constructed。
- Verification ready。
- Model 提供 numeric `overall_package_height`。
- 至少一個 numeric supporting dimension 存在。
- Model value 等於 derived height value。
- Supporting dimension 有 evidence chain。

### Contradicted

`Contradicted` 表示 direct height answer 與目前圖面 evidence 衝突。

典型情況：

- Model value 出現在 `ruled_out_dimensions`。
- Model value 雖然是 supporting dimension，但不是 supporting max，因此不應作為 overall height。

這類結果是本方法降低高度 hallucination risk 的主要機制。

### Insufficient Evidence

`Insufficient Evidence` 表示目前不能自動採信 direct answer。

常見原因：

- Stage 2 insufficient。
- Verification not ready。
- Model 沒有提供 numeric height。
- Model value 不在 OCR dimension values 中。
- 沒有 numeric supporting dimensions。
- 單位或 evidence chain 無法比較。

它不是錯誤分類，而是保守 abstention。論文表述應避免把 insufficient evidence 寫成模型答案必然錯。

## Stage 3 成果可以代表什麼

Stage 3 可回答：

- 框架是否能安全 support 某些 correct direct answers？
- 框架是否能攔截 direct answer 中的 height-related wrong answers？
- 框架在證據不足時是否能保守不採信？

Stage 3 不回答：

- 完整尺寸抽取任務是否成功。
- 所有 target dimensions 是否正確。
- 系統是否理解了所有 view identity。

## 對論文敘事的建議

Stage 3 不建議使用 `accept / reject / abstain` 作為主要名詞，因為它容易讓人誤會系統在評分整個模型輸出。

建議使用：

- `Supported`
- `Contradicted`
- `Insufficient Evidence`

這三個名稱更準確地表達它是 evidence-based screening，而不是 generic model grading。

