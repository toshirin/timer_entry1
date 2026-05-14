# timer_entry runtime Spec

本仕様は、時刻起点の短期売買戦略を AWS Lambda 上で実運用するための汎用実行基盤を定義する。
runtime は `src/timer_entry/` の core 仕様を実売買へ接続する層とし、Bid / Ask、feature、filter、PnL 符号規約を独自に再定義しない。

## 1. 目的

- 東京市場系、ロンドン市場系を同一基盤で運用する
- DST aware / unaware の差異を基盤側で吸収する
- 個別 setting は DynamoDB 上の config 追加・更新・無効化で展開できるようにする
- 初期運用では誤作動時の延焼防止を優先し、起動時間帯を手動で縛り込む
- core と同じ Bid / Ask 規約を runtime の発注、決済、state、log でも維持する

## 2. スコープ

初版で扱う対象は以下とする。

- ブローカーは Oanda
- 通貨ペアは `USD_JPY` 固定
- 売買方向は setting config に従う
- TP / SL は entry fill price を基準に Oanda へ設定する
- forced exit は別 Lambda が担当する
- Oanda API 認証情報は AWS Secrets Manager で管理する

本仕様には以下を含む。

- Lambda 実行方式
- EventBridge 起動方針
- DynamoDB schema
- setting config の表現
- 冪等性と安全装置
- build / deploy / setting apply の運用方針
- core 仕様との接続方針
- Bid / Ask と Oanda trigger side の監査方針

本仕様には以下を含まない。

- 個別戦略ロジックの研究手順
- 検証コードの再現実験仕様
- feature / filter / Bid / Ask 規約の runtime 独自再定義

### 2.1 core 参照方針

runtime の恒久的な仕様参照元は以下とする。

- `src/timer_entry/Spec.md`
- `src/timer_entry/direction.py`
- `src/timer_entry/features.py`
- `src/timer_entry/filters.py`
- `src/timer_entry/schemas.py`

runtime は side 文字列から直接 Bid / Ask を分岐せず、core の DirectionSpec 相当の定義を通して価格系列を決定する。

## 3. 用語定義

- `strategy`: 全体のやり方、売買アプローチの系統
- `slot`: 1時間ごとの時間帯
- `setting`: 時刻、side、TP/SL、filter 条件などを束ねた実行単位
- `requested price`: runtime が発注前 snapshot から記録した参考価格
- `fill price`: Oanda が返す実約定価格
- `trigger side`: TP / SL の発動判定に使う Bid / Ask 側

## 4. 全体構成

構成要素は以下とする。

- EventBridge
- Lambda `entry_handler`
- Lambda `forced_exit_handler`
- DynamoDB `setting_config`
- DynamoDB `trade_state`
- DynamoDB `execution_log`
- AWS Secrets Manager
- CloudWatch Logs

役割は以下とする。

- EventBridge は固定粒度で Lambda を起動する
- `entry_handler` は現在スロットに該当する setting を取得し、entry 判定と発注を行う
- `forced_exit_handler` は現在スロットに該当する未決済ポジションを強制決済する
- `setting_config` は setting 定義と実行条件を管理する
- `trade_state` は日次の実行状態、冪等性、発注結果、価格系列監査情報を管理する
- `execution_log` は発注要求、Oanda 識別子、価格系列、Oanda response の追跡を管理する

## 5. スケジューリング方針

### 5.1 基本方針

- EventBridge は固定粒度で起動する
- 初期粒度は 5 分おきとする
- 実際の執行可否は Lambda 内で判定する

### 5.2 初期の安全重視運用

- 初期は Lambda 料金よりも誤作動時の延焼防止を優先する
- EventBridge ルールは対象時間帯のみ手動で縛り込む
- EventBridge の entry 用時間帯と exit 用時間帯は分離して管理する
- 東京系は必要な JST 時間帯に対応する UTC 範囲のみ許可する
- ロンドン系は夏時間と冬時間の両方を考慮した UTC 範囲を許可する
- ロンドン系の許可範囲は entry 時刻だけでなく forced exit まで含む十分な幅を持たせる

### 5.3 DST 対応

- 東京系 setting は `market_tz=Asia/Tokyo` を使用する
- ロンドン系 setting は `market_tz=Europe/London` を使用する
- Lambda 内では setting ごとの local clock を timezone-aware に UTC へ変換して判定する
- UTC 固定時刻で直接 setting を判定しない

