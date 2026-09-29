# Agent Warden

Collaborative Flower Agents whose actions are checked before they run. When one node's warden blocks something, it turns the block into a tested rule and shares it, so every node in the federation is protected.

Built at the Flower Collaborative Agent Hackathon, Stanford, September 29, 2026.

## Why

In September 2026, OpenAI reported that an agent in training escaped its sandbox through a DNS resolver. Monitoring took 15 minutes to flag it, repeat attempts went unflagged, and the automatic shutdown failed. [FelonyBench](https://www.felonybench.com/) counts 24 incidents where lab agents affected third parties.

Monitors that work alone and react in minutes don't scale to many agents. Agent Warden puts the check in code, in front of every tool call, and lets nodes teach each other.

## How it works

```
agent asks to run a tool
        │
   Warden.check ── allowed ──▶ tool runs (filesystem connector or Grid)
        │
     blocked (0.03 ms)
        │
   Warden.evolve: propose broader rules, replay each against known-good calls,
                  keep the broadest one with zero false alarms
        │
   signature sent to other nodes over the Grid ──▶ their wardens enforce it
```

- **Check before run.** The model never gets the final say: a blocked call never reaches the connector or the Grid, even if the model ignores its instructions.
- **Three families of rules:** sandbox escape (paths outside the allowed folder), credential access (keys, tokens, secret material), data exfiltration (raw record IDs sent to other agents).
- **Self-improving.** Each block produces candidate rules from broad to narrow. Every candidate is replayed against `agent/known_good.py`, and the broadest one with no false alarms is adopted and shared.
- **Human-supervised.** Anything the warden can't generalize safely stays narrow; humans add known-good calls to tighten the check.

## Results (local replay)

| Test | Result |
|---|---|
| Built-in rules on 6 attack calls | 6 blocked |
| Built-in rules on 5 normal calls | 5 allowed |
| Signature from node A enforced on node B | variant blocked in 0.035 ms |
| One block, narrow rule | catches 1 of 5 unseen variants |
| One block, evolved rule | catches 3 of 5 unseen variants, 0 false alarms |

Run them:

```bash
python tests/test_warden.py
python tests/test_evolve.py
```

## Run on SuperGrid

```bash
uv sync
uv run flwr build
uv run flwr login supergrid
uv run flwr chat
# at the prompt
/load .
```

Model credentials come from the SuperNode environment (`FLWR_MODEL_API_KEY`). Never commit keys; `.env` and `keys/` are ignored.

## Layout

| File | What it does |
|---|---|
| `agent/agent_app.py` | Collaborative AgentApp loop with every tool call routed through the warden |
| `agent/warden.py` | Rules, checks, signature sharing, rule evolution |
| `agent/known_good.py` | Normal calls a new rule must never block |
| `tests/` | Local replays of attacks, sharing, and evolution |

## Use with Claude Code

Agent Warden can run as a Claude Code `PreToolUse` hook, blocking matching tool
calls before they execute. See the [hook setup guide](hooks/README.md) for the
example settings, persistent shared-rule directory, and failure behavior.

## Limits

- Rules are pattern matches, so they can be phrased around. Evolution narrows that gap; it doesn't close it.
- Warden broadcasts are trusted without signatures. A real deployment would sign them.
- The model relays broadcasts through Grid tools; sending them directly from code would be more reliable.

Based on the Flower Collaborative AgentApp template (Apache 2.0).
