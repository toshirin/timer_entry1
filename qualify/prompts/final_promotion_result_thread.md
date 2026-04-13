# qualify final promotion result thread

このスレッドでは、E008 まで合格した setting について、runtime 昇格用の最終結果 JSON を作成してください。
この JSON は実験入力 params ではなく、E004-E008 の安全性確認結果を含む「昇格判定済み成果物」です。

## 前提

- E004 tick replay が合格済みであること
- E005 slippage 耐性が合格済みであること
- E006 walk-forward / holdout が合格済みであること
- E007 risk_fraction / kill-switch / 維持率が合格済みであること
- E008 entry delay 耐性が合格済みであること
- E005 の `slip_pips` は one-way 表示で、実質往復 penalty は `2 * slip_pips` です
- E007 では `selected_risk_fraction`, `kill_switch_dd_pct`, `min_maintenance_margin_pct`, `initial_capital_jpy` を明示してください
- 結果 JSON では、後から取り出したい主要指標を `evidence` の中だけでなく top-level にも入れてください

## 添付する資料

- `qualify/params/{slot_id}/e004.json`
- `qualify/params/{slot_id}/e005-e008.json`
- E004 の `summary.csv` / `sanity_summary.csv`
- E005-E008 の各 `summary.csv`
- E007 の `equity_curve.csv` が必要なら添付
- 結果分析スレッドの結論

## あなたに依頼したいこと

1. E004-E008 がすべて合格か確認してください
2. runtime へ昇格してよいかを `approved_for_runtime` で明示してください
3. 採用する setting 条件を固定してください
4. 採用する risk / kill-switch 条件を固定してください
5. 根拠となる主要指標を top-level に入れ、補足を `evidence` に短くまとめてください
6. 最後に Codex 保存用 JSON を必ず `json` コードブロックで出してください

## 保存先

Codex 側では以下に保存します。

- `qualify/results/{slot_id}/{result_id}.json`

## JSON 形式

```json
{
  "result_type": "qualify_promotion_result",
  "schema_version": 1,
  "result_id": "{slot_id}_buy_v1",
  "slot_id": "{slot_id}",
  "side": "buy",
  "market_tz": "Europe/London",
  "entry_clock_local": "15:40",
  "forced_exit_clock_local": "16:45",
  "tp_pips": 15,
  "sl_pips": 20,
  "filter_labels": ["right_stronger"],
  "pass_stability_gate": true,
  "e004_passed": true,
  "e005_passed": true,
  "e006_passed": true,
  "e007_passed": true,
  "e008_passed": true,
  "approved_for_runtime": true,
  "selected_risk_fraction": 0.0015,
  "kill_switch_dd_pct": -0.2,
  "min_maintenance_margin_pct": 150.0,
  "initial_capital_jpy": 100000,
  "final_equity_jpy": 101000.0,
  "annualized_pips": 12.3,
  "cagr": 0.01,
  "trade_rate": 0.42,
  "gross_pips": 86.1,
  "in_gross_pips": 55.0,
  "out_gross_pips": 31.1,
  "win_rate": 0.54,
  "source_params_files": {
    "E004": "qualify/params/{slot_id}/e004.json",
    "E005-E008": "qualify/params/{slot_id}/e005-e008.json"
  },
  "source_output_dirs": {
    "E004": "qualify/out/{slot_id}/E004/latest",
    "E005-E008": "qualify/out/{slot_id}"
  },
  "evidence": {
    "E004": {
      "summary": "tick replay sanity passed"
    },
    "E005": {
      "max_one_way_slip_pips_passed": 0.3,
      "max_round_trip_slip_pips_passed": 0.6
    },
    "E006": {
      "summary": "walk-forward accepted"
    },
    "E007": {
      "min_maintenance_margin_pct": 150.0,
      "annualized_pips": 0.0,
      "trade_rate": 0.0,
      "win_rate": 0.0,
      "cagr": 0.0
    },
    "E008": {
      "max_entry_delay_seconds_passed": 15
    }
  },
  "notes": "short rationale"
}
```
