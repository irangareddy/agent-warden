# Changelog

## 0.3.5 · September 29, 2026

- A 1-minute narrated film, linked from the top of the README: https://irangareddy.github.io/wagent/film/

## 0.3.4 · September 29, 2026

- Show the Discord alerts screenshot on the Flower Hub page (image served from GitHub).

## 0.3.3 · September 29, 2026

- Fix the Flower Hub page failing to load: write the top links as standard Markdown links.

## 0.3.2 · September 29, 2026

- Show full GitHub, Flower Hub, release and changelog addresses at the top of the README, so they read as links on the Flower Hub page.

## 0.3.1 · September 29, 2026

- Links to the GitHub repository from the Flower Hub page (README and project URLs).

## 0.3.0 · September 29, 2026

First release, built at the Flower Collaborative Agent Hackathon, Stanford.

**Wagent is a warden for your AI agents: when one is stopped, the rest learn from it, without sharing any data.**

### What's in it
- Every tool call is checked in code before it runs (median 0.03 ms). Block, allow, or ask a human.
- A block becomes the broadest rule that still allows normal work, travels through the Flower coordinator, and each agent tests it on its own work before using it.
- Shared rules are rate-limited (3 new rules per message, 20 per agent); extra rules wait for review.
- Rule packs shaped like skills: `secrets`, `git-safety`, `publishing`, `customer-data`, plus an example `beet` pack.
- Hooks for Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI and Grok.
- Mixed-model fleets: agents can run on Nebius Token Factory models (Kimi-K2.7-Code, MiniMax-M3) next to GPT. Flower Endeavor is supported for evaluation.
- Alerts in Discord for blocks, approvals and run results.
- A local demo page (`python3.12 demo/server.py`) with a live SuperGrid attack button and a recorded replay.

### Measured
- 3 false alarms in 39,633 real commands (0.02%) from 1,500 runs of the Hugging Face dataset `nebius/SWE-agent-trajectories`, all checked by hand.
- 81% of attacks caught vs 41% for a plain denylist on the same cases, with no routine work blocked.
- Sharing rules raised the attacks every agent stops from 10% to 31% in a 4-agent test.
- Live on Flower SuperGrid: one agent's catch protected all four agents, across three model providers (runs 13331100501952200106, 8508852592345920671, 12969821724815512231).

### Not yet
- Signed rules are built on the `signed-rules` branch, not merged.
- Approving held actions from Discord or Flower.
- A blind red team and a larger held-out evaluation.
