"""The saved Research path over an approved Hermes relay release, with the shared PostgreSQL spend ledger.

`open_hermes_application` composes, and adds no runner of its own:

    GuardedTurnRunner (accepted) over PostgresSpendLedger (shared), priced by the release's price snapshot
      -> RelayTurnRunner (accepted: grant before the job, close after, E1-COST1 cost check with the SAME TokenPrice)
        -> TransportTurnRunner -> GuardedDockerTurnRunner with the relay job entry (accepted; the job holds no key)

One immutable `HermesApplicationRelease` binds the approved relay record (route, policy, model, output schema, CA,
destination), the job image, the relay channel and ONE `TokenPrice` built from the price snapshot the record names. That
price object is the one the ledger reserves and settles with and the one the relay runner checks the provider cost with.

A release is composed only from a code-owned definition in `RELEASE_DEFINITIONS` whose record SHA-256 is in the relay's
trusted registry `relay_admission.APPROVED_ACTUAL_RELEASES`. Both are empty, so the default composes nothing: no engine,
file, key, socket or Docker command. No setting, environment value, file or request adds a definition. Production is
refused. The application holds no provider key: the relay holds it. The owner and saved request of each grant are read
from the saved attempt row and must equal those the RESERVED reservation copied from it; anything else gets no grant.

Give `app.runner` and `app.config` to `create_app(settings, hermes_runner=..., hermes_config=...)` with
`EDGE_OS_INTERPRETER=hermes_local`. The lane-1 relay operator starts the relay and owns its shutdown; its one-time
handoff file names the endpoint and evidence folder and approves nothing. LOCAL only: the accepted job
code lives under `scripts/`, which this module adds to the import path; the application factory does not import it.
See `docs/qualification/hermes-application-release/CONTRACT.md`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from edge_os_api.core.database import make_engine, make_session_factory, require_head
from edge_os_api.core.settings import Settings
from edge_os_api.research.hermes_interpreter import HermesInterpreterConfig, HermesTurn, HermesTurnRunner, LiveRelease
# `hermes_transport_mount` (through `provider_spend_ledger`) has already added the accepted runner folders.
from edge_os_api.research.hermes_transport_mount import DEFAULT_POLICY, MountRefused
from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, SpendLimits, TokenPrice

RELAY = Path(__file__).resolve().parents[5] / "scripts" / "hermes_provider_relay"
if str(RELAY) not in sys.path:
    sys.path.append(str(RELAY))

import relay_admission  # noqa: E402  - read at call time, so the trusted registry is the relay's own
from guarded_docker_runner import GuardedDockerTurnRunner  # noqa: E402
from provider_guard import GuardPolicy  # noqa: E402
from provider_transport import TransportRoute  # noqa: E402
from relay_admission import ActualRelease, RelaySubject, load_actual_release  # noqa: E402
from relay_turn_runner import RelayEndpoint, build_relay_job  # noqa: E402

__all__ = ["HermesApplication", "HermesApplicationRelease", "RELEASE_DEFINITIONS", "RelayApplicationDefinition",
           "bind_release", "compose_application", "open_hermes_application"]

SNAPSHOT_FIELDS = frozenset({"model", "provider", "prompt_usd_per_million", "completion_usd_per_million"})
DECIMAL = re.compile(r"(0|[1-9][0-9]{0,8})(\.[0-9]{1,12})?")
HANDOFF_FORMAT = "edge-os.relay-operator-handoff/1"
HANDOFF_FIELDS = frozenset({"format", "operation_id", "config_sha256", "kind", "release", "release_record",
                            "ca_bundle_sha256", "image", "endpoint", "evidence_dir", "shutdown_owner", "started_at"})
ENDPOINT_FIELDS = frozenset({"grants", "revocations", "state", "admission_key_file", "channel_root",
                             "heartbeat_max_age_seconds"})
MAX_HANDOFF_BYTES = 16 * 1024
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")  # the immutable id `docker image inspect --format {{.Id}}` reports
IMAGE_REFERENCE = re.compile(r"[^\s]{1,200}")
MAX_HEARTBEAT_AGE_SECONDS = 10.0


@dataclass(frozen=True)
class RelayApplicationDefinition:
    """One code-owned application release: the exact bytes it is admitted by and what the application adds to them.

    Adding one is a reviewed code change together with the record's entry in `APPROVED_ACTUAL_RELEASES`.
    """

    record: bytes  # the frozen ACTUAL release record (relay CONTRACT A6)
    record_sha256: str
    price_snapshot: bytes  # the provider price the record names by `price_snapshot_sha256`
    response_format: Mapping[str, Any] | None  # the output schema the record names by `response_format_sha256`
    image: str  # the pinned Hermes job image by its Docker image id `sha256:<64 hex>`, the id the operator launches
    channel_root: str  # this application's job channel under the relay
    global_cap_usd: Decimal  # every owner together
    owner_cap_usd: Decimal  # each owner on their own


# Empty: no release is approved. Every actual value is still an input of a later qualification packet.
RELEASE_DEFINITIONS: tuple[RelayApplicationDefinition, ...] = ()


@dataclass(frozen=True)
class HermesApplicationRelease:
    """Everything one application serves, bound to one approved record. Built only by `bind_release`."""

    actual: ActualRelease
    approval_sha256: str
    price_snapshot_sha256: str
    price: TokenPrice  # the one instance the ledger and the relay runner both use
    route: TransportRoute
    policy: GuardPolicy
    config: HermesInterpreterConfig
    image: str
    channel_root: str
    limits: SpendLimits
    required_extra_sha256: str  # the policy's request shape when bound; checked again before anything is built

    def unchanged(self) -> bool:
        """The owned request shape is still exactly the bound one and still the record's."""
        required = self.policy.required_extra
        return (hmac.compare_digest(hashlib.sha256(_canonical(required)).hexdigest(), self.required_extra_sha256)
                and _canonical(required["provider"]) == _canonical(self.actual.provider)
                and _canonical(required.get("reasoning")) == _canonical(self.actual.reasoning)
                and _canonical(required.get("prompt_cache_options")) == _canonical(self.actual.prompt_cache_options))


