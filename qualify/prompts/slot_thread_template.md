# scan slot thread template

このスレッドでは、特定 slot の `qualify/E001` 着手内容だけを議論してください。
コード生成は不要です。scan 結果の解釈と、次に試す閾値群の提案に集中してください。
最後に Codex 側で実行しやすい JSON を必ず出してください。

## 対象

- slot: `{slot_id}`
- side: `{side}`

## 前提

- scan は filter family の当たりを見る段階です
- qualify/E001 は scan で反応した family の threshold sweep を行う段階です
- Bid/Ask、same-bar、保守的 SL exit、event time の扱いは core で固定済みです
- `strategy / slot / setting` の意味は添付資料に従ってください

## あなたに依頼したいこと

1. この slot / side の scan 結果から、E001 で最初に深掘るべき filter family を選んでください
2. その family について、最初に試す閾値群を提案してください
3. `all` を残すべきか外すべきかを判断してください
4. `tp/sl` の初手候補を絞ってください
5. `same_bar_conflict_count` と `same_bar_unresolved_count` を踏まえて、execution 上の注意点があれば書いてください
6. 最後に Codex 実行用 JSON を出してください

## 出力形式

以下の順で出してください。

1. 結論
2. 根拠
3. E001 の初手パラメータ案
4. 注意点
5. Codex 実行用 JSON

## JSON 形式

以下のキーを基本としてください。

```json
{
  "experiment_code": "E001",
  "variant_code": null,
  "slot_id": "tyo09",
  "side": "buy",
  "baseline": {
    "entry_clock_local": "09:25",
    "forced_exit_clock_local": "10:20",
    "tp_pips": 5,
    "sl_pips": 15,
    "filter_labels": ["all"]
  },
  "comparison_family": "pre_open_slope",
  "comparison_labels": ["all", "ge0", "ge2", "ge4"],
  "notes": "short rationale"
}
```

`variant_code` は `E001A` のような派生が必要なときだけ使ってください。

## 添付する資料

- `docs/FX_Research_Constitution.md`
- `src/timer_entry/Spec.md`
- `src/timer_entry/schemas.py`
- `src/timer_entry/filters.py`
- この slot の `per_slot/summary_{slot_id}.csv`
- 必要なら今回 run の `reports/summary_report.md`
