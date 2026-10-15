"""Forward history recorder: fixed-schedule P0-P5 reads, durable admissions and one immutable handoff.

The recorder implements the LOCAL design adopted for the qualified demo (D2, D3 and D11 in the private builder
authority) against the predecessor read packet ``SOURCE_FACT_PACKET.json`` (sha256 c4fc01c4...). Its contract,
mechanical amendments and claim limits are in ``docs/qualification/forward-history-recorder/CONTRACT.md``.

A plain CLI invocation validates an input and prints a redacted plan; it reads no credential and sends nothing.
Network execution exists only as the injected ``run_attempt`` entry: the caller supplies the transport, the clocks and
the credential source. This ticket authorizes synthetic transports only. P6 (mechanics) is never called here.

Safety stops end every provider. Other failed reads stay weak evidence and are never retried. Every physical call is
appended to a private journal with UNKNOWN liability and fsynced before it is sent; an existing attempt is never
executed again.
"""

from __future__ import annotations

import argparse
import calendar
import functools
import hashlib
import inspect
import json
import math
import os
import re
import stat
import sys
import time
import weakref
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import edge_os_api.research_history.http_clients.http_transport as stdlib_transport_module
from edge_os_api.records.contract_adapter import canonical_bytes
from edge_os_api.research_history.http_clients.client_config import (
    ClientBounds,
    ClientConfigError,
    HttpProviderError,
    validate_endpoint,
)
from edge_os_api.research_history.http_clients.envio_query_client import BLOCK_FIELD_SELECTION, LOG_FIELD_SELECTION
from edge_os_api.research_history.http_clients.http_transport import (
    HttpResponse,
    HttpTransport,
    StdlibHttpTransport,
    decode_json_reply,
    refuse_provider_status,
)
from edge_os_api.research_history.http_clients.quicknode_rpc_client import HttpQuickNodeRpcClient
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceTimeout
from edge_os_api.research_history.qualification_engine import iso_utc
from scripts.history_payload_binding import (
    CANONICALIZATION_VERSION,
    HANDOFF_SCHEMA,
    PayloadError,
    bucket_members,
    canonical_payload,
    hex_value,
    project_log,
    quantity,
    read_bounded,
    strict_json,
    write_exclusive,
)

INPUT_SCHEMA = "edge-os.forward-history-input/1"
TRANSPORT_RECEIPTS_SCHEMA = "edge-os.forward-history-transport-receipts/1"
TRANSPORT_RECEIPTS_FILE = "transport-receipts.json"
PREDECESSOR_SHA256 = "c4fc01c4d498742cd9a904606135fdb2b27fea448bb254462a79a9f67824312f"
DECODER_VERSION = "retained-v2-pair-created/1"
CHAIN_ID = 143
SWAP_TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
SELECTORS = {"decimals": "0x313ce567", "token0": "0x0dfe1681", "token1": "0xd21220a7", "factory": "0xc45a0155"}
WINDOW_SECONDS = 1200
BUCKET_SECONDS = 300
BUCKET_COUNT = 4
QUICKNODE_METHODS = frozenset({"eth_chainId", "eth_getTransactionReceipt", "eth_call", "eth_getCode",
                               "eth_getBlockByNumber"})
PHASE_LIMITS = {"P1": {"quicknode": 6, "hypersync": 1}, "P2": {"quicknode": 1}, "P3": {"hypersync": 8},
                "P4": {"quicknode": 4}, "P5": {"quicknode": 6}}
PROVIDER_LIMITS = {"quicknode": 17, "hypersync": 9}
MAX_REQUEST_BYTES = 65_536
MAX_REPLY_BYTES = 2_097_152
MAX_TOTAL_REPLY_BYTES = 67_108_864
MAX_CALL_SECONDS = 120.0
MAX_CONNECT_SECONDS = 15.0
PACING_SECONDS = 1.0
MAX_BLOCKS_PER_PAGE = 10_000
MAX_INPUT_BYTES = 65_536
MAX_JOURNAL_BYTES = 4 * 1024 * 1024
FIRST_READ_OFFSET = 30
SECOND_READ_OFFSET = 120
P2_EARLIEST, P2_CUTOFF = 120, 5
LATE_PHASE_SECONDS = 3600
SCAN_LOG_LIMIT = 61
QUOTA_SIGNALS = (b"quota", b"rate limit", b"rate-limit", b"ratelimit", b"too many requests", b"request limit",
                 b"requests limit", b"payment",
                 b"billing", b"insufficient credit", b"credits exhausted")
SAFETY_CODES = frozenset({"AUTH_DENIED", "PAYMENT_REQUIRED", "RATE_LIMITED"})
_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_HOST = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*")


class RecorderInputError(ValueError):
    """The frozen input is invalid. Raised before any credential read or transport use."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AttemptExists(RuntimeError):
    """The attempt path already exists. A network attempt is never executed twice."""


class AdmissionRefused(RuntimeError):
    """A call was refused before admission: nothing was sent and no liability was added."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SafetyStop(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CredentialIncident(SafetyStop):
    def __init__(self) -> None:
        super().__init__("CREDENTIAL_INCIDENT")


class ClockUntrusted(Exception):
    pass


class EvidenceWriteFailed(Exception):
    pass