### 5.4 除外 window

`execution_spec_json.exclude_windows` に除外 window が指定された setting は、entry handler の local clock 一致後、Oanda API を呼ぶ前に除外判定を行う。

- 初期対応 window は `us_uk_dst_mismatch`
- `us_uk_dst_mismatch` は London 系 setting の US / UK DST mismatch 期間を除外する
- 除外日は `skipped_exclude_window` として `decision_log` に記録する
- forced exit handler は安全側に倒すため、除外 window では止めない
- 未知の window 名や不正な `exclude_windows` 型は config error とみなし、`SETTING_ERROR` / handler result `status=error` として目立たせる。現行実装では `skipped_config_error` の decision_log にはしない

## 6. Setting Config 方針

### 6.1 命名

- 本番 setting の一意キーを `setting_id` とする
- `setting_id` は運用用の人間可読キーとする
- 研究上のラベルは `research_label` として別属性で保持する

例:

- `jst09_pre_open_slope_ge4_v1`
- `lon10_left_stronger_v1`

### 6.2 実行判定

setting は以下の条件をすべて満たした場合のみ実行対象とする。

- `enabled=true`
- 現在スロットに対応する `trigger_bucket` に一致する
- 現在時刻が setting の local time 条件に一致する
- 市場開場チェックを通過する
- 口座上の open trade 数が `max_concurrent_positions` 未満である
- 同一 `setting_id + trade_date_local` の実行済み state が存在しない

### 6.2.1 setting 間の競合

初版では、setting 間の競合制御は `max_concurrent_positions` と account / instrument 上の open trade 数を使う。

- 先に broker 上で open trade を作った setting が優先される
- 後続 setting は open trade 数により `skipped_concurrency` として不発にする
- ただし、open trade の `setting_id` を broker `clientExtensions.id` から復元でき、対応する setting に `label=watch` が付いている場合、その open trade は concurrency count から除外する
- `setting_id` を復元できない open trade、または setting_config を参照できない open trade は安全側で concurrency count に含める
- 同一 setting / 同一 trade date の二重発注は `trade_state` の conditional write で防ぐ

ただし、複数 setting が同時起動し、どちらも broker open trade 作成前に concurrency check を通過する race は残りうる。将来、同一 bucket 内の候補を厳密に排他したい場合は、account / instrument / strategy group 単位の lock item を DynamoDB に持つ。

排他や concurrency により不発になった setting は、将来の組み合わせ最適化に使うため、永続イベントログへ reason と blocking trade / setting を残す。

### 6.3 サイズ計算

発注数量は以下の優先順位で決定する。

- `fixed_units` が設定されていればそれを使用する
- `fixed_units` が未設定で、`margin_ratio_target` と `size_scale_pct` が設定されていれば、`margin_ratio_target * (100 / size_scale_pct)` を実効維持率として units を算出する
- `fixed_units` が未設定で、`margin_ratio_target` のみ設定されていれば、それをそのまま使って units を算出する
- `size_scale_pct` 単独は無効とする
- 両方未設定の場合は設定不備として発注しない
- 両方設定されている場合は `fixed_units` を優先する

`trade_state` には以下を記録する。

- `requested_units`
- `sizing_basis`
- `estimated_margin_ratio_after_entry`
- sizing に使った価格と価格系列

## 7. DynamoDB Schema

### 7.1 `setting_config`

主キー:

- PK: `setting_id`

GSI:

- `gsi_entry_trigger`
- GSI PK: `trigger_bucket_entry`
- GSI SK: `setting_id`
- `gsi_exit_trigger`
- GSI PK: `trigger_bucket_exit`
- GSI SK: `setting_id`

必須トップレベル属性:

- `setting_id`
- `enabled`
- `strategy_id`
- `slot_id`
- `market_session`
- `market_tz`
- `instrument`
- `side`
- `entry_clock_local`
- `forced_exit_clock_local`
- `trigger_bucket_entry`
- `trigger_bucket_exit`
- `fixed_units`
- `margin_ratio_target`
- `size_scale_pct`
- `tp_pips`
- `sl_pips`
- `research_label`
- `labels`
- `market_open_check_seconds`
- `max_concurrent_positions`
- `kill_switch_dd_pct`
- `kill_switch_reference_balance_jpy`
- `min_maintenance_margin_pct`
- `created_at`
- `updated_at`

