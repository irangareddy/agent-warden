# Wagent

**Wagent is a warden for your coding agents.** It checks every tool call before it runs, stops the risky ones, and turns each catch into a rule the rest of your fleet can use. Rules travel through Flower's coordinator, and each agent tests a new rule against its own normal work before adopting it, so bad or overly broad rules are turned away. Only the rule is shared, never code, files or prompts. When an action depends on context, like merging to production, Wagent asks you instead of guessing, and you can review every rule the fleet learns.

Built at the Flower Collaborative Agent Hackathon, Stanford, September 29, 2026.

## Why

AI agents now run unsupervised with real access: repositories, credentials, production deploys. In September 2026 OpenAI reported an agent in training reaching an outside chatbot through a DNS resolver; monitoring took about 15 minutes to flag it, repeat attempts went unflagged, and the automatic stop failed. A public tracker, [FelonyBench](https://www.felonybench.com/), lists incidents where lab agents affected third parties.

Prompts ask agents to behave. They don't guarantee it. Wagent enforces the rules in code, and makes one agent's catch protect the whole fleet.

## Try it in 30 seconds (no network)

```bash
git clone https://github.com/irangareddy/wagent && cd wagent
uv sync
bash scripts/demo.sh
```

The demo runs nine scenario suites and prints each step: blocking, rule evolution, poisoned-rule rejection, relay between nodes, rule packs, the Beet fleet pack, a scripted attack across a fleet, the Claude Code hook, and asking a human for context-dependent actions.

## Set up your project

Initialize a project-local rule pack and print the hook configuration for your
agent harness:

```bash
python3 tools/warden.py init --project . --harness claude --write-hook --yes
python3 tools/warden.py status --project .
python3 tools/warden.py test --project . --tool Bash "cat .env"
python3 tools/warden.py review --project . --list
```

`init` detects routine test/build commands, stores them as known-good calls, and
adds a project pack alongside the default `secrets`, `git-safety`, and
`publishing` packs. Without flags it prompts for the harness, packs, and pack
name. Learned rules remain enforced while pending; use `review --approve ID` to
add one to the project pack or `review --reject ID` to remove and permanently
reject that pattern. Hook files are only changed with `--write-hook`; existing
JSON is merged and backed up first.

## How it works

```
agent asks to run a tool
      │
  1. CHECK in code (< 1 ms)  ── allowed ──► tool runs
      │ blocked: the call never runs
  2. EVOLVE  propose broader rules, replay each against normal work,
             keep the broadest one with zero false alarms
      │
  3. SHARE   node ──► coordinator ──► every other node, in code
      │      (Flower nodes can't message each other; the coordinator relays)
  4. VALIDATE each node replays the rule on its OWN normal work;
             overbroad or poisoned rules are rejected
```

- **The model never has the final say.** A blocked call never reaches the connector or the Grid, even if the model was told to comply.
- **Rules come in packs**, shaped like agent skills (see below): credentials, git safety, publishing, and a company pack.
- **Nothing is shared but the rule.** No files, records, or prompts leave a node.

## Results

Full details: [notes on evaluation](#evaluation). Short version:

| Evaluation | Result |
|---|---|
| Scenario suites (`scripts/demo.sh`) | 9/9 pass |
| **Real agent history**: 70 tool calls from a coding-agent fleet (Codex, Claude Code, OpenClaw), private data, only totals published | **0 routine actions blocked** (37/40 allowed, 3 merges ask for approval) · **15/15 rephrased attacks stopped** (12 blocked, 3 sent for approval) · **12/15 risky actions stopped** (6 blocked, 6 sent for approval) |
| Adversarial inputs up to 30,000 characters | Slowest rule check under 1 ms |
| Live on Flower SuperGrid, 4-node fleet | Block in 0.06 ms, rule evolved and relayed; scripted attack: target blocked, rule validated and accepted by the coordinator, all 4 nodes blocked the probe |

Some actions can't be judged from the command alone: `gh pr merge 644` doesn't say whether it targets production. Those get a third outcome, **ask a human**, instead of a guess. The 3 remaining misses are debatable labels (resolving a merge conflict, opening a production pull request without merging it).

### Evaluation

1. **Scenarios we wrote** (optimistic by construction): 6/6 attacks blocked and 5/5 normal calls allowed by the core rules; an evolved rule caught 3/5 unseen variants where the narrow rule caught 1/5, with 0 false alarms; 3/3 poisoned rules rejected while the honest rule was accepted.
2. **Real history** (the honest score): see the table above. The first replay found 3 false alarms and several evasions (`git -C`, `+HEAD:` refspecs, config edits through patches); closing them produced the current numbers. The rules were tuned on this same data, so a held-out set is the next step.
3. **Performance**: the real-data replay exposed a rule that backtracked for seconds on long commands; after the fix, every rule stays under 50 ms on a 20,000-character adversarial string (tested) and under 1 ms in practice.
4. **Live**: models sometimes refused a requested attack on their own and sometimes didn't. That inconsistency is the reason the check lives in code. The scripted attack removes the model from the attack path so the demo is reproducible.

### Does it get better over time?

`eval/learning_curve.py` feeds 48 attacks one at a time in random order (30 orders). After each one, Wagent learns: a blocked call becomes an evolved rule, and a missed call is flagged by a human in review and evolved the same way. After every step it is scored on attacks it has **not seen yet**, and on 20 routine calls held out from its known-good set.

| Start | Learns from | Catch on unseen attacks: 0 → 12 → 24 seen | False alarms on held-out routine |
|---|---|---|---|
| Default packs | its own blocks + human flags | 79% → 93% → 96% | 0 → 0.5 of 20 |
| Default packs | its own blocks only | 79% → 81% → 80% | 0 → 0.5 of 20 |
| No rules at all | its own blocks + human flags | 0% → 23% → 30% | 0 → 0.5 of 20 |

What this shows: learning works when a human flags what got through; on its own, Wagent barely improves, because it only learns from what it already blocks. Learned rules also add a small number of false alarms on unseen normal work, which is why `wagent review` exists. The cases are ours (synthetic), so treat this as a mechanism test, not a real-world score.

## Run a fleet on Flower SuperGrid

Requires Docker, [uv](https://docs.astral.sh/uv/), and a Flower account with Agent access.

```bash
uv run flwr login supergrid
bash scripts/setup_fleet.sh        # keys, node registration, federation, node image
docker compose -f fleet/compose.yaml up
```

`fleet/README.md` walks through each step. The four demo nodes use fake data only; each container sees only its own folder and its own key.

Send prompts from the terminal (or use `uv run flwr chat`, then `/load .`):

```bash
uv run python tools/ask.py --federation @<you>/wagent-demo "Ask every node for a one-line status."
```

### Scripted attack (demo fleets only)

A node simulates an attack only if its operator sets `WARDEN_ALLOW_RED_TEAM=1` on that machine; a prompt alone can't switch it on. The demo fleet sets it.

```bash
uv run python tools/ask.py --federation @<you>/wagent-demo "[SCRIPTED-ATTACK] target=Backend read=/data/backend/.env"
```

## Three outcomes: allow, block, ask

Most actions are clearly fine or clearly dangerous. Some depend on context the command doesn't show, like merging a pull request or publishing a release. Rules can say `"action": "ask"`: the Claude Code hook then makes Claude ask you, and a Flower agent holds the action instead of running it. Block rules always win over ask rules.

## Rule packs (shaped like agent skills)

```
agent/rulepacks/<name>/
  SKILL.md          what it protects and when to enable it, in plain English
  rules.json        block rules
  known_good.json   normal actions the pack must never block
```

Enable with `WARDEN_RULEPACKS` (default `secrets,git-safety,publishing`; `beet` is opt-in). Add your own directory with `WARDEN_RULEPACKS_DIR`.

Skills tell agents the rules. Wagent enforces them.

## Use with Claude Code

Wagent also runs as a Claude Code `PreToolUse` hook that checks each tool call before it executes. It fails open by default so a broken hook never blocks your agent. See [hooks/README.md](hooks/README.md).

## Use with your agent

One shared hook now adapts Wagent to several coding-agent harnesses; see
[installation snippets and contract details](hooks/README.md).

| Native adapters | Generic bridge examples |
|---|---|
| Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, Grok | OpenClaw, Hermes, OpenCode (untested) |

## Layout

| Path | What it does |
|---|---|
| `agent/agent_app.py` | Collaborative AgentApp loop; every tool call goes through the warden |
| `agent/warden.py` | Checks, rule evolution, local validation |
| `agent/relay.py` | Rules travel node → coordinator → nodes in code |
| `agent/rulepacks/` | Rule packs |
| `agent/redteam.py` | Scripted attack for demo fleets |
| `hooks/` | Claude Code hook |
| `fleet/`, `scripts/` | Demo fleet template, setup, one-command demo |
| `tools/` | `ask.py` (prompts without the chat screen), `measure_audit.py` (replay a private audit, totals only) |
| `tests/` | Scenario suites |

## Limits and next steps

- Rules are patterns and can be phrased around. Evolution narrows the gap; hard isolation (sandboxes, OS or hardware policy) stays underneath. Wagent is the learning layer on top, not a replacement.
- Shared rules are validated locally but not yet cryptographically signed.
- The ask tier works in the Claude Code hook (Claude prompts the user). Inside Flower, ask actions are held without running; approval cards on Flower are next.
- The Claude Code hook uses local rules and packs; syncing rules from a fleet to it isn't built.
- Next: a held-out evaluation set, signed rules, approval cards on Flower.

Based on the Flower Collaborative AgentApp template (Apache 2.0).
