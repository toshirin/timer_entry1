# portfolio Spec

本仕様は、`runtime/config` で運用対象になっている複数 setting を束ね、資金運用、setting 間 conflict、自動昇降格、再投資と出金を検証する統合バックテストを定義する。

`portfolio` は個別 setting の品質検証ではなく、採用済み setting 群を同時運用した場合のポートフォリオ挙動を検証する領域である。

## 1. 目的

- runtime 採用済み setting 群を同時稼働させた場合の損益、DD、CAGR を確認する
- setting 間 conflict によって、どの setting がどの setting の機会損益を阻害したかを計測する
- `Unit_Level_Policy.md` に基づく自動昇降格で、太い edge が高 level に落ち着くかを検証する
- 税金、手取り、再投資、損失繰越を含む実運用寄りの資金推移を検証する
- 翌年指定日まで税金と手取りを引き落とさず、100%再投資できる複利効果を計測する

## 2. スコープ

対象実験は以下とする。

- `E011`: conflict 競合シミュレーション
- `E012`: 自動昇降格シミュレーション
- `E013`: 再投資 50%、税金 20%、手取り 30% シミュレーション

本仕様には以下を含む。

- 入力データの選択
- trade ledger の生成
- conflict 判定
- units と JPY 損益の計算
- unit level 推移の計算
- 税金、手取り、再投資、損失繰越の計算
- 出力ファイルの方針

本仕様には以下を含まない。

- 個別 setting の探索、選抜、昇格判断
- tick replay の再実行仕様
- 実 broker への発注処理
- runtime config の自動更新

## 3. ディレクトリ構成

想定構成は以下とする。

```text
portfolio/
  Spec.md
  README.md
  e011.py
  e012.py
  e013.py
  common/
    inputs.py
    ledger.py
    conflict.py
    capital.py
    unit_level.py
    tax.py
    reporting.py
  out/
    E011/latest/
    E012/latest/
    E013/latest/
```

`portfolio/out/` は生成物置き場である。再現性のため、各 run は `latest` だけでなく timestamp 付きディレクトリへ出力できることが望ましい。

## 4. 入力

### 4.1 setting config

入力 setting は `runtime/config/*/*.json` とする。

デフォルトでは以下を対象とする。

- `enabled=true`
- `watch` label 付き setting も含める
- `fixed_units`、`margin_ratio_target`、`size_scale_pct`、`unit_level`、`labels` を読み取る

`enabled=false` はデフォルトでは除外する。ただし、検証用途として `--include-disabled` で含められるようにする。

### 4.2 tick replay result

各 setting の trade 入力は E004 以降の tick replay 成果物を使う。初版の標準入力は以下とする。

```text
qualify/out/<slot_id>/v1/E004/latest/trades.csv
qualify/out/<slot_id>/v1/E004/latest/summary.csv
```

setting と qualify 出力の対応は、原則として以下で解決する。

- `setting.slot_id`
- `setting.side`
- `setting.research_label`

同一 slot に複数 setting が存在する将来ケースでは、`research_label` と `comparison_label` または `execution_spec_json.source_result_id` を使って一意に対応させる。

### 4.3 期間

デフォルト期間は以下とする。

```text
date_from = 2019-01-01
date_to = 2025-12-31
```

期間は CLI 引数で外部指定できること。

`date_local` は setting の market timezone における取引日として扱う。UTC 変換により一部 row が前年末日を持つ場合でも、デフォルト期間では `date_local` が 2019-01-01 以降の row のみを対象とする。

## 5. 共通計算

### 5.1 trade ledger

各 E004 `trades.csv` から、統合処理用の ledger を生成する。

必須列は以下とする。

```text
setting_id
slot_id
research_label
side
market_tz
date_local
entry_time
exit_time
entry_price
exit_price
pnl_pips
tp_pips
sl_pips
exit_reason
```

`pnl_pips` が欠損している row は約定なしとして除外する。

