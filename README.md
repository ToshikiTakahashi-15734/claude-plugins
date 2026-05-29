# claude-plugins

[Claude Code](https://code.claude.com) 用の個人プラグイン集（マーケットプレイス）。

## 収録プラグイン

### pr-contribution

Claude Code との作業における人間とAIの寄与を、transcript(JSONL) と git 差分から数値化するプラグイン。
**意味の異なる2つの指標**を持つ。

#### 指標① 会話コンテキスト比率 — 「どれだけ相談・資料を投入したか」

```
人間由来コンテキスト = 人間が打った指示(会話) + 読み込まれたdoc/既存コード/コマンド結果(ユニーク)
AI生成量           = assistant の output_tokens (実測)
人間コンテキスト比率 = 人間由来コンテキスト / (人間由来 + AI生成)
```

#### 指標② コード実装率 — 「最終的にPRに残ったコードを誰が書いたか」

会話量に左右されず、実際の差分で判定する。

```
PR最終差分の追加行を、Claudeが Write/Edit で書いた内容と1行ずつ照合:
  AIが書いた行   = Claudeの出力に含まれる行
  人間が書いた行 = 含まれない行
AI実装率 = AIが書いた行 / (AIが書いた行 + 人間が書いた行)
```

> ①と②は別物。①でAI比率が高くても、②で人間実装率が高ければ
> 「相談は多いが手は人間が動かした」と読める。

#### できること

| 機能 | 内容 |
|---|---|
| **スキル** `/pr-contribution` | ①②両方を算出して表示。PR本文へ埋め込みも可 |
| **ステータスライン** | 画面下部に現在セッションのコンテキスト比(①)を常時表示（`👤 7% █░░░ 🤖 93%`） |

## インストール

```
/plugin marketplace add ToshikiTakahashi-15734/claude-plugins
/plugin install pr-contribution@takahashitoshiki-plugins
```

スキルは `/pr-contribution:pr-contribution` で実行できます。

### ステータスラインの有効化

ステータスラインは Claude Code 全体で1つだけのため、`settings.json` に手動で設定します。

```jsonc
// ~/.claude/settings.json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/statusline.py\""
  }
}
```

> `${CLAUDE_PLUGIN_ROOT}` が settings.json 内で展開されない環境では、インストール後の
> 実体パス（`~/.claude/plugins/cache/.../statusline.py`）を絶対パスで指定してください。

## ローカル開発・テスト

```bash
# マーケットプレイスとして追加せず直接ロード
claude --plugin-dir ./plugins/pr-contribution

# 編集後の再読み込み（Claude Code内）
/reload-plugins
```

スクリプト単体のテスト:

```bash
# 指標① 会話コンテキスト比率（ブランチ横断で集計）
python3 plugins/pr-contribution/skills/pr-contribution/analyze.py --cwd "$PWD" --branch <branch>

# 指標② コード実装率（誰が書いたか）
python3 plugins/pr-contribution/skills/pr-contribution/code_authorship.py --repo "$PWD"

# ステータスライン出力
echo '{"transcript_path":"<jsonl>"}' | python3 plugins/pr-contribution/skills/pr-contribution/statusline.py
```

## 仕組み

transcript は各自のマシンのローカル（`~/.claude/projects/`）にのみ存在します。
このプラグインは **自分のローカルログのみ** を解析します（他人の会話内容にはアクセスできません）。
チームで共有したい場合は、各自が算出した **数値だけ** を PR 本文やコメントに公開する運用になります。

## 既知の限界

- CLAUDE.md やシステムプロンプトに自動注入される doc は `tool_result` に現れないため、
  人間由来コンテキストに含まれません（参考として「最大コンテキスト」を併記）。
- 人間が他所からコピペした文章も「人間の指示」として数えます（出所までは判別しません）。
- トークン数は文字種ベースの概算（AI生成量のみ実測）。絶対値より比率・推移を見る用途向き。

## License

MIT
