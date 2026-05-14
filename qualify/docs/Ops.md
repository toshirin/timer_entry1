# qualify Ops

本ドキュメントは `qualify/` の実験運用フローを定める。
仕様そのものは `qualify/Spec.md`、旧資産との比較監査は `qualify/docs/Audit_Result.md` を参照する。

## 1. 基本原則

- ChatGPT 側スレッド
  - 候補の解釈、比較軸の決定、次実験の判断を担う
- Codex 側スレッド
  - JSON を受けて機械的に実行する
  - 未実装の filter instance や schema 差分があれば、先に実装・整備する

`qualify` は `scan` のような自律探索ではない。
必ず「判断スレッド」と「実行スレッド」を分ける。

## 2. ファイル役割

- `qualify/prompts/`
  - ChatGPT 側に渡す experiment 別 prompt
- `qualify/params/`
  - ChatGPT 側が出した JSON を保存する
- `qualify/e00N.py`
  - Codex 側の実行入口
- `qualify/e005-e008.py`
  - E005-E008 suite の実行入口
- `qualify/out/`
  - 実験結果の保存先

## 2.1 version ディレクトリ規約

1 slot に複数 setting を持てるよう、`qualify/params` と `qualify/out` では `slot_id` の下に candidate version として `vN` ディレクトリを置く。

- `v1`
  - その slot の最初の昇格候補
- `v2`, `v3`, ...
  - 同じ slot の別候補

例:

- `qualify/params/lon08/v1/e001.json`
- `qualify/params/lon08/v2/e001.json`
- `qualify/out/lon08/v1/E004/latest/summary.csv`
- `qualify/out/lon08/v2/E004/latest/summary.csv`

`qualify/results` と `runtime/config` は従来どおり file name の `..._v1.json` で version を表す。
slot 自体を `lon08a` のように枝番化しない。

現役ではない候補や旧成果物は `archived` 配下へ退避する。

- `qualify/params/archived/lon12/{version_id}/e004.json`
- `qualify/out/archived/lon12/{version_id}/E004/latest/summary.csv`
- `qualify/results/archived/tyo14/{version_id}/tyo14_buy_v1.json`

`archived` を除いて見れば、現役の params / out / results を集められるように保つ。
`version_id` は active と同様に version を表す。既存の旧候補アーカイブは `v0` を使う。

## 3. prompt 一覧

- `qualify/prompts/e001_slot_thread.md`
  - scan の時間別 summary から filter family 深掘りを決め、E001 JSON を出す
- `qualify/prompts/e002_thread.md`
  - E001 結果から TP/SL sweep を決め、E002 JSON を出す
- `qualify/prompts/e003_thread.md`
  - E002 結果から forced exit sweep を決め、E003 JSON を出す
- `qualify/prompts/e004_thread.md`
  - E003 結果から tick replay 条件を確定し、E004 JSON を出す
- `qualify/prompts/e005_e008_thread.md`
  - E004 通過候補に対する E005-E008 suite 条件をまとめて決め、E005-E008 JSON を出す
- `qualify/prompts/result_analysis_thread.md`
  - Codex 実行後の CSV を分析し、採用 / 再実験 / 次段進行を判断する
- `qualify/prompts/final_promotion_result_thread.md`
  - E008 合格後に runtime 昇格用の最終結果 JSON を出す
- `qualify/prompts/slot_thread_template.md`
  - どの prompt を使うか案内する親ドキュメント

## 4. 標準フロー

全 experiment は、原則として以下の二段 prompt 運用にする。

本ドキュメントでは、以下の呼称を使う。

- プロンプト1
  - params 作成プロンプト
  - `qualify/prompts/e001_slot_thread.md` などの experiment 別 prompt を指す
  - 次にやるタスク内容を決め、Codex 実行用 params JSON を出す
- プロンプト2
  - 結果分析プロンプト
  - `qualify/prompts/result_analysis_thread.md` を指す
  - Codex 実行後の CSV を読み、採用 / 再実験 / 次段進行を判断する

