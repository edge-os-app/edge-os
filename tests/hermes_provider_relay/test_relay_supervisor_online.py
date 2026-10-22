"""The supervisor's E1 topology (CONTRACT A6), checked on the Docker commands it would issue. A fake `docker` records
every call: nothing runs, no network, no container. The real start, isolation and cleanup are Docker-suite checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

import relay_admission
import relay_supervisor
from relay_admission import ActualRelease, RelayRelease, load_actual_release
from relay_supervisor import LABEL, RelaySupervisor

from conftest import SENTINEL

RELEASE = RelayRelease("local-relay-1", "authored-local-1", "AUTHORED", "fixture-model/1", 4096, 12_000, 65_536)
STAND_IN_IP = "172.30.0.2"


class FakeDocker:
    """Answers like Docker and plays each container's readiness file, so `start()` runs to the end."""

    def __init__(self, supervisor: RelaySupervisor) -> None:
        self.supervisor, self.calls = supervisor, []

    def __call__(self, *args: str, timeout: float = 0, check: bool = True) -> Any:
        self.calls.append(list(args))
        out = ""
        if args[0] == "run":
            name = args[args.index("--name") + 1]
            out = f"id-{name}"
            if name.startswith("relay-provider-"):
                self.supervisor.path("provider", "receipts", "ready").write_text("{}")
            elif name.startswith("relay-gateway-"):
                self.supervisor.path("gateway", "receipts", "ready").write_text("{}")
            else:
                self.supervisor.path("state", "heartbeat.json").write_text(json.dumps({"started_at": 1e12}))
        elif args[:2] == ("network", "create") or args[:2] == ("volume", "create"):
            out = f"id-{args[-1]}"
        elif args[0] == "inspect" and "--format" in args:
            out = STAND_IN_IP
        return type("Done", (), {"stdout": out, "stderr": "", "returncode": 0})()

    def runs(self) -> dict[str, list[str]]:
        return {call[call.index("--name") + 1].removesuffix("-hpr-unit"): call for call in self.calls if call[0] == "run"}


def mounts(argv: list[str]) -> dict[str, str]:
    found = {}
    for flag, value in zip(argv, argv[1:]):
        if flag == "--mount":
            parts = dict(item.split("=", 1) if "=" in item else (item, "") for item in value.split(","))
            found[parts["dst"]] = value
    return found


def supervisor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> tuple[RelaySupervisor, FakeDocker]:
    key = tmp_path / "provider-key"
    key.write_text(SENTINEL)
    key.chmod(0o400)
    fields = {"root": tmp_path / "relay", "release": RELEASE, "image": "pinned:test", "run_id": "hpr-unit",
              "provider_key_file": key, "channel_roots": {"jobs": tmp_path / "jobs"}, "online": True, **kwargs}
    made = RelaySupervisor(**fields)
    fake = FakeDocker(made)
    monkeypatch.setattr(relay_supervisor, "docker", fake)
    monkeypatch.setattr(relay_supervisor, "make_provider_tls",
                        lambda folder, hosts: [folder.mkdir(parents=True, exist_ok=True),
                                               *(folder.joinpath(n).write_text(",".join(hosts))
                                                 for n in ("ca.pem", "server.pem", "server.key"))])
    return made, fake


