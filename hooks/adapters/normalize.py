"""Normalize harness-specific tool names and arguments."""

from __future__ import annotations

from typing import Any

from .base import CanonicalCall


_ALIASES = {
    # Shell and unified execution tools.
    "bash": "Bash",
    "shell": "Bash",
    "exec": "Bash",
    "execute": "Bash",
    "terminal": "Bash",
    "powershell": "Bash",
    "run_shell_command": "Bash",
    "shelltool": "Bash",
    # Reads and search-like file inspection tools.
    "read": "Read",
    "view": "Read",
    "read_file": "Read",
    "list_directory": "Read",
    "grep": "Read",
    # Writes and edits.
    "write": "Write",
    "write_file": "Write",
    "edit": "Edit",
    "multiedit": "Edit",
    "multi_edit": "Edit",
    # Patches and web access.
    "apply_patch": "apply_patch",
    "patch": "apply_patch",
    "webfetch": "WebFetch",
    "web_fetch": "WebFetch",
}


def normalize_call(tool_name: str, tool_input: dict[str, Any]) -> CanonicalCall:
    """Return a canonical tool name and a JSON-safe argument mapping."""
    canonical = tool_name if _is_mcp(tool_name) else _ALIASES.get(tool_name.lower(), tool_name)
    arguments = dict(tool_input)

    if canonical == "Bash":
        _copy_first(arguments, "command", "cmd", "input")
    elif canonical in {"Read", "Write", "Edit"}:
        _copy_first(arguments, "file_path", "filePath", "path", "file")
        file_path = arguments.get("file_path")
        if isinstance(file_path, str) and "/" not in file_path and "\\" not in file_path:
            # The bundled path rules recognize path-segment boundaries. A bare
            # relative filename such as `.env` is semantically `./.env`.
            arguments["file_path"] = f"./{file_path}"
    elif canonical == "apply_patch":
        # Codex uses command; other integrations commonly use input or patch.
        if "command" not in arguments and "input" not in arguments:
            _copy_first(arguments, "input", "patch")
    elif canonical == "WebFetch":
        _copy_first(arguments, "url", "uri")

    return CanonicalCall(canonical, arguments, tool_name)


def _copy_first(arguments: dict[str, Any], target: str, *sources: str) -> None:
    if target in arguments:
        return
    for source in sources:
        if source in arguments:
            arguments[target] = arguments[source]
            return


def _is_mcp(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return lowered.startswith("mcp__") or lowered.startswith("mcp:")
