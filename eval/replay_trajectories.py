"""How often does Wagent flag real coding-agent work it has never seen?

Replays commands from nebius/SWE-agent-trajectories (CC-BY-4.0): SWE-agent
runs solving real GitHub issues. Each agent step ends with its command in a
code block; every command goes through Wagent as a Bash tool call.

The trajectories are unlabeled, so a flagged command is either a real catch or
a false alarm. The flagged rate is an upper bound on false alarms until the
flagged set (written to a CSV) is hand-labeled.

    python3.12 eval/replay_trajectories.py --trajectories 500
"""

import argparse
import collections
import csv
import json
import os
import random
import re
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="wagent-replay-")

ROWS_API = (
    "https://datasets-server.huggingface.co/rows?dataset=nebius/SWE-agent-trajectories"
    "&config=default&split=train&offset={offset}&length={length}"
)
CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def fetch_commands(trajectories: int, cache: str) -> list[dict]:
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    rows = []
    for offset in range(0, trajectories, 100):
        url = ROWS_API.format(offset=offset, length=min(100, trajectories - offset))
        with urllib.request.urlopen(url, timeout=120) as resp:
            rows.extend(r["row"] for r in json.load(resp)["rows"])
    commands = []
    for run, row in enumerate(rows):
        steps = [m for m in row["trajectory"] if m.get("role") == "ai"]
        for step, message in enumerate(steps):
            blocks = CODE_BLOCK.findall(message.get("text") or "")
            if blocks and blocks[-1].strip():
                commands.append({"run": run, "instance_id": row["instance_id"], "model_name": row["model_name"],
                                 "step": step, "command": blocks[-1].strip()})
    with open(cache, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c) + "\n" for c in commands)
    return commands


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", type=int, default=500)
    ap.add_argument("--packs", default="secrets,git-safety,publishing")
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "wagent-nebius-commands.jsonl"))
    ap.add_argument("--sample", type=int, default=15)
    opt = ap.parse_args()

    os.environ["WARDEN_RULEPACKS"] = opt.packs
    from agent.warden import Warden
    from eval.baseline import wilson_interval

    commands = fetch_commands(opt.trajectories, opt.cache)
    occurrences = collections.Counter(c["command"] for c in commands)
    w = Warden("replay")
    w._log = lambda d: d

    flagged = []
    actions = collections.Counter()
    weighted = collections.Counter()
    by_rule = collections.Counter()
    for command, count in occurrences.items():
        d = w.check({"type": "function_call", "name": "Bash", "arguments": json.dumps({"command": command})})
        actions[d.action] += 1
        weighted[d.action] += count
        if d.action != "allow":
            by_rule[d.rule_id] += 1
            flagged.append((d.action, d.rule_id, count, command))

    n_unique, n_total = len(occurrences), sum(occurrences.values())
    trajectories = len({c["run"] for c in commands})
    print(f"nebius/SWE-agent-trajectories: {trajectories} runs, {n_total} commands, {n_unique} unique; packs={opt.packs}")
    for action in ("block", "ask"):
        k = actions[action]
        lo, hi = wilson_interval(k, n_unique)
        print(f"  {action:5} {k:5} of {n_unique} unique ({k / n_unique:.2%}; 95% range {lo:.2%} to {hi:.2%}); "
              f"{weighted[action]} of {n_total} occurrences")
    print("  flagged by rule:", ", ".join(f"{r} {c}" for r, c in by_rule.most_common(10)) or "none")

    out = opt.cache + ".flagged.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["action", "rule_id", "count", "command", "human_label"])
        writer.writerows(row + ("",) for row in flagged)
    print(f"  all flagged commands: {out} (fill in human_label: catch / false-alarm)")

    random.Random(0).shuffle(flagged)
    for action, rule, count, command in flagged[: opt.sample]:
        print(f"    {action:5} {rule:28} {command[:160].replace(chr(10), '⏎')}")
    print("Caveat: unlabeled data. Flagged = real catch or false alarm; the rate is an upper bound on false alarms.")


if __name__ == "__main__":
    main()
