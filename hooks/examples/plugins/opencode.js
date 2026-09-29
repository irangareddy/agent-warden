/**
 * UNTESTED OpenCode tool.execute.before plugin example.
 * Verify against https://opencode.ai/docs/plugins/
 */
import { spawnSync } from "node:child_process";

const hook = process.env.WARDEN_HOOK_PATH ?? "/ABSOLUTE/PATH/TO/agent-warden/hooks/warden_hook.py";

export const AgentWarden = async () => ({
  "tool.execute.before": async (input, output) => {
    const child = spawnSync("python3", [hook, "--harness", "generic"], {
      input: JSON.stringify({ tool: input.tool, args: output.args }),
      encoding: "utf8",
    });
    if (child.status !== 0) {
      throw new Error(child.stderr.trim() || "Agent Warden hook failed closed");
    }
    const result = JSON.parse(child.stdout);
    if (result.action !== "allow") {
      throw new Error(result.reason || "Agent Warden requires approval");
    }
  },
});
