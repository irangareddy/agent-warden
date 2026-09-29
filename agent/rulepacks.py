"""Load portable Agent Warden rule packs from bundled and local directories."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from agent.warden import Rule


DEFAULT_PACKS = ("secrets", "git-safety", "publishing")
PACKS_ENV = "WARDEN_RULEPACKS"
PACKS_DIR_ENV = "WARDEN_RULEPACKS_DIR"
_RULE_FIELDS = {"id", "family", "tool", "pattern", "reason"}
_OPTIONAL_RULE_FIELDS = {"action"}


class RulePackError(ValueError):
    """A requested rule pack is missing or malformed."""


def enabled_pack_names() -> list[str]:
    """Return configured pack names, using the generic defaults when unset."""
    raw = os.environ.get(PACKS_ENV)
    if raw is None:
        return list(DEFAULT_PACKS)
    return [name.strip() for name in raw.split(",") if name.strip()]


def load_packs(names: Iterable[str] | None = None) -> tuple[list["Rule"], list[dict[str, Any]]]:
    """Load rules and known-good calls from the requested packs."""
    from agent.warden import Rule

    requested = enabled_pack_names() if names is None else list(names)
    roots = _search_roots()
    rules: list[Rule] = []
    known_good: list[dict[str, Any]] = []
    seen: set[str] = set()

    for name in requested:
        if name in seen:
            continue
        seen.add(name)
        _validate_pack_name(name)
        pack_dir = next((root / name for root in roots if (root / name).is_dir()), None)
        if pack_dir is None:
            locations = ", ".join(str(root) for root in roots)
            raise RulePackError(f"unknown rule pack {name!r}; searched: {locations}")

        raw_rules = _read_json_list(pack_dir / "rules.json", name)
        raw_known_good = _read_json_list(pack_dir / "known_good.json", name)

        for index, raw_rule in enumerate(raw_rules):
            where = f"rule pack {name!r} rules.json entry {index}"
            if (
                not isinstance(raw_rule, dict)
                or not _RULE_FIELDS.issubset(raw_rule)
                or not set(raw_rule).issubset(_RULE_FIELDS | _OPTIONAL_RULE_FIELDS)
            ):
                raise RulePackError(
                    f"{where} must contain required fields {sorted(_RULE_FIELDS)} "
                    f"and optional fields {sorted(_OPTIONAL_RULE_FIELDS)}"
                )
            if not all(isinstance(value, str) for value in raw_rule.values()):
                raise RulePackError(f"{where} fields must all be strings")
            if raw_rule.get("action", "block") not in {"block", "ask"}:
                raise RulePackError(f"{where} action must be 'block' or 'ask'")
            for field in ("tool", "pattern"):
                try:
                    re.compile(raw_rule[field], re.I | re.S)
                except re.error as err:
                    rule_id = raw_rule.get("id", f"entry {index}")
                    raise RulePackError(
                        f"invalid {field} regex in rule pack {name!r}, rule {rule_id!r}: {err}"
                    ) from err
            rules.append(Rule(**raw_rule, source=f"pack:{name}"))

        for index, call in enumerate(raw_known_good):
            where = f"rule pack {name!r} known_good.json entry {index}"
            if not isinstance(call, dict) or set(call) != {"tool", "arguments"}:
                raise RulePackError(f"{where} must contain exactly ['arguments', 'tool']")
            if not isinstance(call["tool"], str) or not isinstance(call["arguments"], dict):
                raise RulePackError(f"{where} requires a string tool and object arguments")
            known_good.append(call)

    return rules, known_good


def _search_roots() -> list[Path]:
    roots = [Path(__file__).resolve().with_suffix("")]
    extra = os.environ.get(PACKS_DIR_ENV)
    if extra:
        roots.extend(Path(value).expanduser().resolve() for value in extra.split(os.pathsep) if value)
    return roots


def _validate_pack_name(name: str) -> None:
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise RulePackError(f"invalid rule pack name {name!r}")


def _read_json_list(path: Path, pack_name: str) -> list[Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as err:
        raise RulePackError(f"rule pack {pack_name!r} is missing {path.name}") from err
    except json.JSONDecodeError as err:
        raise RulePackError(f"rule pack {pack_name!r} has invalid {path.name}: {err}") from err
    if not isinstance(value, list):
        raise RulePackError(f"rule pack {pack_name!r} {path.name} must contain a JSON list")
    return value
