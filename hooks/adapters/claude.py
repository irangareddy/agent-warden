"""Claude Code PreToolUse adapter."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall, HookResponse, require_name, require_object
from .normalize import normalize_call
from .render import exit_two, json_line, reason


class ClaudeAdapter:
    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        name = require_name(payload.get("tool_name"), "tool_name")
        arguments = require_object(payload.get("tool_input"), "tool_input")
        return normalize_call(name, arguments)

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        if decision.action == "allow":
            return HookResponse()
        if decision.action == "ask":
            return HookResponse(stdout=json_line({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason(call, decision, detailed=False),
                }
            }))
        return exit_two(reason(call, decision, detailed=True))


ADAPTER = ClaudeAdapter()
