"""Decision rendering shared by harness adapters."""

from __future__ import annotations

import json
from typing import Any

from .base import CanonicalCall, HookResponse


def json_line(value: dict[str, Any]) -> str:
    return json.dumps(value) + "\n"


def reason(call: CanonicalCall, decision: Any, *, detailed: bool) -> str:
    base = decision.reason or "Denied by Wagent"
    if detailed:
        label = call.original_name
        if call.original_name != call.name:
            label = f"{call.original_name} as {call.name}"
        base = (
            f"Wagent blocked {label} ({decision.family}): {base} "
            f"[rule {decision.rule_id}, from {decision.source}]"
        )
    elif call.original_name != call.name:
        base = f"{base} (original tool: {call.original_name}; normalized to {call.name})"
    return base


def deny_reason(call: CanonicalCall, decision: Any) -> str:
    rendered = reason(call, decision, detailed=decision.action == "block")
    if decision.action == "ask":
        return f"Needs human approval: {rendered}"
    return rendered


def exit_two(message: str) -> HookResponse:
    return HookResponse(exit_code=2, stderr=message + "\n")
