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
        tool=r"^(?:read_file|list_directory|Read|Edit|Write|MultiEdit|NotebookEdit)$",
        pattern=r"\.\./|/etc/|/root/|/proc/|/var/run/|/home/[^/\"]+/\.",
        reason="Reads outside the agent's allowed folder",
    ),
    Rule(
        id="cred-keys",
        family="credential_access",
        tool=r".*",
        pattern=(
            r"(?:^|[/\\])keys(?=$|[/\\\"'\s])|(?:^|[/\\])\.ssh(?=$|[/\\\"'\s])|"
            r"(?:^|[/\\])id_(?:rsa|ecdsa)(?=$|[/\\\"'\s])|\.pem\b|"
            r"supernode-\d|hosts\.yml|(?:^|[/\\])credentials\.json\b|"
            r"(?:^|[/\\])\.aws[/\\]credentials(?=$|[/\\\"'\s])|"
            r"(?:^|[/\\\s])\.env(?!\.(?:example|sample|template)(?=$|[/\\\"'\s]))"
            r"(?:\.[A-Za-z0-9_-]+)?(?=$|[/\\\"'\s])"
        ),
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
        # Imported after Rule is defined so beet_rules can construct Rule values
        # without creating a module-import cycle.
        from agent.beet_rules import BEET_RULES

        return BUILT_IN_RULES + BEET_RULES + self.shared

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
            if re.search(rule.tool, name, re.I) and _pattern_matches(rule.pattern, args):
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

    def validate(self, rule: Rule) -> tuple[bool, str]:
        """Test a rule against this node's own normal work before trusting it.

        A shared rule is only a proposal. It is rejected if it is not a valid
        pattern, if it would match almost anything, or if it would block any
        call in this node's known-good set.
        """
        from agent.known_good import KNOWN_GOOD

        try:
            compiled = re.compile(rule.pattern, re.I | re.S)
        except re.error as err:
            return False, f"invalid pattern ({err})"
        probes = ["", "a", "/", "read_file", '{"path": "/tmp/x"}']
        if any(compiled.search(p) for p in probes):
            return False, "pattern is too broad (matches almost anything)"
        blocked = [g["arguments"] for g in KNOWN_GOOD
                   if _pattern_matches(rule.pattern, g["arguments"])]
        if blocked:
            return False, f"would block {len(blocked)} normal action(s) on this node"
        return True, "passed local validation"

    def learn(self, rule: Rule, validate: bool = True) -> bool:
        """Adopt a rule. Rules from other nodes must pass local validation first."""
        if any(r.pattern == rule.pattern for r in self.shared):
            return False
        if validate:
            ok, why = self.validate(rule)
            self._log_rule(rule, accepted=ok, why=why)
            if not ok:
                return False
        self.shared.append(rule)
        _save_shared(self.shared)
        return True

    def learn_from_prompt(self, prompt: str) -> tuple[list[Rule], list[tuple[Rule, str]]]:
        """Pick up signatures another node sent. Returns (accepted, rejected with reason)."""
        accepted, rejected = [], []
        for raw in re.findall(re.escape(SIGNATURE_PREFIX) + r"(\{.*?\})(?=\s|$)", prompt, re.S):
            try:
                rule = Rule(**json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
            ok, why = self.validate(rule)
            if ok and self.learn(rule, validate=False):
                self._log_rule(rule, accepted=True, why=why)
                accepted.append(rule)
            elif not ok:
                self._log_rule(rule, accepted=False, why=why)
                rejected.append((rule, why))
        return accepted, rejected

    def _log_rule(self, rule: Rule, accepted: bool, why: str) -> None:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "rule_decisions.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"node": self.node_name, "accepted": accepted, "why": why,
                                "ts": time.time(), **asdict(rule)}) + "\n")

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


def _pattern_matches(pattern: str, arguments: str) -> bool:
    """Match JSON arguments while treating documented .env templates as safe.

    Python considers the dot in ``.env.example`` a word boundary, so the
    historic shared pattern ``\\.env\\b`` would otherwise block templates.
    Mask only those template names for rules containing that exact fragment;
    other sensitive material in the same call remains visible to the regex.
    """
    if r"\.env\b" in pattern:
        arguments = re.sub(
            r"(?i)(?:^|(?<=[/\\]))\.env\.(?:example|sample|template)(?=[/\\\"'\s]|$)",
            "ENV_TEMPLATE",
            arguments,
        )
    return bool(re.search(pattern, arguments, re.I | re.S))
