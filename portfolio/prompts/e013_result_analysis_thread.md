# portfolio E013 result analysis thread

このスレッドでは、Codex 側で実行した `portfolio` E013 の結果 CSV を分析してください。
目的は、再投資 50%、税金 20%、手取り 30% の実運用寄りシミュレーションと、翌年引落日まで 100% 再投資できる複利効果を定量評価することです。

## 必須: Code Interpreter 使用

必ず Code Interpreter / Python を使って添付 CSV を読み込んでください。
目視だけで結論を出さないでください。

- 各 CSV を `pandas.read_csv()` で読み込む
- 読み込んだファイル名、行数、列名、主要列の欠損状況を確認する
- `deferred_withdrawal` と `immediate_withdrawal` を比較する
- `unlimited` と `equity_basis_cap_100m_jpy` を比較する
- `deferred_reinvestment_benefit_jpy` と `deferred_reinvestment_benefit_pct` を確認する
- `yearly_allocation.csv` から年別の課税対象利益、税金、手取り、損失繰越を確認する
- `setting_level_history.csv` から unit level 推移を確認する
- `initial_level_source` を確認し、高 level start の override がある場合は final equity / DD / cashflow への影響を分けて評価する
- `cashflow_events.csv` で終了年の強制精算が行われていることを確認する
- 必要列が不足している場合は結論を出さず、不足ファイルまたは不足列を明記する

## 添付する資料

必須:

- `portfolio/out/E013/latest/summary.csv`
- `portfolio/out/E013/latest/yearly_allocation.csv`
- `portfolio/out/E013/latest/cashflow_events.csv`
- `portfolio/out/E013/latest/equity_curve.csv`
- `portfolio/out/E013/latest/setting_level_history.csv`
- `portfolio/out/E013/latest/input_summary.csv`
- `portfolio/out/E013/latest/params.json`
- `portfolio/out/E013/latest/metadata.json`

必要に応じて:

- `portfolio/out/E013/latest/trade_ledger.csv`

## 見てほしいこと

1. deferred withdrawal と immediate withdrawal の final equity 差
2. unlimited と equity basis cap 100m の final equity 差
3. 翌年 2 月まで 100% 再投資できる効果の大きさ
4. 年別の taxable profit、tax、takehome、reinvest の内訳
5. 内部損失繰越と外部損失枠の使われ方
6. unit level 推移と final equity の関係
7. 高 level start した setting が維持できたか、final equity にどの程度寄与したか
8. 2025-12-31 など終了年の final settlement 後の最終 equity
9. 税金 / 手取り比率や引落日の感度分析が必要か

## 出力形式

以下の順で出してください。

1. 結論
2. deferred vs immediate / sizing_mode 別の主要指標
3. 年別 allocation
4. unit level 推移
5. cashflow と final settlement 確認
6. 複利効果の評価
7. 次のアクション