拡張属性:

- `filter_spec_json`
- `execution_spec_json`
- `notes`

補足:

- 検索・判定に使う項目はトップレベル属性に置く
- 将来増える setting 詳細は JSON 文字列または Map 属性で持つ
- `instrument` は初版では `USD_JPY` 固定だが、属性としては保持する
- `labels` は ops dashboard のフィルタ用に使う文字列配列とし、runtime の売買判定には使わない
- 初期運用では `max_concurrent_positions=1` を基本値とし、口座上の open trade が 1 本でも残っていれば新規 entry を見送る

### 7.2 `trigger_bucket`

bucket は timezone を含める。

例:

- `ENTRY#Asia/Tokyo#0925`
- `EXIT#Asia/Tokyo#1000`
- `ENTRY#Europe/London#1000`
- `EXIT#Europe/London#1030`

entry 処理時は `trigger_bucket_entry`、forced exit 処理時は `trigger_bucket_exit` を使って query する。

### 7.3 `trade_state`

主キー:

- PK: `trade_id`

推奨属性:

- `trade_id`
- `idempotency_key`
- `setting_id`
- `strategy_id`
- `slot_id`
- `trade_date_local`
- `market_tz`
- `instrument`
- `side`
- `status`
- `scheduled_entry_at_utc`
- `scheduled_exit_at_utc`
- `requested_units`
- `sizing_basis`
- `estimated_margin_ratio_after_entry`
- `pnl_pips`
- `pnl_jpy`
- `entry_order_id`
- `entry_trade_id`
- `entry_filled_at`
- `requested_entry_price`
- `requested_entry_price_side`
- `entry_price`
- `entry_price_side`
- `tp_trigger_price`
- `tp_trigger_side`
- `sl_trigger_price`
- `sl_trigger_side`
- `exit_order_id`
- `exit_filled_at`
- `exit_price`
- `exit_price_side`
- `exit_reason`
- `error_code`
- `error_message`
- `created_at`
- `updated_at`
- `ttl`

冪等性キー:

- `idempotency_key = setting_id#trade_date_local`

status 例:

- `planned`
- `entered`
- `exited`
- `skipped_market_closed`
- `skipped_duplicate`
- `skipped_config_error`
- `skipped_kill_switch`
- `entry_failed`
- `exit_failed`

### 7.4 `execution_log`

主キー:

- PK: `execution_id`

推奨属性:

- `execution_id`
- `setting_id`
- `strategy_id`
- `slot_id`
- `trade_date_local`
- `market_tz`
- `instrument`
- `side`
- `units`
- `requested_entry_time_local`
- `requested_entry_time_utc`
- `oanda_order_id`
- `oanda_trade_id`
- `oanda_client_id`
- `entry_price_side`
- `tp_trigger_side`
- `sl_trigger_side`
- `exit_price_side`
- `status`
- `created_at`
- `updated_at`

status 例:

- `requested`
- `order_created`
- `order_failed`
- `tp_sl_requested`
- `tp_sl_created`
- `tp_sl_failed`
- `close_requested`
- `close_created`
- `close_failed`

### 7.5 `decision_log`

不発を含む runtime の判定履歴は `decision_log` として永続化する。

`execution_log` は broker 発注 request / response の追跡を主目的とする。発注前に不発になったものまで `execution_log` に混ぜると意味が曖昧になるため、初版では判定ログを分ける。

主キー:

- PK: `decision_id`

推奨 `decision_id`:

- `setting_id#trade_date_local#handler_name#invoked_at_utc`

推奨属性:

- `decision_id`
- `setting_id`
- `strategy_id`
- `slot_id`
- `trade_date_local`
- `market_tz`
- `instrument`
- `side`
- `handler_name`
- `trigger_bucket`
- `scheduled_local`
- `actual_invoked_at_utc`
- `decision`
- `reason`
- `blocking_trade_id`
- `open_trade_count`
- `open_trade_setting_ids`
- `blocking_open_trade_count`
- `blocking_trade_setting_id`
- `ignored_watch_open_trade_count`
- `filter_results`
- `created_at`
- `ttl`

`decision` 例:

