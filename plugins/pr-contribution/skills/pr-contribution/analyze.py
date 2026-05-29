#!/usr/bin/env python3
"""
PR Contribution Analyzer
========================
Claude Code の transcript (JSONL) を解析し、
「人間が投入したコンテキスト量」と「AIが生成した量」を数値化する。

考え方:
  人間由来コンテキスト = 人間が打った指示(user文字列) + 読み込まれたdoc/コード/コマンド結果(tool_result)
  AI生成量            = assistant の output_tokens (実測)
  人間コンテキスト比率 = 人間由来 / (人間由来 + AI生成)

  - 比率が高い  → 大量のdoc/コード/指示を土台にAIに作らせた = 人間主導
  - 比率が低い  → わずかなコンテキストからAIが大量生成     = AI主導

スコープ:
  各エントリの gitBranch を見て、PRブランチ単位で複数セッションを横断集計できる。

使い方:
  python3 analyze.py --branch <branch>          # 現プロジェクトの該当ブランチを横断集計
  python3 analyze.py --session <file.jsonl>      # 単一セッションだけ
  python3 analyze.py --branch <branch> --json     # JSON出力
  python3 analyze.py --branch <branch> --markdown # PR本文に貼る用のmarkdown
"""
import sys, os, json, glob, argparse, hashlib


def estimate_tokens(text):
    """言語混在テキストのトークン数を概算する。
    ASCII(英数記号)は約4文字/token、それ以外(日本語など)は約1.5文字/tokenで見積もる。
    実トークナイザではないが、比率指標には十分な一貫性を持つ。"""
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return int(ascii_chars / 4 + other / 1.5)


def project_dir_for_cwd(cwd):
    """cwd を Claude Code の projects ディレクトリ名に変換する。
    例: /Users/x/develop/app -> ~/.claude/projects/-Users-x-develop-app"""
    base = os.path.expanduser("~/.claude/projects")
    # Claude Code は '/' と '.' を '-' に置換する
    for slug in (cwd.replace("/", "-").replace(".", "-"), cwd.replace("/", "-")):
        cand = os.path.join(base, slug)
        if os.path.isdir(cand):
            return cand
    return None


