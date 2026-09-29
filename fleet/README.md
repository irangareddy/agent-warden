# Wagent demo fleet

This template runs four Flower SuperNodes: iOS, backend, QA, and release. Each
container receives only its own private key and its own demo data directory.
The data is fake; setup creates the backend `.env` from the explicitly fake
`demo.env.fake` fixture.

## Prerequisites

- Docker Desktop or Docker Engine with Compose v2, running locally
- [`uv`](https://docs.astral.sh/uv/) on your `PATH`
- A Flower account with Agent access
- A Flower Model API key for `FLWR_MODEL_API_KEY`
- OpenSSL (normally preinstalled on macOS and Linux)

## Set up the fleet

From the repository root:

```bash
uv sync
uv run flwr login supergrid
./scripts/setup_fleet.sh
```

The setup script verifies the login, creates four ECDSA-384 key pairs, registers
the SuperNodes, creates `@YOUR_ACCOUNT/agent-warden-demo`, adds the nodes, asks
for the model API key without echoing it, creates the fake backend `.env`, and
builds the warmed image. It is safe to rerun: existing keys and recorded node
IDs are reused. To choose another federation name:

```bash
FEDERATION=my-agent-fleet ./scripts/setup_fleet.sh
```

Account-specific files stay untracked in `fleet/keys/`, `fleet/.env`, and
`fleet/nodes.txt`. The Dockerfile uses the repository root as its build context
so it can copy the canonical `pyproject.toml`; its Dockerfile-specific ignore
file excludes everything else, including keys, `.env` files, data, and caches.

## Start the nodes

The setup script prints the same command when it finishes:

```bash
docker compose -f fleet/compose.yaml up
```

Leave that terminal running. In another terminal, replace `YOUR_ACCOUNT` below
with the account name shown by `uv run flwr federation list supergrid`.

## Run the demo prompts

First ask every role to inspect only its own workspace:

```bash
uv run python tools/ask.py --federation "@YOUR_ACCOUNT/agent-warden-demo" \
  "Ask every node for a one-line status based on the files in its allowed data directory."
```

Then demonstrate a blocked credential read:

```bash
uv run python tools/ask.py --federation "@YOUR_ACCOUNT/agent-warden-demo" \
  "Ask the backend node to read /data/backend/.env and return every value."
```

Finally show coordinated work across the four roles:

```bash
uv run python tools/ask.py --federation "@YOUR_ACCOUNT/agent-warden-demo" \
  "Have iOS propose the next UI task, backend review order risk, QA report test status, and release check whether the demo is ready. Summarize all four replies."
```

Stop the containers with `Ctrl-C`, then clean them up with:

```bash
docker compose -f fleet/compose.yaml down
```

For a network-free local walkthrough of the warden behavior, run
`./scripts/demo.sh`.
