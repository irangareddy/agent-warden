#!/usr/bin/env python3
"""Backward-compatible Claude Code entry point for Agent Warden."""

try:
    from .warden_hook import main as shared_main
except ImportError:  # Direct execution puts hooks/ rather than the repo on sys.path.
    from warden_hook import main as shared_main


def main() -> int:
    return shared_main(["--harness", "claude"])


if __name__ == "__main__":
    raise SystemExit(main())
