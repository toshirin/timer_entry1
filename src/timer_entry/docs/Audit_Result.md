# Audit Result

本ドキュメントは `src/timer_entry/` の core 実装に対する監査結果を集約する。
対象は `scan` / `qualify` / `runtime` で共有する意味論であり、個別 experiment の比較結果は含めない。

## 1. 監査対象

- `direction.py`
- `time_utils.py`
- `minute_data.py`
- `features.py`
- `filters.py`
- `schemas.py`
- `backtest_1m.py`
- `backtest_fast.py`
- `tests/test_backtest_parity.py`
- `tests/test_event_times.py`

旧資産比較では主に以下を参照した。

- `../fx_260312/research/probe5`
- `../fx_260312/research/jst09_exhaustive1`
- `../fx_260312/research/jst10_exhaustive1`
- `../fx_260312/research/jst12_exhaustive1`
- `../fx_260312/research/lon08_exhaustive1`
- `../fx_260312/infer/timed_entry_runtime1`

## 2. 現時点の結論

- core の意味論は旧資産の寄せ集めではなく、研究憲法準拠の canonical として再定義した
- Bid / Ask、same-bar、保守的 SL exit、event time の扱いは core に固定済み
- `backtest_1m.py` と `backtest_fast.py` の parity は synthetic test で通過済み
- event time 列の基礎テストも通過済み
- したがって、core 初版は実装上の基準として採用してよい

## 3. 検知・反映済みの主な論点

### 3.1 Bid / Ask 規約

- `probe5` は探索系として有用だが、exit 価格モデルは canonical に採らない
- `jst10` Sell は `entry=Ask / forced_exit=Bid` 系で明確な非整合があり、canonical 参照元から除外した
- `probe5` の `DirectionSpec` 自体は原型として有用だが、`sl_grid / tp_grid` をそのまま損益化するため、そのまま canonical 実装基準には使わない
- `jst09` / `lon08` の Buy 系は `entry=Ask_Open`、`TP hit=Bid_High`、`SL hit=Ask_Low`、`forced_exit=Bid_Close` で整合しており、Buy canonical の主要参照元とした
- runtime の Oanda 実売買意味論も Buy/Sell の向きはこれと整合しているため、Sell は runtime 側意味論を主参照にした
- canonical は以下で固定した
  - Buy
    - entry: `Ask_Open`
    - TP hit: `Bid_High`
    - SL hit: `Ask_Low`
    - forced exit: `Bid_Close`
  - Sell
    - entry: `Bid_Open`
    - TP hit: `Ask_Low`
    - SL hit: `Bid_High`
    - forced exit: `Ask_Close`

### 3.1.1 `direction.py` に対する補足結論

- `BUY_SPEC`
  - `entry_col="Ask_Open"`
  - `tp_hit_col="Bid_High"`
  - `tp_time_col="Bid_High_Time"`
  - `sl_hit_col="Ask_Low"`
  - `sl_time_col="Ask_Low_Time"`
  - `forced_exit_col="Bid_Close"`
- `SELL_SPEC`
  - `entry_col="Bid_Open"`
  - `tp_hit_col="Ask_Low"`
  - `tp_time_col="Ask_Low_Time"`
  - `sl_hit_col="Bid_High"`
  - `sl_time_col="Bid_High_Time"`
  - `forced_exit_col="Ask_Close"`

これは旧 research 実装の平均ではなく、整合性と runtime 意味論を優先して定めた canonical である。

### 3.2 保守的 SL exit

- `jst09/lon08` のような「SL level をそのまま exit に近く扱う」系ではなく、spread を残す保守的モデルを採用した
- `jst12` は `SL trigger = Ask/Bid` 自体は整合しているが、`entry_spread` を差し引き・加算する保守的差分を持つ
- `lon12` でも Buy の SL は `sl_price_ask - entry_spread` を用いる保守的モデルであり、`probe5/p001b.py` のような「SL level をそのまま損益化する」方式とは一致しない
- 旧失敗シリーズで確認した通り、`all / 5-25` のズレの主因は Buy SL 価格モデルの差であり、SL の Bid/Ask 問題だけでなく、spread を落とすかどうかが大きく効いていた
- 今回のやり直し理由を踏まえ、canonical はこの保守的モデルへ寄せた
- canonical は以下
  - Buy
    - `SL trigger = Ask`
    - `SL exit = trigger_ask - entry_spread`
  - Sell
    - `SL trigger = Bid`
    - `SL exit = trigger_bid + entry_spread`

