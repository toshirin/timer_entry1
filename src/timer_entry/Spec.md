# timer_entry core Spec

本ドキュメントは `src/timer_entry/` に置く共通 core の実装標準を定める。
対象は `scan` / `qualify` / `runtime` で共通利用するロジックであり、研究憲法の具体的なコード化を目的とする。

最上位規約は [docs/FX_Research_Constitution.md](../../docs/FX_Research_Constitution.md) とする。
本 Spec はそれを実装レベルへ落とした補助仕様であり、矛盾する場合は研究憲法を優先する。

## 1. scope

`src/timer_entry/` に含める初版 scope は以下とする。

- 時刻処理
- 価格系列規約
- 特徴量計算
- 軽量フィルター
- 1分足バックテスト
- 共通 dataclass

初版では tick replay は含めない。
tick replay は `qualify/` 内で共通化する。

## 1.1 用語定義

本リポジトリでは、以下の用語を固定して使う。

- `strategy`
  - 売買のやり方そのものを指す
  - 本リポジトリではタイマー売買戦略を意味する
- `slot`
  - 1時間ごとの時間帯を指す
  - 例として `tyo09` や `lon08` のような単位で扱う
  - `tyo` は `Asia/Tokyo` の `07:00-15:59`、`lon` は `Europe/London` の `08:00-21:59` を対象とする
- `setting`
  - 1つの slot の中で使う具体的な売買条件を指す
  - entry 時刻、forced exit 時刻、TP / SL、軽量フィルター条件を含む

schema では、主に以下の対応を取る。

- `strategy`
  - `strategy_id`
- `slot`
  - `slot_id`
- `setting`
  - `setting_id`
  - `StrategySetting`
  - `RuntimeConfig`

## 2. 最重要原則

### 2.1 Bid / Ask 完全分離

各 side で使用する価格系列は固定とし、呼び出し側の気分で差し替えない。

- Buy
  - entry 価格: Ask
  - TP 判定: Bid
  - SL 判定: Ask
  - forced exit: 原則 Bid
- Sell
  - entry 価格: Bid
  - TP 判定: Ask
  - SL 判定: Bid
  - forced exit: 原則 Ask

各 backtest / runtime / report 出力には、実際に使用した価格系列名を必ず記録する。

### 2.2 未来参照禁止

- entry より後に確定する情報を filter 判定に使わない
- feature window は entry 直前までで閉じる
- entry バー内の TP / SL 判定を行わない
- same-bar 競合は順序情報が取れる場合のみ順序判定し、取れない場合は不利側優先とする

### 2.3 監視窓の分離

- SL / TP の監視開始は entry 直後とする
- forced exit 監視と同一ロジックに混ぜない
- `monitor_start = max(entry, exit_start)` のような混同を禁止する

## 3. 想定モジュール

初版では以下のような構成を想定する。

- `src/timer_entry/time_utils.py`
  - `Time_JST` 優先の時刻復元
  - market timezone 変換
  - 日付境界とローカル時刻窓処理
- `src/timer_entry/direction.py`
  - side ごとの価格系列規約
- `src/timer_entry/features.py`
  - 共通特徴量計算
- `src/timer_entry/filters.py`
  - canonical filter 定義と評価器
- `src/timer_entry/backtest_1m.py`
  - 1分足ベースの共通バックテスト
- `src/timer_entry/schemas.py`
  - 共通 dataclass
- `src/timer_entry/reporting.py`
  - sanity summary と series metadata の出力補助

これは初版案であり、実装の都合で分割は調整してよい。
ただし責務の境界は維持する。

## 4. 時刻処理仕様

### 4.1 1分足時刻

- DataFrame index は broker time `UTC+3` とみなす
- 時刻の基準は `Time_JST` を優先使用する
- `Time_JST` が無い、または不正な行のみ index から JST を復元する
- JST 復元時は repo 慣習に従い broker time から `+6時間` 相当で扱う

### 4.2 市場時刻

- Tokyo 系は `Asia/Tokyo`
- 東京以外は `Europe/London`
- セッションごとの entry / forced exit / feature window は market local time 基準で定義する
- 東京以外は DST aware に扱うため、時間帯集計の基準時計として `Europe/London` を使う
- London と NY は市場が重なるため、時間帯基準を頻繁に切り替えない
- 米国統計時間は market timezone を切り替えて吸収せず、除外窓として別処理する

