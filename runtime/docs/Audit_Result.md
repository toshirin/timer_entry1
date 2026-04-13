# timer_entry runtime Audit Result

本ドキュメントは runtime 移植前の監査結果を集約する。

一時参照 runtime は移植完了後に削除される前提のため、本ドキュメントでは参照元パスを恒久的な仕様参照先として扱わない。runtime の恒久的な基準は `src/timer_entry/` の core とする。

## 1. 監査目的

- runtime を core 利用へ作り替える前に Bid / Ask のズレを洗い出す
- TP / SL / forced exit の broker 実行意味論を core と比較する
- 移植時にそのまま持ち込んではいけない実装上の癖を明確にする
- state / log に不足している監査項目を列挙する

## 2. Core の基準

core の side 規約:

- Buy
  - entry: Ask
  - TP trigger: Bid
  - SL trigger: Ask
  - forced exit: Bid
- Sell
  - entry: Bid
  - TP trigger: Ask
  - SL trigger: Bid
  - forced exit: Ask

core の SL exit model:

- Buy: `SL trigger = Ask`, `SL exit = trigger_ask - entry_spread`
- Sell: `SL trigger = Bid`, `SL exit = trigger_bid + entry_spread`

runtime は broker 約定を扱うため、1分足 backtest の保守的 SL exit price をそのまま発注価格として使うわけではない。ただし trigger side は core と一致させる必要がある。

## 3. 監査結果サマリ

現行 runtime の entry side は core と概ね整合している。

- Buy entry は Ask snapshot を参照している
- Sell entry は Bid snapshot を参照している
- PnL pips の符号は Buy / Sell とも core と同じ向きである

一方で、移植前に修正すべき点がある。

- TP / SL の trigger side が注文 payload 上で明示されていない
- TP / SL level が entry fill price ではなく発注前 snapshot 基準で計算される
- state / log に `entry_price_side`、`tp_trigger_side`、`sl_trigger_side`、`exit_price_side` が保存されていない
- 旧 jst10 Sell 系の研究根拠は Bid / Ask 非準拠として隔離が必要である
- margin 計算が Buy / Sell にかかわらず Ask 基準であり、実害は限定的だが監査上は明示が必要である

## 4. Bid / Ask 監査

### 4.1 Entry

entry の reference price は以下の扱いだった。

- Buy: Ask
- Sell: Bid

これは core の entry side と一致している。

ただし、実際の約定価格は broker fill price であり、snapshot と一致する保証はない。runtime 移植後は `requested_entry_price` と `entry_fill_price` を分けて保存する。

### 4.2 TP

TP level は reference price から pips を加減して計算されていた。

- Buy: `reference_price + tp_pips`
- Sell: `reference_price - tp_pips`

方向は core と一致するが、trigger side が注文 payload で明示されていなかった。runtime 移植後は以下を明示する。

- Buy TP: Bid trigger
- Sell TP: Ask trigger

### 4.3 SL

SL level は reference price から pips を加減して計算されていた。

- Buy: `reference_price - sl_pips`
- Sell: `reference_price + sl_pips`

方向は core と一致するが、trigger side が注文 payload で明示されていなかった。runtime 移植後は以下を明示する。

- Buy SL: Ask trigger
- Sell SL: Bid trigger

この点が今回の最重要 Bid / Ask リスクである。Oanda API の default trigger に依存すると、core の `SL trigger side` と runtime の実売買がズレる可能性がある。

### 4.4 Forced Exit

forced exit は broker trade close を使っているため、実約定 side は以下の想定になる。

- Buy close: Bid
- Sell close: Ask

これは core の forced exit side と一致する。

ただし state には `exit_price_side` が保存されていないため、移植後は close result とともに記録する。

## 5. Fill Price と Snapshot Price

現行 runtime は market order 作成前の price snapshot を TP / SL level の基準にしていた。

core の backtest は entry price を基準に TP / SL level を計算する。実運用では market fill に slippage が出るため、snapshot 基準の TP / SL は core と距離がズレる。

移植後の canonical 方針:

- entry fill price を取得する
- fill price を基準に TP / SL level を計算する
- TP / SL trigger side を core に合わせて明示する
- snapshot price は `requested_entry_price` として監査用に残す

## 6. State / Log 不足

追加すべき state 項目:

- `requested_entry_price`
- `requested_entry_price_side`
- `entry_price`
- `entry_price_side`
- `tp_trigger_price`
- `tp_trigger_side`
- `sl_trigger_price`
- `sl_trigger_side`
- `exit_price`
- `exit_price_side`
- `price_series_source`

追加すべき log 項目:

- `direction_spec`
- `entry_price_side`
- `tp_trigger_side`
- `sl_trigger_side`
- `forced_exit_price_side`
- `requested_entry_price`
- `entry_fill_price`
- `tp_trigger_price`
- `sl_trigger_price`
- `exit_fill_price`

## 7. Config 監査

現行の Buy 系 setting は runtime の entry side と整合している。

- jst09 Buy
- jst12 Buy
- lon08 Buy

Sell 系 setting は実売買 runtime では Bid entry になっているが、旧研究系列の jst10 short は Bid / Ask 非準拠として扱う。

jst10 Sell は移植後に以下のどちらかを行う。

- 無効化したまま再 qualify する
- core の Sell 規約で再計算した結果だけを採用する

旧研究系列の結果を runtime config の根拠としてそのまま使わない。

## 8. Filter 監査

現行 runtime の filter は M1 Bid candle を使っている。

- `pre_open_slope`: Bid open / close
- `shape_balance`: Bid open / close
- `pre_range_regime`: Bid high / low
- `trend_ratio`: Bid open / close と Bid high / low

これは core の feature 方向と概ね一致している。

移植後は runtime 独自 evaluator を増やすより、core の feature / filter 定義を参照する構成へ寄せる。

## 9. 移植時の修正リスト

- core の `DirectionSpec` を runtime の注文生成に使う
- side 文字列から直接 Bid / Ask を選ばない
- Oanda dependent order の trigger side を明示する
- TP / SL を fill price 基準へ変更する
- state / log に価格系列名を保存する
- jst10 Sell を再 qualify まで採用しない
- Buy / Sell の unit test を追加する
- dry-run payload で trigger side と price level を確認する

## 10. 初期合格条件

runtime 移植初版は以下を満たすまで完了扱いにしない。

- Buy entry が Ask、Sell entry が Bid であることを test する
- Buy TP が Bid trigger、Sell TP が Ask trigger であることを test する
- Buy SL が Ask trigger、Sell SL が Bid trigger であることを test する
- Buy forced exit が Bid、Sell forced exit が Ask として state に残ることを test する
- TP / SL が fill price 基準で計算されることを test する
- state / log に使用価格系列名が保存されることを test する