- `entered`
- `exited`
- `skipped_disabled`
- `skipped_clock_mismatch`
- `skipped_market_closed`
- `skipped_concurrency`
- `skipped_duplicate`
- `skipped_filter`
- `skipped_kill_switch`
- `skipped_exclude_window`
- `skipped_config_error`
- `entry_failed`
- `exit_failed`

不発理由は少なくとも以下を区別する。

- 排他 / concurrency 原因
- 同一 setting の duplicate 原因
- filter 条件不達
- market closed
- clock mismatch
- kill switch
- exclude window
- config error

## 8. 時刻と市場セッション

- setting は `market_session` を持つ
- 初版では `tokyo` と `london` を想定する
- 東京系の基準 timezone は `Asia/Tokyo`
- ロンドン系の基準 timezone は `Europe/London`

運用上の時間帯定義:

- 東京市場帯はローカルで 07:00-16:00 を基準とする
- ロンドン系はそれ以外の時間帯に置かれることを想定する

ただし最終的な実行判定は市場帯の大まかな区分だけで決めず、必ず以下で判定する。

- `market_tz`
- `entry_clock_local`
- `forced_exit_clock_local`
- 現在時刻を local timezone に変換した結果

## 9. 市場開場チェック

- Lambda 起動時に Oanda Pricing API で最新 tick を取得する
- 最新 tick 時刻と Lambda 現在時刻との差が `market_open_check_seconds` 以内なら市場開場とみなす
- 判定は timezone-aware な UTC datetime で行う
- 判定失敗時は異常終了ではなく `skipped_market_closed` を記録して正常終了する
- entry / forced exit の両 Lambda で実施する

## 10. Entry 処理

`entry_handler` の処理順は以下とする。

1. 現在スロットに対応する `trigger_bucket` を計算する
2. `setting_config` から該当 setting のみ query する
3. `enabled` と local time 条件を確認する
4. 市場開場チェックを行う
5. `max_concurrent_positions` に基づき、口座上の open trade 数を確認する
6. setting の filter 条件を評価する
7. `idempotency_key` により同日重複実行を防止する
8. units を計算する
9. kill switch 条件を確認する
10. Oanda に成行発注する
11. market order が fill したら、TP / SL 設定前に `trade_state` を `entered` へ更新する
12. entry fill price を基準に TP / SL を設定する
13. TP / SL 設定に失敗しても、open trade を forced exit 対象に残すため `trade_state.status=entered` は維持する
14. `execution_log` を requested / order_created / tp_sl_requested / tp_sl_created / order_failed / tp_sl_failed で更新する
15. 発注有無にかかわらず `decision_log` を記録する

### 10.1 Bid / Ask と TP / SL

runtime は core の side 規約を発注 payload と state に反映する。

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

TP / SL level は broker の entry fill price から計算する。発注前 snapshot は `requested_entry_price` として監査用に記録し、TP / SL の canonical 基準価格にはしない。

Oanda API へ trigger side を指定できる注文では、runtime は `triggerCondition` を明示する。API の default trigger には依存しない。

## 11. Forced Exit 処理

`forced_exit_handler` の処理順は以下とする。

1. 現在スロットに対応する exit bucket を計算する
2. 対象 setting に対応する未決済 `trade_state` を取得する
3. 市場開場チェックを行う
4. Oanda の対象ポジションまたは trade をクローズする
5. 成功時は `trade_state` を `exited` に更新する
6. 失敗時は再取得のうえ再試行する

forced exit は `setting.enabled=false` でも未決済 `trade_state` があれば実行する。これは setting を down した後でも、既存 open trade を安全に閉じるためである。

保険リトライ:

- 初版の retry 回数は 3 回とする
- 各 retry 前に open trade / position を再取得する
- 規定回数失敗時は `exit_failed` として記録し、CloudWatch Logs に error を残す

forced exit は core の forced exit side と同じ向きで broker 約定される想定とする。

- Buy close: Bid
- Sell close: Ask

forced exit 実行時点ですでに broker 側で close 済みの場合は、close price、realized P/L、close reason を回収して `broker_closed` として記録する。

## 12. Filter 拡張方針

setting 固有の軽量 filter は config 駆動で表現できるようにする。

想定 filter 例:

- `pre_open_slope`
- `shape_balance`
- `pre_range_regime`
- `trend_ratio`

`filter_spec_json` には複数条件を保持できる形を採る。

想定要素:

- `filter_type`
- `lookback_start_min`
- `lookback_end_min`
- `operator`
- `threshold`
- `mode`
- `aux_param`

