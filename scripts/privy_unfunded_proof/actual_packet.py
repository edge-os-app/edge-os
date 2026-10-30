"""Frozen exact actual proof packet and its code-owned approval registry.

LOCAL only. This module defines the exact, frozen inputs one unfunded actual
policy-proof run would need, and the code-owned approval a run must resolve
before it may touch a credential or open a socket. It performs no I/O, reads no
credential and holds no transport.

A packet is admitted only when the *code* registers it in
``CODE_OWNED_PACKET_APPROVALS``; no caller argument, flag, environment value or
Boolean can approve one. The registry holds two sealed packets, the v3
policy-layer packet and the control-proof packet, so every other packet
refuses with ``ACTUAL_PACKET_NOT_APPROVED``. The packet binds the app, the
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

from edge_os_api.execution.privy_policy_reply import reply_code
from scripts.privy_unfunded_proof import chain_proof, specimens
from scripts.privy_unfunded_proof.actual_transport import MAX_SAFE_INTEGER, QUANTITY_FIELDS, wire_quantity
from scripts.privy_unfunded_proof.specimens import (
    DESTINATION,
    FROZEN_TABLE,
    MAX_REQUEST_BODY_BYTES,
    MAX_SPECIMENS_PER_PROFILE,
    PROFILES,
    Category,
    Expected,
    FrozenRequest,
    Specimen,
    SpecimenRefused,
    SpecimenTable,
    build_table,
    canonical_json,
    envelope_sha256,
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

# A policy-layer packet proves the wallet-provider policy only. It does not claim
# a real trade: controls enforced by the host, the contract or a later stage stay
# at their true evidence state and do not block this narrow proof.
PROOF_SCOPES: tuple[str, ...] = ("TRADE", "POLICY_LAYER")
POLICY_LAYER_CONTROLS: tuple[str, ...] = (
    "chain",
    "wallet_signer_binding",
    "entrypoint_method",
    "approvals",
)

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
PROOF_SCOPE_INVALID = "PROOF_SCOPE_INVALID"
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
    proof_scope: str = "TRADE"

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
            "proof_scope": self.proof_scope,
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


# Code-owned approval registry. The v3 policy-layer packet and the control-proof
# packet are registered at the end of this module; no other packet is approved.
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
    """The executor must not administer the policy.

    One human builder may own both the wallet and the policy. The party that must
    stay outside policy administration is the executor that holds the signing key.
    """
    if not _is_identity(packet.policy_resource_owner_id):
        raise SpecimenRefused(POLICY_ADMIN_OWNER_MISSING)
    if packet.policy_resource_owner_id == packet.executor_id or packet.owner_id == packet.executor_id:
        raise SpecimenRefused(POLICY_ADMIN_NOT_SEPARATED)


def _check_controls(packet: ActualProofPacket) -> None:
    if packet.proof_scope not in PROOF_SCOPES:
        raise SpecimenRefused(PROOF_SCOPE_INVALID, packet.proof_scope)
    for name in MANDATORY_CONTROLS:
        if name not in packet.controls:
            raise SpecimenRefused(MANDATORY_CONTROL_UNQUALIFIED, name)
    required = POLICY_LAYER_CONTROLS if packet.proof_scope == "POLICY_LAYER" else MANDATORY_CONTROLS
    for name in required:
        state = packet.controls.get(name)
        if state is None or state in BLOCKING_CONTROL_STATES:
            raise SpecimenRefused(MANDATORY_CONTROL_UNQUALIFIED, name)
    if packet.proof_scope == "TRADE" and packet.position_inventory in BLOCKING_CONTROL_STATES:
        raise SpecimenRefused(POSITION_INVENTORY_UNQUALIFIED)


def _check_profile_policies(packet: ActualProofPacket, table: SpecimenTable) -> None:
    """One separate policy id and content hash for every profile the table uses."""
    active = {row.profile for row in table.all()}
    if not active or set(packet.profile_policies) != active or set(packet.profile_policy_sha256) != active:
        raise SpecimenRefused(PROFILE_POLICY_UNBOUND, "profile-set")
    for profile in active:
        policy_id = packet.profile_policies.get(profile)
        policy_sha = packet.profile_policy_sha256.get(profile)
        if not _is_identity(policy_id) or not _is_identity(policy_sha):
            raise SpecimenRefused(PROFILE_POLICY_UNBOUND, profile)
    if (len(set(packet.profile_policies.values())) != len(active)
            or len(set(packet.profile_policy_sha256.values())) != len(active)):
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
    _check_profile_policies(packet, table)
    _check_controls(packet)
    _check_ceilings(packet, table)
    _check_matrix(packet, table)
    return packet


# ---------------------------------------------------------------- frozen unfunded policy packet


UNFUNDED_POLICY_PROFILE_ID = "privy.raw.v1"
POLICY_ID = "c30racyru6duaipj815cvjce"
# Version 2 binds the rules-only PATCH body: the live rules returned by Privy,
# normalized (rule ids removed, address values lower-cased), in canonical JSON.
POLICY_BODY_SHA256 = "61860d201ecd9ce6d92bff5e7c2122b40164ecb69d1fa375738cb67b17b0892b"
APP_ID = "cmuyj4smt00tw0dla2j19tlu7"
POLICY_OWNER_ID = "a5gwmgrsn6903ac09lphyv9a"
EXECUTOR_ID = "zu1qjdfqlbcq1ct7sdxendgg"
WALLET_ID = "bsb2feecuxl81dl5jz4u9xxo"
WALLET_ADDRESS = "0x91BB52A63c91986813288965e4681FF111De1b63"
SIGNING_URL = DESTINATION.format(wallet_id=WALLET_ID)
WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
ENTRYPOINT = "0xb3e6778480b2e488385e8205ea05e20060b813cb"
SINK = "0x000000000000000000000000000000000000dead"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MON = 10**18
CAP = 70 * MON
GAS_DEPOSIT = 100_000
GAS_APPROVE = 100_000
GAS_TRANSFER = 100_000
GAS_SWAP = 500_000
MAX_FEE_PER_GAS = 100_000_000_000
MAX_PRIORITY_FEE_PER_GAS = 2_000_000_000
PACKET_EXPIRES_AT_EPOCH = 1_793_836_800
PACKET_AUTH_HEADER_EXPIRY = "1793836800000"
PACKET_ATTEMPT_IDENTITY = "unfunded-policy-proof-3"

# The reviewed identities. The registry admits the packet and the table only when
# their recomputed hashes equal these literals. A source edit cannot approve a
# new packet or table without a new reviewed literal.
SEALED_PACKET_SHA256 = "8255d003097fd1a0216a6b64c48637f2ef745c7ebbe73035d0b8929403500528"
SEALED_ACTUAL_MANIFEST_SHA256 = "f485816e431aae37e30d062df038a3e1d62b8cdadac8e510ebb5d0181c827b63"

DEPOSIT_CALLDATA = "0xd0e30db0"
APPROVE_SELECTOR = "0x095ea7b3"
TRANSFER_SELECTOR = "0xa9059cbb"
EXECUTE_SWAP_SELECTOR = "0xce1e7030"
EXECUTE_SWAP_WITH_RECEIVER_SIGNATURE = (
    "executeSwapWithReceiver((address,uint256,address,uint256),"
    "(address,uint256,address,uint256,bool),bytes,address)"
)
EXECUTE_SWAP_WITH_RECEIVER_SELECTOR = "0x31343b21"
SWAP_PROGRAM = "01"

_ADDRESS_VALUE = re.compile(r"0x[0-9a-fA-F]{40}")


def normalize_live_policy_rules(rules: Any) -> Any:
    """Normalize live Privy rules to the reviewed write body.

    Privy returns rule ids and checksum-cased address values. The reviewed PATCH
    body has neither. Remove every ``id`` key and lower-case every address value,
    and change no other field, so the canonical hash is stable across reads.
    """
    if isinstance(rules, Mapping):
        return {name: normalize_live_policy_rules(value) for name, value in rules.items() if name != "id"}
    if isinstance(rules, list):
        return [normalize_live_policy_rules(value) for value in rules]
    if isinstance(rules, str) and _ADDRESS_VALUE.fullmatch(rules) is not None:
        return rules.lower()
    return rules


def policy_body_sha256(live_rules: Any) -> str:
    """The content hash of one policy rules body, derived as the packet binds it."""
    return hashlib.sha256(canonical_json({"rules": normalize_live_policy_rules(live_rules)})).hexdigest()


def _word(value: int) -> str:
    return f"{value:064x}"


def _address_word(address: str) -> str:
    return "0" * 24 + address[2:].lower()


def _approve_calldata(spender: str, amount: int) -> str:
    return APPROVE_SELECTOR + _address_word(spender) + _word(amount)


def _transfer_calldata(recipient: str, amount: int) -> str:
    return TRANSFER_SELECTOR + _address_word(recipient) + _word(amount)


def _execute_swap_calldata() -> str:
    """The exact executeSwap layout decoded by the accepted Kuru Flow decoder.

    The token pair and program are inert policy sentinels: WMON on both sides and
    a one-byte program. They are never broadcast and prove no trade route.
    """
    head = (
        _address_word(WMON) + _word(MON) + _address_word(WMON) + _word(2 * MON)
        + _address_word(ZERO_ADDRESS) + _word(0)
        + _address_word(ZERO_ADDRESS) + _word(0) + _word(0)
        + _word(320)
    )
    padded_program = SWAP_PROGRAM + "0" * (64 - len(SWAP_PROGRAM))
    return EXECUTE_SWAP_SELECTOR + head + _word(len(SWAP_PROGRAM) // 2) + padded_program


def _execute_swap_with_receiver_calldata(receiver: str) -> str:
    """The exact receiver variant layout: the same tuples, then bytes offset 352 and one receiver word."""
    head = (
        _address_word(WMON) + _word(MON) + _address_word(WMON) + _word(2 * MON)
        + _address_word(ZERO_ADDRESS) + _word(0)
        + _address_word(ZERO_ADDRESS) + _word(0) + _word(0)
        + _word(352) + _address_word(receiver)
    )
    padded_program = SWAP_PROGRAM + "0" * (64 - len(SWAP_PROGRAM))
    return (EXECUTE_SWAP_WITH_RECEIVER_SELECTOR + head
            + _word(len(SWAP_PROGRAM) // 2) + padded_program)


def _transaction(*, to: str, value: int, data: str, chain_id: int = 143, gas_limit: int,
                 nonce: int = 0) -> dict[str, Any]:
    return {
        "type": 2,
        "chain_id": chain_id,
        "nonce": nonce,
        "to": to,
        "value": value,
        "data": data,
        "gas_limit": gas_limit,
        "max_fee_per_gas": MAX_FEE_PER_GAS,
        "max_priority_fee_per_gas": MAX_PRIORITY_FEE_PER_GAS,
    }


def _policy_request(transaction: Mapping[str, Any],
                    headers: tuple[tuple[str, str], ...] = ()) -> FrozenRequest:
    wire = dict(transaction)
    for name in QUANTITY_FIELDS:
        if name == "chain_id":
            value = transaction[name]
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_SAFE_INTEGER:
                raise ValueError("chain_id must stay a safe integer")
            wire[name] = value
        else:
            wire[name] = wire_quantity(transaction[name])
    body = {"method": "eth_signTransaction", "params": {"transaction": wire}}
    body_bytes = canonical_json(body)
    if len(body_bytes) > MAX_REQUEST_BODY_BYTES:
        raise ValueError("policy request exceeds the frozen request byte bound")
    if not specimens.headers_are_canonical(headers):
        raise ValueError("policy request headers are not canonical")
    return FrozenRequest(SIGNING_URL, "POST", headers, body_bytes,
                         envelope_sha256(SIGNING_URL, "POST", headers, body_bytes))


def _policy_row(name: str, category: Category, expected: Expected,
                transaction: Mapping[str, Any], headers: tuple[tuple[str, str], ...] = ()) -> Specimen:
    return Specimen(f"raw.{name}", "raw", category, expected, WALLET_ID,
                    _policy_request(transaction, headers), dict(transaction))


def _policy_rows() -> list[Specimen]:
    allow, deny = Expected.ALLOW, Expected.POLICY_DENY
    positive, operation, field = Category.POSITIVE_CONTROL, Category.OPERATION, Category.FIELD_MUTATION
    swap_data = _execute_swap_calldata()
    return [
        _policy_row("allow_deposit_1_mon", positive, allow,
                    _transaction(to=WMON, value=MON, data=DEPOSIT_CALLDATA, gas_limit=GAS_DEPOSIT)),
        _policy_row("allow_deposit_at_cap", operation, allow,
                    _transaction(to=WMON, value=CAP, data=DEPOSIT_CALLDATA, gas_limit=GAS_DEPOSIT)),
        _policy_row("allow_approve_at_cap", operation, allow,
                    _transaction(to=WMON, value=0, data=_approve_calldata(ENTRYPOINT, CAP),
                                 gas_limit=GAS_APPROVE)),
        _policy_row("allow_swap_zero_value", operation, allow,
                    _transaction(to=ENTRYPOINT, value=0, data=swap_data, gas_limit=GAS_SWAP)),
        _policy_row("deny_deposit_wrong_to", field, deny,
                    _transaction(to=SINK, value=MON, data=DEPOSIT_CALLDATA, gas_limit=GAS_DEPOSIT)),
        _policy_row("deny_deposit_wrong_chain", field, deny,
                    _transaction(to=WMON, value=MON, data=DEPOSIT_CALLDATA, chain_id=10143,
                                 gas_limit=GAS_DEPOSIT)),
        _policy_row("deny_approve_wrong_chain", field, deny,
                    _transaction(to=WMON, value=0, data=_approve_calldata(ENTRYPOINT, CAP),
                                 chain_id=10143, gas_limit=GAS_APPROVE)),
        _policy_row("deny_swap_wrong_chain", field, deny,
                    _transaction(to=ENTRYPOINT, value=0, data=swap_data, chain_id=10143,
                                 gas_limit=GAS_SWAP)),
        _policy_row("deny_approve_wrong_to", field, deny,
                    _transaction(to=SINK, value=0, data=_approve_calldata(ENTRYPOINT, CAP),
                                 gas_limit=GAS_APPROVE)),
        _policy_row("deny_swap_wrong_to", field, deny,
                    _transaction(to=SINK, value=0, data=swap_data, gas_limit=GAS_SWAP)),
        _policy_row("deny_wmon_wrong_function", field, deny,
                    _transaction(to=WMON, value=0, data=_transfer_calldata(SINK, 1),
                                 gas_limit=GAS_TRANSFER)),
        _policy_row("deny_entrypoint_wrong_function", field, deny,
                    _transaction(to=ENTRYPOINT, value=0, data=DEPOSIT_CALLDATA, gas_limit=GAS_DEPOSIT)),
        _policy_row("deny_execute_swap_with_receiver", field, deny,
                    _transaction(to=ENTRYPOINT, value=0,
                                 data=_execute_swap_with_receiver_calldata(SINK), gas_limit=GAS_SWAP)),
        _policy_row("deny_approve_other_spender", field, deny,
                    _transaction(to=WMON, value=0, data=_approve_calldata(SINK, CAP),
                                 gas_limit=GAS_APPROVE)),
        _policy_row("deny_approve_above_cap", field, deny,
                    _transaction(to=WMON, value=0, data=_approve_calldata(ENTRYPOINT, CAP + 1),
                                 gas_limit=GAS_APPROVE)),
        _policy_row("deny_approve_with_value", field, deny,
                    _transaction(to=WMON, value=1, data=_approve_calldata(ENTRYPOINT, CAP),
                                 gas_limit=GAS_APPROVE)),
        _policy_row("deny_deposit_above_cap", field, deny,
                    _transaction(to=WMON, value=CAP + 1, data=DEPOSIT_CALLDATA, gas_limit=GAS_DEPOSIT)),
        _policy_row("deny_swap_with_mon", field, deny,
                    _transaction(to=ENTRYPOINT, value=1, data=swap_data, gas_limit=GAS_SWAP)),
        _policy_row("deny_plain_mon_transfer", field, deny,
                    _transaction(to=SINK, value=1, data="0x", gas_limit=GAS_TRANSFER)),
    ]


UNFUNDED_POLICY_ORDER: tuple[str, ...] = (
    "raw.allow_deposit_1_mon",
    "raw.allow_deposit_at_cap",
    "raw.allow_approve_at_cap",
    "raw.allow_swap_zero_value",
    "raw.deny_deposit_wrong_to",
    "raw.deny_deposit_wrong_chain",
    "raw.deny_approve_wrong_chain",
    "raw.deny_swap_wrong_chain",
    "raw.deny_approve_wrong_to",
    "raw.deny_swap_wrong_to",
    "raw.deny_wmon_wrong_function",
    "raw.deny_entrypoint_wrong_function",
    "raw.deny_execute_swap_with_receiver",
    "raw.deny_approve_other_spender",
    "raw.deny_approve_above_cap",
    "raw.deny_approve_with_value",
    "raw.deny_deposit_above_cap",
    "raw.deny_plain_mon_transfer",
    "raw.deny_swap_with_mon",
)

UNFUNDED_POLICY_TABLE = build_table(_policy_rows())
specimens.CODE_OWNED_ACTUAL_MANIFESTS = frozenset({SEALED_ACTUAL_MANIFEST_SHA256})


def _build_unfunded_policy_packet() -> ActualProofPacket:
    rows = UNFUNDED_POLICY_TABLE.all()
    requests: dict[str, FrozenRequest] = {}
    expected: dict[str, str] = {}
    for row in rows:
        if row.request is None:
            raise ValueError("the policy table has a row without a frozen request")
        requests[row.specimen_id] = row.request
        expected[row.specimen_id] = str(row.expected)
    controls = {
        "chain": ControlState.DOCUMENTED,
        "wallet_signer_binding": ControlState.SOURCE_INSPECTED,
        "entrypoint_method": ControlState.DOCUMENTED,
        "input_output_assets": ControlState.UNKNOWN,
        "raw_input": ControlState.SOURCE_INSPECTED,
        "recipient": ControlState.SOURCE_INSPECTED,
        "minimum_output": ControlState.SOURCE_INSPECTED,
        "fees": ControlState.SOURCE_INSPECTED,
        "approvals": ControlState.SOURCE_INSPECTED,
        "gas_action_capacity": ControlState.UNSET,
        "expiry_freshness": ControlState.DOCUMENTED,
        "opaque_program": ControlState.UNKNOWN,
    }
    return build_packet(
        app_id=APP_ID,
        executor_id=EXECUTOR_ID,
        owner_id=POLICY_OWNER_ID,
        policy_resource_owner_id=POLICY_OWNER_ID,
        wallet_id=WALLET_ID,
        wallet_address=WALLET_ADDRESS,
        network_id="eip155:143",
        chain_id=143,
        signing_url=SIGNING_URL,
        signing_method="eth_signTransaction",
        profile_policies={"raw": POLICY_ID},
        profile_policy_sha256={"raw": POLICY_BODY_SHA256},
        source_code_id="UNRESOLVED_KURU_SOURCE",
        deployed_code_id="UNRESOLVED_KURU_DEPLOYED_CODE",
        expires_at_epoch=PACKET_EXPIRES_AT_EPOCH,
        auth_header_expiry=PACKET_AUTH_HEADER_EXPIRY,
        attempt_identity=PACKET_ATTEMPT_IDENTITY,
        requests=requests,
        specimen_expected=expected,
        request_count_ceiling=MAX_SPECIMENS_PER_PROFILE,
        request_byte_ceiling=MAX_REQUEST_BODY_BYTES,
        time_ceiling_seconds=3600,
        controls=controls,
        position_inventory=ControlState.UNSUPPORTED,
        proof_scope="POLICY_LAYER",
    )


def _sealed_packet_registry(packet: ActualProofPacket, sealed_sha256: str) -> dict[str, ActualProofPacket]:
    """Admit the packet only when its recomputed identity equals the reviewed literal."""
    return {packet.packet_id: packet} if packet.packet_id == sealed_sha256 else {}


UNFUNDED_POLICY_PACKET = _build_unfunded_policy_packet()


# ---------------------------------------------------------------- frozen control-proof packet
#
# New rows only, for the in-app trade control proofs (docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md).
# The v3 packet above and its 19 rows are unchanged. Every row uses a nonce far above the wallet's, so even a
# signature that leaked could not be included before the wallet sent a million transactions; the runner never
# saves signed bytes and has no broadcast path. The only expected signature is a revoke to zero.

CONTROL_PROOF_NONCE = 1_000_000
CONTROL_PROOF_ATTEMPT_IDENTITY = "control-proofs-1"
CONTROL_PROOF_EXPIRES_AT_EPOCH = 1_796_083_200  # 2026-11-30T00:00:00Z
CONTROL_PROOF_AUTH_HEADER_EXPIRY = "1796083200000"
# 2026-10-14T23:06:40Z: a request expiry already past, sent only on the in-policy expiry row.
CONTROL_PROOF_EXPIRED_HEADER = "1792000000000"
CONTROL_GAS_APPROVE = 70_000
SEALED_CONTROL_PROOF_PACKET_SHA256 = "501942ec92178a5621f25acb7395b44884a0d9770cbb23f44bc0c459656ae775"
SEALED_CONTROL_PROOF_MANIFEST_SHA256 = "556fdeb5fb8101cc35b3f2b119cc7c86680544155a731b81680b920f4f5fff1d"


def _execute_swap_with_receiver_release_calldata(receiver: str) -> str:
    """The release swap (WMON -> MOE, the approved program, minimum 1) as the receiver variant."""
    swap = chain_proof.swap_calldata(min_output_raw=1)
    head, tail = swap[10:10 + 64 * 9], swap[10 + 64 * 10:]
    return EXECUTE_SWAP_WITH_RECEIVER_SELECTOR + head + _word(352) + _address_word(receiver) + tail


def _control_rows() -> list[Specimen]:
    allow, deny = Expected.ALLOW, Expected.POLICY_DENY
    nonce = CONTROL_PROOF_NONCE
    moe, entry = chain_proof.MOE, ENTRYPOINT
    return [
        _policy_row("ctl_allow_revoke_zero", Category.POSITIVE_CONTROL, allow,
                    _transaction(to=WMON, value=0, data=_approve_calldata(entry, 0),
                                 gas_limit=CONTROL_GAS_APPROVE, nonce=nonce)),
        _policy_row("ctl_deny_approve_moe_entrypoint", Category.FIELD_MUTATION, deny,
                    _transaction(to=moe, value=0, data=_approve_calldata(entry, chain_proof.INPUT_RAW),
                                 gas_limit=CONTROL_GAS_APPROVE, nonce=nonce)),
        _policy_row("ctl_deny_swap_receiver_wallet", Category.FIELD_MUTATION, deny,
                    _transaction(to=entry, value=0,
                                 data=_execute_swap_with_receiver_release_calldata(WALLET_ADDRESS),
                                 gas_limit=chain_proof.SWAP_GAS_LIMIT, nonce=nonce)),
        _policy_row("ctl_deny_moe_transfer_sink", Category.OPERATION, deny,
                    _transaction(to=moe, value=0, data=_transfer_calldata(SINK, 1),
                                 gas_limit=GAS_TRANSFER, nonce=nonce)),
        _policy_row("ctl_deny_expired_request", Category.TIMING, Expected.EXPIRY_REFUSAL,
                    _transaction(to=entry, value=0, data=chain_proof.swap_calldata(min_output_raw=1),
                                 gas_limit=chain_proof.SWAP_GAS_LIMIT, nonce=nonce),
                    headers=(("privy-request-expiry", CONTROL_PROOF_EXPIRED_HEADER),)),
    ]


CONTROL_PROOF_ORDER: tuple[str, ...] = (
    "raw.ctl_allow_revoke_zero",
    "raw.ctl_deny_approve_moe_entrypoint",
    "raw.ctl_deny_swap_receiver_wallet",
    "raw.ctl_deny_moe_transfer_sink",
    "raw.ctl_deny_expired_request",
)
CONTROL_PROOF_TABLE = build_table(_control_rows())


def _build_control_proof_packet() -> ActualProofPacket:
    base = UNFUNDED_POLICY_PACKET
    rows = CONTROL_PROOF_TABLE.all()
    return build_packet(**{
        **{field.name: getattr(base, field.name) for field in dataclasses.fields(base)
           if field.name not in ("packet_id", "requests", "specimen_expected", "attempt_identity",
                                 "expires_at_epoch", "auth_header_expiry")},
        "requests": {row.specimen_id: row.request for row in rows if row.request is not None},
        "specimen_expected": {row.specimen_id: str(row.expected) for row in rows},
        "attempt_identity": CONTROL_PROOF_ATTEMPT_IDENTITY,
        "expires_at_epoch": CONTROL_PROOF_EXPIRES_AT_EPOCH,
        "auth_header_expiry": CONTROL_PROOF_AUTH_HEADER_EXPIRY,
    })


CONTROL_PROOF_PACKET = _build_control_proof_packet()
specimens.CODE_OWNED_ACTUAL_MANIFESTS = frozenset({SEALED_ACTUAL_MANIFEST_SHA256,
                                                   SEALED_CONTROL_PROOF_MANIFEST_SHA256})
CODE_OWNED_PACKET_APPROVALS = {
    **_sealed_packet_registry(UNFUNDED_POLICY_PACKET, SEALED_PACKET_SHA256),
    **_sealed_packet_registry(CONTROL_PROOF_PACKET, SEALED_CONTROL_PROOF_PACKET_SHA256),
}


if __name__ == "__main__":
    from scripts.privy_unfunded_proof.specimens import refuse_module_run

    refuse_module_run()