def user_text(content):
    """userエントリから「人間が打ったテキスト」を取り出す。
    tool_result ブロックを含む場合はツール出力なので人間テキストではない -> None。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
        if has_tool_result:
            return None
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def tool_result_text(content):
    """userエントリ内の tool_result の中身(=読み込まれたdoc/コード/コマンド結果)を文字列化する。"""
    if not isinstance(content, list):
        return None
    out = []
    for b in content:
        if not (isinstance(b, dict) and b.get("type") == "tool_result"):
            continue
        c = b.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            for sub in c:
                if isinstance(sub, dict) and sub.get("type") == "text":
                    out.append(sub.get("text", ""))
    return "\n".join(out) if out else None


def analyze(files, branch=None):
    stats = {
        "human_prompt_tokens": 0,   # 人間が打った指示
        "context_material_tokens": 0,  # 読み込まれたdoc/コード/コマンド結果(ユニーク)
        "ai_output_tokens": 0,      # AIが生成したトークン(実測)
        "human_turns": 0,           # 人間の発話回数
        "ai_turns": 0,              # AIの応答回数
        "peak_context_tokens": 0,   # AIが一度に抱えた最大コンテキスト
        "sessions": set(),
        "branches": set(),
    }
    seen_material = set()  # 同一doc/コードの重複読み込みは1回分として数える

    for fp in files:
        try:
            fh = open(fp, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("isSidechain"):
                    continue  # サブエージェント等の脇道は除外
                eb = o.get("gitBranch")
                if eb:
                    stats["branches"].add(eb)
                if branch is not None and eb != branch:
                    continue
                t = o.get("type")
                if t == "user":
                    msg = o.get("message", {})
                    content = msg.get("content")
                    ut = user_text(content)
                    if ut is not None:
                        stats["human_prompt_tokens"] += estimate_tokens(ut)
                        stats["human_turns"] += 1
                    else:
                        tr = tool_result_text(content)
                        if tr:
                            h = hashlib.md5(tr.encode("utf-8", "ignore")).hexdigest()
                            if h not in seen_material:
                                seen_material.add(h)
                                stats["context_material_tokens"] += estimate_tokens(tr)
                elif t == "assistant":
                    if o.get("sessionId"):
                        stats["sessions"].add(o["sessionId"])
                    usage = o.get("message", {}).get("usage", {}) or {}
                    stats["ai_output_tokens"] += usage.get("output_tokens", 0) or 0
                    stats["ai_turns"] += 1
                    ctx = ((usage.get("input_tokens", 0) or 0)
                           + (usage.get("cache_read_input_tokens", 0) or 0)
                           + (usage.get("cache_creation_input_tokens", 0) or 0))
                    stats["peak_context_tokens"] = max(stats["peak_context_tokens"], ctx)

    human_context = stats["human_prompt_tokens"] + stats["context_material_tokens"]
    ai = stats["ai_output_tokens"]
    total = human_context + ai
    stats["human_context_tokens"] = human_context
    stats["human_context_ratio"] = (human_context / total) if total else 0.0
    stats["ai_ratio"] = (ai / total) if total else 0.0
    stats["sessions"] = sorted(stats["sessions"])
    stats["branches"] = sorted(stats["branches"])
    return stats


def fmt_int(n):
    return f"{n:,}"


def render_human(s, branch):
    hr = s["human_context_ratio"] * 100
    ar = s["ai_ratio"] * 100
    bar_h = int(round(hr / 5))
    bar = "█" * bar_h + "░" * (20 - bar_h)
    lines = [
        "",
        f"  PR Contribution  (branch: {branch or 'ALL'})",
        "  " + "─" * 46,
        f"  人間コンテキスト比率   {hr:5.1f}%  {bar}",
        f"  AI生成比率            {ar:5.1f}%",
        "",
        f"  人間由来コンテキスト   {fmt_int(s['human_context_tokens'])} tok",
        f"    ├ 指示(会話)         {fmt_int(s['human_prompt_tokens'])} tok  ({s['human_turns']} turns)",
        f"    └ doc/コード/結果    {fmt_int(s['context_material_tokens'])} tok  (ユニーク)",
        f"  AI生成                {fmt_int(s['ai_output_tokens'])} tok  ({s['ai_turns']} turns)",
        "",
        f"  最大コンテキスト       {fmt_int(s['peak_context_tokens'])} tok",
        f"  対象セッション数       {len(s['sessions'])}",
        "  " + "─" * 46,
    ]
    return "\n".join(lines)


def render_markdown(s, branch):
    hr = s["human_context_ratio"] * 100
    ar = s["ai_ratio"] * 100
    return "\n".join([
        "## 🤝 Contribution Breakdown",
        "",
        f"| 指標 | 値 |",
        f"|---|---|",
        f"| **人間コンテキスト比率** | **{hr:.1f}%** |",
        f"| AI生成比率 | {ar:.1f}% |",
        f"| 人間由来コンテキスト | {fmt_int(s['human_context_tokens'])} tok |",
        f"| &nbsp;&nbsp;├ 指示(会話) | {fmt_int(s['human_prompt_tokens'])} tok ({s['human_turns']} turns) |",
        f"| &nbsp;&nbsp;└ doc/コード/結果(ユニーク) | {fmt_int(s['context_material_tokens'])} tok |",
        f"| AI生成 | {fmt_int(s['ai_output_tokens'])} tok ({s['ai_turns']} turns) |",
        f"| 最大コンテキスト | {fmt_int(s['peak_context_tokens'])} tok |",
        "",
        f"<sub>人間コンテキスト比率 = 人間由来コンテキスト / (人間由来 + AI生成)。"
        f"高いほど人間が用意した素材(指示・doc・既存コード)を土台にした作業。"
        f"branch: `{branch or 'ALL'}` / {len(s['sessions'])} session(s)。</sub>",
    ])


def main():
    ap = argparse.ArgumentParser(description="PR contribution analyzer")
    ap.add_argument("--branch", help="対象gitブランチ(横断集計)。未指定なら全ブランチ")
    ap.add_argument("--session", help="単一セッションのjsonlファイルを直接指定")
    ap.add_argument("--project-dir", help="~/.claude/projects 配下の対象ディレクトリ")
    ap.add_argument("--cwd", default=os.getcwd(), help="プロジェクト推定に使うcwd")
    ap.add_argument("--json", action="store_true", help="JSON出力")
    ap.add_argument("--markdown", action="store_true", help="PR本文用markdown出力")
    ap.add_argument("--list-branches", action="store_true", help="対象に含まれるブランチ一覧を表示して終了")
    args = ap.parse_args()

    if args.session:
        files = [args.session]
    else:
        pdir = args.project_dir or project_dir_for_cwd(args.cwd)
        if not pdir:
            print(f"projectsディレクトリが見つかりません (cwd={args.cwd})", file=sys.stderr)
            sys.exit(2)
        files = sorted(glob.glob(os.path.join(pdir, "*.jsonl")))
        if not files:
            print(f"transcriptが見つかりません: {pdir}", file=sys.stderr)
            sys.exit(2)

    if args.list_branches:
        s = analyze(files, branch=None)
        print("\n".join(s["branches"]))
        return

    s = analyze(files, branch=args.branch)

    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(render_markdown(s, args.branch))
    else:
        print(render_human(s, args.branch))


if __name__ == "__main__":
    main()
