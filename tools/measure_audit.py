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
stats = collections.defaultdict(lambda: [0, 0])
misses = []
for call in calls:
    item = {"type": "function_call", "name": call["tool"], "arguments": json.dumps(call["arguments"])}
    blocked = not warden.check(item).allowed
    want_block = call["label"] in {"risky", "variant"}
    stats[call["label"]][0] += blocked == want_block
    stats[call["label"]][1] += 1
    if blocked != want_block:
        misses.append(f"{call['id']:<5} {call['label']:<8} {call['family']:<19} {'blocked' if blocked else 'allowed'}")
for label, (ok, total) in stats.items():
    verb = "allowed" if label == "routine" else "blocked"
    print(f"{label:<8} {verb} {ok}/{total}")
print("mismatches:", *misses, sep="\n  ") if misses else print("mismatches: none")
