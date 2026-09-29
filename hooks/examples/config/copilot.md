# GitHub Copilot `.github/hooks/warden.json`

> Verify against the [current GitHub Copilot hook docs](https://docs.github.com/en/copilot/reference/hooks-reference) before use.

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness copilot",
        "cwd": ".",
        "timeoutSec": 10
      }
    ]
  }
}
```

Use `PreToolUse` instead of `preToolUse` when installing through a
Claude-compatible plugin; the adapter accepts either payload shape.