### 5.2 units

JPY 損益は以下で計算する。

```text
pnl_jpy = units * pnl_pips * 0.01
```

USD/JPY の 1 unit あたり 1 pip 価値は `0.01 JPY` とする。

E011 では全 setting を `size_scale_pct=100%` 相当として扱い、`margin_ratio_target` から units を計算する。`fixed_units` や現在の `unit_level=0` は E011 では無視する。

E012/E013 では unit level または指定された simulation mode に基づいて units を計算する。

### 5.3 runtime sizing 準拠

units 計算は runtime の `compute_units()` と同等の式に揃える。

```text
effective_margin_ratio = margin_ratio_target * (100 / size_scale_pct)
units = int(equity_jpy / (effective_margin_ratio / 100) / (entry_price * OANDA_MARGIN_RATE))
```

`OANDA_MARGIN_RATE` は runtime 定義に合わせる。

### 5.4 maintenance margin

entry 時点の概算維持率は以下で計算する。

```text
required_margin_jpy = units * entry_price * OANDA_MARGIN_RATE
estimated_margin_ratio_after_entry = equity_before_jpy / required_margin_jpy * 100
```

必要に応じて `min_maintenance_margin_pct` 未満の entry を skip する mode を追加できる。ただし E011 の主目的は conflict 検証であるため、初版では runtime の open position conflict を優先して再現する。

## 6. Conflict ルール

### 6.1 基本方針

conflict は runtime の `max_concurrent_positions=1` に近い挙動として扱う。

- trade は `entry_time` 昇順で処理する
- `entry_time` / `exit_time` は各 setting の market timezone の local naive timestamp なので、conflict 判定前に UTC へ正規化する
- position が open の間、他 setting の entry は block される
- blocker の `exit_time` に到達すると lock は解除される
- 同一 setting / 同一 `date_local` の重複 row は一意化する

### 6.2 同時刻の判定順

同一 `entry_time` に複数 setting が存在する場合は、今の runtime の判定順に準拠する。

実装では deterministic order として以下を使う。

```text
trigger_bucket_entry
setting_id
```

将来、DynamoDB query の実順をより厳密に再現する必要が出た場合は、この sort key を runtime 側の実 order と合わせて更新する。

### 6.3 watch label

E011 では conflict を見たいので `watch` label 付き setting も 100% size で対象に含める。

runtime では watch の open trade は concurrency count から除外されるが、E011 は意図的に全 setting の競合関係を見るため、watch も通常 setting と同様に block 対象とする。

### 6.4 conflict event

block された trade ごとに conflict event を出力する。

```text
blocked_setting_id
blocker_setting_id
blocked_entry_time
blocked_exit_time
blocker_entry_time
blocker_exit_time
blocked_pnl_pips
blocked_units
blocked_pnl_jpy
blocker_pnl_pips
blocker_units
blocker_pnl_jpy
opportunity_delta_jpy
```

`opportunity_delta_jpy` は以下とする。

```text
opportunity_delta_jpy = blocked_pnl_jpy - blocker_pnl_jpy
```

この値が正であれば、block された trade のほうが結果的に有利だったことを示す。負であれば、block した trade を優先したことが結果的に有利だったことを示す。

## 7. E011: conflict 競合

### 7.1 目的

E011 は、現在の runtime ルールで setting 間 conflict によりどれだけ損益、DD、CAGR が削られるかを見る。

各 setting は常に `size_scale_pct=100%` 相当で取引する。

### 7.2 出力

標準出力先:

```text
portfolio/out/E011/latest/
```

出力ファイル:

```text
summary.csv
setting_summary.csv
conflict_events.csv
conflict_blocker_summary.csv
equity_curve.csv
trade_ledger.csv
params.json
metadata.json
```

`summary.csv` には少なくとも以下を含める。

