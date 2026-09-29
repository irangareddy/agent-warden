#!/usr/bin/env python3
"""Probe Nebius Token Factory text generation and function calling."""

import os
import sys
import time
from typing import Any


BASE_URL = "https://api.tokenfactory.tf-ca1.nebius.com/v1"
MODEL_IDS = (
    "dedicated/flowerai/Kimi-K2.7-Code-1OUHWL",
    "dedicated/flowerai/MiniMax-M3-OOLI9o",
)
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
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        print(
            "nebius_probe.py: NEBIUS_API_KEY is missing; set it in the environment",
            file=sys.stderr,
        )
        return 2

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=60.0)
    results = [_probe_model(client, model) for model in MODEL_IDS]
    all_ok = all(results)
    if not all_ok:
        print("Nebius probe failed one or more capability checks.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
