# Gemini CLI `settings.json` (`.gemini/settings.json` or user settings)

> Verify against the [current Gemini CLI hook docs](https://geminicli.com/docs/hooks/reference/) before use.

```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "name": "Wagent",
            "command": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness gemini"
          }
        ]
      }
    ]
  }
}
```
