#!/usr/bin/env python3
"""Set up and operate Agent Warden for a project."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_PACKS = ["secrets", "git-safety", "publishing"]
HARNESSES = ("claude", "codex", "cursor", "copilot", "gemini", "grok", "generic")
HOOK_FILES = {
    "claude": Path(".claude/settings.json"),
    "codex": Path(".codex/hooks.json"),
    "cursor": Path(".cursor/hooks.json"),
    "copilot": Path(".github/hooks/warden.json"),
    "gemini": Path(".gemini/settings.json"),
    "grok": Path(".grok/hooks/warden.json"),
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    return slug or "project"


def _prompt(label: str, default: str) -> str:
    answer = input(f"{label} [{default}]: ").strip()
    return answer or default


def _resolve_project(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _known_good(project: Path) -> list[dict[str, Any]]:
    commands: list[str] = []

    package = project / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
            if isinstance(scripts, dict):
                for name in scripts:
                    if isinstance(name, str):
                        commands.append("npm test" if name == "test" else f"npm run {name}")
        except (json.JSONDecodeError, OSError, AttributeError):
            pass

    makefile = next((path for path in (project / "Makefile", project / "makefile") if path.is_file()), None)
    if makefile is not None:
        try:
            for line in makefile.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(?:\s|$)", line)
                if match and not match.group(1).startswith("."):
                    commands.append(f"make {match.group(1)}")
        except OSError:
            pass

    if any((project / name).exists() for name in ("pyproject.toml", "pytest.ini", "conftest.py")):
        commands.extend(("pytest", "uv run pytest"))
    if (project / "Package.swift").is_file():
        commands.extend(("swift build", "swift test"))
    if any(project.glob("*.xcodeproj")) or any(project.glob("*.xcworkspace")):
        commands.append("xcodebuild test")
    commands.extend(("git status", "git diff", "git log --oneline"))

    unique = list(dict.fromkeys(commands))
    return [{"tool": "Bash", "arguments": {"command": command}} for command in unique]


def _skill_template(name: str) -> str:
    return f"""---
name: {name}
description: Project-specific protections for {name}.
---

# {name} rules

TODO: Describe what this pack protects, when it should be enabled, and examples
of calls that should be blocked or allowed.

Add rules to `rules.json`. JSON does not support comments; this is an example:

