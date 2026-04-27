# Audit Result

本ドキュメントは `qualify/` 実装に向けた監査結果を集約する。
比較対象の旧資産は一時 checkout 中の `fx_260312` を参照する。

## 1. 参照対象

比較・監査対象は以下。

- `../fx_260312/research/jst09_exhaustive1/e001.py`
- `../fx_260312/research/jst10_exhaustive1/e001.py`
- `../fx_260312/research/lon08_exhaustive1/e001.py`
- `../fx_260312/research/jst09_exhaustive1/specs/jst09_exhaustive1_E001_E002_Spec_for_Codex.md`
- `../fx_260312/research/jst10_exhaustive1/specs/jst10_exhaustive1_E001_Spec_for_Codex.md`
- `../fx_260312/research/jst12_exhaustive1/specs/jst12_exhaustive1_E001_Spec_for_Codex.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E001_spec.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E001A_spec.md`

## 2. 現時点の結論

- 旧 `e001.py` は slot 固定の個別実験としては有用
- ただし、`qualify` の共通基盤へはそのまま移植しない
- 継承すべきなのは実験の目的と比較軸
- 実装は現在の core を使って組み直す

## 3. 継承するもの

- E001 は監査付きモデル実験であり、新規大規模探索ではない
- `all` を baseline として残し、改善候補を比較する
- in / out / year / DD / PF を見る
- `pass_stability_gate` を昇格ゲートとして使う
- tick replay は後続 E004 へ分離する
- `all` 主線 slot でも、小規模な再審査は許容する

## 4. 継承しないもの

- slot ごとの `e001.py` 個別実装
- series ごとに複製された `common/`
- filter 名の方言
- summary 出力の列揺れ
- Buy / Sell 別 util の複製

## 5. 旧実装との差分

- 旧 repo
  - slot 単位のシリーズ実装
  - feature 計算、filter 解釈、summary 出力が series 内に埋め込まれがち
  - E001 が再現実験寄りのものと、深掘り寄りのものが混在
- 新 repo
  - `scan` と `qualify` を repo 上位で分離
  - core 仕様は `src/timer_entry/` に集約済み
  - `qualify` は experiment code ごとの共通基盤として設計する
  - 出力は schema 主語に統一する

## 6. E001 監査メモ

- `all` 本命 slot については、旧 `lon08` E001 / E001A のような代表点比較の考え方が有用
- 旧 `jst10` / `jst12` の仕様書にある「監査付き小規模比較」という位置付けは継承する
- 旧 `jst09` のような再現実験型 E001 は、そのままでは今回の `scan -> qualify` 流れと一致しない
- ただし、現行 `qualify` では E001 も `pass_stability_gate` を前提ゲートとして扱う
- gate を満たさない候補は、通常の E001 本線ではなく、例外的な再点検や派生実験として切り分ける

## 7. E002 監査メモ

### 7.1 参照対象

- `../fx_260312/research/jst10_exhaustive1/e002.py`
- `../fx_260312/research/jst12_exhaustive1/e002.py`
- `../fx_260312/research/lon08_exhaustive1/e002.py`
- `../fx_260312/research/jst09_exhaustive1/e002.py`
- `../fx_260312/research/jst10_exhaustive1/specs/jst10_exhaustive1_E002_Spec_for_Codex.md`
- `../fx_260312/research/jst12_exhaustive1/specs/jst12_exhaustive1_E002_Spec_for_Codex.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E002_spec.md`
- `../fx_260312/research/jst09_exhaustive1/specs/jst09_exhaustive1_E001_E002_Spec_for_Codex.md`

### 7.2 結論

- 旧 `jst10` / `jst12` / `lon08` の E002 は、ほぼ「固定条件に対する小規模 SL/TP sweep」で共通化しやすい
- 旧 `jst09` の E002 は 9時台全体の scan 再現色が強く、今回の `qualify` の E002 には継承しない
- したがって、`qualify/E002` は「E001 通過候補を固定し、TP / SL だけを sweep する段階」と再定義するのが妥当

### 7.3 継承するもの

- E002 は E001 通過候補の次段である
- filter 条件は固定したまま TP / SL を小規模 sweep する
- forced exit は原則固定する
- gross 最大だけで決めず、PF / maxDD / in/out / ex_top10 を見る
- 過剰最適化を避けるため sweep 範囲は近傍に限る
- entry バー監視禁止、same-bar、不利側優先などの canonical 仕様を維持する

