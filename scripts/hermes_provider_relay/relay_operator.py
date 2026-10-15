"""One bounded operator entry for the accepted relay: start, restart and stop `RelaySupervisor` from one configuration.

    python relay_operator.py CONFIG [check|start|restart|stop]     (run with the API's Python; `check` is the default)

The configuration is one immutable strict JSON file (format `edge-os.relay-operator-config/1`). It names the release
(AUTHORED settings, or an ACTUAL release record by path and SHA256 with its CA bundle), the pinned Hermes image by
reference and Docker id, the task-owned run root and operation id, the one channel and the host-held provider key file.
The topology is always the accepted E1 one (`online=True`, CONTRACT A6). Every refusal happens before any effect:

- `check` reads the configuration, the release record and the CA bundle and stats the key file. No Docker, no write.
- `start` also requires a run root and channel folder that do not exist yet, the image id Docker reports for the
  reference and no container, network or volume under this operation's names. It then claims the run root (an
  exclusive `mkdir`, 0700), records its owner, starts the supervisor, records the network id and writes `handoff.json`
  once (0444). Any failure after the claim removes the resources this operation owns and records `start-failed.json`.
- `restart` restarts the relay of a complete started operation; the relay's own recovery marks a started attempt
  `unknown_restart` and never sends it again. The operator sends nothing itself.
- `stop` removes exactly this operation's owned containers, network and volume, records `stopped.json` once when the
  stop ends clean and `stop-incomplete-<ns>.json` otherwise. It needs only the configuration bytes and the run root's
  owner record, not the key file or a still-approved release.

Ownership: the supervisor run id (every Docker name and label) is `<operation_id>-<first 12 hex of the configuration
SHA256>`, so two configurations never share names even with one operation id. A resource counts as this operation's
only if it carries this run id's label and, for a container, mounts its role's config file from this run root (the
resolved path, or exactly that path under Docker Desktop's `/host_mnt`), for
the network, has the id recorded at start, and for the egress volume, carries the random claim label this start wrote
(the operator creates that volume before the supervisor, because Docker re-uses an existing volume of that name).
Absent means Docker's exact no-such-object answer for that kind and name (Docker 29.4.0 says `network NAME not found`
for a network, plain or in the daemon's JSON `message`); any other unreadable answer is unknown, never gone and never ours.
Foreign and unknown objects are never killed, removed, mounted or adopted, and are reported. Removal goes by the Docker
id just inspected (a volume by its name) and is then checked; only a stop that ends clean writes `stopped.json`.

ACTUAL is accepted only through `relay_admission.load_actual_release` with its default registry, which is empty: every
ACTUAL configuration is refused. The operator never reads the provider key; it only checks the file is outside the
repository and readable by its owner only. No key, key path or environment value is written to the handoff or printed.
`read_handoff` is the operator's strict reader of its own handoff (format `edge-os.relay-operator-handoff/1`).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import subprocess
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
from relay_supervisor import LABEL, RelaySupervisor  # noqa: E402
from relay_turn_runner import RelayEndpoint  # noqa: E402

__all__ = ["OperationTarget", "OperatorConfig", "OperatorHandoff", "OperatorRefused", "load_config", "load_target",
           "main", "read_handoff", "restart", "start", "stop"]

CONFIG_FORMAT = "edge-os.relay-operator-config/1"
HANDOFF_FORMAT = "edge-os.relay-operator-handoff/1"
SHUTDOWN_OWNER = "relay_operator"  # the only actor that stops, restarts or removes the relay; the application never does
CONFIG_FIELDS = frozenset({"format", "operation_id", "kind", "release", "release_record", "ca_bundle", "image",
                           "run_root", "channel", "provider_key_file", "shutdown_owner"})
HANDOFF_FIELDS = frozenset({"format", "operation_id", "config_sha256", "kind", "release", "release_record",
                            "ca_bundle_sha256", "image", "endpoint", "evidence_dir", "shutdown_owner", "started_at"})
ENDPOINT_FIELDS = ("grants", "revocations", "state", "admission_key_file", "channel_root", "heartbeat_max_age_seconds")
OPERATION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
CHANNEL_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_FILE_BYTES = 1024 * 1024
VOLUME_CLAIM_LABEL = "edge-os.relay-operator.claim"  # a fresh random value per start, on the egress volume only
CONFIG_FILES = {"relay": "relay-config.json", "gateway": "gateway-config.json", "provider": "provider-config.json"}


class OperatorRefused(ValueError):
    """The configuration or the host state does not allow this command. Nothing was started, changed or removed."""


@dataclass(frozen=True)
class OperationTarget:
    """What identifies one operation's resources: enough to stop it without its key file or release approval."""

    sha256: str  # of the configuration bytes
    operation_id: str
    run_root: Path

    @property
    def run_id(self) -> str:
        """The supervisor run id: every Docker name and label. Distinct for every configuration."""
        return f"{self.operation_id}-{self.sha256[:12]}"

    def names(self) -> dict[str, str]:
        """The names `RelaySupervisor` gives this run id's resources (checked against it in the tests)."""
        run = self.run_id
        return {"relay": f"relay-{run}", "provider": f"relay-provider-{run}", "gateway": f"relay-gateway-{run}",
                "egress": f"relay-egress-{run}"}


