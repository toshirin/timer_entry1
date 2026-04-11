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
  - `qualify/prompts/` 配下の experiment 別 prompt を使って候補を読む
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
- `qualify/e005-e008.py`
  - E005-E008 robustness suite の入口
- `qualify/out/`
  - 実験出力

`common/` に置く想定モジュール例は以下。

- `qualify/common/scenarios.py`
- `qualify/common/reporting.py`
- `qualify/common/io.py`
- `qualify/common/params.py`
- `qualify/common/tick_replay/`

## 7. 起動方式

E001-E004 は `qualify/e00N.py` を入口にする。
E005-E008 は `qualify/e005-e008.py` を suite 入口にする。
起動スクリプトは薄く保ち、以下の役割に限定する。

- 引数や JSON 入力の受け取り
- scenario のロード
- 共通 runner の呼び出し
- 出力先の確定

実験ロジックそのものは `qualify/common/` に寄せる。

## 8. 入力方針

初版の `qualify` は、ChatGPT 側スレッドで決定したパラメータを入力として実行する。
入力形式は JSON を基本とする。

ただし、`qualify` の入口に載せる候補は、原則として `pass_stability_gate == True` を満たすものに限定する。
`pass_stability_gate == False` の候補は、通常の昇格候補としては扱わず、例外的な再点検対象として明示的に区別する。

想定する入力情報は以下。

- experiment code
- variant code
  - 例: `E001A`
- baseline setting
- 比較対象 filter family
- 閾値群
- date range
- segment policy
- pass_stability_gate
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
  - E001 通過候補の TP / SL 深掘り
- E003
  - E002 通過候補の forced exit 深掘り
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

E004 は昇格審査として独立させる。
E005-E008 は E004 通過後の robustness suite としてまとめて実行してよい。
ただし、評価とレポートは experiment ごとに分ける。

E005-E008 の運用原則は以下。

- default
  - `e005-e008.py` で E005-E008 を一括実行する
- optional
  - 引数で E005 / E006 / E007 / E008 の単独実行を許容する
- params
  - E004 で確定した baseline setting を `e005-e008.json` にコピーして固定する
  - E005 / E007 / E008 の sweep 範囲は ChatGPT 側で決め、`e005-e008.json` から読み込む
  - CLI 引数では sweep / risk 条件を受けない

E005 と E007 では、以下を追加原則とする。

- E005
  - `slip_pips` は one-way 表示とする
  - entry / exit の両方に不利側 slip を乗せるため、実質往復 penalty は `2 * slip_pips`
  - report でも `round_trip_slip_pips` を併記できるようにする
- E007
  - risk grid は `SL5 -> risk_fraction 0.5%` を基準点として組む
  - center は `risk_fraction_center = 0.5% * (sl_pips / 5)` としてよい
  - 比較はこの center と、その前後の保守側 / 攻め側で行う
  - summary には少なくとも `min_maintenance_margin_pct`, `annualized_pips`, `trade_rate`, `win_rate`, `CAGR` を出す

派生実験は `E001A` のように扱ってよい。
ただし、派生は experiment code の意味を壊さず、主実験の補助目的に留める。

## 11. stability gate

`qualify` は `scan` から渡された stability 情報を昇格ゲートとして使う。

`pass_stability_gate` の定義は `src/timer_entry/Spec.md` に従い、初版では以下をすべて満たすものとする。

- `in_gross_pips > 0`
- `out_gross_pips > 0`
- `rank_gap_abs < 100`
- `ex_top10_gross_pips > 0`

`qualify` シリーズ全体では以下を原則とする。

- `pass_stability_gate == True`
  - 通常の昇格審査対象
- `pass_stability_gate == False`
  - 原則として除外
  - ただし、ChatGPT 側スレッドで明示的な理由が付いた再点検や派生実験は許容する

reporting では、少なくとも以下を結果メタデータに保持できるようにする。

- `pass_stability_gate`
- `in_gross_pips`
- `out_gross_pips`
- `rank_gap_abs`
- `ex_top10_gross_pips`

## 12. E001 の位置付け

E001 は `scan` の後段であり、mission は次のいずれかである。

- `scan` で反応した filter family の threshold sweep
- `all` が最上位だった slot の説明可能な範囲での再審査

ここでいう再審査は再探索ではなく、小規模で説明可能な比較に限る。

- 同一 slot / side / entry / forced exit を維持する
- filter 多重組み合わせは行わない
- rolling 分位や年別分位は使わない
- threshold sweep は代表点に限る

E001 でも `pass_stability_gate` を適用する。
したがって、初手の baseline 候補は原則として `pass_stability_gate == True` のものから選ぶ。
`False` の候補を試す場合は、通常線ではなく例外的な監査や派生実験として扱う。

E001 の詳細な比較・旧資産との差分は `qualify/docs/Audit_Result.md` に集約する。

## 13. E002 の位置付け

E002 は E001 の次段であり、mission は以下とする。