class _Refused(MountRefused):
    """The definition does not bind one consistent release. Nothing was built."""


def _strict_object(raw: bytes, label: str) -> dict[str, Any]:
    def no_repeats(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key is repeated")
        return dict(pairs)

    def no_constant(name: str) -> Any:
        raise ValueError(f"{name} is not allowed")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_repeats, parse_constant=no_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise _Refused(f"the {label} is not strict JSON") from error
    if not isinstance(value, dict):
        raise _Refused(f"the {label} must be one JSON object")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _owned(value: Any) -> Any:
    """A copy that shares no object with the record or the definition, so a later change there cannot reach it."""
    return json.loads(_canonical(value))


def _rate(snapshot: Mapping[str, Any], name: str, ceiling: Any) -> Decimal:
    """A snapshot rate: a positive plain decimal string, at most the routing `max_price` for the same tokens."""
    value = snapshot[name]
    if not isinstance(value, str) or not DECIMAL.fullmatch(value) or Decimal(value) <= 0:
        raise _Refused(f"{name} must be a positive plain decimal string")
    if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float, str)):
        raise _Refused("routing max_price must give a number for prompt and completion")
    try:
        limit = Decimal(str(ceiling))
    except InvalidOperation as error:
        raise _Refused("routing max_price must give a number for prompt and completion") from error
    if not limit.is_finite() or Decimal(value) > limit:
        raise _Refused(f"{name} is above the routing max_price")
    return Decimal(value)


def _price(definition: RelayApplicationDefinition, actual: ActualRelease, expected_sha256: str) -> TokenPrice:
    """The snapshot's price, only if its bytes are the ones the record names and it prices the record's model."""
    if not hmac.compare_digest(hashlib.sha256(definition.price_snapshot).hexdigest(), expected_sha256):
        raise _Refused("the price snapshot bytes are not the ones the release record names")
    snapshot = _strict_object(definition.price_snapshot, "price snapshot")
    if set(snapshot) != SNAPSHOT_FIELDS:
        raise _Refused("the price snapshot must have exactly the frozen fields")
    if snapshot["model"] != actual.release.model or snapshot["provider"] != actual.provider["only"][0]:
        raise _Refused("the price snapshot must price the record's model at its one routed provider")
    ceiling = actual.provider["max_price"]
    return TokenPrice(_rate(snapshot, "prompt_usd_per_million", ceiling.get("prompt")),
                      _rate(snapshot, "completion_usd_per_million", ceiling.get("completion")))


