#!/usr/bin/env python3
"""
Code Authorship Analyzer
========================
「PRのコードを誰が書いたか」を測る。会話量ではなく、最終的にPRに残ったコードで判定する。

考え方:
  1. base ブランチとの差分(git diff)から、PRで追加された行を集める。
  2. transcript から Claude が Write/Edit/MultiEdit で書いた行をすべて集める。
  3. 追加行の各行が Claude の書いた内容に含まれていれば「AIが書いた行」、
     含まれていなければ「人間が書いた行」とする。
  4. AI実装率 = AIが書いた行 / (AIが書いた行 + 人間が書いた行)

  些末な行(空行・括弧だけ等)は誤判定の元なので分母から除外する。

使い方:
  python3 code_authorship.py --repo <repo path> [--base main] [--branch <b>]
  python3 code_authorship.py --repo <repo> --markdown
"""
import sys, os, json, glob, argparse, subprocess


def project_dir_for_cwd(cwd):
    base = os.path.expanduser("~/.claude/projects")
    for slug in (cwd.replace("/", "-").replace(".", "-"), cwd.replace("/", "-")):
        cand = os.path.join(base, slug)
        if os.path.isdir(cand):
            return cand
    return None


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True)


def detect_base(repo, explicit):
    if explicit:
        return explicit
    for ref in ("origin/main", "origin/master", "main", "master", "develop"):
        if git(repo, "rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return ref
    return None


def is_trivial(line):
    """空行・括弧だけ・極端に短い行は照合の誤判定が多いので除外する。"""
    s = line.strip()
    if len(s) < 4:
        return True
    if all(c in "{}()[];,:" for c in s):
        return True
    return False


def diff_added_lines(repo, base, include_wt):
    """base...HEAD の追加行(+行)を返す。include_wt なら未コミット変更も含める。"""
    specs = [f"{base}...HEAD"]
    if include_wt:
        specs = [base]  # base と作業ツリーの差分
    out = git(repo, "diff", "--no-color", "-U0", *specs).stdout
    added = []
    for ln in out.splitlines():
        if ln.startswith("+++"):
            continue
        if ln.startswith("+"):
            added.append(ln[1:])
    return added


def claude_lines(files, branch=None):
    """transcript から Claude が Write/Edit 系で書いた行の集合を返す(正規化済み)。"""
    lines = set()
    EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
    for fp in files:
        try:
            fh = open(fp, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    o = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "assistant" or o.get("isSidechain"):
                    continue
                if branch is not None and o.get("gitBranch") not in (None, branch):
                    continue
                content = o.get("message", {}).get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    if b.get("name") not in EDIT_TOOLS:
                        continue
                    inp = b.get("input", {}) or {}
                    texts = []
                    if "content" in inp:           # Write
                        texts.append(inp["content"])
                    if "new_string" in inp:        # Edit
                        texts.append(inp["new_string"])
                    if "new_source" in inp:        # NotebookEdit
                        texts.append(inp["new_source"])
                    for e in inp.get("edits", []) or []:  # MultiEdit
                        if isinstance(e, dict) and "new_string" in e:
                            texts.append(e["new_string"])
                    for t in texts:
                        if not isinstance(t, str):
                            continue
                        for line in t.splitlines():
                            lines.add(line.strip())
    return lines


def analyze(repo, base, files, branch, include_wt):
    added = diff_added_lines(repo, base, include_wt)
    ai_set = claude_lines(files, branch)
    ai = human = trivial = 0
    for line in added:
        if is_trivial(line):
            trivial += 1
            continue
        if line.strip() in ai_set:
            ai += 1
        else:
            human += 1
    total = ai + human
    return {
        "ai_lines": ai,
        "human_lines": human,
        "trivial_lines": trivial,
        "scored_lines": total,
        "ai_impl_rate": (ai / total) if total else 0.0,
        "human_impl_rate": (human / total) if total else 0.0,
        "base": base,
    }


def render_human(s, branch):
    ar = s["ai_impl_rate"] * 100
    hr = s["human_impl_rate"] * 100
    fill = int(round(ar / 5))
    bar = "█" * fill + "░" * (20 - fill)
    return "\n".join([
        "",
        f"  Code Authorship  (base: {s['base']}, branch: {branch or 'current'})",
        "  " + "─" * 48,
        f"  AI実装率              {ar:5.1f}%  {bar}",
        f"  人間実装率            {hr:5.1f}%",
        "",
        f"  AIが書いた行           {s['ai_lines']:,}",
        f"  人間が書いた行         {s['human_lines']:,}",
        f"  判定対象の追加行       {s['scored_lines']:,}",
        f"  (些末で除外した行       {s['trivial_lines']:,})",
        "  " + "─" * 48,
    ])


def render_markdown(s, branch):
    ar = s["ai_impl_rate"] * 100
    hr = s["human_impl_rate"] * 100
    return "\n".join([
        "## 🧑‍💻 Code Authorship",
        "",
        "| 指標 | 値 |",
        "|---|---|",
        f"| **AI実装率** | **{ar:.1f}%** |",
        f"| 人間実装率 | {hr:.1f}% |",
        f"| AIが書いた行 | {s['ai_lines']:,} |",
        f"| 人間が書いた行 | {s['human_lines']:,} |",
        f"| 判定対象の追加行 | {s['scored_lines']:,}（些末 {s['trivial_lines']:,} 行を除外） |",
        "",
        f"<sub>PR最終差分(base: `{s['base']}`)の追加行を、Claudeが Write/Edit で書いた内容と照合して判定。"
        f"会話量ではなく実際にPRに残ったコードで算出。空行・括弧のみ等の些末な行は分母から除外。</sub>",
    ])


def main():
    ap = argparse.ArgumentParser(description="code authorship analyzer")
    ap.add_argument("--repo", default=os.getcwd(), help="gitリポジトリのパス")
    ap.add_argument("--base", help="比較対象のベースブランチ(未指定なら自動検出)")
    ap.add_argument("--branch", help="transcript絞り込み用ブランチ(任意)")
    ap.add_argument("--project-dir", help="~/.claude/projects 配下の対象ディレクトリ")
    ap.add_argument("--include-working-tree", action="store_true",
                    help="未コミットの作業ツリー変更も含める")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if git(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
        print(f"git リポジトリではありません: {repo}", file=sys.stderr)
        sys.exit(2)

    base = detect_base(repo, args.base)
    if not base:
        print("ベースブランチを検出できません。--base で指定してください。", file=sys.stderr)
        sys.exit(2)

    pdir = args.project_dir or project_dir_for_cwd(repo)
    files = sorted(glob.glob(os.path.join(pdir, "*.jsonl"))) if pdir else []
    if not files:
        print(f"transcriptが見つかりません(project dir: {pdir})。AI行は0として計算します。",
              file=sys.stderr)

    s = analyze(repo, base, files, args.branch, args.include_working_tree)

    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(render_markdown(s, args.branch))
    else:
        print(render_human(s, args.branch))


if __name__ == "__main__":
    main()
