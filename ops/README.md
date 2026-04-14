# timer_entry ops

`ops/` は `timer_entry_runtime` の外側に置く運用補助基盤です。
詳細仕様は `ops/Spec.md` を参照してください。

## 初版の構成

- Aurora PostgreSQL Serverless v2
- RDS Data API
- 日次 Lambda `daily_transaction_import`
- EventBridge
- demo schema 用 seed SQL
- ローカル Web 用の土台

## ビルド

ローカル実行:

```bash
bash ops/build.sh
```

Docker 実行:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -w /work \
  python:3.12-slim \
  ops/build.sh
```

生成物:

- `ops/dist/daily_transaction_import.zip`

## CDK

```bash
cd ops/cdk
npm install
npx cdk synth
```

Docker 実行例:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work/ops/cdk \
  node:22-bullseye \
  -lc "npm install && npx cdk synth"
```

deploy:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work/ops/cdk \
  -e AWS_PROFILE \
  -e AWS_REGION=ap-northeast-1 \
  -e OANDA_SECRET_NAME=oanda_rest_api_key \
  -e DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
  -e EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
  -e OPS_IMPORT_SCHEDULE_EXPRESSION='cron(15 22 * * ? *)' \
  -e OPS_AURORA_POSTGRES_VERSION=16.4 \
  node:22-bullseye \
  -lc "npm install && npx cdk deploy TimerEntryOpsStack --require-approval never"
```

`OPS_IMPORT_SCHEDULE_EXPRESSION` の初期値は `cron(15 22 * * ? *)` です。
EventBridge cron は UTC なので、これは JST 07:15 固定です。
NY close 後の日次区切りを意識しつつ、cron の DST 非対応を避けるため、初版では JST 07:15 固定にします。

destroy は DB retain 前提ですが、実行前に CloudFormation の変更内容を確認してください。

Aurora PostgreSQL の engine version はリージョンによって利用可否が異なります。
`OPS_AURORA_POSTGRES_VERSION` の初期値は `16.4` です。
`16.0` から `16.3` は RDS 側で deprecated になっているため使いません。
`Cannot find version ... for aurora-postgresql` で失敗した場合は、deploy 先リージョンで利用可能な version に変更します。

## DB schema

CDK deploy 後に Data API の接続先を環境変数へ入れてから実行します。

```bash
PYTHONPATH=ops/src \
OPS_DB_CLUSTER_ARN=... \
OPS_DB_SECRET_ARN=... \
OPS_DB_NAME=timer_entry_ops \
OANDA_SECRET_NAME=oanda_rest_api_key \
DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
python ops/scripts/apply_sql.py ops/sql/schema.sql
```

Docker 実行:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work \
  -e AWS_PROFILE \
  -e AWS_REGION=ap-northeast-1 \
  -e OPS_DB_CLUSTER_ARN='...' \
  -e OPS_DB_SECRET_ARN='...' \
  -e OPS_DB_NAME=timer_entry_ops \
  -e OANDA_SECRET_NAME=oanda_rest_api_key \
  -e DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
  -e EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
  python:3.12-slim \
  -lc "pip install boto3 && PYTHONPATH=ops/src python ops/scripts/apply_sql.py ops/sql/schema.sql"
```

demo データ:

```bash
PYTHONPATH=ops/src \
OPS_DB_CLUSTER_ARN=... \
OPS_DB_SECRET_ARN=... \
OPS_DB_NAME=timer_entry_ops \
OANDA_SECRET_NAME=oanda_rest_api_key \
DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
python ops/scripts/apply_sql.py ops/sql/demo_seed.sql
```

Docker 実行:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work \
  -e AWS_PROFILE \
  -e AWS_REGION=ap-northeast-1 \
  -e OPS_DB_CLUSTER_ARN='...' \
  -e OPS_DB_SECRET_ARN='...' \
  -e OPS_DB_NAME=timer_entry_ops \
  -e OANDA_SECRET_NAME=oanda_rest_api_key \
  -e DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
  -e EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
  python:3.12-slim \
  -lc "pip install boto3 && PYTHONPATH=ops/src python ops/scripts/apply_sql.py ops/sql/demo_seed.sql"
