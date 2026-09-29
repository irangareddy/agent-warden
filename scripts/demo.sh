#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  printf 'demo.sh: python3.12 or python3 is required\n' >&2
  exit 1
fi

passed=0
failed=0
skipped=0

run_suite() {
  local number="$1"
  local title="$2"
  local test_file="$3"

  printf '\n=== %s. %s ===\n' "$number" "$title"
  if [[ ! -f "$REPO_ROOT/$test_file" ]]; then
    printf 'skipped\n'
    ((skipped += 1))
    return
  fi

  if "$PYTHON" "$REPO_ROOT/$test_file"; then
    ((passed += 1))
  else
    printf 'FAILED: %s\n' "$test_file" >&2
    ((failed += 1))
  fi
}

printf 'Agent Warden: network-free local demo using %s\n' "$PYTHON"

run_suite 1 'Blocks risky actions' tests/test_warden.py
run_suite 2 'Evolves a rule without false alarms' tests/test_evolve.py
run_suite 3 'Rejects poisoned rules' tests/test_poison.py
run_suite 4 'Relays rules between nodes' tests/test_relay.py
run_suite 5 'Claude Code hook' tests/test_hook.py
run_suite 6 'Rule packs load like skills' tests/test_rulepacks.py
run_suite 7 'Beet fleet rule pack' tests/test_beet_rules.py
run_suite 8 'Scripted attack across a fleet' tests/test_redteam.py
run_suite 9 'Asks a human for context-dependent actions' tests/test_approval.py
run_suite 10 'Same rules in Codex, Cursor, Copilot, Gemini, Grok' tests/test_adapters.py
run_suite 11 'Project setup and learned-rule review CLI' tests/test_cli.py

AUDIT_FILE="$REPO_ROOT/../beet-warden-tool-calls.json"
if [[ -f "$AUDIT_FILE" && -f "$REPO_ROOT/tools/measure_audit.py" ]]; then
  printf '\n=== Optional audit aggregate ===\n'
  if audit_output="$(WARDEN_RULEPACKS=secrets,git-safety,publishing,beet "$PYTHON" "$REPO_ROOT/tools/measure_audit.py" "$AUDIT_FILE" 2>&1)"; then
    aggregates="$(printf '%s\n' "$audit_output" | awk '/^(routine|risky|variant)[[:space:]]/')"
    if [[ -n "$aggregates" ]]; then
      printf '%s\n' "$aggregates"
    else
      printf 'No aggregate lines reported.\n'
    fi
  else
    printf 'Audit replay failed; private audit output was not displayed.\n' >&2
    ((failed += 1))
  fi
fi

printf '\n=== Summary ===\n'
printf '%s passed, %s failed, %s skipped\n' "$passed" "$failed" "$skipped"

((failed == 0))