1. プロンプト1で次にやるタスク内容を決め、Codex 実行用 params JSON を出す
2. E001 だけは、この時点で slot 別 `summary_{slot_id}.csv` も添付する
3. JSON が出力されたら、必要に応じて Codex 側で新規 filter / schema を実装する
4. Codex 側で `e00N.py` または `e005-e008.py` を実行する
5. プロンプト2 `qualify/prompts/result_analysis_thread.md` に結果 CSV を添付し、「分析して」と依頼する
6. 目的値が決まる / 安全が確認される / 再実験が必要、のいずれかを判断する
7. E008 まで合格したら `qualify/prompts/final_promotion_result_thread.md` で最終結果 JSON を作る

JSON の出力は必ず `json` コードブロックにする。
E001 の新規 filter 定義は、Codex 宛の実装仕様書として `markdown` コードブロックにする。

### 4.1 E001

入力:

- `scan/out/.../per_slot/summary_{slot_id}.csv`
- 必要なら `scan/out/.../reports/summary_report.md`
- `docs/FX_Research_Constitution.md`
- `src/timer_entry/Spec.md`
- `src/timer_entry/filters.py`

出力:

- `qualify/params/{slot_id}/{version_id}/e001.json`

手順:

1. ChatGPT 側で `qualify/prompts/e001_slot_thread.md` を使う
2. filter family と threshold sweep を決める
3. 未知の `comparison_labels` が必要なら、JSON と一緒に「新規定義案」を出す
4. その内容を Codex 側スレッドへ貼る
5. Codex 側で必要なら `src/timer_entry/filters.py` と runner を拡張する
6. 実装後に `qualify/e001.py` を実行する

### 4.2 E002

入力:

- E001 の `summary.csv`
- E001 の `split_summary.csv`
- E001 の `year_summary.csv`
- 必要なら E001 の `trades.csv`

出力:

- `qualify/params/{slot_id}/{version_id}/e002.json`

手順:

1. ChatGPT 側で `qualify/prompts/e002_thread.md` を使う
2. baseline filter を固定し、`tp_values` / `sl_values` を決める
3. Codex 側で `qualify/e002.py` を実行する

### 4.3 E003

入力:

- E002 の `summary.csv`
- E002 の `split_summary.csv`
- E002 の `year_summary.csv`

出力:

- `qualify/params/{slot_id}/{version_id}/e003.json`

手順:

1. ChatGPT 側で `qualify/prompts/e003_thread.md` を使う
2. baseline を固定し、`forced_exit_values` を決める
3. Codex 側で `qualify/e003.py` を実行する

### 4.4 E004

入力:

- E003 の `summary.csv`
- E003 の `split_summary.csv`
- E003 の `year_summary.csv`
- 必要なら E003 の `trades.csv`

出力:

- `qualify/params/{slot_id}/{version_id}/e004.json`

手順:

1. ChatGPT 側で `qualify/prompts/e004_thread.md` を使う
2. tick replay 対象 setting と execution 条件を確定する
3. Codex 側で `qualify/e004.py` を実行する

### 4.5 E005-E008

入力:

- `qualify/params/{slot_id}/{version_id}/e004.json`
- E004 の `summary.csv`
- E004 の `split_summary.csv`
- E004 の `year_summary.csv`
- E004 の `trades.csv`
- E004 の `sanity_summary.csv`

出力:

- `qualify/params/{slot_id}/{version_id}/e005-e008.json`

手順:

1. ChatGPT 側で `qualify/prompts/e005_e008_thread.md` を使う
2. E004 通過 setting を前提に、E005-E008 の比較軸を決める
3. `slippage_values`, `entry_delay_values`, `target_maintenance_margin_candidates`, `kill_switch_dd_pct` を JSON に含める
4. Codex 側で `qualify/e005-e008.py` を実行する
5. デフォルトは E005-E008 一括実行とする
6. 必要なら引数で E005 / E006 / E007 / E008 の単独実行を行う
7. 派生再実験として保存したい場合は `--output-alias E007=E007A` のように指定する

追加運用ルール:

- E005
  - `slip_pips` は one-way 表示で扱う
  - ChatGPT 側の評価文でも、実質往復 penalty は `2 * slip_pips` と明記する
