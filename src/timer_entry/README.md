# timer_entry core

`src/timer_entry/` は `scan` / `qualify` / `runtime` で共有する core 実装です。
ここでは、価格系列規約、時刻処理、特徴量、軽量フィルター、schema、canonical backtest、高速 scan backtest を管理します。

詳細な実装標準は [Spec.md](Spec.md) を参照してください。
監査結果は [docs/Audit_Result.md](docs/Audit_Result.md) に集約します。

## 主なモジュール

- `direction.py`
  - Buy / Sell の価格系列規約
- `time_utils.py`
  - 時刻正規化と timezone 補助
- `minute_data.py`
  - 1分足データの読み込みと TradingDay 化
- `features.py`
  - canonical 特徴量計算
- `filters.py`
  - canonical 軽量フィルター
- `schemas.py`
  - scan / qualify / runtime 共通 schema
- `backtest_1m.py`
  - pandas ベースの canonical backtest engine
- `backtest_fast.py`
  - scan 用の高速 backtest engine
- `tests/`
  - parity test や spot check を置く

## テスト方針

- `backtest_1m.py`
  - 正しさ基準の canonical engine
- `backtest_fast.py`
  - scan 用の高速 engine
- `tests/`
  - 両 engine の parity test
  - event time 列の spot check
  - loader / feature / filter の基礎テスト

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
  python -m pytest src/timer_entry/tests
```

個別実行例:

```bash
docker run --rm \
  -v "$PWD:/work" \
  timer_entry1 \
  python -m pytest src/timer_entry/tests/test_backtest_parity.py
```
