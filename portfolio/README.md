# portfolio

`portfolio/` は、`runtime/config` の setting 群を同時運用した場合の資金推移、setting 間 conflict、自動昇降格、税金 / 手取り / 再投資を検証する統合バックテスト領域です。

詳細仕様は `portfolio/Spec.md` を参照してください。

## 役割

- `runtime/config` の全 setting を読み込む
- `qualify/out/<slot_id>/v1/E004/latest/trades.csv` の tick replay 結果を使う
- E011-E013 の portfolio simulation を実行する
- ChatGPT 側で結果分析しやすい CSV と prompt を出す

## Docker 実行

ビルド:

```bash
docker build -f docker/Dockerfile -t timer_entry1 .
```

E011 conflict 競合:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python portfolio/e011.py \
    --runtime-config-dir runtime/config \
    --qualify-out-dir qualify/out \
    --date-from 2019-01-01 \
    --date-to 2025-12-31 \
    --initial-capital-jpy 1000000 \
    --out-dir portfolio/out/E011/latest
```

E011 の `final_equity_jpy` は、100% size を trade ごとに最新 equity で再計算する複利結果です。
複利効果を外した参考値は `summary.csv` の `fixed_initial_*` 列を見ます。
また、E011 はデフォルトで以下の 2 系統を出します。

- `unlimited`: notional 制限なし
- `equity_basis_cap_100m_jpy`: 資金が1億円を超えたら、units計算に使う equity を1億円で制限

Tokyo / London の trade 時刻は、market local time の naive timestamp ではなく UTC に正規化して conflict 判定します。

E012 自動昇降格:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python portfolio/e012.py \
    --runtime-config-dir runtime/config \
    --qualify-out-dir qualify/out \
    --date-from 2019-01-01 \
    --date-to 2025-12-31 \
    --initial-capital-jpy 1000000 \
    --initial-level-setting lon15=3 \
    --initial-level-setting lon08=3 \
    --initial-level-setting lon10=3 \
    --initial-level-setting lon19=3 \
    --initial-level-setting tyo12=3 \
    --basis both \
    --out-dir portfolio/out/E012/latest
```

E012 も `sizing_mode` 列で以下の 2 系統を出します。

- `unlimited`
- `equity_basis_cap_100m_jpy`

太い edge を高 level から開始したい場合は、`--initial-level-setting SETTING_OR_SLOT=LEVEL` を列挙します。
キーは `setting_id` または一意な `slot_id` を指定できます。全 setting を同じ level にしたい場合は `--initial-level` を使います。
E012/E013 の昇降格判定と level sizing は、ops と同じ `runtime/src/timer_entry_runtime/level_policy.py` を import して使います。

現在の太い edge 候補を level 3 start にする引数:

```bash
--initial-level-setting lon15=3 \
--initial-level-setting lon08=3 \
--initial-level-setting lon10=3 \
--initial-level-setting lon19=3 \
--initial-level-setting tyo12=3
```

E013 再投資 / 税金 / 手取り:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python portfolio/e013.py \
    --runtime-config-dir runtime/config \
    --qualify-out-dir qualify/out \
    --date-from 2019-01-01 \
    --date-to 2025-12-31 \
    --initial-capital-jpy 1000000 \
    --reinvest-ratio 0.5 \
    --tax-ratio 0.2 \
    --takehome-ratio 0.3 \
    --initial-level-setting lon15=3 \
    --initial-level-setting lon08=3 \
    --initial-level-setting lon10=3 \
    --initial-level-setting lon19=3 \
    --initial-level-setting tyo12=3 \
    --tax-withdraw-month-day 02-01 \
    --takehome-withdraw-month-day 02-01 \
    --out-dir portfolio/out/E013/latest
