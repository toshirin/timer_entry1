# Ops Dashboard UI

本仕様は `timer_entry_ops1` のローカル Web dashboard の UI / API / 集計方針を定義する。
ops 全体の責務、基盤、日次 import、DB 層の親仕様は `ops/Spec.md` を参照する。

## 1. 目的

- Oanda 口座資産、期間別損益、setting 別損益、直近ログをローカル Web で確認する
- runtime の実績を `decision_log` / `execution_log` / Oanda transaction の統合 fact から確認する
- `execution_spec_json` の期待値と実運用の差を setting 単位で追跡する
- conflict、filter skip、kill switch、突合状態を早めに発見できる形にする

## 2. 前提

- Dashboard はローカル起動専用とし、AWS 上に常設公開しない
- browser から AWS へ直接接続せず、Next.js の API route から RDS Data API を呼ぶ
- DB schema は UI 上で `ops_main` / `ops_demo` を選択できる
- Aurora PostgreSQL Serverless v2 は `min ACU 0` を前提とする
- 高頻度 polling は行わず、手動 refresh と必要最小限の自動 retry に留める

## 3. DB Resume 対応

Aurora auto-pause 後の初回アクセスでは、DB resume 待ちが発生する。

UI は以下の状態を持つ。

- loading: API 呼び出し中
- waking: DB 起動中。自動 retry 中であることを表示する
- ready: データ取得済み
- empty: 条件に該当するデータなし
- error: retry しても取得できない

API 側は Data API の一時的な接続失敗、resume 中、timeout を汎用 500 として返さず、可能な範囲で `waking` として扱える status を返す。
フロントは `waking` の場合に短い間隔で数回 retry し、手動 refresh ボタンも表示する。

## 4. 共通コントロール

画面右上に以下を置く。

- DB 選択: `ops_main` / `ops_demo`
- 期間選択: `all` / `year` / `month` / `week`
- 表示時期選択: 前後期間への移動、カレンダーコントロールによる任意時期への移動
- ラベル選択: `all` / include / exclude
- refresh

URL query に状態を保持する。

例:

```text
?schema=ops_demo&period=month&at=2026-04&labelMode=exclude&labels=watch
```

### 4.1 期間と表示粒度

Dashboard の時間粒度は以下とする。

| 期間 | 表示対象 | 集計粒度 |
| --- | --- | --- |
| `all` | 全期間 | 年 |
| `year` | 指定年 | 月 |
| `month` | 指定月 | 日 |
| `week` | 指定週 | 日 |

時間単位表示は採用しない。

### 4.2 ラベル条件

ラベル条件は期間別損益と setting 別損益に適用する。
資産表示には適用しない。

- `all`: ラベル条件なし
- `include`: 選択ラベルを少なくとも 1 つ持つ行を対象にする
- `exclude`: 選択ラベルを 1 つも持たない行を対象にする

`exclude` は `watch` の除外など、監視対象外ラベルを落として通常運用を見る用途を想定する。

## 5. ローカル Config

資産表示の全期間開始値と裁量取引補正は SQL ではなくファイルで管理する。
初期候補は `ops/web/config/dashboard.json` とする。

設定例:

```json
{
  "initialEquityJpy": 100000,
  "initialEquityDate": "2026-01-01",
  "manualAdjustments": [
    {
      "year": 2026,
      "amountJpy": -120,
      "note": "manual trade for API activity"
    }
  ]
}
```

`manualAdjustments` は裁量取引など、runtime 外で発生した損益を年単位で補正するために使う。
基本は空配列とし、必要な年だけ設定する。
補正は損益表示に反映する。
資産グラフは Oanda `account_balance` の実値を表示し、裁量取引補正による加工はしない。

## 6. セクション構成

### 6.1 資産表示

ラベル条件は適用しない。

表示項目:

- 現在資産額
- 選択期間の開始時点からの損益円
- 選択期間の開始時点からの損益率
- 折れ線グラフ

現在資産額は、最新 Oanda transaction の `account_balance` 相当を使う。
過去時点の資産額は、各集計 bucket の最後の `account_balance` を使う。

全期間の開始値は config の `initialEquityJpy` を使う。
年単位の補正損益は、該当年の `manualAdjustments` を加味する。

資産グラフの粒度:

| 期間 | プロット |
| --- | --- |
| `all` | 年ごとの最後の値 |
| `year` | 月ごとの最後の値 |
| `month` | 日ごとの最後の値 |
| `week` | 日ごとの最後の値 |

### 6.2 期間別損益

ラベル条件を適用する。

表は選択期間に応じて以下の行を持つ。

| 期間 | 行 |
| --- | --- |
| `all` | 年 |
| `year` | 月 |
| `month` | 日 |
| `week` | 日 |

現在を含む bucket は、その時点までの値で表示する。

表の列:

- pnl pips
- 累積 pnl pips
- 損益円
- 累積損益円
- maxDD pips
- conflict rate
- trade rate
- win rate

グラフ:

- グラフ1: pnl pips を折れ線、損益円を棒で表示する 2 値グラフ
- グラフ2: 件数の積立グラフ
- グラフ3: 累積 pnl pips と累積損益円の 2 値グラフ

グラフ2の積立項目:

