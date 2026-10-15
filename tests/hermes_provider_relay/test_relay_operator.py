"""The relay operator entry: configuration admission, ownership, immutable handoff, cleanup and restart. No Docker runs:
a fake `docker` records every call and plays the containers' readiness files. Synthetic key, record and CA only."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import relay_admission
import relay_operator
import relay_supervisor
from relay_operator import OperatorRefused, load_config, main, read_handoff

from conftest import SENTINEL

IMAGE_ID = "sha256:" + "1" * 64
OTHER_ID = "sha256:" + "2" * 64
SETTINGS = {"release_id": "local-relay-1", "route_id": "authored-local-1", "kind": "AUTHORED",
            "model": "fixture-model/1", "max_output_tokens": 4096, "max_request_bytes": 12_000, "max_reply_bytes": 65_536}
SCHEMA = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {"type": "object"}}}
ROUTING = {"only": ["synthetic-slug"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 1, "completion": 2}}


class FakeDocker:
    """Answers like Docker. `existing` names objects that already exist; `fail_run` makes that container's run fail."""

    def __init__(self, image_id: str = IMAGE_ID, existing: set[str] = frozenset(), fail_run: str | None = None) -> None:
        self.image_id, self.existing, self.fail_run = image_id, set(existing), fail_run
        self.calls: list[list[str]] = []
        self.supervisor_root: Path | None = None
        self.beats = itertools.count(1)

    def __call__(self, *args: str, timeout: float = 0, check: bool = True) -> Any:
        self.calls.append(list(args))
        out, code = "", 0
        if args[:2] == ("image", "inspect"):
            out = self.image_id
        elif args[0] == "inspect" and args[1] == "--type":
            code = 0 if args[3] in self.existing else 1
        elif args[0] == "inspect":
            out = "172.30.0.2"  # the AUTHORED stand-in's bridge address
        elif args[0] == "run":
            name = args[args.index("--name") + 1]
            if self.fail_run is not None and name.startswith(self.fail_run):
                raise subprocess.CalledProcessError(125, ["docker", *args], "", "synthetic failure /secret/path")
            root = self.supervisor_root
            assert root is not None
            out = f"id-{name}"
            if name.startswith("relay-provider-"):
                (root / "provider" / "receipts" / "ready").write_text("{}")
            elif name.startswith("relay-gateway-"):
                (root / "gateway" / "receipts" / "ready").write_text("{}")
            else:
                (root / "state" / "heartbeat.json").write_text(json.dumps({"started_at": 1e12 + next(self.beats)}))
        return type("Done", (), {"stdout": out, "stderr": "", "returncode": code})()

    def runs(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "run"]

    def effects(self) -> list[list[str]]:
        """Every call that creates or removes something."""
        return [call for call in self.calls if call[0] in ("run", "rm", "kill") or call[1:2] in (["create"], ["rm"])]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    made = FakeDocker()
    monkeypatch.setattr(relay_supervisor, "docker", made)
    monkeypatch.setattr(relay_supervisor, "make_provider_tls",
                        lambda folder, hosts: [folder.mkdir(parents=True, exist_ok=True),
                                               *(folder.joinpath(n).write_text("synthetic") for n in
                                                 ("ca.pem", "server.pem", "server.key"))])
    return made


@pytest.fixture
def key(tmp_path: Path) -> Path:
    folder = tmp_path / "secrets"
    folder.mkdir(mode=0o700)
    path = folder / "provider-key"
    path.write_text(SENTINEL)
    path.chmod(0o400)
    return path


def config(tmp_path: Path, key: Path, **changes: Any) -> dict[str, Any]:
    value = {"format": "edge-os.relay-operator-config/1", "operation_id": "hpr-op-unit", "kind": "AUTHORED",
             "release": dict(SETTINGS), "release_record": None, "ca_bundle": None,
             "image": {"reference": "edge-os-p05-hermes:unit", "id": IMAGE_ID}, "run_root": str(tmp_path / "run"),
             "channel": {"name": "jobs", "path": str(tmp_path / "jobs")}, "provider_key_file": str(key),
             "shutdown_owner": "relay_operator"}
    value.update(changes)
    return value


