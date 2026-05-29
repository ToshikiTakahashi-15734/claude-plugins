#!/usr/bin/env python3
"""
PR Contribution Statusline
==========================
Claude Code のステータスライン用スクリプト。
標準入力で渡される JSON(transcript_path 等) から現在セッションの transcript を読み、
「人間由来コンテキスト」と「AI生成量」の比率を 1 行で出力する。

考え方は analyze.py と同じ:
  人間由来コンテキスト = 人間の指示(会話) + 読み込まれたdoc/コード/コマンド結果(ユニーク)
  AI生成量           = assistant の output_tokens (実測)
  人間コンテキスト比率 = 人間由来 / (人間由来 + AI生成)

settings.json での設定例:
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/<you>/.claude/skills/pr-contribution/statusline.py"
  }
"""
import sys, os, json, glob, hashlib


def estimate_tokens(text):
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return int(ascii_chars / 4 + other / 1.5)


def project_dir_for_cwd(cwd):
    base = os.path.expanduser("~/.claude/projects")
    for slug in (cwd.replace("/", "-").replace(".", "-"), cwd.replace("/", "-")):
        cand = os.path.join(base, slug)
        if os.path.isdir(cand):
            return cand
    return None


def resolve_transcript(data):
    """stdin JSON から transcript パスを決める。無ければ cwd から最新を推定。"""
    tp = data.get("transcript_path")
    if tp and os.path.isfile(tp):
        return tp
    cwd = (data.get("workspace", {}) or {}).get("current_dir") or data.get("cwd") or os.getcwd()
    pdir = project_dir_for_cwd(cwd)
    if not pdir:
        return None
    files = glob.glob(os.path.join(pdir, "*.jsonl"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)  # 最新更新 = 現在セッション


def analyze(path):
    human_prompt = 0
    material = 0
    ai_output = 0
    seen = set()
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return None
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
                continue
            t = o.get("type")
            if t == "user":
                content = o.get("message", {}).get("content")
                if isinstance(content, str):
                    human_prompt += estimate_tokens(content)
                elif isinstance(content, list):
                    has_tr = any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
                    if has_tr:
                        parts = []
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                c = b.get("content")
                                if isinstance(c, str):
                                    parts.append(c)
                                elif isinstance(c, list):
                                    parts += [s.get("text", "") for s in c
                                              if isinstance(s, dict) and s.get("type") == "text"]
                        tr = "\n".join(parts)
                        if tr:
                            h = hashlib.md5(tr.encode("utf-8", "ignore")).hexdigest()
                            if h not in seen:
                                seen.add(h)
                                material += estimate_tokens(tr)
                    else:
                        txt = "\n".join(b.get("text", "") for b in content
                                        if isinstance(b, dict) and b.get("type") == "text")
                        human_prompt += estimate_tokens(txt)
            elif t == "assistant":
                usage = o.get("message", {}).get("usage", {}) or {}
                ai_output += usage.get("output_tokens", 0) or 0
    human = human_prompt + material
    total = human + ai_output
    return human, ai_output, total


# モードファイル。プラグイン更新で消えない安定パスに置く。
# 環境変数 PR_CONTRIB_MODE_FILE で上書き可能。
MODE_FILE = os.environ.get(
    "PR_CONTRIB_MODE_FILE", os.path.expanduser("~/.claude/pr-contribution.mode"))
DEFAULT_PRIOR = 5000  # human-start モードの初期人間クレジット K (tok)


def read_mode():
    """モードファイルを読む。"raw" or "human-start[:K]"。既定は human-start。"""
    mode, prior = "human-start", DEFAULT_PRIOR
    try:
        txt = open(MODE_FILE, encoding="utf-8").read().strip()
    except OSError:
        return mode, prior
    if not txt:
        return mode, prior
    parts = txt.split(":")
    name = parts[0].strip().lower()
    if name in ("raw", "cumulative"):
        mode = "raw"
    elif name in ("human-start", "start", "human"):
        mode = "human-start"
        if len(parts) > 1 and parts[1].strip().isdigit():
            prior = int(parts[1].strip())
    return mode, prior


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    mode, prior = read_mode()

    path = resolve_transcript(data)
    res = analyze(path) if path else None
    human, ai = (res[0], res[1]) if res else (0, 0)

    if mode == "human-start":
        # Aが0(=まだ何も生成していない)なら必ず100%。Aが増えるほど実比率へ収束。
        denom = human + ai + prior
        hr = (human + prior) / denom * 100 if denom else 100.0
        tag = "start"
    else:  # raw: 生の累積。データ皆無なら -- 表示。
        total = human + ai
        if total == 0:
            print("👤 -- 🤖 -- [raw]")
            return
        hr = human / total * 100
        tag = "raw"
    ar = 100 - hr

    # ANSI色: 人間=シアン, AI=マゼンタ
    C = "\033[36m"; M = "\033[35m"; D = "\033[2m"; R = "\033[0m"
    width = 12
    fill = int(round(hr / 100 * width))
    bar = C + "█" * fill + R + D + "░" * (width - fill) + R
    print(f"{C}👤 {hr:.0f}%{R} {bar} {M}🤖 {ar:.0f}%{R} "
          f"{D}({human//1000}k / {ai//1000}k tok)[{tag}]{R}")


if __name__ == "__main__":
    main()
