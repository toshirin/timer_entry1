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
- `qualify/out/E00N/...`
  - 実験結果の保存先

## 3. prompt 一覧

- `qualify/prompts/e001_slot_thread.md`
  - scan の時間別 summary から filter family 深掘りを決め、E001 JSON を出す
- `qualify/prompts/e002_thread.md`
  - E001 結果から TP/SL sweep を決め、E002 JSON を出す
- `qualify/prompts/e003_thread.md`
  - E002 結果から forced exit sweep を決め、E003 JSON を出す
- `qualify/prompts/e004_thread.md`
  - E003 結果から tick replay 条件を確定し、E004 JSON を出す
- `qualify/prompts/e005_thread.md`
  - E004 通過候補に slippage 耐性条件を与える
- `qualify/prompts/e006_thread.md`
  - holdout / walk-forward 条件を与える
- `qualify/prompts/e007_thread.md`
  - risk_fraction / kill-switch 系条件を与える
- `qualify/prompts/e008_thread.md`
  - entry delay 耐性条件を与える
- `qualify/prompts/slot_thread_template.md`
  - どの prompt を使うか案内する親ドキュメント

## 4. 標準フロー

### 4.1 E001

入力:

- `scan/out/.../per_slot/summary_{slot_id}.csv`
- 必要なら `scan/out/.../reports/summary_report.md`
- `docs/FX_Research_Constitution.md`
- `src/timer_entry/Spec.md`
- `src/timer_entry/filters.py`

出力:

- `qualify/params/{slot_id}/e001.json`

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

- `qualify/params/{slot_id}/e002.json`

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

- `qualify/params/{slot_id}/e003.json`

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

- `qualify/params/{slot_id}/e004.json`

手順:

1. ChatGPT 側で `qualify/prompts/e004_thread.md` を使う
2. tick replay 対象 setting と execution 条件を確定する
3. Codex 側で `qualify/e004.py` を実行する

### 4.5 E005-E008

E005-E008 も同じ型で運用する。
各段階の JSON schema は experiment ごとに別であり、`experiment_code` だけを書き換えて流用する前提ではない。

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
  - `qualify/params/{slot_id}/e001.json`
  - `qualify/params/{slot_id}/e001a.json`
  - `qualify/params/{slot_id}/e002.json`
  - `qualify/params/{slot_id}/e003.json`
  - `qualify/params/{slot_id}/e004.json`
- output
  - `qualify/out/E001/{slot_id}/...`
  - `qualify/out/E001A/{slot_id}/...`

## 8. 現在の実装状況

- 実装済み
  - E001
  - E002
  - E003
  - E004
- 未実装
  - E005
  - E006
  - E007
  - E008

未実装段階の prompt は、先行して運用方針を揃えるための雛形として置いてよい。