@dataclass(frozen=True)
class OperatorConfig:
    target: OperationTarget
    release: RelayRelease
    actual: ActualRelease | None
    release_record: Path | None
    ca_bundle: Path | None
    image_reference: str
    image_id: str
    channel_name: str
    channel_path: Path
    provider_key_file: Path

    @property
    def sha256(self) -> str:
        return self.target.sha256

    @property
    def operation_id(self) -> str:
        return self.target.operation_id

    @property
    def run_root(self) -> Path:
        return self.target.run_root

    def supervisor(self) -> RelaySupervisor:
        """Construction does nothing (accepted `RelaySupervisor`); the relay lives under `<run root>/relay`. Every container
        is launched by the immutable image id, never by the reference, so a moved tag cannot change what runs."""
        return RelaySupervisor(self.run_root / "relay", self.release, self.image_id, self.target.run_id,
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


def _number(value: Any, what: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (
            positive and value <= 0):
        raise OperatorRefused(f"{what} must be a finite number" + (" above 0" if positive else ""))
    return float(value)


def _named_file(value: Any, what: str) -> tuple[Path, str]:
    if (not isinstance(value, dict) or set(value) != {"path", "sha256"} or not isinstance(value["sha256"], str)
            or not SHA256.fullmatch(value["sha256"])):
        raise OperatorRefused(f"{what} must be {{path, sha256}} with a lower-case SHA256")
    return _absolute(value["path"], f"{what} path"), value["sha256"]


def _image(value: Any) -> tuple[str, str]:
    if (not isinstance(value, dict) or set(value) != {"reference", "id"} or not isinstance(value["reference"], str)
            or not 0 < len(value["reference"]) <= 200 or any(c.isspace() for c in value["reference"])
            or not isinstance(value["id"], str) or not IMAGE_ID.fullmatch(value["id"])):
        raise OperatorRefused("image must be {reference, id} with a Docker sha256 id")
    return value["reference"], value["id"]


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


def _target(raw: bytes, value: dict[str, Any]) -> OperationTarget:
    if value.get("format") != CONFIG_FORMAT:
        raise OperatorRefused(f"the configuration format must be {CONFIG_FORMAT}")
    operation_id = value.get("operation_id")
    if not isinstance(operation_id, str) or not OPERATION_ID.fullmatch(operation_id):
        raise OperatorRefused("operation_id must be 1-40 lower-case letters, digits or -")
    return OperationTarget(hashlib.sha256(raw).hexdigest(), operation_id, _absolute(value.get("run_root"), "run_root"))


def load_target(raw: bytes) -> OperationTarget:
    """Only what `stop` needs: the configuration hash, operation id and run root. No key file or release is read."""
    return _target(raw, _strict_json(raw, "operator configuration"))


def load_config(raw: bytes) -> OperatorConfig:
    """The validated configuration in `raw`, or OperatorRefused. Reads the named record and CA bundle; no other effect."""
    value = _strict_json(raw, "operator configuration")
    if set(value) != CONFIG_FIELDS:
        raise OperatorRefused("the operator configuration must have exactly the frozen fields")
    target = _target(raw, value)
    if value["shutdown_owner"] != SHUTDOWN_OWNER:
        raise OperatorRefused(f"shutdown_owner must be {SHUTDOWN_OWNER}")
    reference, image_id = _image(value["image"])
    channel = value["channel"]
    if (not isinstance(channel, dict) or set(channel) != {"name", "path"} or not isinstance(channel["name"], str)
            or not CHANNEL_NAME.fullmatch(channel["name"])):
        raise OperatorRefused("channel must be {name, path} with a short lower-case name")
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
        except (TypeError, ValueError) as error:
            raise OperatorRefused(f"the ACTUAL release is refused: {error}") from error
        if ca_sha != actual.ca_bundle_sha256:
            raise OperatorRefused("the CA bundle hash is not the release record's")
        if not hmac.compare_digest(hashlib.sha256(_read_file(ca, "CA bundle")).hexdigest(), ca_sha):
            raise OperatorRefused("the CA bundle file does not have the named hash")
        release = actual.release
    else:
        raise OperatorRefused("kind must be AUTHORED or ACTUAL")
    return OperatorConfig(target, release, actual, record, ca, reference, image_id, channel["name"], channel_path, key)


# --- ownership -----------------------------------------------------------------------------------------------------------

def _write_once(path: Path, value: dict[str, Any], mode: int) -> str:
    """Create `path` exclusively with `value`; return its SHA256. An existing file is never replaced; a failed write
    leaves no partial file."""
    data = (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
        os.fchmod(fd, mode)
    except BaseException:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    os.close(fd)
    return hashlib.sha256(data).hexdigest()


def _docker(*args: str) -> subprocess.CompletedProcess[str] | None:
    """One Docker call that never raises: None when Docker could not be asked (missing, timed out)."""
    try:
        return relay_supervisor.docker(*args, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


DAEMON_ERROR = "Error response from daemon: "
DOCKER_DESKTOP_HOST_ROOT = "/host_mnt"  # Docker Desktop's bind Source for a host path is this prefix + the path


def _absent_answers(kind: str, name: str) -> set[str]:
    """Docker's whole error line for no `kind` object named `name`: the generic `inspect` forms and each kind's own
    (Docker 29.4.0: `network NAME not found`, `No such container: NAME`, `get NAME: no such volume`)."""
    own = {"container": f"No such container: {name}", "network": f"network {name} not found",
           "volume": f"get {name}: no such volume"}[kind]
    return {prefix + text for prefix in ("Error: ", DAEMON_ERROR)
            for text in (f"No such object: {name}", f"No such {kind}: {name}", own)}


def _absent_line(line: str, kind: str, name: str) -> bool:
    """One of those lines, plain or with the daemon's JSON body (`Error response from daemon: {"message": "..."}`,
    one strict object whose only key is a string `message`), as Docker 29.4.0 also answers."""
    allowed = _absent_answers(kind, name)
    if line in allowed:
        return True
    if not line.startswith(DAEMON_ERROR):
        return False
    try:
        body = _strict_json(line.removeprefix(DAEMON_ERROR).encode(), "Docker error")
    except OperatorRefused:
        return False
    message = body.get("message")
    return set(body) == {"message"} and isinstance(message, str) and DAEMON_ERROR + message in allowed


def _inspect(kind: str, name: str) -> dict[str, Any] | None | bool:
    """Docker's view of the object named `name`: None only when Docker's whole answer is the no-such-object error for
    this kind and name, False when it is anything else that is not one readable object (daemon down, permission,
    timeout, another name or kind, an extra error, a malformed reply)."""
    seen = _docker("inspect", "--type", kind, name)
    if seen is None:
        return False
    if seen.returncode != 0:
        lines = (seen.stderr or "").strip().splitlines()
        absent = (seen.stdout or "").strip() in ("", "[]") and lines and all(_absent_line(line, kind, name)
                                                                               for line in lines)
        return None if absent else False
    try:
        [value] = json.loads(seen.stdout)
    except (TypeError, ValueError):
        return False
    return value if isinstance(value, dict) else False


def _ownership(target: OperationTarget, kind: str, role: str, network_id: str | None,
               claim: str | None) -> tuple[str, str | None]:
    """('absent' | 'owned' | 'foreign' | 'unknown', what to remove an owned object by) for one of this operation's names.
    Owned: this run id's label, and a container's role config mounted from this run root, the network id recorded at
    start, the volume's claim label written by this start."""
    name = target.names()["egress" if kind != "container" else role]
    seen = _inspect(kind, name)
    if seen is None:
        return "absent", None
    if seen is False:
        return "unknown", None  # never treated as gone and never as ours
    labels = (seen.get("Config") or {}).get("Labels") if kind == "container" else seen.get("Labels")
    if not isinstance(labels, dict) or labels.get(LABEL) != target.run_id:
        return "foreign", None
    if kind == "container":
        expected = str((target.run_root / "relay" / CONFIG_FILES[role]).resolve())
        sources = {mount.get("Source") for mount in seen.get("Mounts") or [] if isinstance(mount, dict)}
        if not sources & {expected, DOCKER_DESKTOP_HOST_ROOT + expected}:
            return "foreign", None
    if kind == "network" and network_id is not None and seen.get("Id") != network_id:
        return "foreign", None
    if kind == "volume" and (claim is None or labels.get(VOLUME_CLAIM_LABEL) != claim):
        return "foreign", None
    identity = name if kind == "volume" else seen.get("Id")
    return ("owned", identity) if isinstance(identity, str) and identity else ("unknown", None)


def _recorded_network(target: OperationTarget) -> str | None:
    path = target.run_root / "resources.json"
    if not path.exists():
        return None
    value = _strict_json(_read_file(path, "resource record"), "resource record").get("network_id")
    if not isinstance(value, str):
        raise OperatorRefused("the resource record names no network id")
    return value


def _resources(target: OperationTarget, network_id: str | None, claim: str | None) -> dict[str, tuple[str, str | None]]:
    found = {role: _ownership(target, "container", role, None, claim) for role in ("relay", "gateway", "provider")}
    found["network"] = _ownership(target, "network", "egress", network_id, claim)
    found["volume"] = _ownership(target, "volume", "egress", network_id, claim)
    return found


def _name(target: OperationTarget, role: str) -> str:
    return target.names()["egress" if role in ("network", "volume") else role]


def _remove_owned(target: OperationTarget, network_id: str | None, claim: str | None) -> dict[str, Any]:
    """Remove this operation's owned objects by id and check they are gone. Foreign objects stay; objects whose state
    Docker did not establish stay as `unknown`; failed removals are `errors`. Clean only when every list is empty."""
    found = _resources(target, network_id, claim)
    foreign = sorted({_name(target, role) for role, (state, _) in found.items() if state == "foreign"})
    unknown = sorted({_name(target, role) for role, (state, _) in found.items() if state == "unknown"})
    errors: list[str] = []
    removal = {"relay": ("rm", "-f"), "gateway": ("rm", "-f"), "provider": ("rm", "-f"), "network": ("network", "rm"),
               "volume": ("volume", "rm")}
    for role in ("relay", "gateway", "provider", "network", "volume"):  # containers first: a used network cannot go
        state, identity = found[role]
        if state == "owned":
            done = _docker(*removal[role], str(identity))
            if done is None or done.returncode != 0:
                errors.append(_name(target, role))
    for role, (state, _) in found.items():  # every removed object must now be positively absent
        if state == "owned" and _ownership(target, "container" if role not in ("network", "volume") else role,
                                           role if role not in ("network", "volume") else "egress", network_id,
                                           claim)[0] != "absent":
            unknown.append(_name(target, role))
    left: dict[str, Any] = {}
    label = f"label={LABEL}={target.run_id}"
    for key, command in (("containers_left", ("ps", "-a")), ("networks_left", ("network", "ls")),
                         ("volumes_left", ("volume", "ls"))):
        listed = _docker(*command, "--filter", label, "--format", "{{.Names}}" if key == "containers_left" else
                         "{{.Name}}")
        if listed is None or listed.returncode != 0:
            unknown.append(f"listing:{key}")
            left[key] = []
        else:
            left[key] = listed.stdout.split()
    return {**left, "foreign": foreign, "unknown": sorted(set(unknown)), "errors": sorted(set(errors))}


def _check_owned(target: OperationTarget) -> dict[str, Any]:
    """Restart and stop act only on a run root this exact configuration claimed. Returns its owner record."""
    try:
        owner = _strict_json(_read_file(target.run_root / "owner.json", "owner record"), "owner record")
    except OperatorRefused as error:
        raise OperatorRefused("this run root was not started by an operator") from error
    if (owner.get("config_sha256"), owner.get("operation_id"), owner.get("run_id")) != (
            target.sha256, target.operation_id, target.run_id):
        raise OperatorRefused("this run root belongs to another operator configuration")
    return owner


def _check_image(config: OperatorConfig) -> None:
    """The reference must name exactly the configured image now; the launches then use the id itself."""
    seen = relay_supervisor.docker("image", "inspect", config.image_reference, "--format", "{{.Id}}", check=False)
    if seen.returncode != 0 or seen.stdout.strip() != config.image_id:
        raise OperatorRefused("the image reference does not have the configured Docker id")


def _check_new_folders(config: OperatorConfig) -> None:
    for path, what in ((config.run_root, "run root"), (config.channel_path, "channel folder")):
        if path.exists() or path.is_symlink():
            raise OperatorRefused(f"the {what} already exists: an operation starts once with new folders")
    channel = config.channel_path.resolve()
    if channel == config.run_root.resolve() or channel.is_relative_to((config.run_root / "relay").resolve()):
        raise OperatorRefused("the channel folder must not be the run root or inside the relay's folder")


def _claim_volume(target: OperationTarget, claim: str) -> None:
    """Create the egress volume before the supervisor does, with the supervisor's own options and run label plus this
    start's claim label, and require that claim. Docker re-uses an existing local volume of that name without an error
    (and keeps its labels), so a volume that was already there fails this check before any container mounts it. The
    supervisor's own `volume create` then re-uses this one."""
    name = target.names()["egress"]
    created = _docker("volume", "create", "--driver", "local", "--opt", "type=tmpfs", "--opt", "device=tmpfs", "--opt",
                      f"o=uid={os.getuid()},gid={os.getgid()},mode=0700,size=1m", "--label", f"{LABEL}={target.run_id}",
                      "--label", f"{VOLUME_CLAIM_LABEL}={claim}", name)
    if created is None or created.returncode != 0:
        raise RuntimeError("the egress volume could not be created")
    if _ownership(target, "volume", "egress", None, claim)[0] != "owned":
        raise RuntimeError("a volume under this operation's name was there before this start's claim")


# --- commands ------------------------------------------------------------------------------------------------------------

def start(config: OperatorConfig) -> tuple[Path, str]:
    """Start the operation; return the handoff path and its SHA256. After the claim, any failure removes exactly the
    owned objects, records `start-failed.json` (error class, cleanup result or cleanup error class) and re-raises."""
    target = config.target
    _check_new_folders(config)
    supervisor = config.supervisor()
    _check_image(config)
    for role, (state, _) in _resources(target, None, None).items():
        if state != "absent":
            raise OperatorRefused(f"the {role} name is not free ({state}); this operation did not create it")
    try:
        config.run_root.mkdir(mode=0o700)  # the exclusive claim: a competing start of this configuration fails here
    except FileExistsError as error:
        raise OperatorRefused("another start claimed this run root first") from error
    claim = secrets.token_hex(16)
    try:
        _write_once(config.run_root / "owner.json", {"operation_id": target.operation_id, "run_id": target.run_id,
                                                     "config_sha256": target.sha256, "shutdown_owner": SHUTDOWN_OWNER,
                                                     "volume_claim": claim}, 0o400)
    except BaseException:
        config.run_root.rmdir()  # still empty and created by this call; an rmdir never removes anything else
        raise
    try:
        config.channel_path.mkdir(mode=0o700)
        _claim_volume(target, claim)
        supervisor.start()
        network = _inspect("network", target.names()["egress"])
        if not isinstance(network, dict) or not isinstance(network.get("Id"), str):
            raise RuntimeError("the started network cannot be read")
        _write_once(config.run_root / "resources.json", {"network_id": network["Id"]}, 0o400)
        needed = ("relay", "gateway", "network", "volume") + (("provider",) if config.actual is None else ())
        found = _resources(target, network["Id"], claim)
        if any(found[role][0] != "owned" for role in needed):  # finds a swap; cannot undo a mount that already happened
            raise RuntimeError("a started object is not this operation's own")
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
    except BaseException as error:
        cleanup: dict[str, Any] | None = None
        cleanup_error: str | None = None
        try:
            cleanup = _remove_owned(target, _recorded_network(target), claim)
        except Exception as failure:  # noqa: BLE001 - recorded; the start error is the one raised
            cleanup_error = type(failure).__name__
        try:
            _write_once(config.run_root / "start-failed.json", {"error": type(error).__name__, "cleanup": cleanup,
                                                                "cleanup_error": cleanup_error}, 0o400)
        except OSError:
            pass  # the start error still propagates; `stop` can clean up from owner.json
        raise


def restart(config: OperatorConfig) -> None:
    """Restart the relay of this complete started operation. The relay's recovery never resends a started attempt."""
    target = config.target
    owner = _check_owned(target)
    for name, why in (("start-failed.json", "its start failed"), ("stopped.json", "it was stopped")):
        if (config.run_root / name).exists():
            raise OperatorRefused(f"this operation is not restarted: {why}")
    if any(config.run_root.glob("stop-incomplete-*.json")):
        raise OperatorRefused("this operation is not restarted: a stop was asked for")
    if not (config.run_root / "handoff.json").exists():
        raise OperatorRefused("this operation is not restarted: it has no handoff (its start did not complete)")
    found = _resources(target, _recorded_network(target), owner.get("volume_claim"))
    needed = ("gateway", "network", "volume") + (("provider",) if config.actual is None else ())
    if found["relay"][0] not in ("owned", "absent") or any(found[role][0] != "owned" for role in needed):
        raise OperatorRefused("this operation is incomplete, or a resource under its names is not its own or unknown")
    if found["relay"][0] == "owned":
        relay_supervisor.docker("kill", str(found["relay"][1]), check=False)
        relay_supervisor.docker("rm", "-f", str(found["relay"][1]), check=False)
    config.supervisor().start_relay()  # by image id: Docker refuses the launch if that exact image is gone


def stop(target: OperationTarget) -> dict[str, Any]:
    """Remove exactly this operation's owned objects. Only a stop that ends with nothing left, foreign, unknown or failed
    writes `stopped.json` (the first such stop); any other stop writes its own `stop-incomplete-<ns>.json`."""
    owner = _check_owned(target)
    left = _remove_owned(target, _recorded_network(target), owner.get("volume_claim"))
    record = {"left": left, "stopped_at": time.time()}
    if any(left.values()):
        _write_once(target.run_root / f"stop-incomplete-{time.time_ns()}.json", record, 0o400)
    elif not (target.run_root / "stopped.json").exists():
        _write_once(target.run_root / "stopped.json", record, 0o400)
    return left


# --- the operator's own handoff reader -----------------------------------------------------------------------------------

def read_handoff(path: Path, sha256: str) -> OperatorHandoff:
    """The handoff at `path`, only if its bytes have `sha256` and exactly the frozen fields and value shapes. It loads no
    ACTUAL record: the application still calls `load_actual_release` on the named record's raw bytes itself."""
    raw = _read_file(path, "handoff")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_sha, sha256):
        raise OperatorRefused("the handoff bytes do not have the named hash")
    value = _strict_json(raw, "handoff")
    if set(value) != HANDOFF_FIELDS or value["format"] != HANDOFF_FORMAT or value["shutdown_owner"] != SHUTDOWN_OWNER:
        raise OperatorRefused("the handoff must have exactly the frozen fields and format")
    if not isinstance(value["operation_id"], str) or not OPERATION_ID.fullmatch(value["operation_id"]):
        raise OperatorRefused("the handoff operation_id is not an operation id")
    if not isinstance(value["config_sha256"], str) or not SHA256.fullmatch(value["config_sha256"]):
        raise OperatorRefused("the handoff config_sha256 is not a SHA256")
    kind, release = value["kind"], value["release"]
    try:  # the same field rules as a release; an ACTUAL one is checked as settings, never built
        valid = isinstance(release, dict) and RelayRelease.from_settings({**release, "kind": "AUTHORED"}).settings() == {
            **release, "kind": "AUTHORED"}
    except (KeyError, TypeError, ValueError):
        valid = False
    if kind not in ("AUTHORED", "ACTUAL") or not valid or release["kind"] != kind:
        raise OperatorRefused("the handoff release settings are not a valid release of its kind")
    if kind == "ACTUAL":
        named = _named_file(value["release_record"], "release_record")
        if not isinstance(value["ca_bundle_sha256"], str) or not SHA256.fullmatch(value["ca_bundle_sha256"]):
            raise OperatorRefused("an ACTUAL handoff names its CA bundle hash")
    elif value["release_record"] is None and value["ca_bundle_sha256"] is None:
        named = None
    else:
        raise OperatorRefused("the handoff kind and release record do not agree")
    reference, image_id = _image(value["image"])
    endpoint = value["endpoint"]
    if not isinstance(endpoint, dict) or set(endpoint) != set(ENDPOINT_FIELDS):
        raise OperatorRefused("the handoff endpoint must have exactly the RelayEndpoint fields")
    if not isinstance(endpoint["channel_root"], str) or not CHANNEL_NAME.fullmatch(endpoint["channel_root"]):
        raise OperatorRefused("the handoff channel_root is not a channel name")
    return OperatorHandoff(
        actual_sha, value["operation_id"], value["config_sha256"], kind, release, named, value["ca_bundle_sha256"],
        reference, image_id,
        RelayEndpoint(_absolute(endpoint["grants"], "grants"), _absolute(endpoint["revocations"], "revocations"),
                      _absolute(endpoint["state"], "state"), _absolute(endpoint["admission_key_file"], "admission key"),
                      endpoint["channel_root"],
                      _number(endpoint["heartbeat_max_age_seconds"], "heartbeat_max_age_seconds", positive=True)),
        _absolute(value["evidence_dir"], "evidence_dir"), _number(value["started_at"], "started_at", positive=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("command", nargs="?", default="check", choices=("check", "start", "restart", "stop"))
    args = parser.parse_args(argv)
    try:
        raw = _read_file(args.config, "operator configuration")
        if args.command == "stop":
            target = load_target(raw)
            left = stop(target)
            print(f"stopped {target.operation_id} left {json.dumps(left, sort_keys=True)}")
            return 0 if not any(left.values()) else 1
        config = load_config(raw)
        if args.command == "check":
            print(f"config {config.sha256} kind {config.release.kind} operation {config.operation_id} admitted")
        elif args.command == "start":
            path, sha = start(config)
            print(f"handoff {path} sha256 {sha}")
        else:
            restart(config)
            print(f"restarted {config.operation_id}")
    except OperatorRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - report the class only: Docker errors carry mount paths and arguments
        print(f"failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