- conflict による不発
- filter による不発
- entry で勝ち
- entry で負け

### 6.3 Setting 別損益

ラベル条件を適用する。

Setting 別損益は以下の 2 セクションに分ける。

- 全 setting 一覧表
- 選択 setting の期間別損益

#### 6.3.1 全 setting 一覧表

行は setting とする。
集計対象は以下とする。

| 期間 | 集計対象 |
| --- | --- |
| `all` | 全期間 |
| `year` | 指定年 |
| `month` | 指定月 |
| `week` | 指定週 |

各行に radio を置き、選択された setting を後続の期間別損益の対象にする。

列:

- setting
- labels
- pnl pips
- 累積 pnl pips
- 損益円
- 累積損益円
- maxDD pips
- conflict rate
- trade rate
- win rate
- kill 状態
- kill 最終発生日からの経過日数
- cagr

`trade rate` と `win rate` は `execution_spec_json` の想定値との差を括弧灰色小文字で表示する。
`cagr` は `all` の年単位表示の場合のみ表示する。
`all` の年単位表示では、pnl pips と cagr にも `execution_spec_json` の想定値との差を括弧灰色小文字で表示する。

Kill 状態は、初版では直近 N 日の `skipped_kill_switch` 有無と、最終発生日からの経過日数で表現する。

#### 6.3.2 選択 setting の期間別損益

期間別損益と同じ表、グラフ1、グラフ2、グラフ3を表示する。
対象は全 setting 一覧表で選択された setting に限定する。

### 6.4 直近ログ

現在の Recent Events 相当。

列:

- time
- setting
- labels
- slot
- decision
- reason
- match
- units
- pnl pips
- 損益円

## 7. 指標定義

### 7.1 Count / Rate

- `decision_count`: fact 行数
- `entered_count`: `decision = 'entered'`
- `conflict_count`: `decision = 'skipped_concurrency'`
- `filter_skip_count`: `decision = 'skipped_filter'` または `reason = 'filter_rejected'`
- `conflict_rate`: `conflict_count / decision_count`
- `trade_rate`: `entered_count / decision_count`
- `win_rate`: `pnl_pips > 0` の決済済み entry 件数 / 決済済み entry 件数

未決済の進行中ポジションは win rate から除外する。

### 7.2 PnL / DD

- `pnl_pips`: 対象 bucket の `pnl_pips` 合計
- `pnl_jpy`: 対象 bucket の `pnl_jpy` 合計
- `cumulative_pnl_pips`: 表示期間の最初から当該 bucket までの累積 `pnl_pips`
- `cumulative_pnl_jpy`: 表示期間の最初から当該 bucket までの累積 `pnl_jpy`
- `maxDD pips`: 累積 pnl pips の peak から trough までの最大下落幅

`maxDD pips` は初版では API 側で日次系列から計算する。

### 7.3 CAGR

`cagr` は `all` の年単位表示の場合のみ表示する。

計算式:

```text
cagr = (ending_equity / beginning_equity) ^ (1 / years) - 1
```

`beginning_equity` は config の `initialEquityJpy` を使う。
`ending_equity` は現在資産額を使う。
`years` は開始日から終了日までの日数を年換算する。
年単位の裁量取引補正は資産表示の損益計算に加味する。

## 8. Data / API 方針

### 8.1 SQL 側に追加する候補

初版で追加検討する SQL 側の構造は以下とする。

- `setting_metadata`
- `daily_setting_summary`

`setting_metadata` は `execution_spec_json`、labels、slot、strategy、想定 `trade_rate`、想定 `win_rate`、想定 `annualized_pips`、想定 `cagr` などを setting 単位で安定参照するために使う。
SQL 側で runtime config の完全な正本を持つというより、dashboard 集計に必要な snapshot として扱う。

`daily_setting_summary` は UI の主参照先とする。
年、月、週の表示は日次 summary からロールアップする。
時間単位 summary は作らない。
初版では既存 view を拡張する。
データ量や Data API 応答時間が問題になった場合は、materialized view よりも日次 import で更新する summary table へ昇格する。

`setting_metadata` は専用 import CLI コマンドで runtime config から取り込む。
Dashboard からの編集は行わない。

### 8.2 既存 fact から追加で欲しい値

直近ログと集計のため、以下は API レスポンスに含める。

- `units`
- `pnl_jpy`
- `status`
- `entry_at`
- `exit_at`

Filter skip は初版では `filter による不発` までを扱い、filter 種別ごとの細分類は行わない。

### 8.3 重い query の扱い

1 発の巨大 query に寄せすぎない。
画面セクションごとに API を分けるか、同一 API 内でも集計単位ごとに query を分離する。

初版は `daily_setting_summary` を中心にし、必要になったら table または materialized view 化する。

## 9. 初版で含めないもの

- Dashboard からの `enabled` 自動操作
- AWS 常設公開
- 認証機構
- リアルタイム更新
- 高頻度 polling
- 時間単位の損益表示

## 10. 残論点

実装前に詰める論点:

- `execution_spec_json` の期待 `annualized_pips` / `cagr` をどのキーから読むか
- 資産 config のファイルパスと Docker mount 方針
- `watch` など運用ラベルの命名規則を固定するか
