"""Code-owned approval of one hosted deployment: the only path from local proof to a production live part.

A deployment record names the exact releases, origins, database TLS mode, host-gate references, image digests and
validity window of one hosted deployment. `APPROVED_HOSTED_DEPLOYMENTS` maps a deployment id to the canonical SHA-256
of its record. The map is empty in this candidate. Adding an entry is a reviewed code change with a recorded builder
approval of that exact record. No setting, environment value, file or request adds one: a record file is read only to
compare it with the code-owned hash, and only after the id is registered.

Production admits the Hermes relay application, the `hermes_local` interpreter and the approved research release only
when the running configuration names a registered record whose canonical hash and bound origins and TLS mode match.
Record version 2 adds `execution_release`, the exact release id and SHA-256 of the one controlled execution release
the deployment approves. A version 1 record still parses and binds no execution release, so it grants no execution.
Every other production refusal stays. See `docs/qualification/hosted-activation/CONTRACT.md` and
`docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

RECORD_VERSION = "edge-os.hosted-deployment/1"
RECORD_VERSION_2 = "edge-os.hosted-deployment/2"
MAX_RECORD_BYTES = 64 * 1024
TLS_MODES = frozenset({"require", "verify-ca", "verify-full"})
HOST_GATES = ("h1_egress", "h2_runner_isolation", "h8_provider_spend_cap", "h10_backup_restore")
RECORD_FIELDS = frozenset({"schema_version", "deployment_id", "public_origins", "cors_origins",
                           "database_tls_mode", "hermes_relay", "research_release", "host_gates",
                           "image_digests", "valid_from", "valid_until"})
# Version 2 is version 1 plus the bound execution release. Each version has exactly its frozen fields.
RECORD_FIELDS_BY_VERSION: Mapping[str, frozenset[str]] = {
    RECORD_VERSION: RECORD_FIELDS,
    RECORD_VERSION_2: RECORD_FIELDS | {"execution_release"},
}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
# Operating release ids carry a version suffix, for example `actual-moe-nansen-demo-20261018/1`.
RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
SHA256 = re.compile(r"[0-9a-f]{64}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_NAME = re.compile(r"[a-z][a-z0-9._-]{0,63}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
MAX_PATH = 400

# Approved hosted deployment id -> the canonical SHA-256 of its record. Empty in this candidate. Adding, changing or
# removing an entry is a reviewed code change that cites the builder's recorded approval of that exact record.
APPROVED_HOSTED_DEPLOYMENTS: Mapping[str, str] = {}


class HostedDeploymentRefused(RuntimeError):
    """The named deployment cannot be used. Raised before any live part is composed. The message never holds a value."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class GateReference:
    """One frozen host-gate artifact: a repository path and its exact SHA-256."""

    path: str
    sha256: str


@dataclass(frozen=True)
class HostedDeployment:
    """One validated hosted deployment record. Built only by `check_hosted_deployment`."""

    deployment_id: str
    record_sha256: str
    public_origins: tuple[str, ...]
    cors_origins: tuple[str, ...]
    database_tls_mode: str
    hermes_relay_release_id: str
    hermes_relay_record_sha256: str
    research_release_id: str
    research_release_sha256: str
    host_gates: Mapping[str, GateReference]
    image_digests: Mapping[str, str]
    valid_from: datetime
    valid_until: datetime
    # None for a version 1 record: it binds no execution release and admits none.
    execution_release_id: str | None = None
    execution_release_sha256: str | None = None

    def admits_hermes_relay(self, release_id: str, record_sha256: str) -> bool:
        """True only for the exact relay release id and record SHA-256 this deployment approves."""
        return (release_id == self.hermes_relay_release_id
                and hmac.compare_digest(record_sha256, self.hermes_relay_record_sha256))

    def admits_hermes_release_id(self, release_id: str) -> bool:
        """The relay release id alone. Used where a configuration carries no record hash."""
        return release_id == self.hermes_relay_release_id

    def admits_research_release(self, release_id: str, sha256: str) -> bool:
        """True only for the exact research release id and release SHA-256 this deployment approves."""
        return (release_id == self.research_release_id
                and hmac.compare_digest(sha256, self.research_release_sha256))

    def admits_execution_release(self, release_id: str, sha256: str) -> bool:
        """True only for the exact execution release id and SHA-256 a version 2 record binds. Never for version 1."""
        if self.execution_release_id is None or self.execution_release_sha256 is None:
            return False
        if not isinstance(release_id, str) or not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            return False
        return (release_id == self.execution_release_id
                and hmac.compare_digest(sha256, self.execution_release_sha256))