### 3.3 same-bar と `*_Time`

- same-bar 競合は `*_Time` による順序判定を使う
- `*_Time` が欠損、同時刻、または順序不明なら不利側優先とする
- canonical では unresolved 件数を sanity に残す
- `probe5` の行列版も不利側優先自体は持つが、sanity 粒度は粗く、そのまま canonical には採らない

### 3.4 特徴量定義

- `probe5` の close-close 系ではなく、open-close 基準を canonical とした
- `pre_open_slope`、左右の形、`pre_range`、`trend_ratio` は `features.py` に集約した
- `same_sign` は runtime 寄りに、片側 0 を same 側に寄せた
- `lon12` は `probe5` とは feature 定義が異なり、`pre_open_slope = Bid_Close(t-5) - Bid_Open(t-55)`、左右も open/close 混在の canonical 寄り実装だった
- このため、`all` は近くても `ge0` 以降の filter 比較では `probe5` 再現と一致しない
- `trend_ratio` は `pre_range_pips <= 0` のとき `NaN` とする
- `lon08/common/feature_filters.py` は `pre_open_slope` と `pre_range` のみで、shape/trend の canonical 参照としては不足している

### 3.4.1 `features.py` に対する補足結論

- `pre_open_slope_pips`
  - `Bid_Close(t-5) - Bid_Open(t-55)`
- `left_ret_pips`
  - `Bid_Close(t-30) - Bid_Open(t-55)`
- `right_ret_pips`
  - `Bid_Close(t-5) - Bid_Open(t-30)`
- `pre_range_pips`
  - `max(Bid_High on t-55..t-5) - min(Bid_Low on t-55..t-5)`
- `net_move_pips`
  - `Bid_Close(t-5) - Bid_Open(t-55)`
- `trend_ratio`
  - `abs(net_move_pips) / pre_range_pips`
  - `pre_range_pips <= 0` なら `NaN`

### 3.5 軽量フィルター定義

- `ge0` / `le0`
- `left_stronger` / `right_stronger`
- `same_sign` / `opposite_sign`
- `vol_ge_med` / `vol_lt_med`
- `trend_ge_0_5` / `range_lt_0_3`

を canonical として固定した。

- `same_sign` の 0 の扱いは旧資産で揺れていた
  - `probe5`
    - `left * right >= 0`
  - 一部 exhaustive 系
    - `sign(left) == sign(right)`
  - runtime
    - 片側 0 でも same 側
- canonical は runtime 寄りとし、片側 0 を same 側へ寄せた

### 3.5.1 `filters.py` に対する補足結論

- runtime 側は `filter_type + operator / mode / threshold` 形式
- research 側は `ge0` や `vol_ge_med` の label 中心
- そのため core では
  - canonical label
  - runtime spec 変換
  - `qualify` 拡張 label
を分けて扱う必要がある
- family は以下で固定した
  - `pre_open_slope`
  - `shape_balance`
  - `pre_range_regime`
  - `trend_ratio`
  - `all`
- scan canonical label は以下
  - `all`
  - `ge0`
  - `le0`
  - `left_stronger`
  - `right_stronger`
  - `same_sign`
  - `opposite_sign`
  - `vol_ge_med`
  - `vol_lt_med`
  - `trend_ge_0_5`
  - `range_lt_0_3`

### 3.6 feature availability の厳密化

- feature window は `t-55 .. t-5` で固定した
- 過去バー不足や minute 欠損がある日は
  - `insufficient_history`
  - `incomplete_feature_window`
  - `missing_required_clock`
  - `nan_required_value`
 で不採用とする
- これにより、朝一やセッション境界付近では entry 時刻によって `trade_count` が自然に変動する

### 3.7 時刻正規化と重複時計

- `Time_JST` 優先、壊れた行のみ index fallback とした
- `Time_JST_Fallback_Used` 相当の監査値を summary に集約した
- `duplicate_clock_removed_count` を loader summary に残すようにした
- `jst09` のような「`Time_JST` 列が存在すると部分破損でも fallback しない」系は採らず、`jst12` / `lon08` / `probe5` 寄りの部分 fallback を採った
- JST 系の naive / London 系の aware が混在していたため、core では tz-aware に統一した
- `drop_duplicates("Clock_*")` 自体は旧資産に広くあるが、core では削除件数を必ず監査値として残す

### 3.7.1 `time_utils.py` / `minute_data.py` に対する補足結論

