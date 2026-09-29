"""Shared types and helpers for Wagent hook adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class CanonicalCall:
    """A harness tool call normalized for ``Warden.check``."""

    name: str
    arguments: dict[str, Any]
    original_name: str


@dataclass(frozen=True)
class HookResponse:
    """Process output produced for one harness decision."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


class Adapter(Protocol):
    """Contract implemented by each harness adapter."""

    def parse(self, payload: dict[str, Any]) -> CanonicalCall:
        """Parse and normalize one harness payload."""

    def respond(self, call: CanonicalCall, decision: Any) -> HookResponse:
        """Convert a Warden decision to the harness response contract."""


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"missing or invalid {label}")
    return value


def require_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing or invalid {label}")
    return value


def first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None
