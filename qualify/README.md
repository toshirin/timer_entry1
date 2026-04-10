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
    --params-file qualify/params/{slot_id}/e001.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir qualify/out/E001/latest
```

E002:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e002.py \
    --params-file qualify/params/{slot_id}/e002.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir qualify/out/E002/latest
```

E003:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e003.py \
    --params-file qualify/params/{slot_id}/e003.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir qualify/out/E003/latest
```

E004:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e004.py \
    --params-file qualify/params/{slot_id}/e004.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --ticks-dir ticks/USDJPY \
    --out-dir qualify/out/E004/latest \
    --jobs 4
```

E005-E008 suite:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python qualify/e005-e008.py \
    --params-file qualify/params/{slot_id}/e004.json \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --ticks-dir ticks/USDJPY \
    --out-dir qualify/out \
    --only E005 E008
```

## 補足

- `qualify` は `scan` のように自律探索するのではなく、ChatGPT 側で決めた JSON params を入力として実行します
- `pass_stability_gate == False` の候補を流す場合は、各 runner に `--allow-gate-fail` を明示してください
- E004 は独立の tick replay 審査です
- E005-E008 は `e005-e008.py` で一括実行を基本とし、入力は原則 `e004.json` を再利用します
