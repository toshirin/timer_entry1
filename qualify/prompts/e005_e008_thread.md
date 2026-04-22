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
  - target maintenance margin / kill-switch / 維持率
- E008
  - entry delay 耐性

## 前提

- E004 は独立の昇格審査です
- E005-E008 はその後段の robustness suite です
- デフォルト実行は `qualify/e005-e008.py` の一括実行です
- 単独確認が必要なら `--only E005` のように実行します
- E007 を新思想でやり直す場合など、既存出力を残したい派生再実験は `--only E007 --output-alias E007=E007A` のように保存先を分けます
- params は `qualify/params/{slot_id}/e005-e008.json` を新規に出力します
- E004 の baseline setting は `e005-e008.json` にコピーして固定します
- E005 の `slip_pips` は one-way 表示です
- E005 では entry / exit の両方に slip を乗せるので、実質往復 penalty は `2 * slip_pips` です
- E007 は risk_fraction の最適化ではなく、採用する `target_maintenance_margin_pct` を決める審査です
- E007 の通常候補は `target_maintenance_margin_candidates: [150, 180, 200]` としてください
- 150/180/200 で問題が消えない、または弱い edge を捨てたくない setting では `[150, 180, 200, 230, 260]` まで拡張してよいです
- E007 の採用判断は CAGR 最大ではなく、低い維持率候補から順に見て安全条件を満たした最初の候補を採用してください
- `maintenance_below_100_count > 0` は一発NGです
- `stop_triggered == true` または `maintenance_below_130_count > 0` は、その維持率が強すぎるシグナルとして一段上の候補を確認してください
- 120%ラインは採用判定に使わないでください
- E007 の結果分析では各 target maintenance margin について、少なくとも `target_maintenance_margin_pct`, `annualized_pips`, `cagr`, `trade_rate`, `win_rate`, `max_dd_pct`, `min_maintenance_margin_pct`, `maintenance_below_130_count`, `maintenance_below_100_count`, `stop_triggered`, `final_equity_jpy`, `total_return_pct`, `pips_year_rate_pct_at_150usd` を本文に数値で出してください
- `pips_year_rate_pct_at_150usd` は `166.67 / target_maintenance_margin_pct` の近似指標として、`annualized_pips` と `cagr` の関係を読む補助にしてください

## あなたに依頼したいこと

1. E005-E008 のうち、今回実行対象にする experiment を決めてください
2. E005 の `slippage_values` を決めてください
3. E008 の `entry_delay_values` を決めてください
4. E007 の `target_maintenance_margin_candidates` と `kill_switch_dd_pct` を決めてください
5. E005 の one-way 表示と往復 penalty の読み替えを明記してください
6. E007 の維持率候補、130%警戒線、100%絶対NG、採用順序を明記してください
7. 最後に `E005-E008` 用 JSON を必ず `json` コードブロックで出してください

## 出力形式

以下の順で出してください。

1. 結論
2. E005-E008 の実行方針
3. sweep / maintenance margin grid
4. 評価観点
5. E005 の slip 解釈
6. E007 の maintenance margin grid
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
  "target_maintenance_margin_candidates": [150, 180, 200],
  "kill_switch_dd_pct": -0.2,
  "initial_capital_jpy": 100000,
  "notes": "short rationale"
}
```

`slippage_values` は one-way の値です。
`target_maintenance_margin_candidates` は通常 `[150, 180, 200]` とし、必要な場合だけ `[150, 180, 200, 230, 260]` へ拡張してください。