def test_the_online_topology_is_a_keyless_gateway_on_its_own_bridge_and_a_relay_with_no_network(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    made, fake = supervisor(tmp_path, monkeypatch)
    made.start()
    network = ["network", "create", "--driver", "bridge", "--label", f"{LABEL}=hpr-unit", "relay-egress-hpr-unit"]
    assert network in fake.calls and not any("--internal" in call for call in fake.calls)
    [volume] = [call for call in fake.calls if call[:2] == ["volume", "create"]]
    assert f"o=uid={os.getuid()},gid={os.getgid()},mode=0700,size=1m" in volume and "type=tmpfs" in volume
    runs = fake.runs()
    assert list(runs) == ["relay-provider", "relay-gateway", "relay"]  # stand-in, then gateway, then relay
    for role, argv in runs.items():
        for flag in relay_supervisor.HARDENING:
            assert flag in argv, (role, flag)
        assert not {"-p", "--publish", "--privileged", "--cap-add", "--net=host"} & set(argv)
        assert not any("docker.sock" in item for item in argv)
    assert runs["relay"][runs["relay"].index("--network") + 1] == "none"
    for role in ("relay-gateway", "relay-provider"):
        assert runs[role][runs[role].index("--network") + 1] == "relay-egress-hpr-unit"
    relay_mounts, gateway_mounts = mounts(runs["relay"]), mounts(runs["relay-gateway"])
    assert "type=volume,src=relay-egress-hpr-unit" in relay_mounts["/relay/egress"]
    assert "type=volume,src=relay-egress-hpr-unit" in gateway_mounts["/egress"]
    assert "/relay/secrets/provider-key" in relay_mounts
    assert not any("key" in target for target in gateway_mounts)  # the gateway holds no key and no CA
    assert set(gateway_mounts) == {"/egress", "/gateway/receipts", "/gateway/egress_gateway.py", "/gateway/config.json"}


def test_the_online_configs_fix_the_destination_and_the_test_resolution_names_the_stand_in(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    made, _ = supervisor(tmp_path, monkeypatch)
    made.start()
    relay = json.loads(made.path("relay-config.json").read_text())
    gateway = json.loads(made.path("gateway-config.json").read_text())
    provider = json.loads(made.path("provider-config.json").read_text())
    assert relay["destination"] == {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"}
    assert (relay["gateway_socket"], relay["egress_probes"]) == ("/relay/egress/gateway.sock", [])
    assert gateway == {"socket": "/egress/gateway.sock", "receipts": "/gateway/receipts", "test_resolution": STAND_IN_IP,
                       "destination": {"host": "openrouter.ai", "port": 443}}  # the gateway's one allowed target
    assert (provider["bind"], provider["port"], provider["path"]) == ("0.0.0.0", 443, "/api/v1/chat/completions")
    assert made.path("tls", "server.pem").read_text() == "openrouter.ai"  # a test CA for the stand-in only


def test_stop_removes_every_container_the_network_and_the_socket_volume(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    made, fake = supervisor(tmp_path, monkeypatch)
    made.start()
    fake.calls.clear()
    made.stop()
    removed = [call for call in fake.calls if call[:2] == ["rm", "-f"]]
    assert sorted(call[2] for call in removed) == ["relay-gateway-hpr-unit", "relay-hpr-unit", "relay-provider-hpr-unit"]
    assert ["network", "rm", "relay-egress-hpr-unit"] in fake.calls
    assert ["volume", "rm", "relay-egress-hpr-unit"] in fake.calls


@pytest.fixture
def actual(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ActualRelease, Path, Path]:
    bundle = tmp_path / "ca-bundle.pem"
    bundle.write_bytes(b"synthetic CA bundle")
    raw = json.dumps({
        "release_id": "rel-synthetic-1", "route_id": "route-synthetic", "kind": "ACTUAL",
        "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
        "destination": {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"},
        "ca_bundle_sha256": hashlib.sha256(b"synthetic CA bundle").hexdigest(), "model": "fixture-model/1",
        "provider": {"only": ["s"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
                     "max_price": {"prompt": 1, "completion": 2}}, "max_tokens": 4096, "reasoning": None,
        "response_format_sha256": "d" * 64, "stream": False,
        "allowed_fields": ["model", "messages", "stream", "provider", "max_tokens", "session_id"],
        "max_request_bytes": 12_000, "max_reply_bytes": 65_536, "timeout_seconds": 90,
        "price_snapshot_sha256": "c" * 64}).encode()
    record = tmp_path / "release.json"
    record.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({sha}))
    return load_actual_release(raw, sha), record, bundle


def test_an_actual_supervisor_runs_no_stand_in_and_no_test_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                      actual: Any) -> None:
    release, record, bundle = actual
    made, fake = supervisor(tmp_path, monkeypatch, release=release.release, actual=release, release_record=record,
                            ca_bundle_file=bundle)
    made.start()
    assert list(fake.runs()) == ["relay-gateway", "relay"]
    assert "test_resolution" not in json.loads(made.path("gateway-config.json").read_text())
    relay = json.loads(made.path("relay-config.json").read_text())
    assert relay["release_record"] == {"path": "/relay/release/record.json", "sha256": release.record_sha256}
    assert "release" not in relay and "destination" not in relay
    assert mounts(fake.runs()["relay"])["/relay/tls/ca.pem"].startswith(f"type=bind,src={bundle.resolve()},")


@pytest.mark.parametrize("problem", ["ca", "key_mode", "release"])
def test_an_actual_supervisor_refuses_a_mismatched_ca_a_readable_key_or_another_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actual: Any, problem: str) -> None:
    release, record, bundle = actual
    if problem == "ca":
        bundle.write_bytes(b"another bundle")
    kwargs = {"release": RELEASE if problem == "release" else release.release, "actual": release,
              "release_record": record, "ca_bundle_file": bundle}
    with pytest.raises(ValueError):
        if problem == "key_mode":
            key = tmp_path / "provider-key"
            key.write_text(SENTINEL)
            key.chmod(0o644)
            RelaySupervisor(root=tmp_path / "relay", image="i", run_id="r", provider_key_file=key,
                            channel_roots={}, online=True, **kwargs)
        else:
            supervisor(tmp_path, monkeypatch, **kwargs)


def test_the_loopback_topology_is_unchanged_when_online_is_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    made, fake = supervisor(tmp_path, monkeypatch, online=False)
    made.start()
    runs = fake.runs()
    assert list(runs) == ["relay-provider", "relay"]
    assert runs["relay"][runs["relay"].index("--network") + 1] == "container:id-relay-provider-hpr-unit"
    assert not any(call[:2] in (["network", "create"], ["volume", "create"]) for call in fake.calls)


def test_a_gateway_restart_keeps_its_receipts_and_test_resolution_and_touches_no_relay_record(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    made, fake = supervisor(tmp_path, monkeypatch)
    made.start()
    made.path("gateway", "receipts", "tunnels.jsonl").write_text('{"attempt_id": "a1"}\n')
    fake.calls.clear()
    made.restart_gateway()
    assert [call[:2] for call in fake.calls[:2]] == [["kill", "relay-gateway-hpr-unit"], ["rm", "-f"]]
    assert list(fake.runs()) == ["relay-gateway"]
    assert made.path("gateway", "receipts", "tunnels.jsonl").read_text() == '{"attempt_id": "a1"}\n'
    assert json.loads(made.path("gateway-config.json").read_text())["test_resolution"] == STAND_IN_IP
    assert made.roles() == ("relay", "gateway", "provider")