```text
date_from
date_to
initial_capital_jpy
final_equity_jpy
total_return_pct
cagr
max_dd_pct
trade_count_theoretical
trade_count_executed
trade_count_blocked
theoretical_pnl_jpy
executed_pnl_jpy
blocked_pnl_jpy
conflict_drag_jpy
max_dd_pct
max_dd_jpy
profit_factor
worst_trade_pnl_jpy
max_consecutive_losses
```

E011 はデフォルトで以下の 2 系統を出力する。

```text
unlimited
equity_basis_cap_100m_jpy
```

`unlimited` は notional 制限なしで、100% size を最新 equity で毎 trade 再計算する。
`equity_basis_cap_100m_jpy` は、資産が増えても units計算に使う equity を 1 億円までに制限する参考集計である。

複利効果を外した参考値として、初期資金を基準に units を固定再計算した `fixed_initial_*` 列も出力する。

`conflict_blocker_summary.csv` には、blocker と blocked の組み合わせ別に以下を含める。

```text
blocker_setting_id
blocked_setting_id
block_count
blocked_pnl_jpy_sum
blocked_positive_pnl_jpy_sum
blocked_negative_pnl_jpy_sum
blocker_pnl_jpy_sum
blocker_positive_pnl_jpy_sum
blocker_negative_pnl_jpy_sum
opportunity_delta_jpy_sum
```

## 8. E012: 自動昇降格

### 8.1 目的

E012 は、`docs/Unit_Level_Policy.md` に基づく自動昇降格シミュレーションを行う。

検証したい仮説は以下である。

- 太い edge は時間とともに高い level に落ち着く
- 細い edge は昇格せず低い level に留まる
- conflict により、本来昇格できる setting が阻害される場合がある

### 8.2 level policy

level 定義、watch label、月次判定、閾値、即時降格の基本仕様は `docs/Unit_Level_Policy.md` に従う。
E012/E013 の月次昇降格判定と level sizing は、ops が使う `runtime/src/timer_entry_runtime/level_policy.py` を import して行う。
portfolio 側に同 policy を再実装しない。

初期 level は引数で指定できること。デフォルトは runtime config の `unit_level` を使い、未設定の場合は `0` とする。
太い edge を高 level から開始する比較のため、setting 単位の初期 level override を CLI で列挙できること。

```text
--initial-level 2
--initial-level-setting lon15=4
--initial-level-setting lon08_buy_runtime_v1=3
```

`--initial-level` は全 setting 一律の初期 level override とする。
`--initial-level-setting` は `SETTING_OR_SLOT=LEVEL` 形式で、キーは `setting_id` または一意な `slot_id` を指定できる。
setting 単位 override は全体 override より優先する。

### 8.3 判定基準

E012 は以下の 2 系統を出力する。

```text
realized_after_conflict
theoretical_without_conflict
```

また、それぞれについて以下の 2 系統を出力する。

```text
unlimited
equity_basis_cap_100m_jpy
```

`realized_after_conflict`:

- conflict 後に実際に entry できた trade の realized PnL のみを月次昇降格に使う
- 実運用に近い level 推移を見るための基準

`theoretical_without_conflict`:

- conflict を無視し、各 setting が単独で entry できた前提の PnL を月次昇降格に使う
- setting 本来の edge と level 到達力を見るための参考基準

### 8.4 月次判定

月次判定は対象月の realized PnL JPY を使う。

```text
threshold_jpy = 0.1 * current_units

if cum_jpy_month > threshold_jpy:
    next_level = min(current_level + 1, 7)
elif cum_jpy_month < -threshold_jpy:
    next_level = max(current_level - 1, 0)
else:
    next_level = current_level
```

境界値は据え置きとする。

### 8.5 出力

標準出力先:

```text
portfolio/out/E012/latest/
```

出力ファイル:

```text
summary.csv
setting_summary.csv
setting_monthly_pnl.csv
setting_level_history.csv
setting_level_pivot.csv
equity_curve.csv
trade_ledger.csv
params.json
metadata.json
```

