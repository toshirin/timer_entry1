# timer_entry_ops1 Spec

本仕様は、`timer_entry_runtime` の運用監視、約定データ収集、分析、レビュー支援を行う補助系基盤 `timer_entry_ops1` を定義する。
本補助系は執行系 runtime とは責務を分離し、AWS 上の分析DBと、必要時のみローカルで起動する Web アプリおよび CLI により構成する。

## 1. 目的

- Oanda の transaction を日次で収集し、分析可能な形で保存する
- `timer_entry_runtime` の `decision_log` / `execution_log` と Oanda transaction を統合し、strategy / slot / setting 単位で実績を追跡可能にする
- ローカル起動の Web ダッシュボードで運用監視を行えるようにする
- ChatGPT に渡すための分析用データを CLI で出力できるようにする
- 将来の再検証バッチ、再探索バッチの基盤となる分析DBを整備する

## 2. スコープ

初版で扱う対象は以下とする。

- ブローカーは Oanda
- 対象 runtime は `timer_entry_runtime`
- Oanda transaction の日次収集
- runtime 側 `decision_log` / `execution_log` の日次 scan / query に基づく統合
- AWS 上の SQL 系分析DB
- ローカル Web ダッシュボード
- ChatGPT 向けデータ出力 CLI
- AWS 基盤の CDK 管理
- Docker 経由での CDK 実行

本仕様には以下を含む。

- 補助系全体構成
- Oanda データ取得方針
- 分析DB方針
- 突合方針
- ダッシュボード方針
- CLI 出力方針
- CDK / Docker 運用方針

本仕様には以下を含まない。

- 個別戦略ロジックの研究手順
- runtime の執行仕様そのもの
- 再検証バッチ、再探索バッチの詳細仕様
- 自動 enable / disable 制御の実装詳細

## 3. 命名

- 補助系アプリ名は `timer_entry_ops1` とする
- ベースディレクトリは `ops` とする
- ブランチ名は `ops_timer_entry_ops1` とする
- 末尾の数字は世代番号とする
- runtime 側本番執行基盤は `timer_entry_runtime` とし、本補助系とは責務を分離する

## 4. 全体構成

構成要素は以下とする。

- EventBridge
- Lambda `daily_transaction_import`
- Aurora PostgreSQL Serverless v2
- RDS Data API
- 必要に応じて Secrets Manager
- CloudWatch Logs
- ローカル Web アプリ
- ローカル CLI

役割は以下とする。

- EventBridge は日次で transaction 収集 Lambda を起動する
- `daily_transaction_import` は Oanda transaction と runtime 側 DynamoDB log を取得し、分析DBへ保存する
- Aurora PostgreSQL は raw / normalized / summary の分析データを保持する
- Data API は Lambda、Web、CLI からの共通アクセス経路とする
- ローカル Web アプリは必要時のみ起動し、監視ダッシュボードを表示する
- ローカル CLI は ChatGPT 向けデータを整形出力する

## 5. 基本方針

### 5.1 runtime との責務分離

- `timer_entry_runtime` は執行専用とする
- `timer_entry_ops1` は監視、収集、分析、レビュー支援を担当する
- runtime 側 DynamoDB は執行状態共有用であり、分析DBの代替とはしない

### 5.2 分析ソース

分析の主ソースは以下とする。

- runtime 側 `decision_log`
- runtime 側 `execution_log`
- Oanda transaction

補助ソースとして以下を使うことがある。

- runtime 側 `trade_state`

ただし `trade_state` は Lambda 間の情報共有および状態管理が主目的であり、TTL により揮発しうるため、初版では分析の核とはしない。
不発を含めた母数は `decision_log` を正本に近い入力とし、`execution_log` と Oanda transaction は発注、約定、決済情報の補完に使う。
runtime log 同士の紐付けには、可能であれば `decision_log` と `execution_log` に共通の `correlation_id` を持たせる。
ただし DynamoDB 上でグローバルな連番 counter を採番する方式は、初版では採用しない。

### 5.3 Oanda 識別情報の利用

突合には runtime 側が Oanda `ClientExtensions` に埋め込む識別情報を利用する。

- `id`: `setting_id`
- `tag`: `strategy_id`
- `comment`: `slot_id:build_version`

初版では上記を前提に突合を行う。
将来は `comment` を構造化しやすい形式へ寄せることを推奨する。

## 6. 分析DB方針

### 6.1 採用DB

分析DBは `Aurora PostgreSQL Serverless v2` とする。

理由:

