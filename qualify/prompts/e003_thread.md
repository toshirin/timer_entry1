# qualify E003 thread

このスレッドでは `qualify/E003` だけを議論してください。
E002 通過候補を固定し、forced exit 時刻の小規模 sweep を決めてください。

最後に `E003` 用 JSON を必ず `json` コードブロックで出してください。

## JSON 形式

```json
{
  "experiment_code": "E003",
  "variant_code": null,
  "slot_id": "lon08",
  "side": "buy",
  "baseline": {
    "entry_clock_local": "08:40",
    "forced_exit_clock_local": "09:45",
    "tp_pips": 10,
    "sl_pips": 30,
    "filter_labels": ["vol_ge_p70"]
  },
  "forced_exit_values": ["09:35", "09:45", "09:55"],
  "pass_stability_gate": true,
  "notes": "short rationale"
}
```
