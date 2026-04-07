# qualify Spec

本ドキュメントは `qualify/` に置く昇格審査フレームワークの仕様を定める。
対象は `scan` で見つかった候補を受け取り、E001-E008 を共通実行基盤で再現可能に回すための入口実装である。

最上位規約は `docs/FX_Research_Constitution.md` とする。
core の共通仕様は `src/timer_entry/Spec.md` を優先し、`qualify/` はその上に実験 orchestration と実行管理を載せる。

## 1. 目的

`qualify/` の目的は以下とする。

- `scan` で見つかった候補を昇格審査する
- E001-E008 を単発スクリプトの寄せ集めではなく、共通基盤で扱う
- pandas の canonical engine と tick replay engine を、同じ setting 主語で接続する
- 出力を core schema に寄せ、後段の runtime / ops と接続しやすくする

## 2. 用語

- `strategy`
  - 売買のやり方そのもの
- `slot`
  - 1時間帯
  - `tyo07..tyo15`, `lon08..lon21`
- `setting`
  - 1 slot 内の具体条件
- `scenario`
  - experiment code の下で実行される比較単位
  - `QualifyScenario` を基本表現とする
- `experiment variant`
  - `E001A` のような派生実験
  - 同じ experiment code の派生として扱う

## 3. 責務境界

`qualify/` が持つ責務は以下。

- ChatGPT 側スレッドで決定された実験パラメータを受け取り、機械的に実行する
- E001-E008 の実験入口を `e00N.py` として提供する
- scenario の正規化、実行、集計、出力保存を担当する
- tick replay を共通モジュールとして保持する
- 監査結果と旧資産との差分をドキュメントとして集約する

`qualify/` が持たない責務は以下。

- Bid/Ask、same-bar、event time、feature、filter 定義の再実装
- `scan` の高速総当たり探索
- ChatGPT 側の実験意思決定そのもの
- `runtime` の本番執行処理

## 4. 実行体制

`qualify/` は以下の分業を前提に設計する。

- ChatGPT 側スレッド
  - `qualify/prompts/slot_thread_template.md` を使って slot ごとの候補を読む
  - E001 などの初手パラメータを決定する
  - 結果を読み、継続・修正・派生実験の判断を行う
- Codex 側スレッド
  - 決定済みパラメータを JSON などの機械入力として受け取る
  - 実験を機械的に実行する
  - 出力物を標準形式に整形する
  - 必要なら E001A など派生実験の起動も行う

このため、`qualify/` は `scan/summary.csv` を直接読みながら自律的に候補選定する構成を初版の前提にしない。
候補選定と比較軸の決定は、ChatGPT 側スレッド主導とする。

## 5. engine 方針

- 1分足 canonical
  - `src/timer_entry/backtest_1m.py`
- tick replay
  - `qualify/` 配下で共通化
- schema
  - `src/timer_entry/schemas.py`

重要なのは engine 差ではなく仕様一致である。`qualify/` では以下を再定義しない。

- 価格系列規約
- feature 定義
- canonical filter 名
- same-bar 解釈
- 保守的 SL exit

## 6. ディレクトリ構成

初版の推奨構成は以下。

- `qualify/README.md`
  - 概要と使い方
- `qualify/Spec.md`
  - 本仕様
- `qualify/docs/`
  - 監査結果や実験運用メモ
- `qualify/prompts/`
  - ChatGPT 側スレッド用 prompt
- `qualify/common/`
  - 共通実行モジュール
- `qualify/e001.py`
  - E001 の入口
- `qualify/e002.py`
  - E002 の入口
- `qualify/e003.py`
  - E003 の入口
- `qualify/e004.py`
  - E004 の入口
- `qualify/e005.py`
  - E005 の入口
- `qualify/e006.py`
  - E006 の入口
- `qualify/e007.py`
  - E007 の入口
- `qualify/e008.py`
  - E008 の入口
- `qualify/out/`
  - 実験出力

`common/` に置く想定モジュール例は以下。

- `qualify/common/scenarios.py`
- `qualify/common/reporting.py`
- `qualify/common/io.py`
- `qualify/common/params.py`
- `qualify/common/tick_replay/`

## 7. 起動方式

各 experiment は `qualify/e00N.py` を入口にする。
起動スクリプトは薄く保ち、以下の役割に限定する。

- 引数や JSON 入力の受け取り
- scenario のロード
- 共通 runner の呼び出し
- 出力先の確定

実験ロジックそのものは `qualify/common/` に寄せる。

## 8. 入力方針

初版の `qualify` は、ChatGPT 側スレッドで決定したパラメータを入力として実行する。
入力形式は JSON を基本とする。

想定する入力情報は以下。

- experiment code
- variant code
  - 例: `E001A`
- baseline setting
- 比較対象 filter family
- 閾値群
- date range
- segment policy
- 実行メモ

この JSON は `QualifyScenario` を中心に表現し、必要に応じて補助フィールドを持たせる。

## 9. 出力方針

出力は core schema に寄せる。

- trade 明細
  - `BacktestTrade` 準拠
- summary
  - `BacktestSummary` 準拠
- sanity
  - `SanitySummary` 準拠
- scenario metadata
  - `QualifyScenario` と補助メタデータ

experiment 固有で追加してよい列は、比較ラベルや派生コードなど、横断利用しやすいものに限る。
slot ごとの方言 CSV は増やさない。

## 10. experiment code の役割

- E001
  - filter family の深掘り
  - `all` 主線候補の小規模再審査
- E002
  - TP / SL 深掘り
- E003
  - forced exit 深掘り
- E004
  - tick replay 昇格審査
- E005
  - slippage 耐性
- E006
  - walk-forward / holdout
- E007
  - risk_fraction / kill-switch / 維持率
- E008
  - entry delay 耐性

派生実験は `E001A` のように扱ってよい。
ただし、派生は experiment code の意味を壊さず、主実験の補助目的に留める。

## 11. E001 の位置付け

E001 は `scan` の後段であり、mission は次のいずれかである。

- `scan` で反応した filter family の threshold sweep
- `all` が最上位だった slot の説明可能な範囲での再審査

ここでいう再審査は再探索ではなく、小規模で説明可能な比較に限る。

- 同一 slot / side / entry / forced exit を維持する
- filter 多重組み合わせは行わない
- rolling 分位や年別分位は使わない
- threshold sweep は代表点に限る

E001 の詳細な比較・旧資産との差分は `qualify/docs/Audit_Result.md` に集約する。

## 12. 旧資産の扱い

`fx_260312` は比較用の一時 checkout と位置付ける。
このため、`qualify` の恒久仕様は以下の方針を取る。

- 旧 repo のコード構成には依存しない
- 継承対象は実験の目的、比較軸、注意点に限る
- 旧パスは監査資料にのみ残す
- 実装仕様や README には恒久依存として書かない

旧 `e001.py` は実験色が強いため、そのまま移植しない。
今の core を使って組み直し、エッセンスだけを拝借する。

## 13. 監査ドキュメント

監査結果は `qualify/docs/Audit_Result.md` に集約する。
ここには以下を載せる。

- 旧 `fx_260312` の参照対象
- 仕様差分
- 実装差分
- 継承するもの
- 継承しないもの
- 未解決論点

## 14. 次の実装順

1. ChatGPT 側 prompt を JSON 出力前提に整える
2. `qualify/common/params.py` と scenario 入力契約を定める
3. `qualify/e001.py` と共通 runner を作る
4. reporting を schema 主語で整える
5. E002 以降へ横展開する
