"""Frozen exact actual proof packet and its code-owned approval registry.

LOCAL only. This module defines the exact, frozen inputs one unfunded actual
policy-proof run would need, and the code-owned approval a run must resolve
before it may touch a credential or open a socket. It performs no I/O, reads no
credential and holds no transport.

A packet is admitted only when the *code* registers it in
``CODE_OWNED_PACKET_APPROVALS``; no caller argument, flag, environment value or
Boolean can approve one. That registry is empty here, so every default actual
run refuses with ``ACTUAL_PACKET_NOT_APPROVED``. The packet binds the app, the
owner, a policy-resource owner outside executor control, the wallet, the
network, the signing route, the per-profile policy identities and content
hashes, the source and deployed code identities, expiry, the auth-header
expiry, the one-use attempt identity, the exact frozen request bytes per
specimen, the per-profile specimen manifest and the count/byte/time ceilings,
together with the twelve P21 mandatory controls and the separate
position-inventory obligation.

See docs/qualification/privy-unfunded-proof/CONTRACT.md.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from scripts.privy_unfunded_proof.specimens import (
    FROZEN_TABLE,
    MAX_REQUEST_BODY_BYTES,
    MAX_SPECIMENS_PER_PROFILE,
    PROFILES,
    Expected,
    FrozenRequest,
    SpecimenRefused,
    SpecimenTable,
    canonical_json,
)

ACTUAL_EVIDENCE_CLASS = "LOCAL_TESTED"
PROVIDER_PROOF_UNQUALIFIED = "UNQUALIFIED"

# The twelve P21 mandatory controls, in the order of CONTROL_RESTRICTIONS.md.
MANDATORY_CONTROLS: tuple[str, ...] = (
    "chain",
    "wallet_signer_binding",
    "entrypoint_method",
    "input_output_assets",
    "raw_input",
    "recipient",
    "minimum_output",
    "fees",
    "approvals",
    "gas_action_capacity",
    "expiry_freshness",
    "opaque_program",
)
POSITION_INVENTORY = "position_inventory"

# Refusal codes produced before any effect.
ACTUAL_PACKET_NOT_APPROVED = "ACTUAL_PACKET_NOT_APPROVED"
ACTUAL_PACKET_MISMATCH = "ACTUAL_PACKET_MISMATCH"
ACTUAL_PACKET_EXPIRED = "ACTUAL_PACKET_EXPIRED"
POLICY_ADMIN_OWNER_MISSING = "POLICY_ADMIN_OWNER_MISSING"
POLICY_ADMIN_NOT_SEPARATED = "POLICY_ADMIN_NOT_SEPARATED"
MANDATORY_CONTROL_UNQUALIFIED = "MANDATORY_CONTROL_UNQUALIFIED"
POSITION_INVENTORY_UNQUALIFIED = "POSITION_INVENTORY_UNQUALIFIED"
PROFILE_POLICY_NOT_SEPARATED = "PROFILE_POLICY_NOT_SEPARATED"
PROFILE_POLICY_UNBOUND = "PROFILE_POLICY_UNBOUND"
MATRIX_NOT_COVERED = "MATRIX_NOT_COVERED"
PACKET_CEILING_INVALID = "PACKET_CEILING_INVALID"
REQUEST_COUNT_EXCEEDED = "REQUEST_COUNT_EXCEEDED"
REQUEST_OVER_BOUND = "REQUEST_OVER_BOUND"
TIME_CEILING_EXCEEDED = "TIME_CEILING_EXCEEDED"
REQUEST_PROFILE_UNQUALIFIED = "REQUEST_PROFILE_UNQUALIFIED"
DESTINATION_UNQUALIFIED = "DESTINATION_UNQUALIFIED"
TRANSPORT_NOT_BOUND = "TRANSPORT_NOT_BOUND"
TRANSPORT_BINDING_MISMATCH = "TRANSPORT_BINDING_MISMATCH"
STOPPED_AFTER_UNKNOWN = "STOPPED_AFTER_UNKNOWN"
OWNER_AUTHORITY_ABSENT = "OWNER_AUTHORITY_ABSENT"
AUTHORITY_NOT_OWNER_BOUND = "AUTHORITY_NOT_OWNER_BOUND"
SYNTHETIC_AUTHORITY_NOT_PROOF = "SYNTHETIC_AUTHORITY_NOT_PROOF"


_AUTH_HEADER_EXPIRY = re.compile(r"[0-9]{13}")


class ControlState(StrEnum):
    """The evidence class of one mandatory control.

    ``DOCUMENTED``, ``SOURCE_INSPECTED`` and ``LOCAL_TESTED`` are declarable and
    do not block admission by themselves. ``UNKNOWN``, ``UNSUPPORTED``,
    ``UNSET`` and ``NOT_RUN`` block the affected real action. ``ENFORCED`` and
    ``PROVIDER_ACTUAL`` claim an actual provider result and are not fabricated
    by this unit.
    """

    DOCUMENTED = "DOCUMENTED"
    SOURCE_INSPECTED = "SOURCE_INSPECTED"
    LOCAL_TESTED = "LOCAL_TESTED"
    PROVIDER_ACTUAL = "PROVIDER_ACTUAL"
    ENFORCED = "ENFORCED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    UNSET = "UNSET"
    NOT_RUN = "NOT_RUN"


BLOCKING_CONTROL_STATES = frozenset(
    {ControlState.UNKNOWN, ControlState.UNSUPPORTED, ControlState.UNSET, ControlState.NOT_RUN}
)


def _is_identity(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _request_projection(request: FrozenRequest) -> dict[str, Any]:
    return {
        "url": request.url,
        "http_method": request.http_method,
        "headers": [list(item) for item in request.headers],
        "body_sha256": hashlib.sha256(request.body).hexdigest(),
        "request_sha256": request.request_sha256,
    }


@dataclass(frozen=True)
class ActualProofPacket:
    """The frozen, exact inputs of one unfunded actual proof run.

    It is data. Constructing one does not approve it. Only a matching entry in
    ``CODE_OWNED_PACKET_APPROVALS`` admits it, after every field below is re-checked.
    """

    packet_id: str
    app_id: str
    executor_id: str
    owner_id: str
    policy_resource_owner_id: str
    wallet_id: str
    wallet_address: str
    network_id: str
    chain_id: int
    signing_url: str
    signing_method: str
    profile_policies: Mapping[str, str]
    profile_policy_sha256: Mapping[str, str]
    source_code_id: str
    deployed_code_id: str
    expires_at_epoch: int
    auth_header_expiry: str
    attempt_identity: str
    requests: Mapping[str, FrozenRequest]
    specimen_expected: Mapping[str, str]
    request_count_ceiling: int
    request_byte_ceiling: int
    time_ceiling_seconds: int
    controls: Mapping[str, ControlState]
    position_inventory: ControlState

    def request_for(self, specimen_id: str) -> FrozenRequest:
        try:
            return self.requests[specimen_id]
        except KeyError:
            raise SpecimenRefused(MATRIX_NOT_COVERED, specimen_id) from None

    def attempt_identity_for(self, specimen_id: str) -> str:
        """The one-use attempt identity for one specimen, derived from the frozen prefix."""
        return f"{self.attempt_identity}:{specimen_id}"

    def _projection(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "executor_id": self.executor_id,
            "owner_id": self.owner_id,
            "policy_resource_owner_id": self.policy_resource_owner_id,
            "wallet_id": self.wallet_id,
            "wallet_address": self.wallet_address,
            "network_id": self.network_id,
            "chain_id": self.chain_id,
            "signing_url": self.signing_url,
            "signing_method": self.signing_method,
            "profile_policies": dict(self.profile_policies),
            "profile_policy_sha256": dict(self.profile_policy_sha256),
            "source_code_id": self.source_code_id,
            "deployed_code_id": self.deployed_code_id,
            "expires_at_epoch": self.expires_at_epoch,
            "auth_header_expiry": self.auth_header_expiry,
            "attempt_identity": self.attempt_identity,
            "requests": {sid: _request_projection(req) for sid, req in sorted(self.requests.items())},
            "specimen_expected": dict(self.specimen_expected),
            "request_count_ceiling": self.request_count_ceiling,
            "request_byte_ceiling": self.request_byte_ceiling,
            "time_ceiling_seconds": self.time_ceiling_seconds,
            "controls": {name: str(state) for name, state in sorted(self.controls.items())},
            "position_inventory": str(self.position_inventory),
        }

    def packet_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self._projection())).hexdigest()


def build_packet(**fields: Any) -> ActualProofPacket:
    """Freeze a packet and bind its content hash into ``packet_id``."""
    packet = ActualProofPacket(packet_id="", **fields)
    return dataclasses.replace(packet, packet_id=packet.packet_sha256())


@dataclass(frozen=True)
class OwnerBoundType4Authority:
    """A valid owner-bound type-4 self-authorization. Never saved or logged.

    An absent authority keeps a type-4 specimen ``NOT_RUN``. A synthetic or
    unrelated authority object is not delegation proof."""
    authority_id: str
    owner_id: str


# Code-owned approval registry. It is empty: no packet is approved in this unit.
CODE_OWNED_PACKET_APPROVALS: Mapping[str, ActualProofPacket] = {}

# Code-owned type-4 authority registry. It is empty: no authority exists here.
CODE_OWNED_TYPE4_AUTHORITIES: Mapping[str, OwnerBoundType4Authority] = {}


def resolve_type4_authority(
    authority_id: str | None,
    *,
    owner_id: str,
) -> OwnerBoundType4Authority:
    """Return the code-owned owner-bound authority, or refuse with a fixed NOT_RUN detail."""
    if authority_id is None:
        raise SpecimenRefused("NOT_RUN", OWNER_AUTHORITY_ABSENT)
    authority = CODE_OWNED_TYPE4_AUTHORITIES.get(authority_id)
    if authority is None:
        raise SpecimenRefused("NOT_RUN", SYNTHETIC_AUTHORITY_NOT_PROOF)
    if authority.owner_id != owner_id:
        raise SpecimenRefused(AUTHORITY_NOT_OWNER_BOUND)
    return authority


def _check_administration(packet: ActualProofPacket) -> None:
    if not _is_identity(packet.policy_resource_owner_id):
        raise SpecimenRefused(POLICY_ADMIN_OWNER_MISSING)
    if packet.policy_resource_owner_id in (packet.owner_id, packet.executor_id):
        raise SpecimenRefused(POLICY_ADMIN_NOT_SEPARATED)


def _check_controls(packet: ActualProofPacket) -> None:
    for name in MANDATORY_CONTROLS:
        state = packet.controls.get(name)
        if state is None or state in BLOCKING_CONTROL_STATES:
            raise SpecimenRefused(MANDATORY_CONTROL_UNQUALIFIED, name)
    if packet.position_inventory in BLOCKING_CONTROL_STATES:
        raise SpecimenRefused(POSITION_INVENTORY_UNQUALIFIED)


def _check_profile_policies(packet: ActualProofPacket) -> None:
    bound = 0
    for profile in PROFILES:
        policy_id = packet.profile_policies.get(profile)
        policy_sha = packet.profile_policy_sha256.get(profile)
        if not _is_identity(policy_id) or not _is_identity(policy_sha):
            raise SpecimenRefused(PROFILE_POLICY_UNBOUND, profile)
        bound += 1
    if (bound != len(PROFILES) or len(set(packet.profile_policies.values())) != len(PROFILES)
            or len(set(packet.profile_policy_sha256.values())) != len(PROFILES)):
        raise SpecimenRefused(PROFILE_POLICY_NOT_SEPARATED)


def _check_matrix(packet: ActualProofPacket, table: SpecimenTable) -> None:
    accepted_ids = {row.specimen_id for row in table.all()}
    if set(packet.specimen_expected) != accepted_ids:
        raise SpecimenRefused(MATRIX_NOT_COVERED, "id-set")
    # The accepted matrix fixes every expectation except the type-4 placeholder, which a
    # packet may rebind to a runnable negative control only with owner-bound authority.
    for row in table.all():
        if row.expected is not Expected.NOT_RUN and packet.specimen_expected.get(row.specimen_id) != str(row.expected):
            raise SpecimenRefused(MATRIX_NOT_COVERED, row.specimen_id)
    for specimen_id, expected in packet.specimen_expected.items():
        try:
            Expected(expected)
        except ValueError:
            raise SpecimenRefused(MATRIX_NOT_COVERED, specimen_id) from None
        if len(packet.attempt_identity_for(specimen_id)) > 256:
            raise SpecimenRefused(MATRIX_NOT_COVERED, specimen_id)
        if expected != Expected.NOT_RUN.value:
            packet.request_for(specimen_id)


def _check_ceilings(packet: ActualProofPacket, table: SpecimenTable) -> None:
    if not (0 < packet.request_count_ceiling <= MAX_SPECIMENS_PER_PROFILE
            and 0 < packet.request_byte_ceiling <= MAX_REQUEST_BODY_BYTES
            and packet.time_ceiling_seconds > 0):
        raise SpecimenRefused(PACKET_CEILING_INVALID)
    for profile in PROFILES:
        if len(table.profile(profile)) > packet.request_count_ceiling:
            raise SpecimenRefused(REQUEST_COUNT_EXCEEDED, profile)


def resolve_approved_packet(
    packet_id: str,
    *,
    now_epoch: int,
    table: SpecimenTable = FROZEN_TABLE,
) -> ActualProofPacket:
    """Return the code-approved packet, or refuse before any effect.

    Refusal order: an unknown id, a content-hash mismatch, an expired packet, a
    missing or non-separated policy-resource owner, an unbound or unseparated
    profile policy, an unqualified mandatory control, an unqualified
    position-inventory obligation, and a specimen manifest that does not cover
    the accepted matrix.
    """
    packet = CODE_OWNED_PACKET_APPROVALS.get(packet_id)
    if packet is None:
        raise SpecimenRefused(ACTUAL_PACKET_NOT_APPROVED)
    if packet.packet_id != packet_id or packet.packet_sha256() != packet_id:
        raise SpecimenRefused(ACTUAL_PACKET_MISMATCH)
    if now_epoch >= packet.expires_at_epoch:
        raise SpecimenRefused(ACTUAL_PACKET_EXPIRED)
    _check_administration(packet)
    if _AUTH_HEADER_EXPIRY.fullmatch(packet.auth_header_expiry) is None:
        raise SpecimenRefused(ACTUAL_PACKET_MISMATCH, "auth_header_expiry")
    _check_profile_policies(packet)
    _check_controls(packet)
    _check_ceilings(packet, table)
    _check_matrix(packet, table)
    return packet


if __name__ == "__main__":
    from scripts.privy_unfunded_proof.specimens import refuse_module_run

    refuse_module_run()
