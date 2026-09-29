"""Agent Warden: a Collaborative AgentApp whose tool calls pass through a warden."""

import os
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context
from openai import OpenAI

from agent.utils import _conversation, _stream_response
from agent.warden import Warden, blocked_output

MAX_TOOL_ROUNDS = 20
app = AgentApp()


def _say(agent: AgentSession, text: str) -> None:
    """Show a warden notice in Flower Chat alongside the model's streamed text."""
    agent.events.emit({"type": "response.output_text.delta", "delta": f"\n{text}\n"})


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Let the model use Grid and filesystem tools, with every call checked first."""
    warden = Warden()

    # Signatures sent by other nodes' wardens arrive inside Grid messages.
    for rule in warden.learn_from_prompt(agent.prompt):
        _say(agent, f"🛡️ Warden learned a signature from {rule.source}: {rule.reason}")

    client = OpenAI(
        base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
        api_key=os.environ["FLWR_RUNTIME_API_KEY"],
        max_retries=0,
    )
    input_items: list[Any] = _conversation(agent, context)
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
            decision = warden.check(item)
            if not decision.allowed:
                signature = warden.signature_for(decision, item)
                warden.learn(signature)
                _say(
                    agent,
                    f"🛡️ Warden BLOCKED `{decision.tool}` ({decision.family}: "
                    f"{decision.reason}) in {decision.latency_ms} ms",
                )
                input_items.append(blocked_output(item, decision, signature))
                continue
            input_items.append(
                agent.connectors.call(item)
                if item.get("name") in connector_tool_names
                else agent.grid.call(item)
            )
    raise RuntimeError(f"Agent exceeded {MAX_TOOL_ROUNDS} tool rounds")