```json
{{
  "id": "{name}-example",
  "family": "project-policy",
  "tool": "^Bash$",
  "pattern": "dangerous-command",
  "reason": "Explain why this command is blocked.",
  "action": "block"
}}
```
"""


def _hook_spec(harness: str) -> dict[str, Any]:
    command = f"python3 {ROOT / 'hooks' / 'warden_hook.py'} --harness {harness}"
    standard = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": command}],
    }
    if harness in {"claude", "codex", "grok"}:
        return {"hooks": {"PreToolUse": [standard]}}
    if harness == "gemini":
        gemini = {
            "matcher": ".*",
            "hooks": [{"type": "command", "name": "Agent Warden", "command": command}],
        }
        return {"hooks": {"BeforeTool": [gemini]}}
    if harness == "copilot":
        return {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {"type": "command", "bash": command, "cwd": ".", "timeoutSec": 10}
                ]
            },
        }
    if harness == "cursor":
        return {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {"matcher": "*", "command": command, "failClosed": True}
                ],
                "beforeShellExecution": [{"command": command, "failClosed": True}],
            },
        }
    return {
        "command": command,
        "input": {"tool": "NAME", "args": {"command": "..."}},
    }


def _merge_json(existing: Any, addition: Any) -> Any:
    if isinstance(existing, dict) and isinstance(addition, dict):
        merged = dict(existing)
        for key, value in addition.items():
            merged[key] = _merge_json(merged[key], value) if key in merged else value
        return merged
    if isinstance(existing, list) and isinstance(addition, list):
        merged = list(existing)
        for value in addition:
            if value not in merged:
                merged.append(value)
        return merged
    return addition


def _write_hook(project: Path, harness: str, spec: dict[str, Any]) -> Path:
    relative = HOOK_FILES.get(harness)
    if relative is None:
        raise ValueError("the generic harness has no native project config file")
    target = (project / relative).resolve()
    if project != target and project not in target.parents:
        raise ValueError("hook config must stay inside the project")
    existing: Any = {}
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = target.with_name(f"{target.name}.bak-{stamp}")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"cannot merge invalid JSON in {target}: {error}") from error
        if not isinstance(existing, dict):
            raise ValueError(f"cannot merge non-object JSON in {target}")
    _json_write(target, _merge_json(existing, spec))
    return target


def command_init(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    project.mkdir(parents=True, exist_ok=True)
    interactive = not args.noninteractive
    harness = args.harness or (_prompt("Harness", "claude") if interactive else "claude")
    if harness not in HARNESSES:
        raise ValueError(f"unknown harness {harness!r}")
    pack_text = args.packs or (
        _prompt("Base packs (comma-separated)", ",".join(DEFAULT_PACKS))
        if interactive
        else ",".join(DEFAULT_PACKS)
    )
    packs = [value.strip() for value in pack_text.split(",") if value.strip()]
    default_name = _slug(project.name)
    name = _slug(args.name or (_prompt("Project pack name", default_name) if interactive else default_name))
    packs = list(dict.fromkeys([*packs, name]))

    warden_dir = project / ".agent-warden"
    pack_dir = warden_dir / "packs" / name
    pack_dir.mkdir(parents=True, exist_ok=True)
    config = (
        f"packs = {json.dumps(packs)}\n"
        'pack_dir = ".agent-warden/packs"\n'
        f'state_dir = "~/.agent-warden/{name}"\n'
        "fail_closed = false\n"
        f"harness = {json.dumps(harness)}\n"
    )
    (warden_dir / "config.toml").write_text(config, encoding="utf-8")
    skill = pack_dir / "SKILL.md"
    rules = pack_dir / "rules.json"
    known_good = pack_dir / "known_good.json"
    if not skill.exists():
        skill.write_text(_skill_template(name), encoding="utf-8")
    if not rules.exists():
        _json_write(rules, [])
    if not known_good.exists():
        _json_write(known_good, _known_good(project))

    spec = _hook_spec(harness)
    print(f"Initialized Agent Warden in {warden_dir}")
    print("Hook configuration:")
    print(json.dumps(spec, indent=2))
    if args.write_hook:
        target = _write_hook(project, harness, spec)
        print(f"Wrote hook configuration to {target}")
    return 0


def _load_for_project(project_arg: str):
    from agent.config import load_project_config

    project = _resolve_project(project_arg)
    config_path, config = load_project_config(project)
    if config_path is None:
        raise ValueError(f"no .agent-warden/config.toml found from {project}")
    from agent.warden import Warden

    return project, config_path, config, Warden("warden-cli")


def _read_list(path: Path) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _project_pack(config_path: Path, config: dict[str, Any]) -> tuple[str, Path]:
    root = config_path.parent.parent
    pack_root = Path(str(config.get("pack_dir", ".agent-warden/packs"))).expanduser()
    if not pack_root.is_absolute():
        pack_root = root / pack_root
    packs = config.get("packs", [])
    for name in reversed(packs if isinstance(packs, list) else []):
        candidate = pack_root / str(name)
        if candidate.is_dir():
            return str(name), candidate
    raise ValueError("config does not name a project pack in pack_dir")


def _pending(warden: Any, pack_dir: Path) -> list[Any]:
    existing_ids = {
        item.get("id") for item in _read_list(pack_dir / "rules.json") if isinstance(item, dict)
    }
    return [rule for rule in warden.shared if rule.id not in existing_ids]


def _excerpt(value: Any, limit: int = 72) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _recent_for(rule: Any, state_dir: Path) -> dict[str, Any] | None:
    decisions = [entry for entry in _read_jsonl(state_dir / "decisions.jsonl")]
    origin = rule.id
    if origin.startswith("shared-"):
        origin = origin[len("shared-") :].rsplit("-", 1)[0]
    for entry in reversed(decisions):
        if entry.get("rule_id") in {rule.id, origin} or entry.get("family") == rule.family:
            return entry
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except json.JSONDecodeError:
                continue
    except FileNotFoundError:
        pass
    return rows


def _print_pending(warden: Any, rules: list[Any], state_dir: Path) -> None:
    print("Pending learned rules remain enforced until approved or rejected.")
    if not rules:
        print("No pending learned rules.")
        return
    for rule in rules:
        valid, why = warden.validate(rule)
        recent = _recent_for(rule, state_dir)
        trigger = "none"
        if recent:
            arguments = recent.get("arguments", recent.get("command", recent.get("file_path", "")))
            trigger = f"{recent.get('tool', '?')} {_excerpt(arguments) or '(arguments not logged)'}"
        print(
            f"{rule.id} | family={rule.family} | source={rule.source} | "
            f"pattern={rule.pattern} | reason={rule.reason} | "
            f"validation={'pass' if valid else 'fail'} ({why}) | latest={trigger}"
        )


def _approve(warden: Any, rule: Any, pack_dir: Path, state_dir: Path) -> None:
    path = pack_dir / "rules.json"
    rules = _read_list(path)
    if not any(isinstance(item, dict) and item.get("id") == rule.id for item in rules):
        rules.append(
            {
                "id": rule.id,
                "family": rule.family,
                "tool": rule.tool,
                "pattern": rule.pattern,
                "reason": rule.reason,
                "action": "block",
            }
        )
        _json_write(path, rules)
    if not rule.source.startswith("approved:"):
        rule.source = f"approved:{rule.source}"
        _json_write(state_dir / "signatures.json", [asdict(value) for value in warden.shared])
    print(f"Approved {rule.id}; added to {path} and retained in shared enforcement.")


def _reject(warden: Any, rule: Any, state_dir: Path) -> None:
    removed = warden.remove_shared_rule(rule.id)
    if removed is None:
        raise ValueError(f"learned rule {rule.id!r} was not found")
    rejected_path = state_dir / "rejected.json"
    patterns = [value for value in _read_list(rejected_path) if isinstance(value, str)]
    if rule.pattern not in patterns:
        patterns.append(rule.pattern)
        _json_write(rejected_path, patterns)
    print(f"Rejected {rule.id}; removed from shared enforcement and recorded its pattern.")


def command_review(args: argparse.Namespace) -> int:
    _, config_path, config, warden = _load_for_project(args.project)
    _, pack_dir = _project_pack(config_path, config)
    state_dir = Path(os.environ["WARDEN_STATE_DIR"])
    pending = _pending(warden, pack_dir)
    by_id = {rule.id: rule for rule in pending}
    if args.approve:
        rule = by_id.get(args.approve)
        if rule is None:
            raise ValueError(f"pending rule {args.approve!r} was not found")
        _approve(warden, rule, pack_dir, state_dir)
    elif args.reject:
        rule = by_id.get(args.reject)
        if rule is None:
            raise ValueError(f"pending rule {args.reject!r} was not found")
        _reject(warden, rule, state_dir)
    elif args.approve_all:
        for rule in pending:
            _approve(warden, rule, pack_dir, state_dir)
    elif args.list:
        _print_pending(warden, pending, state_dir)
    else:
        _print_pending(warden, pending, state_dir)
        for rule in pending:
            choice = input(f"{rule.id}: [a]pprove / [r]eject / [s]kip? ").strip().lower()
            if choice.startswith("a"):
                _approve(warden, rule, pack_dir, state_dir)
            elif choice.startswith("r"):
                _reject(warden, rule, state_dir)
    return 0


def command_status(args: argparse.Namespace) -> int:
    _, config_path, config, warden = _load_for_project(args.project)
    project_name, pack_dir = _project_pack(config_path, config)
    packs = config.get("packs", [])
    counts: dict[str, int] = {}
    for rule in warden.pack_rules:
        counts[rule.source.removeprefix("pack:")] = counts.get(rule.source.removeprefix("pack:"), 0) + 1
    print("Active packs:")
    for name in packs:
        print(f"  {name}: {counts.get(str(name), 0)} rules")
    state_dir = Path(os.environ["WARDEN_STATE_DIR"])
    pending = _pending(warden, pack_dir)
    rejected = [value for value in _read_list(state_dir / "rejected.json") if isinstance(value, str)]
    print(
        f"Learned: {len(warden.shared)} | pending: {len(pending)} | "
        f"rejected: {len(rejected)} | project pack: {project_name}"
    )
    print("Last decisions:")
    decisions = _read_jsonl(state_dir / "decisions.jsonl")[-10:]
    if not decisions:
        print("  none")
    for decision in decisions:
        arguments = decision.get("arguments", decision.get("command", decision.get("file_path", "")))
        print(
            f"  {decision.get('action', 'allow')} {decision.get('tool', '?')} "
            f"{_excerpt(arguments) or '(arguments not logged)'}"
        )
    return 0


def command_test(args: argparse.Namespace) -> int:
    _, _, _, warden = _load_for_project(args.project)
    key = "command" if args.tool.lower() in {"bash", "exec", "shell"} else "file_path"
    decision = warden.check(
        {"name": args.tool, "arguments": json.dumps({key: args.value})}
    )
    detail = ""
    if decision.rule_id:
        detail = f" | rule={decision.rule_id} | reason={decision.reason}"
    print(f"{decision.action}{detail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="set up Agent Warden in a project")
    init.add_argument("--project", default=".")
    init.add_argument("--harness", choices=HARNESSES)
    init.add_argument("--packs")
    init.add_argument("--name")
    init.add_argument("--write-hook", action="store_true")
    init.add_argument("--yes", action="store_true")
    init.set_defaults(func=command_init)

    review = subparsers.add_parser("review", help="review learned rules")
    review.add_argument("--project", default=".")
    group = review.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true")
    group.add_argument("--approve", metavar="ID")
    group.add_argument("--reject", metavar="ID")
    group.add_argument("--approve-all", action="store_true")
    review.set_defaults(func=command_review)

    status = subparsers.add_parser("status", help="show active rules and recent decisions")
    status.add_argument("--project", default=".")
    status.set_defaults(func=command_status)

    test = subparsers.add_parser("test", help="dry-run one tool call")
    test.add_argument("--project", default=".")
    test.add_argument("--tool", required=True)
    test.add_argument("value")
    test.set_defaults(func=command_test)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw)
    if args.command == "init":
        args.noninteractive = args.yes or any(
            token == option or token.startswith(option + "=")
            for token in raw
            for option in ("--project", "--harness", "--packs", "--name", "--write-hook")
        )
    try:
        return args.func(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
