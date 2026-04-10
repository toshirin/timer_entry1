# Audit Result

本ドキュメントは `scan/` の監査結果を集約する。
対象は `probe5` からの移植差分、summary 出力の健全性、昇格ゲート、推薦順の妥当性である。

## 1. 監査対象

- `run_scan.py`
- `reporting.py`
- `src/timer_entry/backtest_fast.py`
- `scan/prompts/priority_review_initial.md`
- `scan/out/*/summary.csv`

比較対象として旧 `probe5` の以下を参照する。

- `../fx_260312/research/probe5/probe5_common.py`
- `../fx_260312/research/probe5/p001a.py`

## 2. 現時点の結論

- scan の実装構造は `probe5` を踏襲している
  - 1時間ごと処理
  - append 書き出し
  - メモリに全件保持しない
- ただし意味論は core に合わせて組み直している
  - Bid / Ask
  - same-bar
  - 保守的 SL exit
  - canonical feature / filter
- したがって、現行 scan は「`probe5` の高速 batch 方式を借りた別仕様」ではなく、「canonical 仕様の fast engine」である

## 3. 検知・反映済みの主な論点

### 3.1 filter universe 差

- 旧 `probe5` には `le0` がなかった
- 現行 scan では `le0` を追加した
- そのため今回上位に来る `le0` 候補は、旧 scan では探索対象外だった可能性がある

### 3.2 stability gate

- 旧 `pass_p007_like` をそのままの名前では使わず、`pass_stability_gate` として正式化した
- 併せて以下を summary に追加した
  - `trade_count_in`
  - `trade_count_out`
  - `in_gross_pips`
  - `out_gross_pips`
  - `rank_in`
  - `rank_out`
  - `rank_gap_abs`
  - `top1_share_of_total`
  - `ex_top10_gross_pips`
  - `pass_stability_gate`

### 3.3 `pass_stability_gate` の定義

初版では以下を満たすものとする。

- `in_gross_pips > 0`
- `out_gross_pips > 0`
- `rank_gap_abs < 100`
- `ex_top10_gross_pips > 0`

また、ChatGPT 側の priority review prompt でも、`pass_stability_gate == False` は原則除外とした。

### 3.4 feature availability の厳密化

- 現行 scan は `t-55 .. t-5` の feature window を厳密に要求する
- 過去不足や window 欠損がある日は scan 対象にしない
- そのため `trade_count` は entry 時刻ごとに自然に変化しうる

## 4. 今回の比較で新たに分かった未検知事項

旧 `probe5` summary と現行 `summary.csv` の比較により、以下は初期監査では未検知だった。

### 4.1 London 側の隣接 slot 完全重複

- 旧 summary では、隣接 slot なのに以下が完全一致する候補が大量にあった
  - `gross_pips`
  - `in_gross_pips`
  - `out_gross_pips`
  - `rank_gap_abs`
  - `ex_top10`
  - `max_dd`
- この種の重複は現行 `summary.csv` では消えている
- したがって、旧 London 側上位の一部は、二重計上や実質重複に汚染されていた可能性がある

### 4.2 旧 scan の `trade_count` 不自然性

- 旧 scan では、同一 slot 内の entry 時刻を変えても `trade_count` が不自然に一定なケースがあった
- 現行 scan では、feature availability の厳密化により、朝一や境界付近ほど `trade_count` が減る自然な形が出ている
- したがって、旧 scan と現行 scan は「SL 修正だけの差」ではない

## 5. 実務的な解釈

- 前回 `probe5` の top 候補と今回の top 候補が大きく変わるのは不自然ではない
- 主因は以下の複合効果と考える
  - London 隣接 slot 重複の解消
  - `trade_count` 形成ロジックの厳密化
  - `le0` 追加
  - SL Bid / Ask 修正
  - same-bar / forced exit 厳密化

したがって、前回 top 候補は「そのまま再利用するもの」ではなく、

- 時間帯として残るか
- side が変わるか
- family が変わるか
- exact minute が変わるか

を分けて見直すべきである。

## 6. 現時点の立場

- 旧 `probe5` の top10 は破棄寄りで扱う
- ただし、`lon08` / `lon09` / `lon12` / `lon13` / `lon15` / `tyo09` のような時間帯自体は再現している可能性がある
- したがって、時間帯レベルの再現性と、候補細目の再現性を分けて評価する

## 7. 今後の追加監査項目

- summary-level exact duplicate 検査の自動化
- 隣接 slot 重複率の自動レポート
- `trade_count` 形状の比較レポート
- 旧 top 候補と現行 top 候補の対応表

## 8. sanity 実行結果

現行 `scan/out/latest` に対して summary-level sanity を実行した結果は以下。

- `summary_row_count = 151800`
- `exact_duplicate_row_count = 0`
- `exact_duplicate_group_count = 0`
- `adjacent_slot_duplicate_row_count = 0`
- `adjacent_slot_duplicate_group_count = 0`

したがって、旧 `probe5` で問題になった London 隣接 slot の大量重複は、現行 scan では再発していない。
少なくとも summary 構造の健全性という観点では、今回の `summary.csv` を scan 基準として採用してよい。
