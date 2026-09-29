"""Subprocess matrix for all Wagent harness adapters (Python 3.12)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "warden_hook.py"


@dataclass(frozen=True)
class Harness:
    label: str
    name: str
    payload: Callable[[str, dict[str, Any]], dict[str, Any]]
    deny_kind: str


def snake(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"tool_name": tool, "tool_input": arguments}


def cursor(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"toolName": tool, "toolInput": arguments}


def copilot(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"toolName": tool, "toolArgs": arguments, "cwd": str(ROOT)}


def grok(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"toolName": tool, "toolInput": arguments}


def generic(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "args": arguments}


HARNESSES = [
    Harness("claude", "claude", snake, "exit2"),
    Harness("codex", "codex", snake, "hook_json"),
    Harness("cursor", "cursor", cursor, "cursor_json"),
    Harness("copilot native", "copilot", copilot, "exit2"),
    Harness("copilot compatible", "copilot", snake, "exit2"),
    Harness("gemini", "gemini", snake, "decision_json"),
    Harness("grok", "grok", grok, "decision_json"),
    Harness("generic", "generic", generic, "generic_json"),
]


TOOLS = {
    "claude": ("Read", {"file_path": ".env"}, "Bash"),
    "codex": ("Bash", {"command": "cat .env"}, "Bash"),
    "cursor": ("Read", {"path": ".env"}, "Shell"),
    "copilot native": ("view", {"path": ".env"}, "bash"),
    "copilot compatible": ("Read", {"file_path": ".env"}, "Bash"),
    "gemini": ("read_file", {"file_path": ".env"}, "run_shell_command"),
    "grok": ("Read", {"file_path": ".env"}, "Bash"),
    "generic": ("read_file", {"file_path": ".env"}, "shell"),
}


def invoke(
    harness: str,
    raw_input: str,
    state_dir: str,
    *,
    fail_closed: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WARDEN_STATE_DIR"] = state_dir
    env["WARDEN_NODE_NAME"] = "adapter-test"
    env["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing"
    if fail_closed:
        env["AGENT_WARDEN_FAIL_CLOSED"] = "1"
    else:
        env.pop("AGENT_WARDEN_FAIL_CLOSED", None)
    return subprocess.run(
        [sys.executable, str(HOOK), "--harness", harness],
        input=raw_input,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        check=False,
    )


def assert_denied(case: Harness, result: subprocess.CompletedProcess[str], phrase: str) -> None:
    if case.deny_kind == "exit2":
        assert result.returncode == 2, result
        assert phrase in result.stderr, result
        assert result.stdout == "", result
        return

    assert result.returncode == 0, result
    assert result.stderr == "", result
    body = json.loads(result.stdout)
    if case.deny_kind == "hook_json":
        output = body["hookSpecificOutput"]
        assert output["permissionDecision"] == "deny", body
        assert phrase in output["permissionDecisionReason"], body
    elif case.deny_kind == "cursor_json":
        assert body["permission"] == "deny", body
        assert phrase in body["agent_message"], body
        assert phrase in body["user_message"], body
    elif case.deny_kind == "decision_json":
        assert body["decision"] == "deny", body
        assert phrase in body["reason"], body
    else:
        assert body["action"] == "block", body
        assert phrase in body["reason"], body


def assert_allowed(case: Harness, result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result
    assert result.stderr == "", result
    if case.deny_kind == "generic_json":
        assert json.loads(result.stdout) == {"action": "allow", "reason": ""}, result
    else:
        assert result.stdout == "", result


def assert_approval(case: Harness, result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == (0 if case.deny_kind != "exit2" or case.name == "claude" else 2), result
    if case.name == "claude":
        body = json.loads(result.stdout)["hookSpecificOutput"]
        assert body["permissionDecision"] == "ask", body
        assert "human confirmation" in body["permissionDecisionReason"], body
        assert result.stderr == "", result
    elif case.deny_kind == "generic_json":
        body = json.loads(result.stdout)
        assert body["action"] == "ask", body
        assert "human confirmation" in body["reason"], body
        assert result.stderr == "", result
    elif case.deny_kind == "exit2":
        assert "Needs human approval:" in result.stderr, result
        assert result.stdout == "", result
    else:
        body = json.loads(result.stdout)
        rendered = (
            body["hookSpecificOutput"]["permissionDecisionReason"]
            if case.deny_kind == "hook_json"
            else body["agent_message"]
            if case.deny_kind == "cursor_json"
            else body["reason"]
        )
        assert "Needs human approval:" in rendered, body


def run_case(label: str, check: Callable[[], None], failures: list[str]) -> None:
    try:
        check()
    except (AssertionError, json.JSONDecodeError, KeyError) as error:
        failures.append(label)
        print(f"FAIL {label}: {error}")
    else:
        print(f"PASS {label}")


def main() -> int:
    failures: list[str] = []
    total = 0
    with tempfile.TemporaryDirectory(prefix="agent-warden-adapters-") as state_dir:
        for case in HARNESSES:
            read_tool, read_args, shell_tool = TOOLS[case.label]

            total += 1
            run_case(
                f"{case.label}: .env access denied",
                lambda case=case, read_tool=read_tool, read_args=read_args: assert_denied(
                    case,
                    invoke(case.name, json.dumps(case.payload(read_tool, read_args)), state_dir),
                    "Wagent",
                ),
                failures,
            )

            total += 1
            run_case(
                f"{case.label}: git status allowed",
                lambda case=case, shell_tool=shell_tool: assert_allowed(
                    case,
                    invoke(
                        case.name,
                        json.dumps(case.payload(shell_tool, {"command": "git status"})),
                        state_dir,
                    ),
                ),
                failures,
            )

            total += 1
            run_case(
                f"{case.label}: PR merge approval",
                lambda case=case, shell_tool=shell_tool: assert_approval(
                    case,
                    invoke(
                        case.name,
                        json.dumps(case.payload(
                            shell_tool,
                            {"command": "gh pr merge 42 --squash"},
                        )),
                        state_dir,
                    ),
                ),
                failures,
            )

            total += 1
            run_case(
                f"{case.label}: malformed input fails open",
                lambda case=case: _assert_malformed(
                    invoke(case.name, "{not valid json\n", state_dir),
                    expected_code=0,
                    disposition="open",
                ),
                failures,
            )

            total += 1
            run_case(
                f"{case.label}: malformed input fails closed",
                lambda case=case: _assert_malformed(
                    invoke(case.name, "{not valid json\n", state_dir, fail_closed=True),
                    expected_code=2,
                    disposition="closed",
                ),
                failures,
            )

        total += 1
        run_case(
            "cursor: beforeShellExecution payload denied",
            lambda: assert_denied(
                HARNESSES[2],
                invoke(
                    "cursor",
                    json.dumps({"command": "cat .env", "cwd": str(ROOT)}),
                    state_dir,
                ),
                "Wagent",
            ),
            failures,
        )

    print(f"{total - len(failures)}/{total} adapter cases passed")
    return 1 if failures else 0


def _assert_malformed(
    result: subprocess.CompletedProcess[str],
    *,
    expected_code: int,
    disposition: str,
) -> None:
    assert result.returncode == expected_code, result
    assert result.stdout == "", result
    assert result.stderr.startswith("Wagent warning:"), result
    assert f"failing {disposition}" in result.stderr, result
    assert len(result.stderr.strip().splitlines()) == 1, result


if __name__ == "__main__":
    raise SystemExit(main())
