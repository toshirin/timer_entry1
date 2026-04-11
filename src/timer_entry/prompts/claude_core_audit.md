# Claude Code audit prompt for timer_entry core

この依頼では、`timer_entry1` の core 実装を監査してください。
主目的は、Bid/Ask、same-bar、event time、scan/qualify/runtime 間の仕様整合性の確認です。
新機能提案や大規模リファクタ提案よりも、仕様逸脱・実装バグ・監査上の盲点の発見を優先してください。

## あなたの役割

- 仕様監査者
- 実装差分レビュー担当
- 特に Bid/Ask と same-bar の独立監査担当

## 前提

- この repo はタイマー売買戦略専用 repo です
- `strategy / slot / setting` の意味は repo の定義に従ってください
- 実装仕様は添付の Constitution / README / Spec に固定されています
- `scan` / `qualify` / `runtime` は core の仕様を共有します
- 監査対象は主に `src/timer_entry/` です

## 最重要監査項目

1. Bid / Ask 完全分離
2. Buy / Sell の鏡像性
3. entry バー内 TP / SL 判定禁止
4. same-bar 競合時の `*_Time` 利用
5. `*_Time` 不明時の不利側優先
6. 保守的 SL exit モデル
7. feature 定義の canonical 固定
8. filter 定義の canonical 固定
9. `backtest_1m.py` と `backtest_fast.py` の仕様一致
10. `minute_data.py` の時刻 fallback と event time 正規化

## 監査対象ファイル

- `docs/FX_Research_Constitution.md`
- `README.md`
- `src/timer_entry/Spec.md`
- `src/timer_entry/direction.py`
- `src/timer_entry/time_utils.py`
- `src/timer_entry/minute_data.py`
- `src/timer_entry/features.py`
- `src/timer_entry/filters.py`
- `src/timer_entry/schemas.py`
- `src/timer_entry/backtest_1m.py`
- `src/timer_entry/backtest_fast.py`
- `src/timer_entry/tests/test_backtest_parity.py`
- `src/timer_entry/tests/test_event_times.py`

必要に応じて、参照用として以下の旧実装も見てください。

- `fx_260312/research/probe5`
- `fx_260312/research/jst09_exhaustive1`
- `fx_260312/research/jst10_exhaustive1`
- `fx_260312/research/jst12_exhaustive1`
- `fx_260312/research/lon08_exhaustive1`
- `fx_260312/infer/timed_entry_runtime1`

## 出力形式

以下の順で出してください。

### Findings

- severity を `High / Medium / Low` で付けてください
- まずバグ、仕様逸脱、監査上の重大懸念を列挙してください
- 可能ならファイル名と行付近を示してください

### Open questions

- 判断に迷う点
- 仕様として明文化した方がよい点

### Residual risks

- 現時点では通っていても、将来崩れやすい点

## 特に見てほしい具体論点

- Buy の SL trigger と SL exit の価格系列が本当に一致しているか
- Sell の SL trigger と SL exit の価格系列が Buy の鏡像になっているか
- `probe5` 由来の高速 engine に、旧来の exit 価格バグが残っていないか
- `same_bar_unresolved_count` の意味が slow / fast で一致しているか
- event time 列の naive / aware 混在時に、誤って `NaT` へ落ちる経路がないか
- `scan` と `qualify` が filter family / threshold の意味をずらさずに使えるか

## 注意

- 「改善案」よりも「監査結果」を優先してください
- 既存の tests が通ることだけを根拠に安全と断定しないでください
- 憲法違反の可能性があるものは、小さな差でも指摘してください
