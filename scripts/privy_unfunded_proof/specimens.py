"""Frozen synthetic policy-proof specimens and the durable one-use attempt store.

LOCAL and SYNTHETIC_FIXTURE only. This module builds a frozen baseline and a
named mutation table into exact request bytes and SHA-256 identities, and owns
the NOT_SENT -> INTENT_SAVED -> terminal attempt record. It holds no transport,
credential, signer or provider profile. Mutations replace whole frozen words,
one program byte or one transaction field. It is not an ABI encoder. See
docs/qualification/privy-unfunded-proof/CONTRACT.md.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

EVIDENCE_CLASS = "SYNTHETIC_FIXTURE"
PROVIDER_PROOF = "UNQUALIFIED"

MAX_REQUEST_BODY_BYTES = 4096
MAX_RECORD_BYTES = 4096
MAX_SPECIMENS_PER_PROFILE = 32

DESTINATION = "https://api.privy.io/v1/wallets/{wallet_id}/rpc"
HTTP_METHOD = "POST"
WALLETS = {
    "synthetic-probe-wallet-a": "0x00000000000000000000000000000000000000a1",
    "synthetic-probe-wallet-b": "0x00000000000000000000000000000000000000a2",
}
OPERATIONS = ("eth_signTransaction", "personal_sign")
ALLOWED_HEADERS = ("privy-request-expiry",)
PROFILES = ("raw", "decoded")

_ID = re.compile(r"(raw|decoded)\.[a-z0-9_]{1,56}")
_EXPIRY_VALUE = re.compile(r"[0-9]{13}")


class Expected(StrEnum):
    ALLOW = "ALLOW"
    POLICY_DENY = "POLICY_DENY"
    AUTHORIZATION_DENY = "AUTHORIZATION_DENY"
    EXPIRY_REFUSAL = "EXPIRY_REFUSAL"
    DIAGNOSTIC = "DIAGNOSTIC"
    NOT_RUN = "NOT_RUN"


class Category(StrEnum):
    POSITIVE_CONTROL = "POSITIVE_CONTROL"
    FIELD_MUTATION = "FIELD_MUTATION"
    ENVELOPE_VARIANT = "ENVELOPE_VARIANT"
    DIAGNOSTIC = "DIAGNOSTIC"
    AUTHORITY = "AUTHORITY"
    TIMING = "TIMING"
    OPERATION = "OPERATION"


class AttemptState(StrEnum):
    NOT_SENT = "NOT_SENT"
    INTENT_SAVED = "INTENT_SAVED"
    TERMINAL = "TERMINAL"
    UNCERTAIN = "UNCERTAIN"


class SpecimenRefused(Exception):
    """A refusal before any send. ``code`` and ``detail`` are fixed strings."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}:{detail}")
        self.code = code
        self.detail = detail


class SpecimenTableError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EvidenceOverBound(ValueError):
    pass


# ---------------------------------------------------------------- frozen baseline


def _word(value: int) -> str:
    return f"{value:064x}"


def _address(last_byte: int) -> str:
    return "0x" + f"{last_byte:040x}"


ENTRYPOINT = "0xb3e6778480b2E488385E8205eA05E20060B813cb"
SELECTOR = "12345678"
RECEIVER_SELECTOR = "87654321"
APPROVE_SELECTOR = "095ea7b3"
PROGRAM = "a1b2c3d4e5f60718"

