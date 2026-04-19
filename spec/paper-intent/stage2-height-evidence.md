# Paper Intent Spec: Stage 2 Height Evidence

## 階段意圖

Stage 2 是本研究的核心方法階段。它把 Stage 1 的低階輸入轉成可解釋的 height evidence result。

這一階段不直接判斷模型 direct height answer 對錯。它回答的是：

```text
Can we construct reliable height evidence from the extracted low-level signals?
```

## 2A Evidence Fusion 的意圖

Evidence Fusion 的角色是把三份 Stage 1 outputs 整理成 rule engine 可使用的 internal evidence object。

它檢查：

- layout 是否有效。
- dimension extraction 與 top-view detection 的 layout 是否一致。
- occupied slots 是否被 views 完整覆蓋。
- top-view slot 是否在 occupied slots 中。
- dimensions 是否有 numeric value、orientation、belongs-to-slot。

Fusion 不是高度驗證，也不是 ground truth correction。它只建立可供後續規則使用的 evidence surface。

## 2B Evidence Audit 的意圖

Evidence Audit 是實驗透明化工具。若有 ground truth，它回答：

- OCR value extraction 品質如何？
- dimension orientation 是否可靠？
- belongs-to-slot assignment 是否可靠？
- top-view detection 是否可靠？
- layout 是否一致或正確？

Audit 的論文價值是 error attribution。當 Stage 3 無法 support 一個答案時，研究者可以回頭看是 low-level evidence extraction 失敗，還是 rule construction 本身不足。

Audit 不進入主流程，也不修正模型輸入。這一點很重要，因為 screening 效果必須來自 model output 與 rules，而不是 ground truth leakage。

## 2C Height Evidence Construction 的意圖

Height Evidence Construction 使用 top-view-grounded rules：

- 若非 top-view 與 top-view 水平相鄰，該 view 中的 horizontal dimension lines 是高度候選支撐。
- 若非 top-view 與 top-view 垂直相鄰，該 view 中的 vertical dimension lines 是高度候選支撐。
- 若另一個非 top-view 沒有直接與 top-view 相鄰，但與已 grounded 非 top-view 相鄰，它繼承相同 z-axis orientation。

這個設計刻意避免要求完整三視圖身份。系統只使用 top-view anchor、slot adjacency、dimension line orientation 這些低階訊號。

## Bucket 的研究意義

Stage 2 輸出三個 bucket：

- `supporting_dimensions`：目前規則可支撐為 height evidence 的 dimensions。
- `ruled_out_dimensions`：目前規則可排除為非 height evidence 的 dimensions。
- `unresolved_dimensions`：低階 evidence 不足或 local invalid，無法分類的 dimensions。

這三個 bucket 讓論文可以表達：

- 哪些圖面 evidence 真正支撐高度。
- 哪些值雖然被 OCR 到，但不該用來支撐高度。
- 哪些情況系統需要保守，不應自動採信。

## `constructed` 與 `ready`

Stage 2 case-level 狀態只應理解為 construction status：

- `constructed`：已建立 height evidence result。
- `insufficient`：無法建立可靠 height evidence result。

`constructed` 不等於可驗證。`verification_readiness.status == ready` 才表示 evidence set 足以交給 Stage 3 做 direct answer screening。

這個分層避免把 Stage 2 誤解成 answer classifier，也避免把 partial evidence 過度解讀為可支持答案。

## Stage 2 成果可以代表什麼

Stage 2 可回答：

- 規則能否從低階 evidence 建構出 height evidence？
- 哪些 dimensions 支撐高度，哪些被排除，哪些仍未解？
- z-axis orientation 是如何從 top-view adjacency 推導或傳播的？
- 目前 evidence 是否 ready for verification？

Stage 2 不回答：

- direct height answer 是否正確。
- model 是否應被 accept/reject。
- ground truth height 是多少。

