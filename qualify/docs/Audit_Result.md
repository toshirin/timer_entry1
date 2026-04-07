# Audit Result

本ドキュメントは `qualify/` 実装に向けた監査結果を集約する。
比較対象の旧資産は一時 checkout 中の `fx_260312` を参照する。

## 1. 参照対象

比較・監査対象は以下。

- `../fx_260312/research/jst09_exhaustive1/e001.py`
- `../fx_260312/research/jst10_exhaustive1/e001.py`
- `../fx_260312/research/lon08_exhaustive1/e001.py`
- `../fx_260312/research/jst09_exhaustive1/specs/jst09_exhaustive1_E001_E002_Spec_for_Codex.md`
- `../fx_260312/research/jst10_exhaustive1/specs/jst10_exhaustive1_E001_Spec_for_Codex.md`
- `../fx_260312/research/jst12_exhaustive1/specs/jst12_exhaustive1_E001_Spec_for_Codex.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E001_spec.md`
- `../fx_260312/research/lon08_exhaustive1/specs/lon08_exhaustive1_E001A_spec.md`

## 2. 現時点の結論

- 旧 `e001.py` は slot 固定の個別実験としては有用
- ただし、`qualify` の共通基盤へはそのまま移植しない
- 継承すべきなのは実験の目的と比較軸
- 実装は現在の core を使って組み直す

## 3. 継承するもの

- E001 は監査付きモデル実験であり、新規大規模探索ではない
- `all` を baseline として残し、改善候補を比較する
- in / out / year / DD / PF を見る
- tick replay は後続 E004 へ分離する
- `all` 主線 slot でも、小規模な再審査は許容する

## 4. 継承しないもの

- slot ごとの `e001.py` 個別実装
- series ごとに複製された `common/`
- filter 名の方言
- summary 出力の列揺れ
- Buy / Sell 別 util の複製

## 5. 旧実装との差分

- 旧 repo
  - slot 単位のシリーズ実装
  - feature 計算、filter 解釈、summary 出力が series 内に埋め込まれがち
  - E001 が再現実験寄りのものと、深掘り寄りのものが混在
- 新 repo
  - `scan` と `qualify` を repo 上位で分離
  - core 仕様は `src/timer_entry/` に集約済み
  - `qualify` は experiment code ごとの共通基盤として設計する
  - 出力は schema 主語に統一する

## 6. E001 監査メモ

- `all` 本命 slot については、旧 `lon08` E001 / E001A のような代表点比較の考え方が有用
- 旧 `jst10` / `jst12` の仕様書にある「監査付き小規模比較」という位置付けは継承する
- 旧 `jst09` のような再現実験型 E001 は、そのままでは今回の `scan -> qualify` 流れと一致しない

## 7. 未解決論点

- ChatGPT 側から受け取る JSON の最終 schema
- `E001A` のような派生コードの命名・保存ルール
- report 形式の最終標準形
- E002 以降で共通利用する scenario metadata の最小集合
