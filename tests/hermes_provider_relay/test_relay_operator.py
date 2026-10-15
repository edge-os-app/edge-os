"""The relay operator entry: configuration admission, ownership, immutable handoff, cleanup and restart. No Docker runs:
a fake `docker` keeps containers, networks and volumes (name, id, label, mounts), refuses a second object under one name
like Docker does, and plays the containers' readiness files. Synthetic key, record and CA only."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import relay_admission
import relay_operator
import relay_supervisor
from relay_operator import OperatorRefused, load_config, main, read_handoff
from relay_supervisor import LABEL

from conftest import SENTINEL

IMAGE_ID = "sha256:" + "1" * 64
OTHER_ID = "sha256:" + "2" * 64
SETTINGS = {"release_id": "local-relay-1", "route_id": "authored-local-1", "kind": "AUTHORED",
            "model": "fixture-model/1", "max_output_tokens": 4096, "max_request_bytes": 12_000, "max_reply_bytes": 65_536}
SCHEMA = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {"type": "object"}}}
ROUTING = {"only": ["synthetic-slug"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 1, "completion": 2}}
KINDS = ("container", "network", "volume")


DOCKER_29_ABSENT = {  # Docker 29.4.0 `docker inspect --type KIND NAME` for no such object, recorded in RUNTIME1
    "network": "Error response from daemon: network {name} not found",
    "container": "Error response from daemon: No such container: {name}",
    "volume": "Error response from daemon: get {name}: no such volume"}


DOCKER_29_WRAPPED = {  # the same Docker 29.4.0 answers with the daemon's JSON body, recorded in RUNTIME2
    kind: 'Error response from daemon: {"message":"' + line.removeprefix("Error response from daemon: ") + '"}'
    for kind, line in DOCKER_29_ABSENT.items()}


def absent_answer(wording: str, kind: str, name: str) -> str:
    if wording in ("docker-29.4.0", "docker-29.4.0-json"):
        table = DOCKER_29_ABSENT if wording == "docker-29.4.0" else DOCKER_29_WRAPPED
        return table[kind].replace("{name}", name) + "\n"  # the JSON braces are not format fields
    return f"Error: No such object: {name}\n"


def done(stdout: str = "", code: int = 0, stderr: str = "") -> Any:
    return type("Done", (), {"stdout": stdout, "stderr": stderr, "returncode": code})()


class FakeDocker:
    """Docker's object model as far as the operator and supervisor use it. `objects[kind][name]` is {Id, Labels, Mounts}.
    `before_create(kind, name)` runs before each create and `on_inspect(name)` before each inspect, so a test can put a
    competing object in place. A missing object answers like Docker 29.4.0 (`absent_wording`: each kind's own text,
plain or in the daemon's JSON body, or the generic "No such object" of other versions); a second network or container
    under one name is refused; a second `volume create` of a local volume re-uses the first without an error, as Docker
    documents (docker/cli docs/reference/commandline/volume_create.md). Fault switches: `daemon_down`,
    `malformed` (names whose inspect reply is not JSON), `fail_list`, `fail_rm` (names or ids whose removal fails)."""

    def __init__(self) -> None:
        self.image_id = IMAGE_ID
        self.calls: list[list[str]] = []
        self.objects: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in KINDS}
        self.ids = itertools.count(1)
        self.beats = itertools.count(1)
        self.fail_run: str | None = None  # a container name prefix whose launch fails
        self.before_create: Callable[[str, str], None] | None = None
        self.raise_on_rm: BaseException | None = None
        self.on_inspect: Callable[[str], None] | None = None
        self.daemon_down = False
        self.malformed: set[str] = set()
        self.fail_list = False
        self.fail_rm: set[str] = set()
        self.inspect_error: set[str] = set()  # names whose inspect fails with an error that is not "no such object"
        self.ignore_rm: set[str] = set()  # ids whose removal answers success but leaves the object
        self.absent_wording = "docker-29.4.0"

    def add(self, kind: str, name: str, *, label: str | None, sources: tuple[str, ...] = (),
            labels: dict[str, str] | None = None) -> str:
        identity = f"{kind[0]}{next(self.ids):04d}"
        self.objects[kind][name] = {"Id": identity, "Name": name,
                                    "Labels": {**({LABEL: label} if label else {}), **(labels or {})},
                                    "Mounts": [{"Source": source} for source in sources]}
        return identity

    def find(self, kind: str, key: str) -> str | None:
        for name, value in self.objects[kind].items():
            if key in (name, value["Id"]):
                return name
        return None

    def __call__(self, *args: str, timeout: float = 0, check: bool = True) -> Any:
        self.calls.append(list(args))
        if self.daemon_down:
            if check:
                raise subprocess.CalledProcessError(1, ["docker", *args], "", "Cannot connect to the Docker daemon")
            return done(code=1, stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock")
        if args[:2] == ("image", "inspect"):
            return done(self.image_id)
        if args[0] == "inspect" and args[1] == "--type":
            if self.on_inspect is not None:
                self.on_inspect(args[3])
            if args[3] in self.malformed:
                return done("<html>proxy error</html>")
            if args[3] in self.inspect_error:
                return done(code=1, stderr="Error response from daemon: i/o timeout")
            name = self.find(args[2], args[3])
            if name is None:
                return done("[]", 1, absent_answer(self.absent_wording, args[2], args[3]))
            value = self.objects[args[2]][name]
            shaped = ({"Id": value["Id"], "Name": "/" + name, "Config": {"Labels": value["Labels"]},
                       "Mounts": value["Mounts"]} if args[2] == "container" else
                      {"Id": value["Id"], "Name": name, "Labels": value["Labels"]})
            return done(json.dumps([shaped]))
        if args[0] == "inspect":
            return done("172.30.0.2")  # the AUTHORED stand-in's bridge address
        if args[0] == "run":
            return self._run(list(args))
        if args[1:2] == ("create",):
            kind, name = args[0], args[-1]
            labels = dict(args[i + 1].split("=", 1) for i, flag in enumerate(args) if flag == "--label")
            if kind == "volume" and name in self.objects["volume"]:
                if self.before_create is not None:
                    self.before_create(kind, name)
                return done(name)  # Docker re-uses a local volume of that name; its labels stay as they were
            self._create(kind, name, label=labels.pop(LABEL), labels=labels)
            return done(name if kind == "volume" else f"id-{name}")
        if args[0] in ("rm", "kill") or args[1:2] == ("rm",):
            if self.raise_on_rm is not None and args[0] != "kill":
                raise self.raise_on_rm
            kind = "container" if args[0] in ("rm", "kill") else args[0]
            if args[-1] in self.fail_rm:
                return done(code=1, stderr="Error response from daemon: removal failed")
            if args[-1] in self.ignore_rm:
                return done()
            name = self.find(kind, args[-1])
            if name is not None and args[0] != "kill":
                del self.objects[kind][name]
            return done(code=0 if name is not None else 1)
        if args[0] in ("ps", "network", "volume"):  # ps -a / network ls / volume ls --filter label=K=V
            if self.fail_list:
                return done(code=1, stderr="Error response from daemon: listing failed")
            kind = {"ps": "container", "network": "network", "volume": "volume"}[args[0]]
            wanted = args[args.index("--filter") + 1].removeprefix("label=").split("=", 1)
            names = [n for n, v in self.objects[kind].items() if v["Labels"].get(wanted[0]) == wanted[1]]
            return done("\n".join(names))
        raise AssertionError(f"unexpected docker call {args}")

    def _create(self, kind: str, name: str, *, label: str, sources: tuple[str, ...] = (),
                labels: dict[str, str] | None = None) -> str:
        if self.before_create is not None:
            self.before_create(kind, name)
        if name in self.objects[kind]:  # Docker: the name is already in use (a raced volume is re-used instead)
            if kind == "volume":
                return self.objects[kind][name]["Id"]
            raise subprocess.CalledProcessError(125, ["docker", kind, "create", name], "", "name in use")
        return self.add(kind, name, label=label, sources=sources, labels=labels)

    def _run(self, argv: list[str]) -> Any:
        name = argv[argv.index("--name") + 1]
        if self.fail_run is not None and name.startswith(self.fail_run):
            raise subprocess.CalledProcessError(125, ["docker", *argv], "", "synthetic failure /secret/path")
        mounts = {}
        for flag, value in zip(argv, argv[1:]):
            if flag == "--mount" and "type=bind" in value:
                parts = dict(item.split("=", 1) for item in value.split(",") if "=" in item)
                mounts[parts["dst"]] = parts["src"]
        identity = self._create("container", name, label=argv[argv.index("--label") + 1].split("=", 1)[1],
                                sources=tuple(mounts.values()))
        if "/provider/receipts" in mounts:
            Path(mounts["/provider/receipts"], "ready").write_text("{}")
        elif "/gateway/receipts" in mounts:
            Path(mounts["/gateway/receipts"], "ready").write_text("{}")
        else:
            Path(mounts["/relay/state"], "heartbeat.json").write_text(json.dumps({"started_at": 1e12 + next(self.beats)}))
        return done(identity)

    def labelled(self, run_id: str) -> dict[str, list[str]]:
        return {kind: sorted(n for n, v in self.objects[kind].items() if v["Labels"].get(LABEL) == run_id)
                for kind in KINDS}

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


def config(tmp_path: Path, key: Path, suffix: str = "", **changes: Any) -> dict[str, Any]:
    value = {"format": "edge-os.relay-operator-config/1", "operation_id": "hpr-op-unit", "kind": "AUTHORED",
             "release": dict(SETTINGS), "release_record": None, "ca_bundle": None,
             "image": {"reference": "edge-os-p05-hermes:unit", "id": IMAGE_ID},
             "run_root": str(tmp_path / f"run{suffix}"),
             "channel": {"name": "jobs", "path": str(tmp_path / f"jobs{suffix}")}, "provider_key_file": str(key),
             "shutdown_owner": "relay_operator"}
    value.update(changes)
    return value


def write(tmp_path: Path, value: dict[str, Any], name: str = "operator.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value))
    return path


def loaded_from(value: dict[str, Any]) -> relay_operator.OperatorConfig:
    return load_config(json.dumps(value).encode())


def started(tmp_path: Path, key: Path, suffix: str = "", **changes: Any) -> tuple[relay_operator.OperatorConfig, Path, str]:
    loaded = loaded_from(config(tmp_path, key, suffix, **changes))
    path, sha = relay_operator.start(loaded)
    return loaded, path, sha


def names(loaded: relay_operator.OperatorConfig) -> dict[str, str]:
    return loaded.supervisor().names


def owned_state(fake: FakeDocker, loaded: relay_operator.OperatorConfig) -> dict[str, list[str]]:
    return fake.labelled(loaded.target.run_id)


# --- admission before any effect ----------------------------------------------------------------------------------------

def test_check_is_the_default_command_and_makes_no_docker_call_and_no_write(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path)]) == 0
    assert "kind AUTHORED operation hpr-op-unit admitted" in capsys.readouterr().out
    assert fake.calls == [] and not (tmp_path / "run").exists() and not (tmp_path / "jobs").exists()


def test_the_cli_entry_point_runs_as_a_script(tmp_path: Path, key: Path) -> None:
    path = write(tmp_path, config(tmp_path, key))
    ran = subprocess.run([sys.executable, str(Path(relay_operator.__file__)), str(path)], capture_output=True,
                         text=True, timeout=60, env={**os.environ, "PATH": ""})  # no docker can be found or run
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.startswith("config ") and SENTINEL not in ran.stdout + ran.stderr


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


@pytest.mark.parametrize("where", ["exists", "inside_relay_folder", "is_run_root"])
def test_the_channel_folder_must_be_new_and_task_owned(tmp_path: Path, key: Path, fake: FakeDocker, where: str) -> None:
    path = {"exists": tmp_path / "shared", "inside_relay_folder": tmp_path / "run" / "relay" / "jobs",
            "is_run_root": tmp_path / "run"}[where]
    if where == "exists":
        path.mkdir()
    value = config(tmp_path, key, channel={"name": "jobs", "path": str(path)})
    assert main([str(write(tmp_path, value)), "start"]) == 2
    assert fake.effects() == [] and not (tmp_path / "run").exists()


def test_a_channel_folder_inside_the_run_root_is_created_by_the_operator(tmp_path: Path, key: Path,
                                                                          fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key, channel={"name": "jobs", "path": str(tmp_path / "run" / "jobs")})
    assert stat.S_IMODE((tmp_path / "run" / "jobs").stat().st_mode) == 0o700 and owned_state(fake, loaded)["container"]


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
    loaded, path, sha = started(tmp_path, key, **{k: value[k] for k in
                                                  ("kind", "release", "release_record", "ca_bundle")})
    assert owned_state(fake, loaded)["container"] == sorted([names(loaded)["gateway"], names(loaded)["relay"]])
    handoff = read_handoff(path, sha)
    assert handoff.kind == "ACTUAL" and handoff.release == loaded.release.settings()
    assert handoff.release_record == (Path(value["release_record"]["path"]), value["release_record"]["sha256"])
    assert handoff.ca_bundle_sha256 == value["ca_bundle"]["sha256"]


def test_stop_needs_neither_the_key_file_nor_a_still_approved_record(
        tmp_path: Path, key: Path, fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> None:
    value = actual_config(tmp_path, key)
    approve(monkeypatch, value)
    loaded, _, _ = started(tmp_path, key, **{k: value[k] for k in ("kind", "release", "release_record", "ca_bundle")})
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset())  # approval withdrawn
    key.chmod(0o600)
    key.unlink()  # key rotated away
    assert main([str(write(tmp_path, value)), "stop"]) == 0
    assert owned_state(fake, loaded) == {kind: [] for kind in KINDS}


# --- image identity and naming ------------------------------------------------------------------------------------------

def test_a_reference_that_does_not_name_the_configured_image_id_is_refused_before_any_effect(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    fake.image_id = OTHER_ID  # the tag was moved to another image
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path), "start"]) == 2
    assert fake.effects() == [] and not (tmp_path / "run").exists()


def test_every_container_is_launched_by_the_immutable_image_id_never_the_reference(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    started(tmp_path, key)
    runs = [call for call in fake.calls if call[0] == "run"]
    assert len(runs) == 3
    for argv in runs:
        assert IMAGE_ID in argv and "edge-os-p05-hermes:unit" not in argv


def test_names_carry_the_configuration_hash_so_a_reused_operation_id_gets_other_names(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    first = loaded_from(config(tmp_path, key, "-a"))
    second = loaded_from(config(tmp_path, key, "-b"))
    assert first.operation_id == second.operation_id
    assert first.supervisor().run_id == f"hpr-op-unit-{first.sha256[:12]}"
    assert set(names(first).values()).isdisjoint(names(second).values())
    assert first.target.names() == names(first)  # the operator's names are the supervisor's


# --- ownership: foreign, stale, competing and reused resources ----------------------------------------------------------

@pytest.mark.parametrize("role", ["relay", "gateway", "provider", "network", "volume"])
def test_an_existing_resource_under_the_operation_names_is_foreign_and_nothing_is_started_or_removed(
        tmp_path: Path, key: Path, fake: FakeDocker, role: str) -> None:
    loaded = loaded_from(config(tmp_path, key))
    kind = {"network": "network", "volume": "volume"}.get(role, "container")
    fake.add(kind, names(loaded)["egress" if kind != "container" else role], label=None)
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 2
    assert fake.effects() == [] and not (tmp_path / "run").exists()


def test_two_starts_of_one_configuration_have_one_winner_and_the_loser_touches_nothing(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    started(tmp_path, key)
    before, effects = json.dumps(fake.objects, sort_keys=True), len(fake.effects())
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 2
    assert json.dumps(fake.objects, sort_keys=True) == before and len(fake.effects()) == effects


def test_a_reused_operation_id_with_another_run_root_never_touches_the_newer_operation(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    old = write(tmp_path, config(tmp_path, key, "-a"), "old.json")
    assert main([str(old), "start"]) == 0 and main([str(old), "stop"]) == 0
    newer, _, _ = started(tmp_path, key, "-b")
    held = owned_state(fake, newer)
    assert main([str(old), "stop"]) == 0  # a stale second stop of the old operation
    assert main([str(old), "restart"]) == 2
    assert owned_state(fake, newer) == held and all(held.values())


def test_a_stale_failed_start_cannot_restart_or_stop_a_later_operation(tmp_path: Path, key: Path,
                                                                       fake: FakeDocker) -> None:
    old = write(tmp_path, config(tmp_path, key, "-a"), "old.json")
    fake.fail_run = "relay-gateway-"
    assert main([str(old), "start"]) == 1
    fake.fail_run = None
    newer, _, _ = started(tmp_path, key, "-b")
    held = owned_state(fake, newer)
    relay_id = fake.objects["container"][names(newer)["relay"]]["Id"]
    assert main([str(old), "restart"]) == 2
    assert main([str(old), "stop"]) == 0
    assert owned_state(fake, newer) == held and fake.objects["container"][names(newer)["relay"]]["Id"] == relay_id


def test_a_competing_object_created_under_our_name_during_start_is_never_removed(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    loaded = loaded_from(config(tmp_path, key))
    gateway = names(loaded)["gateway"]

    def compete(kind: str, name: str) -> None:  # after our name check, before our launch: even with a copied label
        if name == gateway and name not in fake.objects["container"]:
            fake.add("container", name, label=loaded.supervisor().run_id, sources=("/elsewhere/gateway-config.json",))

    fake.before_create = compete
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert capsys.readouterr().err == "failed: CalledProcessError\n"
    assert list(fake.objects["container"]) == [gateway] and fake.objects["network"] == fake.objects["volume"] == {}
    failed = json.loads((tmp_path / "run" / "start-failed.json").read_text())
    assert failed["error"] == "CalledProcessError" and failed["cleanup_error"] is None
    assert failed["cleanup"]["foreign"] == [gateway] and failed["cleanup"]["containers_left"] == [gateway]


@pytest.mark.parametrize("replaced", ["relay", "network", "volume"])
def test_a_resource_replaced_under_our_name_after_start_is_left_and_reported(
        tmp_path: Path, key: Path, fake: FakeDocker, replaced: str) -> None:
    loaded, _, _ = started(tmp_path, key)
    kind = "container" if replaced == "relay" else replaced
    name = names(loaded)["relay" if replaced == "relay" else "egress"]
    if kind == "network":
        for container in list(fake.objects["container"]):  # Docker refuses to remove a network in use
            del fake.objects["container"][container]
    del fake.objects[kind][name]
    fake.add(kind, name, label=loaded.supervisor().run_id if kind != "volume" else "someone-else")
    foreign_id = fake.objects[kind][name]["Id"]
    assert main([str(write(tmp_path, config(tmp_path, key))), "stop"]) == 1
    assert fake.objects[kind][name]["Id"] == foreign_id
    assert not (tmp_path / "run" / "stopped.json").exists()  # not a clean stop
    [record] = (tmp_path / "run").glob("stop-incomplete-*.json")
    assert json.loads(record.read_text())["left"]["foreign"] == [name]


@pytest.mark.parametrize("command", ["restart", "stop"])
def test_restart_and_stop_refuse_a_run_root_of_another_configuration(
        tmp_path: Path, key: Path, fake: FakeDocker, command: str) -> None:
    started(tmp_path, key)
    calls = len(fake.calls)
    other = write(tmp_path, config(tmp_path, key, release={**SETTINGS, "release_id": "local-relay-2"}), "other.json")
    assert main([str(other), command]) == 2
    assert len(fake.calls) == calls


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


def reread(tmp_path: Path, value: dict[str, Any]) -> relay_operator.OperatorHandoff:
    other = tmp_path / "other-handoff.json"
    other.unlink(missing_ok=True)
    other.write_bytes(json.dumps(value).encode())
    return read_handoff(other, hashlib.sha256(other.read_bytes()).hexdigest())


def test_read_handoff_refuses_other_bytes_and_other_shapes(tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    _, path, sha = started(tmp_path, key)
    with pytest.raises(OperatorRefused, match="hash"):
        read_handoff(path, "0" * 64)
    value = json.loads(path.read_text())
    endpoint = value["endpoint"]
    for changed in ({**value, "provider_key_file": "/x"}, {**value, "format": "other"},
                    {**value, "kind": "ACTUAL"}, {**value, "shutdown_owner": "application"},
                    {**value, "endpoint": {**endpoint, "extra": 1}},
                    {**value, "operation_id": 7}, {**value, "config_sha256": "abc"},
                    {**value, "image": {**value["image"], "id": "latest"}},
                    {**value, "image": {**value["image"], "reference": ""}},
                    {**value, "release": {**value["release"], "max_reply_bytes": 0}},
                    {**value, "release": {**value["release"], "extra": 1}},
                    {**value, "endpoint": {**endpoint, "channel_root": "../jobs"}},
                    {**value, "endpoint": {**endpoint, "heartbeat_max_age_seconds": "2"}},
                    {**value, "endpoint": {**endpoint, "heartbeat_max_age_seconds": True}},
                    {**value, "endpoint": {**endpoint, "heartbeat_max_age_seconds": 0}},
                    {**value, "endpoint": {**endpoint, "grants": "relative"}},
                    {**value, "started_at": None}, {**value, "started_at": True},
                    {**value, "evidence_dir": 3}):
        with pytest.raises(OperatorRefused):
            reread(tmp_path, changed)
    assert reread(tmp_path, value).endpoint == read_handoff(path, sha).endpoint  # the unchanged copy reads


def test_the_authored_scripts_folder_follows_from_the_handoff_state_folder(tmp_path: Path, key: Path,
                                                                           fake: FakeDocker) -> None:
    """AUTHORED test scaffolding only: the stand-in's scripts sit beside the handoff's relay `state` folder."""
    loaded, path, sha = started(tmp_path, key)
    assert read_handoff(path, sha).endpoint.state.parent / "provider" / "scripts" == loaded.supervisor().path(
        "provider", "scripts")


# --- failure, restart and stop ------------------------------------------------------------------------------------------

def test_a_failed_start_removes_exactly_what_it_started_and_writes_no_handoff(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    fake.fail_run = "relay-gateway-"  # the stand-in is running, the gateway launch fails
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert capsys.readouterr().err == "failed: CalledProcessError\n"  # no argument, mount path or stderr text
    assert fake.objects == {kind: {} for kind in KINDS}
    failed = json.loads((tmp_path / "run" / "start-failed.json").read_text())
    assert failed == {"error": "CalledProcessError", "cleanup_error": None,
                      "cleanup": {"containers_left": [], "networks_left": [], "volumes_left": [], "foreign": [], "unknown": [], "errors": []}}
    assert not (tmp_path / "run" / "handoff.json").exists()


def test_a_failed_handoff_write_after_start_is_cleaned_up_like_a_failed_start(
        tmp_path: Path, key: Path, fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> None:
    real = relay_operator._write_once

    def full_disk(path: Path, value: dict[str, Any], mode: int) -> str:
        if path.name == "handoff.json":
            raise OSError(28, "No space left on device")
        return real(path, value, mode)

    monkeypatch.setattr(relay_operator, "_write_once", full_disk)
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert fake.objects == {kind: {} for kind in KINDS}
    assert json.loads((tmp_path / "run" / "start-failed.json").read_text())["error"] == "OSError"
    assert not (tmp_path / "run" / "handoff.json").exists()


def test_a_removal_timeout_in_cleanup_keeps_the_start_error_and_records_what_is_left(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    fake.fail_run = "relay-gateway-"
    fake.raise_on_rm = subprocess.TimeoutExpired(["docker", "rm"], 60)
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert capsys.readouterr().err == "failed: CalledProcessError\n"
    failed = json.loads((tmp_path / "run" / "start-failed.json").read_text())
    assert (failed["error"], failed["cleanup_error"]) == ("CalledProcessError", None)
    assert failed["cleanup"]["errors"] and failed["cleanup"]["containers_left"]  # not reported as clean
    assert fake.objects["container"]  # nothing claimed removed that was not


def test_an_exception_inside_cleanup_keeps_the_start_error_and_records_both(
        tmp_path: Path, key: Path, fake: FakeDocker, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    fake.fail_run = "relay-gateway-"

    def broken(*args: Any) -> dict[str, Any]:
        raise RuntimeError("cleanup broke")

    monkeypatch.setattr(relay_operator, "_remove_owned", broken)
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert capsys.readouterr().err == "failed: CalledProcessError\n"
    failed = json.loads((tmp_path / "run" / "start-failed.json").read_text())
    assert failed == {"error": "CalledProcessError", "cleanup_error": "RuntimeError", "cleanup": None}


@pytest.mark.parametrize("state", ["start_failed", "stopped", "no_handoff", "gateway_gone", "volume_gone",
                                   "foreign_relay"])
def test_restart_is_refused_unless_the_operation_is_started_complete_and_owned(
        tmp_path: Path, key: Path, fake: FakeDocker, state: str) -> None:
    path = write(tmp_path, config(tmp_path, key))
    if state == "start_failed":
        fake.fail_run = "relay-gateway-"
        assert main([str(path), "start"]) == 1
        fake.fail_run = None
    else:
        assert main([str(path), "start"]) == 0
    loaded = load_config(path.read_bytes())
    if state == "stopped":
        assert main([str(path), "stop"]) == 0
    elif state == "no_handoff":
        (tmp_path / "run" / "handoff.json").chmod(0o644)
        (tmp_path / "run" / "handoff.json").unlink()
    elif state == "gateway_gone":
        del fake.objects["container"][names(loaded)["gateway"]]
    elif state == "volume_gone":
        del fake.objects["volume"][names(loaded)["egress"]]
    elif state == "foreign_relay":
        del fake.objects["container"][names(loaded)["relay"]]
        fake.add("container", names(loaded)["relay"], label="someone-else")
    calls = len(fake.effects())
    assert main([str(path), "restart"]) == 2
    assert len(fake.effects()) == calls  # nothing killed, removed or started


def test_restart_keeps_every_relay_record_so_a_started_attempt_is_never_sent_again(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key)
    attempt = loaded.run_root / "relay" / "state" / "attempt-1"
    attempt.mkdir()
    (attempt / "started.json").write_text('{"grant_id": "g-1"}')  # started, no finished: recovery C marks it lost
    before = sorted(p.relative_to(loaded.run_root) for p in loaded.run_root.rglob("*") if p.name != "heartbeat.json")
    old_relay = fake.objects["container"][names(loaded)["relay"]]["Id"]
    fake.calls.clear()
    relay_operator.restart(loaded)
    effects = fake.effects()
    assert [call[:1] for call in effects] == [["kill"], ["rm"], ["run"]] and effects[0][-1] == old_relay
    assert IMAGE_ID in effects[-1]
    assert fake.objects["container"][names(loaded)["relay"]]["Id"] != old_relay
    after = sorted(p.relative_to(loaded.run_root) for p in loaded.run_root.rglob("*") if p.name != "heartbeat.json")
    assert after == before and (attempt / "started.json").read_text() == '{"grant_id": "g-1"}'


def test_stop_removes_exactly_the_operation_resources_by_id_records_once_and_a_stopped_operation_is_not_restarted(
        tmp_path: Path, key: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]) -> None:
    loaded, _, _ = started(tmp_path, key)
    bystander = fake.add("container", "someone-elses-container", label=None)
    ours = names(loaded)
    expected = {fake.objects["container"][ours[role]]["Id"] for role in ("relay", "gateway", "provider")}
    expected |= {fake.objects["network"][ours["egress"]]["Id"], ours["egress"]}  # a volume has only its name
    path = write(tmp_path, config(tmp_path, key))
    fake.calls.clear()
    assert main([str(path), "stop"]) == 0
    assert {call[-1] for call in fake.effects()} == expected
    assert list(fake.objects["container"]) == ["someone-elses-container"]
    assert fake.objects["container"]["someone-elses-container"]["Id"] == bystander
    stopped = (loaded.run_root / "stopped.json").read_bytes()
    assert main([str(path), "stop"]) == 0  # stopping again checks again and keeps the first record
    assert (loaded.run_root / "stopped.json").read_bytes() == stopped
    capsys.readouterr()
    calls = len(fake.effects())
    assert main([str(path), "restart"]) == 2 and len(fake.effects()) == calls
    assert (loaded.run_root / "handoff.json").exists()  # evidence stays; the operator removes no files


# --- Docker (needs a capacity grant; select with -k test_docker_) ------------------------------------------------------

IMAGE_RECEIPT = "HERMES_OPERATOR_IMAGE_RECEIPT"  # a kept `source_identity.json` of an existing pinned Hermes image


@pytest.fixture(scope="module")
def pinned_hermes_image() -> str:
    """Overrides the session builder for this module: reuse an existing pinned image by its immutable id, named by a
    kept build receipt. Nothing is built, pulled or removed here; the image stays its builder's."""
    from docker_turn_runner import PINNED_HERMES, PYTHON_IMAGE

    receipt = os.environ.get(IMAGE_RECEIPT)
    if not receipt:
        pytest.fail(f"{IMAGE_RECEIPT} must name the source_identity.json of an existing pinned image; this test builds "
                    "no image")
    value = json.loads(Path(receipt).read_text())
    assert (value["commit"], value["python_image"]) == (PINNED_HERMES, PYTHON_IMAGE), value
    seen = relay_supervisor.docker("image", "inspect", value["image_id"], "--format", "{{.Id}}", check=False)
    assert seen.returncode == 0 and seen.stdout.strip() == value["image_id"], "the receipted image is not present"
    return value["image_id"]


def test_docker_the_cli_runs_the_e1_relay_from_the_handoff_restarts_and_stops_with_nothing_left(
        pinned_hermes_image: str, evidence_root: Path, synthetic_key: Path, run_id: str) -> None:
    """The real CLI starts an owned AUTHORED E1 operation. One application-shaped turn takes its endpoint, evidence
    folder and image id from the handoff only; the AUTHORED stand-in's scripts folder is test scaffolding beside the
    handoff's `state` folder. A CLI restart keeps the finished attempt's records and sends nothing new. The CLI stops
    the operation and nothing labelled is left. Synthetic key and stand-in only."""
    from edge_os_api.research.hermes_interpreter import Interpreted
    from leak_scan import find_leaks
    from relay_harness import EXACT_CHARGE, RELEASE, Rig, case, counts, provider_receipts, relay_record

    root = evidence_root / "operator"
    root.mkdir()
    image_id = relay_supervisor.docker("image", "inspect", pinned_hermes_image, "--format", "{{.Id}}").stdout.strip()
    value = config(root, synthetic_key, operation_id=f"op-{run_id}"[:40], release=RELEASE.settings(),
                   image={"reference": pinned_hermes_image, "id": image_id})
    path = write(root, value)

    def cli(command: str) -> subprocess.CompletedProcess[str]:
        ran = subprocess.run([sys.executable, str(Path(relay_operator.__file__)), str(path), command],
                             capture_output=True, text=True, timeout=600)
        (root / f"cli-{command}.txt").write_text(f"{ran.returncode}\n{ran.stdout}{ran.stderr}")
        return ran

    started_cli = cli("start")
    try:
        assert started_cli.returncode == 0, started_cli.stderr
        _, handoff_path, _, sha = started_cli.stdout.split()
        handoff = read_handoff(Path(handoff_path), sha)
        relay_folder = handoff.endpoint.state.parent

        class FromHandoff:  # the application's view: the handoff endpoint; run id is the application's own
            run_id = handoff.operation_id

            @staticmethod
            def path(*parts: str) -> Path:
                return relay_folder.joinpath(*parts)

            @staticmethod
            def endpoint(name: str) -> Any:
                assert name == handoff.endpoint.channel_root
                return handoff.endpoint

        heartbeat = json.loads((handoff.endpoint.state / "heartbeat.json").read_text())
        assert handoff.evidence_dir == root / "jobs" and heartbeat["release"] == handoff.release
        rig = Rig(FromHandoff(), handoff.image_id, root, "op-valid", case())
        assert isinstance(rig.run_case(), Interpreted)
        assert counts(FromHandoff, "op-valid-1") == (1, 1)
        assert rig.spend.committed_usd() == EXACT_CHARGE
        records = {name: relay_record(FromHandoff, "op-valid-1", name) for name in ("started", "finished", "closed")}

        restarted = cli("restart")
        assert restarted.returncode == 0, restarted.stderr
        after = json.loads((handoff.endpoint.state / "heartbeat.json").read_text())
        assert after["started_at"] > heartbeat["started_at"]
        assert {name: relay_record(FromHandoff, "op-valid-1", name) for name in records} == records
        assert len(provider_receipts(FromHandoff, "op-valid-1")) == 1  # nothing sent again
        assert SENTINEL.encode() not in Path(handoff_path).read_bytes()
        assert find_leaks(root / "jobs", SENTINEL) == []
    finally:
        stopped_cli = cli("stop")
    assert stopped_cli.returncode == 0, stopped_cli.stdout + stopped_cli.stderr
    assert json.loads((root / "run" / "stopped.json").read_text())["left"] == {"containers_left": [], "networks_left": [], "volumes_left": [], "foreign": [], "unknown": [], "errors": []}


# --- round 3: unknown Docker state, the volume race, the claim race and the owner record --------------------------------

@pytest.mark.parametrize("fault", ["daemon_down", "malformed_relay", "list_fails", "relay_removal_fails"])
def test_a_stop_that_cannot_establish_a_clean_state_records_no_clean_stop(
        tmp_path: Path, key: Path, fake: FakeDocker, fault: str) -> None:
    loaded, _, _ = started(tmp_path, key)
    relay = names(loaded)["relay"]
    if fault == "daemon_down":
        fake.daemon_down = True
    elif fault == "malformed_relay":
        fake.malformed.add(relay)
    elif fault == "list_fails":
        fake.fail_list = True
    else:
        fake.fail_rm.add(fake.objects["container"][relay]["Id"])
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path), "stop"]) == 1
    assert not (loaded.run_root / "stopped.json").exists()
    [record] = loaded.run_root.glob("stop-incomplete-*.json")
    left = json.loads(record.read_text())["left"]
    assert left["unknown"] or left["errors"] or left["containers_left"], left
    if fault in ("daemon_down", "malformed_relay", "relay_removal_fails"):
        assert relay in fake.objects["container"]  # nothing unknown is treated as gone
    assert main([str(path), "restart"]) == 2  # a stop was asked for: no restart after it
    fake.daemon_down, fake.fail_list = False, False
    fake.malformed.clear()
    fake.fail_rm.clear()
    assert main([str(path), "stop"]) == 0  # the first genuine clean stop is the one recorded
    assert json.loads((loaded.run_root / "stopped.json").read_text())["left"] == {"containers_left": [], "networks_left": [], "volumes_left": [], "foreign": [], "unknown": [], "errors": []}