### 7.4 継承しないもの

- slot ごとに別々の candidate grid をコードへ埋め込む構成
- series ごとの独自 summary 列
- scan 再現型 E002
- heatmap や top10 CSV を experiment 固有の必須成果物にする設計

### 7.5 `qualify` 向け定義

`qualify/E002` の定義は以下がよい。

- 入力
  - E001 で選ばれた baseline setting
  - TP 候補群
  - SL 候補群
  - `pass_stability_gate`
- 固定するもの
  - slot
  - side
  - entry
  - forced exit
  - filter 条件
- sweep するもの
  - TP / SL のみ
- 出力
  - schema 主語の summary / split / year / trades / sanity
  - comparison label として `tp/sl` を持つ

### 7.6 実装含意

- E001 runner の構造をかなり流用できる
- 差分は comparison axis が filter label から `tp/sl grid` に変わる点だけに近い
- `qualify/common/reporting.py` も大部分を再利用できるはず
- E002 では `pass_stability_gate` を再計算するというより、E001 から持ち込んだ baseline の gate 状態を前提メタデータとして保持するのが自然

## 8. E003 監査メモ

### 8.1 参照対象

- `../fx_260312/research/jst10_exhaustive1/e003.py`
- `../fx_260312/research/jst12_exhaustive1/e003.py`
- `../fx_260312/research/lon08_exhaustive1/e003.py`
- `../fx_260312/research/jst09_exhaustive1/e003.py`
- `../fx_260312/research/jst10_exhaustive1/specs/jst10_exhaustive1_E003_Spec_for_Codex.md`
- `../fx_260312/research/jst12_exhaustive1/specs/jst12_exhaustive1_E003_Spec_for_Codex.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E003_spec.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E003A_spec.md`
- `../fx_260312/research/jst09_exhaustive1/specs/E003_Spec.md`

### 8.2 結論

- 旧 `jst10` / `jst12` / `lon08` の E003 は、ほぼ「固定条件に対する forced exit sweep」で共通化しやすい
- `lon08` では E003A のような探索幅拡張が行われており、これは `variant_code` で素直に表現できる
- したがって、`qualify/E003` は「E002 通過候補を固定し、forced exit 時刻だけを sweep する段階」と再定義するのが妥当

### 8.3 継承するもの

- E003 は E002 通過候補の次段である
- filter / TP / SL / entry は固定したまま forced exit だけを sweep する
- gross 最大だけで決めず、PF / maxDD / in/out / ex_top10 を見る
- 時刻帯分離や隣接 slot との干渉回避を評価軸に含めてよい
- entry バー監視禁止、same-bar、不利側優先などの canonical 仕様を維持する

### 8.4 継承しないもの

- slot ごとに別々の forced exit 候補配列をコードへ埋め込む構成
- series ごとの独自 summary 列や time profile 専用 CSV を必須成果物にする設計
- slot 固有の議論を本体仕様へ埋め込む構成

### 8.5 `qualify` 向け定義

`qualify/E003` の定義は以下がよい。

- 入力
  - E002 で選ばれた baseline setting
  - forced exit 候補群
  - `pass_stability_gate`
- 固定するもの
  - slot
  - side
  - entry
  - filter 条件
  - TP / SL
- sweep するもの
  - forced exit 時刻のみ
- 出力
  - schema 主語の summary / split / year / trades / sanity
  - comparison label として `forced_exit_clock_local` を持つ

### 8.6 実装含意

- E002 runner の構造をかなり流用できる
- 差分は comparison axis が `tp/sl grid` から `forced_exit grid` に変わる点だけに近い
- `variant_code` で `E003A` のような拡張探索も表現しやすい
- E003 でも gate は再計算するというより、前段から持ち込んだ baseline の gate 状態を前提メタデータとして保持するのが自然

## 9. 未解決論点

- ChatGPT 側から受け取る JSON の最終 schema
- `E001A` のような派生コードの命名・保存ルール
- report 形式の最終標準形
- E002 以降で共通利用する scenario metadata の最小集合
- `pass_stability_gate == False` の候補をどの粒度で例外許可するか
- E002 の TP / SL grid を ChatGPT 側 JSON でどこまで自由化するか
- E003 の forced exit grid を ChatGPT 側 JSON でどこまで自由化するか
- E004 の signal metadata と tick request の最小 schema

