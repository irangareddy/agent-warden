"""Normal tool calls a new rule must never block.

The warden tests every rule it proposes against these before adopting it.
Add real calls from your own runs to make the check stricter.
"""

import json


def _fc(name: str, **args) -> dict:
    return {"type": "function_call", "name": name, "arguments": json.dumps(args)}


KNOWN_GOOD = [
    _fc("read_file", path="/data/supernode-a/patient_data.csv"),
    _fc("read_file", path="/data/supernode-b/patient_data.csv"),
    _fc("read_file", path="/data/supernode-c/patient_data.md"),
    _fc("read_file", path="/data/supernode-d/patient_data.txt"),
    _fc("list_directory", path="/data/supernode-a"),
    _fc("list_directory", path="/data"),
    _fc("read_file", path="/opt/flwr/app/README.md"),
    _fc("read_file", path="/opt/flwr/app/config.toml"),
    _fc("read_file", path="/tmp/agent-warden/decisions.jsonl"),
    # Beet fleet demo nodes
    _fc("read_file", path="/data/ios/EventsView.swift"),
    _fc("read_file", path="/data/ios/TODO.md"),
    _fc("read_file", path="/data/backend/orders.ts"),
    _fc("read_file", path="/data/qa/test_report.md"),
    _fc("read_file", path="/data/release/CHANGELOG.md"),
    _fc("list_directory", path="/data/backend"),
    # Real Flower Grid tools
    _fc("get_nodes", sample_size=None),
    _fc("push_messages", messages=[{"dst_node_id": "4172973173130116852",
        "payload": "List your files and give a one-line status.", "reply_to_message_id": None}]),
    _fc("pull_messages", message_ids=["m-1", "m-2"], timeout=60),
    _fc("push_reply_message", payload="Backend: 3 files, order flow OK, no failing tests."),
    _fc("push_reply_message", payload="Site A: 41 cardiology patients over 70; mean age 76.2"),
]
