"""Per-harness adapters for the shared Agent Warden hook."""

from .claude import ADAPTER as CLAUDE
from .codex import ADAPTER as CODEX
from .copilot import ADAPTER as COPILOT
from .cursor import ADAPTER as CURSOR
from .gemini import ADAPTER as GEMINI
from .generic import ADAPTER as GENERIC
from .grok import ADAPTER as GROK


ADAPTERS = {
    "claude": CLAUDE,
    "codex": CODEX,
    "cursor": CURSOR,
    "copilot": COPILOT,
    "gemini": GEMINI,
    "grok": GROK,
    "generic": GENERIC,
}

__all__ = ["ADAPTERS"]
