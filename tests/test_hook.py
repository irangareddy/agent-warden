"""Exercise the Claude Code PreToolUse hook as a subprocess."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "claude_code_pretooluse.py"


def invoke(raw_input: str, state_dir: str, fail_closed: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WARDEN_STATE_DIR"] = state_dir
    env["WARDEN_NODE_NAME"] = "hook-test"
    if fail_closed:
        env["AGENT_WARDEN_FAIL_CLOSED"] = "1"
    else:
        env.pop("AGENT_WARDEN_FAIL_CLOSED", None)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw_input,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        check=False,
    )


CASES = [
    (
        "Bash blocks .env",
        {"tool_name": "Bash", "tool_input": {"command": "cat backend/.env"}},
        2,
        "Agent Warden blocked Bash (credential_access): Touches keys or credentials "
        "[rule cred-keys, from built-in]",
        False,
    ),
    (
        "Read blocks SSH key",
        {"tool_name": "Read", "tool_input": {"file_path": "/Users/dev/.ssh/id_ed25519"}},
        2,
        "Agent Warden blocked Read (credential_access): Touches keys or credentials "
        "[rule cred-keys, from built-in]",
        False,
    ),
    (
        "Bash allows git status",
        {"tool_name": "Bash", "tool_input": {"command": "git status"}},
        0,
        "",
        False,
    ),
    (
        "Read allows project source",
        {
            "tool_name": "Read",
            "tool_input": {"file_path": "/Users/dev/Beet/Sources/EventsView.swift"},
        },
        0,
        "",
        False,
    ),
    ("Malformed input fails open", None, 0, "Agent Warden warning:", False),
    ("Malformed input fails closed", None, 2, "Agent Warden warning:", True),
]


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory(prefix="agent-warden-hook-") as state_dir:
        for name, payload, expected_code, expected_stderr, fail_closed in CASES:
            raw_input = json.dumps(payload) if payload is not None else "{not valid json\n"
            result = invoke(raw_input, state_dir, fail_closed)
            stderr = result.stderr.strip()
            code_ok = result.returncode == expected_code
            stderr_ok = stderr == expected_stderr if not expected_stderr.startswith(
                "Agent Warden warning:"
            ) else stderr.startswith(expected_stderr)
            stdout_ok = result.stdout == ""

            if code_ok and stderr_ok and stdout_ok:
                print(f"PASS {name}: exit {result.returncode}")
                continue

            failures.append(name)
            print(f"FAIL {name}: exit {result.returncode}, stderr={stderr!r}, stdout={result.stdout!r}")
            print(f"  expected: exit {expected_code}, stderr={expected_stderr!r}, stdout='' ")

    print(f"{len(CASES) - len(failures)}/{len(CASES)} hook cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
