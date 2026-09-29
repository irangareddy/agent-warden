# Claude Code hook

`claude_code_pretooluse.py` adapts Claude Code `PreToolUse` events to Agent
Warden checks. It has three outcomes:

- `allow`: exit 0 without output, so Claude Code runs the requested tool.
- `block`: exit 2 with the reason on standard error, so Claude Code does not run it.
- `ask`: exit 0 with a `hookSpecificOutput` JSON response requesting human approval.

The `ask` JSON format should be checked against the current Claude Code hooks
documentation when installing or upgrading the hook.

## Install

1. Clone or otherwise keep this repository at a stable absolute path.
2. Copy the `hooks.PreToolUse` entry from
   [`claude-settings.example.json`](claude-settings.example.json) into the
   Claude Code settings file you want to use.
3. Replace `/ABSOLUTE/PATH/TO/agent-warden` with this repository's absolute
   path. Keep the `matcher` as `"*"` to check every tool.
4. Restart Claude Code so it reloads the settings.

The example invokes the script with `python3`, so executable permissions are
not required. The hook imports Agent Warden directly from this repository and
has no third-party runtime dependencies.

By default, decisions and learned signatures are stored in
`~/.agent-warden`. Set `WARDEN_STATE_DIR` in Claude Code's environment to use a
different shared state directory. Set `WARDEN_NODE_NAME` to give this client a
stable fleet name; otherwise it uses `claude-code@<hostname>`.

## Rules

The hook uses local built-in rules, enabled local rule packs, and local learned
signatures loaded through `Warden`. Set `WARDEN_RULEPACKS` to a comma-separated
list such as `secrets,git-safety,publishing` to choose the local packs. It does
not yet synchronize rules from a Flower fleet.

## Failure behavior

The hook fails open: malformed input, import failures, state-directory errors,
or other internal problems produce a one-line warning on standard error and
exit 0. This prevents a broken hook from disabling every Claude Code tool.

For environments that require blocking on hook failures, set
`AGENT_WARDEN_FAIL_CLOSED=1`; internal errors then exit 2 instead.

## Uninstall

Remove the corresponding entry from `hooks.PreToolUse` in your Claude Code
settings and restart Claude Code. The optional `~/.agent-warden` state
directory is not removed automatically.
