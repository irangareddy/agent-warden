# Claude Code `.claude/settings.json`

> Verify against the [current Claude Code hook docs](https://code.claude.com/docs/en/hooks) before use.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness claude"
          }
        ]
      }
    ]
  }
}
```
