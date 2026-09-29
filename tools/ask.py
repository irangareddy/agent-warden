"""Send one prompt to Wagent on a federation and print the run's events.

Uses the same calls as `flwr chat`, without the interactive screen, so demo
steps can be scripted and logged.

    uv run python tools/ask.py "Ask every node for a one-line status."
    uv run python tools/ask.py --federation @irangareddy/beet-fleet "..."
"""

import argparse
import json
import os
import sys
from pathlib import Path

from flwr.cli.chat.chat_app import parse_task_event, start_chat_run
from flwr.cli.chat.chat_local_agent import build_local_agent
from flwr.cli.constant import CHAT_SUPERGRID_CONNECTION_NAME
from flwr.cli.flower_config import read_superlink_connection
from flwr.cli.utils import init_http_client_from_connection
from flwr.proto.control_pb2 import StreamRunEventsRequest  # pylint: disable=E0611

ROOT = Path(__file__).resolve().parent.parent


def _short(value: object, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--federation", default="@irangareddy/beet-fleet")
    args = parser.parse_args()

    connection = read_superlink_connection(
        os.environ.get("FLWR_CHAT_SUPERLINK", CHAT_SUPERGRID_CONNECTION_NAME)
    )
    stub = init_http_client_from_connection(connection)
    try:
        local = build_local_agent(ROOT)
        run_id, series_id = start_chat_run(
            stub, args.prompt, args.federation, None,
            local.app_spec, local.fab_hash, local.fab_content,
        )
        print(f"run {run_id} (series {series_id}) on {args.federation}\n", flush=True)
        text: list[str] = []
        for res in stub.StreamRunEvents(StreamRunEventsRequest(run_id=run_id)):
            kind, payload = parse_task_event(res.task_event)
            data_type = payload.get("type", kind)
            if data_type == "response.output_text.delta":
                text.append(str(payload.get("delta", "")))
                continue
            if text:
                print("".join(text), flush=True)
                text = []
            if data_type == "function_call":
                print(f"→ {payload.get('name')} {_short(payload.get('arguments'))}", flush=True)
            elif data_type == "function_call_output":
                print(f"← {_short(payload.get('output'))}", flush=True)
            elif data_type in {"response.failed", "error"} or "fail" in str(kind).lower():
                print(f"!! {kind}: {_short(payload, 600)}", flush=True)
        if text:
            print("".join(text), flush=True)
        print(f"\nrun {run_id} finished")
    finally:
        stub.close()


if __name__ == "__main__":
    sys.exit(main())
