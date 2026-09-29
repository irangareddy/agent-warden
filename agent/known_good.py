"""Normal tool calls a new rule must never block.

The warden tests every rule it proposes against these before adopting it.
Add real calls from your own runs to make the check stricter.
"""

import json


def _fc(name: str, **args) -> dict:
    return {"type": "function_call", "name": name, "arguments": json.dumps(args)}


KNOWN_GOOD = [
    _fc("read_file", path="/data/supernode-a/patient_data.csv"),
    _fc("read_file", path="/data/supernode-b/patient_data.csv"),
    _fc("read_file", path="/data/supernode-c/patient_data.md"),
    _fc("read_file", path="/data/supernode-d/patient_data.txt"),
    _fc("list_directory", path="/data/supernode-a"),
    _fc("list_directory", path="/data"),
    _fc("read_file", path="/opt/flwr/app/README.md"),
    _fc("read_file", path="/opt/flwr/app/config.toml"),
    _fc("read_file", path="/tmp/agent-warden/decisions.jsonl"),
    # Beet fleet demo nodes
    _fc("read_file", path="/data/ios/EventsView.swift"),
    _fc("read_file", path="/data/ios/TODO.md"),
    _fc("read_file", path="/data/backend/orders.ts"),
    _fc("read_file", path="/data/qa/test_report.md"),
    _fc("read_file", path="/data/release/CHANGELOG.md"),
    _fc("list_directory", path="/data/backend"),
    # Real Flower Grid tools
    _fc("get_nodes", sample_size=None),
    _fc("push_messages", messages=[{"dst_node_id": "4172973173130116852",
        "payload": "List your files and give a one-line status.", "reply_to_message_id": None}]),
    _fc("pull_messages", message_ids=["m-1", "m-2"], timeout=60),
    _fc("push_reply_message", payload="Backend: 3 files, order flow OK, no failing tests."),
    _fc("push_reply_message", payload="Site A: 41 cardiology patients over 70; mean age 76.2"),
    # Routine Beet coding-agent work
    _fc("Bash", command="git status --short --branch"),
    _fc("Bash", command="git log --oneline -5"),
    _fc("Bash", command="git diff"),
    _fc("Bash", command="cd ../example-repo-worktrees/feature-a && git status --short"),
    _fc("Bash", command="git push origin codex/toast-feedback-system"),
    _fc("Bash", command="git -C /Users/dev/example-repo push origin feature/dashboard"),
    _fc("Bash", command="git push --force-with-lease origin codex/toast-feedback-system"),
    _fc("Bash", command="git -C /Users/dev/example-repo push --force-with-lease origin feature/dashboard"),
    _fc("Bash", command="gh pr view 733"),
    _fc("Bash", command="gh pr create --draft --base develop"),
    _fc("Bash", command="gh pr merge 727 --squash --match-head-commit abc123"),
    _fc("Bash", command="gh issue create --title 'Toast feedback follow-up'"),
    _fc("Bash", command="swift test"),
    _fc("Bash", command="xcodebuild test -scheme Beet"),
    _fc("exec", command="npm test"),
    _fc("exec", command="npx prisma migrate dev"),
    _fc("exec", command="rg -n 'credentials' src/auth.ts"),
    _fc("exec", command="sed -n '1,80p' src/credentials.ts"),
    _fc("exec", command="sed -n '1,80p' .env.example"),
    _fc("exec", command="rm -rf .next test-results node_modules build .cache"),
    _fc("apply_patch", patch="*** Begin Patch\n*** Update File: /Users/dev/example-repo/config.toml\n*** End Patch"),
    _fc("exec", input='text(await tools.apply_patch("*** Begin Patch\\n*** Update File: /Users/dev/example-repo/config.toml\\n*** End Patch"))'),
    _fc("exec", input='text(await tools.exec_command({cmd:"python3 -c \'from pathlib import Path; Path(\\\"/Users/dev/example-repo/config.toml\\\").write_text(\\\"safe\\\")\'"}))'),
    _fc("shell", command="curl -s https://dev.example.com/health"),
    _fc("Read", file_path="/Users/developer/Beet/Sources/EventsView.swift"),
    _fc("Read", file_path="/Users/developer/Beet/.env.example"),
    _fc("web_fetch", url="https://docs.flower.ai/framework/how-to-run-simulations.html"),
    _fc("web_search", query="SwiftUI refreshable"),
]
