"""Qualified actual reply/decoder profiles and their code-owned registry.

LOCAL only. The synthetic ``ReplyProfile`` in ``evidence.py`` refuses every
qualification other than ``SYNTHETIC``. This module is the successor boundary
for an api where the provider reply schema and the signed-field decoder are
actually qualified. Exactly one profile is registered: the Privy raw profile
for the frozen policy-layer packet. Every other profile id refuses with
``ACTUAL_PROFILE_UNQUALIFIED`` before any effect.

A profile binds one of the two accepted specimen profiles (``raw`` or
``decoded``) to:
- a reply classifier (a code -> status/outcome/reason table), and
- a signed-transaction decoder that verifies the full decoded key set, exact
  value types and every original field of the accepted unsigned transaction.

The decoder reuses ``edge_os_api.execution.original_transaction.validate_signed``
as the accepted qualified decoder; that helper checks the type-2 fields, the
sender and the canonical encoding and returns the Keccak-256 hash of the whole
signed serialization.

Gate F6 is resolved by the accepted Phase B helper. ``validate_signed`` now
requires the complete expected key set, the complete decoded key set and the
exact value types before it compares any field. This module therefore binds that
helper as the one qualified raw decoder. Do not register an arbitrary callable
as a qualified decoder.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from edge_os_api.execution.original_transaction import validate_signed
from scripts.privy_unfunded_proof.evidence import Outcome
from scripts.privy_unfunded_proof.specimens import PROFILES, SpecimenRefused

ACTUAL_PROFILE_UNQUALIFIED = "ACTUAL_PROFILE_UNQUALIFIED"

# The outcome values a qualified profile may treat as a denial of the specimen.
DENIAL_OUTCOMES: frozenset[str] = frozenset(
    {Outcome.POLICY_DENY.value, Outcome.AUTHORIZATION_DENY.value, "EXPIRY_REFUSAL"}
)


class ActualProfileUnqualified(ValueError):
    """A reply profile was constructed outside the accepted qualified shape."""


@dataclass(frozen=True)
class SignedDecode:
    """The result of decoding and verifying one signed transaction.

    ``matched`` is true only when every accepted field and the sender match.
    ``reasons`` are fixed codes. ``signed_bytes_sha256`` is the SHA-256 of the
    signed bytes held in memory; the bytes themselves are never saved.
    """

    matched: bool
    reasons: tuple[str, ...]
    signed_bytes_sha256: str


@dataclass(frozen=True)
class QualifiedActualProfile:
    """A reply classifier and signed-field decoder for one accepted profile.

    Constructing one does not qualify it. Only a matching entry in
    ``QUALIFIED_ACTUAL_PROFILES`` admits it for a run.
    """

    profile: str
    qualification: str
    codes: Mapping[str, tuple[int, str, str]]
    decoder_factory: Callable[[Mapping[str, Any], str], Callable[[bytes], SignedDecode]]

    def __post_init__(self) -> None:
        if self.qualification != "QUALIFIED":
            raise ActualProfileUnqualified("actual reply profiles are UNQUALIFIED in this unit")
        if self.profile not in PROFILES:
            raise ActualProfileUnqualified(f"unknown profile {self.profile!r}")
        if not isinstance(self.codes, Mapping) or not self.codes:
            raise ActualProfileUnqualified("a qualified profile must classify at least one reply code")
        for code, entry in self.codes.items():
            if not isinstance(code, str) or len(entry) != 3 or not isinstance(entry[0], int):
                raise ActualProfileUnqualified("a code entry must be (status, outcome, reason)")
            if entry[1] not in {outcome.value for outcome in Outcome}:
                raise ActualProfileUnqualified(f"unknown outcome {entry[1]!r}")
            if not isinstance(entry[2], str) or not entry[2]:
                raise ActualProfileUnqualified("a code entry needs a fixed reason")
        if not callable(self.decoder_factory):
            raise ActualProfileUnqualified("decoder_factory must be callable")

    def denial(self, outcome: str) -> bool:
        return outcome in DENIAL_OUTCOMES


def accepted_signed_decoder(unsigned: Mapping[str, Any], wallet: str) -> Callable[[bytes], SignedDecode]:
    """Bind the accepted ``validate_signed`` helper to one unsigned transaction and wallet.

    ``unsigned`` is the frozen type-2 transaction in the accepted snake-case
    shape; ``wallet`` is the exact agent wallet address. The returned callable
    verifies every field and the sender, and returns the SHA-256 of the signed
    bytes. It never returns or saves the signed bytes.
    """

    def decode(raw: bytes) -> SignedDecode:
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        try:
            transaction_hash, reasons = validate_signed("0x" + raw.hex(), unsigned, wallet)
        except Exception:  # noqa: BLE001 - untrusted bytes: any decoder failure is a fixed refusal
            return SignedDecode(False, ("SIGNED_BYTES_MALFORMED",), digest)
        return SignedDecode(transaction_hash is not None, tuple(reasons), digest)

    return decode


# The documented Privy refusal codes. Privy documents a 400 ``policy_violation``
# for a denied signing request; the first negative in the frozen packet confirms
# the observed status and body path before any later specimen runs.
PRIVY_POLICY_CODES: Mapping[str, tuple[int, str, str]] = {
    "policy_violation": (400, Outcome.POLICY_DENY.value, "PRIVY_POLICY_VIOLATION"),
    "request_expired": (400, Outcome.UNKNOWN.value, "EXPIRY_REFUSAL"),
    "zero_correct_authorization_signatures": (
        401, Outcome.AUTHORIZATION_DENY.value, "PRIVY_AUTHORIZATION_DENIED",
    ),
}

PRIVY_RAW_V1 = QualifiedActualProfile(
    profile="raw",
    qualification="QUALIFIED",
    codes=PRIVY_POLICY_CODES,
    decoder_factory=accepted_signed_decoder,
)

# Code-owned qualified-profile registry. Exactly one profile is registered.
QUALIFIED_ACTUAL_PROFILES: Mapping[str, QualifiedActualProfile] = {"privy.raw.v1": PRIVY_RAW_V1}


def resolve_qualified_profile(profile_id: str) -> QualifiedActualProfile:
    """Return the code-registered qualified profile, or refuse before any effect."""
    profile = QUALIFIED_ACTUAL_PROFILES.get(profile_id)
    if profile is None or profile.qualification != "QUALIFIED":
        raise SpecimenRefused(ACTUAL_PROFILE_UNQUALIFIED, profile_id)
    return profile


if __name__ == "__main__":
    from scripts.privy_unfunded_proof.specimens import refuse_module_run

    refuse_module_run()
