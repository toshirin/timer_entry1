# qualify E005-E008 thread

このスレッドでは `qualify/E005-E008` をまとめて議論してください。
対象は E004 を通過した setting です。

主目的は以下です。

- E005
  - slippage 耐性
- E006
  - walk-forward / holdout
- E007
  - risk_fraction / kill-switch / 維持率
- E008
  - entry delay 耐性

## 前提

- E004 は独立の昇格審査です
- E005-E008 はその後段の robustness suite です
- デフォルト実行は `qualify/e005-e008.py` の一括実行です
- 単独確認が必要なら `--only E005` のように実行します
- params は原則として `qualify/params/{slot_id}/e004.json` をそのまま使います

## あなたに依頼したいこと

1. E005-E008 のうち、今回優先して見る論点を整理してください
2. E005-E008 を一括実行してよいか、単独再確認が必要な項目があるか判断してください
3. `--only` で再実行すべき項目があれば列挙してください
4. 結果評価で重視する観点を experiment ごとに整理してください

## 出力形式

以下の順で出してください。

1. 結論
2. E005-E008 の実行方針
3. 単独再実行が必要な項目
4. 評価観点
5. Codex 実行コマンド案
