"""Exercise approval-tier decisions across Warden, hook, and AgentApp guard."""

import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="approval-state-")
os.environ["WARDEN_RULEPACKS"] = "publishing"

from agent.warden import Warden  # noqa: E402


def call(command: str) -> dict[str, str]:
    return {
        "type": "function_call",
        "name": "Bash",
        "call_id": "approval-test",
        "arguments": json.dumps({"command": command}),
    }


warden = Warden("approval-test")

ask = warden.check(call("gh pr merge 42 --squash"))
assert ask.action == "ask"
assert ask.rule_id == "beet-approval-pr-merge"
print("PASS ask rule returns action ask")

explicit_nonproduction = warden.check(call("gh pr merge 42 --squash --base develop"))
assert explicit_nonproduction.allowed
assert explicit_nonproduction.action == "allow"

overlap = warden.check(call("npm publish"))
assert not overlap.allowed
assert overlap.action == "block"
assert overlap.rule_id == "beet-publishing-npm"
print("PASS block rule wins over matching ask rule")

hook_env = os.environ.copy()
hook_env["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="approval-hook-")
hook_env["WARDEN_RULEPACKS"] = "publishing"
hook_result = subprocess.run(
    [sys.executable, str(ROOT / "hooks" / "claude_code_pretooluse.py")],
    input=json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 42 --squash"},
    }),
    text=True,
    capture_output=True,
    cwd=ROOT,
    env=hook_env,
    check=False,
)
assert hook_result.returncode == 0
assert hook_result.stderr == ""
assert json.loads(hook_result.stdout) == {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": ask.reason,
    }
}
print("PASS hook prints ask JSON and exits 0")


# The direct test runner intentionally has no Flower dependency installed. Stub
# only the imported SDK types so the AgentApp guard itself can be exercised.
flwr = types.ModuleType("flwr")
flwr_agentapp = types.ModuleType("flwr.agentapp")
flwr_app = types.ModuleType("flwr.app")


class AgentApp:
    def main(self):
        return lambda function: function


flwr_agentapp.AgentApp = AgentApp
flwr_agentapp.AgentSession = object
flwr_app.Context = object
flwr.agentapp = flwr_agentapp
flwr.app = flwr_app
sys.modules.setdefault("flwr", flwr)
sys.modules.setdefault("flwr.agentapp", flwr_agentapp)
sys.modules.setdefault("flwr.app", flwr_app)

openai = types.ModuleType("openai")
openai.OpenAI = object
sys.modules.setdefault("openai", openai)

from agent.agent_app import _guarded_call  # noqa: E402


class NeverCalled:
    def call(self, item):
        raise AssertionError(f"approval-required call was executed: {item}")


class Events:
    def __init__(self) -> None:
        self.items = []

    def emit(self, item) -> None:
        self.items.append(item)


class FakeAgent:
    def __init__(self) -> None:
        self.connectors = NeverCalled()
        self.grid = NeverCalled()
        self.events = Events()


agent = FakeAgent()
new_rules = []
outcome = _guarded_call(
    agent,
    call("gh release create v1.2.3"),
    warden,
    {"Bash"},
    new_rules,
    [],
)
assert outcome.decision.action == "ask"
assert outcome.signature is None
assert outcome.output["output"].endswith("This action was not executed.")
assert new_rules == []
assert agent.events.items == [{
    "type": "response.output_text.delta",
    "delta": "\n⏸ Needs human approval: Creating a GitHub release needs human confirmation.\n",
}]
print("PASS AgentApp treats ask as not executed and evolves no rule")
