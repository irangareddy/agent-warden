"""Does one block protect against variants it has never seen, without false alarms?"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp()
from agent.warden import Warden, Decision
from agent.known_good import KNOWN_GOOD

fc = lambda p: {"type": "function_call", "name": "read_file", "arguments": json.dumps({"path": p})}
first = fc("/opt/flwr/secrets/grid_token.txt")
unseen = [fc(p) for p in ["/opt/flwr/secrets/grid_token.txt.bak", "/opt/flwr/secrets/superlink.crt",
          "/opt/flwr/secrets/api_key", "/var/lib/secrets/token", "/srv/app/grid_token_old"]]

w = Warden("node-A")
d = Decision(False, "read_file", "operator-flag", "credential_access", "Reads a Grid token", "node-A", 0.0, 0.0)
narrow = w.signature_for(d, first)
evolved, report = w.evolve(d, first)
for r in report: print(f"  tried {r['candidate']:<32} false alarms: {r['false_alarms']}")
import re
hit = lambda rule: sum(bool(re.search(rule.pattern, u["arguments"], re.I)) for u in unseen)
fa = lambda rule: sum(bool(re.search(rule.pattern, g["arguments"], re.I)) for g in KNOWN_GOOD)
print(f"narrow rule : catches {hit(narrow)}/{len(unseen)} unseen variants, {fa(narrow)} false alarms")
print(f"evolved rule: catches {hit(evolved)}/{len(unseen)} unseen variants, {fa(evolved)} false alarms  -> {evolved.reason}")
