# qualify E004 thread

このスレッドでは `qualify/E004` だけを議論してください。
E003 通過候補を対象に、tick replay の execution 検証条件を確定してください。

最後に `E004` 用 JSON を出してください。

## JSON 形式

```json
{
  "experiment_code": "E004",
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
  "pass_stability_gate": true,
  "slippage_mode": "none",
  "fixed_slippage_pips": 0.0,
  "entry_delay_seconds": 0,
  "notes": "short rationale"
}
```
