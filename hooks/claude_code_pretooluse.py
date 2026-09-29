#!/usr/bin/env python3
"""Claude Code PreToolUse adapter for Agent Warden."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import NoReturn


def _stop_on_error() -> bool:
    return os.environ.get("AGENT_WARDEN_FAIL_CLOSED") == "1"


def _internal_error(error: BaseException) -> NoReturn:
    detail = " ".join(str(error).split()) or error.__class__.__name__
    print(f"Agent Warden warning: hook error ({detail}); failing "
          f"{'closed' if _stop_on_error() else 'open'}", file=sys.stderr)
    raise SystemExit(2 if _stop_on_error() else 0)


def main() -> int:
    try:
        repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo_root))

        # agent.warden reads this setting when it is imported, so establish the
        # local user default first. An explicitly configured directory wins.
        os.environ.setdefault("WARDEN_STATE_DIR", str(Path.home() / ".agent-warden"))

        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")

        tool_name = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("missing or invalid tool_name")
        if not isinstance(tool_input, dict):
            raise ValueError("missing or invalid tool_input")

        from agent.warden import Warden

        node_name = os.environ.get("WARDEN_NODE_NAME") or f"claude-code@{socket.gethostname()}"
        item = {
            "type": "function_call",
            "name": tool_name,
            "arguments": json.dumps(tool_input),
        }
        decision = Warden(node_name).check(item)
        if decision.action == "ask":
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": decision.reason,
                }
            }))
            return 0

        if decision.allowed:
            return 0

        print(
            f"Agent Warden blocked {tool_name} ({decision.family}): "
            f"{decision.reason} [rule {decision.rule_id}, from {decision.source}]",
            file=sys.stderr,
        )
        return 2
    except BaseException as error:
        _internal_error(error)


if __name__ == "__main__":
    raise SystemExit(main())
