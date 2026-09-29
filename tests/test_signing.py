"""Signed shared rules verify, pin their source key, and relay unchanged."""

import importlib
import json
import os
import sys
import tempfile
from dataclasses import replace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ENV_VARS = (
    "WARDEN_REQUIRE_SIGNED",
    "WARDEN_SIGNING_KEY_FILE",
    "WARDEN_TRUSTED_KEYS_FILE",
    "WARDEN_STATE_DIR",
)

for variable in _ENV_VARS:
    os.environ.pop(variable, None)

import agent.warden as warden_module  # noqa: E402
from agent.relay import attach_signatures  # noqa: E402
from agent.signing import sign_rule, verify_rule  # noqa: E402


def node(state_dir: str, name: str):
    os.environ["WARDEN_STATE_DIR"] = state_dir
    importlib.reload(warden_module)
    return warden_module, warden_module.Warden(name)


def save_key(path: str) -> None:
    private_key = Ed25519PrivateKey.generate()
    with open(path, "wb") as key_file:
        key_file.write(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )


with tempfile.TemporaryDirectory(prefix="wagent-signing-") as state_root:
    sender_dir = os.path.join(state_root, "sender")
    wa, sender = node(sender_dir, "node-A")
    call = {
        "name": "read_file",
        "arguments": json.dumps({"path": "/srv/private/token.txt"}),
    }
    decision = wa.Decision(
        False, "read_file", "test-rule", "credential_access", "test secret", "node-A", 0, 1
    )
    signed, _ = sender.evolve(decision, call)
    assert signed.sig and signed.pubkey and verify_rule(signed)
    assert oct(os.stat(os.path.join(sender_dir, "node_key.pem")).st_mode & 0o777) == "0o600"

    receiver_dir = os.path.join(state_root, "receiver")
    _, receiver = node(receiver_dir, "receiver")
    accepted, rejected = receiver.learn_from_prompt(attach_signatures("status", [signed]))
    assert [rule.id for rule in accepted] == [signed.id] and not rejected
    assert accepted[0].sig == signed.sig and accepted[0].pubkey == signed.pubkey
    print("PASS signed rule round-tripped and was accepted")

    tampered = replace(signed, pattern=r"/tampered/")
    accepted, rejected = receiver.learn_from_prompt(attach_signatures("status", [tampered]))
    assert not accepted and rejected[0][1] == "bad signature"
    print("PASS tampered rule was rejected: bad signature")

    alternate_key = os.path.join(state_root, "alternate.pem")
    save_key(alternate_key)
    os.environ["WARDEN_SIGNING_KEY_FILE"] = alternate_key
    different_key_rule = wa.Rule(
        "different-key", "credential_access", ".*", r"/other-secret/", "other secret", "node-A"
    )
    sign_rule(different_key_rule)
    assert verify_rule(different_key_rule)
    accepted, rejected = receiver.learn_from_prompt(
        attach_signatures("status", [different_key_rule])
    )
    assert not accepted
    assert rejected[0][1] == "key does not match pinned key for node-A"
    os.environ.pop("WARDEN_SIGNING_KEY_FILE")
    print("PASS a different key for the same source was rejected")

    preset_file = os.path.join(state_root, "trusted-keys.json")
    with open(preset_file, "w", encoding="utf-8") as trusted_keys:
        json.dump({"node-A": different_key_rule.pubkey}, trusted_keys)
    os.environ["WARDEN_TRUSTED_KEYS_FILE"] = preset_file
    accepted, rejected = receiver.learn_from_prompt(
        attach_signatures("status", [different_key_rule])
    )
    assert [rule.id for rule in accepted] == [different_key_rule.id] and not rejected
    os.environ.pop("WARDEN_TRUSTED_KEYS_FILE")
    print("PASS preset trusted keys take precedence over TOFU pins")

    unsigned = wa.Rule(
        "unsigned-default", "credential_access", ".*", r"/unsigned-default/", "legacy", "old-node"
    )
    default_dir = os.path.join(state_root, "unsigned-default")
    _, default_receiver = node(default_dir, "default-receiver")
    accepted, rejected = default_receiver.learn_from_prompt(
        attach_signatures("status", [unsigned])
    )
    assert [rule.id for rule in accepted] == [unsigned.id] and not rejected

    os.environ["WARDEN_REQUIRE_SIGNED"] = "1"
    required = wa.Rule(
        "unsigned-required", "credential_access", ".*", r"/unsigned-required/", "legacy", "old-node"
    )
    accepted, rejected = default_receiver.learn_from_prompt(
        attach_signatures("status", [required])
    )
    assert not accepted and rejected[0][1] == "unsigned rule"
    os.environ.pop("WARDEN_REQUIRE_SIGNED")
    print("PASS unsigned rules follow WARDEN_REQUIRE_SIGNED")

    coordinator_dir = os.path.join(state_root, "coordinator")
    _, coordinator = node(coordinator_dir, "coordinator")
    relayed, rejected = coordinator.learn_from_prompt(attach_signatures("reply", [signed]))
    assert not rejected and len(relayed) == 1
    forwarded = attach_signatures("forward", relayed)
    assert relayed[0].sig == signed.sig and relayed[0].pubkey == signed.pubkey
    assert warden_module.encode_signature(signed) in forwarded
    print("PASS relayed rule kept its original signature")

for variable in _ENV_VARS:
    os.environ.pop(variable, None)
