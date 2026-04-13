# qualify results

E008 合格後の最終昇格結果 JSON を保存する場所です。

保存形式:

- `qualify/results/{slot_id}/{result_id}.json`

この JSON は `src/timer_entry/schemas.py` の `QualifyPromotionResult` に従います。
`qualify/params/` は実験入力、`qualify/results/` は昇格判定済みの結果成果物として扱います。

運用メモ:

- runtime に必要な採用値は top-level に置きます。
- E005 / E007 / E008 の sweep 成績は `evidence` に要約して残します。
- 全 trade や全 equity curve は転記せず、元 CSV への参照と主要 summary row の数値だけを残します。