## 10. E004 監査メモ

### 10.1 参照対象

- `../fx_260312/research/jst09_exhaustive1/e004.py`
- `../fx_260312/research/jst10_exhaustive1/e004.py`
- `../fx_260312/research/jst12_exhaustive1/e004.py`
- `../fx_260312/research/lon08_exhaustive1/e004.py`
- `../fx_260312/research/jst09_exhaustive1/common/tick_executor.py`
- `../fx_260312/research/jst10_exhaustive1/common/tick_executor.py`
- `../fx_260312/research/jst12_exhaustive1/common/tick_executor.py`
- `../fx_260312/research/lon08_exhaustive1/common/tick_executor.py`
- `../fx_260312/research/jst09_exhaustive1/common/tick_runner.py`
- `../fx_260312/research/jst10_exhaustive1/common/tick_runner.py`
- `../fx_260312/research/jst12_exhaustive1/specs/jst12_exhaustive1_E004_Spec_for_Codex.md`
- `../fx_260312/research/jst10_exhaustive1/specs/jst10_exhaustive1_E004_Spec_for_Codex.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E004_spec.md`
- `../fx_260312/research/jst09_exhaustive1/specs/E004_Spec.md`

### 10.2 結論

- `tick_runner.py` の枠組みは軽量で、signal day 単位の並列化と対象時間帯だけの tick 読み込みになっており、`qualify` でも継承価値が高い
- `tick_executor.py` は series 間でほぼコピペだが、`jst10` short 側だけ Bid/Ask 非準拠である
- したがって、E004 では runner / io の枠組みは維持しつつ、executor は side 主語で共通化して再実装するのが妥当

### 10.3 series 別監査表

- `jst09`
  - side: buy
  - entry series: ask
  - TP hit series: bid
  - SL hit series: ask
  - exit / forced exit series: bid
  - compliant: yes
- `jst12`
  - side: buy
  - entry series: ask
  - TP hit series: bid
  - SL hit series: ask
  - exit / forced exit series: bid
  - compliant: yes
- `lon08`
  - side: buy
  - entry series: ask
  - TP hit series: bid
  - SL hit series: ask
  - exit / forced exit series: bid
  - compliant: yes
- `jst10`
  - side: sell
  - entry series: ask
  - TP hit series: bid
  - SL hit series: ask
  - exit / forced exit series: bid
  - compliant: no

### 10.4 `jst10` の非準拠点

`jst10_exhaustive1/common/tick_executor.py` は short 側で以下の問題を持つ。

- entry を `ask` で持っている
- TP 判定を `bid <= tp_level` にしている
- SL 判定を `ask >= sl_level` にしている
- exit と forced exit を `bid` にしている
- PnL を `entry_ask - exit_bid` で計算している

short の canonical 規約は以下である。

- entry: `bid`
- TP 判定: `ask`
- SL 判定: `bid`
- exit / forced exit: `ask`

したがって `jst10` の tick replay は non-compliant と判断する。

### 10.5 継承するもの

- signal_provider / tick_executor / tick_runner / report_builder の責務分離
- signal day 単位の並列化
- 全 tick 一括ロードを避ける対象日・対象時間帯限定の読み込み
- slippage / entry delay フック
- sanity summary の集計方針

### 10.6 継承しないもの

- series ごとの `tick_executor.py` コピペ
- buy/sell 別の価格系列規約をコードに埋め込む構成
- short 側の non-compliant な実装
- series ごとに微妙に異なる request schema

### 10.7 `qualify` 向け定義

`qualify/E004` の定義は以下がよい。

- 入力
  - E003 で選ばれた baseline setting
  - date range
  - slippage mode
  - entry delay
  - jobs
- 固定するもの
  - entry / TP / SL / forced exit の setting
  - side
  - filter 条件
- 共通化するもの
  - signal_provider
  - tick_io
  - tick_runner
  - tick_executor
  - reporting
- 出力
  - signal days
  - trades
  - summary / yearly / sanity
  - minute baseline との差分比較

### 10.8 実装含意

