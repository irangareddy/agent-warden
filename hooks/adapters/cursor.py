"""Cursor preToolUse and beforeShellExecution adapter."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall, HookResponse, first, require_name, require_object
from .normalize import normalize_call
from .render import deny_reason, json_line


class CursorAdapter:
    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        name_value = first(payload, "tool_name", "toolName", "tool")
        arguments_value = first(payload, "tool_input", "toolInput", "input")

        # beforeShellExecution supplies a top-level command/cwd rather than a
        # preToolUse tool envelope.
        if name_value is None and isinstance(payload.get("command"), str):
            name_value = "Shell"
            arguments_value = {
                key: payload[key]
                for key in ("command", "cwd")
                if key in payload
            }

        name = require_name(name_value, "tool name")
        arguments = require_object(arguments_value, "tool input")
        return normalize_call(name, arguments)

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        if decision.action == "allow":
            return HookResponse()
        rendered = deny_reason(call, decision)
        return HookResponse(stdout=json_line({
            "permission": "deny",
            "agent_message": rendered,
            "user_message": rendered,
        }))


ADAPTER = CursorAdapter()
