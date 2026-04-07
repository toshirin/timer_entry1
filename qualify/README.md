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
- slot ごとの対話テンプレート
  - `qualify/prompts/slot_thread_template.md`

実装コードはこれから追加します。入口は `qualify/e00N.py`、共通ロジックは `qualify/common/` に寄せる想定です。