### 4.3 除外窓

- 外生ショックを避けるための時刻帯は `exclude_windows` として別管理する
- 代表例は米国統計時間帯である
- 除外窓は時間帯集計の基準 timezone とは独立して扱う

### 4.4 監視開始

- 1分足 backtest では entry バーの次バーから TP / SL 判定を始める
- tick replay では entry 約定直後から監視する

## 5. DirectionSpec

Bid / Ask 規約はコード上でも固定する。
そのため `direction.py` に side ごとの series set を定義する。

主要 dataclass 案:

```python
@dataclass(frozen=True)
class DirectionSpec:
    side: Literal["buy", "sell"]
    entry_col: str
    tp_hit_col: str
    tp_time_col: str | None
    sl_hit_col: str
    sl_time_col: str | None
    forced_exit_col: str
    tp_sign: int
    sl_sign: int
```

責務:

- side ごとの entry / TP / SL / forced exit 系列を固定する
- backtest と report の双方で使用系列を参照できるようにする
- Buy / Sell の計算分岐を列名の分散ではなく spec に閉じ込める

初版では `BUY_SPEC` と `SELL_SPEC` を定数として持つ。

## 6. 共通特徴量

初版で canonical とする特徴量は以下である。
いずれも feature window は `t-55 .. t-5` を基本とする。

### 6.1 pre_open_slope

- `close(t-5) - open(t-55)` を pips 化したもの
- 価格系列は Bid を用いる

出力名:

- `pre_open_slope_pips`

### 6.2 左右の形

前半 25 分と後半 25 分の値動き比較のみを扱う。

- `left_ret_pips = close(t-30) - open(t-55)`
- `right_ret_pips = close(t-5) - open(t-30)`
- `left_abs = abs(left_ret_pips)`
- `right_abs = abs(right_ret_pips)`

出力名:

- `left_ret_pips`
- `right_ret_pips`
- `left_abs_pips`
- `right_abs_pips`

### 6.3 pre_range

- `pre_range_pips = max(Bid_High) - min(Bid_Low)` on `t-55 .. t-5`

出力名:

- `pre_range_pips`

### 6.4 trend_ratio

- `net_move_pips = close(t-5) - open(t-55)`
- `path_range_pips = pre_range_pips`
- `trend_ratio = abs(net_move_pips) / path_range_pips`
- `path_range_pips <= 0` の場合は `NaN`

出力名:

- `net_move_pips`
- `trend_ratio`

## 7. 軽量フィルター canonical 定義

本リポジトリでは以下の filter 名を canonical とする。
同じ名前で異なる中身を使うことを禁止する。

ただし、scan と qualify では filter の使い方が異なる。

- scan
  - filter family ごとの当たりを見る段階
  - 基本閾値だけを確認する
- qualify
  - 反応した filter family を深掘りする段階
  - 同一 family 内で threshold sweep や percentile sweep を行う

そのため core では、可能であれば `filter family` と `filter instance` を分けて扱う。

### 7.1 pre_open_slope 系

- `all`
  - 常に通す
- `ge0`
  - `pre_open_slope_pips >= 0`
- `le0`
  - `pre_open_slope_pips <= 0`

scan の初期探索では `ge0` / `le0` のような基本閾値を使う。
qualify では `ge2` / `ge4` などの追加閾値を sweep してよい。

### 7.2 左右の形

- `left_stronger`
  - `abs(left_ret_pips) > abs(right_ret_pips)`
- `right_stronger`
  - `abs(right_ret_pips) > abs(left_ret_pips)`
- `same_sign`
  - `left_ret_pips` と `right_ret_pips` の符号が同じ
  - どちらかが 0 の場合も同符号側として扱う
- `opposite_sign`
  - `left_ret_pips` と `right_ret_pips` の符号が逆
  - 0 を含む場合は不通過とする

### 7.3 ボラ系

`vol_ge_med` は標準偏差ボラではない。
本リポジトリでは以下に固定する。

