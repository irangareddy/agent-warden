"""Does Wagent get better as it sees more attacks? A sequential learning curve.

Attacks arrive one at a time in random order. After each one, Wagent learns:
  * a call it blocked is evolved into a broader rule (automatic);
  * a call it missed is flagged by a human reviewer and evolved the same way
    (the `review` step), unless --no-human.
Every learned rule must pass validation against the project's known-good calls.
After each step we measure, on data the learner has NOT seen:
  * catch rate on the attacks still to come,
  * false alarms on held-out routine calls (half the routine set; the other
    half seeds known-good, as `wagent init` does).

Data: the synthetic risky/routine cases in tests/test_beet_rules.py (written by us).

    python3.12 eval/learning_curve.py [--start cold|default] [--no-human] [--orders 30]
"""

import argparse
import contextlib
import io
import json
import os
import random
import statistics
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ["WARDEN_STATE_DIR"] = tempfile.mkdtemp(prefix="wagent-curve-")
with contextlib.redirect_stdout(io.StringIO()):
    try:
        import test_beet_rules as cases
    except SystemExit:
        pass
import agent.warden as W  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--start", choices=["cold", "default"], default="cold")
ap.add_argument("--no-human", action="store_true")
ap.add_argument("--orders", type=int, default=30)
opt = ap.parse_args()

if opt.start == "cold":
    os.environ["WARDEN_RULEPACKS"] = ""
    W.BUILT_IN_RULES = []
else:
    os.environ["WARDEN_RULEPACKS"] = "secrets,git-safety,publishing"

attacks = [item for _, _, item in cases.RISKY]
routine = [c[-1] for c in cases.ROUTINE]


def as_known_good(item):
    return {"name": item["name"], "arguments": json.loads(item["arguments"])}


def run(seed):
    rng = random.Random(seed)
    order = attacks[:]
    rng.shuffle(order)
    rt = routine[:]
    rng.shuffle(rt)
    seed_good, held_out = rt[: len(rt) // 2], rt[len(rt) // 2:]
    state = tempfile.mkdtemp(prefix="wagent-run-")
    W.STATE_DIR, W.SIGNATURES_FILE = state, os.path.join(state, "signatures.json")
    W.LOG_FILE, W.REJECTED_FILE = os.path.join(state, "d.jsonl"), os.path.join(state, "rej.json")
    w = W.Warden("curve")
    w._log = lambda d: d
    w._log_rule = lambda *a, **k: None
    w.pack_known_good = w.pack_known_good + [as_known_good(i) for i in seed_good]
    catch, fa, rules = [], [], []
    for k in range(len(order) + 1):
        unseen = order[k:]
        if unseen:
            catch.append(sum(w.check(i).action != "allow" for i in unseen) / len(unseen))
        fa.append(sum(w.check(i).action == "block" for i in held_out))
        rules.append(len(w.shared))
        if k == len(order):
            break
        item = order[k]
        d = w.check(item)
        if d.action == "allow":
            if opt.no_human:
                continue
            d = W.Decision(False, item["name"], "human-flag", "flagged", "flagged in review",
                           "human", 0.0, float(k), "block")
        rule, _ = w.evolve(d, item)
        w.learn(rule)
    return catch, fa, rules, len(held_out)


results = [run(s) for s in range(opt.orders)]
n = len(attacks)
mode = f"start={opt.start}, learning={'own blocks only' if opt.no_human else 'own blocks + human flags'}"
print(f"{mode}; {n} attacks, {len(routine)} routine ({results[0][3]} held out), {opt.orders} random orders")
print(f"{'seen':>5} {'catch unseen':>13} {'false alarms':>13} {'rules':>6}")
for k in list(range(0, n, max(1, n // 8))) + [n - 1]:
    c = statistics.mean(r[0][k] for r in results)
    lo, hi = min(r[0][k] for r in results), max(r[0][k] for r in results)
    f = statistics.mean(r[1][k] for r in results)
    ru = statistics.mean(r[2][k] for r in results)
    print(f"{k:>5} {c:>7.0%} ({lo:.0%}-{hi:.0%}) {f:>8.2f}/{results[0][3]} {ru:>6.1f}")
print(f"final false alarms on held-out routine: mean {statistics.mean(r[1][-1] for r in results):.2f}")
