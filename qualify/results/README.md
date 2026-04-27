# qualify results

E008 合格後の最終昇格結果 JSON を保存する場所です。

保存形式:

- `qualify/results/{slot_id}/{result_id}.json`
- `qualify/results/archived/{slot_id}/{version_id}/{result_id}.json`

この JSON は `src/timer_entry/schemas.py` の `QualifyPromotionResult` に従います。
`qualify/params/{slot_id}/{version_id}/` は実験入力、`qualify/results/{slot_id}/` は昇格判定済みの結果成果物として扱います。
`qualify/results/archived/{slot_id}/{version_id}/` は、不合格、やり直し前、regime 変更などで現役から外れた結果成果物の保管場所です。既存の旧候補アーカイブは `v0` を使います。

運用メモ:

- runtime に必要な採用値は top-level に置きます。
- E005 / E007 / E008 の sweep 成績は `evidence` に要約して残します。
- 全 trade や全 equity curve は転記せず、元 CSV への参照と主要 summary row の数値だけを残します。
