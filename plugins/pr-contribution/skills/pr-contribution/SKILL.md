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

Claude Code の transcript を解析し、作業における人間とAIの寄与を数値化するスキル。
**2つの独立した指標**を持つ。

スクリプトはプラグイン内に同梱されている。パスは環境変数 `${CLAUDE_PLUGIN_ROOT}` を基点に参照する。

## ステータスラインのモード（`statusline.py`）

画面下部の常時表示には2モードある。モードは `~/.claude/pr-contribution.mode`
（環境変数 `PR_CONTRIB_MODE_FILE` で変更可）で切り替える。

| モード | 挙動 | 式 |
|---|---|---|
| **human-start**（既定） | まだAIが何も生成していない状態は**人間100%**から始まり、AIが生成するほど実比率へ収束 | `(H+K) / (H+A+K)` |
| **raw** | 生の累積比率（従来）。データ皆無なら `--` | `H / (H+A)` |

- `K` は100%の粘り具合を決める初期人間クレジット（既定5000tok）。`human-start:20000` のように指定可。
- 切替コマンド:
  ```bash
  echo human-start   > ~/.claude/pr-contribution.mode   # 100%スタート（既定）
  echo human-start:20000 > ~/.claude/pr-contribution.mode  # 100%を長く保つ
  echo raw           > ~/.claude/pr-contribution.mode   # 生の累積
  ```
- 表示末尾に現在のモードが `[start]` / `[raw]` として出る。

## 指標① 会話コンテキスト比率（`analyze.py`）

「どれだけ相談・資料を投入したか」= **会話・コンテキストの量**を測る。

```
人間由来コンテキスト = 人間が打った指示(会話) + 読み込まれたdoc/既存コード/コマンド結果(ユニーク)
AI生成量           = assistant の output_tokens (実測)
人間コンテキスト比率 = 人間由来コンテキスト / (人間由来コンテキスト + AI生成量)
```

- 比率が **高い** → 大量のdoc・既存コード・指示を土台にAIに作らせた = **人間主導**
- 比率が **低い** → わずかなコンテキストからAIが大量に生成した = **AI主導**

> 注: この指標は**会話量**を見ており、最終的なコードの著者は見ていない。
> AI生成量にはコード以外(説明・思考・ボツ案)も含まれるため、おしゃべりなセッションほどAI比率が上がる。
> 「コードを誰が書いたか」を知りたい場合は指標②を使う。

## 指標② コード実装率（`code_authorship.py`）

「最終的にPRに残ったコードを誰が書いたか」= **コードの著者**を測る。会話量に左右されない。

```
PR最終差分(base...HEAD)の追加行を、Claudeが Write/Edit/MultiEdit で書いた内容と1行ずつ照合:
  AIが書いた行   = Claudeの出力に含まれる追加行
  人間が書いた行 = Claudeの出力に含まれない追加行
AI実装率 = AIが書いた行 / (AIが書いた行 + 人間が書いた行)
```

> 注: 空行・括弧だけ等の些末な行は誤判定の元なので分母から除外する。
> インデント差を吸収するため行は trim して照合する(短い汎用行の誤マッチを避けるため些末行を除外)。
> lockファイル等の生成物は「人間が書いた行」に大量計上されうる点に注意。

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

### Step 3: コード実装率を解析（指標②）
最終的なコードを誰が書いたかを `code_authorship.py` で測る。git リポジトリ内で実行する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/code_authorship.py" --repo "$PWD"
```

ベースブランチは自動検出(origin/main → master → develop の順)。明示する場合は `--base <ref>`。
未コミットの変更も含めるなら `--include-working-tree`。

### Step 4: 結果を提示
指標①(会話コンテキスト比率)と指標②(コード実装率)の両方を提示し、日本語で簡潔に解説する。
- ①は「どれだけ相談・資料を投入したか」、②は「実際のコードを誰が書いたか」で意味が違う点を必ず添える。
- 例: ①でAI比率が高くても、②で人間実装率が高ければ「相談は多いが手は人間が動かした」と読める。

### Step 5: PRへの埋め込み（任意）
ユーザーがPR本文への記載を望む場合のみ実行する。両指標の markdown を生成する。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py" --cwd "$PWD" --branch "<branch>" --markdown
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/code_authorship.py" --repo "$PWD" --markdown
```

- 既存PRがある場合: `gh pr view --json body -q .body` で本文を取得し、生成した
  markdown ブロックを追記して `gh pr edit --body` で更新する。既に
  `## 🤝 Contribution Breakdown` / `## 🧑‍💻 Code Authorship` セクションがあれば置き換える。
- PR新規作成時: 本文の末尾にこれらの markdown ブロックを含めて `gh pr create` する。

PR を勝手に作成・更新せず、必ずユーザーの承認を得てから行うこと。

## オプション早見表

指標①: `A="${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/analyze.py"`

| 用途 | コマンド |
|---|---|
| ブランチ横断で集計 | `python3 "$A" --cwd "$PWD" --branch <branch>` |
| 単一セッションのみ | `python3 "$A" --session <file.jsonl>` |
| 全ブランチ合算 | `python3 "$A" --cwd "$PWD"` (--branch省略) |
| JSON / markdown 出力 | `... --json` / `... --markdown` |
| 含まれるブランチ確認 | `... --list-branches` |

指標②: `B="${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/code_authorship.py"`

| 用途 | コマンド |
|---|---|
| コード実装率を測る | `python3 "$B" --repo "$PWD"` |
| ベース指定 | `python3 "$B" --repo "$PWD" --base origin/main` |
| 未コミット変更も含む | `python3 "$B" --repo "$PWD" --include-working-tree` |
| JSON / markdown 出力 | `... --json` / `... --markdown` |

## 既知の限界

指標①（会話コンテキスト比率）:
- CLAUDE.md やシステムプロンプトに自動注入される doc は `tool_result` に現れないため、
  人間由来コンテキストに**含まれない**（参考として「最大コンテキスト」を併記している）。
- 人間が他所からコピペした文章は「人間の指示」として数えるため、その出所までは判別しない。
- 会話量を見ており、最終コードの著者は見ていない（それは指標②の役目）。

指標②（コード実装率）:
- lockファイル等の生成物・vendoredコードは「人間が書いた行」に大量計上されうる。
- インデント差吸収のため行を trim 照合するため、短い汎用行は誤マッチしうる（些末行は分母から除外して緩和）。
- 人間がClaudeの出力をコピペした行はAI判定になる（タイプ元ではなく内容で判定するため）。
- トークンは概算（AI生成のみ実測）。絶対値より比率・推移を見る用途に向く。