```

## 初回 cursor

`daily_transaction_import` は、`ops_main.import_cursor` に `oanda_last_transaction_id` がない場合、Oanda の最新 `lastTransactionID` を取得して cursor だけを初期化します。
その初回実行では過去 transaction は取り込まず、次回以降に `sinceid` で増分取得します。
cursor が数字でない場合、または Oanda が `Invalid value specified for 'id'` を返した場合も、最新 `lastTransactionID` へリセットします。

現在の cursor 確認:

```sql
select * from ops_main.import_cursor;
```

手動で cursor を削除し、次回 Lambda 実行で再初期化する場合:

```sql
delete from ops_main.import_cursor
where cursor_name = 'oanda_last_transaction_id';
```

手動で cursor を指定する場合:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work \
  -e AWS_PROFILE \
  -e AWS_REGION=ap-northeast-1 \
  -e OPS_DB_CLUSTER_ARN='...' \
  -e OPS_DB_SECRET_ARN='...' \
  -e OPS_DB_NAME=timer_entry_ops \
  -e OANDA_SECRET_NAME=oanda_rest_api_key \
  -e DECISION_LOG_TABLE_NAME=timer-entry-runtime-decision-log \
  -e EXECUTION_LOG_TABLE_NAME=timer-entry-runtime-execution-log \
  python:3.12-slim \
  -lc "pip install boto3 && PYTHONPATH=ops/src python ops/scripts/apply_sql.py --statement \"insert into ops_main.import_cursor (cursor_name, cursor_value, updated_at) values ('oanda_last_transaction_id', 'YOUR_TRANSACTION_ID', now()) on conflict (cursor_name) do update set cursor_value = excluded.cursor_value, updated_at = excluded.updated_at\""
```

## 取込データの現状

`daily_transaction_import` の初版では、Oanda transaction を `ops_main.oanda_transactions_raw` へ raw JSON として保存し、runtime の `decision_log` を `ops_main.runtime_oanda_event_fact` へ `decision_only` として取り込みます。

`runtime_oanda_event_fact` には約定単価、実現損益、Oanda trade id、Oanda transaction id、units などを検索しやすい形で持つ列を用意しています。ただし現時点では、Oanda transaction の正規化、`execution_log` との突合、資金情報 snapshot の fact 化は未実装です。つまり、Oanda の実約定金額や口座資金推移をすぐ SQL / dashboard で検索する段階にはまだ達していません。

## setting labels

runtime の `setting_config.labels` は、ops dashboard での分類・絞り込み用の文字列配列です。売買判定には使いません。

流れ:

1. qualify 最終結果 JSON の `labels` に分類を入れる
2. runtime promotion が `setting_config.labels` として出力する
3. runtime が `trade_state` / `execution_log` / `decision_log` に `setting_labels` として記録する
4. ops import が `decision_log.setting_labels` を `runtime_oanda_event_fact.setting_labels` に JSONB で保存する
5. ops dashboard が `setting_labels` を配列として読み、Label Filter で絞り込む

## 手順まとめ

1. runtime 側を build / deploy し、`correlation_id` を反映する
2. `ops/build.sh` を Docker で実行する
3. `TimerEntryOpsStack` を Docker で deploy する
4. CloudFormation outputs の `OpsDatabaseClusterArn` / `OpsDatabaseSecretArn` を使って `ops/sql/schema.sql` を適用する
5. 必要なら `ops/sql/demo_seed.sql` を適用する
6. EventBridge の日次実行、または Lambda 手動実行で cursor 初期化と import を確認する

## ローカル Web

初期表示は UI 確認用の `ops_demo` schema です。

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -p 3000:3000 \
  -v "$PWD/ops/web:/app" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /app \
  -e AWS_PROFILE \
  -e AWS_REGION=ap-northeast-1 \
  -e OPS_DB_CLUSTER_ARN='...' \
  -e OPS_DB_SECRET_ARN='...' \
  -e OPS_DB_NAME=timer_entry_ops \
  -e OPS_WEB_SCHEMA=ops_demo \
  node:22-bullseye \
  -lc "npm install && npm run dev"
```

起動後に `http://localhost:3000` を開きます。
本番 schema を見る場合は `OPS_WEB_SCHEMA=ops_main` に変更します。

## 補足

- 本番用 schema は `ops_main`、UI 確認用 schema は `ops_demo` を初期値とします
- Oanda transaction cursor は `ops_main.import_cursor` に保存します
- 初回 cursor 未設定時は、Lambda が Oanda の最新 `lastTransactionID` を保存します
- demo seed は UI 表示確認専用で、運用判断には使いません
