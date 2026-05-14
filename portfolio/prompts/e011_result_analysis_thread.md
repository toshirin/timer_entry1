# portfolio E011 result analysis thread

このスレッドでは、Codex 側で実行した `portfolio` E011 の結果 CSV を分析してください。
目的は、setting 間 conflict がポートフォリオ損益、DD、CAGR、機会損益に与えた影響を定量評価することです。

## 必須: Code Interpreter 使用

必ず Code Interpreter / Python を使って添付 CSV を読み込んでください。
目視だけで結論を出さないでください。

- 各 CSV を `pandas.read_csv()` で読み込む
- 読み込んだファイル名、行数、列名、主要列の欠損状況を確認する
- `summary.csv` の final equity、CAGR、max DD、executed / blocked 件数を確認する
- `summary.csv` の `max_dd_pct`, `max_dd_jpy`, `profit_factor`, `worst_trade_pnl_jpy`, `max_consecutive_losses` を確認する
- `basis=unlimited` と `basis=equity_basis_cap_100m_jpy` を分けて確認する
- conflict 判定が UTC 正規化済みの時系列で行われている前提で読む
- `conflict_events.csv` から blocker / blocked の関係を集計する
- `conflict_blocker_summary.csv` で、阻害して得をした組み合わせと損をした組み合わせを分ける
- 必要列が不足している場合は結論を出さず、不足ファイルまたは不足列を明記する

## 添付する資料

必須:

- `portfolio/out/E011/latest/summary.csv`
- `portfolio/out/E011/latest/setting_summary.csv`
- `portfolio/out/E011/latest/conflict_events.csv`
- `portfolio/out/E011/latest/conflict_blocker_summary.csv`
- `portfolio/out/E011/latest/equity_curve.csv`
- `portfolio/out/E011/latest/input_summary.csv`
- `portfolio/out/E011/latest/params.json`
- `portfolio/out/E011/latest/metadata.json`

必要に応じて:

- `portfolio/out/E011/latest/trade_ledger.csv`

## 見てほしいこと

1. conflict により、理論合計からどれだけ損益が削られたか
2. unlimited と equity basis cap 100m の差
3. max DD、worst trade、連敗数、PF から見た破綻リスク
4. block 件数が多い setting / block されやすい setting はどれか
5. `opportunity_delta_jpy` が大きい組み合わせはどれか
6. `blocked_positive_pnl_jpy_sum` と `blocked_negative_pnl_jpy_sum` の内訳
7. blocker 側の損益と blocked 側の機会損益を比較し、調停候補を挙げる
8. 現在の runtime 競合ルールを維持してよいか、見直し候補があるか

## 出力形式

以下の順で出してください。

1. 結論
2. ポートフォリオ主要指標
3. conflict 全体影響
4. blocker / blocked 組み合わせ別の重要論点
5. 調停候補
6. 次のアクション