- `time_utils.py` は
  - broker index を `UTC+3` として扱う
  - `Time_JST` の部分 fallback
  - `Time_London` / `Clock_*` / `Minute_*` / `Date_*` 付与
  - duplicate clock 監査
を担う
- `minute_data.py` は
  - 年次 pickle 読み込み
  - 必須列チェック
  - 価格列 dtype 正規化
  - event time 列 parse
  - TradingDay 分割
  - fallback / duplicate 集計
を担う
- `data_loader.py` 的な責務は「その他よろず」ではなく、core の重要機能として分離した

### 3.7.2 event time 正規化に関する補足

- event time 列は行単位で naive / aware を判定して正規化する
- 混在列を一括変換すると `NaT` が増えやすいため、この点も実装修正済みである

## 4. parity / test 結果

- `tests/test_backtest_parity.py`
  - `backtest_1m.py` と `backtest_fast.py` の基本シナリオ整合確認
  - Buy TP
  - Buy same-bar unresolved
  - Buy event-time TP first
  - Sell conservative SL
- `tests/test_event_times.py`
  - event time の timezone 正規化
  - market clock 派生
  - event time の minute bar 内妥当性
  - `Time_JST` fallback

いずれも通過済み。

## 4.1 `backtest_1m.py` 監査補足

- `probe5` の 1分足行列シミュレーションは、exit side で約定した価格を表していないため canonical 参照元にしない
- `jst10` の Sell 1分足ロジックは non-compliant であり参照しない
- Buy の骨格は `jst09` / `lon08`
- Sell の意味論は runtime 側
- 監査時点では `lon12` を直接再確認できていないため、主要比較は `probe5 / jst09 / jst10 / jst12 / lon08 / runtime` ベースで行った

## 5. 未検知だった論点

今回の scan 結果と旧 `probe5` summary の比較により、以下は core / scan 初期監査では明示検知できていなかった。

### 5.1 summary-level の隣接 slot 完全重複

- 旧 London scan では、隣接 slot 間で gross / in / out / rank / DD まで完全一致する候補が大量に存在していた
- これは `minute_data.py` の `duplicate_clock_removed_count` では検知できない
- 理由:
  - これは 1日データ内の clock 重複ではなく、summary 上の slot 間 exact duplicate だからである
- 今後は scan 側で summary-level duplicate 監査を別項目として持つ必要がある

### 5.2 旧 scan の trade_count 不自然性の明示監査

- core では feature availability の厳密化を実装済みだが、
  - 「旧 scan は entry 時刻ごとの `trade_count` が不自然に一定」
 という比較所見自体は、初回監査文書には残せていなかった
- 今後は旧 scan 比較時に、
  - entry 時刻別の `trade_count` 推移
  - 朝一・境界付近での有効日数変動
を監査メモに含める

## 6. 旧資産の位置付け

- `probe5`
  - scan 構造と高速化思想の参照元
  - ただし exit 価格モデルと feature 定義は canonical に採らない
- `jst09` / `lon08`
  - Buy 系の意味論参照として有用
- `lon10`
  - Buy 系の意味論は `jst09/lon08` と同系統で、Bid/Ask を分けるという意味では概ね整合
- `jst10`
  - Sell 側の非整合検出対象として重要
- `jst12`
  - 完全非準拠ではなく、整合寄りだが保守的差分を含む系統
  - 強いエッジの存在可能性は否定しないが、canonical へはそのまま移植しない
- `lon12`
  - `jst12` と同様に、整合寄りだが保守的 SL exit と feature 差分を含む系統
  - `probe5` 再現用ではなく、保守的 execution 参照として位置付ける

## 6.1 旧 E001 系の3分類

旧 `*_exhaustive1/e001*.py` は一律ではなく、少なくとも以下の3分類で見る必要がある。

- Bid/Ask 完全整合寄り
  - `jst09`
  - `lon08`
  - `lon10`
- 整合だが保守的差分あり
  - `jst12`
  - `lon12`
- 非整合を含む
  - `probe5`
  - `jst10` Sell

この分類に基づき、canonical は「完全整合寄り」だけでなく、「整合だが保守的差分あり」も安全側参照として採り入れた。

## 7. 今後の追加監査項目

- scan summary の slot 間 exact duplicate 検査
- 隣接 slot の重複率レポート
- 旧 `probe5` と現行 scan の `trade_count` 形状比較
- `jst12` 系の強い候補が、scan の粗い family 探しで埋もれる条件の切り分け
