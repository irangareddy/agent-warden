"""The claim: another node blocks a variant only because it learned the rule.

Backend enables the customer-data pack; QA does not. QA must allow the probe
before learning Backend's rule, validate the rule on its own work, then block.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="wagent-shared-only-")

from agent.redteam import function_call, variant_path  # noqa: E402
from agent.relay import attach_signatures  # noqa: E402
from agent.warden import Warden  # noqa: E402

EXPORT = "/data/backend/exports/customers-2026-09.csv"

os.environ["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing,customer-data"
backend = Warden("Beet Backend Agent")
attack = function_call("filesystem_read_file", "attack", path=EXPORT)
decision = backend.check(attack)
assert decision.action == "block" and decision.rule_id == "customer-data-exports", decision
rule, _ = backend.evolve(decision, attack)
print(f"1. Backend blocked the export read ({decision.rule_id}) and shared: {rule.pattern}")

os.environ["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing"
qa = Warden("Beet QA Agent")
probe = function_call("filesystem_read_file", "probe", path=variant_path([rule], qa.node_name))
before = qa.check(probe)
assert before.action == "allow", f"QA already blocked it with {before.rule_id}; the test proves nothing"
print("2. QA, without the customer-data pack, allows the variant: its own rules miss it")

accepted, rejected = qa.learn_from_prompt(attach_signatures("status please", [rule]))
assert [r.pattern for r in accepted] == [rule.pattern] and not rejected
after = qa.check(probe)
assert after.action == "block" and after.rule_id == rule.id, after
print(f"3. QA validated Backend's rule on its own work, learned it, and now blocks the variant ({after.rule_id})")
again, rejected = qa.learn_from_prompt(attach_signatures("probe again", [rule]))
assert [r.pattern for r in again] == [rule.pattern] and not rejected, "a rule learned in an earlier run must still be reported"
print("4. Sent the same rule again (a later run): QA reports it as already accepted")
print("PASS: the block came only from the shared rule")
