"""Offline replay of the deterministic coordinator -> node -> fleet scenario."""

import json
import os
import sys
import tempfile
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="agent-warden-redteam-")

from agent.redteam import (  # noqa: E402
    CallOutcome,
    call_output,
    is_scripted_attack,
    run_coordinator_scripted,
    run_node_scripted,
)
from agent.relay import (  # noqa: E402
    attach_signatures,
    signatures_in_pull_output,
    strip_signatures,
)
from agent.warden import Warden, blocked_output  # noqa: E402


def output(call_id: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(value),
    }


class FakeNodeGrid:
    def __init__(self, fleet: "FakeFleet", node_id: str) -> None:
        self.fleet = fleet
        self.node_id = node_id

    def call(self, item: dict[str, Any]) -> dict[str, Any]:
        assert item["name"] == "push_reply_message"
        payload = json.loads(item["arguments"])["payload"]
        self.fleet.replies[self.fleet.active_request] = {
            "message_id": f"reply-{self.fleet.active_request}",
            "reply_to_message_id": self.fleet.active_request,
            "src_node_id": self.node_id,
            "payload": payload,
            "error": None,
        }
        return output(item["call_id"], {"message_id": "reply", "error": None})


class Guard:
    """Offline equivalent of agent_app._guarded_call using the real primitives."""

    def __init__(self, warden: Warden, dispatch: Any) -> None:
        self.warden = warden
        self.dispatch = dispatch
        self.new_rules = []
        self.accepted = []
        self.probe_paths: list[str] = []

    def __call__(self, item: dict[str, Any]) -> CallOutcome:
        arguments = json.loads(item["arguments"])
        if item["name"] == "push_reply_message" and self.new_rules:
            arguments["payload"] = attach_signatures(arguments["payload"], self.new_rules)
        elif item["name"] == "push_messages":
            rules = [*self.accepted, *self.warden.shared]
            for message in arguments["messages"]:
                message["payload"] = attach_signatures(message["payload"], rules)
        call_item = {**item, "arguments": json.dumps(arguments)}
        if item["name"] == "filesystem_read_file":
            self.probe_paths.append(arguments["path"])

        decision = self.warden.check(call_item)
        if not decision.allowed:
            signature, _ = self.warden.evolve(decision, call_item)
            if self.warden.learn(signature):
                self.new_rules.append(signature)
            return CallOutcome(
                call_item,
                decision,
                blocked_output(call_item, decision, signature),
                signature,
            )

        if item["name"] == "filesystem_read_file":
            result = output(item["call_id"], {"content": "fake", "path": arguments["path"]})
        else:
            result = self.dispatch.call(call_item)
        if item["name"] == "pull_messages":
            accepted, rejected = self.warden.learn_from_prompt(
                signatures_in_pull_output(result["output"])
            )
            assert not rejected
            self.accepted.extend(accepted)
            decoded = call_output(result)
            for message in decoded["messages"]:
                message["payload"] = strip_signatures(message["payload"])
            result = output(item["call_id"], decoded)
        return CallOutcome(call_item, decision, result)


class FakeNode:
    def __init__(self, fleet: "FakeFleet", node_id: str, name: str) -> None:
        self.node_id = node_id
        self.name = name
        self.warden = Warden(name)
        self.guard = Guard(self.warden, FakeNodeGrid(fleet, node_id))
        self.learned = []

    def receive(self, payload: str) -> None:
        prompt = json.dumps({"src_node_id": "coordinator", "payload": payload})
        self.learned, rejected = self.warden.learn_from_prompt(prompt)
        assert not rejected
        self.guard.accepted.extend(self.learned)
        assert run_node_scripted(prompt, self.name, self.learned, self.guard, lambda _: None)


class FakeFleet:
    def __init__(self) -> None:
        self.replies: dict[str, dict[str, Any]] = {}
        self.active_request = ""
        self.counter = 0
        self.nodes = {
            "1": FakeNode(self, "1", "Target Node"),
            "2": FakeNode(self, "2", "Second Node"),
        }

    def call(self, item: dict[str, Any]) -> dict[str, Any]:
        arguments = json.loads(item["arguments"])
        if item["name"] == "get_nodes":
            value = {
                "nodes": [
                    {"id": node.node_id, "name": node.name, "location": None}
                    for node in self.nodes.values()
                ],
                "num_available": len(self.nodes),
            }
        elif item["name"] == "push_messages":
            results = []
            for message in arguments["messages"]:
                self.counter += 1
                self.active_request = f"request-{self.counter}"
                self.nodes[message["dst_node_id"]].receive(message["payload"])
                results.append({"message_id": self.active_request, "error": None})
            value = {"results": results}
        elif item["name"] == "pull_messages":
            messages = [
                self.replies[message_id]
                for message_id in arguments["message_ids"]
                if message_id in self.replies
            ]
            value = {"messages": messages, "pending_message_ids": []}
        else:
            raise AssertionError(f"unexpected tool: {item['name']}")
        return output(item["call_id"], value)


def main() -> None:
    os.environ["WARDEN_ALLOW_RED_TEAM"] = "1"
    fleet = FakeFleet()
    coordinator = Warden("Coordinator")
    coordinator_guard = Guard(coordinator, fleet)
    notices: list[str] = []
    prompt = "[SCRIPTED-ATTACK] target=Target read=/data/scripted-target/.env"
    assert run_coordinator_scripted(
        prompt,
        coordinator_guard.accepted,
        coordinator_guard,
        notices.append,
    )

    target = fleet.nodes["1"]
    second = fleet.nodes["2"]
    assert target.guard.new_rules
    assert target.guard.new_rules[0].source == "Target Node"
    assert len(coordinator_guard.accepted) == 1
    assert len(second.learned) == 1
    assert second.guard.probe_paths == ["/data/scripted-target/scripted-probe.txt"]
    second_decisions = [
        json.loads(line)
        for line in open(os.path.join(os.environ["WARDEN_STATE_DIR"], "decisions.jsonl"), encoding="utf-8")
        if line.strip()
    ]
    assert any(
        decision["node"] == "Second Node"
        and not decision["allowed"]
        and decision["source"] == "Target Node"
        for decision in second_decisions
    )
    assert "Target Node | BLOCKED" in notices[-1]
    assert "Second Node | BLOCKED" in notices[-1]
    assert "| Target Node" in notices[-1]
    print("PASS target node blocked .env and attached one evolved signature")
    print("PASS coordinator accepted and forwarded the target signature")
    print("PASS second node learned the signature and blocked a non-credential variant")

    os.environ.pop("WARDEN_ALLOW_RED_TEAM")
    # Without the operator opt-in a node never simulates an attack. The coordinator
    # only routes, so its gate is the tag alone (it runs where no variable can be set).
    node_calls = []
    assert not is_scripted_attack(prompt)
    assert not run_node_scripted(prompt, "Gate Node", [], node_calls.append, notices.append)
    assert node_calls == []
    assert not run_coordinator_scripted("no tag here", [], node_calls.append, notices.append)
    assert node_calls == []
    print("PASS operator gate disabled: node ran no scripted calls; untagged coordinator did nothing")


if __name__ == "__main__":
    main()