- `vol_ge_med`
  - `pre_range_pips >= global_median(pre_range_pips)`
- `vol_lt_med`
  - `pre_range_pips < global_median(pre_range_pips)`

ここでいう `global_median` は、その実験対象期間全体で計算した median とする。
年別 median や std-based volatility を同名で呼んではならない。

scan では `vol_ge_med` / `vol_lt_med` のような基本二値だけを使う。
qualify では percentile ベースの深掘りを追加してよいが、canonical 名と別名にするか、threshold を明示して区別する。

### 7.4 レンジ / トレンド状態

- `trend_ge_0_5`
  - `trend_ratio >= 0.5`
- `range_lt_0_3`
  - `trend_ratio < 0.3`

## 8. filter 評価の標準化

filter は runtime でも scan / qualify でも同じ評価器を使う。
初版では以下を守る。

- filter 名と閾値定義は `filters.py` に集約する
- runtime 側だけ独自解釈を入れない
- report 出力には filter 名、閾値、実測値を残せるようにする

## 8.1 scan の stability gate

scan は filter family の当たりを見る段階だが、gross の大きさだけで昇格候補を決めてはならない。
`probe5` で用いていた `in/out` 安定性と `exclude top10` の思想は、本リポジトリでも上位仕様として維持する。

scan summary では少なくとも以下を計算する。

- `trade_count_in`
- `trade_count_out`
- `in_gross_pips`
- `out_gross_pips`
- `gross_pips`
- `rank_in`
- `rank_out`
- `rank_gap_abs`
- `top1_share_of_total`
- `ex_top10_gross_pips`
- `pass_stability_gate`

ここで、

- `in`
  - 初版では `2019-2022`
- `out`
  - 初版では `2023-2025`

とする。

`rank_in` と `rank_out` は、同一 summary 集合の中での `in_gross_pips` / `out_gross_pips` の順位である。
`rank_gap_abs = abs(rank_in - rank_out)` は、in では上位でも out で崩れる候補を検出するための指標である。

`ex_top10_gross_pips` は、上位 10 日を除外した後でも損益が正かを見る指標であり、一部の大当たり依存を避けるために使う。

初版の `pass_stability_gate` は以下をすべて満たすものとする。

- `in_gross_pips > 0`
- `out_gross_pips > 0`
- `rank_gap_abs < 100`
- `ex_top10_gross_pips > 0`

`qualify` の優先順位付けでは、原則として `pass_stability_gate == True` の候補を優先し、これを満たさない候補は除外または強く減点する。

## 9. 1分足 backtest 仕様

### 9.1 entry と exit

- entry 価格は `DirectionSpec.entry_col`
- forced exit 価格は `DirectionSpec.forced_exit_col`
- TP / SL 判定は `DirectionSpec.tp_hit_col` と `DirectionSpec.sl_hit_col`

### 9.2 entry バー内判定の禁止

- entry バー内の TP / SL 判定は行わない
- 1分足 backtest の監視開始は次バーからとする

### 9.3 same-bar 競合

- 同じバーで TP / SL の両方が成立しうる場合は `*_Time` で順序判定する
- 順序が不明なら不利側優先とする
- 不利側優先を行った件数は sanity に記録する

### 9.4 sanity 項目

少なくとも以下を記録する。

- `entry_price_series`
- `tp_price_series`
- `sl_price_series`
- `forced_exit_price_series`
- `entry_equals_exit_count`
- `entry_equals_exit_sl_count`
- `same_bar_conflict_count`
- `same_bar_unresolved_count`
- `forced_exit_count`
- `forced_exit_missing_count`
- `feature_skip_count`

## 10. schemas の責務

ここでいう `schemas` は、scan / qualify / runtime 間で受け渡す共通データ構造である。
`dict` の場当たり的な増殖を防ぎ、名称と意味を固定するために置く。

主要 dataclass の候補は以下とする。

### 10.1 StrategySetting

責務:

- 実運用または backtest で使う基本 setting を表現する

主要フィールド:

- `setting_id`
- `slot_id`
- `side`
- `market_tz`
- `exclude_windows`
- `entry_clock_local`
- `forced_exit_clock_local`
- `tp_pips`
- `sl_pips`
- `filter_labels`
- `pre_range_threshold`

