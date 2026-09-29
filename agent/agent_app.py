"""Agent Warden: a Collaborative AgentApp whose tool calls pass through a warden."""

import json
import os
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context
from openai import OpenAI

from agent.relay import attach_signatures, signatures_in_pull_output, strip_signatures
from agent.utils import _conversation, _stream_response
from agent.warden import Rule, Warden, blocked_output

MAX_TOOL_ROUNDS = 20
app = AgentApp()


def _say(agent: AgentSession, text: str) -> None:
    """Show a warden notice in Flower Chat alongside the model's streamed text."""
    agent.events.emit({"type": "response.output_text.delta", "delta": f"\n{text}\n"})


def _announce_rules(
    agent: AgentSession,
    accepted: list[Rule],
    rejected: list[tuple[Rule, str]],
) -> None:
    """Show the result of validating signatures from other nodes."""
    for rule in accepted:
        _say(
            agent,
            f"🛡️ Warden accepted a rule from {rule.source} after local validation: "
            f"{rule.reason}",
        )
    for rule, why in rejected:
        _say(agent, f"⛔ Warden REJECTED a rule from {rule.source}: {why}")


def _rewrite_relay_call(
    item: dict[str, Any],
    new_rules: list[Rule],
    accepted_rules: list[Rule],
    shared_rules: list[Rule],
) -> dict[str, Any]:
    """Attach locally known signatures to outgoing Grid messages."""
    name = item.get("name")
    if name not in {"push_reply_message", "push_messages"}:
        return item
    try:
        arguments = json.loads(item.get("arguments", ""))
    except (json.JSONDecodeError, TypeError):
        return item
    if not isinstance(arguments, dict):
        return item

    if name == "push_reply_message" and new_rules:
        payload = arguments.get("payload")
        if isinstance(payload, str):
            arguments["payload"] = attach_signatures(payload, new_rules)
    elif name == "push_messages":
        messages = arguments.get("messages")
        if not isinstance(messages, list):
            return item
        rewritten = []
        for message in messages:
            if not isinstance(message, dict):
                rewritten.append(message)
                continue
            message = dict(message)
            payload = message.get("payload")
            destination = str(message.get("dst_node_id", ""))
            if isinstance(payload, str):
                rules = [
                    *accepted_rules,
                    *(rule for rule in shared_rules if rule.source != destination),
                ]
                message["payload"] = attach_signatures(payload, rules)
            rewritten.append(message)
        arguments["messages"] = rewritten
    return {**item, "arguments": json.dumps(arguments)}


def _clean_pull_result(result: Any) -> Any:
    """Hide relayed signatures in pull_messages output shown to the model."""
    if not isinstance(result, dict) or not isinstance(result.get("output"), str):
        return result
    try:
        output = json.loads(result["output"])
    except json.JSONDecodeError:
        return result
    if not isinstance(output, dict) or not isinstance(output.get("messages"), list):
        return result
    output = dict(output)
    messages = []
    for message in output["messages"]:
        if isinstance(message, dict) and isinstance(message.get("payload"), str):
            message = {**message, "payload": strip_signatures(message["payload"])}
        messages.append(message)
    output["messages"] = messages
    return {**result, "output": json.dumps(output)}


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Let the model use Grid and filesystem tools, with every call checked first."""
    warden = Warden()

    # Signatures sent by other nodes' wardens arrive inside Grid messages.
    accepted, rejected = warden.learn_from_prompt(agent.prompt)
    _announce_rules(agent, accepted, rejected)
    accepted_this_run = list(accepted)
    new_rules: list[Rule] = []

    client = OpenAI(
        base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
        api_key=os.environ["FLWR_RUNTIME_API_KEY"],
        max_retries=0,
    )
    input_items: list[Any] = _conversation(agent, context)
    for input_item in input_items:
        if (
            isinstance(input_item, dict)
            and input_item.get("type") == "message"
            and isinstance(input_item.get("content"), str)
        ):
            input_item["content"] = strip_signatures(input_item["content"])
    try:
        connector_tools = agent.connectors.tools(["filesystem"])
    except ValueError:
        connector_tools = []
    connector_tool_names = {tool["name"] for tool in connector_tools}
    grid_tools = agent.grid.tools()
    tools = [*grid_tools, *connector_tools]
    print("Warden: available tools:", [t.get("name") for t in tools])
    print("Warden: active rules:", len(warden.rules), "shared:", len(warden.shared))

    for _ in range(MAX_TOOL_ROUNDS):
        response, completed_event = _stream_response(client, agent, input_items, tools)
        response_output = [item.to_dict() for item in response.output]
        tool_calls = [
            item for item in response_output if item.get("type") == "function_call"
        ]
        input_items.extend(response_output)
        if not tool_calls:
            agent.events.emit(completed_event)
            return

        for item in tool_calls:
            call_item = _rewrite_relay_call(
                item, new_rules, accepted_this_run, warden.shared
            )
            decision = warden.check(call_item)
            if not decision.allowed:
                signature, report = warden.evolve(decision, call_item)
                if warden.learn(signature):
                    new_rules.append(signature)
                _say(
                    agent,
                    f"🛡️ Warden BLOCKED `{decision.tool}` ({decision.family}: "
                    f"{decision.reason}) in {decision.latency_ms} ms",
                )
                tried = ", ".join(
                    f"{r['candidate']} ({r['false_alarms']} false alarms)" for r in report
                )
                _say(agent, f"🧬 Evolved rule: {signature.reason}. Tested: {tried}")
                input_items.append(blocked_output(call_item, decision, signature))
                continue
            result = (
                agent.connectors.call(call_item)
                if call_item.get("name") in connector_tool_names
                else agent.grid.call(call_item)
            )
            if call_item.get("name") == "pull_messages" and isinstance(result, dict):
                relay_text = signatures_in_pull_output(str(result.get("output", "")))
                pull_accepted, pull_rejected = warden.learn_from_prompt(relay_text)
                accepted_this_run.extend(pull_accepted)
                _announce_rules(agent, pull_accepted, pull_rejected)
                result = _clean_pull_result(result)
            input_items.append(result)
    raise RuntimeError(f"Agent exceeded {MAX_TOOL_ROUNDS} tool rounds")
