# Cursor `.cursor/hooks.json`

> Verify against the [current Cursor hook docs](https://cursor.com/docs/hooks) before use.

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "matcher": "*",
        "command": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness cursor",
        "failClosed": true
      }
    ],
    "beforeShellExecution": [
      {
        "command": "python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness cursor",
        "failClosed": true
      }
    ]
  }
}
```

The adapter accepts `tool_name`/`toolName`, `tool_input`/`toolInput`/`input`,
and the top-level `command`/`cwd` form used by `beforeShellExecution`.