初版では、query に不要な filter 詳細は JSON 側に寄せる。

filter は entry より前に確定済みの M1 Bid candle だけを使い、core の feature / filter 定義と一致させる。

## 13. Secrets Manager

- Oanda API 認証情報は AWS Secrets Manager で手動登録する
- CDK は secret の値を作成しない
- CDK は既存 secret 名を参照し、Lambda に読み取り権限のみ付与する
- secret value は CloudWatch Logs や DynamoDB に出力しない

## 14. CDK と運用粒度

### 14.1 CDK の責務

CDK は基盤のみを管理する。

- DynamoDB
- Lambda
- EventBridge
- IAM
- CloudWatch Logs
- Secrets Manager 参照権限

### 14.2 Setting の up / down

setting の追加・更新・無効化・削除は CDK ではなく config 運用で行う。

- up: `setting_config` 登録または `enabled=true`
- down: `enabled=false`
- delete: `setting_config` 削除

### 14.3 初期導入順

1. Secrets Manager に Oanda 認証情報を手動登録する
2. CDK で基盤を deploy する
3. setting config を投入する
4. setting を有効化する

## 15. Docker 実行方針

実験シリーズと同様に、build / deploy / apply は Docker 経由で実行できる形を目指す。

想定コマンド体系:

- Lambda build: AWS Lambda Python 公式イメージで `build.sh`
- CDK deploy / destroy: `node` 公式イメージで `npx cdk ...`
- setting apply / disable: `python` 公式イメージで補助スクリプト実行

例:

```bash
docker run --rm \
  -v "$PWD:/work" \
  -w /work \
  public.ecr.aws/lambda/python:3.12 \
  bash runtime/build.sh
```

```bash
docker run --rm \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work/runtime/cdk \
  node:22-bullseye \
  bash -lc "npm ci && npx cdk deploy TimerEntryRuntimeStack"
```

本番 Lambda では、初版は可能な限り標準ライブラリ中心で実装し、`pandas` / `numpy` の導入は必要性が明確になった時点で再検討する。

## 16. 監査ログ方針

CloudWatch 上で setting ごとの判定経緯を追跡できるように、検索しやすいキーワード付きログを出力する。

推奨ログ種別:

- `SETTING_SCAN`
- `SETTING_CHECK`
- `SETTING_FILTER`
- `SETTING_SKIP`
- `SETTING_ENTER`
- `SETTING_TP_SL`
- `SETTING_EXIT`
- `SETTING_ERROR`

用途:

- `SETTING_SCAN`: `trigger_bucket` 計算結果、query 条件、取得件数、対象 setting 一覧
- `SETTING_CHECK`: `enabled`、local time、市場開場、concurrency、idempotency、units 計算などの基礎判定
- `SETTING_FILTER`: filter 条件の計算詳細と pass / fail
- `SETTING_SKIP`: 実行しなかった理由
- `SETTING_ENTER`: 発注内容と発注結果
- `SETTING_TP_SL`: TP / SL の価格、trigger side、Oanda 識別子
- `SETTING_EXIT`: forced exit の実行内容と結果
- `SETTING_ERROR`: 例外や API 失敗

`SETTING_CHECK` には少なくとも以下を含める。

- `setting_id`
- `strategy_id`
- `slot_id`
- `market_tz`
- `scheduled_local`
- `actual_invoked_at_utc`
- 判定に使った主要値
- 各チェック項目の pass / fail
- units 計算結果
- 最終判定結果

`SETTING_FILTER` には少なくとも以下を含める。

- `setting_id`
- filter ごとの入力値
- filter ごとの計算結果
- filter ごとの pass / fail

価格系列を伴うログには少なくとも以下を含める。

- `entry_price_side`
- `tp_trigger_side`
- `sl_trigger_side`
- `exit_price_side`
- `requested_entry_price`
- `entry_fill_price`
- `tp_trigger_price`
- `sl_trigger_price`
- `exit_fill_price`

不発を含む判定履歴は CloudWatch Logs だけでなく `decision_log` にも保存する。特に concurrency / 排他ロック起因の不発は、後続の portfolio / setting 組み合わせ最適化で使うため永続化する。

## 16.1 qualify から runtime config への変換

`qualify/params/{slot_id}/{version_id}/*.json` は研究・検証側の入力であり、そのまま `setting_config` へ投入しない。

