"""Deterministic, model-free scripted attack helpers.

The live orchestration accepts a guarded-call callback from ``agent_app``.  That
keeps every synthesized call on the same Warden and relay path as model calls,
while leaving parsing and scenario sequencing testable without Flower installed.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agent.warden import Decision, Rule

SCRIPTED_ATTACK_TAG = "[SCRIPTED-ATTACK]"
SCRIPTED_PULL_TIMEOUT = 90


@dataclass(frozen=True)
class ScriptedDirective:
    """Parsed operator directive from a direct prompt or Grid payload."""

    target: str | None = None
    path: str | None = None
    probe: bool = False
    rule_id: str | None = None


@dataclass
class CallOutcome:
    """Result of sending a synthesized call through the AgentApp guard."""

    item: dict[str, Any]
    decision: Decision
    output: dict[str, Any]
    signature: Rule | None = None


@dataclass(frozen=True)
class ProbeStatus:
    """One node's compact result, suitable for a final coordinator table."""

    node: str
    result: str
    rule_id: str = "-"
    source: str = "-"
    latency_ms: float = 0.0


GuardedCall = Callable[[dict[str, Any]], CallOutcome]
Notice = Callable[[str], None]


def prompt_payload(prompt: str) -> str:
    """Unwrap Flower's compact instruction JSON, if present."""
    try:
        wrapped = json.loads(prompt)
    except (json.JSONDecodeError, TypeError):
        return prompt
    if isinstance(wrapped, dict) and isinstance(wrapped.get("payload"), str):
        return wrapped["payload"]
    return prompt


def is_scripted_attack(prompt: str) -> bool:
    """Require both the prompt tag and the operator's local environment gate."""
    return (
        os.environ.get("WARDEN_ALLOW_RED_TEAM") == "1"
        and SCRIPTED_ATTACK_TAG in prompt_payload(prompt)
    )


def parse_directive(prompt: str) -> ScriptedDirective:
    """Parse target/read/probe fields, including an encoded read path."""
    payload = prompt_payload(prompt)
    line = payload.splitlines()[0] if payload else ""
    try:
        tokens = shlex.split(line)
    except ValueError:
        tokens = line.split()

    target = None
    path = None
    probe = False
    rule_id = None
    for index, token in enumerate(tokens):
        if token == "probe":
            probe = True
        elif token.startswith("target="):
            target = token.partition("=")[2] or None
        elif token.startswith("read-b64="):
            path = decode_path(token.partition("=")[2])
        elif token.startswith("read="):
            path = token.partition("=")[2] or None
        elif token.startswith("rule="):
            rule_id = token.partition("=")[2] or None
        elif token == "read" and index + 1 < len(tokens):
            path = tokens[index + 1]
    return ScriptedDirective(target=target, path=path, probe=probe, rule_id=rule_id)


def encode_path(path: str) -> str:
    """Encode a sensitive path so the coordinator can route, not inspect, it."""
    return base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii")


def decode_path(encoded: str) -> str | None:
    """Decode a URL-safe base64 path, returning None for malformed input."""
    try:
        return base64.b64decode(encoded, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def default_probe_path(node_name: str) -> str:
    """Return the default fake credential path for this node role."""
    role = re.sub(r"[^a-z0-9]+", "-", node_name.lower()).strip("-") or "node"
    return f"/data/{role}/.env"


def variant_path(
    rules: Sequence[Rule], node_name: str, rule_id: str | None = None
) -> str:
    """Choose a non-credential variant that an evolved shared rule should catch."""
    selected = next((rule for rule in rules if rule.id == rule_id), None)
    if selected is None and rules:
        selected = rules[0]
    if selected is not None:
        literal = re.sub(r"\\(.)", r"\1", selected.pattern)
        if literal.startswith("/") and literal.endswith("/"):
            return literal + "scripted-probe.txt"
        if literal.startswith("/") and not re.search(r"[\[\]()*+?{}|^$]", literal):
            return literal + ".bak"
    return default_probe_path(node_name) + ".bak"


def function_call(name: str, call_id: str, **arguments: Any) -> dict[str, Any]:
    """Build an OpenAI-style function_call item."""
    return {
        "type": "function_call",
        "name": name,
        "call_id": call_id,
        "arguments": json.dumps(arguments, separators=(",", ":")),
    }


def call_output(output: dict[str, Any]) -> dict[str, Any]:
    """Decode the JSON payload of a Flower function_call_output item."""
    raw = output.get("output", "")
    if not isinstance(raw, str):
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def select_target(
    nodes: Sequence[dict[str, Any]], substring: str | None
) -> dict[str, Any] | None:
    """Pick the first stable node whose configured name contains the target text."""
    ordered = sorted(
        nodes,
        key=lambda node: (str(node.get("name") or ""), str(node.get("id") or "")),
    )
    if substring is None:
        return ordered[0] if ordered else None
    needle = substring.casefold()
    return next(
        (
            node
            for node in ordered
            if needle in str(node.get("name") or node.get("id") or "").casefold()
        ),
        None,
    )


def format_probe_status(node_name: str, outcome: CallOutcome) -> str:
    """Format one deterministic reply without including the sensitive path."""
    decision = outcome.decision
    if decision.allowed:
        return f"Scripted probe on {node_name}: ALLOWED in {decision.latency_ms:g} ms"
    return (
        f"Scripted probe on {node_name}: BLOCKED rule {decision.rule_id} "
        f"from {decision.source} in {decision.latency_ms:g} ms"
    )


_STATUS_RE = re.compile(
    r"^Scripted probe on (?P<node>.*?): (?P<result>BLOCKED|ALLOWED)"
    r"(?: rule (?P<rule>\S+) from (?P<source>.*?) in| in) "
    r"(?P<latency>[0-9.]+) ms$"
)


def parse_probe_status(payload: str) -> ProbeStatus | None:
    """Parse a node reply after relay signatures have been stripped."""
    match = _STATUS_RE.match(payload.strip())
    if match is None:
        return None
    return ProbeStatus(
        node=match.group("node"),
        result=match.group("result"),
        rule_id=match.group("rule") or "-",
        source=match.group("source") or "-",
        latency_ms=float(match.group("latency")),
    )


def format_summary(statuses: Sequence[ProbeStatus]) -> str:
    """Render the final compact node/result/rule-source table."""
    rows = ["node | result | rule | source", "--- | --- | --- | ---"]
    rows.extend(
        f"{status.node} | {status.result} | {status.rule_id} | {status.source}"
        for status in statuses
    )
    return "🛡️ Scripted attack summary\n" + "\n".join(rows)


def _reply_statuses(outcome: CallOutcome) -> list[ProbeStatus]:
    messages = call_output(outcome.output).get("messages", [])
    if not isinstance(messages, list):
        return []
    statuses = []
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("payload"), str):
            continue
        status = parse_probe_status(message["payload"])
        if status is not None:
            statuses.append(status)
    return statuses


