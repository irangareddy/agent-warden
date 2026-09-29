"""Exercise bundled defaults, loader errors, and local rule-pack extensions."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="rulepacks-state-")

from agent.rulepacks import DEFAULT_PACKS, RulePackError, load_packs
from agent.warden import Rule, Warden


previous_packs = os.environ.pop("WARDEN_RULEPACKS", None)
previous_dir = os.environ.pop("WARDEN_RULEPACKS_DIR", None)
try:
    default_rules, default_good = load_packs()
    default_sources = {rule.source for rule in default_rules}
    assert default_sources == {f"pack:{name}" for name in DEFAULT_PACKS}
    assert default_good
    print(f"default packs: {','.join(DEFAULT_PACKS)} ({len(default_rules)} rules)")

    try:
        load_packs(["does-not-exist"])
    except RulePackError as err:
        assert "unknown rule pack 'does-not-exist'" in str(err)
        print("unknown pack: clear error")
    else:
        raise AssertionError("unknown pack did not raise RulePackError")

    with tempfile.TemporaryDirectory(prefix="warden-custom-pack-") as root:
        pack = Path(root) / "custom"
        pack.mkdir()
        (pack / "SKILL.md").write_text(
            "---\nname: custom\ndescription: Test-only local rule pack.\n---\n",
            encoding="utf-8",
        )
        (pack / "rules.json").write_text(
            json.dumps(
                [
                    {
                        "id": "custom-danger",
                        "family": "custom",
                        "tool": "^custom_tool$",
                        "pattern": "dangerous-command",
                        "reason": "Blocks the custom dangerous command.",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (pack / "known_good.json").write_text(
            json.dumps(
                [
                    {
                        "tool": "custom_tool",
                        "arguments": {"path": "/safe-routine-command/normal"},
                    }
                ]
            ),
            encoding="utf-8",
        )

        os.environ["WARDEN_RULEPACKS"] = "custom"
        os.environ["WARDEN_RULEPACKS_DIR"] = root
        warden = Warden("custom-pack-test")
        item = {
            "name": "custom_tool",
            "arguments": json.dumps({"command": "dangerous-command"}),
        }
        decision = warden.check(item)
        assert not decision.allowed
        assert decision.rule_id == "custom-danger"
        assert decision.source == "pack:custom"

        overbroad = Rule(
            "custom-false-alarm",
            "custom",
            "^custom_tool$",
            "safe-routine-command",
            "Would block a known-good custom call.",
            "remote-node",
        )
        valid, why = warden.validate(overbroad)
        assert not valid
        assert "would block 1 normal action" in why
        print("custom pack: rule enforced and pack known-good used by validation")

        evolved, report = warden.evolve(
            decision,
            {"name": "custom_tool", "arguments": json.dumps({"path": "/safe-routine-command/key"})},
        )
        assert report[0]["false_alarms"] == 1
        assert evolved.pattern != report[0]["pattern"]
        print("custom pack: pack known-good also used by evolution")
finally:
    if previous_packs is None:
        os.environ.pop("WARDEN_RULEPACKS", None)
    else:
        os.environ["WARDEN_RULEPACKS"] = previous_packs
    if previous_dir is None:
        os.environ.pop("WARDEN_RULEPACKS_DIR", None)
    else:
        os.environ["WARDEN_RULEPACKS_DIR"] = previous_dir
