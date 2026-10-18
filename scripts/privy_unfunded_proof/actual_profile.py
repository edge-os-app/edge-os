"""Qualified actual reply/decoder profiles and their code-owned registry.

LOCAL only. The synthetic ``ReplyProfile`` in ``evidence.py`` refuses every
qualification other than ``SYNTHETIC``. This module is the successor boundary
for an api where the provider reply schema and the signed-field decoder are
actually qualified. No qualified profile is registered here: the registry is
empty, so an actual run refuses with ``ACTUAL_PROFILE_UNQUALIFIED`` before any
effect.

A profile binds one of the two accepted specimen profiles (``raw`` or
``decoded``) to:
- a reply classifier (a code -> status/outcome/reason table), and
- a signed-transaction decoder that verifies the full decoded key set, exact
  value types and every original field of the accepted unsigned transaction.

The decoder reuses ``edge_os_api.execution.original_transaction.validate_signed``
as the accepted qualified decoder; that helper checks the type-2 fields, the
sender and the canonical encoding and returns the Keccak-256 hash of the whole
signed serialization.
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
            if entry[1] not in {outcome.value for outcome in Outcome} and entry[1] not in DENIAL_OUTCOMES:
                raise ActualProfileUnqualified(f"unknown outcome {entry[1]!r}")
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


# Code-owned qualified-profile registry. It is empty: no actual reply schema or
# decoder profile is qualified in this unit.
QUALIFIED_ACTUAL_PROFILES: Mapping[str, QualifiedActualProfile] = {}


def resolve_qualified_profile(
    profile_id: str, *, profiles: Mapping[str, QualifiedActualProfile] | None = None
) -> QualifiedActualProfile:
    """Return the code-registered qualified profile, or refuse before any effect."""
    registry = QUALIFIED_ACTUAL_PROFILES if profiles is None else profiles
    profile = registry.get(profile_id)
    if profile is None or profile.qualification != "QUALIFIED":
        raise SpecimenRefused(ACTUAL_PROFILE_UNQUALIFIED, profile_id)
    return profile


if __name__ == "__main__":
    from scripts.privy_unfunded_proof.specimens import refuse_module_run

    refuse_module_run()
