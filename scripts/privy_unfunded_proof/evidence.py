"""Bounded capture and explicit outcomes for one synthetic policy-proof attempt.

LOCAL and SYNTHETIC_FIXTURE only. ``run_specimen`` admits one frozen specimen,
saves intent, calls the injected send once, saves a sanitized capture record
before any JSON parse, and classifies the reply with the SYNTHETIC reply
profile. No actual provider error profile exists here. Reply bodies, signed
bytes, credentials and unknown error strings are never saved, logged or
re-raised. See docs/qualification/privy-unfunded-proof/CONTRACT.md.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from scripts.privy_unfunded_proof.specimens import (
    EVIDENCE_CLASS,
    FROZEN_TABLE,
    PROVIDER_PROOF,
    WALLETS,
    AttemptState,
    AttemptStore,
    EvidenceOverBound,
    Expected,
    FrozenRequest,
    Specimen,
    SpecimenRefused,
    SpecimenTable,
    envelope_sha256,
    headers_are_canonical,
    refuse_module_run,
)

MAX_REPLY_BYTES = 16384
MAX_CONTENT_TYPE_CHARS = 128


class Outcome(StrEnum):
    ALLOW = "ALLOW"
    POLICY_DENY = "POLICY_DENY"
    AUTHORIZATION_DENY = "AUTHORIZATION_DENY"
    SCHEMA_REJECTED = "SCHEMA_REJECTED"
    UNKNOWN = "UNKNOWN"
    BREACH = "BREACH"


class ProfileUnqualified(ValueError):
    pass


@dataclass(frozen=True)
class Reply:
    """What an injected send returns. Fields are validated, never trusted."""

    status: object
    content_type: object
    body: object

    def __repr__(self) -> str:
        return "Reply(<withheld>)"


@dataclass(frozen=True)
class ReplyProfile:
    """The reply classifier. Only the invented SYNTHETIC codes exist in this unit."""

    qualification: str = "SYNTHETIC"

    def __post_init__(self) -> None:
        if self.qualification != "SYNTHETIC":
            raise ProfileUnqualified("actual reply profiles are UNQUALIFIED in this unit")

    # code -> (required status, outcome, reason)
    @property
    def codes(self) -> Mapping[str, tuple[int, Outcome, str]]:
        return {
            "synthetic_policy_violation": (400, Outcome.POLICY_DENY, "SYNTHETIC_POLICY_CODE"),
            "synthetic_wallet_not_authorized": (403, Outcome.AUTHORIZATION_DENY, "SYNTHETIC_AUTHORIZATION_CODE"),
            "synthetic_invalid_field": (400, Outcome.SCHEMA_REJECTED, "SYNTHETIC_SCHEMA_CODE"),
            "synthetic_request_expired": (400, Outcome.UNKNOWN, "EXPIRY_REFUSAL"),
        }


SYNTHETIC_PROFILE = ReplyProfile()

_DENIALS = (Expected.POLICY_DENY, Expected.AUTHORIZATION_DENY, Expected.EXPIRY_REFUSAL)
# Expected refusals end one capability test. Every other UNKNOWN is a network, access,
# unexpected-server or evidence failure and stops the stage, as the P21 packet requires.
_NON_STOPPING_UNKNOWN = ("EXPIRY_REFUSAL",)


@dataclass(frozen=True)
class RunResult:
    specimen_id: str
    profile: str
    expected: str
    outcome: Outcome
    reason: str
    matches_expectation: bool
    evidence_class: str = EVIDENCE_CLASS
    provider_proof: str = PROVIDER_PROOF


def _matches(expected: Expected, outcome: Outcome, reason: str) -> bool:
    if expected is Expected.EXPIRY_REFUSAL:
        return outcome is Outcome.UNKNOWN and reason == "EXPIRY_REFUSAL"
    if expected is Expected.DIAGNOSTIC:
        return outcome in (Outcome.ALLOW, Outcome.POLICY_DENY)
    return outcome.value == expected.value


def _normalized(value: object) -> object:
    if isinstance(value, str) and value[:2].lower() == "0x":
        return value.lower()
    return value


def _hex_bytes(value: object) -> bytes | None:
    if not isinstance(value, str) or not value.startswith("0x") or len(value) % 2:
        return None
    try:
        return bytes.fromhex(value[2:])
    except ValueError:
        return None


def _metadata(reply: object) -> tuple[int | None, str | None, bytes, bool]:
    status = getattr(reply, "status", None)
    content_type = getattr(reply, "content_type", None)
    body = getattr(reply, "body", None)
    status_ok = type(status) is int and 100 <= status <= 599
    type_ok = (
        isinstance(content_type, str)
        and len(content_type) <= MAX_CONTENT_TYPE_CHARS
        and content_type.isascii()
        and content_type.isprintable()
    )
    body_ok = isinstance(body, bytes)
    return (
        status if status_ok else None,
        content_type if type_ok else None,
        body if body_ok else b"",
        status_ok and type_ok and body_ok,
    )


def _media_type(content_type: str | None) -> str | None:
    """Return a fixed media classification. Reply text is never saved."""
    if content_type is None:
        return None
    media = content_type.split(";")[0].strip().lower()
    return "application/json" if media == "application/json" else "OTHER"


class _Attempt:
    """One claimed specimen. Every exit writes at most one outcome record."""

    def __init__(self, specimen: Specimen, store: AttemptStore, clock: Callable[[], str]) -> None:
        self.specimen = specimen
        self.store = store
        self.clock = clock
        self.capture_sha256: str | None = None
        self.extra: dict[str, Any] = {}

    def finish(self, outcome: Outcome, reason: str) -> RunResult:
        expected = self.specimen.expected
        result = RunResult(
            self.specimen.specimen_id, self.specimen.profile, expected.value, outcome, reason,
            _matches(expected, outcome, reason),
        )
        if outcome is Outcome.BREACH or (outcome is Outcome.UNKNOWN and reason not in _NON_STOPPING_UNKNOWN):
            self._stop(reason)
        record = {
            "specimen_id": result.specimen_id,
            "profile": result.profile,
            "request_sha256": self.specimen.request.request_sha256 if self.specimen.request else None,
            "expected": result.expected,
            "outcome": outcome.value,
            "reason": reason,
            "matches_expectation": result.matches_expectation,
            "capture_record_sha256": self.capture_sha256,
            "evidence_class": EVIDENCE_CLASS,
            "provider_proof": PROVIDER_PROOF,
            "completed_at": self.clock(),
            **self.extra,
        }
        try:
            self.store.write_outcome(self.specimen.specimen_id, record)
        except (OSError, EvidenceOverBound, ValueError):
            self._stop("OUTCOME_NOT_PERSISTED")
            if outcome is Outcome.BREACH:
                return result
            return RunResult(result.specimen_id, result.profile, result.expected, Outcome.UNKNOWN,
                             "OUTCOME_NOT_PERSISTED", False)
        return result

    def _stop(self, reason: str) -> None:
        try:
            self.store.stop({"specimen_id": self.specimen.specimen_id, "reason": reason, "at": self.clock()})
        except (OSError, EvidenceOverBound):
            pass

    def capture(self, reply: object) -> tuple[int | None, str | None, bytes, bool] | None:
        status, content_type, body, valid = _metadata(reply)
        record = {
            "specimen_id": self.specimen.specimen_id,
            "profile": self.specimen.profile,
            "request_sha256": self.specimen.request.request_sha256 if self.specimen.request else None,
            "status": status,
            "media_type": _media_type(content_type),
            "content_type_sha256": (
                hashlib.sha256(content_type.encode("ascii")).hexdigest() if content_type is not None else None
            ),
            "byte_count": len(body),
            "raw_body_sha256": hashlib.sha256(body).hexdigest(),
            "metadata_valid": valid,
            "captured_at": self.clock(),
            "evidence_class": EVIDENCE_CLASS,
        }
        try:
            saved = self.store.write_capture(self.specimen.specimen_id, record)
        except (OSError, EvidenceOverBound):
            self._stop("CAPTURE_FAILED")
            return None
        self.capture_sha256 = hashlib.sha256(saved).hexdigest()
        return status, content_type, body, valid


def _classify_success(
    attempt: _Attempt, data: Mapping[str, Any], decode_signed: Callable[[bytes], Mapping[str, Any]]
) -> RunResult:
    specimen = attempt.specimen
    signed = _hex_bytes(data.get("signed_transaction"))
    signature = _hex_bytes(data.get("signature"))
    if signed is None and signature is None:
        return attempt.finish(Outcome.UNKNOWN, "MALFORMED_SUCCESS")
    attempt.extra["signed_bytes_sha256"] = hashlib.sha256(signed if signed is not None else signature).hexdigest()
    if specimen.expected in _DENIALS:
        return attempt.finish(Outcome.BREACH, "ALLOWED_WHERE_DENIAL_REQUIRED")
    if signed is None or specimen.transaction is None:
        return attempt.finish(Outcome.UNKNOWN, "MALFORMED_SUCCESS")
    try:
        decoded = decode_signed(signed)
    except Exception:  # noqa: BLE001 - decoder messages may carry signed bytes; keep a fixed reason
        return attempt.finish(Outcome.UNKNOWN, "DECODE_FAILED")
    if not isinstance(decoded, Mapping):
        return attempt.finish(Outcome.UNKNOWN, "DECODE_FAILED")
    want = {**specimen.transaction, "wallet": WALLETS[specimen.wallet_id]}
    # Only frozen specimen values are saved, never values taken from the reply.
    try:
        matches = {key: bool(_normalized(decoded.get(key)) == _normalized(value)) for key, value in sorted(want.items())}
    except Exception:  # noqa: BLE001 - a hostile decoded value may raise with reply text; keep a fixed reason
        return attempt.finish(Outcome.UNKNOWN, "DECODE_FAILED")
    public: dict[str, Any] = {}
    for key, matched in matches.items():
        if matched and key == "data":
            public["data_sha256"] = hashlib.sha256(bytes.fromhex(want[key][2:])).hexdigest()
        elif matched:
            public[key] = want[key]
    attempt.extra["decoded_field_matches"] = matches
    attempt.extra["decoded_public_fields"] = public
    if not all(matches.values()):
        return attempt.finish(Outcome.BREACH, "SIGNED_FIELDS_MISMATCH")
    return attempt.finish(Outcome.ALLOW, "SIGNED_FIELDS_MATCH")


def _positive_control_allowed(table: SpecimenTable, store: AttemptStore, profile: str) -> bool:
    control = table.positive_control(profile)
    record = store.read_outcome(control.specimen_id)
    return record is not None and record.get("outcome") == Outcome.ALLOW.value


def _admit(
    specimen_id: str, table: SpecimenTable, store: AttemptStore, run_mode: str, owner_authority: object
) -> tuple[Specimen, FrozenRequest]:
    if run_mode != EVIDENCE_CLASS:
        raise SpecimenRefused("ACTUAL_RUN_REFUSED")
    if not table.manifest_matches_rows():
        raise SpecimenRefused("MANIFEST_MISMATCH")
    specimen = table.get(specimen_id)
    request = specimen.request
    if request is None:
        detail = "OWNER_AUTHORITY_ABSENT" if owner_authority is None else "SYNTHETIC_AUTHORITY_NOT_PROOF"
        raise SpecimenRefused("NOT_RUN", detail)
    if not headers_are_canonical(request.headers):
        raise SpecimenRefused("MALFORMED_REQUEST_HEADERS")
    if envelope_sha256(request.url, request.http_method, request.headers, request.body) != request.request_sha256:
        raise SpecimenRefused("REQUEST_BYTES_CHANGED")
    state = store.state(specimen_id)
    if state is AttemptState.TERMINAL:
        raise SpecimenRefused("ALREADY_CLAIMED")
    if state is not AttemptState.NOT_SENT:
        raise SpecimenRefused("ATTEMPT_UNCERTAIN")
    if store.is_stopped():
        raise SpecimenRefused("STAGE_STOPPED")
    blocking = store.blocking_attempt(excluding=specimen_id)
    if blocking is not None:
        raise SpecimenRefused(blocking)
    if not specimen.is_positive_control and not _positive_control_allowed(table, store, specimen.profile):
        raise SpecimenRefused("POSITIVE_CONTROL_NOT_QUALIFIED")
    return specimen, request


def run_specimen(
    specimen_id: str,
    *,
    store: AttemptStore,
    send: Callable[[FrozenRequest], object],
    decode_signed: Callable[[bytes], Mapping[str, Any]],
    clock: Callable[[], str],
    table: SpecimenTable = FROZEN_TABLE,
    reply_profile: ReplyProfile = SYNTHETIC_PROFILE,
    run_mode: str = EVIDENCE_CLASS,
    owner_authority: object = None,
) -> RunResult:
    """Run one frozen specimen at most once. Raises ``SpecimenRefused`` before any effect."""
    specimen, request = _admit(specimen_id, table, store, run_mode, owner_authority)
    store.claim(specimen, at=clock())
    attempt = _Attempt(specimen, store, clock)
    try:
        reply = send(request)
    except Exception:  # noqa: BLE001 - transport errors may carry secrets; keep a fixed reason
        return attempt.finish(Outcome.UNKNOWN, "SEND_FAILED")
    captured = attempt.capture(reply)
    if captured is None:
        return RunResult(specimen.specimen_id, specimen.profile, specimen.expected.value, Outcome.UNKNOWN,
                         "CAPTURE_FAILED", False)
    status, content_type, body, valid = captured
    if not valid:
        return attempt.finish(Outcome.UNKNOWN, "MALFORMED_METADATA")
    if len(body) > MAX_REPLY_BYTES:
        return attempt.finish(Outcome.UNKNOWN, "RESPONSE_OVER_BOUND")
    if content_type is None or content_type.split(";")[0].strip().lower() != "application/json":
        return attempt.finish(Outcome.UNKNOWN, "NON_JSON")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return attempt.finish(Outcome.UNKNOWN, "MALFORMED_JSON")
    if status == 200:
        data = parsed.get("data") if isinstance(parsed, dict) else None
        if not isinstance(data, dict):
            return attempt.finish(Outcome.UNKNOWN, "MALFORMED_SUCCESS")
        return _classify_success(attempt, data, decode_signed)
    code = parsed.get("code") if isinstance(parsed, dict) else None
    entry = reply_profile.codes.get(code) if isinstance(code, str) else None
    if entry is None or entry[0] != status:
        return attempt.finish(Outcome.UNKNOWN, "UNRECOGNIZED_REPLY")
    _, outcome, reason = entry
    if outcome is Outcome.POLICY_DENY and not _positive_control_allowed(table, store, specimen.profile):
        return attempt.finish(Outcome.UNKNOWN, "POSITIVE_CONTROL_NOT_QUALIFIED")
    return attempt.finish(outcome, reason)


if __name__ == "__main__":
    refuse_module_run()