def write(tmp_path: Path, value: dict[str, Any], name: str = "operator.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value))
    return path


def started(tmp_path: Path, key: Path, fake: FakeDocker, **changes: Any) -> tuple[relay_operator.OperatorConfig, Path, str]:
    loaded = load_config(json.dumps(config(tmp_path, key, **changes)).encode())
    fake.supervisor_root = loaded.run_root / "relay"
    path, sha = relay_operator.start(loaded)
    return loaded, path, sha


# --- admission before any effect ----------------------------------------------------------------------------------------

def test_check_is_the_default_command_and_makes_no_docker_call_and_no_write(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path)]) == 0
    assert "kind AUTHORED operation hpr-op-unit admitted" in capsys.readouterr().out
    assert fake.calls == [] and not (tmp_path / "run").exists() and not (tmp_path / "jobs").exists()


def test_the_cli_entry_point_runs_as_a_script(tmp_path: Path, key: Path) -> None:
    path = write(tmp_path, config(tmp_path, key))
    done = subprocess.run([sys.executable, str(Path(relay_operator.__file__)), str(path)], capture_output=True,
                          text=True, timeout=60, env={**os.environ, "PATH": ""})  # no docker can be found or run
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("config ") and SENTINEL not in done.stdout + done.stderr


@pytest.mark.parametrize("change", [
    {"format": "edge-os.relay-operator-config/0"},
    {"shutdown_owner": "application"},
    {"operation_id": "Has_Upper"},
    {"operation_id": "x" * 41},
    {"image": {"reference": "edge-os-p05-hermes:unit", "id": "sha256:short"}},
    {"image": {"reference": "a b", "id": IMAGE_ID}},
    {"channel": {"name": "../jobs", "path": "/tmp/jobs"}},
    {"channel": {"name": "jobs", "path": "relative/jobs"}},
    {"run_root": "relative/run"},
    {"kind": "OTHER"},
    {"release": {**SETTINGS, "kind": "ACTUAL"}},  # an ACTUAL release cannot come from settings
    {"release": {**SETTINGS, "extra": 1}},
    {"release": {**SETTINGS, "max_reply_bytes": 0}},
    {"release_record": {"path": "/x/record.json", "sha256": "a" * 64}},  # AUTHORED takes no record
    {"extra": True},
])
def test_an_invalid_configuration_is_refused_before_any_effect(
        tmp_path: Path, key: Path, fake: FakeDocker, change: dict[str, Any]) -> None:
    path = write(tmp_path, config(tmp_path, key, **change))
    assert main([str(path), "start"]) == 2
    assert fake.calls == [] and not (tmp_path / "run").exists()


def test_repeated_keys_and_constants_are_refused(tmp_path: Path) -> None:
    for raw in (b'{"format": 1, "format": 2}', b'{"format": NaN}', b"[]", b"\xff"):
        with pytest.raises(OperatorRefused):
            load_config(raw)


@pytest.mark.parametrize("problem", ["readable_by_group", "link", "missing", "inside_repository"])
def test_the_provider_key_file_must_be_an_owner_only_file_outside_the_repository(
        tmp_path: Path, key: Path, fake: FakeDocker, monkeypatch: pytest.MonkeyPatch, problem: str) -> None:
    target = key
    if problem == "readable_by_group":
        key.chmod(0o440)
    elif problem == "link":
        target = tmp_path / "secrets" / "link"
        target.symlink_to(key)
    elif problem == "missing":
        target = tmp_path / "secrets" / "absent"
    else:
        monkeypatch.setattr(relay_operator, "REPO", tmp_path)
    path = write(tmp_path, config(tmp_path, key, provider_key_file=str(target)))
    assert main([str(path), "start"]) == 2
    assert fake.calls == [] and not (tmp_path / "run").exists()


