# qualify E005-E008 thread

このスレッドでは `qualify/E005-E008` をまとめて議論してください。
対象は E004 を通過した setting です。
コード生成は不要です。E005-E008 suite の sweep 範囲と実行条件を決め、最後に Codex 実行用 JSON を出してください。

主目的は以下です。

- E005
  - slippage 耐性
- E006
  - walk-forward / holdout
- E007
  - risk_fraction / kill-switch / 維持率
- E008
  - entry delay 耐性

## 前提

- E004 は独立の昇格審査です
- E005-E008 はその後段の robustness suite です
- デフォルト実行は `qualify/e005-e008.py` の一括実行です
- 単独確認が必要なら `--only E005` のように実行します
- params は `qualify/params/{slot_id}/e005-e008.json` を新規に出力します
- E004 の baseline setting は `e005-e008.json` にコピーして固定します
- E005 の `slip_pips` は one-way 表示です
- E005 では entry / exit の両方に slip を乗せるので、実質往復 penalty は `2 * slip_pips` です
- E007 の risk grid は `SL5 -> risk_fraction 0.5%` を基準に、現在の SL 幅へ換算して考えてください
- E007 では最低証拠金維持率、`annualized_pips`、`trade_rate`、`win_rate`、`CAGR` を必ず確認してください

## あなたに依頼したいこと

1. E005-E008 のうち、今回実行対象にする experiment を決めてください
2. E005 の `slippage_values` を決めてください
3. E008 の `entry_delay_values` を決めてください
4. E007 の `risk_fractions` と `kill_switch_dd_pct` を決めてください
5. E005 の one-way 表示と往復 penalty の読み替えを明記してください
6. E007 の基準 risk と、その前後の比較点を明記してください
7. 最後に `E005-E008` 用 JSON を必ず `json` コードブロックで出してください

## 出力形式

以下の順で出してください。

1. 結論
2. E005-E008 の実行方針
3. sweep / risk grid
4. 評価観点
5. E005 の slip 解釈
6. E007 の risk grid
7. Codex 実行用 JSON

## JSON 形式

以下のキーを基本としてください。

```json
{
  "experiment_code": "E005-E008",
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
  "selected_experiments": ["E005", "E006", "E007", "E008"],
  "slippage_mode": "none",
  "fixed_slippage_pips": 0.0,
  "entry_delay_seconds": 0,
  "slippage_values": [0.0, 0.1, 0.2, 0.3],
  "entry_delay_values": [0, 30, 60, 120],
  "risk_fractions": [0.015, 0.03, 0.06],
  "kill_switch_dd_pct": -0.2,
  "initial_capital_jpy": 100000,
  "notes": "short rationale"
}
```

`slippage_values` は one-way の値です。
`risk_fractions` は `SL5 -> 0.5%` を基準に、現在の `sl_pips` に換算して決めてください。