```

E013 も `sizing_mode` 列で以下の 2 系統を出します。

- `unlimited`
- `equity_basis_cap_100m_jpy`

E013 は `docs/Unit_Level_Policy.md` に基づく月次 unit level も反映します。
level 推移は `setting_level_history.csv` に出力します。
E013 でも `--initial-level` と `--initial-level-setting SETTING_OR_SLOT=LEVEL` を指定できます。

外部損失枠を使う例:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python portfolio/e013.py \
    --initial-capital-jpy 1000000 \
    --external-loss-offset-json '[{"amount_jpy":500000,"expires_on":"2026-12-31"}]'
```

## 出力

E011:

- `portfolio/out/E011/latest/summary.csv`
- `portfolio/out/E011/latest/setting_summary.csv`
- `portfolio/out/E011/latest/conflict_events.csv`
- `portfolio/out/E011/latest/conflict_blocker_summary.csv`
- `portfolio/out/E011/latest/equity_curve.csv`
- `portfolio/out/E011/latest/trade_ledger.csv`
- `portfolio/out/E011/latest/params.json`
- `portfolio/out/E011/latest/metadata.json`

E012:

- `portfolio/out/E012/latest/summary.csv`
- `portfolio/out/E012/latest/setting_summary.csv`
- `portfolio/out/E012/latest/setting_monthly_pnl.csv`
- `portfolio/out/E012/latest/setting_level_history.csv`
- `portfolio/out/E012/latest/setting_level_pivot.csv`
- `portfolio/out/E012/latest/equity_curve.csv`
- `portfolio/out/E012/latest/trade_ledger.csv`
- `portfolio/out/E012/latest/params.json`
- `portfolio/out/E012/latest/metadata.json`

E013:

- `portfolio/out/E013/latest/summary.csv`
- `portfolio/out/E013/latest/yearly_allocation.csv`
- `portfolio/out/E013/latest/cashflow_events.csv`
- `portfolio/out/E013/latest/equity_curve.csv`
- `portfolio/out/E013/latest/setting_level_history.csv`
- `portfolio/out/E013/latest/trade_ledger.csv`
- `portfolio/out/E013/latest/params.json`
- `portfolio/out/E013/latest/metadata.json`

## ChatGPT 分析プロンプト

結果分析用 prompt は以下です。

- E011: `portfolio/prompts/e011_result_analysis_thread.md`
- E012: `portfolio/prompts/e012_result_analysis_thread.md`
- E013: `portfolio/prompts/e013_result_analysis_thread.md`

ChatGPT 側では、各 prompt を貼り、以下のファイルを添付します。

E011 添付:

- `summary.csv`
- `setting_summary.csv`
- `conflict_events.csv`
- `conflict_blocker_summary.csv`
- `equity_curve.csv`
- `input_summary.csv`
- `params.json`
- `metadata.json`
- 必要なら `trade_ledger.csv`

E012 添付:

- `summary.csv`
- `setting_summary.csv`
- `setting_monthly_pnl.csv`
- `setting_level_history.csv`
- `setting_level_pivot.csv`
- `equity_curve.csv`
- `input_summary.csv`
- `params.json`
- `metadata.json`
- 必要なら `trade_ledger.csv`

E013 添付:

- `summary.csv`
- `yearly_allocation.csv`
- `cashflow_events.csv`
- `equity_curve.csv`
- `setting_level_history.csv`
- `input_summary.csv`
- `params.json`
- `metadata.json`
- 必要なら `trade_ledger.csv`

## 補足

- portfolio は runtime config を変更しません
- 初版では E004 tick replay の `trades.csv` を正本にします
- E011 では watch label 付き setting も 100% size で conflict 対象に含めます
- E012 は `realized_after_conflict` と `theoretical_without_conflict` の 2 系統を出します
- E012/E013 は `unlimited` と `equity_basis_cap_100m_jpy` の 2 系統を出します
- E012/E013 は `--initial-level-setting SETTING_OR_SLOT=LEVEL` で setting 別の初期 level を指定できます
- E013 は unit level を反映した上で `deferred_withdrawal` と `immediate_withdrawal` の差を出し、終了年の税金と手取りは `date_to` で強制精算します