def canonical(record: Mapping[str, Any]) -> bytes:
    """The canonical JSON bytes the registry hash covers: sorted keys, compact separators, UTF-8."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check_hosted_deployment(settings: Any, *, approvals: Mapping[str, str] | None = None,
                            now: datetime | None = None) -> HostedDeployment | None:
    """The running configuration's approved deployment, or None when it names none.

    Raises `HostedDeploymentRefused` when the configuration names a record that is not approved, cannot be read, or
    does not bind the running origins and TLS mode. `approvals` replaces the code-owned registry for tests only."""
    named_id = getattr(settings, "hosted_deployment_id", None)
    named_path = getattr(settings, "hosted_deployment_record_path", None)
    if named_id is None and named_path is None:
        return None
    if named_id is None or named_path is None:
        raise HostedDeploymentRefused("hosted_deployment_incomplete",
                                      "the deployment id and the record path are set together")
    if not isinstance(named_id, str) or not IDENTIFIER.fullmatch(named_id):
        raise HostedDeploymentRefused("hosted_deployment_id_invalid", "the deployment id is not a valid identifier")
    path = _checked_path(named_path)
    registry = APPROVED_HOSTED_DEPLOYMENTS if approvals is None else approvals
    approved = registry.get(named_id)
    if not isinstance(approved, str) or not SHA256.fullmatch(approved):
        raise HostedDeploymentRefused("hosted_deployment_not_approved",
                                      "the code-owned registry lists no approval for this deployment id")
    value, digest = _read_bounded(path)
    if not hmac.compare_digest(digest, approved):
        raise HostedDeploymentRefused("hosted_deployment_hash_mismatch",
                                      "the record's canonical hash is not the approved hash")
    record = _parse(value, digest)
    if record.deployment_id != named_id:
        raise HostedDeploymentRefused("hosted_deployment_id_mismatch",
                                      "the record names another deployment id")
    running_origins = tuple(getattr(settings, "cors_origins", ()))
    if running_origins != record.cors_origins:
        raise HostedDeploymentRefused("hosted_deployment_origin_mismatch",
                                      "the running CORS origins are not the record's origins")
    if _running_tls_mode(settings) != record.database_tls_mode:
        raise HostedDeploymentRefused("hosted_deployment_tls_mismatch",
                                      "the running database TLS mode is not the record's mode")
    if now is None:
        now = datetime.now(UTC)
    if not (record.valid_from <= now < record.valid_until):
        raise HostedDeploymentRefused("hosted_deployment_outside_window",
                                      "the record is outside its validity window")
    return record


def _checked_path(value: Any) -> Path:
    if (not isinstance(value, str) or not value or len(value) > MAX_PATH or "\x00" in value
            or not Path(value).is_absolute() or ".." in Path(value).parts):
        raise HostedDeploymentRefused("hosted_deployment_record_path_invalid",
                                      "the record path must be a short absolute path without '..'")
    return Path(value)


def _read_bounded(path: Path) -> tuple[dict[str, Any], str]:
    """The record object, its canonical hash and nothing else. A regular file, not through a link, size bounded."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (OSError, TypeError, ValueError) as error:
        raise HostedDeploymentRefused("hosted_deployment_record_unreadable",
                                      "the record cannot be opened") from error
    try:
        try:
            info = os.fstat(fd)
        except OSError as error:
            raise HostedDeploymentRefused("hosted_deployment_record_unreadable",
                                          "the record cannot be read") from error
        if not stat.S_ISREG(info.st_mode):
            raise HostedDeploymentRefused("hosted_deployment_record_unreadable", "the record is not a regular file")
        if info.st_size > MAX_RECORD_BYTES:
            raise HostedDeploymentRefused("hosted_deployment_record_too_large", "the record is too large")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(fd, 8192)
            except OSError as error:
                raise HostedDeploymentRefused("hosted_deployment_record_unreadable",
                                              "the record cannot be read") from error
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_RECORD_BYTES:
                raise HostedDeploymentRefused("hosted_deployment_record_too_large", "the record is too large")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    parsed = _strict_object(raw)
    return parsed, hashlib.sha256(canonical(parsed)).hexdigest()


