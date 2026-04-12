# timer_entry runtime

時刻起点の短期売買戦略を AWS Lambda 上で運用するための runtime です。
詳細仕様は `runtime/Spec.md` を参照してください。

## できること

- EventBridge 起動の `entry_handler` / `forced_exit_handler`
- DynamoDB `setting_config` による setting 駆動運用
- Oanda REST API での成行 entry、TP/SL 作成、forced exit
- `SETTING_*` 監査ログ出力
- `decision_log` による不発・skip 理由の永続化
- setting 単位の kill switch
- qualify の最終結果から runtime setting_config JSON への promotion
- CDK による基盤作成

## core との関係

`runtime/build.sh` は Lambda zip 作成時に `runtime/src/timer_entry_runtime` と `src/timer_entry` を同梱します。
runtime は core の以下を利用します。

- `timer_entry.direction`: buy/sell の Bid/Ask 規約
- `timer_entry.filters`: qualify filter label から runtime filter spec への変換
- `timer_entry.schemas`: qualify/scan/runtime 間の setting schema

`runtime/src/timer_entry_runtime/filtering.py` は Oanda の直近 candle から runtime 実行時に filter 判定するための軽量評価器です。
core 側の filter label 変換は利用していますが、core の pandas 前提 feature 計算を Lambda handler の実行経路へ持ち込まないため、runtime 側で Candle dataclass 向けに評価しています。

## ディレクトリ

- `runtime/src/timer_entry_runtime/`: Lambda 本体
- `runtime/cdk/`: AWS CDK 定義
- `runtime/scripts/`: 運用補助 script
- `runtime/build.sh`: Lambda zip 作成
- `runtime/apply_setting.sh`: setting_config 投入
- `runtime/disable_setting.sh`: setting 無効化
- `runtime/dist/`: build 生成物
- `runtime/Spec.md`: 仕様書

## 前提

- Oanda の認証情報を Secrets Manager に手動登録済みであること
- AWS 認証情報を利用できること
- 初期対象 instrument は `USD_JPY`
- `setting_config` / `trade_state` / `execution_log` / `decision_log` は CDK で作成する

Secrets Manager の想定キー:

- `access_token`
- `account_id`
- `environment`

## ビルド

ローカル実行:

```bash
bash runtime/build.sh
```

Docker 実行:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -w /work \
  public.ecr.aws/lambda/python:3.12 \
  runtime/build.sh
```

生成物:

- `runtime/dist/entry_handler.zip`
- `runtime/dist/forced_exit_handler.zip`

## CDK

依存インストール:

```bash
cd runtime/cdk
npm install
```

補足:

- 初回は `package-lock.json` が未作成のため `npm install` を使う
- `package-lock.json` 作成後は `npm ci` に切り替えてよい
- deploy 前に `bash runtime/build.sh` を実行して zip を作成する

synth:

```bash
cd runtime/cdk
npx cdk synth
```

bootstrap:

```bash
cd runtime/cdk
npx cdk bootstrap aws://YOUR_ACCOUNT_ID/ap-northeast-1
```

deploy:

```bash
cd runtime/cdk
npx cdk deploy TimerEntryRuntimeStack --require-approval never
```

Docker で deploy:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work/runtime/cdk \
  node:22-bullseye \
  -lc "npm install && npx cdk deploy TimerEntryRuntimeStack --require-approval never"
```

Docker で bootstrap:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /work/runtime/cdk \
  node:22-bullseye \
  -lc "npm install && npx cdk bootstrap aws://YOUR_ACCOUNT_ID/ap-northeast-1"
```

主な環境変数:

- `OANDA_SECRET_NAME`
- `ENTRY_SCHEDULE_EXPRESSION`
- `EXIT_SCHEDULE_EXPRESSION`
- `SUPPORTED_MARKET_TIMEZONES`
- `FORCED_EXIT_RETRY_COUNT`
- `TRADE_STATE_TTL_DAYS`
- `DECISION_LOG_TTL_DAYS`
- `LOG_LEVEL`

## setting_config

runtime は DynamoDB の `setting_config` を参照して動作します。
少なくとも以下を設定します。

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
- `tp_pips`
- `sl_pips`
- `market_open_check_seconds`
- `max_concurrent_positions`

サイズ設定:

- `fixed_units`
- または `margin_ratio_target`
- 必要に応じて `size_scale_pct`

kill switch 設定:

- `kill_switch_dd_pct`
- `kill_switch_reference_balance_jpy`
- `min_maintenance_margin_pct`

同時動作制御:

- `max_concurrent_positions`
- 初期運用では `1` を推奨
- `1` の場合、Oanda 口座上に open trade が 1 本でも残っていれば新規 entry を見送る
- 見送りは `decision_log` に `skipped_concurrency` として残す

filter 設定:

- `filter_spec_json`

## qualify から setting_config を作る

qualify の最終結果 JSON から runtime setting_config JSON を作成します。
初期状態では `enabled=false` で出力されます。
既定では `fixed_units=10`、`max_concurrent_positions=1`、`kill_switch_dd_pct=-0.2`、`kill_switch_reference_balance_jpy=100000`、`min_maintenance_margin_pct=150` を補完します。必要に応じて `--fixed-units`、`--use-margin-ratio --margin-ratio-target`、`--size-scale-pct`、`--kill-switch-dd-pct`、`--kill-switch-reference-balance-jpy`、`--min-maintenance-margin-pct`、`--max-concurrent-positions` で上書きします。

```bash
PYTHONPATH="$PWD/src:$PWD/runtime/src:$PWD" \
python3 -m timer_entry_runtime.promotion \
  --params-file qualify/params/lon15/e004.json \
  --out-file runtime/out/lon15_e004_runtime.json \
  --setting-id lon15_e004_runtime_v1
