#!/usr/bin/env python3
"""
ステータスラインのモード切替ヘルパー。
  引数なし          : human-start <-> raw をトグル
  start / human     : human-start に設定
  start:20000       : K(初期人間クレジット)を指定して human-start に
  raw / cumulative  : raw に設定
"""
import os, sys

MODE_FILE = os.environ.get(
    "PR_CONTRIB_MODE_FILE", os.path.expanduser("~/.claude/pr-contribution.mode"))


def read_current():
    try:
        return open(MODE_FILE, encoding="utf-8").read().strip() or "human-start"
    except OSError:
        return "human-start"


def main():
    arg = " ".join(sys.argv[1:]).strip().lower()
    cur = read_current()

    if not arg:  # トグル
        new = "raw" if cur.split(":")[0] in ("human-start", "start", "human") else "human-start"
    elif arg in ("raw", "cumulative"):
        new = "raw"
    elif arg.split(":")[0] in ("start", "human", "human-start"):
        new = f"human-start:{arg.split(':',1)[1]}" if ":" in arg else "human-start"
    else:
        print(f"不明なモード: {arg}  (使い方: start / raw / start:20000)")
        sys.exit(1)

    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    with open(MODE_FILE, "w", encoding="utf-8") as f:
        f.write(new + "\n")
    print(f"ステータスラインのモード: {cur} → {new}")


if __name__ == "__main__":
    main()
