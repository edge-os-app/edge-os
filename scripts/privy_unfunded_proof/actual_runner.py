"""One LOCAL unfunded actual policy-proof attempt.

LOCAL only. ``run_actual_specimen`` resolves a code-owned approved packet and a
code-owned qualified reply/decoder profile, admits one frozen specimen, saves an
immutable one-use intent with ``O_EXCL``/``fsync`` before a single sign-only
send, rechecks the stop marker after the claim and before the send, captures
bounded sanitized reply metadata before any parse, then classifies the reply
with the qualified profile. The accepted durable store, capture shape and
signed-field decoder are reused unchanged.

Every result is ``LOCAL_TESTED``/``UNQUALIFIED``. No provider request, credential,
wallet, policy, signature or broadcast exists in this unit: the code-owned
approval registries are empty, so the default actual run refuses. Reply bodies,
authorization signatures, credentials, signed bytes and unknown error strings
are never saved, logged or re-raised. See
docs/qualification/privy-unfunded-proof/CONTRACT.md.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from scripts.privy_unfunded_proof.actual_packet import (
    ACTUAL_EVIDENCE_CLASS,
    PROVIDER_PROOF_UNQUALIFIED,
    ActualProofPacket,
    OwnerBoundType4Authority,
    resolve_approved_packet,
    resolve_type4_authority,
)
from scripts.privy_unfunded_proof.actual_profile import QualifiedActualProfile, resolve_qualified_profile
from scripts.privy_unfunded_proof.actual_transport import TransportLost, TransportRefused
from scripts.privy_unfunded_proof.evidence import Outcome, RunResult
from scripts.privy_unfunded_proof.specimens import (
    FROZEN_TABLE,
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
    replace_specimen,
)

MAX_REPLY_BYTES = 16384
MAX_CONTENT_TYPE_CHARS = 128

# Expected outcomes that end one capability test. A success for any of these is a breach.
_DENIAL_EXPECTATIONS = (Expected.POLICY_DENY, Expected.AUTHORIZATION_DENY, Expected.EXPIRY_REFUSAL)
_NON_STOPPING_UNKNOWN = ("EXPIRY_REFUSAL",)


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
    if content_type is None:
        # The accepted HttpTransport seam returns HttpResponse(status, headers, body).
        headers = getattr(reply, "headers", None)
        if isinstance(headers, Mapping):
            content_type = next((value for name, value in headers.items()
                                 if str(name).lower() == "content-type"), None)
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
    if content_type is None:
        return None
    media = content_type.split(";")[0].strip().lower()
    return "application/json" if media == "application/json" else "OTHER"


def _frozen_unsigned(request: FrozenRequest) -> Mapping[str, Any] | None:
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    params = body.get("params") if isinstance(body, dict) else None
    transaction = params.get("transaction") if isinstance(params, dict) else None
    return transaction if isinstance(transaction, Mapping) else None


def _positive_control_allowed(table: SpecimenTable, store: AttemptStore, profile: str) -> bool:
    control = table.positive_control(profile)
    record = store.read_outcome(control.specimen_id)
    return record is not None and record.get("outcome") == Outcome.ALLOW.value


class _ActualAttempt:
    """One claimed actual specimen. Every exit writes at most one outcome record."""

    def __init__(self, specimen: Specimen, packet: ActualProofPacket, profile_id: str,
                 store: AttemptStore, clock: Callable[[], str]) -> None:
        self.specimen = specimen
        self.packet = packet
        self.profile_id = profile_id
        self.store = store
        self.clock = clock
        self.capture_sha256: str | None = None
        self.extra: dict[str, Any] = {}

    def _stop(self, reason: str) -> None:
        try:
            self.store.stop({"specimen_id": self.specimen.specimen_id, "reason": reason, "at": self.clock()})
        except (OSError, EvidenceOverBound):
            pass

    def finish(self, outcome: Outcome, reason: str) -> RunResult:
        expected = self.specimen.expected
        result = RunResult(
            self.specimen.specimen_id, self.specimen.profile, expected.value, outcome, reason,
            _matches(expected, outcome, reason), ACTUAL_EVIDENCE_CLASS, PROVIDER_PROOF_UNQUALIFIED,
        )
        if outcome is Outcome.BREACH or (outcome is Outcome.UNKNOWN and reason not in _NON_STOPPING_UNKNOWN):
            self._stop(reason)
        record = {
            "specimen_id": result.specimen_id,
            "profile": result.profile,
            "packet_id": self.packet.packet_id,
            "reply_profile_id": self.profile_id,
            "request_sha256": self.specimen.request.request_sha256 if self.specimen.request else None,
            "expected": result.expected,
            "outcome": outcome.value,
            "reason": reason,
            "matches_expectation": result.matches_expectation,
            "capture_record_sha256": self.capture_sha256,
            "evidence_class": ACTUAL_EVIDENCE_CLASS,
            "provider_proof": PROVIDER_PROOF_UNQUALIFIED,
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
                             "OUTCOME_NOT_PERSISTED", False, ACTUAL_EVIDENCE_CLASS, PROVIDER_PROOF_UNQUALIFIED)
        return result

    def capture(self, reply: object) -> tuple[int | None, str | None, bytes, bool] | None:
        status, content_type, body, valid = _metadata(reply)
        record = {
            "specimen_id": self.specimen.specimen_id,
            "profile": self.specimen.profile,
            "packet_id": self.packet.packet_id,
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
            "evidence_class": ACTUAL_EVIDENCE_CLASS,
        }
        try:
            saved = self.store.write_capture(self.specimen.specimen_id, record)
        except (OSError, EvidenceOverBound):
            self._stop("CAPTURE_FAILED")
            return None
        self.capture_sha256 = hashlib.sha256(saved).hexdigest()
        return status, content_type, body, valid


def _matches(expected: Expected, outcome: Outcome, reason: str) -> bool:
    if expected is Expected.EXPIRY_REFUSAL:
        return outcome is Outcome.UNKNOWN and reason == "EXPIRY_REFUSAL"
    if expected is Expected.DIAGNOSTIC:
        return outcome in (Outcome.ALLOW, Outcome.POLICY_DENY)
    return outcome.value == expected.value


def _success_verdict(
    attempt: _ActualAttempt, data: Mapping[str, Any], unsigned: Mapping[str, Any] | None,
    profile: QualifiedActualProfile,
) -> tuple[Outcome, str]:
    """Classify one success envelope without writing. Used by the normal and failed-capture paths."""
    specimen = attempt.specimen
    signed = _hex_bytes(data.get("signed_transaction"))
    signature = _hex_bytes(data.get("signature"))
    if signed is None and signature is None:
        return Outcome.UNKNOWN, "MALFORMED_SUCCESS"
    attempt.extra["signed_bytes_sha256"] = hashlib.sha256(
        signed if signed is not None else signature).hexdigest()
    if specimen.expected in _DENIAL_EXPECTATIONS:
        return Outcome.BREACH, "ALLOWED_WHERE_DENIAL_REQUIRED"
    if signed is None or unsigned is None:
        return Outcome.UNKNOWN, "MALFORMED_SUCCESS"
    try:
        decoded = profile.decoder_factory(unsigned, attempt.packet.wallet_address)(signed)
    except Exception:  # noqa: BLE001 - decoder messages may carry signed bytes; keep a fixed reason
        return Outcome.UNKNOWN, "DECODE_FAILED"
    attempt.extra["signed_bytes_sha256"] = decoded.signed_bytes_sha256
    if not decoded.matched:
        attempt.extra["signed_field_reasons"] = list(decoded.reasons)
        return Outcome.BREACH, "SIGNED_FIELDS_MISMATCH"
    return Outcome.ALLOW, "SIGNED_FIELDS_MATCH"


def _classify_success(
    attempt: _ActualAttempt, data: Mapping[str, Any], unsigned: Mapping[str, Any] | None,
    profile: QualifiedActualProfile,
) -> RunResult:
    return attempt.finish(*_success_verdict(attempt, data, unsigned, profile))


def _in_memory_success_data(reply: object) -> Mapping[str, Any] | None:
    """Parse a bounded in-memory success reply without writing, for the failed-capture path."""
    status, content_type, body, valid = _metadata(reply)
    if not valid or status != 200 or len(body) > MAX_REPLY_BYTES:
        return None
    if content_type is None or content_type.split(";")[0].strip().lower() != "application/json":
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    data = parsed.get("data") if isinstance(parsed, dict) else None
    return data if isinstance(data, dict) else None


def _admit(
    specimen_id: str, packet: ActualProofPacket, store: AttemptStore, table: SpecimenTable,
    type4_authority_id: str | None, type4_authorities: Mapping[str, OwnerBoundType4Authority] | None,
) -> tuple[Specimen, FrozenRequest]:
    if not table.manifest_matches_rows():
        raise SpecimenRefused("MANIFEST_MISMATCH")
    accepted = table.get(specimen_id)
    try:
        effective = Expected(packet.specimen_expected.get(specimen_id, ""))
    except ValueError:
        raise SpecimenRefused("MATRIX_NOT_COVERED", specimen_id) from None
    specimen = replace_specimen(accepted, expected=effective)
    if effective is Expected.NOT_RUN:
        detail = "OWNER_AUTHORITY_ABSENT" if type4_authority_id is None else "SYNTHETIC_AUTHORITY_NOT_PROOF"
        raise SpecimenRefused("NOT_RUN", detail)
    request = packet.request_for(specimen_id)
    if not headers_are_canonical(request.headers):
        raise SpecimenRefused("MALFORMED_REQUEST_HEADERS")
    if envelope_sha256(request.url, request.http_method, request.headers, request.body) != request.request_sha256:
        raise SpecimenRefused("REQUEST_BYTES_CHANGED")
    if len(request.body) > packet.request_byte_ceiling:
        raise SpecimenRefused("REQUEST_OVER_BOUND", specimen_id)
    if accepted.request is None:
        # A rebinding of the type-4 placeholder onto a runnable negative control needs a
        # valid owner-bound authority before its request may be sent.
        resolve_type4_authority(type4_authority_id, owner_id=packet.owner_id, authorities=type4_authorities)
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


def run_actual_specimen(
    specimen_id: str,
    *,
    store: AttemptStore,
    transport: object,
    packet_id: str,
    profile_id: str,
    clock: Callable[[], str],
    now_epoch: int,
    started_at_epoch: int,
    table: SpecimenTable = FROZEN_TABLE,
    type4_authority_id: str | None = None,
    approvals: Mapping[str, ActualProofPacket] | None = None,
    profiles: Mapping[str, QualifiedActualProfile] | None = None,
    type4_authorities: Mapping[str, OwnerBoundType4Authority] | None = None,
) -> RunResult:
    """Run one actual specimen at most once. Raises ``SpecimenRefused`` before any effect.

    ``transport`` must expose ``send(request) -> response`` (see
    ``ActualSignOnlyTransport``). The accepted reply has ``status``,
    ``content_type`` and ``body`` attributes.
    """
    packet = resolve_approved_packet(packet_id, now_epoch=now_epoch, table=table, approvals=approvals)
    profile = resolve_qualified_profile(profile_id, profiles=profiles)
    if now_epoch - started_at_epoch > packet.time_ceiling_seconds:
        raise SpecimenRefused("TIME_CEILING_EXCEEDED")
    specimen, request = _admit(specimen_id, packet, store, table, type4_authority_id, type4_authorities)
    if profile.profile != specimen.profile:
        raise SpecimenRefused("ACTUAL_PROFILE_UNQUALIFIED", profile_id)
    store.claim_record(specimen_id, {
        "specimen_id": specimen_id,
        "profile": specimen.profile,
        "packet_id": packet.packet_id,
        "attempt_identity": packet.attempt_identity_for(specimen_id),
        "reply_profile_id": profile_id,
        "policy_id": packet.profile_policies[specimen.profile],
        "request_sha256": request.request_sha256,
        "destination": request.url,
        "http_method": request.http_method,
        "state": "INTENT_SAVED",
        "intent_at": clock(),
        "evidence_class": ACTUAL_EVIDENCE_CLASS,
    })
    attempt = _ActualAttempt(specimen, packet, profile_id, store, clock)
    # Recheck the stop marker after the claim and immediately before the send.
    if store.is_stopped():
        return attempt.finish(Outcome.UNKNOWN, "STOPPED_AFTER_CLAIM")
    try:
        reply = transport.send(request)  # type: ignore[attr-defined]
    except TransportRefused:
        # Nothing was sent, but the one-use intent is already claimed.
        return attempt.finish(Outcome.UNKNOWN, "SEND_REFUSED")
    except TransportLost:
        return attempt.finish(Outcome.UNKNOWN, "SEND_LOST")
    except Exception:  # noqa: BLE001 - transport errors may carry secrets; keep a fixed reason
        return attempt.finish(Outcome.UNKNOWN, "SEND_FAILED")
    captured = attempt.capture(reply)
    if captured is None:
        # A failed capture write must not hide a breach-shaped reply still held in memory.
        data = _in_memory_success_data(reply)
        if data is not None:
            verdict = _success_verdict(attempt, data, _frozen_unsigned(request), profile)
            if verdict[0] is Outcome.BREACH:
                return attempt.finish(*verdict)
        return RunResult(specimen_id, specimen.profile, specimen.expected.value, Outcome.UNKNOWN,
                         "CAPTURE_FAILED", False, ACTUAL_EVIDENCE_CLASS, PROVIDER_PROOF_UNQUALIFIED)
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
        return _classify_success(attempt, data, _frozen_unsigned(request), profile)
    code = parsed.get("code") if isinstance(parsed, dict) else None
    entry = profile.codes.get(code) if isinstance(code, str) else None
    if entry is None or entry[0] != status:
        return attempt.finish(Outcome.UNKNOWN, "UNRECOGNIZED_REPLY")
    _, outcome_value, reason = entry
    if profile.denial(outcome_value) and not _positive_control_allowed(table, store, specimen.profile):
        return attempt.finish(Outcome.UNKNOWN, "POSITIVE_CONTROL_NOT_QUALIFIED")
    return attempt.finish(Outcome(outcome_value), reason)


if __name__ == "__main__":
    refuse_module_run()