### 10.2 RuntimeConfig

責務:

- runtime がそのまま consume する設定 JSON を表現する
- `StrategySetting` から機械的に変換できるようにする

主要フィールド:

- `setting_id`
- `strategy_id`
- `slot_id`
- `market_session`
- `market_tz`
- `side`
- `entry_clock_local`
- `forced_exit_clock_local`
- `trigger_bucket_entry`
- `trigger_bucket_exit`
- `tp_pips`
- `sl_pips`
- `filter_spec_json`
- `execution_spec_json`

### 10.3 ScanCandidate

責務:

- scan の探索結果から、qualify に渡す候補を表現する

主要フィールド:

- `candidate_id`
- `session_label`
- `side`
- `entry_clock_local`
- `forced_exit_clock_local`
- `filter_labels`
- `tp_pips`
- `sl_pips`
- `pre_range_threshold`
- `summary`

### 10.4 QualifyScenario

責務:

- E001-E008 の実行条件を表現する

主要フィールド:

- `scenario_id`
- `experiment_code`
- `base_setting`
- `date_from`
- `date_to`
- `slippage_mode`
- `fixed_slippage_pips`
- `entry_delay_seconds`
- `risk_fraction`

### 10.5 BacktestTrade

責務:

- 1 trade の実行結果を標準形式で持つ

主要フィールド:

- `trade_id`
- `date_local`
- `side`
- `entry_time`
- `entry_price`
- `exit_time`
- `exit_price`
- `exit_reason`
- `pnl_pips`
- `hold_minutes`
- `entry_price_series`
- `exit_price_series`

### 10.6 BacktestSummary

責務:

- summary.csv 相当の主要 KPI を標準形式で持つ

主要フィールド:

- `trade_count`
- `gross_pips`
- `mean_pips`
- `median_pips`
- `std_pips`
- `win_rate`
- `profit_factor`
- `max_dd_pips`
- `annualized_pips`

### 10.7 SanitySummary

責務:

- series 使用実績と危険信号を集約する

主要フィールド:

- `entry_price_series`
- `tp_price_series`
- `sl_price_series`
- `forced_exit_price_series`
- `same_bar_conflict_count`
- `entry_equals_exit_sl_count`
- `forced_exit_missing_count`
- `time_jst_fallback_count`
- `duplicate_clock_removed_count`

## 11. scan / qualify / runtime の関係

- scan
  - 候補発見のために広く探索する
- qualify
  - 候補の深掘りと昇格審査を行う
- runtime
  - qualify で通した setting を実運用に載せる

3者は入口が違うだけで、以下は同じ core を共有する。

- DirectionSpec
- 特徴量
- 軽量フィルター
- 1分足 backtest の価格系列規約
- 共通 dataclass

### 11.1 実行 engine の分担

実行 engine は複数あってよい。
ただし、違ってよいのは実装方式と計算速度であり、仕様差分を持ち込んではならない。

- `scan`
  - 高速 engine を使う
  - 目的は slot ごとの全探索と、軽量フィルター family の当たり探し
- `qualify`
  - pandas ベースの canonical `backtest_1m.py` を使う
  - 目的は setting の深掘りと、軽量フィルター閾値の探索
- `tick replay`
  - tick ベース engine を使う
  - 目的は約定順序、slippage、entry delay、forced exit 現実性の確認

3者は engine が別でも、少なくとも以下は同じ core に従う。

- DirectionSpec
- 特徴量定義
- filter 定義
- same-bar 解釈
- 保守的 SL exit モデル

## 12. parity test 方針

共通化により独立監査性は弱まるため、以下で補う。

- Buy / Sell の series 使用が spec 通りであること
- entry バー内 TP / SL 判定禁止が守られること
- same-bar 競合で順序判定と不利側優先が正しく働くこと
- runtime filter 評価と scan / qualify filter 評価が一致すること
- report 出力の series metadata が欠落しないこと

## 13. 今後の拡張

- tick replay を将来 core へ昇格するかは、`qualify/` の成熟後に判断する
- filter 種別の追加は canonical 定義を壊さない範囲で行う
- 新しい filter 名を導入する場合は、本 Spec を先に更新する