責務分担は以下とする。

- qualify は最終候補の根拠、baseline、sweep 結果、stability gate、tick replay 結果を出力する
- core は filter label から runtime filter spec への変換など、共通変換ロジックを提供する
- runtime は deploy 可能な `setting_config` JSON への変換、default 値補完、運用 risk 値補完、schema validation を担当する

runtime 側には `qualify/results/{slot_id}/{result_id}.json` の最終昇格結果を読み、`setting_config` JSON を生成する promotion tool を置く。

promotion tool は少なくとも以下を検証する。

- `pass_stability_gate=true`
- tick replay の sanity が合格している
- side ごとの Bid / Ask 規約が core と一致する
- `entry_clock_local` と `forced_exit_clock_local` が有効である
- `tp_pips` / `sl_pips` が正数である
- `filter_labels` が runtime filter spec に変換可能である
- `market_tz` / `trigger_bucket_entry` / `trigger_bucket_exit` が生成可能である
- risk / kill switch / concurrency の運用値が明示されている

## 17. Kill Switch

初版では setting 単位の kill switch を持つ。

entry 前に以下を確認する。

- `kill_switch_dd_pct` を下回る setting は新規 entry を停止する
- `min_maintenance_margin_pct` を下回る見込みの setting は新規 entry を停止する

drawdown 判定は、当該 setting の確定済み `trade_state` を用いて行う。

- `pnl_jpy` の累積から equity curve を再構成する
- 初期 equity は `kill_switch_reference_balance_jpy` を基準にする
- peak からの drawdown が `kill_switch_dd_pct` 以下なら停止する

停止時は以下を行う。

- 発注しない
- `SETTING_SKIP` に kill switch 理由を残す
- 必要に応じて `trade_state` を `skipped_kill_switch` として記録する

## 18. 安全装置

- `idempotency_key` による同日二重発注防止
- `max_concurrent_positions` による同時動作 setting 数の制御
- 市場開場チェック
- setting 単位 kill switch
- EventBridge の時間帯手動制限
- forced exit retry
- config 不備時の skip
- 全処理の CloudWatch Logs 出力
- 価格系列を state / log に保存する Bid / Ask 監査

## 19. Oanda 識別子

entry 発注時は Oanda の ClientExtensions を設定する。

- `id`: `setting_id`
- `tag`: `strategy_id`
- `comment`: `slot_id + build_version`

目的:

- Oanda 側の注文履歴から setting を復元できるようにする
- `execution_log` と外部分析基盤の突合精度を上げる

注意:

- MT4 系アカウントでは ClientExtensions を使わない
- 文字列長制限を考慮する

## 20. Dry Run

runtime は broker 発注なしで以下を確認できる dry-run を持つ。

- setting query
- local clock match
- market open check の代替入力
- filter 評価
- sizing
- order payload
- TP / SL trigger side
- state 更新予定値

dry-run は本番 secret を必要としない形を優先する。

## 21. Test

初版の必須 test:

- Buy entry が Ask、Sell entry が Bid であること
- Buy TP が Bid trigger、Sell TP が Ask trigger であること
- Buy SL が Ask trigger、Sell SL が Bid trigger であること
- Buy forced exit が Bid、Sell forced exit が Ask として state に残ること
- TP / SL が fill price 基準で計算されること
- state / log に使用価格系列名が保存されること
- duplicate state が二重発注を防ぐこと
- market closed が skip になること
- filter rejected が skip になること
- forced exit retry が close 済み trade を正常回収すること

## 22. 初版の既定値

- instrument: `USD_JPY`
- EventBridge 粒度: 5 分
- sizing 優先順位: `fixed_units` 優先、未設定時のみ `margin_ratio_target` と `size_scale_pct` を考慮
- forced exit retry: 3 回
- kill switch: setting 単位で有効
- 東京 timezone: `Asia/Tokyo`
- ロンドン timezone: `Europe/London`
- TP / SL level: entry fill price 基準
- TP / SL trigger side: core DirectionSpec に従い明示

## 23. 今後の拡張

- 通貨ペアの config 化
- setting ごとの複数 entry slot 対応
- 多市場の追加
- filter evaluator の拡張
- setting apply / disable 用の管理 CLI 整備
- concurrency の account / instrument / strategy group 単位切り替え
