"""End-to-end tests for the project setup and review CLI (Python 3.12)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CLI = ROOT / "tools" / "warden.py"
HOOK = ROOT / "hooks" / "warden_hook.py"
TOTAL = 0
PASSED = 0


def passed(name: str) -> None:
    global TOTAL, PASSED
    TOTAL += 1
    PASSED += 1
    print(f"PASS {name}")


def run(
    arguments: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"command failed: {arguments}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent-warden-cli-") as temporary:
        temp = Path(temporary)
        project = temp / "Sample Project"
        project.mkdir()
        (project / "package.json").write_text(
            json.dumps({"scripts": {"test": "node --test", "lint": "eslint ."}}),
            encoding="utf-8",
        )
        (project / "Package.swift").write_text("// swift-tools-version: 6.0\n", encoding="utf-8")
        claude_file = project / ".claude" / "settings.json"
        claude_file.parent.mkdir()
        claude_file.write_text(json.dumps({"permissions": {"allow": ["Read"]}}), encoding="utf-8")

        env = os.environ.copy()
        for key in (
            "WARDEN_RULEPACKS",
            "WARDEN_RULEPACKS_DIR",
            "WARDEN_STATE_DIR",
            "AGENT_WARDEN_FAIL_CLOSED",
            "WARDEN_NODE_NAME",
            "WARDEN_MAX_RULES_PER_MESSAGE",
            "WARDEN_MAX_RULES_PER_SOURCE",
        ):
            env.pop(key, None)
        env["HOME"] = str(temp / "home")
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        init = run(
            [
                str(CLI),
                "init",
                "--project",
                str(project),
                "--harness",
                "claude",
                "--packs",
                "secrets,git-safety,publishing",
                "--name",
                "sample-project",
                "--write-hook",
                "--yes",
            ],
            cwd=ROOT,
            env=env,
        )
        assert "--harness claude" in init.stdout
        config = (project / ".agent-warden" / "config.toml").read_text(encoding="utf-8")
        assert '"sample-project"' in config
        pack = project / ".agent-warden" / "packs" / "sample-project"
        assert (pack / "SKILL.md").is_file()
        assert json.loads((pack / "rules.json").read_text(encoding="utf-8")) == []
        known_good = json.loads((pack / "known_good.json").read_text(encoding="utf-8"))
        commands = {call["arguments"]["command"] for call in known_good}
        assert {"npm test", "npm run lint", "swift build", "swift test"} <= commands
        passed("init creates config, pack skeleton, and detected known-good commands")

        hook_config = json.loads(claude_file.read_text(encoding="utf-8"))
        assert hook_config["permissions"] == {"allow": ["Read"]}
        pre_tool = hook_config["hooks"]["PreToolUse"]
        assert pre_tool and str(HOOK) in pre_tool[0]["hooks"][0]["command"]
        assert list(claude_file.parent.glob("settings.json.bak-*"))
        passed("init --write-hook merges Claude PreToolUse and backs up existing JSON")

        original_known_good = (pack / "known_good.json").read_text(encoding="utf-8")
        original_rules = (pack / "rules.json").read_text(encoding="utf-8")
        run(
            [str(CLI), "init", "--project", str(project), "--name", "sample-project", "--yes"],
            cwd=ROOT,
            env=env,
        )
        assert (pack / "known_good.json").read_text(encoding="utf-8") == original_known_good
        assert (pack / "rules.json").read_text(encoding="utf-8") == original_rules
        passed("init is idempotent for project rules and known-good calls")

        status = run([str(CLI), "status", "--project", str(project)], cwd=ROOT, env=env)
        assert "sample-project: 0 rules" in status.stdout and "pending: 0" in status.stdout
        passed("status reports active packs and review counts")

        blocked = run(
            [str(CLI), "test", "--project", str(project), "--tool", "Bash", "cat .env"],
            cwd=ROOT,
            env=env,
        )
        allowed = run(
            [str(CLI), "test", "--project", str(project), "--tool", "Bash", "git status"],
            cwd=ROOT,
            env=env,
        )
        assert blocked.stdout.startswith("block | rule=")
        assert allowed.stdout.strip() == "allow"
        passed("test dry-run blocks .env access and allows git status")

        state_dir = temp / "home" / ".agent-warden" / "sample-project"
        os.environ["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing,sample-project"
        os.environ["WARDEN_RULEPACKS_DIR"] = str(project / ".agent-warden" / "packs")
        os.environ["WARDEN_STATE_DIR"] = str(state_dir)
        from agent.warden import RATE_LIMIT_REASON, Rule, Warden, encode_signature

        learned = Rule(
            "learned-review-rule",
            "project-policy",
            "^Bash$",
            "custom-danger-command",
            "Blocks a learned project danger.",
            "remote-node",
        )
        learner = Warden("cli-test")
        assert learner.learn(learned)
        listing = run(
            [str(CLI), "review", "--project", str(project), "--list"], cwd=ROOT, env=env
        )
        assert "Pending learned rules remain enforced" in listing.stdout
        assert "learned-review-rule" in listing.stdout and "validation=pass" in listing.stdout
        passed("review --list shows a learned pending rule and validation")

        held = Rule(
            "held-review-rule",
            "project-policy",
            "^Bash$",
            "held-danger-command",
            "Candidate held by the source quota.",
            "noisy-node",
        )
        os.environ["WARDEN_MAX_RULES_PER_MESSAGE"] = "0"
        held_accepted, held_rejected = learner.learn_from_prompt(encode_signature(held))
        os.environ.pop("WARDEN_MAX_RULES_PER_MESSAGE")
        assert not held_accepted and held_rejected == [(held, RATE_LIMIT_REASON)]
        listing = run(
            [str(CLI), "review", "--project", str(project), "--list"], cwd=ROOT, env=env
        )
        assert "Rate-limited rules held for human review (not enforced)." in listing.stdout
        assert "held-review-rule" in listing.stdout and RATE_LIMIT_REASON in listing.stdout
        passed("review --list shows rate-limited rules as held and not enforced")

        approved = run(
            [str(CLI), "review", "--project", str(project), "--approve", learned.id],
            cwd=ROOT,
            env=env,
        )
        assert "Approved learned-review-rule" in approved.stdout
        project_rules = json.loads((pack / "rules.json").read_text(encoding="utf-8"))
        assert any(rule["id"] == learned.id and rule["action"] == "block" for rule in project_rules)
        shared = json.loads((state_dir / "signatures.json").read_text(encoding="utf-8"))
        assert next(rule for rule in shared if rule["id"] == learned.id)["source"] == "approved:remote-node"
        fresh = Warden("fresh-after-approval")
        decision = fresh.check(
            {"name": "Bash", "arguments": json.dumps({"command": "custom-danger-command"})}
        )
        assert decision.action == "block" and any(
            rule.id == learned.id and rule.source == "pack:sample-project" for rule in fresh.pack_rules
        )
        passed("review --approve adds an enforceable project rule and keeps shared provenance")

        rejected_rule = Rule(
            "learned-reject-rule",
            "project-policy",
            "^Bash$",
            "human-rejected-pattern",
            "Candidate requiring review.",
            "remote-node",
        )
        assert learner.learn(rejected_rule)
        rejected = run(
            [str(CLI), "review", "--project", str(project), "--reject", rejected_rule.id],
            cwd=ROOT,
            env=env,
        )
        assert "Rejected learned-reject-rule" in rejected.stdout
        after = json.loads((state_dir / "signatures.json").read_text(encoding="utf-8"))
        assert all(rule["id"] != rejected_rule.id for rule in after)
        assert rejected_rule.pattern in json.loads(
            (state_dir / "rejected.json").read_text(encoding="utf-8")
        )
        retry = Rule(
            "learned-reject-retry",
            rejected_rule.family,
            rejected_rule.tool,
            rejected_rule.pattern,
            rejected_rule.reason,
            "another-node",
        )
        assert not learner.learn(retry)
        log_lines = (state_dir / "rule_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(log_lines[-1])["why"] == "previously rejected by a human"
        passed("review --reject removes shared rule and prevents relearning its pattern")

        project_rules.append(
            {
                "id": "project-hook-rule",
                "family": "project-policy",
                "tool": "^Bash$",
                "pattern": "project-forbidden-command",
                "reason": "Blocked by the project pack.",
                "action": "block",
            }
        )
        (pack / "rules.json").write_text(json.dumps(project_rules, indent=2) + "\n", encoding="utf-8")
        hook = subprocess.run(
            [sys.executable, str(HOOK), "--harness", "claude"],
            cwd=project,
            env=env,
            input=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": "project-forbidden-command"}}
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        assert hook.returncode == 2, hook
        assert "Blocked by the project pack." in hook.stderr
        passed("hook discovers project config from cwd and enforces the project pack")

    print(f"{PASSED}/{TOTAL} CLI cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