```

Docker 実行:

```bash
docker run --rm \
  -v "$PWD:/work" \
  -w /work \
  -e PYTHONPATH=/work/src:/work/runtime/src:/work \
  python:3.12-slim \
  python -m timer_entry_runtime.promotion \
    --params-file qualify/params/lon15/e004.json \
    --out-file runtime/out/lon15_e004_runtime.json \
    --setting-id lon15_e004_runtime_v1
```

有効化済み JSON として出す場合:

```bash
PYTHONPATH="$PWD/src:$PWD/runtime/src:$PWD" \
python3 -m timer_entry_runtime.promotion \
  --params-file qualify/params/lon15/e004.json \
  --out-file runtime/out/lon15_e004_runtime_enabled.json \
  --setting-id lon15_e004_runtime_v1 \
  --enabled
```

Docker 実行:

```bash
docker run --rm \
  -v "$PWD:/work" \
  -w /work \
  -e PYTHONPATH=/work/src:/work/runtime/src:/work \
  python:3.12-slim \
  python -m timer_entry_runtime.promotion \
    --params-file qualify/params/lon15/e004.json \
    --out-file runtime/out/lon15_e004_runtime_enabled.json \
    --setting-id lon15_e004_runtime_v1 \
    --enabled
```

## setting 投入

```bash
AWS_ACCESS_KEY_ID=xxx \
AWS_SECRET_ACCESS_KEY=xxx \
AWS_REGION=ap-northeast-1 \
bash runtime/apply_setting.sh \
  runtime/out/lon15_e004_runtime.json
```

無効化:

```bash
AWS_ACCESS_KEY_ID=xxx \
AWS_SECRET_ACCESS_KEY=xxx \
AWS_REGION=ap-northeast-1 \
bash runtime/disable_setting.sh \
  lon15_e004_runtime_v1
```

補足:

- `SETTING_CONFIG_TABLE_NAME` を指定しない場合、既定値は `timer-entry-runtime-setting-config`
- `apply_setting.sh` は plain JSON を DynamoDB 形式へ変換して投入する
- 既存 `setting_id` に対して再 apply した場合、`created_at` は保持し、`updated_at` のみ更新する

aws CLI 未導入の場合の Docker 例:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -e AWS_ACCESS_KEY_ID=xxx \
  -e AWS_SECRET_ACCESS_KEY=xxx \
  -e AWS_REGION=ap-northeast-1 \
  -w /work \
  python:3.12-slim \
  -lc "pip install --no-cache-dir awscli && bash runtime/apply_setting.sh runtime/out/lon15_e004_runtime.json"
```

Docker で無効化:

```bash
docker run --rm \
  --entrypoint /bin/bash \
  -v "$PWD:/work" \
  -e AWS_ACCESS_KEY_ID=xxx \
  -e AWS_SECRET_ACCESS_KEY=xxx \
  -e AWS_REGION=ap-northeast-1 \
  -w /work \
  python:3.12-slim \
  -lc "pip install --no-cache-dir awscli && bash runtime/disable_setting.sh lon15_e004_runtime_v1"
```

## trigger_bucket

`trigger_bucket` は timezone を含めた実行スロットです。

例:

- `ENTRY#Asia/Tokyo#0925`
- `EXIT#Asia/Tokyo#1000`
- `ENTRY#Europe/London#1000`

EventBridge から `trigger_bucket` を明示的に渡さない場合、Lambda 側で対応 timezone 分を計算します。

## ログ

CloudWatch Logs に以下のラベルで JSON ログを出力します。

- `SETTING_SCAN`
- `SETTING_CHECK`
- `SETTING_FILTER`
- `SETTING_SKIP`
- `SETTING_ENTER`
- `SETTING_TP_SL`
- `SETTING_EXIT`
- `SETTING_ERROR`
- `DECISION_LOG_ERROR`

DynamoDB には以下を残します。

- `execution_log`: broker への発注要求と Oanda order/trade の記録
- `decision_log`: disabled、clock mismatch、market closed、concurrency、filter rejection、duplicate、kill switch、entry/exit failure などの判断記録