# --- ACTUAL: only the default registry, the record and its CA bundle ----------------------------------------------------

def actual_files(tmp_path: Path, **record_changes: Any) -> tuple[dict[str, str], dict[str, str]]:
    ca = tmp_path / "ca-bundle.pem"
    ca.write_text("synthetic CA bundle")
    record = {"release_id": "rel-synthetic-1", "route_id": "route-synthetic", "kind": "ACTUAL",
              "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
              "destination": {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"},
              "ca_bundle_sha256": hashlib.sha256(ca.read_bytes()).hexdigest(), "model": "synthetic/model-1",
              "provider": ROUTING, "max_tokens": 4096, "reasoning": {"effort": "low"},
              "response_format_sha256": hashlib.sha256(json.dumps(SCHEMA, sort_keys=True, separators=(",", ":"))
                                                       .encode()).hexdigest(),
              "stream": False, "allowed_fields": ["model", "messages", "stream", "response_format", "provider",
                                                  "reasoning", "max_tokens", "session_id"],
              "max_request_bytes": 65_536, "max_reply_bytes": 262_144, "timeout_seconds": 90,
              "price_snapshot_sha256": "c" * 64, **record_changes}
    path = tmp_path / "record.json"
    path.write_bytes(json.dumps(record).encode())
    return ({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
            {"path": str(ca), "sha256": record["ca_bundle_sha256"]})


def actual_config(tmp_path: Path, key: Path) -> dict[str, Any]:
    record, ca = actual_files(tmp_path)
    return config(tmp_path, key, kind="ACTUAL", release=None, release_record=record, ca_bundle=ca)


def test_an_actual_configuration_is_refused_by_the_empty_default_registry(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset()
    path = write(tmp_path, actual_config(tmp_path, key))
    assert main([str(path), "start"]) == 2
    assert "not an approved ACTUAL release" in capsys.readouterr().err
    assert fake.calls == [] and not (tmp_path / "run").exists()


def approve(monkeypatch: pytest.MonkeyPatch, value: dict[str, Any]) -> None:
    """Test-only: patch the module registry, as the accepted ACTUAL tests do. No production caller can pass one."""
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({value["release_record"]["sha256"]}))


@pytest.mark.parametrize("mismatch", ["record_bytes", "ca_named_hash", "ca_file_bytes", "settings_given"])
def test_a_mismatched_actual_record_or_ca_bundle_is_refused_before_any_effect(
        tmp_path: Path, key: Path, fake: FakeDocker, monkeypatch: pytest.MonkeyPatch, mismatch: str) -> None:
    value = actual_config(tmp_path, key)
    approve(monkeypatch, value)
    if mismatch == "record_bytes":
        Path(value["release_record"]["path"]).write_bytes(Path(value["release_record"]["path"]).read_bytes() + b" ")
    elif mismatch == "ca_named_hash":
        value["ca_bundle"]["sha256"] = "d" * 64
    elif mismatch == "ca_file_bytes":
        Path(value["ca_bundle"]["path"]).write_text("another CA")
    else:
        value["release"] = dict(SETTINGS)
    assert main([str(write(tmp_path, value)), "start"]) == 2
    assert fake.calls == [] and not (tmp_path / "run").exists()


def test_an_approved_actual_record_starts_the_e1_topology_with_no_stand_in_and_hands_off_the_record(
        tmp_path: Path, key: Path, fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> None:
    value = actual_config(tmp_path, key)
    approve(monkeypatch, value)
    loaded, path, sha = started(tmp_path, key, fake, **{k: value[k] for k in
                                                         ("kind", "release", "release_record", "ca_bundle")})
    assert [call[call.index("--name") + 1] for call in fake.runs()] == ["relay-gateway-hpr-op-unit",
                                                                         "relay-hpr-op-unit"]
    handoff = read_handoff(path, sha)
    assert handoff.kind == "ACTUAL" and handoff.release == loaded.release.settings()
    assert handoff.release_record == (Path(value["release_record"]["path"]), value["release_record"]["sha256"])
    assert handoff.ca_bundle_sha256 == value["ca_bundle"]["sha256"]


# --- image identity, ownership and foreign resources --------------------------------------------------------------------

def test_a_reference_that_does_not_name_the_configured_image_id_is_refused_before_any_effect(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    fake.image_id = OTHER_ID  # the tag was moved to another image
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path), "start"]) == 2
    assert fake.effects() == [] and not (tmp_path / "run").exists()


def test_every_container_is_launched_by_the_immutable_image_id_never_the_reference(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    started(tmp_path, key, fake)
    runs = fake.runs()
    assert len(runs) == 3
    for argv in runs:
        assert IMAGE_ID in argv and "edge-os-p05-hermes:unit" not in argv


@pytest.mark.parametrize("name", ["relay-hpr-op-unit", "relay-gateway-hpr-op-unit", "relay-provider-hpr-op-unit",
                                  "relay-egress-hpr-op-unit"])
def test_an_existing_resource_under_the_operation_names_is_foreign_and_nothing_is_started_or_removed(
        tmp_path: Path, key: Path, fake: FakeDocker, name: str) -> None:
    fake.existing.add(name)
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path), "start"]) == 2
    assert fake.effects() == [] and not (tmp_path / "run").exists()