- E007
  - maintenance margin grid は通常 `[150, 180, 200]`、必要に応じて `[150, 180, 200, 230, 260]` とする
  - summary では `target_maintenance_margin_pct`, `annualized_pips`, `cagr`, `trade_rate`, `win_rate`, `max_dd_pct`, `min_maintenance_margin_pct`, `maintenance_below_130_count`, `maintenance_below_100_count`, `stop_triggered`, `final_equity_jpy`, `total_return_pct`, `pips_year_rate_pct_at_150usd` を必須確認項目とする
  - `min_maintenance_margin_pct` と below count は、entry 直後ではなく即時 SL 到達時の想定維持率で評価する
  - `maintenance_below_100_count > 0` は一発NG、`stop_triggered` または `maintenance_below_130_count > 0` は一段上の維持率確認シグナルとする
  - 採用判断は CAGR 最大ではなく、安全条件を満たした最初の維持率候補で行う

注意:

- `--only E007 --output-alias E007=E007A` は E007 の実行内容を変えず、出力先だけ `qualify/out/{slot_id}/{version_id}/E007A` に分ける

- E004 までを一体化しない
- E004 は tick replay 昇格審査として独立させる
- E005-E008 はその後段の robustness suite として扱う

### 4.6 最終昇格結果

入力:

- `qualify/params/{slot_id}/{version_id}/e004.json`
- `qualify/params/{slot_id}/{version_id}/e005-e008.json`
- E004-E008 の各 `summary.csv`
- E004-E008 の各 `sanity_summary.csv`
- 必要なら E007 の `equity_curve.csv`
- ChatGPT 側の結果分析結論

出力:

- `qualify/results/{slot_id}/{result_id}.json`

手順:

1. ChatGPT 側で `qualify/prompts/final_promotion_result_thread.md` を使う
2. E004-E008 の合格状態と主要根拠を確認する
3. `QualifyPromotionResult` 形式の JSON を出す
4. Codex 側で `qualify/results/{slot_id}/{result_id}.json` に保存する
5. runtime promotion は params ではなく、この result JSON を入力にする

## 5. JSON 運用ルール

- `experiment_code`
  - 実行入口と一致させる
- `variant_code`
  - 派生実験だけに使う
  - 主実験なら原則 `null`
- `baseline`
  - 前段で通した setting を固定して持ち回る
- `pass_stability_gate`
  - 通常は `true`
  - `false` を使う場合は `notes` に理由を書く

## 6. 未知ラベルの扱い

ChatGPT 側が現行 core 未実装の `comparison_labels` を提案してよい。
ただし、その場合は以下を必須とする。

- label 名
- family 名
- 判定式
- runtime に落とす場合の spec 案
- 既存 label と何が違うか

Codex 側では、その定義が `src/timer_entry/Spec.md` と整合するか確認し、必要なら以下を更新する。

- `src/timer_entry/filters.py`
- 必要なテスト
- `qualify/prompts/` の JSON 例

未知ラベルを含む JSON は、その実装が終わるまで「実行候補」であり、「即実行可能 JSON」ではない。

## 7. 命名規則

- params
  - `qualify/params/{slot_id}/{version_id}/e001.json`
  - `qualify/params/{slot_id}/{version_id}/e001a.json`
  - `qualify/params/{slot_id}/{version_id}/e002.json`
  - `qualify/params/{slot_id}/{version_id}/e003.json`
  - `qualify/params/{slot_id}/{version_id}/e004.json`
  - `qualify/params/{slot_id}/{version_id}/e005-e008.json`
- output
  - `qualify/out/{slot_id}/{version_id}/E001/latest/...`
  - `qualify/out/{slot_id}/{version_id}/E001A/latest/...`
  - `qualify/out/{slot_id}/{version_id}/E005/...`
  - `qualify/out/{slot_id}/{version_id}/E006/...`
  - `qualify/out/{slot_id}/{version_id}/E007/...`
  - `qualify/out/{slot_id}/{version_id}/E008/...`
- results
  - `qualify/results/{slot_id}/{result_id}.json`

## 8. 現在の実装状況

- 実装済み
  - E001
  - E002
  - E003
  - E004
  - E005-E008 suite
