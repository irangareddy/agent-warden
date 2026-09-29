"""GitHub Copilot native preToolUse and compatible PreToolUse adapter."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall, HookResponse, require_name, require_object
from .normalize import normalize_call
from .render import deny_reason, exit_two


class CopilotAdapter:
    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        if "toolName" in payload or "toolArgs" in payload:
            name = require_name(payload.get("toolName"), "toolName")
            arguments = require_object(payload.get("toolArgs"), "toolArgs")
        else:
            name = require_name(payload.get("tool_name"), "tool_name")
            arguments = require_object(payload.get("tool_input"), "tool_input")
        return normalize_call(name, arguments)

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        if decision.action == "allow":
            return HookResponse()
        return exit_two(deny_reason(call, decision))


ADAPTER = CopilotAdapter()