- `tick_runner` は旧実装の構造をほぼ踏襲してよい
- `tick_executor` は `DirectionSpec` 相当の side 定義を使う形で書き直すべき
- E005-E008 でも同じ tick engine を使う前提で、request / trade / sanity の schema を最初から共通化するのがよい
- E004 は E005-E008 の前提 engine になるため、ここで side 規約と memory model を固める価値が高い

## 11. E005-E008 監査メモ

### 11.1 参照対象

- `../fx_260312/research/jst09_exhaustive1/e005.py`
- `../fx_260312/research/jst09_exhaustive1/e006.py`
- `../fx_260312/research/jst09_exhaustive1/e007.py`
- `../fx_260312/research/jst09_exhaustive1/e008.py`
- `../fx_260312/research/jst10_exhaustive1/e005.py`
- `../fx_260312/research/jst10_exhaustive1/e006.py`
- `../fx_260312/research/jst10_exhaustive1/e007.py`
- `../fx_260312/research/jst10_exhaustive1/e008.py`
- `../fx_260312/research/jst12_exhaustive1/e005.py`
- `../fx_260312/research/jst12_exhaustive1/e006.py`
- `../fx_260312/research/jst12_exhaustive1/e007.py`
- `../fx_260312/research/jst12_exhaustive1/e008.py`
- `../fx_260312/research/lon08_exhaustive1/e005.py`
- `../fx_260312/research/lon08_exhaustive1/e006.py`
- `../fx_260312/research/lon08_exhaustive1/e007.py`
- `../fx_260312/research/lon08_exhaustive1/e008.py`
- `../fx_260312/research/jst09_exhaustive1/specs/E005_E008_Spec.md`
- `../fx_260312/research/jst10_exhaustive1/specs/jst10_exhaustive1_E005_E008_Spec_for_Codex.md`
- `../fx_260312/research/jst12_exhaustive1/specs/jst12_exhaustive1_E005_E008_Spec_for_Codex.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E005_E008_spec.md`
- `../fx_260312/research/jst10_exhaustive1/common/safety_checks.py`

### 11.2 結論

- 旧 E005-E008 は、実装・仕様ともに「E004 通過 setting を固定し、variant axis だけ差し替える安全性 suite」としてかなり共通化しやすい
- 一方で、旧 spec は「各 experiment は独立に実施」と書く series が多く、評価軸も experiment ごとに異なる
- したがって、`qualify` では「実行入口は suite 化、評価と出力は experiment ごとに分離」とするのが妥当
- E004 は独立の関門として残し、E005-E008 だけを `e005-e008.py` にまとめる方が自然

### 11.3 継承するもの

- E004 の tick replay 基盤をそのまま使う
- signal / setting / TP / SL / forced exit は固定する
- E005 は slippage 軸だけを振る
- E006 は walk-forward split だけを振る
- E007 は target maintenance margin / kill-switch 軸だけを振る
- E008 は entry delay 軸だけを振る
- 出力は summary / yearly / sanity を基本にする

### 11.4 継承しないもの

- slot ごとに別ファイルでほぼ同じロジックを複製する構成
- series ごとに少しずつ異なる summary 列
- E005-E008 を完全に別々の params schema に分割する前提
- E004 まで suite へ含める構成

### 11.5 experiment 別監査

#### E005

- 実質は `run_tick_replay_batch(..., slippage_mode="fixed", fixed_slippage_pips=slip)` の grid 実験
- `append_variant_metrics` により baseline slip=0 比の劣化率を追加している
- `jst10` は slip grid が `(0.0, 0.2, 0.4, 0.6)`、`jst12/lon08/jst09` は `(0.0, 0.1, 0.2, 0.3)` 系で、grid 自体は slot 依存
- 旧実装は entry / exit の両方に slip を乗せるため、表示上の `slip_pips=0.3` は実質往復 `0.6 pips` の penalty に相当する
- よって `qualify/E005` では、`slip_pips` を one-way 表示とし、必要なら `round_trip_slip_pips = 2 * slip_pips` を併記すべき
- よって、engine は完全共通化し、grid は params / CLI 指定に逃がすのがよい

#### E006

- 実質は E004 trades を固定して walk-forward summary を追加計算しているだけ
- 旧 `build_walkforward_summary` は `train 2y -> test 1y` rolling で、train 側再最適化は行っていない
- code 上も tick replay 再実行を必須としない構造で、suite 内では最も軽い

#### E007