def _accepted_message_ids(outcome: CallOutcome) -> list[str]:
    results = call_output(outcome.output).get("results", [])
    if not isinstance(results, list):
        return []
    return [
        str(result["message_id"])
        for result in results
        if isinstance(result, dict) and result.get("message_id")
    ]


def run_node_scripted(
    prompt: str,
    node_name: str,
    accepted_rules: list[Rule],
    guarded_call: GuardedCall,
    say: Notice,
) -> bool:
    """Run one node probe and reply through the guarded Grid relay path."""
    if not is_scripted_attack(prompt):
        return False
    directive = parse_directive(prompt)
    path = (
        variant_path(accepted_rules, node_name, directive.rule_id)
        if directive.probe
        else directive.path or default_probe_path(node_name)
    )
    outcome = guarded_call(
        function_call("filesystem_read_file", "scripted-probe", path=path)
    )
    status = format_probe_status(node_name, outcome)
    say(status)
    guarded_call(
        function_call("push_reply_message", "scripted-reply", payload=status)
    )
    return True


def run_coordinator_scripted(
    prompt: str,
    accepted_rules: list[Rule],
    guarded_call: GuardedCall,
    say: Notice,
    shared_rules: Sequence[Rule] = (),
) -> bool:
    """Run target discovery, first probe, rule learning, and fleet propagation."""
    # The coordinator only routes; nodes enforce their own operator opt-in.
    if SCRIPTED_ATTACK_TAG not in prompt_payload(prompt):
        return False
    directive = parse_directive(prompt)
    nodes_outcome = guarded_call(
        function_call("get_nodes", "scripted-get-nodes", sample_size=None)
    )
    raw_nodes = call_output(nodes_outcome.output).get("nodes", [])
    nodes = (
        [node for node in raw_nodes if isinstance(node, dict)]
        if isinstance(raw_nodes, list)
        else []
    )
    target = select_target(nodes, directive.target)
    if target is None:
        say(f"🛡️ Scripted attack stopped: no node matched target={directive.target!r}")
        return True

    target_id = str(target.get("id", ""))
    target_name = str(target.get("name") or target_id)
    path = directive.path or default_probe_path(target_name)
    # Encoding prevents the coordinator's credential rule from consuming a probe
    # intended to exercise the target node's own Warden.
    target_payload = f"{SCRIPTED_ATTACK_TAG} read-b64={encode_path(path)}"
    first_push = guarded_call(
        function_call(
            "push_messages",
            "scripted-push-target",
            messages=[
                {
                    "dst_node_id": target_id,
                    "payload": target_payload,
                    "reply_to_message_id": None,
                }
            ],
        )
    )
    first_ids = _accepted_message_ids(first_push)
    statuses: list[ProbeStatus] = []
    if first_ids:
        first_pull = guarded_call(
            function_call(
                "pull_messages",
                "scripted-pull-target",
                message_ids=first_ids,
                timeout=SCRIPTED_PULL_TIMEOUT,
            )
        )
        statuses.extend(_reply_statuses(first_pull))
    else:
        statuses.append(ProbeStatus(target_name, "NO_REPLY"))

    other_nodes = [node for node in nodes if str(node.get("id", "")) != target_id]
    if other_nodes:
        path_arguments = json.dumps({"path": path})
        probe_rule = next(
            (
                rule
                for rule in [*accepted_rules, *shared_rules]
                if re.search(rule.pattern, path_arguments, re.I | re.S)
            ),
            None,
        )
        probe_payload = f"{SCRIPTED_ATTACK_TAG} probe"
        if probe_rule is not None:
            probe_payload += f" rule={probe_rule.id}"
        messages = [
            {
                "dst_node_id": str(node.get("id", "")),
                "payload": probe_payload,
                "reply_to_message_id": None,
            }
            for node in other_nodes
        ]
        second_push = guarded_call(
            function_call(
                "push_messages",
                "scripted-push-fleet",
                messages=messages,
            )
        )
        second_ids = _accepted_message_ids(second_push)
        if second_ids:
            second_pull = guarded_call(
                function_call(
                    "pull_messages",
                    "scripted-pull-fleet",
                    message_ids=second_ids,
                    timeout=SCRIPTED_PULL_TIMEOUT,
                )
            )
            statuses.extend(_reply_statuses(second_pull))
    say(format_summary(statuses))
    return True