def bind_release(definition: RelayApplicationDefinition) -> HermesApplicationRelease:
    """The one release this definition serves. Pure: reads nothing but the definition. Raises `MountRefused`.

    The record must be in the relay's trusted registry (`load_actual_release` with no override). Its approval and price
    snapshot hashes, which `ActualRelease` does not keep, are read again from the same accepted bytes.
    """
    try:
        actual = load_actual_release(definition.record, definition.record_sha256)
    except ValueError as error:  # includes ActualReleaseUnapproved
        raise _Refused(f"the release record is refused: {type(error).__name__}") from error
    record = _strict_object(definition.record, "release record")
    price = _price(definition, actual, record["price_snapshot_sha256"])
    extra: dict[str, Any] = {"stream": False, "provider": _owned(actual.provider)}
    if actual.reasoning is not None:
        extra["reasoning"] = _owned(actual.reasoning)
    if actual.prompt_cache_options is not None:
        extra["prompt_cache_options"] = _owned(actual.prompt_cache_options)
    if "response_format" in actual.allowed_fields:
        schema = definition.response_format
        if not isinstance(schema, Mapping) or not hmac.compare_digest(
                hashlib.sha256(_canonical(schema)).hexdigest(), actual.response_format_sha256):
            raise _Refused("the output schema is not the one the release record names")
        extra["response_format"] = _owned(schema)
    elif definition.response_format is not None:
        raise _Refused("the release record sends no output schema, so the definition names none")
    if not isinstance(definition.image, str) or not IMAGE_ID.fullmatch(definition.image):
        raise _Refused("the job image must be named by its Docker image id (sha256:<64 hex>), not a tag or a registry "
                       "digest reference")
    channel = definition.channel_root
    if not isinstance(channel, str) or not relay_admission.IDENTIFIER.fullmatch(channel):
        raise _Refused("the channel root must be 1-64 letters, digits or ._:-")
    release = actual.release
    limits = SpendLimits(global_cap_usd=definition.global_cap_usd, owner_cap_usd=definition.owner_cap_usd, price=price)
    approval = record["approval"]
    config = HermesInterpreterConfig(
        model=release.model, route=release.route_id, max_output_tokens=release.max_output_tokens, runtime_label="LIVE",
        live_release=LiveRelease(release_id=release.release_id, provider=actual.provider["only"][0],
                                 model=release.model, budget_usd=str(definition.global_cap_usd),
                                 recorded_in=approval["path"]))
    return HermesApplicationRelease(
        actual=actual, approval_sha256=approval["sha256"], price_snapshot_sha256=record["price_snapshot_sha256"],
        price=price, route=TransportRoute(release.route_id, "ACTUAL", actual.endpoint_url, release.max_reply_bytes),
        policy=GuardPolicy(model=release.model, max_output_tokens=release.max_output_tokens,
                           max_request_bytes=release.max_request_bytes,
                           max_envelope_chars=DEFAULT_POLICY.max_envelope_chars, required_extra=extra),
        config=config, image=definition.image, channel_root=definition.channel_root, limits=limits,
        required_extra_sha256=hashlib.sha256(_canonical(extra)).hexdigest())


@dataclass
class HermesApplication:
    release: HermesApplicationRelease
    runner: HermesTurnRunner
    supervision: GuardedDockerTurnRunner
    spend: PostgresSpendLedger
    engine: Engine
    startup_recovery: list[dict[str, Any]] = field(default_factory=list)

    @property
    def config(self) -> HermesInterpreterConfig:
        return self.release.config

    def close(self) -> None:
        self.engine.dispose()


def _saved_attempt(connection: Any, attempt_id: str) -> tuple[Any, Any]:
    return tuple(connection.execute(text(
        "SELECT owner_id, intake_record_id FROM interpretation_attempts WHERE attempt_id = :a"),
        {"a": uuid.UUID(attempt_id)}).one())  # raises: no reservation, no grant, nothing sent