class RecorderClock(Protocol):
    def utc(self) -> float: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def utc(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


# Input validation and plan


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RecorderInputError(code)


def _address(value: Any, code: str) -> str:
    try:
        return hex_value(value, 20, code).lower()
    except PayloadError as error:
        raise RecorderInputError(code) from error


def _word32(value: Any, code: str) -> str:
    try:
        return hex_value(value, 32, code)
    except PayloadError as error:
        raise RecorderInputError(code) from error


def _ref(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256


_INPUT_KEYS = {"schema_version", "predecessor_sha256", "attempt_id", "source_id", "evidence_class", "chain_id",
               "pool", "token0", "token1", "base", "quote", "swap_topic0", "selectors", "expected_decimals",
               "creation", "t0_utc", "window_seconds", "bucket_seconds", "destinations", "credential_slots",
               "output_dir", "decisions", "plans", "p6"}


def validate_input(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate every frozen value, limit and schedule. Returns a normalized copy. Never reads credentials."""
    _require(isinstance(raw, Mapping) and set(raw) == _INPUT_KEYS, "INPUT_KEYS")
    _require(raw["schema_version"] == INPUT_SCHEMA, "INPUT_SCHEMA")
    _require(raw["predecessor_sha256"] == PREDECESSOR_SHA256, "PREDECESSOR_SHA256")
    _require(isinstance(raw["attempt_id"], str) and _ATTEMPT_ID.fullmatch(raw["attempt_id"]) is not None,
             "ATTEMPT_ID")
    _require(_ref(raw["source_id"]), "SOURCE_ID")
    _require(raw["evidence_class"] in ("SYNTHETIC", "ACTUAL"), "EVIDENCE_CLASS")
    _require(raw["chain_id"] == CHAIN_ID and not isinstance(raw["chain_id"], bool), "CHAIN_ID")
    pool, token0, token1 = (_address(raw[key], key.upper()) for key in ("pool", "token0", "token1"))
    _require(len({pool, token0, token1}) == 3, "MARKET_ADDRESSES")
    base, quote = _address(raw["base"], "BASE"), _address(raw["quote"], "QUOTE")
    _require({base, quote} == {token0, token1}, "BASE_QUOTE")
    _require(raw["swap_topic0"] == SWAP_TOPIC0, "SWAP_TOPIC0")
    _require(raw["selectors"] == SELECTORS, "SELECTORS")
    decimals = raw["expected_decimals"]
    _require(isinstance(decimals, Mapping) and set(decimals) == {"token0", "token1"}
             and all(type(value) is int and 0 <= value <= 77 for value in decimals.values()), "EXPECTED_DECIMALS")
    creation = raw["creation"]
    _require(isinstance(creation, Mapping) and set(creation) == {"decoder", "transaction_hash", "block_number",
                                                                 "block_hash", "transaction_index", "log_index",
                                                                 "factory", "topic0"}, "CREATION_KEYS")
    _require(creation["decoder"] == DECODER_VERSION, "CREATION_DECODER")
    normalized_creation = {
        "transaction_hash": _word32(creation["transaction_hash"], "CREATION_TX"),
        "block_hash": _word32(creation["block_hash"], "CREATION_BLOCK_HASH"),
        "topic0": _word32(creation["topic0"], "CREATION_TOPIC0"),
        "factory": _address(creation["factory"], "CREATION_FACTORY"),
    }
    for key in ("block_number", "transaction_index", "log_index"):
        _require(type(creation[key]) is int and creation[key] >= 0, f"CREATION_{key.upper()}")
        normalized_creation[key] = creation[key]
    _require(isinstance(raw["t0_utc"], str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", raw["t0_utc"])
             is not None, "T0_FORMAT")
    try:
        t0 = calendar.timegm(time.strptime(raw["t0_utc"], "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError as error:
        raise RecorderInputError("T0_FORMAT") from error
    _require(t0 % BUCKET_SECONDS == 0, "T0_GRID")
    _require(raw["window_seconds"] == WINDOW_SECONDS and raw["bucket_seconds"] == BUCKET_SECONDS, "WINDOW_SHAPE")
    destinations = raw["destinations"]
    _require(isinstance(destinations, Mapping) and set(destinations) == {"quicknode_host", "hypersync_url"},
             "DESTINATIONS")
    host = destinations["quicknode_host"]
    _require(isinstance(host, str) and _HOST.fullmatch(host) is not None, "QUICKNODE_HOST")
    hypersync = destinations["hypersync_url"]
    try:
        validate_endpoint(hypersync)
        parts = urlsplit(hypersync)
    except ClientConfigError as error:
        raise RecorderInputError("HYPERSYNC_URL") from error
    _require(parts.scheme == "https" and parts.path == "/query" and not parts.query, "HYPERSYNC_URL")
    slots = raw["credential_slots"]
    _require(isinstance(slots, Mapping) and set(slots) == {"quicknode", "hypersync"}
             and all(_ref(value) for value in slots.values()), "CREDENTIAL_SLOTS")
    output = raw["output_dir"]
    _require(isinstance(output, str) and os.path.isabs(output), "OUTPUT_DIR")
    try:
        mode = os.lstat(output).st_mode
    except OSError as error:
        raise RecorderInputError("OUTPUT_DIR") from error
    _require(stat.S_ISDIR(mode) and not stat.S_ISLNK(mode), "OUTPUT_DIR")
    for key in ("decisions", "plans", "p6"):
        _require(isinstance(raw[key], Mapping), key.upper())
    _require(set(raw["decisions"]) == {"D1", "D2", "D3"}, "DECISIONS")
    _require(set(raw["plans"]) == {"quicknode", "hypersync"}, "PLANS")
    p6 = raw["p6"]
    _require(set(p6) == {"status", "destination_ref", "evidence_refs"}
             and p6["status"] == "EXTERNAL_EVIDENCE_REQUIRED" and isinstance(p6["evidence_refs"], list), "P6")
    return {**{key: raw[key] for key in ("attempt_id", "source_id", "evidence_class", "t0_utc", "decisions",
                                         "plans", "p6", "credential_slots")},
            "pool": pool, "token0": token0, "token1": token1, "base": base, "quote": quote,
            "expected_decimals": dict(decimals), "creation": normalized_creation, "t0": t0,
            "window_end": t0 + WINDOW_SECONDS, "quicknode_host": host, "hypersync_url": hypersync,
            "output_dir": output}


def readiness_gaps(value: Mapping[str, Any]) -> list[str]:
    """Original P0 prerequisites. Any gap keeps the attempt NOT_READY with zero calls."""
    gaps = [f"DECISION_{key}" for key, ref in sorted(value["decisions"].items()) if not _ref(ref)]
    gaps += [f"PLAN_{key.upper()}" for key, ref in sorted(value["plans"].items()) if not _ref(ref)]
    if not _ref(value["p6"]["destination_ref"]):
        gaps.append("P6_DESTINATION")
    return gaps


def p3_events(t0: int) -> list[tuple[int, str, int]]:
    events = []
    for index in range(BUCKET_COUNT):
        end = t0 + BUCKET_SECONDS * (index + 1)
        events.append((index, "first", end + FIRST_READ_OFFSET))
        events.append((index, "second", end + SECOND_READ_OFFSET))
    return events


def plan(value: Mapping[str, Any]) -> dict[str, Any]:
    t0 = value["t0"]
    slots = [{"bucket": index, "first": iso_utc(t0 + 300 * (index + 1) + FIRST_READ_OFFSET),
              "second": iso_utc(t0 + 300 * (index + 1) + SECOND_READ_OFFSET)} for index in range(BUCKET_COUNT)]
    return {"schema_version": INPUT_SCHEMA, "attempt_id": value["attempt_id"], "t0_utc": value["t0_utc"],
            "window_end_utc": iso_utc(value["window_end"]), "readiness_gaps": readiness_gaps(value),
            "calls_max": {**PROVIDER_LIMITS, "total": sum(PROVIDER_LIMITS.values())},
            "phase_limits": PHASE_LIMITS, "p2_window_utc": [iso_utc(t0 - P2_EARLIEST), iso_utc(t0 - P2_CUTOFF)],
            "p3_admission_slots_utc": slots, "p3_admission_rule": "[due, due+1s), no catch-up",
            "p5_window_utc": [iso_utc(value["window_end"] + 60), iso_utc(value["window_end"] + LATE_PHASE_SECONDS)],
            "quicknode_host": value["quicknode_host"], "hypersync_url": value["hypersync_url"],
            "credential_slots": value["credential_slots"], "p6": "EXTERNAL_EVIDENCE_REQUIRED", "sends": 0}


# Transport construction identity
#
# Only the two construction functions below record a construction, with the exact attributes they created. Any other
# object, including a caller's own StdlibHttpTransport, a subclass, a wrapper or an object that advertises ACTUAL, is
# INJECTED. Construction facts never come from input JSON or from a label on the transport.

_STDLIB_NAME = f"{StdlibHttpTransport.__module__}.{StdlibHttpTransport.__qualname__}"
_STDLIB_SHA256 = hashlib.sha256(Path(stdlib_transport_module.__file__).read_bytes()).hexdigest()
_STDLIB_CLASS = dict(vars(StdlibHttpTransport))
# The accepted constructor inputs, bound at import so a later change to the constructor defaults cannot reach them.
_DEFAULT_CONNECT = stdlib_transport_module._default_connect
_CONSTRUCTED: weakref.WeakKeyDictionary[StdlibHttpTransport, tuple[str, dict[str, Any]]] = (
    weakref.WeakKeyDictionary())


def owned_stdlib_transport() -> StdlibHttpTransport:
    """The recorder-owned construction of the accepted network transport: defaults only, real sockets."""
    return _construct("OWNED_STDLIB", StdlibHttpTransport(connect=_DEFAULT_CONNECT, clock=time.monotonic))


def local_fixture_transport(connect: Callable[..., object], clock: Callable[[], float]) -> StdlibHttpTransport:
    """The real stdlib transport over a fixture connector and clock. Its evidence is a LOCAL_FIXTURE receipt."""
    return _construct("LOCAL_FIXTURE", StdlibHttpTransport(connect=connect, clock=clock))


def _construct(construction: str, transport: StdlibHttpTransport) -> StdlibHttpTransport:
    _CONSTRUCTED[transport] = (construction, dict(vars(transport)))
    return transport


def _same_objects(live: Mapping[str, Any], recorded: Mapping[str, Any]) -> bool:
    return live.keys() == recorded.keys() and all(live[key] is value for key, value in recorded.items())


def _recorded_construction(transport: object) -> str | None:
    """The construction of an exact, unmodified owned or fixture transport, else None."""
    if type(transport) is not StdlibHttpTransport or not _same_objects(vars(StdlibHttpTransport), _STDLIB_CLASS):
        return None
    record = _CONSTRUCTED.get(transport)
    if record is None or not _same_objects(vars(transport), record[1]):
        return None
    return record[0]


def transport_identity(transport: object) -> dict[str, Any]:
    """The canonical transport object of a receipt sidecar."""
    construction = _recorded_construction(transport)
    if construction is None:
        return {"construction": "INJECTED", "implementation": None, "implementation_sha256": None}
    return {"construction": construction, "implementation": _STDLIB_NAME, "implementation_sha256": _STDLIB_SHA256}


class _TransportBinding:
    """Binds the transport identity to the request method before every send; any later substitution is refused."""

    def __init__(self, transport: HttpTransport) -> None:
        self.identity = transport_identity(transport)
        self.sha256 = hashlib.sha256(canonical_bytes(self.identity)).hexdigest()
        self._transport = transport
        self._construction = self.identity["construction"]
        try:
            # A recorded construction altered before binding keeps no identity and is never used.
            self._altered = self._construction == "INJECTED" and transport in _CONSTRUCTED
        except TypeError:
            self._altered = False
        if self._construction == "INJECTED":
            self._methods = self._injected_methods()
            self._send: Callable[..., HttpResponse] = transport.request
        else:
            self._send = functools.partial(_STDLIB_CLASS["request"], transport)

    def _injected_methods(self) -> tuple[Any, ...]:
        kind = type(self._transport)
        return kind, inspect.getattr_static(kind, "request", None), getattr(self._transport, "__dict__", {}).get(
            "request")

    def verified_send(self) -> Callable[..., HttpResponse]:
        if self._construction == "INJECTED":
            unchanged = not self._altered and all(
                live is bound for live, bound in zip(self._injected_methods(), self._methods, strict=True))
        else:
            unchanged = _recorded_construction(self._transport) == self._construction
        if not unchanged:
            raise AdmissionRefused("TRANSPORT_SUBSTITUTED")
        return self._send


# Private journal and recording transport


def _private_dir(path: Path) -> None:
    os.mkdir(path, 0o700)
    os.chmod(path, 0o700)


class AttemptJournal:
    """Append-only, fsynced attempt log. Its records, not a client counter, control every ceiling."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "journal.jsonl"
        self.counts: dict[tuple[str, str], int] = {}
        self.provider_counts: dict[str, int] = {}
        self.resolved = 0
        self.reply_bytes = 0
        self.last_admission: dict[str, float] = {}
        self.sequence = 0
        self.calls: dict[str, dict[str, Any]] = {}

    @classmethod
    def create(cls, directory: Path) -> AttemptJournal:
        try:
            _private_dir(directory)
        except FileExistsError as error:
            raise AttemptExists(directory.name) from error
        _private_dir(directory / "bodies")
        journal = cls(directory)
        descriptor = os.open(journal.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        return journal

    def append(self, record: Mapping[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as error:
            raise EvidenceWriteFailed("JOURNAL") from error

    def admitted(self, provider: str) -> int:
        return self.provider_counts.get(provider, 0)

    def save_body(self, call_id: str, body: bytes) -> None:
        try:
            write_exclusive(self.directory / "bodies" / f"{call_id}.bin", body)
        except OSError as error:
            raise EvidenceWriteFailed("BODY") from error


class RecordingTransport:
    """Admission, durable liability, body receipt, redaction and private audit around the injected transport."""

    def __init__(self, inner: HttpTransport, journal: AttemptJournal, clock: RecorderClock, *, quicknode_url: str,
                 hypersync_url: str, secrets: Sequence[str]) -> None:
        self._binding = _TransportBinding(inner)
        self._receipts: dict[str, dict[str, Any]] = {}
        self._journal = journal
        self._clock = clock
        self._urls = {"quicknode": quicknode_url, "hypersync": hypersync_url}
        self._secrets = tuple(secret for secret in secrets if secret)
        self._label = ("", "", "")
        self._admission_end_utc: float | None = None
        self.last_receipt: dict[str, Any] | None = None
        self.stopped: str | None = None
        self._seen = (clock.utc(), clock.monotonic())

    def label(self, *, phase: str, slot: str, provider: str, admission_end_utc: float | None = None) -> None:
        """Name the next call. `admission_end_utc` closes a fixed P3 admission slot at the durable boundary."""
        self._label = (phase, slot, provider)
        self._admission_end_utc = admission_end_utc

    def observe(self) -> tuple[float, float]:
        utc, mono = self._clock.utc(), self._clock.monotonic()
        if utc < self._seen[0] or mono < self._seen[1]:
            raise ClockUntrusted()
        self._seen = (utc, mono)
        return utc, mono

    def leaks(self, data: bytes) -> bool:
        return any(secret.encode() in data for secret in self._secrets)

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float,
                deadline: float, max_response_bytes: int, cancel: Callable[[], bool] | None = None) -> HttpResponse:
        phase, slot, provider = self._label
        journal = self._journal
        if self.stopped is not None:
            raise AdmissionRefused("STOPPED")
        if cancel is not None and cancel():
            raise AdmissionRefused("CANCELLED")
        if provider not in self._urls or url != self._urls[provider]:
            raise AdmissionRefused("UNLISTED_DESTINATION")
        if journal.counts.get((phase, provider), 0) >= PHASE_LIMITS.get(phase, {}).get(provider, 0):
            raise AdmissionRefused("PHASE_CEILING")
        if journal.admitted(provider) >= PROVIDER_LIMITS[provider]:
            raise AdmissionRefused("PROVIDER_CEILING")
        if len(body) > MAX_REQUEST_BYTES:
            raise AdmissionRefused("REQUEST_TOO_LARGE")
        reply_cap = min(max_response_bytes, MAX_REPLY_BYTES)
        if journal.reply_bytes + reply_cap > MAX_TOTAL_REPLY_BYTES:
            raise AdmissionRefused("AGGREGATE_REPLY_BUDGET")
        send = self._binding.verified_send()
        utc, mono = self.observe()
        if self._admission_end_utc is not None and utc >= self._admission_end_utc:
            raise AdmissionRefused("SLOT_CLOSED")
        if mono >= deadline:
            raise AdmissionRefused("DEADLINE")
        last = journal.last_admission.get(provider)
        if last is not None and mono - last < PACING_SECONDS:
            raise AdmissionRefused("PACING")
        journal.sequence += 1
        call_id = f"{journal.sequence:02d}-{phase}-{provider}"
        journal.append({"event": "ADMITTED", "call_id": call_id, "phase": phase, "slot": slot, "provider": provider,
                        "request_sha256": hashlib.sha256(body).hexdigest(), "request_bytes": len(body),
                        "admitted_utc_us": int(utc * 1_000_000), "admitted_monotonic": mono,
                        "deadline_monotonic": deadline, "liability": "UNKNOWN"})
        journal.calls[call_id] = {"call_id": call_id, "phase": phase, "slot": slot, "provider": provider,
                                  "request_sha256": hashlib.sha256(body).hexdigest(), "request_bytes": len(body),
                                  "outcome": "UNKNOWN", "status": None, "body_sha256": None, "body_bytes": None}
        receipt = {"call_id": call_id, "transport_binding_sha256": self._binding.sha256,
                   "request_sha256": journal.calls[call_id]["request_sha256"], "outcome": "UNKNOWN", "status": None,
                   "body_sha256": None, "body_bytes": None, "received_at_utc_us": None, "elapsed_us": None}
        self._receipts[call_id] = receipt
        journal.counts[(phase, provider)] = journal.counts.get((phase, provider), 0) + 1
        journal.provider_counts[provider] = journal.admitted(provider) + 1
        journal.last_admission[provider] = mono
        try:
            self._binding.verified_send()  # recheck after the recorder clock readings and the journal write
        except AdmissionRefused:
            self.stopped = "TRANSPORT_SUBSTITUTED"  # admitted but never sent: liability stays UNKNOWN, no resend
            raise
        try:
            response = send(method=method, url=url, headers=headers, body=body,
                            timeout=min(timeout, MAX_CONNECT_SECONDS), deadline=deadline,
                            max_response_bytes=reply_cap, cancel=cancel)
        except BaseException as error:
            if isinstance(error, Exception) and self.leaks(str(error).encode()):
                self._incident(call_id, None)
            raise
        received_utc, received_mono = self._clock.utc(), self._clock.monotonic()
        receipt.update(status=response.status, body_bytes=len(response.body))
        if received_utc >= utc and received_mono >= mono:  # a backward clock leaves the receipt time unknown
            receipt.update(received_at_utc_us=int(received_utc * 1_000_000),
                           elapsed_us=int((received_mono - mono) * 1_000_000))
        header_bytes = json.dumps(dict(response.headers), sort_keys=True).encode()
        if self.leaks(response.body) or self.leaks(header_bytes):
            self._incident(call_id, response.body)
        if len(response.body) > reply_cap:
            journal.append({"event": "RESOLVED", "call_id": call_id, "outcome": "OVERSIZED_REFUSED",
                            "body_bytes": len(response.body)})
            journal.resolved += 1
            journal.calls[call_id].update(outcome="OVERSIZED_REFUSED", status=response.status,
                                          body_bytes=len(response.body))
            receipt["outcome"] = "OVERSIZED_REFUSED"
            raise HttpProviderError("OVERSIZED_RESPONSE", "reply exceeds the recorder reply cap")
        journal.reply_bytes += len(response.body)
        journal.save_body(call_id, response.body)
        journal.append({"event": "RESOLVED", "call_id": call_id, "outcome": "REPLY_RECEIVED",
                        "status": response.status, "body_sha256": hashlib.sha256(response.body).hexdigest(),
                        "body_bytes": len(response.body), "received_utc_us": int(received_utc * 1_000_000),
                        "elapsed_us": int((received_mono - mono) * 1_000_000)})
        journal.resolved += 1
        journal.calls[call_id].update(outcome="REPLY_RECEIVED", status=response.status,
                                      body_sha256=hashlib.sha256(response.body).hexdigest(),
                                      body_bytes=len(response.body))
        receipt.update(outcome="REPLY_RECEIVED", body_sha256=journal.calls[call_id]["body_sha256"])
        self.last_receipt = {"call_id": call_id, "utc": received_utc, "mono": received_mono}
        self.observe()
        lowered = response.body.lower()
        if any(signal in lowered for signal in QUOTA_SIGNALS):
            raise SafetyStop("QUOTA_OR_PAYMENT_SIGNAL")
        return response

    def receipts_document(self, attempt_id: str, handoff_sha256: str) -> dict[str, Any]:
        """The `transport-receipts.json` content: construction facts and receipts captured within this process."""
        return {"schema_version": TRANSPORT_RECEIPTS_SCHEMA, "attempt_id": attempt_id,
                "handoff_sha256": handoff_sha256, "recorder_code_sha256": recorder_code_sha256(),
                "evidence_class": EFFECTIVE_EVIDENCE_CLASS,
                "transport": dict(self._binding.identity),
                "receipts": [dict(receipt) for receipt in self._receipts.values()]}

    def _incident(self, call_id: str, body: bytes | None) -> None:
        self._journal.append({"event": "CREDENTIAL_INCIDENT", "call_id": call_id,
                              "body_sha256": None if body is None else hashlib.sha256(body).hexdigest()})
        self.stopped = "CREDENTIAL_INCIDENT"
        self._journal.calls[call_id]["outcome"] = "CREDENTIAL_INCIDENT"  # no body hash leaves the private journal
        self._receipts[call_id]["outcome"] = "CREDENTIAL_INCIDENT"
        raise CredentialIncident()


# The attempt


def _quantity_or(value: Any) -> int | None:
    try:
        return quantity(value, "value")
    except PayloadError:
        return None


def _word_address(word: Any) -> str | None:
    """A 32-byte ABI word that holds an address: 12 zero bytes then 20 address bytes."""
    if not isinstance(word, str) or len(word) != 66 or not word.startswith("0x"):
        return None
    try:
        hex_value(word, 32, "word")
    except PayloadError:
        return None
    if word[2:26] != "0" * 24:
        return None
    return "0x" + word[26:].lower()


def _header(value: Any) -> tuple[int, int, str] | None:
    if not isinstance(value, Mapping):
        return None
    number, timestamp = _quantity_or(value.get("number")), _quantity_or(value.get("timestamp"))
    try:
        digest = hex_value(value.get("hash"), 32, "hash")
    except PayloadError:
        return None
    if number is None or timestamp is None:
        return None
    return number, timestamp, digest


class _Attempt:
    def __init__(self, value: dict[str, Any], transport: HttpTransport, clock: RecorderClock,
                 credentials: Callable[[str], str], cancel: Callable[[], bool] | None) -> None:
        self.value = value
        self.inner = transport
        self.clock = clock
        self.credentials = credentials
        self.cancel = cancel
        self.t0 = value["t0"]
        self.window_end = value["window_end"]
        self.attempt_deadline = self.window_end + LATE_PHASE_SECONDS
        self.status = "COMPLETED"
        self.stop_reason: str | None = None
        self.phases: dict[str, dict[str, Any]] = {}
        self.facts: dict[str, Any] = {
            "bytecode": {}, "fee_transfer_semantics": "EXTERNAL_EVIDENCE_REQUIRED",
            "decimals": {"window_start": {}, "window_end": {}, "current": {}},
            "finality_at_collection": "NOT_OBSERVED", "archive_height": None, "finalized": None, "latest": None,
            "pair_count": None, "creation_block_timestamp": None,
        }
        self.headers: dict[int, tuple[int, str]] = {}
        self.logs: dict[tuple[int, int, int], dict[str, Any]] = {}
        self.anchor: tuple[int, int, str] | None = None
        self.cursor: int | None = None
        self.buckets = [{"index": index, "start": self.t0 + 300 * index, "end": self.t0 + 300 * (index + 1),
                         "status": "OPEN", "first": None, "delivery": None, "reason": None}
                        for index in range(BUCKET_COUNT)]
        self.p3_replies: list[dict[str, Any]] = []
        self.trusted_clock = True

    # Scheduling helpers

    def _stopped(self) -> bool:
        return self.status != "COMPLETED"

    def _stop(self, status: str, reason: str) -> None:
        if not self._stopped():
            self.status, self.stop_reason = status, reason
            self.wire.stopped = reason

    def _wait_until(self, target: float) -> None:
        now = self.wire.observe()[0]
        if target > now:
            self.clock.sleep(target - now)

    def _pace(self, provider: str) -> None:
        last = self.journal.last_admission.get(provider)
        if last is not None:
            gap = PACING_SECONDS - (self.wire.observe()[1] - last)
            if gap > 0:
                self.clock.sleep(gap)

    def _deadline(self, cutoff_utc: float) -> tuple[float, float]:
        """Earliest of call, phase/schedule and attempt cutoffs, as (monotonic deadline, remaining seconds)."""
        utc, mono = self.wire.observe()
        remaining = min(MAX_CALL_SECONDS, cutoff_utc - utc, self.attempt_deadline - utc)
        return mono + remaining, remaining

    def _rpc(self, phase: str, slot: str, method: str, params: list[Any], cutoff_utc: float) -> Any:
        self._pace("quicknode")
        _, remaining = self._deadline(cutoff_utc)
        if remaining <= 0:
            raise AdmissionRefused("DEADLINE")
        client = HttpQuickNodeRpcClient(
            endpoint=self.quicknode_url, transport=self.wire,
            bounds=ClientBounds(deadline_seconds=remaining, connect_timeout_seconds=min(MAX_CONNECT_SECONDS, remaining),
                                max_response_bytes=MAX_REPLY_BYTES, max_request_bytes=MAX_REQUEST_BYTES,
                                max_blocks_per_page=MAX_BLOCKS_PER_PAGE),
            allowed_methods=QUICKNODE_METHODS, clock=self.clock.monotonic, cancel=self.cancel)
        self.wire.label(phase=phase, slot=slot, provider="quicknode")
        return client.call(method, params)

    def _hypersync(self, phase: str, slot: str, payload: Mapping[str, Any], cutoff_utc: float,
                   admission_end_utc: float | None = None) -> Mapping[str, Any]:
        self._pace("hypersync")
        deadline, remaining = self._deadline(cutoff_utc)
        if remaining <= 0:
            raise AdmissionRefused("DEADLINE")
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"content-type": "application/json", "accept": "application/json",
                   "accept-encoding": "identity", "authorization": f"Bearer {self.hypersync_token}"}
        self.wire.label(phase=phase, slot=slot, provider="hypersync", admission_end_utc=admission_end_utc)
        response = self.wire.request(method="POST", url=self.value["hypersync_url"], headers=headers, body=body,
                                     timeout=min(MAX_CONNECT_SECONDS, remaining), deadline=deadline,
                                     max_response_bytes=MAX_REPLY_BYTES, cancel=self.cancel)
        refuse_provider_status(response.status, "the HyperSync query")
        parsed = decode_json_reply(response)
        if self.cancel is not None and self.cancel():
            raise SourceCancelled("cancelled")
        if self.clock.monotonic() >= deadline:
            raise SourceTimeout("the query exceeded its time bound")
        return parsed

    def _classify(self, error: Exception, *, fatal: bool, phase: str) -> str:
        """Return the weak outcome for a failed call, or stop all providers for a safety failure."""
        if isinstance(error, ClockUntrusted):
            self.trusted_clock = False
            self._stop("CLOCK_UNTRUSTED", "CLOCK_UNTRUSTED")
            return "CLOCK_UNTRUSTED"
        if isinstance(error, EvidenceWriteFailed):
            self._stop("EVIDENCE_WRITE_FAILED", "EVIDENCE_WRITE_FAILED")
            return "EVIDENCE_WRITE_FAILED"
        if isinstance(error, SafetyStop):
            self._stop("SAFETY_STOP", error.code)
            return error.code
        if isinstance(error, SourceCancelled) or (isinstance(error, AdmissionRefused) and error.code == "CANCELLED"):
            self._stop("CANCELLED", "CANCELLED")
            return "CANCELLED"
        if isinstance(error, AdmissionRefused) and (error.code != "DEADLINE" or fatal):
            self._stop("SAFETY_STOP", f"ADMISSION_{error.code}")
            return error.code
        if isinstance(error, AdmissionRefused):
            return "FAILED:DEADLINE_PASSED"  # refused before admission: zero sends, zero liability
        if isinstance(error, HttpProviderError) and error.code in SAFETY_CODES:
            self._stop("SAFETY_STOP", error.code)
            return error.code
        code = error.code if isinstance(error, HttpProviderError) else type(error).__name__
        if fatal:
            self._stop("SAFETY_STOP", f"{phase}_CALL_FAILED")
        return f"FAILED:{code}"

    # Phases

    def run(self) -> None:
        try:
            self._p1()
            if not self._stopped():
                self._p2()
            if not self._stopped():
                self._p3()
            if not self._stopped():
                self._p4()
            if not self._stopped():
                self._p5()
        except ClockUntrusted:
            self._classify(ClockUntrusted(), fatal=True, phase="SCHEDULE")
        except EvidenceWriteFailed as error:
            self._classify(error, fatal=True, phase="JOURNAL")
        for bucket in self.buckets:
            if bucket["status"] == "OPEN":
                self._close(bucket, self.stop_reason or "NOT_COVERED")

    def _p1_call(self, slot: str, method: str, params: list[Any]) -> Any:
        try:
            return self._rpc("P1", slot, method, params, self.attempt_deadline)
        except Exception as error:  # every P1 failure is a safety stop
            self._classify(error, fatal=True, phase="P1")
            raise _P1Stop() from None

    def _p1(self) -> None:
        creation = self.value["creation"]
        try:
            chain = self._p1_call("chain_id", "eth_chainId", [])
            if _quantity_or(chain) != CHAIN_ID:
                raise SafetyStop("P1_CHAIN_ID")
            receipt = self._p1_call("creation_receipt", "eth_getTransactionReceipt", [creation["transaction_hash"]])
            event = self._receipt_event(receipt)
            self._p1_hypersync(event)
            factory = self._p1_call("factory", "eth_call", [{"to": self.value["pool"], "data": SELECTORS["factory"]},
                                                            "latest"])
            if _word_address(factory) != creation["factory"]:
                raise SafetyStop("P1_FACTORY_DIFFERS")
            for role in ("pool", "token0", "token1"):
                code = self._p1_call(f"code_{role}", "eth_getCode", [self.value[role], "latest"])
                self.facts["bytecode"][role] = self._code_identity(code)
            self.phases["P1"] = {"outcome": "COMPLETED"}
        except SafetyStop as stop:
            self._stop("SAFETY_STOP", stop.code)
            self.phases["P1"] = {"outcome": "STOPPED"}
        except _P1Stop:
            self.phases["P1"] = {"outcome": "STOPPED"}

    @staticmethod
    def _code_identity(code: Any) -> dict[str, Any] | None:
        if not isinstance(code, str) or not code.startswith("0x") or len(code) % 2 or len(code) <= 2:
            return None
        try:
            raw = bytes.fromhex(code[2:])
        except ValueError:
            return None
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def _receipt_event(self, receipt: Any) -> dict[str, Any]:
        creation = self.value["creation"]
        if not isinstance(receipt, Mapping) or receipt.get("status") != "0x1":
            raise SafetyStop("P1_RECEIPT_STATUS")
        if (str(receipt.get("transactionHash", "")).lower() != creation["transaction_hash"]
                or _quantity_or(receipt.get("blockNumber")) != creation["block_number"]
                or str(receipt.get("blockHash", "")).lower() != creation["block_hash"]
                or _quantity_or(receipt.get("transactionIndex")) != creation["transaction_index"]):
            raise SafetyStop("P1_RECEIPT_IDENTITY")
        logs = receipt.get("logs")
        if not isinstance(logs, list):
            raise SafetyStop("P1_RECEIPT_LOGS")
        matches = [log for log in logs if isinstance(log, Mapping)
                   and str(log.get("address", "")).lower() == creation["factory"]
                   and isinstance(log.get("topics"), list) and log["topics"]
                   and str(log["topics"][0]).lower() == creation["topic0"]]
        if len(matches) != 1:
            raise SafetyStop("P1_CREATION_AMBIGUOUS")
        log = matches[0]
        if log.get("removed", False) is not False:
            raise SafetyStop("P1_CREATION_REMOVED")
        if (_quantity_or(log.get("logIndex")) != creation["log_index"]
                or _quantity_or(log.get("transactionIndex")) != creation["transaction_index"]
                or str(log.get("transactionHash", "")).lower() != creation["transaction_hash"]
                or _quantity_or(log.get("blockNumber")) != creation["block_number"]
                or str(log.get("blockHash", "")).lower() != creation["block_hash"]):
            raise SafetyStop("P1_CREATION_IDENTITY")
        event = self._decode_creation(log["topics"], log.get("data"))
        event.update(log_index=creation["log_index"])
        return event

    def _decode_creation(self, topics: Sequence[Any], data: Any) -> dict[str, Any]:
        """Decoder retained-v2-pair-created/1: three topics, two ABI data words, exact padding and token order."""
        if len(topics) != 3:
            raise SafetyStop("P1_CREATION_LAYOUT")
        token0, token1 = _word_address(topics[1]), _word_address(topics[2])
        if token0 is None or token1 is None:
            raise SafetyStop("P1_CREATION_LAYOUT")
        if not isinstance(data, str) or len(data) != 2 + 128:
            raise SafetyStop("P1_CREATION_LAYOUT")
        pool = _word_address("0x" + data[2:66])
        try:
            pair_count = int(hex_value("0x" + data[66:], 32, "pair_count"), 16)
        except PayloadError as error:
            raise SafetyStop("P1_CREATION_LAYOUT") from error
        if pool is None:
            raise SafetyStop("P1_CREATION_LAYOUT")
        if (token0, token1, pool) != (self.value["token0"], self.value["token1"], self.value["pool"]):
            raise SafetyStop("P1_CREATION_IDENTITY")
        self.facts["pair_count"] = pair_count
        return {"topics": [str(topic).lower() for topic in topics], "data": data.lower()}

    def _p1_hypersync(self, event: Mapping[str, Any]) -> None:
        creation = self.value["creation"]
        payload = {"from_block": creation["block_number"], "to_block": creation["block_number"] + 1,
                   "logs": [{"address": [creation["factory"]], "topics": [[creation["topic0"]]]}],
                   "field_selection": {"block": ["number", "timestamp", "hash"],
                                       "log": ["block_number", "block_hash", "transaction_hash",
                                               "transaction_index", "log_index", "address", "data", "topic0",
                                               "topic1", "topic2", "topic3"]}}
        try:
            reply = self._hypersync("P1", "creation_log", payload, self.attempt_deadline)
        except Exception as error:
            self._classify(error, fatal=True, phase="P1")
            raise _P1Stop() from None
        data = reply.get("data")
        logs = data.get("logs") if isinstance(data, Mapping) else None
        blocks = data.get("blocks") if isinstance(data, Mapping) else None
        if not isinstance(logs, list) or not isinstance(blocks, list):
            raise SafetyStop("P1_HYPERSYNC_SHAPE")
        matches = [log for log in logs if isinstance(log, Mapping)
                   and str(log.get("address", "")).lower() == creation["factory"]
                   and str(log.get("topic0", "")).lower() == creation["topic0"]]
        if len(matches) != 1:
            raise SafetyStop("P1_HYPERSYNC_AMBIGUOUS")
        log = matches[0]
        if log.get("topic3") is not None or log.get("removed", False) is not False:
            raise SafetyStop("P1_HYPERSYNC_LAYOUT")
        observed = (_quantity_or(log.get("block_number")), str(log.get("block_hash", "")).lower(),
                    str(log.get("transaction_hash", "")).lower(), _quantity_or(log.get("transaction_index")),
                    _quantity_or(log.get("log_index")), str(log.get("topic0", "")).lower(),
                    str(log.get("topic1", "")).lower(), str(log.get("topic2", "")).lower(),
                    str(log.get("data", "")).lower())
        expected = (creation["block_number"], creation["block_hash"], creation["transaction_hash"],
                    creation["transaction_index"], creation["log_index"], *event["topics"], event["data"])
        if observed != expected:
            raise SafetyStop("P1_HYPERSYNC_IDENTITY")
        header = next((h for h in map(_header, blocks) if h and h[0] == creation["block_number"]), None)
        if header is None or header[2] != creation["block_hash"]:
            raise SafetyStop("P1_HYPERSYNC_BLOCK")
        self.facts["creation_block_timestamp"] = header[1]

    def _p2(self) -> None:
        self._wait_until(self.t0 - P2_EARLIEST)
        now = self.wire.observe()[0]
        if not self.t0 - P2_EARLIEST <= now < self.t0 - P2_CUTOFF:
            self.phases["P2"] = {"outcome": "MISSED"}
            return
        try:
            header = self._rpc("P2", "anchor", "eth_getBlockByNumber", ["latest", False], self.t0 - P2_CUTOFF)
        except Exception as error:
            self.phases["P2"] = {"outcome": self._classify(error, fatal=False, phase="P2")}
            return
        receipt = self.wire.last_receipt
        parsed = _header(header)
        if parsed is None:
            self.phases["P2"] = {"outcome": "FAILED:MALFORMED_HEADER"}
            return
        if parsed[1] >= self.t0:
            self._stop("SAFETY_STOP", "ANCHOR_NOT_BEFORE_T0")
            self.phases["P2"] = {"outcome": "STOPPED"}
            return
        self.anchor = parsed
        self.cursor = parsed[0]
        self.phases["P2"] = {"outcome": "COMPLETED", "number": parsed[0], "timestamp": parsed[1],
                             "hash": parsed[2], "observed_utc_us": int(receipt["utc"] * 1_000_000)}

    def _close(self, bucket: dict[str, Any], reason: str) -> None:
        if bucket["status"] == "OPEN":
            bucket["status"], bucket["reason"] = "INCOMPLETE", reason

    def _p3(self) -> None:
        outcomes: list[dict[str, Any]] = []
        for index, kind, due in p3_events(self.t0):
            bucket = self.buckets[index]
            if self._stopped():
                break
            if self.anchor is None:
                self._close(bucket, "NO_ANCHOR")
                continue
            if kind == "second" and bucket["first"] != "VALID_INSUFFICIENT":
                self._close(bucket, {"FAILED": "FIRST_READ_FAILED", "REJECTED": "FIRST_READ_REJECTED",
                                     "MISSED": "FIRST_SLOT_MISSED"}.get(bucket["first"], "NOT_COVERED"))
                continue
            if bucket["status"] != "OPEN":
                continue
            outcome = self._p3_read(index, kind, due)
            outcomes.append({"bucket": index, "read": kind, "outcome": outcome})
            if kind == "first":
                bucket["first"] = outcome
            elif bucket["status"] == "OPEN":
                self._close(bucket, {"MISSED": "SECOND_SLOT_MISSED", "REJECTED": "SECOND_READ_REJECTED",
                                     "FAILED": "SECOND_READ_FAILED"}.get(outcome, "NOT_COVERED_AFTER_SECOND_READ"))
        self.phases["P3"] = {"outcome": "STOPPED" if self._stopped() else "COMPLETED", "reads": outcomes}
        if not self._stopped():
            self._wait_until(p3_events(self.t0)[-1][2] + 1)

    def _p3_read(self, index: int, kind: str, due: int) -> str:
        self._wait_until(due)
        last = self.journal.last_admission.get("hypersync")
        if last is not None and self.wire.observe()[1] - last < PACING_SECONDS:
            self._pace("hypersync")
        now = self.wire.observe()[0]
        if not due <= now < due + 1:
            return "MISSED"
        end = self.buckets[index]["end"]
        cutoff = end + SECOND_READ_OFFSET if kind == "first" else now + MAX_CALL_SECONDS
        payload = {"from_block": self.cursor,
                   "logs": [{"address": [self.value["pool"]], "topics": [[SWAP_TOPIC0]]}],
                   "include_all_blocks": True, "max_num_blocks": MAX_BLOCKS_PER_PAGE,
                   "field_selection": {"block": list(BLOCK_FIELD_SELECTION), "log": list(LOG_FIELD_SELECTION)}}
        try:
            reply = self._hypersync("P3", f"bucket{index}_{kind}", payload, cutoff, admission_end_utc=due + 1)
        except AdmissionRefused as refused:
            if refused.code == "SLOT_CLOSED":
                return "MISSED"  # refused before the durable admission: no liability, no send
            self._classify(refused, fatal=False, phase="P3")
            return "FAILED"
        except Exception as error:
            self._classify(error, fatal=False, phase="P3")
            return "FAILED"
        receipt = self.wire.last_receipt
        try:
            accepted = self._accept_page(reply, receipt)
        except SafetyStop as stop:
            self._stop("SAFETY_STOP", stop.code)
            return "STOPPED"
        if not accepted:
            return "REJECTED"
        self._freeze_covered(receipt)
        return "COVERED" if self.buckets[index]["status"] == "DELIVERED" else "VALID_INSUFFICIENT"

    def _accept_page(self, reply: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
        """Validate one forward page against the declared native shape; on success extend the chain."""
        start = self.cursor
        archive, next_block = _quantity_or(reply.get("archive_height")), _quantity_or(reply.get("next_block"))
        data = reply.get("data")
        if archive is None or next_block is None or next_block <= 0 or not isinstance(data, Mapping):
            return False
        blocks, logs = data.get("blocks"), data.get("logs")
        guard = reply.get("rollback_guard")
        if not isinstance(blocks, list) or not isinstance(logs, list) or (guard is not None
                                                                          and not isinstance(guard, Mapping)):
            return False
        if not start < next_block or next_block - start > MAX_BLOCKS_PER_PAGE:
            return False
        page: dict[int, tuple[int, str]] = {}
        for raw in blocks:
            header = _header(raw)
            if header is None:
                return False
            number, timestamp, digest = header
            known = self.headers.get(number)
            if known is not None and known != (timestamp, digest):
                raise SafetyStop("CONFLICTING_BLOCK_FACT")
            if self.anchor is not None and number == self.anchor[0] and (timestamp, digest) != self.anchor[1:]:
                raise SafetyStop("CONFLICTING_BLOCK_FACT")
            if number in page or not start <= number < next_block:
                return False
            page[number] = (timestamp, digest)
        if set(page) != set(range(start, next_block)):
            return False
        previous = self.headers.get(start - 1, (None,))[0] if start - 1 in self.headers else None
        for number in range(start, next_block):
            timestamp = page[number][0]
            if previous is not None and timestamp < previous:
                return False
            if timestamp > receipt["utc"]:
                return False
            previous = timestamp
        if guard is not None and not self._guard_consistent(guard, start, next_block, page):
            return False
        projected: dict[tuple[int, int, int], dict[str, Any]] = {}
        for log in logs:
            if not isinstance(log, Mapping):
                return False
            try:
                number = quantity(log.get("block_number"), "block_number")
                if number not in page:
                    return False
                record = project_log(log, block_timestamp=page[number][0])
                hex_value(log.get("transaction_hash"), 32, "transaction_hash")
            except PayloadError:
                return False
            if (record["block_hash"] != page[number][1] or record["address"] != self.value["pool"]
                    or record["topic0"] != SWAP_TOPIC0 or record["removed"]):
                return False
            identity = (record["block_number"], record["transaction_index"], record["log_index"])
            if identity in projected or identity in self.logs:
                return False
            projected[identity] = record
        for number, fact in page.items():
            self.headers[number] = fact
        self.logs.update(projected)
        self.cursor = next_block
        self.facts["archive_height"] = archive
        self.p3_replies.append({"call_id": receipt["call_id"], "from_block": start, "next_block": next_block,
                                "archive_height": archive, "log_count": len(projected),
                                "received_utc_us": int(receipt["utc"] * 1_000_000)})
        return True

    def _guard_consistent(self, guard: Mapping[str, Any], start: int, next_block: int,
                          page: Mapping[int, tuple[int, str]]) -> bool:
        """Every supplied rollback-guard fact must match the page (source_transport._frame precedent).

        A malformed fact rejects the page; a contradictory fact is a safety stop.
        """
        end_timestamp, end_hash = page[next_block - 1]
        for key, expected in (("first_block_number", start), ("block_number", next_block - 1),
                              ("timestamp", end_timestamp)):
            if key in guard:
                value = _quantity_or(guard[key])
                if value is None:
                    return False
                if value != expected:
                    raise SafetyStop("CONFLICTING_BLOCK_FACT")
        for key, expected in (("hash", end_hash), ("first_parent_hash", self.headers.get(start - 1, (None, None))[1])):
            if key in guard and guard[key] is not None:
                try:
                    value = hex_value(guard[key], 32, key)
                except PayloadError:
                    return False
                if expected is not None and value != expected:
                    raise SafetyStop("CONFLICTING_BLOCK_FACT")
        return True

    def _freeze_covered(self, receipt: Mapping[str, Any]) -> None:
        latest = max((fact[0] for fact in self.headers.values()), default=None)
        for bucket in self.buckets:
            if bucket["status"] != "OPEN" or latest is None or latest < bucket["end"]:
                continue
            members = bucket_members(self.logs.values(), bucket["start"], bucket["end"])
            body = canonical_payload(members)
            received_us = int(receipt["utc"] * 1_000_000)
            bucket.update(status="DELIVERED", delivery={
                "reply_id": receipt["call_id"], "received_at_utc_us": received_us,
                "received_at_utc": iso_utc(math.ceil(received_us / 1_000_000)),
                "record_count": len(members), "payload_sha256": hashlib.sha256(body).hexdigest()})

    def boundaries(self) -> dict[str, int | None]:
        ordered = sorted(self.headers.items())
        pre = max((n for n, (ts, _) in ordered if ts < self.t0), default=None)
        start = min((n for n, (ts, _) in ordered if ts >= self.t0), default=None)
        post = min((n for n, (ts, _) in ordered if ts >= self.window_end), default=None)
        end = None if post is None else max((n for n, (ts, _) in ordered if ts < self.window_end), default=None)
        if pre is not None and start is not None and start != pre + 1:
            start = None
        if end is not None and post is not None and post != end + 1:
            end = post = None
        return {"B_ANCHOR": None if self.anchor is None else self.anchor[0], "B_PRE": pre, "B_START": start,
                "B_END": end, "B_POST": post}

    def _decimals(self, phase: str, stage: str, role: str, block: str, cutoff: float) -> None:
        expected = self.value["expected_decimals"][role]
        try:
            word = self._rpc(phase, f"decimals_{stage}_{role}", "eth_call",
                             [{"to": self.value[role], "data": SELECTORS["decimals"]}, block], cutoff)
        except Exception as error:
            outcome = self._classify(error, fatal=False, phase=phase)
            self.facts["decimals"][stage][role] = "NOT_READ" if outcome.startswith("FAILED") else outcome
            return
        value = _quantity_or(word) if isinstance(word, str) and len(word) == 66 else None
        reference = self.facts["decimals"]["window_start"].get(role)
        if value is None:
            self.facts["decimals"][stage][role] = "NOT_READ"
        elif value != expected or (isinstance(reference, int) and value != reference):
            self._stop("SAFETY_STOP", "DECIMALS_DIFFER")
        else:
            self.facts["decimals"][stage][role] = value

    def _p4(self) -> None:
        start = self.boundaries()["B_START"]
        cutoff = self.t0 + LATE_PHASE_SECONDS
        if start is None:
            for role in ("token1", "token0"):
                self.facts["decimals"]["window_start"][role] = "SKIPPED_NO_B_START"
            self.phases["P4"] = {"outcome": "SKIPPED_NO_B_START"}
            return
        block = hex(start)
        for role in ("token1", "token0"):
            if not self._stopped():
                self._decimals("P4", "window_start", role, block, cutoff)
        tokens = {}
        for role in ("token0", "token1"):
            if self._stopped():
                break
            try:
                word = self._rpc("P4", f"pool_{role}", "eth_call", [{"to": self.value["pool"],
                                                                      "data": SELECTORS[role]}, block], cutoff)
            except Exception as error:
                tokens[role] = self._classify(error, fatal=False, phase="P4")
                continue
            if _word_address(word) != self.value[role]:
                self._stop("SAFETY_STOP", "TOKEN_ORDER_DIFFERS")
            else:
                tokens[role] = "READ"
        self.facts["pool_tokens_at_start"] = tokens
        self.phases["P4"] = {"outcome": "STOPPED" if self._stopped() else "COMPLETED"}

    def _p5(self) -> None:
        self._wait_until(self.window_end + 60)
        cutoff = self.window_end + LATE_PHASE_SECONDS
        bounds = self.boundaries()
        threshold = None if bounds["B_POST"] is None else bounds["B_POST"] + 2
        for tag in ("finalized", "latest"):
            if self._stopped():
                break
            try:
                header = _header(self._rpc("P5", tag, "eth_getBlockByNumber", [tag, False], cutoff))
                observed = self.wire.last_receipt["utc"]
            except Exception as error:
                self.facts[tag] = self._classify(error, fatal=False, phase="P5")
                continue
            self.facts[tag] = None if header is None else {"number": header[0], "timestamp": header[1],
                                                            "observed_utc_us": int(observed * 1_000_000)}
        finalized = self.facts["finalized"]
        if isinstance(finalized, Mapping) and threshold is not None and finalized["number"] >= threshold:
            self.facts["finality_at_collection"] = "OBSERVED_FINAL"
        latest = self.facts["latest"]
        self.facts["archive_height_declarable"] = bool(isinstance(latest, Mapping) and threshold is not None
                                                       and latest["number"] >= threshold)
        for role in ("token1", "token0"):
            if bounds["B_END"] is None:
                self.facts["decimals"]["window_end"][role] = "SKIPPED_NO_B_END"
            elif not self._stopped():
                self._decimals("P5", "window_end", role, hex(bounds["B_END"]), cutoff)
        for role in ("token1", "token0"):
            if not self._stopped():
                self._decimals("P5", "current", role, "latest", cutoff)
        self.phases["P5"] = {"outcome": "STOPPED" if self._stopped() else "COMPLETED"}

    # Handoff

    def evidence_notice(self) -> str:
        if self.value["evidence_class"] == "ACTUAL":
            return ("ACTUAL_NOT_ESTABLISHED: ACTUAL was requested, but transport provenance cannot be established "
                    "through the injected transport seam; the handoff stays SYNTHETIC.")
        return "SYNTHETIC: injected transport."

    def handoff(self, input_sha256: str) -> dict[str, Any]:
        bounds = self.boundaries()
        scan = None
        if bounds["B_PRE"] is not None and bounds["B_POST"] is not None:
            scan = {"from_block": bounds["B_PRE"], "to_block_exclusive": bounds["B_POST"] + 1}
        in_scan = [] if scan is None else [log for log in self.logs.values()
                                           if scan["from_block"] <= log["block_number"] < scan["to_block_exclusive"]]
        retained = set() if scan is None else {log["block_number"] for log in in_scan}
        retained |= {number for number in bounds.values() if number is not None}
        buckets = []
        for bucket in self.buckets:
            delivery = bucket["delivery"] or {}
            buckets.append({"index": bucket["index"], "start_utc": iso_utc(bucket["start"]),
                            "end_utc": iso_utc(bucket["end"]), "status": bucket["status"],
                            "reply_id": delivery.get("reply_id"), "received_at_utc": delivery.get("received_at_utc"),
                            "received_at_utc_us": delivery.get("received_at_utc_us"),
                            "record_count": delivery.get("record_count"),
                            "payload_sha256": delivery.get("payload_sha256"),
                            "reply_body_sha256": self.journal.calls[delivery["reply_id"]]["body_sha256"]
                            if delivery else None,
                            "reason": None if bucket["status"] == "DELIVERED" else bucket["reason"]})
        weaker = []
        if scan is not None and len(in_scan) > SCAN_LOG_LIMIT:
            weaker.append("SCAN_LOG_COUNT_EXCEEDS_61")
        unknown = sum(self.journal.provider_counts.values()) - self.journal.resolved
        value = self.value
        return {
            "schema_version": HANDOFF_SCHEMA, "canonicalization_version": CANONICALIZATION_VERSION,
            "input_schema": INPUT_SCHEMA, "predecessor_sha256": PREDECESSOR_SHA256, "input_sha256": input_sha256,
            "recorder_code_sha256": recorder_code_sha256(), "decoder": DECODER_VERSION,
            "attempt_id": value["attempt_id"], "source_id": value["source_id"], "evidence_class": EFFECTIVE_EVIDENCE_CLASS,
            "requested_evidence_class": value["evidence_class"], "evidence_notice": self.evidence_notice(),
            "status": self.status, "stop_reason": self.stop_reason,
            "network": {"chain_id": CHAIN_ID},
            "market": {"pool": value["pool"], "token0": value["token0"], "token1": value["token1"],
                       "base": value["base"], "quote": value["quote"]},
            "window": {"start_utc": iso_utc(self.t0), "end_utc": iso_utc(self.window_end),
                       "bucket_seconds": BUCKET_SECONDS},
            "query": {"address": value["pool"], "topic0": SWAP_TOPIC0, "include_all_blocks": True,
                      "max_num_blocks": MAX_BLOCKS_PER_PAGE, "field_selection": {
                          "block": list(BLOCK_FIELD_SELECTION), "log": list(LOG_FIELD_SELECTION)}},
            "boundaries": bounds, "scan": scan, "scan_log_count": None if scan is None else len(in_scan),
            "chain_cursor": self.cursor, "weaker_evidence": weaker,
            "headers": [{"number": number, "timestamp": self.headers[number][0], "hash": self.headers[number][1]}
                        for number in sorted(retained) if number in self.headers],
            "phases": self.phases, "p3_replies": self.p3_replies, "facts": self.facts,
            "clock": {"trusted": self.trusted_clock},
            "accounting": {"admitted": {provider: self.journal.admitted(provider) for provider in PROVIDER_LIMITS},
                           "resolved": self.journal.resolved, "unknown_liability": unknown,
                           "reply_bytes": self.journal.reply_bytes, "ceilings": PROVIDER_LIMITS},
            "calls": [dict(call) for call in self.journal.calls.values()],
            "buckets": buckets,
            "delivery_records": {b["start_utc"]: b["received_at_utc"] for b in buckets if b["status"] == "DELIVERED"},
            "release_frozen": False,
            "claim_limit": ("Recorder delivery evidence only. A handoff never freezes a release and proves no "
                            "mechanics, rights, fillability or provider qualification. SYNTHETIC: injected "
                            "transport; actual network provenance is not established by this recorder."),
        }


class _P1Stop(Exception):
    pass


# The public HttpTransport seam cannot show whether a StdlibHttpTransport uses a test connector, so no handoff from
# this recorder is ACTUAL. A requested ACTUAL label is kept separately and reported, never adopted.
EFFECTIVE_EVIDENCE_CLASS = "SYNTHETIC"


def recorder_code_sha256() -> str:
    digest = hashlib.sha256()
    for module in (Path(__file__), Path(__file__).with_name("history_payload_binding.py")):
        digest.update(module.read_bytes())
    return digest.hexdigest()


def run_attempt(raw_input: Mapping[str, Any], *, transport: HttpTransport, clock: RecorderClock,
                credentials: Callable[[str], str], cancel: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Run one attempt through an injected transport. Validates everything before any credential read."""
    value = validate_input(raw_input)
    input_sha256 = hashlib.sha256(canonical_bytes(dict(raw_input))).hexdigest()
    gaps = readiness_gaps(value)
    if gaps:
        return {"status": "NOT_READY", "stop_reason": None, "readiness_gaps": gaps, "sends": 0}
    directory = Path(value["output_dir"]) / value["attempt_id"]
    journal = AttemptJournal.create(directory)
    journal.append({"event": "ATTEMPT_STARTED", "attempt_id": value["attempt_id"], "t0_utc": value["t0_utc"],
                    "input_sha256": input_sha256, "started_utc_us": int(clock.utc() * 1_000_000)})
    attempt = _Attempt(value, transport, clock, credentials, cancel)
    attempt.journal = journal
    quicknode_url = credentials(value["credential_slots"]["quicknode"])
    attempt.hypersync_token = credentials(value["credential_slots"]["hypersync"])
    secrets = [quicknode_url, attempt.hypersync_token, f"Bearer {attempt.hypersync_token}"]
    try:
        parts = urlsplit(quicknode_url)
        validate_endpoint(quicknode_url)
        destination_ok = parts.scheme == "https" and parts.hostname == value["quicknode_host"]
        if parts.path not in ("", "/"):
            secrets.append(parts.path.strip("/"))
    except (ClientConfigError, ValueError, TypeError):
        destination_ok = False
    attempt.quicknode_url = quicknode_url
    attempt.wire = RecordingTransport(transport, journal, clock, quicknode_url=quicknode_url,
                                      hypersync_url=value["hypersync_url"], secrets=secrets)
    if destination_ok:
        attempt.run()
    else:
        attempt.status, attempt.stop_reason = "DESTINATION_MISMATCH", "DESTINATION_MISMATCH"
        for bucket in attempt.buckets:
            attempt._close(bucket, "DESTINATION_MISMATCH")
    handoff = attempt.handoff(input_sha256)
    body = canonical_bytes(handoff)
    path = directory / "handoff.json"
    write_exclusive(path, body)
    handoff_sha256 = hashlib.sha256(body).hexdigest()
    journal.append({"event": "HANDOFF_WRITTEN", "sha256": handoff_sha256})
    receipts = canonical_bytes(attempt.wire.receipts_document(value["attempt_id"], handoff_sha256))
    try:
        write_exclusive(directory / TRANSPORT_RECEIPTS_FILE, receipts)
        receipts_status, receipts_sha256 = "WRITTEN", hashlib.sha256(receipts).hexdigest()
    except OSError:
        # The handoff is already complete. A missing sidecar never changes it and never authorizes a resend.
        receipts_status, receipts_sha256 = "WRITE_FAILED", None
    return {"status": attempt.status, "stop_reason": attempt.stop_reason, "handoff_path": str(path),
            "handoff_sha256": handoff_sha256, "transport_receipts_status": receipts_status,
            "transport_receipts_sha256": receipts_sha256}


def recover_attempt(directory: Path) -> dict[str, Any]:
    """Read-only report of a saved attempt. Never sends, never resumes, never refunds a liability."""
    body = read_bounded(Path(directory) / "journal.jsonl", MAX_JOURNAL_BYTES)
    admitted = resolved = 0
    t0 = None
    admissions: dict[str, list[float]] = {"quicknode": [], "hypersync": []}
    lines = body.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    torn_tail = False
    for position, line in enumerate(lines):
        try:
            record = json.loads(line)
            event = record["event"]
        except (ValueError, TypeError, KeyError):
            if position == len(lines) - 1:
                torn_tail = True  # an interrupted final append; the complete prefix stays authoritative
                break
            raise PayloadError("JOURNAL_CORRUPT") from None
        if event == "ATTEMPT_STARTED":
            t0 = record["t0_utc"]
        elif record["event"] == "ADMITTED":
            admitted += 1
            admissions[record["provider"]].append(record["admitted_monotonic"])
        elif record["event"] == "RESOLVED":
            resolved += 1
    notice = ("TORN_TAIL: the final journal record is incomplete and is not counted. Any call it concerned keeps "
              "uncertain liability; this proves neither a send nor its absence." if torn_tail else "")
    return {"t0_utc": t0, "admitted": admitted, "resolved": resolved, "unknown_liability": admitted - resolved,
            "handoff_present": (Path(directory) / "handoff.json").exists(), "admission_monotonic": admissions,
            "torn_tail": torn_tail, "notice": notice}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a forward history recorder input or inspect an attempt.")
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan", help="validate an input and print the redacted plan; sends nothing")
    plan_parser.add_argument("--input", required=True, type=Path)
    recover_parser = commands.add_parser("recover", help="read-only summary of a saved attempt; sends nothing")
    recover_parser.add_argument("--attempt-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            value = validate_input(strict_json(read_bounded(args.input, MAX_INPUT_BYTES), "INPUT_NOT_STRICT_JSON"))
            print(json.dumps(plan(value), sort_keys=True))
        else:
            print(json.dumps(recover_attempt(args.attempt_dir), sort_keys=True))
    except (RecorderInputError, PayloadError) as error:
        print(json.dumps({"status": "REFUSED", "code": error.code}))
        return 2
    except OSError as error:
        print(json.dumps({"status": "REFUSED", "code": "FILE_ERROR", "errno": error.errno}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
