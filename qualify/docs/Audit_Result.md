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
