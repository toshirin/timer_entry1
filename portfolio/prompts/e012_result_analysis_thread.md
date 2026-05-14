# portfolio E012 result analysis thread

このスレッドでは、Codex 側で実行した `portfolio` E012 の結果 CSV を分析してください。
目的は、`Unit_Level_Policy.md` に基づく自動昇降格で、太い edge が高 level に落ち着くか、細い edge が低 level に留まるかを検証することです。

## 必須: Code Interpreter 使用

必ず Code Interpreter / Python を使って添付 CSV を読み込んでください。
目視だけで結論を出さないでください。

- 各 CSV を `pandas.read_csv()` で読み込む
- 読み込んだファイル名、行数、列名、主要列の欠損状況を確認する
- `setting_level_history.csv` から setting ごとの最終 level、平均 level、level 7 滞在月数、level 0 滞在月数を計算する
- `initial_level_source` を確認し、高 level start の override がある場合はその影響を分けて評価する
- `summary.csv` の `max_dd_pct`, `max_dd_jpy`, `worst_month_pnl_jpy`, `worst_trade_pnl_jpy`, `max_consecutive_losses` を確認する
- `realized_after_conflict` と `theoretical_without_conflict` を比較する
- `unlimited` と `equity_basis_cap_100m_jpy` を比較する
- conflict により昇格が阻害された可能性がある setting を抽出する
- 必要列が不足している場合は結論を出さず、不足ファイルまたは不足列を明記する

## 添付する資料

必須:

- `portfolio/out/E012/latest/summary.csv`
- `portfolio/out/E012/latest/setting_summary.csv`
- `portfolio/out/E012/latest/setting_monthly_pnl.csv`
- `portfolio/out/E012/latest/setting_level_history.csv`
- `portfolio/out/E012/latest/setting_level_pivot.csv`
- `portfolio/out/E012/latest/equity_curve.csv`
- `portfolio/out/E012/latest/input_summary.csv`
- `portfolio/out/E012/latest/params.json`
- `portfolio/out/E012/latest/metadata.json`

必要に応じて:

- `portfolio/out/E012/latest/trade_ledger.csv`

## 見てほしいこと

1. `realized_after_conflict` と `theoretical_without_conflict` の final equity / trade count / PnL 差
2. `unlimited` と `equity_basis_cap_100m_jpy` の差
3. max DD、worst month、worst trade、連敗数、PF から見た unit level policy の効き方
4. setting ごとの level 推移
5. 高 level start した setting が維持できたか、低 level に留まった setting
6. watch label により Level 0 固定になっている setting
7. conflict がなければ昇格していた可能性がある setting
8. Unit Level Policy の閾値が過敏または鈍すぎないか

## 出力形式

以下の順で出してください。

1. 結論
2. basis / sizing_mode 別の主要指標
3. setting 別 level 推移の要約
4. 太い edge / 細い edge の分類
5. conflict による昇格阻害候補
6. 次のアクション