# executeSwap words, alias ABI intent/fees: tokenUserBuys, minAmountUserBuys, tokenUserSells,
# amountUserSells, feeCollectorAddress, feeBps, referrerAddress, referrerFeeBps, isInTokenFee.
_TUPLE_WORDS = (
    _word(0xB1), _word(1000000), _word(0xC1), _word(2000000),
    _word(0xD1), _word(10), _word(0xE1), _word(5), _word(0),
)
_PROGRAM_REGION = _word(len(PROGRAM) // 2) + PROGRAM + "00" * (32 - len(PROGRAM) // 2)
BASELINE_DATA = "0x" + SELECTOR + "".join(_TUPLE_WORDS) + _word(320) + _PROGRAM_REGION

BASELINE_TRANSACTION: Mapping[str, Any] = {
    "type": 2,
    "chain_id": 143,
    "to": ENTRYPOINT,
    "value": 0,
    "nonce": 0,
    "gas_limit": 300000,
    "max_fee_per_gas": 100000000000,
    "max_priority_fee_per_gas": 2000000000,
    "data": BASELINE_DATA,
}

DECODED_POLICY_FIELD_PATHS = (
    "executeSwap.intent.tokenUserBuys",
    "executeSwap.intent.minAmountUserBuys",
    "executeSwap.intent.tokenUserSells",
    "executeSwap.intent.amountUserSells",
    "executeSwap.fees.feeCollectorAddress",
    "executeSwap.fees.feeBps",
    "executeSwap.fees.referrerAddress",
    "executeSwap.fees.referrerFeeBps",
    "executeSwap.fees.isInTokenFee",
    "executeSwap.program",
)

# name -> (tuple word index, replacement word)
_WORD_MUTATIONS = {
    "token_user_buys": (0, _word(0xB2)),
    "min_amount_user_buys": (1, _word(999999)),
    "token_user_sells": (2, _word(0xC2)),
    "amount_user_sells": (3, _word(2000001)),
    "fee_collector_address": (4, _word(0xD2)),
    "fee_bps": (5, _word(11)),
    "referrer_address": (6, _word(0xE2)),
    "referrer_fee_bps": (7, _word(6)),
    "is_in_token_fee": (8, _word(1)),
}


def _with_words(replacements: Mapping[int, str]) -> str:
    words = list(_TUPLE_WORDS)
    for index, word in replacements.items():
        words[index] = word
    return "0x" + SELECTOR + "".join(words) + _word(320) + _PROGRAM_REGION


def _calldata_variants() -> dict[str, str]:
    flipped = PROGRAM[:6] + f"{int(PROGRAM[6:8], 16) ^ 0xFF:02x}" + PROGRAM[8:]
    variants = {name: _with_words({index: word}) for name, (index, word) in _WORD_MUTATIONS.items()}
    variants["program_byte_flip"] = BASELINE_DATA.replace(PROGRAM, flipped)
    variants["trailing_word"] = BASELINE_DATA + _word(1)
    variants["receiver_selector"] = (
        "0x" + RECEIVER_SELECTOR + "".join(_TUPLE_WORDS) + _word(352)
        + _word(int(WALLETS["synthetic-probe-wallet-b"], 16)) + _PROGRAM_REGION
    )
    variants["data_hex_case"] = "0x" + BASELINE_DATA[2:].upper()
    variants["program_hex_case"] = BASELINE_DATA.replace(PROGRAM, PROGRAM.upper())
    return variants


# ---------------------------------------------------------------- frozen requests


@dataclass(frozen=True)
class FrozenRequest:
    url: str
    http_method: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    request_sha256: str

    def __repr__(self) -> str:
        return f"FrozenRequest(url={self.url!r}, request_sha256={self.request_sha256!r})"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def envelope_sha256(url: str, http_method: str, headers: tuple[tuple[str, str], ...], body: bytes) -> str:
    envelope = {
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "headers": dict(headers),
        "http_method": http_method,
        "url": url,
    }
    return hashlib.sha256(canonical_json(envelope)).hexdigest()


def headers_are_canonical(headers: object) -> bool:
    """Accept only a sorted, duplicate-free tuple of allowed lowercase names with exact values."""
    if not isinstance(headers, tuple):
        return False
    names: list[str] = []
    for item in headers:
        if not (isinstance(item, tuple) and len(item) == 2 and all(isinstance(part, str) for part in item)):
            return False
        name, value = item
        if name not in ALLOWED_HEADERS or _EXPIRY_VALUE.fullmatch(value) is None:
            return False
        names.append(name)
    return names == sorted(set(names))


def freeze_request(
    wallet_id: str, body: Mapping[str, Any], headers: Mapping[str, str] | None = None
) -> FrozenRequest:
    """Freeze one admitted request. Raises ``SpecimenTableError`` before any effect."""
    if wallet_id not in WALLETS:
        raise SpecimenTableError("UNSUPPORTED_DESTINATION")
    if body.get("method") not in OPERATIONS:
        raise SpecimenTableError("UNSUPPORTED_OPERATION")
    header_items = tuple(sorted((headers or {}).items()))
    if not headers_are_canonical(header_items):
        raise SpecimenTableError("UNSUPPORTED_HEADER")
    body_bytes = canonical_json(body)
    if len(body_bytes) > MAX_REQUEST_BODY_BYTES:
        raise SpecimenTableError("REQUEST_OVER_BOUND")
    url = DESTINATION.format(wallet_id=wallet_id)
    return FrozenRequest(url, HTTP_METHOD, header_items, body_bytes,
                         envelope_sha256(url, HTTP_METHOD, header_items, body_bytes))


def replace_request(request: FrozenRequest, **changes: Any) -> FrozenRequest:
    """Copy a request without re-hashing. The run-time hash check refuses a changed copy."""
    return dataclasses.replace(request, **changes)


# ---------------------------------------------------------------- specimens and table


@dataclass(frozen=True)
class Specimen:
    specimen_id: str
    profile: str
    category: Category
    expected: Expected
    wallet_id: str
    request: FrozenRequest | None
    transaction: Mapping[str, Any] | None
    not_run_reason: str | None = None

    @property
    def is_positive_control(self) -> bool:
        return self.category is Category.POSITIVE_CONTROL


def replace_specimen(specimen: Specimen, **changes: Any) -> Specimen:
    return dataclasses.replace(specimen, **changes)


def _manifest_sha256(rows: Sequence[Specimen]) -> str:
    manifest = [
        [
            s.specimen_id, s.profile, str(s.category), str(s.expected), s.wallet_id,
            s.request.request_sha256 if s.request else None,
            None if s.transaction is None else dict(s.transaction), s.not_run_reason,
        ]
        for s in rows
    ]
    return hashlib.sha256(canonical_json(manifest)).hexdigest()


@dataclass(frozen=True)
class SpecimenTable:
    rows: tuple[Specimen, ...]
    manifest_sha256: str

    def get(self, specimen_id: str) -> Specimen:
        for row in self.rows:
            if row.specimen_id == specimen_id:
                return row
        raise SpecimenRefused("UNKNOWN_SPECIMEN")

    def profile(self, name: str) -> list[Specimen]:
        return [row for row in self.rows if row.profile == name]

    def all(self) -> list[Specimen]:
        return list(self.rows)

    def positive_control(self, profile: str) -> Specimen:
        for row in self.rows:
            if row.profile == profile and row.is_positive_control:
                return row
        raise SpecimenRefused("POSITIVE_CONTROL_NOT_QUALIFIED")

    def manifest_matches_rows(self) -> bool:
        return _manifest_sha256(self.rows) == self.manifest_sha256 == MANIFEST_SHA256


def build_table(rows: Sequence[Specimen], check_frozen: bool = False) -> SpecimenTable:
    """Admit a specimen table. ``check_frozen`` also requires the frozen manifest."""
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row.specimen_id, str) or _ID.fullmatch(row.specimen_id) is None:
            raise SpecimenTableError("MALFORMED_ID")
        if not row.specimen_id.startswith(row.profile + ".") or row.profile not in PROFILES:
            raise SpecimenTableError("MALFORMED_ID")
        if row.specimen_id in seen:
            raise SpecimenTableError("DUPLICATE_ID")
        seen.add(row.specimen_id)
    for profile in PROFILES:
        if sum(row.profile == profile for row in rows) > MAX_SPECIMENS_PER_PROFILE:
            raise SpecimenTableError("OVER_CAP")
    table = SpecimenTable(tuple(rows), _manifest_sha256(rows))
    if check_frozen and table.manifest_sha256 != MANIFEST_SHA256:
        raise SpecimenTableError("MANIFEST_MISMATCH")
    return table


