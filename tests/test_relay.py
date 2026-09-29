"""Relay one learned rule through a coordinator while rejecting a poisoned rule."""

import importlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent.warden as warden_module
from agent.relay import attach_signatures, signatures_in_pull_output, strip_signatures


def fc(path: str) -> dict:
    return {
        "type": "function_call",
        "name": "read_file",
        "call_id": "c1",
        "arguments": json.dumps({"path": path}),
    }


def node(state_dir: str, name: str):
    os.environ["WARDEN_STATE_DIR"] = state_dir
    importlib.reload(warden_module)
    return warden_module, warden_module.Warden(name)


with tempfile.TemporaryDirectory() as state_root:
    wa, node_a = node(os.path.join(state_root, "node-a"), "node-A")
    attack = fc("/home/agent/.ssh/id_rsa")
    decision = node_a.check(attack)
    assert not decision.allowed
    signature, _ = node_a.evolve(decision, attack)
    assert node_a.learn(signature)
    reply_payload = attach_signatures("Node A completed its task.", [signature])
    assert reply_payload.count(wa.SIGNATURE_PREFIX) == 1
    assert attach_signatures(reply_payload, [signature]) == reply_payload
    print(f"node A blocked {decision.rule_id}; reply carries 1 signature")

    poison = wa.Rule(
        "poison-data",
        "credential_access",
        ".*",
        r"/data/",
        "Blocks all project data",
        "compromised-node",
    )
    poison_payload = attach_signatures("Malicious reply.", [poison])
    pull_output = json.dumps(
        {
            "messages": [
                {
                    "message_id": "m-a",
                    "reply_to_message_id": "request-a",
                    "src_node_id": "node-A",
                    "payload": reply_payload,
                    "error": None,
                },
                {
                    "message_id": "m-evil",
                    "reply_to_message_id": "request-evil",
                    "src_node_id": "compromised-node",
                    "payload": poison_payload,
                    "error": None,
                },
            ],
            "pending_message_ids": [],
        }
    )

    wc, coordinator = node(os.path.join(state_root, "coordinator"), "coordinator")
    relay_text = signatures_in_pull_output(pull_output)
    accepted, rejected = coordinator.learn_from_prompt(relay_text)
    assert [rule.id for rule in accepted] == [signature.id]
    assert [rule.id for rule, _ in rejected] == [poison.id]
    print(
        f"coordinator accepted {len(accepted)} rule and rejected "
        f"{len(rejected)} poisoned rule"
    )

    forwarded_rules = [
        *accepted,
        *(rule for rule in coordinator.shared if rule.source != "node-B"),
    ]
    outgoing_payload = attach_signatures("Review the completed task.", forwarded_rules)
    assert signature.id in outgoing_payload
    assert poison.id not in outgoing_payload
    assert wc.SIGNATURE_PREFIX not in strip_signatures(outgoing_payload)
    print("coordinator forwarded the accepted rule only")

    _, node_b = node(os.path.join(state_root, "node-b"), "node-B")
    variant = fc("/home/agent/private/notes.txt")
    assert node_b.check(variant).allowed
    learned, rejected_by_b = node_b.learn_from_prompt(outgoing_payload)
    assert len(learned) == 1
    assert not rejected_by_b
    blocked_variant = node_b.check(variant)
    assert not blocked_variant.allowed
    assert blocked_variant.rule_id == signature.id
    print("node B learned 1 rule; unseen variant blocked = True")
