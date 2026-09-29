# Wagent hooks

`warden_hook.py` is the shared policy entry point. It reads one hook event from
standard input, normalizes the tool name and arguments, calls the existing
`agent.warden.Warden`, and translates `allow`, `block`, or `ask` back into the
harness's native response. The older `claude_code_pretooluse.py` path remains a
thin, backward-compatible Claude wrapper.

```bash
python3 /ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py --harness claude
```

Replace `claude` with `codex`, `cursor`, `copilot`, `gemini`, `grok`, or
`generic`. Copy and adapt the [configuration snippets](examples/config/); each
snippet is deliberately marked **verify against current docs** because hook
configuration schemas can change.

## Harness support

The native hook contracts below were verified on 2026-09-29. “Ask: deny” means
the adapter does not assume that a reliable interactive approval flow exists;
it blocks with a reason beginning `Needs human approval:`.

| Harness | Configuration | Block response | Ask | Failure behavior | Coverage and status |
|---|---|---|---|---|---|
| [Claude Code](https://code.claude.com/docs/en/hooks) | `.claude/settings.json`, `.claude/settings.local.json`, or `~/.claude/settings.json` | Exit 2 with reason on stderr | Native `permissionDecision: "ask"` | Adapter errors fail open; `AGENT_WARDEN_FAIL_CLOSED=1` exits 2 | PreToolUse; verified and subprocess-tested |
| [Codex](https://developers.openai.com/codex/hooks) | `.codex/hooks.json` or `~/.codex/hooks.json` | PreToolUse deny JSON | Deny | Adapter errors fail open; fail-closed mode exits 2 | Local tool calls only; hosted tools are not covered; verified and subprocess-tested |
| [Cursor](https://cursor.com/docs/hooks) | `.cursor/hooks.json` or `~/.cursor/hooks.json` | `{"permission":"deny",...}` | Deny | Cursor hook crashes/timeouts fail open unless `failClosed:true`; adapter fail-closed mode exits 2 | `preToolUse` and `beforeShellExecution`; cloud read-only startup turns do not run hooks; field variants are assumptions; verified and subprocess-tested |
| [GitHub Copilot](https://docs.github.com/en/copilot/reference/hooks-reference) | `.github/hooks/warden.json` or user hooks directory | Exit 2 with reason on stderr | Deny | Nonzero command exits deny; timeouts fail open; adapter errors otherwise fail open | Native `preToolUse` and Claude-compatible `PreToolUse`; verified and both payloads subprocess-tested |
| [Gemini CLI](https://geminicli.com/docs/hooks/reference/) | `.gemini/settings.json` or `~/.gemini/settings.json` | `{"decision":"deny","reason":...}` | Deny | Only exit 2 blocks on failure; other nonzero exits fail open; adapter fail-closed mode uses exit 2 | BeforeTool; verified and subprocess-tested |
| [Grok](https://docs.x.ai/build/features/hooks) | `.grok/hooks/warden.json` | `{"decision":"deny","reason":...}` | Deny | Crashes/timeouts fail open; adapter fail-closed mode exits 2 | PreToolUse; verified and subprocess-tested |
| Generic | Consumer-defined | `{"action":"block","reason":...}` | Returns `ask` | Adapter errors fail open; fail-closed mode exits 2 | Bridge protocol for the untested plugin examples |
| [OpenClaw](https://docs.openclaw.ai/plugins/hooks/tool-policy) | Plugin-defined | Example maps to `{block:true,blockReason}` | Example blocks | Consumer-defined | `before_tool_call` example is **untested** |
| [Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks) | Python plugin or shell-hook configuration | Example maps to `{"action":"block","message":...}` | Example blocks | Consumer-defined | `pre_tool_call` example is **untested** |
| [OpenCode](https://opencode.ai/docs/plugins/) | JS/TS plugin | Example throws `Error` | Example throws | Consumer-defined | `tool.execute.before` example is **untested** |

## Input and normalization

The adapters accept these documented envelopes:

- Claude and Codex: `{"tool_name": name, "tool_input": {...}}`.
- Cursor: `tool_name`/`toolName`, `tool_input`/`toolInput`/`input`, or a
  `beforeShellExecution` payload with top-level `command` and optional `cwd`.
- Copilot native: `{"toolName": name, "toolArgs": {...}}`; PascalCase
  `PreToolUse` also accepts the Claude-compatible envelope.
- Gemini: `{"tool_name": name, "tool_input": {...}}`.
- Grok: `{"toolName": name, "toolInput": {...}}`.
- Generic: `{"tool": name, "args": {...}}`.

Shell aliases normalize to `Bash` with `command`; file reads to `Read` with
`file_path`; writes to `Write`; edits to `Edit`; patches to `apply_patch` with
`command` or `input`; and web fetches to `WebFetch` with `url`. MCP names are
left unchanged. When normalization changes a tool name, deny/approval reasons
include the original name. A bare relative filename such as `.env` is checked
as the equivalent `./.env` so path-segment rules apply.

Cursor's alternative field spellings are intentionally permissive because the
exact spelling can vary by event/version. Verify them against the current
Cursor documentation when installing. Codex ask responses are treated as deny
because interactive ask support was not verified for this adapter.

## Policy and state

The hook uses built-in rules, enabled local rule packs, and learned signatures
through the existing `Warden`. `WARDEN_RULEPACKS` retains its current behavior
and defaults. `WARDEN_STATE_DIR` defaults to `~/.agent-warden`; set it to share
or isolate hook state. `WARDEN_NODE_NAME` overrides the generated
`<harness>@<hostname>` node name.

Malformed input, import failures, state errors, and other internal failures
emit one warning line on stderr and exit 0. Set
`AGENT_WARDEN_FAIL_CLOSED=1` to deny instead (exit 2). This environment setting
controls failures inside Wagent; harness-level timeout and crash behavior
still follows the host's own contract.

## Security boundary

A pre-tool hook is **not a complete security boundary**. It only sees the tool
calls the harness exposes, and a disabled, bypassed, timed-out, or uncovered
tool can escape it. Combine Wagent with native permissions, sandboxing,
network limits, and scoped credentials.

The OpenClaw, Hermes, and OpenCode files under
[`examples/plugins/`](examples/plugins/) are small, explicitly **untested**
starting points. They shell out to the generic adapter and must be validated
against the installed plugin API before use.