def _intake_scope(engine: Engine) -> Callable[[HermesTurn], str]:
    """One open liability per saved request: the scope is the saved request of the recorded attempt."""
    def scope_for(turn: HermesTurn) -> str:
        with engine.connect() as connection:
            return f"intake:{_saved_attempt(connection, turn.attempt_id)[1]}"
    return scope_for


def _subject(engine: Engine) -> Callable[[HermesTurn], RelaySubject]:
    """The saved attempt's owner and request, required to equal what its RESERVED reservation copied from that row."""
    def subject_for(turn: HermesTurn) -> RelaySubject:
        with engine.connect() as connection:
            owner, intake = _saved_attempt(connection, turn.attempt_id)
            reserved = connection.execute(text(
                "SELECT owner_id, intake_record_id, scope, state FROM usage_local.provider_spend_reservations "
                "WHERE attempt_id = :a"), {"a": uuid.UUID(turn.attempt_id)}).one()
        if tuple(map(str, reserved)) != (str(owner), str(intake), f"intake:{intake}", "RESERVED"):
            raise LookupError("the reservation does not belong to this attempt's owner and saved request")
        return RelaySubject(str(owner), str(intake))
    return subject_for


def compose_application(release: HermesApplicationRelease, engine: Engine, *, endpoint: RelayEndpoint, run_id: str,
                        evidence_dir: Path, run_budget_seconds: int = 60, seal_grace_seconds: float = 5.0,
                        recovery_budget_seconds: float = 5.0, close_budget_seconds: float = 2.0) -> HermesApplication:
    """The composition over an opened engine. No I/O: nothing is read, written or started."""
    if not release.unchanged():
        raise _Refused("the bound request shape changed after it was checked")
    if endpoint.channel_root != release.channel_root:
        raise _Refused("the relay endpoint must serve this release's channel root")
    if not isinstance(run_id, str) or not relay_admission.IDENTIFIER.fullmatch(run_id):
        raise _Refused("run_id must be 1-64 letters, digits or ._:-")
    spend = PostgresSpendLedger(make_session_factory(engine), release.limits)
    job = build_relay_job(release.route, release=release.actual.release, endpoint=endpoint,
                          subject_for=_subject(engine), policy=release.policy, ledger=spend,
                          scope_for=_intake_scope(engine), image=release.image, run_id=run_id,
                          evidence_dir=evidence_dir, script_for=lambda turn: {},
                          timeout_seconds=release.actual.timeout_seconds, run_budget_seconds=run_budget_seconds,
                          seal_grace_seconds=seal_grace_seconds, recovery_budget_seconds=recovery_budget_seconds,
                          close_budget_seconds=close_budget_seconds, actual=release.actual, price=release.price)
    return HermesApplication(release, job.runner, job.supervision, spend, engine)


def _approved_definition() -> RelayApplicationDefinition | None:
    approved = [item for item in RELEASE_DEFINITIONS if item.record_sha256 in relay_admission.APPROVED_ACTUAL_RELEASES]
    if len(approved) > 1:
        raise _Refused("an application serves at most one approved release")
    return approved[0] if approved else None


