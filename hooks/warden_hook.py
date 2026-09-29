#!/usr/bin/env python3
"""Run Agent Warden as a pre-tool hook for supported coding-agent harnesses."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Sequence


def _fail_closed() -> bool:
    return os.environ.get("AGENT_WARDEN_FAIL_CLOSED") == "1"


def _warning(error: BaseException) -> str:
    detail = " ".join(str(error).split()) or error.__class__.__name__
    return (
        f"Agent Warden warning: hook error ({detail}); failing "
        f"{'closed' if _fail_closed() else 'open'}"
    )


def run(harness: str) -> int:
    try:
        repo_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo_root))
        from agent.config import load_project_config

        load_project_config()
        os.environ.setdefault("WARDEN_STATE_DIR", str(Path.home() / ".agent-warden"))

        from hooks.adapters import ADAPTERS

        adapter = ADAPTERS[harness]
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        call = adapter.parse(payload)

        # Import after WARDEN_STATE_DIR is established because agent.warden
        # reads it at import time.
        from agent.warden import Warden

        node_name = os.environ.get("WARDEN_NODE_NAME") or f"{harness}@{socket.gethostname()}"
        item = {
            "type": "function_call",
            "name": call.name,
            "arguments": json.dumps(call.arguments),
        }
        response = adapter.respond(call, Warden(node_name).check(item))
        if response.stdout:
            sys.stdout.write(response.stdout)
        if response.stderr:
            sys.stderr.write(response.stderr)
        return response.exit_code
    except BaseException as error:
        print(_warning(error), file=sys.stderr)
        return 2 if _fail_closed() else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", required=True, choices=(
        "claude", "codex", "cursor", "copilot", "gemini", "grok", "generic"
    ))
    args = parser.parse_args(argv)
    return run(args.harness)


if __name__ == "__main__":
    raise SystemExit(main())
