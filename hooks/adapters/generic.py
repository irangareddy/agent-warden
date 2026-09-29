"""Generic JSON-in/JSON-out adapter for example plugins."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall, HookResponse, require_name, require_object
from .normalize import normalize_call
from .render import json_line, reason


class GenericAdapter:
    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        name = require_name(payload.get("tool"), "tool")
        arguments = require_object(payload.get("args"), "args")
        return normalize_call(name, arguments)

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        rendered = ""
        if decision.action == "block":
            rendered = reason(call, decision, detailed=True)
        elif decision.action == "ask":
            rendered = reason(call, decision, detailed=False)
        return HookResponse(stdout=json_line({
            "action": decision.action,
            "reason": rendered,
        }))


ADAPTER = GenericAdapter()
