# qualify E002 thread

このスレッドでは `qualify/E002` だけを議論してください。
E001 通過候補を固定し、TP/SL の小規模 sweep を決めてください。

最後に `E002` 用 JSON を必ず `json` コードブロックで出してください。

## JSON 形式

```json
{
  "experiment_code": "E002",
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
  "tp_values": [10, 15, 20],
  "sl_values": [20, 25, 30],
  "pass_stability_gate": true,
  "notes": "short rationale"
}
```