def _strict_object(raw: bytes) -> dict[str, Any]:
    def no_repeats(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise HostedDeploymentRefused("hosted_deployment_invalid", "the record repeats a key")
        return dict(pairs)

    def no_constant(name: str) -> Any:
        raise HostedDeploymentRefused("hosted_deployment_invalid", f"the record holds {name}")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_repeats, parse_constant=no_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the record is not strict JSON") from error
    if not isinstance(value, dict):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the record must be one JSON object")
    return value


def _parse(value: dict[str, Any], digest: str) -> HostedDeployment:
    version = value.get("schema_version")
    fields = RECORD_FIELDS_BY_VERSION.get(version) if isinstance(version, str) else None
    if fields is None or set(value) != fields:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the record has not the frozen fields and version")
    deployment_id = value["deployment_id"]
    if not isinstance(deployment_id, str) or not IDENTIFIER.fullmatch(deployment_id):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the deployment id is not valid")
    public = _origins(value["public_origins"])
    cors = _origins(value["cors_origins"])
    if any(origin not in public for origin in cors):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "a CORS origin is not a public origin")
    tls = value["database_tls_mode"]
    if tls not in TLS_MODES:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the TLS mode is not accepted")
    relay = _pair(value["hermes_relay"], "release_id", "record_sha256")
    research = _pair(value["research_release"], "release_id", "sha256")
    execution = (_pair(value["execution_release"], "release_id", "sha256")
                 if value["schema_version"] == RECORD_VERSION_2 else (None, None))
    gates = _host_gates(value["host_gates"])
    images = _images(value["image_digests"])
    start = _timestamp(value["valid_from"])
    end = _timestamp(value["valid_until"])
    if end <= start:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the validity window is empty or reversed")
    return HostedDeployment(
        deployment_id=deployment_id, record_sha256=digest, public_origins=public, cors_origins=cors,
        database_tls_mode=tls, hermes_relay_release_id=relay[0], hermes_relay_record_sha256=relay[1],
        research_release_id=research[0], research_release_sha256=research[1], host_gates=gates,
        image_digests=images, valid_from=start, valid_until=end,
        execution_release_id=execution[0], execution_release_sha256=execution[1])


def _origins(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 20:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "an origin list is empty or too long")
    origins: list[str] = []
    for item in value:
        if not isinstance(item, str) or item in origins or not _is_origin(item):
            raise HostedDeploymentRefused("hosted_deployment_invalid", "an origin is not a public HTTPS origin")
        origins.append(item)
    return tuple(origins)


def _is_origin(value: str) -> bool:
    if "*" in value or len(value) > 200:
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return (parts.scheme == "https" and bool(parts.hostname) and parts.path in ("", "/")
            and not parts.query and not parts.fragment and not parts.username and not parts.password)


def _pair(value: Any, id_field: str, hash_field: str) -> tuple[str, str]:
    if not isinstance(value, dict) or set(value) != {id_field, hash_field}:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "a bound release needs exactly its id and hash")
    release_id, digest = value[id_field], value[hash_field]
    if not isinstance(release_id, str) or not RELEASE_ID.fullmatch(release_id):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "a bound release id is not valid")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "a bound release hash is not a SHA-256")
    return release_id, digest


def _host_gates(value: Any) -> Mapping[str, GateReference]:
    if not isinstance(value, dict) or set(value) != set(HOST_GATES):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the record names not the four host gates")
    gates: dict[str, GateReference] = {}
    for name in HOST_GATES:
        item = value[name]
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise HostedDeploymentRefused("hosted_deployment_invalid", "a host gate needs exactly its path and hash")
        path, digest = item["path"], item["sha256"]
        if (not isinstance(path, str) or not path or len(path) > MAX_PATH
                or not path.startswith("docs/qualification/")
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            raise HostedDeploymentRefused("hosted_deployment_invalid", "a host gate reference is not valid")
        gates[name] = GateReference(path=path, sha256=digest)
    return gates


def _images(value: Any) -> Mapping[str, str]:
    if not isinstance(value, dict) or not value or len(value) > 20:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "the image digest list is empty or too long")
    images: dict[str, str] = {}
    for name, digest in value.items():
        if (not isinstance(name, str) or not IMAGE_NAME.fullmatch(name) or not isinstance(digest, str)
                or not IMAGE_ID.fullmatch(digest)):
            raise HostedDeploymentRefused("hosted_deployment_invalid", "an image digest is not a Docker image id")
        images[name] = digest
    return images


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise HostedDeploymentRefused("hosted_deployment_invalid", "a validity timestamp is not UTC whole seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise HostedDeploymentRefused("hosted_deployment_invalid", "a validity timestamp is not a date") from error


def _running_tls_mode(settings: Any) -> str | None:
    try:
        url = make_url(getattr(settings, "database_url", ""))
    except (ArgumentError, TypeError, ValueError):
        return None
    value = url.query.get("sslmode")
    return value if isinstance(value, str) else None
