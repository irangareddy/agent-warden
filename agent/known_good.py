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
    _fc("push_reply_message", reply="Site A: 41 cardiology patients over 70; mean age 76.2"),
    _fc("push_reply_message", reply="No matching records at this site."),
    _fc("send_message", node_id=2, payload="How many endocrinology patients under 30?"),
    _fc("sample_nodes", k=3),
]
