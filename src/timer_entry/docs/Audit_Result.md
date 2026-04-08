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

### 3.2 保守的 SL exit

- `jst09/lon08` のような「SL level をそのまま exit に近く扱う」系ではなく、spread を残す保守的モデルを採用した
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

### 3.4 特徴量定義

- `probe5` の close-close 系ではなく、open-close 基準を canonical とした
- `pre_open_slope`、左右の形、`pre_range`、`trend_ratio` は `features.py` に集約した
- `same_sign` は runtime 寄りに、片側 0 を same 側に寄せた

### 3.5 軽量フィルター定義

- `ge0` / `le0`
- `left_stronger` / `right_stronger`
- `same_sign` / `opposite_sign`
- `vol_ge_med` / `vol_lt_med`
- `trend_ge_0_5` / `range_lt_0_3`

を canonical として固定した。

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
- `jst10`
  - Sell 側の非整合検出対象として重要
- `jst12`
  - 完全非準拠ではなく、整合寄りだが保守的差分を含む系統
  - 強いエッジの存在可能性は否定しないが、canonical へはそのまま移植しない

## 7. 今後の追加監査項目

- scan summary の slot 間 exact duplicate 検査
- 隣接 slot の重複率レポート
- 旧 `probe5` と現行 scan の `trade_count` 形状比較
- `jst12` 系の強い候補が、scan の粗い family 探しで埋もれる条件の切り分け
