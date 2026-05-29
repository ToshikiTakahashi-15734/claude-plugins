---
name: pr-contribution
description:
  Claude Code との作業における「人間が投入したコンテキスト量」と「AIが生成した量」を
  transcript(JSONL)から数値化するスキル。人間の指示(会話)・読み込まれたdoc/既存コード/
  コマンド結果を人間由来コンテキストとして集計し、AIのoutput_tokensと比較して
  「人間コンテキスト比率」を算出する。PRブランチ単位で複数セッションを横断集計でき、
  PR作成・更新時に結果を本文へ埋め込める。"/pr-contribution" で実行。
metadata:
  author: takahashitoshiki
  version: '1.0.0'
---

# PR Contribution Analyzer

Claude Code の transcript を解析し、作業に占める **人間由来コンテキスト** と **AI生成量** の
比率を数値化する。「人間がどれだけ設計・コンテキストを与えたか」を可視化するためのスキル。

スクリプトはプラグイン内に同梱されている。パスは環境変数 `${CLAUDE_PLUGIN_ROOT}` を基点に参照する:
`"${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py"`

## 指標の定義

```
人間由来コンテキスト = 人間が打った指示(会話) + 読み込まれたdoc/既存コード/コマンド結果(ユニーク)
AI生成量           = assistant の output_tokens (実測)
人間コンテキスト比率 = 人間由来コンテキスト / (人間由来コンテキスト + AI生成量)
```

- 比率が **高い** → 大量のdoc・既存コード・指示を土台にAIに作らせた = **人間主導**
- 比率が **低い** → わずかなコンテキストからAIが大量に生成した = **AI主導**

> 注: doc/コードの量は transcript 上の `tool_result`(Read/Grep等の結果) から測る。
> 同一ファイルの重複読み込みは1回分として数える。会話の指示と読み込み素材の
> トークン数は文字種ベースの概算(ASCII≒4字/tok, 日本語≒1.5字/tok)。AI生成量は実測値。

## 実行手順

ユーザーが `/pr-contribution` と入力したら、以下を順に行う。

### Step 1: 対象ブランチを特定
カレントディレクトリの git ブランチを取得する。

```bash
git -C "$PWD" rev-parse --abbrev-ref HEAD
```

引数でブランチが渡されていればそれを優先する（例: `/pr-contribution feature/foo`）。
ブランチ単位で集計すると、そのPRに紐づく作業を複数セッション横断で測れる。

### Step 2: 解析を実行
同梱の `analyze.py` を、カレントディレクトリ(cwd)からプロジェクトを自動推定して実行する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py" --cwd "$PWD" --branch "<branch>"
```

ブランチ名が transcript 側で `HEAD` 等になっていて一致しない場合は、まず
`--list-branches` で候補を確認し、合わない場合は `--branch` を外して全体集計するか、
特定セッションを `--session <path>` で指定する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py" --cwd "$PWD" --list-branches
```

### Step 3: 結果を提示
Step 2 の出力をユーザーに見せ、人間コンテキスト比率とその内訳(指示/doc・コード/AI生成)を
日本語で簡潔に解説する。比率が何を意味するか(人間主導かAI主導か)も添える。

### Step 4: PRへの埋め込み（任意）
ユーザーがPR本文への記載を望む場合のみ実行する。markdown を生成する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py" --cwd "$PWD" --branch "<branch>" --markdown
```

- 既存PRがある場合: `gh pr view --json body -q .body` で本文を取得し、生成した
  markdown ブロックを追記して `gh pr edit --body` で更新する。既に
  `## 🤝 Contribution Breakdown` セクションがあれば置き換える。
- PR新規作成時: 本文の末尾にこの markdown ブロックを含めて `gh pr create` する。

PR を勝手に作成・更新せず、必ずユーザーの承認を得てから行うこと。

## オプション早見表

`SCRIPT="${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py"` として:

| 用途 | コマンド |
|---|---|
| ブランチ横断で集計 | `python3 "$SCRIPT" --cwd "$PWD" --branch <branch>` |
| 単一セッションのみ | `python3 "$SCRIPT" --session <file.jsonl>` |
| 全ブランチ合算 | `python3 "$SCRIPT" --cwd "$PWD"` (--branch省略) |
| JSON出力 | `... --json` |
| PR本文用markdown | `... --markdown` |
| 含まれるブランチ確認 | `... --list-branches` |

## 既知の限界

- CLAUDE.md やシステムプロンプトに自動注入される doc は `tool_result` に現れないため、
  人間由来コンテキストに**含まれない**（参考として「最大コンテキスト」を併記している）。
- 人間が他所からコピペした文章は「人間の指示」として数えるため、その出所までは判別しない。
- トークンは概算（AI生成のみ実測）。絶対値より比率・推移を見る用途に向く。