def _read_bounded(path: Path) -> bytes:
    """The handoff file's bytes: a regular file, not followed through a link, at most MAX_HANDOFF_BYTES."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (OSError, TypeError, ValueError) as error:
        raise _Refused("the operator handoff cannot be opened") from error
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _Refused("the operator handoff must be a regular file")
        data = os.read(fd, MAX_HANDOFF_BYTES + 1)
    except OSError as error:
        raise _Refused("the operator handoff cannot be read") from error
    finally:
        os.close(fd)
    if len(data) > MAX_HANDOFF_BYTES:
        raise _Refused("the operator handoff is too large")
    return data


def _absolute(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        raise _Refused(f"the operator handoff {label} must be an absolute path")
    return Path(value)


def _handoff(path: Path, expected_sha256: str, release: HermesApplicationRelease) -> tuple[RelayEndpoint, Path]:
    """The relay endpoint and job evidence folder the operator started for exactly this release.

    The handoff (`edge-os.relay-operator-handoff/1`, written once by the lane-1 operator) approves nothing: the release
    comes only from the code-owned definition. Every identity in it must equal the bound release's; its record path is
    never read, because the approved record bytes are the definition's own.
    """
    raw = _read_bounded(path)
    if not isinstance(expected_sha256, str) or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),
                                                                      expected_sha256):
        raise _Refused("the operator handoff bytes do not have the named hash")
    handoff = _strict_object(raw, "operator handoff")
    if set(handoff) != HANDOFF_FIELDS or handoff["format"] != HANDOFF_FORMAT:
        raise _Refused("the operator handoff must have exactly the frozen fields and format")
    actual = release.actual
    record = handoff["release_record"]
    if (handoff["kind"] != "ACTUAL" or handoff["release"] != actual.release.settings()
            or not isinstance(record, dict) or set(record) != {"path", "sha256"}
            or record["sha256"] != actual.record_sha256 or handoff["ca_bundle_sha256"] != actual.ca_bundle_sha256):
        raise _Refused("the operator handoff is not for this release record, release and CA bundle")
    image = handoff["image"]
    if (not isinstance(image, dict) or set(image) != {"reference", "id"} or not isinstance(image["reference"], str)
            or not IMAGE_REFERENCE.fullmatch(image["reference"]) or image["id"] != release.image):
        raise _Refused("the operator handoff must start this release's exact Docker image id")
    if handoff["shutdown_owner"] != "relay_operator":
        raise _Refused("the relay operator must own shutdown; this application never stops the relay")
    given = handoff["endpoint"]
    if not isinstance(given, dict) or set(given) != ENDPOINT_FIELDS:
        raise _Refused("the operator handoff endpoint must have exactly the frozen fields")
    age = given["heartbeat_max_age_seconds"]
    if isinstance(age, bool) or not isinstance(age, (int, float)) or not 0 < age <= MAX_HEARTBEAT_AGE_SECONDS:
        raise _Refused("the heartbeat age bound must be a number above 0 and at most 10 seconds")
    endpoint = RelayEndpoint(*(_absolute(given[name], name) for name in (
        "grants", "revocations", "state", "admission_key_file")), given["channel_root"], float(age))
    if endpoint.channel_root != release.channel_root:
        raise _Refused("the relay endpoint must serve this release's channel root")
    return endpoint, _absolute(handoff["evidence_dir"], "evidence_dir")


def open_hermes_application(settings: Settings, *, handoff_path: Path, handoff_sha256: str, run_id: str,
                            run_budget_seconds: int = 60, seal_grace_seconds: float = 5.0,
                            recovery_budget_seconds: float = 5.0,
                            close_budget_seconds: float = 2.0) -> HermesApplication | None:
    """The approved application release, opened, or None when none is approved. Raises `MountRefused` before any effect.

    `handoff_path` and `handoff_sha256` are the line the relay operator printed at start, given by the application's
    trusted configuration owner. The handoff is read only after an approved definition is found, and it is never
    written. Each API process uses its own stable `run_id`; a restarted process reuses it to recover its dead turns.
    The application never stops, restarts or removes relay resources: `close` disposes only its own engine.
    """
    if settings.env == "production":
        raise MountRefused("the Hermes relay application is refused in production until its deployment is qualified")
    if settings.interpreter != "hermes_local":
        raise MountRefused("the Hermes relay application needs EDGE_OS_INTERPRETER=hermes_local")
    definition = _approved_definition()
    if definition is None:
        return None
    release = bind_release(definition)
    endpoint, evidence_dir = _handoff(handoff_path, handoff_sha256, release)
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    try:
        require_head(engine)
        app = compose_application(release, engine, endpoint=endpoint, run_id=run_id, evidence_dir=evidence_dir,
                                  run_budget_seconds=run_budget_seconds, seal_grace_seconds=seal_grace_seconds,
                                  recovery_budget_seconds=recovery_budget_seconds,
                                  close_budget_seconds=close_budget_seconds)
        app.startup_recovery = app.supervision.recover_pending(recovery_budget_seconds)
    except BaseException:
        engine.dispose()
        raise
    return app
