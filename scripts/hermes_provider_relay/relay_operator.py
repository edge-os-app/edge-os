"""One bounded operator entry for the accepted relay: start, restart and stop `RelaySupervisor` from one configuration.

    python relay_operator.py CONFIG [check|start|restart|stop]     (run with the API's Python; `check` is the default)

The configuration is one immutable strict JSON file (format `edge-os.relay-operator-config/1`). It names the release
(AUTHORED settings, or an ACTUAL release record by path and SHA256 with its CA bundle), the pinned Hermes image by
reference and Docker id, the task-owned run root and operation id, the one channel and the host-held provider key file.
The topology is always the accepted E1 one (`online=True`, CONTRACT A6). Every refusal happens before any effect:

- `check` reads the configuration, the release record and the CA bundle and stats the key file. No Docker, no write.
- `start` also requires a run root that does not exist yet, the image id Docker reports for the reference and no
  container, network or volume under this operation's names. Only then does it create the run root (0700), record its
  owner, start the supervisor and write `handoff.json` once (0444). A failed start removes exactly what it started.
- `restart` restarts the relay of a started operation; the relay's own recovery marks a started attempt
  `unknown_restart` and never sends it again. The operator sends nothing itself.
- `stop` removes exactly this operation's containers, network and volume and records `stopped.json` once.

ACTUAL is accepted only through `relay_admission.load_actual_release` with its default registry, which is empty: every
ACTUAL configuration is refused. The operator never reads the provider key; it only checks the file is outside the
repository and readable by its owner only. No key, key path or environment value is written to the handoff or printed.
`read_handoff` is the application's read-only view of the handoff (format `edge-os.relay-operator-handoff/1`).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for folder in (REPO / "apps" / "api" / "src", HERE.parent / "hermes_job_support", HERE.parent / "hermes_interpretation",
               HERE):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import relay_supervisor  # noqa: E402
from relay_admission import ActualRelease, RelayRelease, load_actual_release  # noqa: E402
from relay_supervisor import RelaySupervisor  # noqa: E402
from relay_turn_runner import RelayEndpoint  # noqa: E402

__all__ = ["OperatorConfig", "OperatorHandoff", "OperatorRefused", "load_config", "main", "read_handoff", "restart",
           "start", "stop"]

CONFIG_FORMAT = "edge-os.relay-operator-config/1"
HANDOFF_FORMAT = "edge-os.relay-operator-handoff/1"
SHUTDOWN_OWNER = "relay_operator"  # the only actor that stops, restarts or removes the relay; the application never does
CONFIG_FIELDS = frozenset({"format", "operation_id", "kind", "release", "release_record", "ca_bundle", "image",
                           "run_root", "channel", "provider_key_file", "shutdown_owner"})
HANDOFF_FIELDS = frozenset({"format", "operation_id", "config_sha256", "kind", "release", "release_record",
                            "ca_bundle_sha256", "image", "endpoint", "evidence_dir", "shutdown_owner", "started_at"})
ENDPOINT_FIELDS = ("grants", "revocations", "state", "admission_key_file", "channel_root", "heartbeat_max_age_seconds")
OPERATION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")  # becomes Docker names: relay-<id>, relay-gateway-<id>, ...
CHANNEL_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_FILE_BYTES = 1024 * 1024


class OperatorRefused(ValueError):
    """The configuration or the host state does not allow this command. Nothing was started, changed or removed."""


@dataclass(frozen=True)
class OperatorConfig:
    sha256: str  # of the configuration bytes
    operation_id: str
    release: RelayRelease
    actual: ActualRelease | None
    release_record: Path | None
    ca_bundle: Path | None
    image_reference: str
    image_id: str
    run_root: Path
    channel_name: str
    channel_path: Path
    provider_key_file: Path

    def supervisor(self) -> RelaySupervisor:
        """Construction does nothing (accepted `RelaySupervisor`); the relay lives under `<run root>/relay`. Every container
        is launched by the immutable image id, never by the reference, so a moved tag cannot change what runs."""
        return RelaySupervisor(self.run_root / "relay", self.release, self.image_id, self.operation_id,
                               self.provider_key_file, {self.channel_name: self.channel_path}, online=True,
                               actual=self.actual, release_record=self.release_record, ca_bundle_file=self.ca_bundle)


@dataclass(frozen=True)
class OperatorHandoff:
    """What the application may use from a started operation. It carries no key and no key path."""

    sha256: str
    operation_id: str
    config_sha256: str
    kind: str
    release: dict[str, Any]  # `RelayRelease.settings()`, the same shape the relay's heartbeat carries
    release_record: tuple[Path, str] | None  # ACTUAL: the record the application loads itself with `load_actual_release`
    ca_bundle_sha256: str | None
    image_reference: str
    image_id: str  # give this, not the reference, as `build_relay_job(image=...)`: the job runs the relay's exact image
    endpoint: RelayEndpoint
    evidence_dir: Path
    started_at: float


def _strict_json(raw: bytes, what: str) -> dict[str, Any]:
    def no_repeats(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key is repeated")
        return dict(pairs)

    def no_constant(name: str) -> Any:
        raise ValueError(f"{name} is not allowed")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_repeats, parse_constant=no_constant)
    except (UnicodeDecodeError, RecursionError, ValueError) as error:
        raise OperatorRefused(f"the {what} is not strict JSON") from error
    if not isinstance(value, dict):
        raise OperatorRefused(f"the {what} must be one JSON object")
    return value


def _read_file(path: Path, what: str) -> bytes:
    """A regular file, not a link, of bounded size."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise OperatorRefused(f"the {what} cannot be opened") from error
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OperatorRefused(f"the {what} must be a regular file")
        data = os.read(fd, MAX_FILE_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_FILE_BYTES:
        raise OperatorRefused(f"the {what} is too large")
    return data


def _absolute(value: Any, what: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        raise OperatorRefused(f"{what} must be an absolute path")
    return Path(value)


def _named_file(value: Any, what: str) -> tuple[Path, str]:
    if (not isinstance(value, dict) or set(value) != {"path", "sha256"} or not isinstance(value["sha256"], str)
            or not SHA256.fullmatch(value["sha256"])):
        raise OperatorRefused(f"{what} must be {{path, sha256}} with a lower-case SHA256")
    return _absolute(value["path"], f"{what} path"), value["sha256"]


def _key_file(value: Any) -> Path:
    """Checked, never read: outside the repository, a regular file (no link) readable by its owner only."""
    path = _absolute(value, "provider_key_file")
    try:
        seen = path.lstat()
    except OSError as error:
        raise OperatorRefused("the provider key file does not exist") from error
    if not stat.S_ISREG(seen.st_mode):
        raise OperatorRefused("the provider key file must be a regular file, not a link")
    if stat.S_IMODE(seen.st_mode) & 0o077:
        raise OperatorRefused("the provider key file must be readable by its owner only")
    if path.resolve().is_relative_to(REPO):
        raise OperatorRefused("the provider key file must be outside the repository")
    return path


def load_config(raw: bytes) -> OperatorConfig:
    """The validated configuration in `raw`, or OperatorRefused. Reads the named record and CA bundle; no other effect."""
    value = _strict_json(raw, "operator configuration")
    if set(value) != CONFIG_FIELDS:
        raise OperatorRefused("the operator configuration must have exactly the frozen fields")
    if value["format"] != CONFIG_FORMAT:
        raise OperatorRefused(f"the configuration format must be {CONFIG_FORMAT}")
    if value["shutdown_owner"] != SHUTDOWN_OWNER:
        raise OperatorRefused(f"shutdown_owner must be {SHUTDOWN_OWNER}")
    operation_id = value["operation_id"]
    if not isinstance(operation_id, str) or not OPERATION_ID.fullmatch(operation_id):
        raise OperatorRefused("operation_id must be 1-40 lower-case letters, digits or -")
    image = value["image"]
    if (not isinstance(image, dict) or set(image) != {"reference", "id"} or not isinstance(image["reference"], str)
            or not 0 < len(image["reference"]) <= 200 or any(c.isspace() for c in image["reference"])
            or not isinstance(image["id"], str) or not IMAGE_ID.fullmatch(image["id"])):
        raise OperatorRefused("image must be {reference, id} with a Docker sha256 id")
    channel = value["channel"]
    if (not isinstance(channel, dict) or set(channel) != {"name", "path"} or not isinstance(channel["name"], str)
            or not CHANNEL_NAME.fullmatch(channel["name"])):
        raise OperatorRefused("channel must be {name, path} with a short lower-case name")
    run_root = _absolute(value["run_root"], "run_root")
    channel_path = _absolute(channel["path"], "channel path")
    key = _key_file(value["provider_key_file"])
    actual = record = ca = None
    if value["kind"] == "AUTHORED":
        if value["release_record"] is not None or value["ca_bundle"] is not None or not isinstance(value["release"], dict):
            raise OperatorRefused("an AUTHORED configuration has release settings and no record or CA bundle")
        try:
            release = RelayRelease.from_settings(value["release"])
        except (KeyError, TypeError, ValueError) as error:
            raise OperatorRefused("the AUTHORED release settings are not a valid release") from error
        if set(value["release"]) != set(release.settings()) or release.kind != "AUTHORED":
            raise OperatorRefused("the AUTHORED release settings are not a valid release")
    elif value["kind"] == "ACTUAL":
        if value["release"] is not None:
            raise OperatorRefused("an ACTUAL release comes only from its approved record, never from settings")
        record, record_sha = _named_file(value["release_record"], "release_record")
        ca, ca_sha = _named_file(value["ca_bundle"], "ca_bundle")
        try:  # the default registry only: no caller, file or setting can approve its own record
            actual = load_actual_release(_read_file(record, "release record"), record_sha)
        except ValueError as error:
            raise OperatorRefused(f"the ACTUAL release is refused: {error}") from error
        if ca_sha != actual.ca_bundle_sha256:
            raise OperatorRefused("the CA bundle hash is not the release record's")
        if not hmac.compare_digest(hashlib.sha256(_read_file(ca, "CA bundle")).hexdigest(), ca_sha):
            raise OperatorRefused("the CA bundle file does not have the named hash")
        release = actual.release
    else:
        raise OperatorRefused("kind must be AUTHORED or ACTUAL")
    return OperatorConfig(hashlib.sha256(raw).hexdigest(), operation_id, release, actual, record, ca, image["reference"],
                          image["id"], run_root, channel["name"], channel_path, key)


# --- effects -----------------------------------------------------------------------------------------------------------

def _write_once(path: Path, value: dict[str, Any], mode: int) -> str:
    """Create `path` exclusively with `value`; return its SHA256. An existing file is never replaced."""
    data = (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.fchmod(fd, mode)
    finally:
        os.close(fd)
    return hashlib.sha256(data).hexdigest()


def _check_image(config: OperatorConfig) -> None:
    """The reference must name exactly the configured image now; the launches then use the id itself."""
    seen = relay_supervisor.docker("image", "inspect", config.image_reference, "--format", "{{.Id}}", check=False)
    if seen.returncode != 0 or seen.stdout.strip() != config.image_id:
        raise OperatorRefused("the image reference does not have the configured Docker id")


def _check_names_free(supervisor: RelaySupervisor) -> None:
    """Nothing under this operation's names may exist before start: stop() removes by these names."""
    names = supervisor.names
    for kind, name in [("container", names[role]) for role in ("relay", "gateway", "provider")] + [
            ("network", names["egress"]), ("volume", names["egress"])]:
        if relay_supervisor.docker("inspect", "--type", kind, name, check=False).returncode == 0:
            raise OperatorRefused(f"a {kind} named {name} already exists; this operation did not create it")


def _check_owned(config: OperatorConfig) -> None:
    """Restart and stop act only on a run root this exact configuration started."""
    try:
        owner = _strict_json(_read_file(config.run_root / "owner.json", "owner record"), "owner record")
    except OperatorRefused as error:
        raise OperatorRefused("this run root was not started by an operator") from error
    if owner.get("config_sha256") != config.sha256 or owner.get("operation_id") != config.operation_id:
        raise OperatorRefused("this run root belongs to another operator configuration")


def start(config: OperatorConfig) -> tuple[Path, str]:
    """Start the operation; return the handoff path and its SHA256. On failure, remove exactly what was started."""
    if config.run_root.exists() or config.run_root.is_symlink():
        raise OperatorRefused("the run root already exists: an operation starts once (use restart or stop)")
    supervisor = config.supervisor()
    _check_image(config)
    _check_names_free(supervisor)
    config.run_root.mkdir(mode=0o700)
    _write_once(config.run_root / "owner.json", {"operation_id": config.operation_id, "config_sha256": config.sha256,
                                                 "shutdown_owner": SHUTDOWN_OWNER}, 0o400)
    try:
        supervisor.start()
    except BaseException as error:
        cleanup = supervisor.stop()
        _write_once(config.run_root / "start-failed.json", {"error": type(error).__name__, "cleanup": cleanup}, 0o400)
        raise
    endpoint = supervisor.endpoint(config.channel_name)
    handoff = {
        "format": HANDOFF_FORMAT, "operation_id": config.operation_id, "config_sha256": config.sha256,
        "kind": config.release.kind, "release": config.release.settings(),
        "release_record": ({"path": str(config.release_record), "sha256": config.actual.record_sha256}
                           if config.actual is not None else None),
        "ca_bundle_sha256": config.actual.ca_bundle_sha256 if config.actual is not None else None,
        "image": {"reference": config.image_reference, "id": config.image_id},
        "endpoint": {name: (str(value) if isinstance(value, Path) else value)
                     for name, value in ((name, getattr(endpoint, name)) for name in ENDPOINT_FIELDS)},
        "evidence_dir": str(config.channel_path), "shutdown_owner": SHUTDOWN_OWNER, "started_at": time.time()}
    path = config.run_root / "handoff.json"
    return path, _write_once(path, handoff, 0o444)


def restart(config: OperatorConfig) -> None:
    """Restart the relay of this started operation. The relay's recovery never resends a started attempt."""
    _check_owned(config)
    if (config.run_root / "stopped.json").exists():
        raise OperatorRefused("this operation was stopped; a stopped operation is not restarted")
    config.supervisor().restart_relay()  # by image id: Docker refuses the launch if that exact image is gone


def stop(config: OperatorConfig) -> dict[str, Any]:
    """Remove exactly this operation's resources; record the first stop once. Returns what is left."""
    _check_owned(config)
    left = config.supervisor().stop()
    if not (config.run_root / "stopped.json").exists():
        _write_once(config.run_root / "stopped.json", {"left": left, "stopped_at": time.time()}, 0o400)
    return left


# --- application view ----------------------------------------------------------------------------------------------

def read_handoff(path: Path, sha256: str) -> OperatorHandoff:
    """The handoff at `path`, only if its bytes have `sha256` and exactly the frozen fields. It loads no ACTUAL record:
    the application still calls `load_actual_release` on the named record's raw bytes itself."""
    raw = _read_file(path, "handoff")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_sha, sha256):
        raise OperatorRefused("the handoff bytes do not have the named hash")
    value = _strict_json(raw, "handoff")
    if set(value) != HANDOFF_FIELDS or value["format"] != HANDOFF_FORMAT or value["shutdown_owner"] != SHUTDOWN_OWNER:
        raise OperatorRefused("the handoff must have exactly the frozen fields and format")
    endpoint = value["endpoint"]
    if not isinstance(endpoint, dict) or set(endpoint) != set(ENDPOINT_FIELDS):
        raise OperatorRefused("the handoff endpoint must have exactly the RelayEndpoint fields")
    record = value["release_record"]
    if value["kind"] == "ACTUAL":
        named = _named_file(record, "release_record")
        if not isinstance(value["ca_bundle_sha256"], str) or not SHA256.fullmatch(value["ca_bundle_sha256"]):
            raise OperatorRefused("an ACTUAL handoff names its CA bundle hash")
    elif value["kind"] == "AUTHORED" and record is None and value["ca_bundle_sha256"] is None:
        named = None
    else:
        raise OperatorRefused("the handoff kind and release record do not agree")
    if not isinstance(value["release"], dict) or value["release"].get("kind") != value["kind"]:
        raise OperatorRefused("the handoff release settings do not name its kind")
    image = value["image"]
    if not isinstance(image, dict) or set(image) != {"reference", "id"}:
        raise OperatorRefused("the handoff image must be {reference, id}")
    return OperatorHandoff(
        actual_sha, value["operation_id"], value["config_sha256"], value["kind"], value["release"], named,
        value["ca_bundle_sha256"], image["reference"], image["id"],
        RelayEndpoint(_absolute(endpoint["grants"], "grants"), _absolute(endpoint["revocations"], "revocations"),
                      _absolute(endpoint["state"], "state"), _absolute(endpoint["admission_key_file"], "admission key"),
                      endpoint["channel_root"], float(endpoint["heartbeat_max_age_seconds"])),
        _absolute(value["evidence_dir"], "evidence_dir"), float(value["started_at"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("command", nargs="?", default="check", choices=("check", "start", "restart", "stop"))
    args = parser.parse_args(argv)
    try:
        config = load_config(_read_file(args.config, "operator configuration"))
        if args.command == "check":
            print(f"config {config.sha256} kind {config.release.kind} operation {config.operation_id} admitted")
        elif args.command == "start":
            path, sha = start(config)
            print(f"handoff {path} sha256 {sha}")
        elif args.command == "restart":
            restart(config)
            print(f"restarted {config.operation_id}")
        else:
            left = stop(config)
            print(f"stopped {config.operation_id} left {json.dumps(left, sort_keys=True)}")
            return 0 if not any(left.values()) else 1
    except OperatorRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - report the class only: Docker errors carry mount paths and arguments
        print(f"failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