- strategy / slot / 日次 / 月次など、複数軸で自由に query したい
- raw transaction と正規化結果、summary を SQL で扱いたい
- ローカルに DB を持たず、AWS 側に集約したい
- Serverless により常設コストを抑えたい

### 6.2 接続方式

接続方式は `RDS Data API` とする。

- Lambda は Data API 経由で DB に書き込む
- ローカル Web アプリは軽量 backend 経由で Data API を利用する
- ローカル CLI も `boto3` 経由で Data API を利用する
- DB への直接 TCP 接続は初版では採用しない

### 6.3 Serverless 前提

- Aurora は auto-pause を前提とする
- ローカル Web は必要時のみ起動する
- 初回アクセス時の resume 待ち時間は許容する
- 常時接続やコネクション保持を前提にしない

### 6.4 UI 確認用データ

UI 確認用に本番データとは別系統のダミーデータを持てる構成とする。

- 初版では同一 Aurora cluster 内に本番用 schema と demo 用 schema を分ける
- demo 用 schema には適当な strategy / slot / setting / pnl / warning / reconciliation 異常を持つ捏造データを投入できるようにする
- ローカル Web は起動時または環境変数で本番用 schema と demo 用 schema を切り替えられるようにする
- demo データは UI 表示確認専用であり、運用判断や ChatGPT 向け review export には使わない

## 7. データ取得方針

### 7.1 取得単位

Oanda からの取得単位は `transaction` とする。

理由:

- order 単位、trade 単位だけでは後から再構成しづらい
- transaction を保存しておけば、後段で多様な view を作れる
- 約定、クローズ、手数料、調整等も追跡しやすい

### 7.2 取得頻度

- 日次で 1 回以上の取り込みを行う
- Oanda transaction は `sinceTransactionID` 相当の増分取得を基本とする
- 必要に応じて再取得可能な設計とする
- 冪等性を持ち、同一 transaction の二重投入を防止する

### 7.3 取得対象

初版では Oanda transaction の情報を可能な限り広く保持する。

- transaction ID
- account ID
- type
- time
- order / trade 関連 ID
- instrument
- units
- price
- realized P/L
- financing
- reason
- ClientExtensions
- 元 JSON 全文

## 8. runtime log / Oanda transaction 統合方針

### 8.1 突合目的

- runtime 側の判定履歴、発注要求、Oanda 実績を結びつける
- `setting_id` / `slot_id` / `strategy_id` 単位で正しい集計を可能にする
- 突合失敗や不整合を監査可能にする

### 8.2 突合キー

主に以下を利用する。

- `correlation_id`
- `decision_id`
- `setting_id`
- `trade_date_local`
- `trade_id`
- `oanda_order_id`
- `oanda_trade_id`
- `oanda_client_id`
- `ClientExtensions.id`
- `ClientExtensions.tag`
- `ClientExtensions.comment`
- transaction time
- instrument
- side / units

### 8.3 突合結果

突合結果は分析用テーブルに保存し、以下を追跡可能にする。

- 正常突合
- Oanda transaction 側のみ存在
- execution_log 側のみ存在
- decision_log 側のみ存在
- 複数候補があり一意に確定できない
- 識別子が欠損している

### 8.4 runtime log 取得方式

runtime 側 DynamoDB log は、日次 Lambda が scan / query により取得する。

- 差分取得は runtime log の `created_at` または日次 partition 相当の属性を使う
- 必要に応じて runtime 側 CDK に `decision_log` / `execution_log` 用の GSI を追加する
- `correlation_id` は `decision_log` と `execution_log` の紐付けに使う
- `trade_id` が存在する entered / exited 系 event では、`trade_id` も補助キーとして使う
- `skipped_concurrency` など execution_log が存在しない不発は `decision_log` 単独で fact 化する
- グローバルなインクリメンタル番号を DynamoDB 上で採番し、その番号だけで差分取得する方式は初版では採用しない

## 9. テーブル設計方針

初版では少なくとも以下の層を持つ。

### 9.1 raw 層

`oanda_transactions_raw`

目的:

- Oanda transaction の完全保存
- 後から正規化ロジックを見直せるようにする

推奨属性:

- `transaction_id`
- `account_id`
- `transaction_time`
- `transaction_type`
- `raw_json`
- `ingested_at`

### 9.2 normalized 層

`oanda_transactions_normalized`

目的:

- query に必要な列を抽出する
- 後段の突合、集計を容易にする

推奨属性:

- `transaction_id`
- `transaction_time`
- `transaction_type`
- `order_id`
- `trade_id`
- `batch_id`
- `instrument`
- `units`
- `price`
- `pl`
- `financing`
- `reason`
- `client_ext_id`
- `client_ext_tag`
- `client_ext_comment`
- `raw_transaction_id_ref`
- `ingested_at`

