"""Compatibility export for the former monolithic Beet rule module."""

from agent.rulepacks import load_packs


BEET_RULES, _BEET_KNOWN_GOOD = load_packs(
    ["secrets", "git-safety", "publishing", "beet"]
)
