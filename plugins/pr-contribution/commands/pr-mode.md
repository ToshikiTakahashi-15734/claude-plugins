---
description: ステータスラインの人間/AI比率モードを切り替える（human-start ⇄ raw）。引数なしでトグル、"raw"/"start"/"start:20000" で指定。
---

以下のコマンドを実行し、切り替え後のモードだけを1行で簡潔に報告してください。
ユーザーが引数（raw / start / start:20000 など）を付けていればそれをモード指定として渡します。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/pr-contribution/mode.py" $ARGUMENTS
```

補足: モードは次の statusline 更新（次の一往復）から反映されます。説明は最小限でよいです。
