# Grok `.grok/hooks/warden.json`

> Verify against the [current Grok hook docs](https://docs.x.ai/build/features/hooks) before use.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness grok"
          }
        ]
      }
    ]
  }
}
```
