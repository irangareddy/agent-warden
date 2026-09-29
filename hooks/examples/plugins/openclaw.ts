/**
 * UNTESTED example for OpenClaw before_tool_call.
 * Verify against https://docs.openclaw.ai/plugins/hooks/tool-policy
 */
import { spawnSync } from "node:child_process";

const hook = process.env.WARDEN_HOOK_PATH ?? "/ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py";

export function before_tool_call(event: { toolName: string; params: Record<string, unknown> }) {
  const child = spawnSync("python3", [hook, "--harness", "generic"], {
    input: JSON.stringify({ tool: event.toolName, args: event.params }),
    encoding: "utf8",
  });
  if (child.status !== 0) {
    return { block: true, blockReason: child.stderr.trim() || "Agent Warden hook failed closed" };
  }
  const result = JSON.parse(child.stdout);
  if (result.action !== "allow") {
    return { block: true, blockReason: result.reason || "Agent Warden requires approval" };
  }
  return {};
}
