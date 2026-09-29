#!/usr/bin/env python3
"""Probe Nebius Token Factory text generation and function calling."""

import os
import sys
import time
from typing import Any


BASE_URL = "https://api.tokenfactory.tf-ca1.nebius.com/v1"
# Each Token Factory endpoint has its own key.
MODEL_KEYS = {
    "dedicated/flowerai/Kimi-K2.7-Code-1OUHWL": "NEBIUS_KIMI_API_KEY",
    "dedicated/flowerai/MiniMax-M3-OOLI9o": "NEBIUS_MINIMAX_API_KEY",
}
DUMMY_TOOL = {
    "type": "function",
    "name": "probe_echo",
    "description": "Return a probe message to the caller.",
    "parameters": {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _emitted_tool_call(response: Any) -> bool:
    return any(getattr(item, "type", None) == "function_call" for item in response.output)


def _probe_model(client: Any, model: str) -> bool:
    started = time.perf_counter()
    reachable = False
    text_ok = False
    tool_call_emitted = False
    failures: list[str] = []

    try:
        plain_response = client.responses.create(
            model=model,
            input="Reply with a short confirmation that the probe is reachable.",
        )
        reachable = True
        text_ok = bool((plain_response.output_text or "").strip())
    except Exception as exc:  # The exception class is safe; details may contain headers.
        failures.append(f"text request: {type(exc).__name__}")

    try:
        tool_response = client.responses.create(
            model=model,
            input="Call probe_echo exactly once with the message 'probe-ok'.",
            tools=[DUMMY_TOOL],
            tool_choice="required",
        )
        reachable = True
        tool_call_emitted = _emitted_tool_call(tool_response)
    except Exception as exc:  # The exception class is safe; details may contain headers.
        failures.append(f"tool request: {type(exc).__name__}")

    latency = time.perf_counter() - started
    print(
        f"{model}: reachable={'yes' if reachable else 'no'}, "
        f"text_ok={'yes' if text_ok else 'no'}, "
        f"tool_call_emitted={'yes' if tool_call_emitted else 'no'}, "
        f"latency={latency:.2f}s"
    )
    if failures:
        print(f"  failures: {', '.join(failures)}")
    return reachable and text_ok and tool_call_emitted


def main() -> int:
    missing = [env for env in MODEL_KEYS.values() if not os.environ.get(env)]
    if missing:
        print(f"nebius_probe.py: missing {', '.join(missing)}; set them in fleet/.env", file=sys.stderr)
        return 2

    from openai import OpenAI

    results = [
        _probe_model(OpenAI(api_key=os.environ[env], base_url=BASE_URL, timeout=60.0), model)
        for model, env in MODEL_KEYS.items()
    ]
    if not all(results):
        print("Nebius probe failed one or more capability checks.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
