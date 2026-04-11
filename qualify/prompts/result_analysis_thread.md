# qualify result analysis thread

このスレッドでは、Codex 側で実行した `qualify` 結果 CSV の分析だけを行ってください。
新しい JSON を出す必要がある場合を除き、次実験の実行条件づくりには進まず、まず結果の合否と論点を整理してください。

## 前提

- `qualify/docs/Ops.md` では、experiment 別の params 作成プロンプトを「プロンプト1」と呼びます
- `qualify/docs/Ops.md` では、この結果分析プロンプトを「プロンプト2」と呼びます
- プロンプト1で params JSON を決め、Codex 側で `e00N.py` または `e005-e008.py` を実行済みです
- プロンプト2では、結果 CSV を読み、目的値が決まったか / 安全が確認されたかを判断します
- E001 で問題があれば、派生実験 `E001A` のように新しい params JSON を出してよいです
- E005 の `slip_pips` は one-way 表示で、実質往復 penalty は `2 * slip_pips` です
- E007 では `min_maintenance_margin_pct`, `annualized_pips`, `trade_rate`, `win_rate`, `CAGR` を必ず確認してください

## 添付する資料

- 対象 experiment の `summary.csv`
- `split_summary.csv`
- `year_summary.csv`
- 必要なら `trades.csv`
- E004 以降では `sanity_summary.csv`
- E007 では必要なら `equity_curve.csv`
- 実行に使った `params.json`

## あなたに依頼したいこと

1. 結果 CSV から、今回の目的値が決まったか判断してください
2. gross 最大だけでなく、PF、maxDD、in/out、trade_count、sanity を併せて見てください
3. E005 では one-way slip と往復 penalty の読み替えを明記してください
4. E007 では維持率と CAGR を含めて安全性を判断してください
5. 問題がなければ次 experiment へ進む結論を出してください
6. 問題があれば、派生実験として再実験 JSON を `json` コードブロックで出してください

## 出力形式

以下の順で出してください。

1. 結論
2. 主要指標
3. 安全性 / sanity 確認
4. 採用する値
5. 次のアクション
6. 再実験が必要な場合のみ Codex 実行用 JSON
