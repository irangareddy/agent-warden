"""UNTESTED Hermes pre_tool_call plugin example.

Verify against https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
"""

import json
import os
import subprocess


HOOK = os.environ.get(
    "WARDEN_HOOK_PATH",
    "/ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py",
)


def warden_pre_tool_call(tool_name: str, args: dict, **_kwargs):
    child = subprocess.run(
        ["python3", HOOK, "--harness", "generic"],
        input=json.dumps({"tool": tool_name, "args": args}),
        text=True,
        capture_output=True,
        check=False,
    )
    if child.returncode:
        return {"action": "block", "message": child.stderr.strip() or "Wagent hook failed closed"}
    result = json.loads(child.stdout)
    if result["action"] != "allow":
        return {"action": "block", "message": result["reason"] or "Wagent requires approval"}
    return {}


def register(ctx):
    ctx.register_hook("pre_tool_call", warden_pre_tool_call)
