# Unit Level Policy

この文書は、FX タイマー売買戦略の `unit level` を運用中に調整する方針を定義する。

目的は、`qualify` で審査済みの setting を前提に、通常時は月次でゆっくり unit size を調整し、kill-switch や異常検知では即時に 1 段縮小できるようにすることである。

本方針は、個別 setting の unit size 調整を扱う。複数 setting 間の資金配分最適化やポートフォリオ全体の rebalance は扱わない。

## 1. 基本方針

- 通常時の unit level 調整は月末バッチでのみ行う
- 通常時の判定材料は当月の確定損益 JPY のみとする
- 1 回の通常判定で動かす level は最大 1 段とする
- `label=watch` の setting は常に Level 0 固定とする
- Level 0 は固定 10 units とする
- Level 1 以上は `size_scale_pct` で管理する
- 月次損益が小さい場合は level を据え置く
- kill-switch 発動時は、月次判定を待たず即時に 1 段降格する
- 将来の異常検知でも、必要に応じて即時に 1 段降格する
- 即時降格系は通常の月次昇降格とは別系統の処理として実装する

通常の月次調整は、regime 変化時に自然に縮退し、回復時に自然に反攻するための仕組みである。異常時の停止、縮小、注文抑制は別の emergency handler が担当する。

## 2. Level 定義

| Level | mode | 値 |
|---|---|---|
| 0 | `fixed_units` | 10 |
| 1 | `size_scale_pct` | 0.1 |
| 2 | `size_scale_pct` | 0.3 |
| 3 | `size_scale_pct` | 1.0 |
| 4 | `size_scale_pct` | 3.0 |
| 5 | `size_scale_pct` | 10.0 |
| 6 | `size_scale_pct` | 30.0 |
| 7 | `size_scale_pct` | 100.0 |

Level 0 は試運転、監視、クーリング用の極小枠である。Level 1 以上は runtime の sizing logic に従い、`margin_ratio_target` と `size_scale_pct` から実効 units を解決する。

## 3. Watch ラベル

`label=watch` が付いている setting は、常に Level 0 とする。

```text
if "watch" in labels:
    next_level = 0
```

watch が付いている限り、当月損益がプラスでも昇格しない。watch が月中で外れた場合は、特別な待機期間を設けず、その月の月末判定から通常ルールを適用する。

## 4. 月次昇降格ルール

月末バッチでは、当月の確定損益 JPY を使って level を判定する。

使用する値は以下である。

- `current_level`: 判定時点の level
- `current_units`: 判定時点の実効 unit 数
- `cum_jpy_month`: 当月に決済済みの realized PnL JPY 合計
- `threshold_jpy`: 昇降格閾値

`cum_jpy_month` は決済済み損益のみとする。open position の unrealized PnL は月次昇降格判定に含めない。unrealized PnL は異常系ハンドラで扱う。

閾値は、現在の unit 数に対する 10 pips 相当額とする。

```text
threshold_jpy = 0.1 * current_units
```

判定は以下とする。

```text
if cum_jpy_month > threshold_jpy:
    next_level = min(current_level + 1, 7)
elif cum_jpy_month < -threshold_jpy:
    next_level = max(current_level - 1, 0)
else:
    next_level = current_level
```

`>` / `<` を使い、境界値は据え置きとする。つまり `cum_jpy_month == threshold_jpy` または `cum_jpy_month == -threshold_jpy` の場合、level は変えない。

## 5. Current Units の解決

月次判定で使う `current_units` は、runtime 本体の sizing logic と一致させる。

Level 0 の場合:

```text
current_units = 10
```

Level 1 以上の場合:

```text
current_units = compute_units(setting, account, price).requested_units
```

基準は、月末時点の `latest_equity_jpy` から runtime sizing logic で再計算した units とする。月次判定専用の別計算式は作らない。

ログには、少なくとも以下を残す。

```text
unit_basis = "month_end_latest_equity_runtime_compute_units"
latest_equity_jpy
current_units
```

## 6. 即時降格

通常の月次昇降格とは別に、以下のイベントでは即時に 1 段降格する。

- kill-switch 発動
- 将来追加する異常検知で、縮小が必要と判定された場合

即時降格は以下とする。

```text
next_level = max(current_level - 1, 0)
```

Level 0 より下には下げない。即時降格は月次判定とは別処理であり、月末を待たずに適用してよい。

即時降格の理由は、月次判定とは区別して記録する。

```text
source = "kill_switch"
decision = "demote"
decision_reason = "kill_switch_triggered"
```

異常検知の場合も同様に、`source` と `decision_reason` を分ける。

## 7. Runtime / Ops の責務境界

unit level policy は runtime と ops の両方にまたがるため、責務を分ける。

### runtime 側

runtime 側は、unit level 判定に必要な純粋ロジックと sizing logic を持つ。

想定する配置:

```text
runtime/src/timer_entry_runtime/level_policy.py
runtime/src/timer_entry_runtime/sizing.py
```

runtime 側の責務:

- Level 定義
- level から `fixed_units` / `size_scale_pct` への変換
- 月次判定の pure function
- 即時 1 段降格の pure function
- `compute_units()` による runtime sizing logic

### ops 側

ops 側は、月次 batch と永続化を担当する。

想定する配置:

```text
ops/src/timer_entry_ops/monthly_unit_level_policy.py
```

ops 側の責務:

- Aurora から当月 realized PnL を集計する
- 最新 equity を取得する
- 月末時点の price snapshot を用意する
- runtime の policy function を呼び出す
- runtime の setting config を更新する
- unit level decision log を保存する
- 月次 batch を冪等に実行する

## 8. Source of Truth

現在の level は runtime の setting config に明示的に持つ。

推奨属性:

```text
unit_level
unit_level_policy_name
unit_level_policy_version
unit_level_updated_at
unit_level_updated_by
unit_level_decision_month
```

Level 0 の setting config は以下の形にする。

```json
{
  "unit_level": 0,
  "fixed_units": 10,
  "size_scale_pct": null
}
```

Level 1 以上の setting config は以下の形にする。

```json
{
  "unit_level": 3,
  "fixed_units": null,
  "size_scale_pct": 1.0
}
```

`margin_ratio_target` は setting 固有の運用値として維持し、level 変更時には原則として変更しない。

## 9. Decision Log

unit level の変更履歴は、ops 側の分析 DB に保存する。

想定テーブル:

```text
ops_main.unit_level_decision_log
```

最低限保存する項目:

- `setting_id`
- `strategy_id`
- `slot_id`
- `instrument`
- `market_session`
- `decision_month`
- `policy_name`
- `policy_version`
- `labels`
- `source`
- `current_level`
- `next_level`
- `current_units`
- `threshold_jpy`
- `cum_jpy_month`
- `latest_equity_jpy`
- `unit_basis`
- `decision`
- `decision_reason`
- `applied`
- `applied_at`
- `created_at`

通常の月次判定では、`source = "monthly"` とする。kill-switch による即時降格では `source = "kill_switch"` とする。異常検知による即時降格では、異常種別に応じて `source` を分ける。

Level 上限や下限で実際には level が変わらない場合も、理由を分けて記録する。

例:

```text
decision = "keep"
decision_reason = "already_at_max_level_profit_above_threshold"
```

```text
decision = "keep"
decision_reason = "already_at_min_level_loss_below_threshold"
```

## 10. Idempotency

月次 batch は冪等に実行する。

同じ `setting_id` と `decision_month` に対して、通常の月次判定を重複適用してはならない。すでに適用済みの月次判定が存在する場合は、再実行時に同じ結果を返すか、`applied = false` として duplicate を記録する。

即時降格系は月次判定とは別の idempotency key を持つ。

例:

```text
monthly: setting_id + decision_month + source
kill_switch: setting_id + trigger_event_id + source
anomaly: setting_id + anomaly_event_id + source
```

## 11. JSON 設定例

```json
{
  "schema_version": 1,
  "policy_name": "unit_level_policy",
  "policy_version": "2026-04-17",
  "levels": [
    {
      "level": 0,
      "mode": "fixed_units",
      "fixed_units": 10
    },
    {
      "level": 1,
      "mode": "size_scale_pct",
      "size_scale_pct": 0.1
    },
    {
      "level": 2,
      "mode": "size_scale_pct",
      "size_scale_pct": 0.3
    },
    {
      "level": 3,
      "mode": "size_scale_pct",
      "size_scale_pct": 1.0
    },
    {
      "level": 4,
      "mode": "size_scale_pct",
      "size_scale_pct": 3.0
    },
    {
      "level": 5,
      "mode": "size_scale_pct",
      "size_scale_pct": 10.0
    },
    {
      "level": 6,
      "mode": "size_scale_pct",
      "size_scale_pct": 30.0
    },
    {
      "level": 7,
      "mode": "size_scale_pct",
      "size_scale_pct": 100.0
    }
  ],
  "watch_rule": {
    "label_equals": "watch",
    "forced_level": 0
  },
  "monthly_rule": {
    "metric": "cum_jpy_month",
    "pnl_basis": "realized_only",
    "threshold_formula": "0.1 * current_units",
    "promote_if": "cum_jpy_month > threshold_jpy",
    "demote_if": "cum_jpy_month < -threshold_jpy",
    "otherwise": "keep",
    "step_size": 1,
    "min_level": 0,
    "max_level": 7
  },
  "unit_resolution": {
    "level0_fixed_units": 10,
    "use_runtime_sizing_logic": true,
    "unit_basis": "month_end_latest_equity_runtime_compute_units"
  },
  "emergency_demotion": {
    "kill_switch": {
      "enabled": true,
      "step_size": 1,
      "min_level": 0
    },
    "anomaly_detection": {
      "enabled": true,
      "step_size": 1,
      "min_level": 0
    }
  }
}
```

## 12. 実装順序

実装する場合は、以下の順で進める。

1. runtime 側に unit level policy の pure function を追加する
2. pure function の単体テストを追加する
3. setting config に `unit_level` 系属性を追加する
4. ops 側に `unit_level_decision_log` を追加する
5. ops 側に月次 batch を追加する
6. monthly decision の冪等性を確認する
7. kill-switch の即時 1 段降格を同じ apply logic で追加する
8. 将来の異常検知から同じ apply logic を呼べるようにする

初版では、月次の通常昇降格を優先する。kill-switch と異常検知による即時降格は、同じ level apply logic を使う別入口として実装する。
