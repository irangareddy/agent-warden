# Wagent

**Wagent is a warden for your AI agents: when one is stopped, the rest learn from it, without sharing any data.**

It's 2 a.m. and your agents are still working. One is fixing a test, one is preparing a release, and one has just found a `.env` file with production keys that has nothing to do with its task. Nobody is watching, and a prompt that says "don't touch secrets" is a request, not a guarantee.

Wagent checks every tool call before it runs. It stops the risky ones, asks you about the ones that depend on context, and turns each catch into a rule the rest of your fleet can use, so the next agent that tries the same thing is stopped too.

Built at the Flower Collaborative Agent Hackathon, Stanford, September 29, 2026.

## What Wagent does

**Checks every action in code.** Each tool call is checked before it runs, in under a millisecond. A blocked call never reaches the tool, even if the model was told to go ahead.

**Turns one catch into protection for everyone.** When an agent is stopped, Wagent widens the pattern as far as it safely can, then shares it through Flower's coordinator. Only the rule travels, never data, files or prompts.

**Keeps bad rules out.** Every agent tests a new rule against its own normal work before adopting it. A rule that would block routine work, or match almost anything, is turned away, so one careless or malicious node can't lock up the fleet.

**Asks you when it can't know.** `gh pr merge 644` doesn't say whether it's going to production. For actions like that, Wagent asks you instead of guessing. You can review every rule the fleet learns and keep or remove it.


## The numbers, and how to check them

| What we measured | Result | Check it |
|---|---|---|
| 70 real tool calls from a coding-agent fleet (Codex, Claude Code, OpenClaw) | No routine work blocked (37 of 40 allowed, 3 merges ask first). All 15 rephrased attacks stopped (12 blocked, 3 asked). 12 of 15 risky actions stopped. | `tools/measure_audit.py` on your own audit file; ours stays private, only totals are published |
| Learning over time, 48 attacks in 30 random orders | With your reviews, catch rate on attacks it hadn't seen rose from 79% to 96% after 24 attacks. False alarms on held-out routine work: 0.5 in 20. | `python3.12 eval/learning_curve.py --start default` |
| Speed | Median check 0.03 ms; under 5 ms on a 20,000-character command | `tests/test_beet_rules.py` includes the timing test |
| Live on Flower SuperGrid, 4 nodes (run 3752845067342549556) | Only the Backend agent guards customer exports. It blocked an export read and shared the rule; the other 3 agents, whose own rules allowed the follow-up read, each blocked it with Backend's rule | `tests/test_shared_only.py` offline; the scripted attack below, live |

Learning only helps when someone flags what got through: on its own blocks alone, Wagent went from 79% to 80%. That's why review is part of the product, not an afterthought.

## Use it with your agents

Set up a project, then connect your agent's hook:

```bash
python3 tools/warden.py init --project . --harness claude --write-hook --yes
python3 tools/warden.py test --project . --tool Bash "cat .env"
python3 tools/warden.py review --project . --list
```

`init` finds your project's routine test and build commands and records them as work Wagent must never block. `review` shows what the fleet has learned so you can keep or remove each rule. Hook files change only with `--write-hook`, and existing settings are backed up first.

| Harness | How Wagent connects |
|---|---|
| Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, Grok | Their before-tool hooks, one shared adapter ([setup](hooks/README.md)) |
| OpenClaw, Hermes, OpenCode | Plugin examples (untested) |
| Flower Agents | Built in: this AgentApp |

## Run a fleet on Flower SuperGrid

Requires Docker, [uv](https://docs.astral.sh/uv/), and a Flower account with Agent access.

```bash
uv run flwr login supergrid
bash scripts/setup_fleet.sh
docker compose -f fleet/compose.yaml up
uv run python tools/ask.py --federation @<you>/wagent-demo "Ask every node for a one-line status."
```

Choose the agents' model with `WARDEN_MODEL` (default `openai/gpt-5.6-terra`). Flower's docs also name `openai/gpt-5.6-sol` and `openai/gpt-5-nano`. `flwrlabs/endeavor-1.0` (Flower Endeavor) is supported for evaluation: Wagent calls it without streaming, as Flower's own Endeavor agent does. In our runs on September 29, 2026, Endeavor returned provider errors, so the demo uses the default.

Each of the four demo nodes sees only its own folder and its own key, and uses fake data. [fleet/README.md](fleet/README.md) walks through each step.

To watch one agent's catch protect the others, send the scripted attack. It runs only on machines whose operator set `WARDEN_ALLOW_RED_TEAM=1`, so a prompt alone can't turn it on:

```bash
uv run python tools/ask.py --federation @<you>/wagent-demo "[SCRIPTED-ATTACK] target=Backend read=/data/backend/exports/customers-2026-09.csv"
```

## How it works

```
agent asks to run a tool
      │
  1. CHECK     in code, under 1 ms ──── allow ──► tool runs
      │                            └─── ask ────► you decide
      │ block: the call never runs
  2. WIDEN     try broader patterns; keep the broadest that blocks no normal work
      │
  3. SHARE     node ──► coordinator ──► every other node
      │
  4. VALIDATE  each node tests the rule on its own normal work before using it
```

## Rule packs

Rules come in packs shaped like agent skills: a plain-English `SKILL.md`, the rules, and the normal actions the pack must never block.

```
agent/rulepacks/<name>/
  SKILL.md          what it protects and when to turn it on
  rules.json        block and ask rules
  known_good.json   normal work the pack must never block
```

The defaults are `secrets`, `git-safety` and `publishing`; `customer-data` is opt-in. Choose packs with `WARDEN_RULEPACKS`, and add your own folder with `WARDEN_RULEPACKS_DIR`. Skills tell agents the rules; Wagent enforces them.

## What's real today (v0.2, preview)

| Part | Status |
|---|---|
| Check engine and default packs | Ready |
| Flower AgentApp: checks, sharing, validation | Ready; run live on a 4-node SuperGrid fleet |
| Setup and review CLI | Ready |
| Hooks for Claude Code, Codex, Cursor, Copilot, Gemini CLI, Grok | Preview: tested against each tool's documented hook format (41 cases), not yet run inside every tool. They fail open by default; set `AGENT_WARDEN_FAIL_CLOSED=1` to fail closed |
| Rule learning | Preview: widens file paths well, commands less so. Review what it learns |
| `beet` pack | Example from one team's setup; copy it, don't enable it as-is |
| OpenClaw, Hermes, OpenCode plugins; scripted attack | Examples only |

What's not done yet:
- **Rules can be phrased around.** Wagent is a layer on top of sandboxes and permissions, not a replacement for them.
- **Shared rules are validated but not signed.** Signed rules are next.
- **"Ask" on Flower holds the action** but has no approval screen yet. Approval cards are next.
- **Rules a fleet learns don't sync to local hooks yet.**
- **Evaluated on coding agents only.** The real-history numbers come from one team, and the rules were tuned on that same data. A held-out evaluation on other teams' data is next.

## Layout

| Path | What it does |
|---|---|
| `agent/agent_app.py` | The Flower AgentApp; every tool call goes through Wagent |
| `agent/warden.py` | Checks, widening rules, validation |
| `agent/relay.py` | Sharing rules node → coordinator → nodes |
| `agent/rulepacks/` | Rule packs |
| `hooks/` | Hooks for coding-agent harnesses |
| `tools/` | Setup CLI, prompts from the terminal, private audit replay |
| `eval/` | Learning-over-time evaluation |
| `fleet/`, `scripts/` | Demo fleet, setup, one-command demo |
| `tests/` | The 12 demo suites |

Based on the Flower Collaborative AgentApp template. Apache 2.0.
