"""Ed25519 signatures and trust-on-first-use keys for shared rules."""

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_CONTENT_FIELDS = ("id", "family", "tool", "pattern", "reason", "source", "action")


def _state_dir() -> str:
    return os.environ.get("WARDEN_STATE_DIR", "/tmp/agent-warden")


def _canonical_rule(rule: Any) -> bytes:
    content = {field: getattr(rule, field) for field in _CONTENT_FIELDS}
    return json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_private_key() -> Ed25519PrivateKey:
    configured_path = os.environ.get("WARDEN_SIGNING_KEY_FILE")
    path = configured_path or os.path.join(_state_dir(), "node_key.pem")
    try:
        with open(path, "rb") as key_file:
            key = serialization.load_pem_private_key(key_file.read(), password=None)
    except FileNotFoundError:
        if configured_path:
            raise
        os.makedirs(_state_dir(), exist_ok=True)
        key = Ed25519PrivateKey.generate()
        encoded = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            with open(path, "rb") as key_file:
                key = serialization.load_pem_private_key(key_file.read(), password=None)
        else:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(encoded)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("WARDEN signing key must be an Ed25519 private key")
    if not configured_path:
        os.chmod(path, 0o600, follow_symlinks=False)
    return key


def sign_rule(rule: Any) -> Any:
    """Sign a rule in place and return it."""
    private_key = _load_private_key()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    rule.pubkey = base64.b64encode(public_key).decode("ascii")
    rule.sig = base64.b64encode(private_key.sign(_canonical_rule(rule))).decode("ascii")
    return rule


def verify_rule(rule: Any) -> bool:
    """Return whether a rule carries a valid Ed25519 signature."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(rule.pubkey, validate=True)
        )
        signature = base64.b64decode(rule.sig, validate=True)
        public_key.verify(signature, _canonical_rule(rule))
    except (AttributeError, TypeError, ValueError, InvalidSignature):
        return False
    return True


def check_rule_trust(rule: Any) -> tuple[bool, str]:
    """Verify a received rule and enforce source-to-key trust on first use."""
    if not getattr(rule, "sig", ""):
        if os.environ.get("WARDEN_REQUIRE_SIGNED") == "1":
            return False, "unsigned rule"
        return True, "unsigned rule allowed"
    if not verify_rule(rule):
        return False, "bad signature"

    source = str(rule.source)
    preset_path = os.environ.get("WARDEN_TRUSTED_KEYS_FILE")
    preset = _load_trusted_keys(preset_path) if preset_path else {}
    if source in preset:
        if preset[source] != rule.pubkey:
            return False, f"key does not match pinned key for {source}"
        return True, "signature verified"

    trust_path = os.path.join(_state_dir(), "trusted_keys.json")
    trusted = _load_trusted_keys(trust_path)
    pinned = trusted.get(source)
    if pinned is not None and pinned != rule.pubkey:
        return False, f"key does not match pinned key for {source}"
    if pinned is None:
        trusted[source] = rule.pubkey
        os.makedirs(_state_dir(), exist_ok=True)
        with open(trust_path, "w", encoding="utf-8") as trust_file:
            json.dump(trusted, trust_file, indent=2, sort_keys=True)
    return True, "signature verified"


def _load_trusted_keys(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as trust_file:
            value = json.load(trust_file)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        str(source): public_key
        for source, public_key in value.items()
        if isinstance(public_key, str)
    }