def _sign_body(transaction: Mapping[str, Any]) -> dict[str, Any]:
    return {"method": "eth_signTransaction", "params": {"transaction": dict(transaction)}}


def _row(
    profile: str, name: str, category: Category, expected: Expected, transaction: Mapping[str, Any] | None,
    *, wallet_id: str = "synthetic-probe-wallet-a", body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None, not_run_reason: str | None = None,
) -> Specimen:
    request = None
    if not_run_reason is None:
        request = freeze_request(wallet_id, body if body is not None else _sign_body(transaction or {}), headers)
    return Specimen(f"{profile}.{name}", profile, category, expected, wallet_id, request,
                    None if transaction is None else dict(transaction), not_run_reason)


def _frozen_rows() -> list[Specimen]:
    base = dict(BASELINE_TRANSACTION)
    data = _calldata_variants()
    legacy = {k: v for k, v in base.items() if k not in ("type", "max_fee_per_gas", "max_priority_fee_per_gas")}
    approve = {
        **base,
        "to": _address(0xC1),
        "data": "0x" + APPROVE_SELECTOR + _word(int(ENTRYPOINT, 16)) + _word(2000000),
    }
    field, deny = Category.FIELD_MUTATION, Expected.POLICY_DENY

    def mutated(name: str) -> dict[str, Any]:
        return {**base, "data": data[name]}

    tuple_names = [
        "token_user_sells", "token_user_buys", "amount_user_sells", "min_amount_user_buys",
        "fee_collector_address", "fee_bps", "referrer_address", "referrer_fee_bps", "is_in_token_fee",
    ]
    raw = [
        _row("raw", "baseline", Category.POSITIVE_CONTROL, Expected.ALLOW, base),
        _row("raw", "wrong_chain", field, deny, {**base, "chain_id": 10143}),
        _row("raw", "foreign_wallet", Category.AUTHORITY, Expected.AUTHORIZATION_DENY, base,
             wallet_id="synthetic-probe-wallet-b"),
        _row("raw", "wrong_to", field, deny, {**base, "to": _address(0xF1)}),
        _row("raw", "receiver_selector", field, deny, mutated("receiver_selector")),
        _row("raw", "program_byte_flip", field, deny, mutated("program_byte_flip")),
        _row("raw", "trailing_word", field, deny, mutated("trailing_word")),
        _row("raw", "data_hex_case", Category.DIAGNOSTIC, Expected.DIAGNOSTIC, mutated("data_hex_case")),
        *[_row("raw", name, field, deny, mutated(name)) for name in tuple_names],
        _row("raw", "native_value", field, deny, {**base, "value": 1}),
        _row("raw", "type1_envelope", Category.ENVELOPE_VARIANT, deny,
             {**legacy, "type": 1, "gas_price": base["max_fee_per_gas"]}),
        _row("raw", "type0_envelope", Category.ENVELOPE_VARIANT, deny,
             {**legacy, "type": 0, "gas_price": base["max_fee_per_gas"]}),
        _row("raw", "type4_envelope", Category.ENVELOPE_VARIANT, Expected.NOT_RUN, None,
             not_run_reason="OWNER_AUTHORITY_ABSENT"),
        _row("raw", "gas_limit", field, deny, {**base, "gas_limit": base["gas_limit"] + 1}),
        _row("raw", "max_fee_per_gas", field, deny, {**base, "max_fee_per_gas": base["max_fee_per_gas"] + 1}),
        _row("raw", "max_priority_fee_per_gas", field, deny,
             {**base, "max_priority_fee_per_gas": base["max_priority_fee_per_gas"] + 1}),
        _row("raw", "window_at_t", Category.TIMING, deny, base),
        _row("raw", "window_after_t", Category.TIMING, deny, base),
        _row("raw", "request_expiry", Category.TIMING, Expected.EXPIRY_REFUSAL, base,
             headers={"privy-request-expiry": "1792000000000"}),
        _row("raw", "allowance_approve", Category.OPERATION, deny, approve),
        _row("raw", "personal_sign", Category.OPERATION, deny, None,
             body={"method": "personal_sign",
                   "params": {"message": "edge-os synthetic inert probe text", "encoding": "utf-8"}}),
        _row("raw", "post_removal", Category.AUTHORITY, Expected.AUTHORIZATION_DENY, base),
    ]
    decoded = [
        _row("decoded", "baseline", Category.POSITIVE_CONTROL, Expected.ALLOW, base),
        _row("decoded", "program_byte_flip", field, deny, mutated("program_byte_flip")),
        _row("decoded", "program_hex_case", Category.DIAGNOSTIC, Expected.DIAGNOSTIC, mutated("program_hex_case")),
        _row("decoded", "trailing_word", field, deny, mutated("trailing_word")),
        *[_row("decoded", name, field, deny, mutated(name)) for name in tuple_names],
        _row("decoded", "receiver_selector", field, deny, mutated("receiver_selector")),
    ]
    return raw + decoded


