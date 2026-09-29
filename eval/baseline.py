"""Compare Wagent with a small, hand-written substring denylist."""

from __future__ import annotations

import contextlib
import importlib
import io
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


# A representative denylist that a team might write in ten minutes.
DENYLIST = [
    ".env",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "secret",
    "token",
    "password",
    "credentials",
    "push --force",
    "push -f",
    "reset --hard",
    "rm -rf",
    "npm publish",
    "DROP TABLE",
    ".p8",
    ".netrc",
    "config.toml",
]

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CAUGHT_ACTIONS = {"block", "ask"}


@dataclass(frozen=True)
class Result:
    name: str
    risky_blocked: int
    risky_asked: int
    true_positives: int
    false_negatives: int
    routine_blocked: int
    routine_asked: int
    precision: tuple[float, float, float]
    recall: tuple[float, float, float]
    false_block_rate: tuple[float, float, float]


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("successes and total must satisfy 0 <= successes <= total")
    if total == 0:
        return 0.0, 1.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return center - margin, center + margin


def baseline_action(item: dict[str, object]) -> str:
    """Classify a call using only case-insensitive substring matching."""
    text = f"{item.get('name', '')} {item.get('arguments', '')}".casefold()
    return "block" if any(term.casefold() in text for term in DENYLIST) else "allow"


def _load_cases() -> tuple[
    list[tuple[str, str, dict[str, object]]],
    list[tuple[str, dict[str, object]]],
    bool,
    str | None,
]:
    """Import the repository's existing cases while silencing script-style tests."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(TESTS))

    with contextlib.redirect_stdout(io.StringIO()):
        try:
            beet_cases = importlib.import_module("test_beet_rules")
        except SystemExit as error:
            raise RuntimeError("tests/test_beet_rules.py failed during import") from error

    risky = list(beet_cases.RISKY)
    routine = [(case[0], case[-1]) for case in beet_cases.ROUTINE]

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            warden_cases = importlib.import_module("test_warden")
    except (Exception, SystemExit) as error:
        return risky, routine, False, f"{type(error).__name__}: {error}"

    risky.extend(
        ("warden-core", f"test_warden attack {index}", item)
        for index, item in enumerate(warden_cases.ATTACKS, start=1)
    )
    routine.extend(
        (f"test_warden normal call {index}", item)
        for index, item in enumerate(warden_cases.BENIGN, start=1)
    )
    return risky, routine, True, None


def _score(
    name: str,
    classify: Callable[[dict[str, object]], str],
    risky: list[tuple[str, str, dict[str, object]]],
    routine: list[tuple[str, dict[str, object]]],
) -> Result:
    risky_actions = [classify(item) for _, _, item in risky]
    routine_actions = [classify(item) for _, item in routine]
    risky_blocked = risky_actions.count("block")
    risky_asked = risky_actions.count("ask")
    true_positives = sum(action in CAUGHT_ACTIONS for action in risky_actions)
    false_negatives = len(risky) - true_positives
    routine_blocked = routine_actions.count("block")
    routine_asked = routine_actions.count("ask")

    false_positives = routine_blocked + routine_asked
    precision_total = true_positives + false_positives
    precision_value = true_positives / precision_total if precision_total else 0.0
    recall_value = true_positives / len(risky)
    false_block_value = routine_blocked / len(routine)
    precision_interval = wilson_interval(true_positives, precision_total)
    recall_interval = wilson_interval(true_positives, len(risky))
    false_block_interval = wilson_interval(routine_blocked, len(routine))

    return Result(
        name=name,
        risky_blocked=risky_blocked,
        risky_asked=risky_asked,
        true_positives=true_positives,
        false_negatives=false_negatives,
        routine_blocked=routine_blocked,
        routine_asked=routine_asked,
        precision=(precision_value, *precision_interval),
        recall=(recall_value, *recall_interval),
        false_block_rate=(false_block_value, *false_block_interval),
    )


def _format_rate(rate: tuple[float, float, float]) -> str:
    value, low, high = rate
    return f"{value:.1%} [{low:.1%}, {high:.1%}]"


def _warden_classifier(warden: object) -> Callable[[dict[str, object]], str]:
    return lambda item: warden.check(item).action


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wagent-baseline-") as state_dir:
        # Set state before importing either test cases or agent modules.
        os.environ["WARDEN_STATE_DIR"] = state_dir
        risky, routine, included_warden, skip_reason = _load_cases()

        # test_warden reloads this module against its own temporary directories.
        # Reload once more so benchmark instances use the isolated state above.
        os.environ["WARDEN_STATE_DIR"] = state_dir
        import agent.warden as warden_module

        warden_module = importlib.reload(warden_module)

        os.environ["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing"
        default_warden = warden_module.Warden("baseline-default")
        default_warden._log = lambda decision: decision

        os.environ["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing,beet"
        beet_warden = warden_module.Warden("baseline-beet")
        beet_warden._log = lambda decision: decision

        results = [
            _score("Plain denylist", baseline_action, risky, routine),
            _score(
                "Wagent default",
                _warden_classifier(default_warden),
                risky,
                routine,
            ),
            _score(
                "Wagent default + beet",
                _warden_classifier(beet_warden),
                risky,
                routine,
            ),
        ]

        source_note = "includes tests/test_warden.py" if included_warden else "tests/test_warden.py skipped"
        print(f"Cases: {len(risky)} risky, {len(routine)} routine ({source_note}).")
        if skip_reason:
            print(f"Skip reason: {skip_reason}")
        print()
        print(
            "| System | Risky blocked | Risky asked | TP/FN | Routine blocked | "
            "Routine asked | Precision (95% Wilson CI) | Recall (95% Wilson CI) | "
            "False-block rate (95% Wilson CI) |"
        )
        print(
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for result in results:
            print(
                f"| {result.name} | {result.risky_blocked} | {result.risky_asked} | "
                f"{result.true_positives}/{result.false_negatives} | "
                f"{result.routine_blocked} | {result.routine_asked} | "
                f"{_format_rate(result.precision)} | {_format_rate(result.recall)} | "
                f"{_format_rate(result.false_block_rate)} |"
            )

        missed_by_family: dict[str, int] = {}
        for family, _, item in risky:
            if baseline_action(item) not in CAUGHT_ACTIONS:
                missed_by_family[family] = missed_by_family.get(family, 0) + 1
        missed = ", ".join(
            f"{family} ({count})" for family, count in sorted(missed_by_family.items())
        )
        print()
        print(f"Baseline risky families missed: {missed or 'none'}")

        false_blocks = [description for description, item in routine if baseline_action(item) == "block"]
        print("Baseline routine cases wrongly blocked:")
        if false_blocks:
            for description in false_blocks:
                print(f"- {description}")
        else:
            print("- none")

        print()
        print(
            "Caveat: cases were written by the Wagent authors, so this measures relative "
            "performance on one shared set, not real-world accuracy."
        )


if __name__ == "__main__":
    main()
