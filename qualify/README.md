# qualify

`qualify/` は `scan` で見つかった候補を、昇格審査用の共通フレームワークで深掘りする入口です。
詳細仕様は `qualify/Spec.md` を参照してください。

## 役割

- E001-E008 を共通実行基盤で扱う
- pandas の canonical engine である `src/timer_entry/backtest_1m.py` を基準にする
- tick replay を `qualify/` 側で共通化する
- ChatGPT 側スレッドで決まった実験パラメータを受けて、Codex 側で機械実行する
- 原則として `pass_stability_gate == True` の候補を昇格審査対象にする

## 使い方

- 方針確認
  - `qualify/Spec.md`
- 監査結果
  - `qualify/docs/Audit_Result.md`
- 運用フロー
  - `qualify/docs/Ops.md`
- experiment ごとの対話テンプレート
  - `qualify/prompts/slot_thread_template.md`

## ディレクトリ規約

`qualify` は 1 slot に複数 setting 候補を持てるよう、`params` と `out` では `slot_id` の下に `vN` ディレクトリを挟む。

- params
  - `qualify/params/{slot_id}/v1/e001.json`
  - `qualify/params/{slot_id}/v2/e001.json`
- out
  - `qualify/out/{slot_id}/v1/E001/latest`
  - `qualify/out/{slot_id}/v2/E001/latest`
- results
  - `qualify/results/{slot_id}/{result_id}.json`
- runtime config
  - `runtime/config/{slot_id}/{result_id}.json`

ここでの `vN` は slot 内 candidate version を表す。slot 自体を `lon08a` のように枝番化しない。
初回候補は `v1` を使う。

現役ではない候補や旧成果物は `archived` 配下へ退避する。

- archived params
  - `qualify/params/archived/{slot_id}/{version_id}/e001.json`
- archived out
  - `qualify/out/archived/{slot_id}/{version_id}/E001/latest`
- archived results
  - `qualify/results/archived/{slot_id}/{version_id}/{result_id}.json`

`archived` には、不合格だった候補、やり直し前の旧候補、regime 変更などで現役から外れた候補を置く。
`version_id` は active と同様に version を表す。既存の旧候補アーカイブは `v0` を使う。

## Docker 実行

ビルド:

```bash
docker build -f docker/Dockerfile -t timer_entry1 .
```

実行例:

E001:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e001.py \
    --params-file qualify/params/{slot_id}/{version_id}/e001.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir qualify/out/{slot_id}/{version_id}/E001/latest
```

E002:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e002.py \
    --params-file qualify/params/{slot_id}/{version_id}/e002.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir qualify/out/{slot_id}/{version_id}/E002/latest
```

E003:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e003.py \
    --params-file qualify/params/{slot_id}/{version_id}/e003.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir qualify/out/{slot_id}/{version_id}/E003/latest
```

E004:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e004.py \
    --params-file qualify/params/{slot_id}/{version_id}/e004.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --ticks-dir ticks/USDJPY \
    --out-dir qualify/out/{slot_id}/{version_id}/E004/latest \
    --jobs 4
```

E005-E008 suite:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e005-e008.py \
    --params-file qualify/params/{slot_id}/{version_id}/e005-e008.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --ticks-dir ticks/USDJPY \
    --out-dir qualify/out/{slot_id}/{version_id} \
    --only E005 E008
```

E005-E008 の sweep / risk 条件は `qualify/params/{slot_id}/{version_id}/e005-e008.json` に書きます。
`--only` は部分再実行したい場合だけ使います。

E008 合格後は `qualify/prompts/final_promotion_result_thread.md` を使い、最終昇格結果を `qualify/results/{slot_id}/{result_id}.json` に保存します。

## 補足

- `qualify` は `scan` のように自律探索するのではなく、ChatGPT 側で決めた JSON params を入力として実行します
- `pass_stability_gate == False` の候補を流す場合は、各 runner に `--allow-gate-fail` を明示してください
- E004 は独立の tick replay 審査です
- E005-E008 は `e005-e008.py` で一括実行を基本とし、入力は `e005-e008.json` を使います
