"""A wrong key file never reaches a release's host (ORBIO_RELEASE_DRAFT section 8, residual R3).

The relay is the only process that reads the key, so it checks the key's shape at start, before it can serve anything: an
Orbio release takes only an `sk-orbio-` key, and any other ACTUAL release refuses one. Synthetic sentinel keys only: the
real process tests use the two approved records, stop at the refusal and open no socket.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import relay_admission
import relay_service

from conftest import REPO

ORBIO_RECORD = REPO / "docs/qualification/orbio-release/orbio_first_call_record.json"
ORBIO_CA = REPO / "docs/qualification/orbio-release/orbio_ca_isrg_root_x1.pem"
OPENROUTER_RECORD = REPO / "docs/qualification/hermes-actual-operation/release/hermes_first_call_record.json"
RIGHT_ORBIO_KEY = b"sk-orbio-SYNTHETIC0sentinel0key"
OPENROUTER_SHAPED_KEY = b"sk-or-v1-SYNTHETIC0sentinel0key"
RECORD_NAME = "provider-key-refused.json"
WRONG_FOR_ORBIO = [
    (OPENROUTER_SHAPED_KEY, "provider_key_not_orbio"),
    (b"sk-test-SYNTHETIC0sentinel0key", "provider_key_not_orbio"),
    (b"SK-ORBIO-SYNTHETIC0sentinel0key", "provider_key_not_orbio"),
    (b"sk-orbio-", "provider_key_not_orbio"),
    (b"", "provider_key_malformed"),
    (b"sk-orbio-SYNTHETIC0 sentinel", "provider_key_malformed"),
    (b"sk-orbio-SYNTHETIC0\nsk-or-v1-sentinel", "provider_key_malformed"),
    ("sk-orbio-SYNTHETIC0é".encode(), "provider_key_malformed"),
    (b"sk-orbio-SYNTHETIC0\xff\xfe", "provider_key_malformed"),
]
WRONG_FOR_OPENROUTER = [
    (RIGHT_ORBIO_KEY, "provider_key_is_orbio"),
    (b"SK-Orbio-SYNTHETIC0sentinel0key", "provider_key_is_orbio"),
    (b"", "provider_key_malformed"),
]


def config_for(root: Path, record: Path, ca_bytes: bytes, key: bytes) -> dict[str, Any]:
    for folder in ("grants", "revocations", "state", "jobs"):
        (root / folder).mkdir(parents=True)
    (root / "admission-key").write_bytes(b"synthetic admission key")
    (root / "provider-key").write_bytes(key)
    (root / "ca.pem").write_bytes(ca_bytes)
    return {"release_record": {"path": str(record), "sha256": hashlib.sha256(record.read_bytes()).hexdigest()},
            "gateway_socket": "/relay/egress/gateway.sock", "channel_roots": {"jobs": str(root / "jobs")},
            "paths": {"provider_key": str(root / "provider-key"), "admission_key": str(root / "admission-key"),
                      "provider_ca": str(root / "ca.pem"), "grants": str(root / "grants"),
                      "revocations": str(root / "revocations"), "state": str(root / "state")}}


def orbio_config(root: Path, key: bytes) -> dict[str, Any]:
    return config_for(root, ORBIO_RECORD, ORBIO_CA.read_bytes(), key)


def openrouter_config(root: Path, key: bytes, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The adopted record names a CA bundle this repository does not keep, so only here its pin follows a synthetic file."""
    value = {**json.loads(OPENROUTER_RECORD.read_bytes()), "ca_bundle_sha256": hashlib.sha256(b"synthetic CA").hexdigest()}
    raw = json.dumps(value).encode()
    (root.parent / "openrouter-record.json").write_bytes(raw)
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({hashlib.sha256(raw).hexdigest()}))
    return config_for(root, root.parent / "openrouter-record.json", b"synthetic CA", key)


def fragments(key: bytes) -> list[bytes]:
    """Every 6-byte piece of the key that is not the published prefix: none of them may appear in any output."""
    secret = key.lower().removeprefix(b"sk-orbio-")
    return [secret[i:i + 6] for i in range(max(0, len(secret) - 5))]


def assert_refused_with_nothing_started(root: Path, reason: str) -> None:
    assert json.loads((root / "state" / RECORD_NAME).read_text())["refusal"] == reason
    assert sorted(path.name for path in (root / "state").iterdir()) == [RECORD_NAME]  # no heartbeat, no attempt folder


@pytest.mark.parametrize("key, reason", WRONG_FOR_ORBIO)
def test_an_orbio_release_refuses_every_key_that_is_not_an_orbio_key_before_serving(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: bytes, reason: str) -> None:
    monkeypatch.setattr(relay_service, "send_once", lambda *a, **k: pytest.fail("the relay sent with a refused key"))
    with pytest.raises(SystemExit) as refused:
        relay_service.Relay(orbio_config(tmp_path / "relay", key))
    assert refused.value.code == f"the provider key file is refused: {reason}"
    assert_refused_with_nothing_started(tmp_path / "relay", reason)


@pytest.mark.parametrize("key, reason", WRONG_FOR_OPENROUTER)
def test_an_openrouter_release_refuses_an_orbio_key_before_serving(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: bytes, reason: str) -> None:
    with pytest.raises(SystemExit):
        relay_service.Relay(openrouter_config(tmp_path / "relay", key, monkeypatch))
    assert_refused_with_nothing_started(tmp_path / "relay", reason)


@pytest.mark.parametrize("key", [RIGHT_ORBIO_KEY, RIGHT_ORBIO_KEY + b"\n"])
def test_an_orbio_release_starts_with_an_orbio_key_and_a_final_new_line_is_not_part_of_it(
        tmp_path: Path, key: bytes) -> None:
    relay = relay_service.Relay(orbio_config(tmp_path / "relay", key))
    assert relay.key == RIGHT_ORBIO_KEY.decode()
    assert not (tmp_path / "relay" / "state" / RECORD_NAME).exists()


def test_an_openrouter_release_still_starts_with_its_own_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    relay = relay_service.Relay(openrouter_config(tmp_path / "relay", OPENROUTER_SHAPED_KEY, monkeypatch))
    assert relay.key == OPENROUTER_SHAPED_KEY.decode()


@pytest.mark.parametrize("key, reason", WRONG_FOR_ORBIO)
def test_the_real_relay_process_exits_and_prints_no_part_of_a_refused_key(tmp_path: Path, key: bytes, reason: str) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(orbio_config(tmp_path / "relay", key)))
    support = f"{REPO / 'scripts/hermes_job_support'}:{REPO / 'scripts/hermes_interpretation'}"

    ended = subprocess.run([sys.executable, "-B", str(REPO / "scripts/hermes_provider_relay/relay_service.py"), str(path)],
                           capture_output=True, timeout=30, env={**os.environ, "RELAY_SUPPORT_PATH": support})

    assert ended.returncode == 1 and ended.stdout == b""
    assert ended.stderr == f"the provider key file is refused: {reason}\n".encode()
    saved = (tmp_path / "relay" / "state" / RECORD_NAME).read_bytes()
    assert not [piece for piece in fragments(key) if piece in saved.lower() or piece in ended.stderr.lower()]
