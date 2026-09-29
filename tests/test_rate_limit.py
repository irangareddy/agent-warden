"""Rate-limit shared rules by source without penalizing known rules."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
state_dir = Path(tempfile.mkdtemp(prefix="agent-warden-rate-limit-"))
os.environ["WARDEN_STATE_DIR"] = str(state_dir)
os.environ["WARDEN_MAX_RULES_PER_MESSAGE"] = "3"
os.environ["WARDEN_MAX_RULES_PER_SOURCE"] = "20"

from agent.warden import RATE_LIMIT_REASON, Rule, Warden, encode_signature  # noqa: E402


def rule(source: str, number: int) -> Rule:
    return Rule(
        f"{source}-{number}",
        "credential_access",
        "^read_file$",
        rf"/rate-limit/{source}/secret-{number}\.txt",
        f"Protects secret {number} from {source}.",
        source,
    )


def prompt(rules: list[Rule]) -> str:
    return "\n".join(encode_signature(item) for item in rules)


warden = Warden("rate-limit-test")
first_batch = [rule("source-a", number) for number in range(5)]
accepted, rejected = warden.learn_from_prompt(prompt(first_batch))
assert [item.id for item in accepted] == [item.id for item in first_batch[:3]]
assert [(item.id, why) for item, why in rejected] == [
    (item.id, RATE_LIMIT_REASON) for item in first_batch[3:]
]
pending = [
    json.loads(line)
    for line in (state_dir / "pending_rules.jsonl").read_text(encoding="utf-8").splitlines()
]
assert len(pending) == 2
assert all(item["reason"] == RATE_LIMIT_REASON for item in pending)
print("PASS one source sent five rules: three accepted and two held for review")

other = rule("source-b", 0)
accepted, rejected = warden.learn_from_prompt(prompt([other]))
assert [item.id for item in accepted] == [other.id] and not rejected
print("PASS a second source has an independent per-message allowance")

known = first_batch[0]
new_rules = [rule("source-a", number) for number in range(5, 8)]
accepted, rejected = warden.learn_from_prompt(prompt([known, *new_rules]))
assert [item.id for item in accepted] == [known.id, *(item.id for item in new_rules)]
assert not rejected
print("PASS an already-enforced rule does not consume the per-message allowance")

os.environ["WARDEN_MAX_RULES_PER_MESSAGE"] = "10"
os.environ["WARDEN_MAX_RULES_PER_SOURCE"] = "4"
total_batch = [rule("source-total", number) for number in range(5)]
accepted, rejected = warden.learn_from_prompt(prompt(total_batch))
assert [item.id for item in accepted] == [item.id for item in total_batch[:4]]
assert [(item.id, why) for item, why in rejected] == [
    (total_batch[4].id, RATE_LIMIT_REASON)
]
assert sum(item.source == "source-total" for item in warden.shared) == 4
print("PASS total shared rules from one source are capped independently")
