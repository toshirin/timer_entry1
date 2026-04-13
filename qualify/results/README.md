# qualify results

E008 合格後の最終昇格結果 JSON を保存する場所です。

保存形式:

- `qualify/results/{slot_id}/{result_id}.json`

この JSON は `src/timer_entry/schemas.py` の `QualifyPromotionResult` に従います。
`qualify/params/` は実験入力、`qualify/results/` は昇格判定済みの結果成果物として扱います。
