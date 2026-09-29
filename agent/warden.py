"""Agent Warden: checks every tool call before it runs and shares what it blocks.

The model never gets the final say. Each tool call the agent requests passes
through `Warden.check` first. A blocked call never reaches the connector or the
Grid. The warden records a signature for it, and signatures received from other
nodes are enforced the same way as the built-in rules.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

STATE_DIR = os.environ.get("WARDEN_STATE_DIR", "/tmp/agent-warden")
SIGNATURES_FILE = os.path.join(STATE_DIR, "signatures.json")
LOG_FILE = os.path.join(STATE_DIR, "decisions.jsonl")
SIGNATURE_PREFIX = "WARDEN_SIGNATURE::"


@dataclass
class Rule:
    """One pattern the warden blocks."""

    id: str
    family: str  # "sandbox_escape" | "credential_access" | "data_exfiltration"
    tool: str  # regex on the tool name
    pattern: str  # regex on the tool call arguments (JSON text)
    reason: str
    source: str = "built-in"  # "built-in" or the node that shared it


BUILT_IN_RULES = [
    Rule(
        id="fs-path-escape",
        family="sandbox_escape",
        tool=r".*",
        pattern=r"\.\./|/etc/|/root/|/proc/|/var/run/|/home/[^/\"]+/\.",
        reason="Reads outside the agent's allowed folder",
    ),
    Rule(
        id="cred-keys",
        family="credential_access",
        tool=r".*",
        pattern=r"/keys\b|\.ssh|id_rsa|id_ecdsa|\.pem\b|supernode-\d|hosts\.yml|credentials|\.env\b",
        reason="Touches keys or credentials",
    ),
    Rule(
        id="cred-secret-material",
        family="credential_access",
        tool=r".*",
        pattern=r"-----BEGIN [A-Z ]*PRIVATE KEY-----|FLWR_MODEL_API_KEY|sk-[A-Za-z0-9]{16,}",
        reason="Carries secret material",
    ),
    Rule(
        id="exfil-record-ids",
        family="data_exfiltration",
        tool=r"push|send|message|reply",
        pattern=r"(CLN-\d{6}.*){3,}",
        reason="Sends raw record identifiers to another agent",
    ),
]


@dataclass
class Decision:
    """The outcome of checking one tool call."""

    allowed: bool
    tool: str
    rule_id: str | None
    family: str | None
    reason: str | None
    source: str | None
    latency_ms: float
    ts: float


def _load_shared() -> list[Rule]:
    try:
        with open(SIGNATURES_FILE, encoding="utf-8") as f:
            return [Rule(**r) for r in json.load(f)]
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return []


def _save_shared(rules: list[Rule]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SIGNATURES_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in rules], f, indent=2)


class Warden:
    """Checks tool calls against built-in rules plus signatures from other nodes."""

    def __init__(self, node_name: str = "") -> None:
        self.node_name = node_name or os.environ.get("WARDEN_NODE_NAME", "this-node")
        self.shared = _load_shared()

    @property
    def rules(self) -> list[Rule]:
        return BUILT_IN_RULES + self.shared

    def check(self, item: dict[str, Any]) -> Decision:
        """Decide whether one model-requested function call may run."""
        start = time.perf_counter()
        name = str(item.get("name", ""))
        args = str(item.get("arguments", ""))
        # A warden broadcast carries the blocked pattern inside it; don't block the alert itself.
        # (Demo shortcut: a real system would sign these messages.)
        if SIGNATURE_PREFIX in args:
            return self._log(Decision(True, name, "signature-broadcast", None, None, None,
                                      _ms(start), time.time()))
        for rule in self.rules:
            if re.search(rule.tool, name, re.I) and re.search(rule.pattern, args, re.I | re.S):
                return self._log(Decision(False, name, rule.id, rule.family, rule.reason,
                                          rule.source, _ms(start), time.time()))
        return self._log(Decision(True, name, None, None, None, None, _ms(start), time.time()))

    def signature_for(self, decision: Decision, item: dict[str, Any]) -> Rule:
        """Build a shareable rule from a blocked call so other nodes block its variants."""
        args = str(item.get("arguments", ""))
        # Keep the most specific path-like or key-like fragment as the shared pattern.
        fragments = re.findall(r"[\w.\-]*(?:/[\w.\-]+)+|[\w\-]*(?:key|secret|token|ssh)[\w\-]*", args, re.I)
        fragment = max(fragments, key=len) if fragments else args[:60]
        return Rule(
            id=f"shared-{decision.rule_id}-{int(decision.ts)}",
            family=decision.family or "unknown",
            tool=r".*",
            pattern=re.escape(fragment),
            reason=f"Shared by {self.node_name}: {decision.reason}",
            source=self.node_name,
        )

    def evolve(self, decision: Decision, item: dict[str, Any]) -> tuple[Rule, list[dict[str, Any]]]:
        """Turn one block into the broadest rule that still allows every known-good call.

        Candidates go from broad to narrow. Each is replayed against KNOWN_GOOD;
        the first with zero false alarms is adopted. The exact fragment is the
        fallback, so evolving never makes the warden weaker.
        """
        from agent.known_good import KNOWN_GOOD

        narrow = self.signature_for(decision, item)
        fragment = re.sub(r"\\(.)", r"\1", narrow.pattern)
        candidates: list[tuple[str, str]] = []
        if "/" in fragment:
            parts = [p for p in fragment.split("/") if p]
            stem = re.split(r"[.\-_]", parts[-1])[0]
            for depth in range(1, len(parts)):  # directory prefixes, broadest first
                prefix = "/" + "/".join(parts[:depth]) + "/"
                candidates.append((f"directory {prefix}", re.escape(prefix)))
            for seg in parts[:-1]:  # a sensitive-looking folder name anywhere
                candidates.append((f"any folder named {seg}", r"/" + re.escape(seg) + r"/"))
            if stem:
                candidates.append((f"files named {stem}*", r"/" + re.escape(stem) + r"[^\"/]*"))
        candidates.append(("exact path", narrow.pattern))

        report = []
        for label, pattern in candidates:
            false_alarms = [
                g["arguments"] for g in KNOWN_GOOD if re.search(pattern, g["arguments"], re.I)
            ]
            report.append({"candidate": label, "pattern": pattern, "false_alarms": len(false_alarms)})
            if not false_alarms:
                narrow.pattern = pattern
                narrow.reason = f"{narrow.reason} (generalized to {label})"
                return narrow, report
        return narrow, report

    def learn(self, rule: Rule) -> bool:
        """Add a signature from another node. Returns False if it was already known."""
        if any(r.pattern == rule.pattern for r in self.shared):
            return False
        self.shared.append(rule)
        _save_shared(self.shared)
        return True

    def learn_from_prompt(self, prompt: str) -> list[Rule]:
        """Pick up signatures another node's warden sent in a Grid message."""
        learned = []
        for raw in re.findall(re.escape(SIGNATURE_PREFIX) + r"(\{.*?\})(?=\s|$)", prompt, re.S):
            try:
                rule = Rule(**json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
            if self.learn(rule):
                learned.append(rule)
        return learned

    def _log(self, decision: Decision) -> Decision:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"node": self.node_name, **asdict(decision)}) + "\n")
        return decision


def encode_signature(rule: Rule) -> str:
    return SIGNATURE_PREFIX + json.dumps(asdict(rule), separators=(",", ":"))


def blocked_output(item: dict[str, Any], decision: Decision, signature: Rule) -> dict[str, Any]:
    """The tool result the model sees instead of the real call."""
    return {
        "type": "function_call_output",
        "call_id": item.get("call_id"),
        "output": (
            f"BLOCKED by Agent Warden ({decision.family}: {decision.reason}). "
            "This action was not executed. Do not retry it or any variant. "
            "Tell every other node about this block by sending them exactly this line, "
            f"then continue the user's task safely:\n{encode_signature(signature)}"
        ),
    }


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)