- 実質は E004 trades を固定して equity curve を後段計算する段階
- E007 は E004 trades を固定し、複数の `target_maintenance_margin_pct` で equity curve を比較する
- grid は通常 `[150, 180, 200]`、必要に応じて `[150, 180, 200, 230, 260]` とし、params へ逃がす
- `maintenance_below_100_count > 0` は一発NG、`stop_triggered` または `maintenance_below_130_count > 0` は一段上の維持率確認シグナルとする
- 採用判断は CAGR 最大ではなく、安全条件を満たした最初の維持率候補で行う
- summary では少なくとも `target_maintenance_margin_pct`, `min_maintenance_margin_pct`, `maintenance_below_130_count`, `maintenance_below_100_count`, `stop_triggered`, `pips_year_rate_pct_at_150usd`, `annualized_pips`, `trade_rate`, `win_rate`, `CAGR` を持つべき

#### E008

- 実質は `entry_delay_seconds` の grid 実験
- 旧 code でも E005 とほぼ鏡像で、variant axis が slip から delay に変わるだけ
- `jst10` は `(0, 30, 60, 120)`、`jst12/lon08/jst09` は `(0, 5, 10, 15, 20, 30)` 系で、grid は slot 依存

### 11.6 `qualify` 向け定義

`qualify/E005-E008` の定義は以下がよい。

- 入力
  - 原則として `qualify/params/{slot_id}/{version_id}/e004.json`
  - E004 通過済みの baseline setting
- 実行入口
  - `qualify/e005-e008.py`
- default
  - E005-E008 を一括実行
- optional
  - `--only E005` などで単独実行
- 出力
  - `qualify/out/E005/...`
  - `qualify/out/E006/...`
  - `qualify/out/E007/...`
  - `qualify/out/E008/...`

追加で以下を明示するのがよい。

- E005
  - `slip_pips` は one-way 表示
  - 実質往復 penalty は `round_trip_slip_pips = 2 * slip_pips`
- E007
  - maintenance margin grid は `[150, 180, 200]` を基本に置く
  - `trade_rate` は `trade_count / eligible_day_count` として定義する

### 11.7 実装含意

- E005 と E008 は同じ variant-runner で実装できる
- E006 と E007 は tick replay 後段集計として実装できる
- `common/safety_checks.py` 相当の helper 群を `qualify/common/e005_e008.py` に集約するのが自然
- suite 入口は共通でよいが、summary / sanity / report は experiment ごとに分けるべき

## 12. Claude Code 監査結果と対応

Claude Code による `qualify/` 監査で、以下を確認した。

### 12.1 false positive

- `tick_executor.py` の exit slippage で `side="sell" if spec.side == "buy" else "buy"` としている点は、誤りではない
- Buy の bid exit は sell 側に滑らせて下方向へ不利化し、Sell の ask exit は buy 側に滑らせて上方向へ不利化するため、意図どおり

### 12.2 修正済み

- `qualify/common/e005_e008.py` の `suite_metadata` で未定義の `initial_capital_jpy` を参照していた問題を、`params.initial_capital_jpy` 参照へ修正した
- `qualify/common/tick_replay/tick_executor.py` の forced exit 境界を、1分足 engine と同じく cutoff ちょうどの tick まで TP/SL 監視対象へ含める形へ修正した
- tick replay の必須 schema を `epoch_us` / `bid` / `ask` として検証し、欠けている場合は fail-fast するようにした
- tick replay の TP/SL 判定列は helper 経由に寄せ、`bid` / `ask` の直書き分散を減らした
- `qualify/common/e004.py` の `pass_stability_gate` は前段候補の gate 状態を保持する意味へ戻した
- E004 tick 後の簡易 in/out 陽性判定は `tick_pass_positive_inout_gate` として別列に分離した
- `qualify/common/e005_e008.py` の out-sample 年は `reporting.DEFAULT_OUT_YEARS` を参照するようにした
- E006 の test year 範囲は `DEFAULT_WALKFORWARD_TEST_YEARS` に定数化し、train 側再最適化を行わない yearly out-sample stress summary であることをコメント化した

### 12.3 残留メモ

- tick replay で同一 tick に TP/SL が同時成立した場合は、tick 内 event time がないため SL 優先とする
- このケースは Bid/Ask の異常や極端な spread 状況を示す可能性があるため、`tp_sl_same_tick_flag` の sanity count として監視する
