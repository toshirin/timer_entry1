# prompts

`src/timer_entry/prompts/` には、外部 LLM や監査エージェントへ渡す固定プロンプトを置きます。

現在の用途:

- `claude_core_audit.md`
  - Claude Code / Claude on Bedrock 向けの core 監査依頼テンプレート

方針:

- repo の仕様が固まったら、監査依頼も repo 管理に入れる
- 手元の説明の揺れを減らし、毎回同じ観点で監査できるようにする
