"""Shared doubles and fixtures for the LOCAL actual proof-runner tests.

Everything here is SYNTHETIC. The test packet and profile exist only to exercise
the runner machinery; the production code-owned registries hold one frozen
policy-layer packet and one raw profile. The helper temporarily injects test
entries by patching the module registries, which is a test-only mutation of
code-owned state. Tests cannot pass an approval through the public run signature,
and every produced result stays LOCAL_TESTED/UNQUALIFIED.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from scripts.privy_unfunded_proof import actual_packet, actual_profile, actual_runner, specimens
from scripts.privy_unfunded_proof.actual_packet import ControlState, MANDATORY_CONTROLS, build_packet
from scripts.privy_unfunded_proof.actual_profile import QualifiedActualProfile, SignedDecode
from scripts.privy_unfunded_proof.evidence import Outcome, Reply
from scripts.privy_unfunded_proof.specimens import AttemptStore

WALLET_A = "0x00000000000000000000000000000000000000a1"
WALLET_B = "0x00000000000000000000000000000000000000a2"
URL_A = "https://api.privy.io/v1/wallets/synthetic-probe-wallet-a/rpc"
NOW = 1_000_000_000
EXPIRES = 2_000_000_000


def clock() -> str:
    return "2026-10-18T00:00:00Z"


def make_packet(**overrides: Any) -> actual_packet.ActualProofPacket:
    rows = specimens.FROZEN_TABLE.all()
    fields: dict[str, Any] = {
        "app_id": "app-test-1",
        "executor_id": "executor-1",
        "owner_id": "owner-1",
        "policy_resource_owner_id": "policy-owner-1",
        "wallet_id": "synthetic-probe-wallet-a",
        "wallet_address": WALLET_A,
        "network_id": "monad-mainnet",
        "chain_id": 143,
        "signing_url": URL_A,
        "signing_method": "eth_signTransaction",
        "profile_policies": {"raw": "policy-raw", "decoded": "policy-decoded"},
        "profile_policy_sha256": {"raw": "sha-raw", "decoded": "sha-decoded"},
        "source_code_id": "src-1",
        "deployed_code_id": "deploy-1",
        "expires_at_epoch": EXPIRES,
        "auth_header_expiry": "1792000000000",
        "attempt_identity": "attempt-1",
        "requests": {row.specimen_id: row.request for row in rows if row.request is not None},
        "specimen_expected": {row.specimen_id: str(row.expected) for row in rows},
        "request_count_ceiling": 32,
        "request_byte_ceiling": 4096,
        "time_ceiling_seconds": 3600,
        "controls": {name: ControlState.DOCUMENTED for name in MANDATORY_CONTROLS},
        "position_inventory": ControlState.LOCAL_TESTED,
    }
    fields.update(overrides)
    return build_packet(**fields)


def expected_binding(packet: actual_packet.ActualProofPacket, specimen_id: str) -> dict[str, object]:
    return {
        "method": "POST",
        "destination": packet.signing_url,
        "wallet_id": packet.wallet_id,
        "app_id": packet.app_id,
        "request_id": packet.attempt_identity_for(specimen_id),
        "request_expiry_ms": int(packet.auth_header_expiry),
    }


def matched_factory(unsigned: Any, wallet: str) -> Callable[[bytes], SignedDecode]:
    def decode(raw: bytes) -> SignedDecode:
        return SignedDecode(True, (), "sha256:" + hashlib.sha256(raw).hexdigest())

    return decode


def mismatched_factory(unsigned: Any, wallet: str) -> Callable[[bytes], SignedDecode]:
    def decode(raw: bytes) -> SignedDecode:
        return SignedDecode(False, ("SIGNED_CHAINID_MISMATCH",), "sha256:" + hashlib.sha256(raw).hexdigest())

    return decode


DEFAULT_CODES = {
    "test_policy_violation": (400, Outcome.POLICY_DENY.value, "TEST_POLICY"),
    "test_wallet_not_authorized": (403, Outcome.AUTHORIZATION_DENY.value, "TEST_AUTHORIZATION"),
    "test_invalid_field": (400, Outcome.SCHEMA_REJECTED.value, "TEST_SCHEMA"),
    "test_request_expired": (400, Outcome.UNKNOWN.value, "EXPIRY_REFUSAL"),
}


def make_profile(
    profile: str = "raw",
    *,
    decoder_factory: Callable[[Any, str], Callable[[bytes], SignedDecode]] = matched_factory,
    codes: dict[str, tuple[int, str, str]] | None = None,
    qualification: str = "QUALIFIED",
) -> QualifiedActualProfile:
    return QualifiedActualProfile(
        profile=profile,
        qualification=qualification,
        codes=DEFAULT_CODES if codes is None else codes,
        decoder_factory=decoder_factory,
    )


def success_reply(signed_hex: str = "0x" + "ab" * 100) -> Reply:
    body = {"method": "eth_signTransaction", "data": {"signed_transaction": signed_hex, "encoding": "rlp"}}
    return Reply(status=200, content_type="application/json", body=json.dumps(body).encode("utf-8"))


def code_reply(status: int, code: str) -> Reply:
    return Reply(status=status, content_type="application/json", body=json.dumps({"code": code}).encode("utf-8"))


class RecordingTransport:
    def __init__(self, reply: Reply | None = None, error: BaseException | None = None,
                 binding: dict | None = None) -> None:
        self.reply = reply
        self.error = error
        self.requests: list = []
        if binding is not None:
            self.binding = lambda: dict(binding)

    def send(self, request):  # noqa: ANN001
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.reply


@contextmanager
def injected(packet: actual_packet.ActualProofPacket, profiles: dict,
             type4_authorities=None) -> Iterator[None]:  # noqa: ANN001
    saved = (actual_packet.CODE_OWNED_PACKET_APPROVALS, actual_profile.QUALIFIED_ACTUAL_PROFILES,
             actual_packet.CODE_OWNED_TYPE4_AUTHORITIES)
    actual_packet.CODE_OWNED_PACKET_APPROVALS = {packet.packet_id: packet}
    actual_profile.QUALIFIED_ACTUAL_PROFILES = dict(profiles)
    if type4_authorities is not None:
        actual_packet.CODE_OWNED_TYPE4_AUTHORITIES = type4_authorities
    try:
        yield
    finally:
        (actual_packet.CODE_OWNED_PACKET_APPROVALS, actual_profile.QUALIFIED_ACTUAL_PROFILES,
         actual_packet.CODE_OWNED_TYPE4_AUTHORITIES) = saved


def run_actual(
    specimen_id: str,
    store_dir,  # noqa: ANN001
    transport,
    *,
    packet: actual_packet.ActualProofPacket | None = None,
    profile: QualifiedActualProfile | None = None,
    profile_id: str | None = None,
    decoder_factory=matched_factory,
    codes=None,
    table=specimens.FROZEN_TABLE,
    type4_authority_id: str | None = None,
    type4_authorities=None,  # noqa: ANN001
    profiles_override: dict | None = None,
    now_epoch: int = NOW,
    started_at_epoch: int = NOW,
    inject: bool = True,
    auto_binding: bool = True,
):
    packet = packet if packet is not None else make_packet()
    profile_name = specimen_id.split(".")[0]
    if profile is None:
        profile = make_profile(profile_name, decoder_factory=decoder_factory, codes=codes)
    if profile_id is None:
        profile_id = f"test.{profile.profile}"
    if auto_binding and getattr(transport, "binding", None) is None:
        transport.binding = lambda: expected_binding(packet, specimen_id)
    call = dict(
        store=AttemptStore(store_dir),
        transport=transport,
        packet_id=packet.packet_id,
        profile_id=profile_id,
        clock=clock,
        now_epoch=now_epoch,
        started_at_epoch=started_at_epoch,
        table=table,
        type4_authority_id=type4_authority_id,
    )
    profiles = {profile_id: profile} if profiles_override is None else profiles_override
    if inject:
        with injected(packet, profiles, type4_authorities):
            return actual_runner.run_actual_specimen(specimen_id, **call)
    return actual_runner.run_actual_specimen(specimen_id, **call)


def allow_baseline(store_dir, profile: str = "raw", **kwargs) -> None:  # noqa: ANN001
    result = run_actual(f"{profile}.baseline", store_dir, RecordingTransport(success_reply()), **kwargs)
    assert result.outcome is Outcome.ALLOW
