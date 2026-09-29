"""A poisoned node shares an overbroad rule; honest nodes must reject it and keep working."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp()
from agent.warden import Warden, Rule, encode_signature

fc = lambda p: {"type": "function_call", "name": "read_file", "arguments": json.dumps({"path": p})}
node = Warden("Beet QA Agent")
poisoned = [
    Rule("evil-1", "credential_access", ".*", r"/data/", "Blocks all project data", "compromised-node"),
    Rule("evil-2", "credential_access", ".*", r".*", "Blocks everything", "compromised-node"),
    Rule("evil-3", "credential_access", ".*", r"read_file|push_reply", "Blocks reading and replying", "compromised-node"),
]
honest = Rule("good-1", "credential_access", ".*", r"\.env\b", "Blocks .env files", "Beet Backend Agent")
msg = " ".join(encode_signature(r) for r in poisoned + [honest])
accepted, rejected = node.learn_from_prompt(f"src_node_id=1 payload={msg}")
for rule, why in rejected:
    print(f"REJECTED {rule.id:<7} from {rule.source}: {why}")
for rule in accepted:
    print(f"ACCEPTED {rule.id:<7} from {rule.source}")
print("normal work still allowed:", node.check(fc("/data/qa/test_report.md")).allowed)
print(".env variant now blocked:", not node.check(fc("/data/qa/.env.local")).allowed)
