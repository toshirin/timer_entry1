# qualify prompt index

`qualify/prompts/slot_thread_template.md` は親ドキュメントです。
実際の運用では experiment ごとの prompt を使ってください。

## 使用先

- E001
  - `qualify/prompts/e001_slot_thread.md`
- E002
  - `qualify/prompts/e002_thread.md`
- E003
  - `qualify/prompts/e003_thread.md`
- E004
  - `qualify/prompts/e004_thread.md`
- E005
  - `qualify/prompts/e005_e008_thread.md`
- E006
  - `qualify/prompts/e005_e008_thread.md`
- E007
  - `qualify/prompts/e005_e008_thread.md`
- E008
  - `qualify/prompts/e005_e008_thread.md`

## 運用原則

- E001 は scan の `summary_{slot_id}.csv` を読み、filter family 深掘りを決める
- E002 以降は前段の `qualify/out/E00N/...` を読み、次段の JSON を決める
- E005-E008 は `e005-e008.py` で一括実行を基本とし、入力は原則 `e004.json` を再利用する
- 現行 core 未実装の label や field が必要なら、ChatGPT 側は JSON と一緒に定義案を出す
- Codex 側は、その定義案を実装してから実験を実行する

詳細な運用は `qualify/docs/Ops.md` を参照してください。