def test_an_operation_starts_once(tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    started(tmp_path, key, fake)
    before = len(fake.calls)
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path), "start"]) == 2
    assert len(fake.calls) == before


@pytest.mark.parametrize("command", ["restart", "stop"])
def test_restart_and_stop_refuse_a_run_root_of_another_configuration(
        tmp_path: Path, key: Path, fake: FakeDocker, command: str) -> None:
    started(tmp_path, key, fake)
    before = len(fake.calls)
    other = write(tmp_path, config(tmp_path, key, release={**SETTINGS, "release_id": "local-relay-2"}), "other.json")
    assert main([str(other), command]) == 2
    assert len(fake.calls) == before


@pytest.mark.parametrize("command", ["restart", "stop"])
def test_restart_and_stop_refuse_a_run_root_no_operator_started(
        tmp_path: Path, key: Path, fake: FakeDocker, command: str) -> None:
    (tmp_path / "run").mkdir()
    assert main([str(write(tmp_path, config(tmp_path, key))), command]) == 2
    assert fake.calls == []


# --- handoff ------------------------------------------------------------------------------------------------------------

def test_the_handoff_is_immutable_redacted_and_gives_the_accepted_endpoint(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, config(tmp_path, key))
    fake.supervisor_root = tmp_path / "run" / "relay"
    assert main([str(path), "start"]) == 0
    printed = capsys.readouterr().out
    handoff_path = tmp_path / "run" / "handoff.json"
    raw = handoff_path.read_bytes()
    assert printed == f"handoff {handoff_path} sha256 {hashlib.sha256(raw).hexdigest()}\n"
    assert stat.S_IMODE(handoff_path.stat().st_mode) == 0o444
    admission_key = (tmp_path / "run" / "relay" / "secrets" / "admission-key").read_bytes()
    for secret in (SENTINEL.encode(), str(key).encode(), admission_key, admission_key.hex().encode()):
        assert secret not in raw and secret.decode(errors="ignore") not in printed
    loaded = load_config(path.read_bytes())
    handoff = read_handoff(handoff_path, hashlib.sha256(raw).hexdigest())
    assert handoff.endpoint == loaded.supervisor().endpoint("jobs")
    assert handoff.endpoint.channel_root == "jobs" and handoff.evidence_dir == tmp_path / "jobs"
    assert (handoff.release, handoff.release_record, handoff.ca_bundle_sha256) == (SETTINGS, None, None)
    assert (handoff.image_reference, handoff.image_id) == ("edge-os-p05-hermes:unit", IMAGE_ID)
    assert handoff.config_sha256 == loaded.sha256
    with pytest.raises(FileExistsError):
        relay_operator._write_once(handoff_path, {"replaced": True}, 0o444)
    assert handoff_path.read_bytes() == raw