`setting_level_history.csv` には少なくとも以下を含める。

```text
basis
decision_month
setting_id
slot_id
side
current_level
next_level
initial_level_source
decision
decision_reason
current_units
threshold_jpy
cum_jpy_month
unit_basis
```

`basis` は `realized_after_conflict` または `theoretical_without_conflict` とする。
`sizing_mode` は `unlimited` または `equity_basis_cap_100m_jpy` とする。

`setting_level_pivot.csv` は、月を行、setting を列にして level 推移を一覧できる形式とする。

`summary.csv` と `setting_summary.csv` には、unit level policy 有無の比較に使うため、少なくとも以下のリスク指標を含める。

```text
max_dd_pct
max_dd_jpy
worst_month_pnl_jpy
worst_trade_pnl_jpy
profit_factor
max_consecutive_losses
```

## 9. E013: 再投資、税金、手取り

### 9.1 目的

E013 は、軌道に乗った後の実運用に近い資金推移を検証する。

基本配分は以下とする。

```text
再投資: 50%
税金: 20%
手取り: 30%
```

税金と手取りは翌年の固定日に引き落とす。それまでは資金に残し、100%再投資されたものとして複利運用に使う。

取引 units は `docs/Unit_Level_Policy.md` の月次 unit level を反映して計算する。
各 setting の level 推移は `setting_level_history.csv` に出力する。
E013 でも E012 と同じ `--initial-level` / `--initial-level-setting SETTING_OR_SLOT=LEVEL` により、太い edge を高 level から開始できること。

### 9.2 開始条件

以下を CLI 引数で指定できること。

```text
date_from
date_to
initial_capital_jpy
```

デフォルト期間は `2019-01-01` から `2025-12-31` とする。

### 9.3 税金と手取りの対象

税金計算は暦年単位とする。

```text
tax_year_start = YYYY-01-01
tax_year_end = YYYY-12-31
```

対象利益は、その暦年の realized PnL JPY とする。

年間利益がマイナスの場合:

- 税金は 0
- 手取りは 0
- 赤字分は翌年以降へ損失繰越する

年間利益がプラスの場合:

- 先に内部損失繰越を相殺する
- 次に外部損失枠を相殺する
- 残った利益を taxable profit とする

```text
taxable_profit_jpy = max(0, yearly_realized_pnl_jpy - internal_loss_carryover_jpy - external_loss_offset_used_jpy)
```

### 9.4 外部損失枠

裁量取引など、シミュレーション外の損失と相殺したい場合のため、外部損失枠を指定できること。

デフォルトは 0 とする。

外部損失枠は以下を持つ。

```text
amount_jpy
expires_on
```

`expires_on` を過ぎた外部損失枠は使用できない。

### 9.5 引落日

税金と手取りの引落日は別々に指定できること。

デフォルトはいずれも以下とする。

```text
tax_withdraw_month_day = 02-01
takehome_withdraw_month_day = 02-01
```

たとえば 2024 年分の税金と手取りは、通常 2025-02-01 に引き落とす。

引落日までは税金分、手取り分も equity に残り、次の trade の units 計算に使われる。

### 9.6 終了年の強制精算

シミュレーション終了年の税金と手取りは、`date_to` 時点で強制的に引き落としてから終了する。

例:

```text
date_to = 2025-12-31
```

この場合、2025 年分の税金と手取りは 2026-02-01 を待たず、2025-12-31 に控除する。

最終結果の正式値は、終了年の強制精算後の equity とする。

### 9.7 100%再投資効果の計測

翌年引落日まで税金と手取りを資金に残す複利効果を確認するため、E013 は以下の 2 系統を比較する。

```text
deferred_withdrawal
immediate_withdrawal
```

`deferred_withdrawal`:

- 税金と手取りを翌年指定日に引き落とす
- 引落日までは 100%再投資として units 計算に含める
- 終了年は `date_to` に強制精算する

`immediate_withdrawal`:

- 各暦年末、または利益確定年の最終処理時点で税金と手取りを即時控除したものとして扱う
- 翌年 2 月までの一時的な複利効果を持たない比較基準

さらに、それぞれについて以下の 2 系統を出力する。

```text
unlimited
equity_basis_cap_100m_jpy
```

`equity_basis_cap_100m_jpy` は、資産が増えても units計算に使う equity を 1 億円までに制限する参考集計である。

`summary.csv` には、少なくとも以下を含める。

```text
final_equity_deferred_jpy
final_equity_immediate_jpy
deferred_reinvestment_benefit_jpy
deferred_reinvestment_benefit_pct
```

計算式:

```text
deferred_reinvestment_benefit_jpy = final_equity_deferred_jpy - final_equity_immediate_jpy
deferred_reinvestment_benefit_pct = final_equity_deferred_jpy / final_equity_immediate_jpy - 1
```

### 9.8 出力

標準出力先:

```text
portfolio/out/E013/latest/
```

出力ファイル:

```text
summary.csv
yearly_allocation.csv
cashflow_events.csv
equity_curve.csv
setting_level_history.csv
trade_ledger.csv
params.json
metadata.json
```

`yearly_allocation.csv` には少なくとも以下を含める。

```text
tax_year
yearly_realized_pnl_jpy
internal_loss_carryover_before_jpy
internal_loss_carryover_after_jpy
external_loss_offset_used_jpy
taxable_profit_jpy
reinvest_amount_jpy
tax_amount_jpy
takehome_amount_jpy
tax_withdraw_date
takehome_withdraw_date
forced_final_settlement
```

`cashflow_events.csv` には少なくとも以下を含める。

```text
event_date
event_type
tax_year
amount_jpy
equity_before_jpy
equity_after_jpy
forced_final_settlement
```

`event_type` は以下を想定する。

```text
tax_withdrawal
takehome_withdrawal
final_tax_withdrawal
final_takehome_withdrawal
```

## 10. CLI 方針

各 experiment は単独実行できること。

例:

```text
python portfolio/e011.py --initial-capital-jpy 1000000
python portfolio/e012.py --initial-capital-jpy 1000000 --date-from 2019-01-01 --date-to 2025-12-31
python portfolio/e013.py --initial-capital-jpy 1000000 --tax-withdraw-month-day 02-01 --takehome-withdraw-month-day 02-01
```

共通引数:

```text
--runtime-config-dir runtime/config
--qualify-out-dir qualify/out
--out-dir portfolio/out/<EXPERIMENT>/latest
--date-from 2019-01-01
--date-to 2025-12-31
--initial-capital-jpy
--include-disabled
```

E012 固有引数:

```text
--initial-level
--initial-level-setting
--basis realized_after_conflict|theoretical_without_conflict|both
```

E013 固有引数:

```text
--initial-level
--initial-level-setting
--reinvest-ratio 0.5
--tax-ratio 0.2
--takehome-ratio 0.3
--tax-withdraw-month-day 02-01
--takehome-withdraw-month-day 02-01
--external-loss-offset-json
```

配分比率は合計 1.0 であることを検証する。

## 11. 再現性

各 run は `params.json` と `metadata.json` を必ず出力する。

`params.json` には CLI 引数、期間、初期資金、税率、引落日、対象 setting 一覧を含める。

`metadata.json` には以下を含める。

```text
experiment_code
generated_at
git_commit
runtime_config_dir
qualify_out_dir
input_trade_files
input_setting_files
```

## 12. 注意事項

- portfolio は研究・検証用途であり、runtime config を直接変更しない
- qualify の tick replay 結果を正本とし、portfolio 側では価格約定を再計算しない
- E011 の watch 取り扱いは runtime と意図的に異なる
- E012 の level 判定は `Unit_Level_Policy.md` に従うが、実 config 更新は行わない
- E013 の税金計算は運用シミュレーション用の近似であり、税務上の最終判断ではない