### 9.3 統合 fact 層

`runtime_oanda_event_fact`

目的:

- runtime 側 `decision_log` を核に、`execution_log` と Oanda transaction を統合する
- 不発を含めた母数、発注、約定、突合状態を 1 つの分析用テーブルで扱えるようにする
- DynamoDB の単純転写と都度統合を避け、日次 Lambda で分析しやすい形に確定する

推奨属性:

- `fact_event_id`
- `correlation_id`
- `decision_id`
- `execution_id`
- `setting_id`
- `strategy_id`
- `slot_id`
- `trade_date_local`
- `market_tz`
- `instrument`
- `side`
- `decision`
- `reason`
- `blocking_trade_id`
- `blocking_setting_id`
- `units`
- `requested_entry_time_local`
- `requested_entry_time_utc`
- `oanda_order_id`
- `oanda_trade_id`
- `oanda_client_id`
- `entry_transaction_id`
- `exit_transaction_id`
- `entry_at`
- `exit_at`
- `entry_price`
- `exit_price`
- `pnl_pips`
- `pnl_jpy`
- `expected_trade_rate`
- `actual_trade_rate`
- `trade_rate_delta`
- `expected_win_rate`
- `actual_win_rate`
- `win_rate_delta`
- `match_status`
- `status`
- `created_at`
- `updated_at`
- `synced_at`

### 9.4 fact 層

`trade_fact`

目的:

- `runtime_oanda_event_fact` から必要に応じて取引単位に再集計する
- 初版では table ではなく view または materialized view としてもよい

推奨属性:

- `fact_trade_id`
- `setting_id`
- `strategy_id`
- `slot_id`
- `trade_date_local`
- `market_tz`
- `instrument`
- `side`
- `entry_at`
- `exit_at`
- `entry_price`
- `exit_price`
- `holding_seconds`
- `pnl_pips`
- `pnl_jpy`
- `win_loss_flag`
- `match_status`
- `source_execution_id`
- `source_entry_transaction_id`
- `source_exit_transaction_id`
- `created_at`
- `updated_at`

### 9.5 summary 層

推奨 summary テーブルまたは materialized view:

- `daily_setting_summary`
- `monthly_setting_summary`
- `slot_summary`
- `kill_switch_events`
- `reconciliation_summary`

初版ダッシュボードは summary 層を主に参照する。

## 10. 監視ダッシュボード方針

### 10.1 配置方針

- ダッシュボードはローカル Web アプリとする
- 必要な時のみ `docker-compose up -d` で起動する
- 閲覧用途に専念し、初版では常設しない
- AWS に常設公開しない

### 10.2 Phase1 必須機能

#### 1. strategy 別パフォーマンス

- `setting_id` 単位
- 累積 pips
- 累積 pnl
- DD
- win rate
- PF
- 取引数

#### 2. 日次 / 月次分解

- 日次 pnl
- 月次 pnl
- 連敗数
- DD 更新日
- 直近 N 日の推移
- `execution_spec_json` にある期待 `trade_rate` / `win_rate` と実績値の比較
- 期待値と実績値の差分

#### 3. slot 別ヒートマップ

- `slot_id` 単位の集計
- side ごとの傾向表示
- 実運用と研究結果のズレを早期検知できる形にする

#### 4. kill-switch 監視

- 発動履歴
- DD 推移
- 判定対象の主要値
- 停止対象 setting 一覧
- 警告系数値
- warning / disabled に近い setting 一覧

#### 5. 突合異常監視

- `execution_log` にあるが Oanda に見つからない
- Oanda transaction はあるが setting に結びつかない
- 複数候補で突合不能
- 欠損識別子の件数

#### 6. conflict 監視

- `decision_log` の排他ロックまたは concurrency 由来の不発件数
- conflict 率
- blocking trade / setting が取れる場合の内訳
- setting / slot / 日次単位の conflict 推移

### 10.3 初版で含めないもの

- ダッシュボードからの `enabled` 自動操作
- 常設運用前提の認証機構
- リアルタイム更新
- 高頻度 polling

### 10.4 技術スタック

- ローカル Web はフロントエンド重視で作る
- 初版候補は `Next.js + React + TypeScript` とする
- browser から AWS へ直接接続せず、Next.js 側の軽量 backend を Data API への土管として使う
- UI 確認時は demo 用 schema のダミーデータを参照できるようにする
- demo 用 schema には勝ち / 負け、DD 悪化、kill-switch 警告、突合異常、Oanda のみ存在、decision のみ存在、conflict 高めの setting、期待 `trade_rate` / `win_rate` との乖離がある setting を含める

