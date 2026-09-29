"""Grok PreToolUse adapter."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall, HookResponse, require_name, require_object
from .normalize import normalize_call
from .render import deny_reason, json_line


class GrokAdapter:
    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        name = require_name(payload.get("toolName"), "toolName")
        arguments = require_object(payload.get("toolInput"), "toolInput")
        return normalize_call(name, arguments)

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        if decision.action == "allow":
            return HookResponse()
        return HookResponse(stdout=json_line({
            "decision": "deny",
            "reason": deny_reason(call, decision),
        }))


ADAPTER = GrokAdapter()
