# scan

`scan/` はタイマー売買戦略の総当たり探索を行う入口です。
実装方針は `probe5` を踏襲し、1時間ごとに処理してその場で集計を掃き出します。
全時間帯の結果をメモリに溜め込まず、`summary.csv` と slot 別 CSV を逐次書き出します。

内部では `src/timer_entry/backtest_fast.py` を使いますが、scan の構造は高速 batch 実行を優先します。
監査結果は [docs/Audit_Result.md](docs/Audit_Result.md) に集約します。

## slot 定義

- `tyo`
  - `Asia/Tokyo` 基準
  - `07:00` から `15:59` までの 9 slot
  - `tyo07` .. `tyo15`
- `lon`
  - `Europe/London` 基準
  - `08:00` から `21:59` までの 14 slot
  - `lon08` .. `lon21`

## 出力

- `summary.csv`
  - 全 slot / side / entry 時刻 / filter / SL / TP の集計
  - `in/out` 損益、rank、`ex_top10_gross_pips`、`pass_stability_gate` を含む
- `per_slot/summary_tyo09.csv`
  - slot ごとの集計 CSV
- `reports/`
  - markdown 要約
- `sanity/sanity.json`
  - run 全体の summary-level sanity 結果
- `sanity/duplicate_candidates.csv`
  - exact duplicate 候補一覧
- `metadata.json`
  - 実行条件
- `report.zip`
  - 上記一式

## Docker 実行

ビルド:

```bash
docker build -f docker/Dockerfile -t timer_entry1 .
```

実行例:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python scan/run_scan.py \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir scan/out/latest
```

US/UK DST のズレ期間を London trading day から除外して再 scan する場合:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python scan/run_scan.py \
    --years 2019 2020 2021 2022 2023 2024 2025 \
    --dataset-dir dataset \
    --out-dir scan/out/latest \
    --exclude-windows us_uk_dst_mismatch
```

## 補足

- `tqdm` を必須とし、slot ごとの進捗を表示する
- 東京系は `tyoXX`、ロンドン系は `lonXX` の slot 名を使う
- slot ごとの処理が終わるたびに `summary.csv` と `per_slot` へ append する
- `--exclude-windows us_uk_dst_mismatch` は米国と英国の DST 適用状態が異なる London trading day を除外する
- `scan` の昇格ゲートとして `pass_stability_gate` を計算する
- `pass_stability_gate`
  - `in_gross_pips > 0`
  - `out_gross_pips > 0`
  - `rank_gap_abs < 100`
  - `ex_top10_gross_pips > 0`
