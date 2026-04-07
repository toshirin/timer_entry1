# scan priority review: initial prompt

このスレッドでは、`timer_entry1` の scan 結果を解釈し、`qualify` に着手する優先順位を決めてください。
コード生成や実装提案は主目的ではありません。主目的は、scan 結果の読解、優先順位付け、E001 の初手設計です。

## 前提

- この repo はタイマー売買戦略専用 repo です
- 実装仕様は添付の Constitution / README / Spec / schemas / filters に固定されています
- `strategy / slot / setting` の意味は添付資料に従ってください
- `slot`
  - `tyo07` から `tyo15`
  - `lon08` から `lon21`
- `scan`
  - filter family の当たりを見る段階です
  - 基本閾値だけを見ています
- `qualify`
  - scan で反応した family の閾値深掘りを行う段階です
- Bid/Ask、same-bar、保守的 SL exit、event time の扱いは core で固定済みです

## あなたに依頼したいこと

1. `summary.csv` を読んで、`qualify` に回す優先 slot を順位付きで提案してください
2. 各 slot について、`buy/sell` のどちらを先に見るべきか示してください
3. 各 slot について、どの filter family を E001 で深掘るべきか示してください
4. 理由は少なくとも以下を踏まえて説明してください
   - `gross_pips`
   - `trade_count`
   - `profit_factor`
   - `max_dd_pips`
   - `same_bar_conflict_count`
   - `same_bar_unresolved_count`
   - `forced_exit_count`
5. 最後に、次スレへそのまま渡せる着手順序表を出してください

## 出力形式

以下の順で出してください。

1. 全体の優先順位
2. slot ごとの簡潔な理由
3. `qualify/E001` の初手案
4. 次スレ用の着手順序表

## 注意

- `scan` は family 探しです。scan の条件名をそのまま最終結論扱いしないでください
- `qualify` では threshold sweep や percentile sweep の入口を示してください
- `all` が強い場合は「追加 filter なしが有力」なのか、「未探索 family がある可能性」なのかを分けて考えてください
- `same_bar_unresolved_count` が多い slot は execution リスク込みで評価してください
- `trade_count` が薄い候補は、gross が高くても過信しないでください

## このスレッドに添付する資料

- `docs/FX_Research_Constitution.md`
- `README.md`
- `src/timer_entry/Spec.md`
- `src/timer_entry/schemas.py`
- `src/timer_entry/filters.py`
- `scan/README.md`
- 今回 run の `summary.csv`
- 今回 run の `reports/summary_report.md`
- 必要な `per_slot/summary_*.csv`
