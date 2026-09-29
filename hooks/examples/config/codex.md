# Codex `.codex/hooks.json`

> Verify against the [current Codex hook docs](https://developers.openai.com/codex/hooks) before use.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness codex"
          }
        ]
      }
    ]
  }
}
```

Codex does not expose hosted-tool calls to this local hook.