def test_read_handoff_refuses_other_bytes_and_other_shapes(tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    _, path, sha = started(tmp_path, key, fake)
    with pytest.raises(OperatorRefused, match="hash"):
        read_handoff(path, "0" * 64)
    value = json.loads(path.read_text())
    for changed in ({**value, "provider_key_file": "/x"}, {**value, "format": "other"},
                    {**value, "kind": "ACTUAL"}, {**value, "shutdown_owner": "application"},
                    {**value, "endpoint": {**value["endpoint"], "extra": 1}}):
        other = tmp_path / "other-handoff.json"
        other.write_bytes(json.dumps(changed).encode())
        with pytest.raises(OperatorRefused):
            read_handoff(other, hashlib.sha256(other.read_bytes()).hexdigest())
        other.unlink()


# --- failure, restart and stop ------------------------------------------------------------------------------------------

def test_a_failed_start_removes_exactly_what_it_started_and_writes_no_handoff(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    fake.fail_run = "relay-gateway-"  # the stand-in is running, the gateway launch fails
    fake.supervisor_root = tmp_path / "run" / "relay"
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert capsys.readouterr().err == "failed: CalledProcessError\n"  # no argument, mount path or stderr text
    removed = [call for call in fake.calls if call[0] == "rm" or call[1:2] == ["rm"]]
    assert removed == [["rm", "-f", "relay-hpr-op-unit"], ["rm", "-f", "relay-gateway-hpr-op-unit"],
                       ["rm", "-f", "relay-provider-hpr-op-unit"], ["network", "rm", "relay-egress-hpr-op-unit"],
                       ["volume", "rm", "relay-egress-hpr-op-unit"]]
    failed = json.loads((tmp_path / "run" / "start-failed.json").read_text())
    assert failed == {"error": "CalledProcessError",
                      "cleanup": {"containers_left": [], "networks_left": [], "volumes_left": []}}
    assert not (tmp_path / "run" / "handoff.json").exists()


def test_restart_keeps_every_relay_record_so_a_started_attempt_is_never_sent_again(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key, fake)
    attempt = loaded.run_root / "relay" / "state" / "attempt-1"
    attempt.mkdir()
    (attempt / "started.json").write_text('{"grant_id": "g-1"}')  # started, no finished: recovery C marks it lost
    before = sorted(p.relative_to(loaded.run_root) for p in loaded.run_root.rglob("*") if p.name != "heartbeat.json")
    fake.calls.clear()
    relay_operator.restart(loaded)
    assert [call[:2] for call in fake.calls] == [["kill", "relay-hpr-op-unit"], ["rm", "-f"], ["run", "-d"]]
    assert IMAGE_ID in fake.calls[-1]
    after = sorted(p.relative_to(loaded.run_root) for p in loaded.run_root.rglob("*") if p.name != "heartbeat.json")
    assert after == before and (attempt / "started.json").read_text() == '{"grant_id": "g-1"}'


def test_stop_removes_exactly_the_operation_resources_records_once_and_a_stopped_operation_is_not_restarted(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    loaded, _, _ = started(tmp_path, key, fake)
    path = write(tmp_path, config(tmp_path, key))
    fake.calls.clear()
    assert main([str(path), "stop"]) == 0
    assert [call for call in fake.calls if call[0] == "rm" or call[1:2] == ["rm"]] == [
        ["rm", "-f", "relay-hpr-op-unit"], ["rm", "-f", "relay-gateway-hpr-op-unit"],
        ["rm", "-f", "relay-provider-hpr-op-unit"], ["network", "rm", "relay-egress-hpr-op-unit"],
        ["volume", "rm", "relay-egress-hpr-op-unit"]]
    stopped = (loaded.run_root / "stopped.json").read_bytes()
    assert main([str(path), "stop"]) == 0  # stopping again checks again and keeps the first record
    assert (loaded.run_root / "stopped.json").read_bytes() == stopped
    capsys.readouterr()
    fake.calls.clear()
    assert main([str(path), "restart"]) == 2 and fake.calls == []
    assert (loaded.run_root / "handoff.json").exists()  # evidence stays; the operator removes no files


def test_stop_reports_leftovers_with_a_failing_exit(tmp_path: Path, key: Path, fake: FakeDocker,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    started(tmp_path, key, fake)

    def leftover(*args: str, **kwargs: Any) -> Any:
        if args[:1] == ("ps",):
            return type("Done", (), {"stdout": "relay-hpr-op-unit\n", "stderr": "", "returncode": 0})()
        return fake(*args, **kwargs)

    monkeypatch.setattr(relay_supervisor, "docker", leftover)
    assert main([str(write(tmp_path, config(tmp_path, key))), "stop"]) == 1


# --- Docker (needs a capacity grant; select with -k docker) ------------------------------------------------------------

def test_docker_the_cli_runs_the_e1_relay_from_the_handoff_and_stops_with_nothing_left(
        pinned_hermes_image: str, evidence_root: Path, synthetic_key: Path, run_id: str) -> None:
    """The real CLI starts an owned AUTHORED E1 operation; one application-shaped turn uses only the handoff (endpoint,
    evidence folder, image id); the CLI stops it and nothing labelled is left. Synthetic key and stand-in only."""
    from edge_os_api.research.hermes_interpreter import Interpreted
    from leak_scan import find_leaks
    from relay_harness import EXACT_CHARGE, RELEASE, Rig, case, counts

    root = evidence_root / "operator"
    root.mkdir()
    image_id = relay_supervisor.docker("image", "inspect", pinned_hermes_image, "--format", "{{.Id}}").stdout.strip()
    value = config(root, synthetic_key, operation_id=f"op-{run_id}"[:40], release=RELEASE.settings(),
                   image={"reference": pinned_hermes_image, "id": image_id})
    path = write(root, value)

    def cli(command: str) -> subprocess.CompletedProcess[str]:
        done = subprocess.run([sys.executable, str(Path(relay_operator.__file__)), str(path), command],
                              capture_output=True, text=True, timeout=600)
        (root / f"cli-{command}.txt").write_text(f"{done.returncode}\n{done.stdout}{done.stderr}")
        return done

    started_cli = cli("start")
    try:
        assert started_cli.returncode == 0, started_cli.stderr
        _, handoff_path, _, sha = started_cli.stdout.split()
        handoff = read_handoff(Path(handoff_path), sha)
        supervisor = load_config(path.read_bytes()).supervisor()  # names and paths only; constructing does nothing

        class FromHandoff:  # what the application has: the handoff endpoint, nothing from the operator's memory
            run_id = supervisor.run_id
            path = staticmethod(supervisor.path)

            @staticmethod
            def endpoint(name: str) -> Any:
                assert name == handoff.endpoint.channel_root
                return handoff.endpoint

        assert handoff.evidence_dir == root / "jobs" and supervisor.heartbeat()["release"] == handoff.release
        rig = Rig(FromHandoff(), handoff.image_id, root, "op-valid", case())
        assert isinstance(rig.run_case(), Interpreted)
        assert counts(supervisor, "op-valid-1") == (1, 1)
        assert rig.spend.committed_usd() == EXACT_CHARGE
        assert SENTINEL.encode() not in Path(handoff_path).read_bytes()
        assert find_leaks(root / "jobs", SENTINEL) == []
    finally:
        stopped_cli = cli("stop")
    assert stopped_cli.returncode == 0, stopped_cli.stdout + stopped_cli.stderr
    assert json.loads((root / "run" / "stopped.json").read_text())["left"] == {
        "containers_left": [], "networks_left": [], "volumes_left": []}
