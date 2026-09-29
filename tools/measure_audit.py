"""Replay a private audit file of real agent tool calls through the warden.

The audit file stays outside the repo; only aggregate numbers are printed.

    python3.12 tools/measure_audit.py ../beet-warden-tool-calls.json
"""

import collections
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("WARDEN_STATE_DIR", tempfile.mkdtemp())
from agent.warden import Warden  # noqa: E402

calls = json.load(open(sys.argv[1], encoding="utf-8"))
warden = Warden("audit-replay")
stats = collections.defaultdict(lambda: collections.Counter(blocked=0, asked=0, allowed=0))
misses = []
for call in calls:
    item = {"type": "function_call", "name": call["tool"], "arguments": json.dumps(call["arguments"])}
    decision = warden.check(item)
    outcome = "allowed" if decision.action == "allow" else f"{decision.action}ed"
    want_block = call["label"] in {"risky", "variant"}
    stats[call["label"]][outcome] += 1
    caught = decision.action != "allow"
    if caught != want_block:
        misses.append(f"{call['id']:<5} {call['label']:<8} {call['family']:<19} {outcome}")
for label, counts in stats.items():
    print(
        f"{label:<8} blocked {counts['blocked']}, "
        f"asked {counts['asked']}, allowed {counts['allowed']}"
    )
print("mismatches:", *misses, sep="\n  ") if misses else print("mismatches: none")
