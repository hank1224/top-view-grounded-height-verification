# Paper Intent Spec: Result Interpretation And Metrics

## 三層結果呈現

論文結果應分成三層呈現，而不是把三個 stage 都寫成狀態分類器。

這種分層能讓讀者看出：

- 低階 evidence 是否可靠。
- 規則是否能建構 height evidence。
- Screening 是否能降低錯誤高度答案被採信的風險。

## 第一層：Low-Level Evidence Quality

對應 Stage 1 與 Stage 2B audit。

主要問題：

```text
模型提供的低階證據是否可靠？
```

建議指標：

- OCR value precision / recall / F1
- dimension line orientation accuracy
- slot assignment accuracy
- top-view detection accuracy
- layout consistency / correctness

這一層幫助區分：若 screening 失敗，是因為規則不夠，還是因為低階 evidence 已經錯了。

## 第二層：Height Evidence Construction Quality

對應 Stage 2 height evidence construction。

主要問題：

```text
規則引擎能否從低階 evidence 建構出可用的高度證據？
```

建議指標：

- constructed rate
- verification-ready rate
- insufficient rate
- supporting dimension count
- ruled-out dimension count
- unresolved dimension count
- rule count distribution

若有 height-supporting dimension ground truth，可進一步計算 supporting dimension precision / recall / F1；目前實作主要輸出 construction 與 bucket-level diagnostics。

## 第三層：Height Answer Screening Effect

對應 Stage 3。

主要問題：

```text
框架是否能把錯誤高度答案攔下來，
同時保留部分可安全放行的答案？
```

建議指標：

- Raw direct-answer height accuracy
- Supported precision
- Wrong-answer interception rate
- Unsafe support rate
- Coverage
- Contradicted / Insufficient Evidence distribution
- Screening decision by ground-truth correctness

## 指標解讀

`raw_height_accuracy`：

- direct answer 與 ground truth height 相等的比例。
- 表示未經 screening 的模型高度答案品質。

`supported_precision`：

- 被系統 supported 的 answers 中，有多少 ground-truth correct。
- 這是「安全放行」品質的核心指標。

`unsafe_support_rate`：

- ground-truth wrong answers 中，有多少仍被 supported。
- 越低越好，代表錯誤答案較少被直接採信。

`coverage`：

- evaluated cases 中，有多少被 supported。
- 反映系統願意自動採信的範圍。

`wrong_answer_interception_rate`：

- ground-truth wrong answers 中，被 contradicted 或 insufficient evidence 攔下的比例。
- 這是 screening effect 的核心風險降低指標。

## Shape-class 與 provider 分析

Reporting 依 provider、shape class、shape-class/provider 組合輸出 metrics。

論文可用這些切面討論：

- 不同 provider 的低階 evidence extraction 差異。
- 不同 package shape class 是否較容易建構 height evidence。
- Screening failure 是否集中在特定 morphology 或 model behavior。

## Caveats

結果解讀需保留以下限制：

- Ground truth audit 是 side channel，不代表主流程使用 ground truth。
- `Insufficient Evidence` 不等於模型答案錯。
- `Contradicted` 是相對於目前 extracted evidence 與 rules 的衝突，不是完整工程圖語意裁決。
- Coverage 太高但 unsafe support rate 高，表示系統過度放行。
- Coverage 低但 interception rate 高，表示系統保守，但仍可能有實用價值。
- Stage 2/3 成果應與 Stage 1 low-level quality 一起看，避免把低階抽取錯誤誤判成規則失效。

