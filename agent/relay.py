"""Helpers for relaying Warden signatures through Grid messages."""

import json
from collections.abc import Iterable

from agent.warden import Rule, SIGNATURE_PREFIX, encode_signature


def attach_signatures(payload: str, rules: Iterable[Rule]) -> str:
    """Append any signatures that are not already present in a payload."""
    signatures = []
    seen = set()
    for rule in rules:
        signature = encode_signature(rule)
        if signature not in payload and signature not in seen:
            signatures.append(signature)
            seen.add(signature)
    if not signatures:
        return payload
    separator = (
        ""
        if not payload or payload.endswith("\n\n")
        else "\n" if payload.endswith("\n") else "\n\n"
    )
    return payload + separator + "\n".join(signatures)


def signatures_in_pull_output(output_json: str) -> str:
    """Collect message payloads from a pull_messages output."""
    try:
        output = json.loads(output_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    messages = output.get("messages", []) if isinstance(output, dict) else []
    return "\n".join(
        payload
        for message in messages
        if isinstance(message, dict) and isinstance((payload := message.get("payload")), str)
    )


def strip_signatures(text: str) -> str:
    """Remove Warden signature lines from text shown to the model."""
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not line.lstrip().startswith(SIGNATURE_PREFIX)
    )