def test_an_unreadable_name_before_start_refuses_the_start(tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded = loaded_from(config(tmp_path, key))
    fake.malformed.add(names(loaded)["gateway"])
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 2
    assert fake.effects() == [] and not (tmp_path / "run").exists()


def test_the_operator_claims_the_volume_with_the_supervisor_options_and_its_own_claim_label(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key)
    creates = [call for call in fake.calls if call[:2] == ["volume", "create"]]
    assert len(creates) == 2  # the operator's claim, then the supervisor's own create re-uses it
    claim, supervisor_create = creates
    nonce = json.loads((loaded.run_root / "owner.json").read_text())["volume_claim"]
    claim_label = f"{relay_operator.VOLUME_CLAIM_LABEL}={nonce}"
    i = claim.index(claim_label)
    assert len(nonce) == 32 and claim[i - 1] == "--label"
    assert claim[:i - 1] + claim[i + 1:] == supervisor_create  # the same options, names and run label
    assert fake.objects["volume"][names(loaded)["egress"]]["Labels"][relay_operator.VOLUME_CLAIM_LABEL] == nonce


def test_a_volume_raced_in_before_the_claim_is_refused_before_any_container_uses_it(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded = loaded_from(config(tmp_path, key))
    egress = names(loaded)["egress"]

    def race(kind: str, name: str) -> None:  # after the name check, before our create: a copied label, no claim
        if kind == "volume" and name == egress and name not in fake.objects["volume"]:
            fake.add("volume", name, label=loaded.target.run_id)

    fake.before_create = race
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    foreign = fake.objects["volume"][egress]["Id"]
    assert [call for call in fake.calls if call[0] == "run"] == []  # no container mounted it
    assert fake.objects["volume"][egress]["Id"] == foreign and fake.objects["container"] == {}
    failed = json.loads((tmp_path / "run" / "start-failed.json").read_text())
    assert failed["cleanup"]["foreign"] == [egress] and not (tmp_path / "run" / "handoff.json").exists()


def test_a_volume_swapped_after_the_claim_is_found_before_any_handoff_and_kept(
        tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    """The post-start check finds the swap and refuses the handoff; it does not undo a mount that already happened."""
    loaded = loaded_from(config(tmp_path, key))
    egress, gateway = names(loaded)["egress"], names(loaded)["gateway"]

    def swap(kind: str, name: str) -> None:
        if kind == "container" and name == gateway:
            del fake.objects["volume"][egress]
            fake.add("volume", egress, label=loaded.target.run_id)

    fake.before_create = swap
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert not (tmp_path / "run" / "handoff.json").exists()
    assert egress in fake.objects["volume"] and fake.objects["container"] == {} and fake.objects["network"] == {}
    assert json.loads((tmp_path / "run" / "start-failed.json").read_text())["cleanup"]["foreign"] == [egress]


def test_failed_start_cleanup_uses_the_recorded_network_id(tmp_path: Path, key: Path, fake: FakeDocker,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = loaded_from(config(tmp_path, key))
    egress = names(loaded)["egress"]
    real = relay_operator._write_once

    def swap_then_fail(path: Path, value: dict[str, Any], mode: int) -> str:
        if path.name == "handoff.json":  # the network was recorded; now another one sits under its name
            del fake.objects["network"][egress]
            fake.add("network", egress, label=loaded.target.run_id)
            raise OSError(28, "No space left on device")
        return real(path, value, mode)

    monkeypatch.setattr(relay_operator, "_write_once", swap_then_fail)
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert egress in fake.objects["network"]
    assert json.loads((tmp_path / "run" / "start-failed.json").read_text())["cleanup"]["foreign"] == [egress]


def test_a_failed_owner_record_write_releases_the_empty_claim(tmp_path: Path, key: Path, fake: FakeDocker,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    real = relay_operator._write_once

    def fail_owner(path: Path, value: dict[str, Any], mode: int) -> str:
        if path.name == "owner.json":
            raise OSError(28, "No space left on device")
        return real(path, value, mode)

    monkeypatch.setattr(relay_operator, "_write_once", fail_owner)
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 1
    assert not (tmp_path / "run").exists() and fake.effects() == []


def test_a_start_that_loses_the_run_root_claim_touches_nothing(tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded = loaded_from(config(tmp_path, key))
    relay = names(loaded)["relay"]

    def other_start_claims(name: str) -> None:  # another start claims the run root between our check and our mkdir
        if name == relay and not loaded.run_root.exists():
            loaded.run_root.mkdir()
            (loaded.run_root / "theirs").write_text("kept")

    fake.on_inspect = other_start_claims
    assert main([str(write(tmp_path, config(tmp_path, key))), "start"]) == 2
    assert sorted(p.name for p in loaded.run_root.iterdir()) == ["theirs"] and fake.effects() == []


def test_an_inspect_error_is_unknown_not_absent_even_when_listing_works(tmp_path: Path, key: Path,
                                                                        fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key)
    relay = names(loaded)["relay"]
    fake.inspect_error.add(relay)
    assert main([str(write(tmp_path, config(tmp_path, key))), "stop"]) == 1
    [record] = loaded.run_root.glob("stop-incomplete-*.json")
    assert relay in json.loads(record.read_text())["left"]["unknown"] and relay in fake.objects["container"]


def test_a_removal_that_answers_success_but_leaves_the_object_is_unknown(tmp_path: Path, key: Path,
                                                                         fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key)
    relay = names(loaded)["relay"]
    fake.ignore_rm.add(fake.objects["container"][relay]["Id"])
    assert main([str(write(tmp_path, config(tmp_path, key))), "stop"]) == 1
    [record] = loaded.run_root.glob("stop-incomplete-*.json")
    assert relay in json.loads(record.read_text())["left"]["unknown"] and not (loaded.run_root / "stopped.json").exists()


def test_no_restart_after_a_stop_that_removed_nothing(tmp_path: Path, key: Path, fake: FakeDocker) -> None:
    loaded, _, _ = started(tmp_path, key)
    fake.fail_rm |= {fake.objects[kind][name]["Id"] for kind in ("container", "network")
                     for name in fake.objects[kind]} | {names(loaded)["egress"]}
    path = write(tmp_path, config(tmp_path, key))
    assert main([str(path), "stop"]) == 1 and all(fake.labelled(loaded.target.run_id).values())
    fake.fail_rm.clear()
    effects = len(fake.effects())
    assert main([str(path), "restart"]) == 2 and len(fake.effects()) == effects


# --- absence wording ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "stderr"), [
    *DOCKER_29_ABSENT.items(), *DOCKER_29_WRAPPED.items(),
    *((kind, form) for kind in KINDS for form in ("Error: No such object: {name}", "Error: No such {kind}: {name}",
                                                  "Error response from daemon: No such {kind}: {name}"))])
def test_each_kind_of_docker_absence_answer_for_the_asked_name_is_absent(
        monkeypatch: pytest.MonkeyPatch, kind: str, stderr: str) -> None:
    name = "relay-egress-op-unit-0123456789ab"
    answer = stderr.replace("{name}", name).replace("{kind}", kind)  # the JSON braces are not format fields
    monkeypatch.setattr(relay_supervisor, "docker", lambda *args, **_: done("[]", 1, answer + "\n"))
    assert relay_operator._inspect(kind, name) is None


@pytest.mark.parametrize(("kind", "stdout", "stderr"), [
    ("network", "[]", "Error response from daemon: network relay-egress-other not found"),  # another name
    ("network", "[]", "Error response from daemon: network relay-egress-op-unit-0123456789ab-2 not found"),
    ("network", "[]", "Error response from daemon: not found"),
    ("network", "[]", "Error response from daemon: network relay-egress-op-unit-0123456789ab not found: i/o timeout"),
    ("network", "[]", "Error response from daemon: network relay-egress-op-unit-0123456789ab not found\nother error"),
    ("volume", "[]", "Error response from daemon: network relay-egress-op-unit-0123456789ab not found"),  # wrong kind
    ("container", "[]", "Error response from daemon: get relay-egress-op-unit-0123456789ab: no such volume"),
    ("network", "[]", "permission denied while trying to connect to the Docker daemon socket"),
    ("network", "[]", "Error response from daemon: context deadline exceeded"),
    ("network", "[]", ""),
    ("network", "[{}]", "Error response from daemon: network relay-egress-op-unit-0123456789ab not found"),
    # the daemon's JSON body: only one strict object with exactly one string `message` naming this kind and name
    ("container", "[]", 'Error response from daemon: {"message":"No such container: relay-egress-op-unit-0123456789ab-2"}'),
    ("container", "[]", 'Error response from daemon: {"message":"get relay-egress-op-unit-0123456789ab: no such volume"}'),
    ("network", "[]", 'Error response from daemon: {"message":"network relay-egress-op-unit-0123456789ab not found",'
                      '"code":404}'),
    ("network", "[]", 'Error response from daemon: {"message":"network relay-egress-op-unit-0123456789ab not found",'
                      '"message":"network relay-egress-op-unit-0123456789ab not found"}'),
    ("network", "[]", 'Error response from daemon: {"message":404}'),
    ("network", "[]", 'Error response from daemon: {"message":NaN}'),
    ("network", "[]", 'Error response from daemon: {"message":"network relay-egress-op-unit-0123456789ab not found"'),
    ("network", "[]", 'Error response from daemon: ["network relay-egress-op-unit-0123456789ab not found"]'),
    ("network", "[]", 'Error: {"message":"network relay-egress-op-unit-0123456789ab not found"}'),
    ("network", "[]", 'Error response from daemon: {"message":"network relay-egress-op-unit-0123456789ab not found"}'
                      '\nError response from daemon: permission denied'),
    ("network", "[{}]", 'Error response from daemon: {"message":"network relay-egress-op-unit-0123456789ab not found"}'),
    ("network", "[]", 'Error response from daemon: {"message":"permission denied"}'),
])
def test_an_absence_answer_for_another_name_kind_or_with_any_other_error_is_unknown(
        monkeypatch: pytest.MonkeyPatch, kind: str, stdout: str, stderr: str) -> None:
    monkeypatch.setattr(relay_supervisor, "docker", lambda *args, **_: done(stdout, 1, stderr))
    assert relay_operator._inspect(kind, "relay-egress-op-unit-0123456789ab") is False


@pytest.mark.parametrize("wording", ["docker-29.4.0", "docker-29.4.0-json", "no-such-object"])
def test_start_and_a_clean_stop_work_with_either_absence_wording(tmp_path: Path, key: Path, fake: FakeDocker,
                                                                  wording: str) -> None:
    fake.absent_wording = wording
    loaded, _, _ = started(tmp_path, key)
    assert main([str(write(tmp_path, config(tmp_path, key))), "stop"]) == 0
    assert (loaded.run_root / "stopped.json").exists() and not any(fake.labelled(loaded.target.run_id).values())