- E001 で通した baseline setting を固定する
- filter 条件は原則固定し、TP / SL の小規模 sweep を行う
- 「最良値の探索」ではなく、「壊れにくい近傍」の確認を目的とする

E002 の原則は以下。

- entry / side / forced exit / filter 条件は固定する
- 新規 filter の追加や差し替えは行わない
- TP / SL の sweep は説明可能な近傍に限る
- gross 最大のみで順位を決めない
- PF、maxDD、in/out、ex_top10、trade_count を併せて評価する
- `pass_stability_gate` を引き続き適用する

`qualify` における E002 は、旧 `fx_260312` の `jst10` / `jst12` / `lon08` 系のような
「固定条件に対する小規模 SL/TP sweep」を継承し、`jst09` のような scan 再現型 E002 は継承しない。

E002 の詳細な比較・旧資産との差分は `qualify/docs/Audit_Result.md` に集約する。

## 14. E003 の位置付け

E003 は E002 の次段であり、mission は以下とする。

- E002 で通した baseline setting を固定する
- entry / side / filter / TP / SL を固定したまま、forced exit 時刻だけを sweep する
- 利益最大化ではなく、時間帯分離やロバスト性の観点から、自然な exit 帯を確認する

E003 の原則は以下。

- sweep 対象は forced exit 時刻のみ
- TP / SL / filter / entry は変更しない
- gross 最大のみで順位を決めない
- PF、maxDD、in/out、ex_top10、trade_count を併せて評価する
- `pass_stability_gate` を引き続き前提メタデータとして保持する

`qualify` における E003 は、旧 `fx_260312` の `jst10` / `jst12` / `lon08` 系のような
「固定条件に対する forced exit sweep」を継承する。
`E003A` のような派生は、探索幅や問題設定を広げる variant として扱ってよい。

E003 の詳細な比較・旧資産との差分は `qualify/docs/Audit_Result.md` に集約する。

## 15. E004 の位置付け

E004 は E003 の次段であり、mission は以下とする。

- E003 で選ばれた最終候補を tick replay で昇格審査する
- 約定順序、Bid/Ask 整合、forced exit、slippage、entry delay の現実性を確認する
- 1分足実験と tick 実行を分離し、今後の E005-E008 でも再利用できる共通 engine を整備する

E004 の原則は以下。

- signal 生成と tick 執行を分離する
- 1分足段階で signal day を確定してから、tick で entry / TP / SL / forced exit を再現する
- `tick_executor` は side 主語の価格系列規約を厳守する
- 全 tick 一括ロードは禁止し、対象日・対象時間帯だけを読む
- `ProcessPoolExecutor` などによる日次並列化を許容する
- `pass_stability_gate` は前段候補の前提メタデータとして保持する

`qualify` における E004 は、旧 `*_exhaustive1/common/tick_runner.py` の高速・省メモリな枠組みを継承してよい。
ただし、`tick_executor.py` はそのまま流用せず、side ごとの Bid/Ask 規約を監査済みの共通実装へ再構成する。

E004 の詳細な比較・旧資産との差分は `qualify/docs/Audit_Result.md` に集約する。

## 16. 旧資産の扱い

`fx_260312` は比較用の一時 checkout と位置付ける。
このため、`qualify` の恒久仕様は以下の方針を取る。

- 旧 repo のコード構成には依存しない
- 継承対象は実験の目的、比較軸、注意点に限る
- 旧パスは監査資料にのみ残す
- 実装仕様や README には恒久依存として書かない

旧 `e001.py` は実験色が強いため、そのまま移植しない。
今の core を使って組み直し、エッセンスだけを拝借する。

旧 `e002.py` についても同様に、そのまま移植せず、`E001 -> E002 -> E003` の共通 flow に沿って再構成する。

旧 `e003.py` についても同様に、そのまま移植せず、comparison axis だけを forced exit へ差し替えた共通 runner として再構成する。

旧 `e004.py` についても同様に、そのまま移植せず、signal_provider / tick_runner / tick_executor / report_builder の責務分離を保ったまま、executor の価格系列と sanity を中心に再監査して再構成する。

## 17. 監査ドキュメント

監査結果は `qualify/docs/Audit_Result.md` に集約する。
ここには以下を載せる。

- 旧 `fx_260312` の参照対象
- 仕様差分
- 実装差分
- 継承するもの
- 継承しないもの
- 未解決論点

## 18. 次の実装順

1. ChatGPT 側 prompt を JSON 出力前提に整える
2. `qualify/common/params.py` と scenario 入力契約を定める
3. `qualify/e001.py` と共通 runner を作る
4. reporting を schema 主語で整える
5. E002 の監査結果を反映し、SL / TP sweep runner へ横展開する
6. E003 の監査結果を反映し、forced exit sweep runner へ横展開する
7. E004 の監査結果を反映し、tick replay engine を共通化する
8. E005-E008 suite を `e005-e008.json` 入力で実装する