## 11. ChatGPT 向け CLI 方針

CLI は ChatGPT に分析させるための review 用エクスポートを生成する。

初版想定機能:

- setting 別サマリ出力
- slot 別サマリ出力
- 期間指定の日次 / 月次集計
- 直近不調 setting の抽出
- 突合異常一覧の出力
- CSV / JSON / Markdown 形式での出力

出力方針:

- 生 transaction 全件ではなく、要約と必要な明細を組み合わせる
- ChatGPT に投入しやすいよう、列名と意味を安定化する
- 再現可能な query 条件をメタ情報として含める

## 12. 日次 Lambda 方針

`daily_transaction_import` の処理順は以下とする。

1. 前回取り込み位置を取得する
2. Oanda から `sinceTransactionID` 相当で transaction を取得する
3. raw テーブルへ保存する
4. normalized テーブルへ反映する
5. runtime 側 DynamoDB から `decision_log` と `execution_log` を日次 scan / query する
6. transaction と `decision_log` / `execution_log` を統合する
7. `runtime_oanda_event_fact` を更新する
8. summary を更新する
9. 突合異常や処理結果をログ出力する

初版では正常系だけでなく、再実行可能性を重視する。

## 13. CDK 方針

### 13.1 CDK の責務

CDK は補助系 AWS 基盤のみを管理する。

- Aurora PostgreSQL Serverless v2
- Data API 利用前提のクラスター構成
- Lambda
- EventBridge
- runtime 側 DynamoDB log 取得に必要な IAM
- runtime 側 DynamoDB log 取得に必要な index 追加または migration
- Secrets Manager
- IAM
- CloudWatch Logs
- 必要に応じて S3
- UI 確認用 demo schema と seed データ投入手段

### 13.2 Docker 実行

runtime と同様に、CDK は Docker 経由で実行できる形を採る。

想定コマンド体系:

- CDK deploy / destroy: `node` 公式イメージ
- 補助系 CLI 実行: `python` 公式イメージまたはローカル実行
- ローカル Web 起動: `docker-compose up -d`

### 13.3 deploy / destroy

- 補助系基盤は runtime と独立に up / down 可能とする
- runtime 側リソースを破壊しない
- DB は原則 retain を前提とし、destroy 時は注意を要する

## 14. ログと監査

推奨ログ種別:

- `TX_IMPORT_START`
- `TX_IMPORT_PAGE`
- `TX_IMPORT_DONE`
- `TX_NORMALIZE`
- `TX_RECONCILE`
- `TX_SUMMARY`
- `TX_WARNING`
- `TX_ERROR`

用途:

- `TX_IMPORT_START`: 取得開始位置、対象期間
- `TX_IMPORT_PAGE`: 取得件数、ページング状況
- `TX_IMPORT_DONE`: 取り込み件数、保存件数
- `TX_NORMALIZE`: 正規化件数
- `TX_RECONCILE`: 突合成功件数、失敗件数
- `TX_SUMMARY`: summary 更新件数
- `TX_WARNING`: 欠損、曖昧一致、再試行
- `TX_ERROR`: API 失敗、DB 更新失敗、予期しない例外

## 15. 将来拡張方針

将来スコープとして以下を想定する。

- 自動スコアリング
- setting の `ACTIVE` / `WARNING` / `DISABLED` 管理
- runtime 側 `setting_config.enabled` への反映支援
- 再検証バッチ
- 再探索バッチ
- 劣化検知バッチ
- ポートフォリオ単位の監視強化
- runtime 複数世代への対応

初版ではこれらの詳細実装は含めないが、分析DB設計は将来拡張に耐えることを重視する。

## 16. 未決事項

初版仕様化までに以下を詰める。

- Oanda transaction の取得位置保存方式と再取得範囲
- runtime 側 `decision_log` / `execution_log` 取得に必要な DynamoDB index
- `trade_fact` の entry / exit 判定ロジック
- summary を table とするか materialized view とするか
- CLI の出力フォーマット優先順位
- kill-switch 関連データを runtime 側からどこまで持ち込むか

## 17. 初期実装順

1. Spec 確定
2. CDK による Aurora / Lambda / EventBridge 基盤作成
3. 日次取得 Lambda と DB schema 整備
4. Oanda transaction raw / normalized 取り込み
5. `decision_log` / `execution_log` と Oanda transaction の統合
6. `runtime_oanda_event_fact` と summary 作成
7. ローカル Web ダッシュボード
8. ChatGPT 向け CLI
9. 将来バッチの詳細化
