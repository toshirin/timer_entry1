# convert_ticks_to_parquet_yearly

`tools/convert_ticks_to_parquet_yearly.py` は、月次の tick zip (`ticks_USDJPY-oj5k_YYYY-MM.zip`) を読み込み、`year` パーティション付きの Parquet データセットへ変換するツールです。

## 概要

- 入力は zip 内の CSV/TSV（通常1ファイル）
- `<DATE> <TIME>` をブローカー時刻（UTC+3 の壁時計）として解釈
- UTCへ補正して `epoch_us`（マイクロ秒）を作成
- `epoch_us`, `bid`, `ask`, `year`, `month` を出力
- chunk 処理で全件をメモリに載せない
- `year=YYYY/part-*.parquet` の構成で書き出し

## 必要モジュール

- `pandas`
- `pyarrow`
- `tqdm`

`zipfile` / `argparse` / `glob` などは標準ライブラリです。

## 実行例

```bash
python tools/convert_ticks_to_parquet_yearly.py \
  --in-dir ticks/zip \
  --out-dir ticks \
  --symbol USDJPY \
  --pattern "ticks_USDJPY-oj5k_*.zip" \
  --sep "\t" \
  --broker-utc-offset-hours 3 \
  --chunksize 2000000
```

## 出力例

```text
dataset_ticks_parquet/
  USDJPY/
    year=2019/
      part-00000000-0.parquet
      part-00000001-0.parquet
    year=2020/
      part-00000042-0.parquet
```

## 補足

- `--sep` は `"\t"` のようなエスケープ指定を受け付けます。
- 不正日時 / `bid` `ask` 欠損行は drop され、最後に統計が表示されます。
- JST 窓抽出は後段で `epoch_us` を基準に実施してください（このツールでは UTC 基準で保存）。
- 実行中は `tqdm` で zip ファイル全体の進捗と、処理中ファイル名を表示します。