MANIFEST_SHA256 = "a7a922b04b445798e8f2ff2ff8c19d4b6904652a5471201f26dcff047f125ff9"
FROZEN_TABLE = build_table(_frozen_rows(), check_frozen=False)


# ---------------------------------------------------------------- durable attempts


def encode_bounded_record(record: Mapping[str, Any], limit: int = MAX_RECORD_BYTES) -> bytes:
    data = canonical_json(record)
    if len(data) > limit:
        raise EvidenceOverBound("record exceeds the local evidence bound")
    return data


class AttemptStore:
    """One directory of exclusive-create attempt files. The key is the specimen ID only."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, specimen_id: str, kind: str) -> Path:
        return self.root / f"{specimen_id}.{kind}.json"

    def _create(self, path: Path, data: bytes) -> None:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            remaining = memoryview(data)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError("record write made no progress")
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def state(self, specimen_id: str) -> AttemptState:
        intent_path = self._path(specimen_id, "intent")
        if not intent_path.exists():
            return AttemptState.NOT_SENT
        intent = self._read(intent_path)
        if intent is None or intent.get("specimen_id") != specimen_id or intent.get("state") != "INTENT_SAVED":
            return AttemptState.UNCERTAIN
        outcome_path = self._path(specimen_id, "outcome")
        if not outcome_path.exists():
            return AttemptState.INTENT_SAVED
        outcome = self._read(outcome_path)
        if outcome is None or outcome.get("specimen_id") != specimen_id or "outcome" not in outcome:
            return AttemptState.UNCERTAIN
        return AttemptState.TERMINAL

    def claim(self, specimen: Specimen, at: str) -> None:
        """Save intent with exclusive create and fsync. One claimant wins."""
        if specimen.request is None:
            raise SpecimenRefused("NOT_RUN", specimen.not_run_reason or "")
        record = {
            "specimen_id": specimen.specimen_id,
            "profile": specimen.profile,
            "request_sha256": specimen.request.request_sha256,
            "destination": specimen.request.url,
            "http_method": specimen.request.http_method,
            "state": "INTENT_SAVED",
            "intent_at": at,
            "evidence_class": EVIDENCE_CLASS,
        }
        try:
            self._create(self._path(specimen.specimen_id, "intent"), encode_bounded_record(record))
        except FileExistsError:
            raise SpecimenRefused("ALREADY_CLAIMED") from None
        except (OSError, EvidenceOverBound):
            raise SpecimenRefused("INTENT_NOT_PERSISTED") from None

    def write_capture(self, specimen_id: str, record: Mapping[str, Any]) -> bytes:
        data = encode_bounded_record(record)
        self._create(self._path(specimen_id, "capture"), data)
        return data

    def write_outcome(self, specimen_id: str, record: Mapping[str, Any]) -> None:
        self._create(self._path(specimen_id, "outcome"), encode_bounded_record(record))

    def read_outcome(self, specimen_id: str) -> dict[str, Any] | None:
        if self.state(specimen_id) is not AttemptState.TERMINAL:
            return None
        return self._read(self._path(specimen_id, "outcome"))

    def stop(self, record: Mapping[str, Any]) -> None:
        try:
            self._create(self.root / "STOP.json", encode_bounded_record(record))
        except FileExistsError:
            pass

    def is_stopped(self) -> bool:
        return (self.root / "STOP.json").exists()

    def blocking_attempt(self, excluding: str) -> str | None:
        """Return a refusal code if another attempt is unresolved or breached."""
        for intent in sorted(self.root.glob("*.intent.json")):
            specimen_id = intent.name[: -len(".intent.json")]
            if specimen_id == excluding:
                continue
            if self.state(specimen_id) is not AttemptState.TERMINAL:
                return "UNRESOLVED_ATTEMPT_IN_STORE"
            outcome = self._read(self._path(specimen_id, "outcome")) or {}
            if outcome.get("outcome") == "BREACH":
                return "STOPPED_AFTER_BREACH"
        return None


def refuse_module_run() -> None:
    print("refused: local synthetic driver has no actual runner", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    refuse_module_run()
