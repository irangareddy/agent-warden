"""Codex PreToolUse adapter."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall, HookResponse, require_name, require_object
from .normalize import normalize_call
from .render import deny_reason, json_line


class CodexAdapter:
    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        name = require_name(payload.get("tool_name"), "tool_name")
        arguments = require_object(payload.get("tool_input"), "tool_input")
        return normalize_call(name, arguments)

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        if decision.action == "allow":
            return HookResponse()
        return HookResponse(stdout=json_line({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_reason(call, decision),
            }
        }))


ADAPTER = CodexAdapter()
