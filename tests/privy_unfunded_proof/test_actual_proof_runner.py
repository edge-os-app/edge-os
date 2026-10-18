"""Regression tests for the LOCAL unfunded actual policy-proof runner.

Every result here is LOCAL_TESTED/UNQUALIFIED. No provider request, credential,
wallet, policy, signature or broadcast is used. The accepted code-owned approval
registries are empty, so the default actual run refuses. Tests inject their own
approval only to exercise the machinery.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from _actual_support import (
    NOW,
    URL_A,
    WALLET_A,
    RecordingTransport,
    allow_baseline,
    clock,
    code_reply,
    expected_binding,
    injected,
    make_packet,
    make_profile,
    mismatched_factory,
    run_actual,
    success_reply,
)
from scripts.privy_unfunded_proof import (
    actual_packet,
    actual_profile,
    actual_runner,
    actual_transport,
    specimens,
)
from scripts.privy_unfunded_proof.actual_packet import (
    ControlState,
    MANDATORY_CONTROLS,
    OwnerBoundType4Authority,
)
from scripts.privy_unfunded_proof.actual_profile import (
    ActualProfileUnqualified,
    SignedDecode,
    accepted_signed_decoder,
)
from scripts.privy_unfunded_proof.actual_transport import (
    ActualSignOnlyTransport,
    TransportLost,
    TransportRefused,
)
from scripts.privy_unfunded_proof.evidence import Outcome, Reply
from scripts.privy_unfunded_proof.specimens import (
    AttemptState,
    AttemptStore,
    SpecimenRefused,
    freeze_request,
    replace_request,
)

CHECKOUT_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
CANARY = "CANARY-ACTUAL-4f2a"


@pytest.fixture
def store_dir(tmp_path: Path) -> Iterator[Path]:
    store = tmp_path / "attempts-root"
    store.mkdir()
    yield store


def all_saved_text(root: Path) -> str:
    return "".join(path.read_text(encoding="utf-8", errors="replace") for path in sorted(root.iterdir()))


def run_child(code: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-s", "-c", code],
        cwd=CHECKOUT_ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=timeout, check=False,
    )


# ---------------------------------------------------------------- default refusal and imports


def test_default_actual_run_refused_before_effect(store_dir: Path) -> None:
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, inject=False)
    assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"
    assert transport.requests == []
    assert list(store_dir.iterdir()) == []


def test_code_owned_registries_are_empty() -> None:
    assert dict(actual_packet.CODE_OWNED_PACKET_APPROVALS) == {}
    assert dict(actual_profile.QUALIFIED_ACTUAL_PROFILES) == {}
    assert dict(actual_packet.CODE_OWNED_TYPE4_AUTHORITIES) == {}
    assert actual_packet.ACTUAL_EVIDENCE_CLASS == "LOCAL_TESTED"
    assert actual_packet.PROVIDER_PROOF_UNQUALIFIED == "UNQUALIFIED"


def test_actual_modules_import_makes_no_network_or_process_call() -> None:
    code = f"""
import sys
sys.path.insert(0, {str(TESTS_DIR)!r})
events = []
def hook(event, args):
    if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn")):
        events.append(event)
sys.addaudithook(hook)
import scripts.privy_unfunded_proof.actual_packet
import scripts.privy_unfunded_proof.actual_profile
import scripts.privy_unfunded_proof.actual_transport
import scripts.privy_unfunded_proof.actual_runner
print(sorted(set(events)))
"""
    completed = run_child(code)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"


@pytest.mark.parametrize("module", ["actual_packet", "actual_profile", "actual_transport", "actual_runner"])
def test_actual_module_run_refused(module: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "-s", "-m", f"scripts.privy_unfunded_proof.{module}"],
        cwd=CHECKOUT_ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 2


# ---------------------------------------------------------------- packet validation


def test_unapproved_packet_refused(store_dir: Path) -> None:
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, inject=False)
    assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"
    assert transport.requests == []


def test_packet_content_hash_mismatch_refused(store_dir: Path) -> None:
    packet = dataclasses.replace(make_packet(), packet_id="0" * 64)
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, packet=packet)
    assert caught.value.code == "ACTUAL_PACKET_MISMATCH"
    assert transport.requests == []


def test_expired_packet_refused(store_dir: Path) -> None:
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, now_epoch=2_000_000_001)
    assert caught.value.code == "ACTUAL_PACKET_EXPIRED"
    assert transport.requests == []


def test_missing_policy_owner_refused(store_dir: Path) -> None:
    packet = make_packet(policy_resource_owner_id="   ")
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "POLICY_ADMIN_OWNER_MISSING"


def test_owner_not_separated_refused(store_dir: Path) -> None:
    packet = make_packet(policy_resource_owner_id="owner-1")
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "POLICY_ADMIN_NOT_SEPARATED"


@pytest.mark.parametrize("control", ["opaque_program", "chain", "expiry_freshness"])
def test_unqualified_mandatory_control_refused(store_dir: Path, control: str) -> None:
    controls = {name: ControlState.DOCUMENTED for name in MANDATORY_CONTROLS}
    controls[control] = ControlState.UNKNOWN
    packet = make_packet(controls=controls)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "MANDATORY_CONTROL_UNQUALIFIED"
    assert caught.value.detail == control


def test_position_inventory_unqualified_refused(store_dir: Path) -> None:
    packet = make_packet(position_inventory=ControlState.UNSUPPORTED)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "POSITION_INVENTORY_UNQUALIFIED"


def test_profile_policy_missing_refused(store_dir: Path) -> None:
    packet = make_packet(profile_policies={"raw": "policy-raw"})
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "PROFILE_POLICY_UNBOUND"


def test_profile_policies_not_separated_refused(store_dir: Path) -> None:
    packet = make_packet(profile_policies={"raw": "policy-same", "decoded": "policy-same"})
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "PROFILE_POLICY_NOT_SEPARATED"


def test_profile_policy_hashes_not_separated_refused(store_dir: Path) -> None:
    packet = make_packet(profile_policy_sha256={"raw": "same", "decoded": "same"})
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "PROFILE_POLICY_NOT_SEPARATED"


def test_packet_cannot_rebind_a_denial_to_allow(store_dir: Path) -> None:
    expected = dict(make_packet().specimen_expected)
    expected["raw.wrong_chain"] = "ALLOW"
    packet = make_packet(specimen_expected=expected)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "MATRIX_NOT_COVERED"


@pytest.mark.parametrize(
    "overrides",
    [
        {"request_count_ceiling": 0},
        {"request_count_ceiling": 33},
        {"request_byte_ceiling": 0},
        {"request_byte_ceiling": 65536},
        {"time_ceiling_seconds": 0},
    ],
)
def test_packet_ceiling_invalid_refused(store_dir: Path, overrides: dict) -> None:
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=make_packet(**overrides))
    assert caught.value.code == "PACKET_CEILING_INVALID"


def test_matrix_not_covered_refused(store_dir: Path) -> None:
    expected = dict(make_packet().specimen_expected)
    del expected["raw.post_removal"]
    packet = make_packet(specimen_expected=expected)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "MATRIX_NOT_COVERED"


def test_request_count_exceeded_refused(store_dir: Path) -> None:
    packet = make_packet(request_count_ceiling=1)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "REQUEST_COUNT_EXCEEDED"


def test_time_ceiling_exceeded_refused(store_dir: Path) -> None:
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), started_at_epoch=NOW - 4000)
    assert caught.value.code == "TIME_CEILING_EXCEEDED"


def test_request_over_packet_byte_bound_refused(store_dir: Path) -> None:
    packet = make_packet(request_byte_ceiling=8)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), packet=packet)
    assert caught.value.code == "REQUEST_OVER_BOUND"


# ---------------------------------------------------------------- profile qualification


def test_unregistered_profile_refused(store_dir: Path) -> None:
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, profiles_override={})
    assert caught.value.code == "ACTUAL_PROFILE_UNQUALIFIED"
    assert transport.requests == []


def test_profile_construction_requires_qualified() -> None:
    with pytest.raises(ActualProfileUnqualified):
        make_profile(qualification="UNQUALIFIED")
    with pytest.raises(ActualProfileUnqualified):
        make_profile(profile="other")


def test_profile_rejects_a_non_outcome_value() -> None:
    with pytest.raises(ActualProfileUnqualified):
        make_profile(codes={"test_expired": (400, "EXPIRY_REFUSAL", "EXPIRY_REFUSAL")})


def test_profile_that_does_not_match_specimen_refused(store_dir: Path) -> None:
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, profile=make_profile("decoded"))
    assert caught.value.code == "ACTUAL_PROFILE_UNQUALIFIED"
    assert transport.requests == []


def test_accepted_signed_decoder_refuses_garbage() -> None:
    decode = accepted_signed_decoder({"chain_id": 143}, WALLET_A)
    result = decode(b"\x00\x01\x02")
    assert result.matched is False
    assert result.reasons == ("TRANSACTION_TYPE_UNSUPPORTED",)
    assert result.signed_bytes_sha256 == "sha256:" + hashlib.sha256(b"\x00\x01\x02").hexdigest()


# ---------------------------------------------------------------- admission


def test_manifest_mismatch_refused(store_dir: Path) -> None:
    table = dataclasses.replace(specimens.FROZEN_TABLE, manifest_sha256="deadbeef")
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()), table=table)
    assert caught.value.code == "MANIFEST_MISMATCH"


def test_changed_request_bytes_refused(store_dir: Path) -> None:
    base = make_packet()
    tampered = replace_request(base.requests["raw.wrong_chain"],
                               body=base.requests["raw.baseline"].body)
    requests = {**base.requests, "raw.wrong_chain": tampered}
    packet = make_packet(requests=requests)
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_chain", store_dir, transport, packet=packet)
    assert caught.value.code == "REQUEST_BYTES_CHANGED"
    assert transport.requests == []


@pytest.mark.parametrize(
    "headers",
    [
        (("privy-request-expiry", "1999999999999"), ("privy-request-expiry", "1792000000000")),
        (("Privy-Request-Expiry", "1792000000000"),),
    ],
    ids=["duplicate", "case"],
)
def test_noncanonical_headers_refused(store_dir: Path, headers: tuple) -> None:
    base = make_packet()
    original = base.requests["raw.request_expiry"]
    tampered = replace_request(original, headers=headers)
    packet = make_packet(requests={**base.requests, "raw.request_expiry": tampered})
    transport = RecordingTransport(code_reply(400, "test_request_expired"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.request_expiry", store_dir, transport, packet=packet)
    assert caught.value.code == "MALFORMED_REQUEST_HEADERS"
    assert transport.requests == []


def test_unknown_specimen_refused(store_dir: Path) -> None:
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.not_listed", store_dir, RecordingTransport(success_reply()))
    assert caught.value.code == "UNKNOWN_SPECIMEN"


def test_positive_control_required_before_negative(store_dir: Path) -> None:
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_chain", store_dir, transport)
    assert caught.value.code == "POSITIVE_CONTROL_NOT_QUALIFIED"
    assert transport.requests == []


def test_profiles_do_not_gate_each_other(store_dir: Path) -> None:
    allow_baseline(store_dir, "raw")
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("decoded.fee_bps", store_dir, RecordingTransport(code_reply(400, "test_policy_violation")))
    assert caught.value.code == "POSITIVE_CONTROL_NOT_QUALIFIED"
    allow_baseline(store_dir, "decoded")
    assert run_actual("decoded.fee_bps", store_dir,
                      RecordingTransport(code_reply(400, "test_policy_violation"))).outcome is Outcome.POLICY_DENY


def test_type4_not_run_without_authority(store_dir: Path) -> None:
    allow_baseline(store_dir)
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.type4_envelope", store_dir, transport)
    assert (caught.value.code, caught.value.detail) == ("NOT_RUN", "OWNER_AUTHORITY_ABSENT")
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.type4_envelope", store_dir, transport, type4_authority_id="missing")
    assert (caught.value.code, caught.value.detail) == ("NOT_RUN", "SYNTHETIC_AUTHORITY_NOT_PROOF")
    assert transport.requests == []


def test_type4_with_authority_but_unsupported_profile_refused(store_dir: Path) -> None:
    allow_baseline(store_dir)
    base = make_packet()
    type4_request = freeze_request("synthetic-probe-wallet-a", {
        "method": "eth_signTransaction",
        "params": {"transaction": {"type": 4, "authorization_list": []}},
    })
    packet = make_packet(
        requests={**base.requests, "raw.type4_envelope": type4_request},
        specimen_expected={**base.specimen_expected, "raw.type4_envelope": "POLICY_DENY"},
    )
    authority = OwnerBoundType4Authority("auth-1", "owner-1")
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.type4_envelope", store_dir, transport, packet=packet,
                   type4_authority_id="auth-1", type4_authorities={"auth-1": authority})
    assert caught.value.code == "REQUEST_PROFILE_UNQUALIFIED"
    assert transport.requests == []


def test_type4_authority_not_owner_bound_refused(store_dir: Path) -> None:
    allow_baseline(store_dir)
    base = make_packet()
    type4_request = freeze_request("synthetic-probe-wallet-a", {
        "method": "eth_signTransaction", "params": {"transaction": {"type": 4}}})
    packet = make_packet(requests={**base.requests, "raw.type4_envelope": type4_request},
                         specimen_expected={**base.specimen_expected, "raw.type4_envelope": "POLICY_DENY"})
    authority = OwnerBoundType4Authority("auth-1", "someone-else")
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.type4_envelope", store_dir, RecordingTransport(success_reply()), packet=packet,
                   type4_authority_id="auth-1", type4_authorities={"auth-1": authority})
    assert caught.value.code == "AUTHORITY_NOT_OWNER_BOUND"


# ---------------------------------------------------------------- lifecycle


def test_one_send_intent_has_packet_identity(store_dir: Path) -> None:
    packet = make_packet()
    transport = RecordingTransport(success_reply())
    result = run_actual("raw.baseline", store_dir, transport, packet=packet)
    assert result.outcome is Outcome.ALLOW
    assert len(transport.requests) == 1
    intent = json.loads((store_dir / "raw.baseline.intent.json").read_text())
    assert intent["packet_id"] == packet.packet_id
    assert intent["attempt_identity"] == "attempt-1:raw.baseline"
    assert intent["evidence_class"] == "LOCAL_TESTED"
    assert intent["state"] == "INTENT_SAVED"


def test_terminal_specimen_refused(store_dir: Path) -> None:
    allow_baseline(store_dir)
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport)
    assert caught.value.code == "ALREADY_CLAIMED"
    assert transport.requests == []


def test_uncertain_specimen_refused_after_new_transport(store_dir: Path) -> None:
    AttemptStore(store_dir).claim_record("raw.baseline", {"specimen_id": "raw.baseline", "state": "INTENT_SAVED"})
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport)
    assert caught.value.code == "ATTEMPT_UNCERTAIN"
    assert transport.requests == []


def test_changing_packet_does_not_reset_uncertain(store_dir: Path) -> None:
    AttemptStore(store_dir).claim_record("raw.baseline", {"specimen_id": "raw.baseline", "state": "INTENT_SAVED"})
    other = make_packet(attempt_identity="attempt-2")
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, packet=other)
    assert caught.value.code == "ATTEMPT_UNCERTAIN"
    assert transport.requests == []


def test_corrupt_intent_is_uncertain(store_dir: Path) -> None:
    (store_dir / "raw.baseline.intent.json").write_text('{"specimen_id": "raw.base')
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport)
    assert caught.value.code == "ATTEMPT_UNCERTAIN"
    assert transport.requests == []


def test_intent_persist_failure_makes_no_send(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_fsync(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(specimens.os, "fsync", failing_fsync)
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport)
    assert caught.value.code == "INTENT_NOT_PERSISTED"
    assert transport.requests == []


def test_stop_after_claim_blocks_send(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_claim = AttemptStore.claim_record

    def claim_then_stop(self, specimen_id, record):  # noqa: ANN001
        real_claim(self, specimen_id, record)
        self.stop({"specimen_id": specimen_id, "reason": "TEST_STOP", "at": clock()})

    monkeypatch.setattr(AttemptStore, "claim_record", claim_then_stop)
    transport = RecordingTransport(success_reply())
    result = run_actual("raw.baseline", store_dir, transport)
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "STOPPED_AFTER_CLAIM")
    assert transport.requests == []


def test_lost_reply_is_unknown_and_consumed(store_dir: Path) -> None:
    result = run_actual("raw.baseline", store_dir, RecordingTransport(error=TimeoutError("lost")))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "SEND_FAILED")
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport)
    assert caught.value.code == "ALREADY_CLAIMED"
    assert transport.requests == []


def test_transport_refusal_keeps_a_distinct_reason(store_dir: Path) -> None:
    result = run_actual("raw.baseline", store_dir,
                        RecordingTransport(error=TransportRefused("DESTINATION_NOT_APPROVED")))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "SEND_REFUSED")


def test_transport_loss_keeps_a_distinct_reason(store_dir: Path) -> None:
    result = run_actual("raw.baseline", store_dir, RecordingTransport(error=TransportLost("TRANSPORT_LOST")))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "SEND_LOST")


def test_concurrent_threads_send_once(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AttemptStore, "state", lambda self, specimen_id: AttemptState.NOT_SENT)
    packet = make_packet()
    profile = make_profile("raw")
    monkeypatch.setattr(actual_packet, "CODE_OWNED_PACKET_APPROVALS", {packet.packet_id: packet})
    monkeypatch.setattr(actual_profile, "QUALIFIED_ACTUAL_PROFILES", {"test.raw": profile})
    barrier = threading.Barrier(8)
    refusals: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        transport = RecordingTransport(success_reply(), binding=expected_binding(packet, "raw.baseline"))
        barrier.wait()
        try:
            actual_runner.run_actual_specimen(
                "raw.baseline", store=AttemptStore(store_dir), transport=transport, packet_id=packet.packet_id,
                profile_id="test.raw", clock=clock, now_epoch=NOW, started_at_epoch=NOW)
        except SpecimenRefused as error:
            with lock:
                refusals.append(error.code)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(list(store_dir.glob("raw.baseline.intent.json"))) == 1
    assert refusals == ["ALREADY_CLAIMED"] * 7


CHILD_PRELUDE = f"""
import json, os, sys
sys.path.insert(0, {str(TESTS_DIR)!r})
from pathlib import Path
from _actual_support import NOW, code_reply, expected_binding, make_packet, make_profile
from scripts.privy_unfunded_proof import actual_runner
import scripts.privy_unfunded_proof.actual_packet as ap
import scripts.privy_unfunded_proof.actual_profile as apr
from scripts.privy_unfunded_proof.specimens import AttemptStore
root = Path(sys.argv[1]); markers = Path(sys.argv[2])
packet = make_packet(); profile = make_profile("raw")
ap.CODE_OWNED_PACKET_APPROVALS = {{packet.packet_id: packet}}
apr.QUALIFIED_ACTUAL_PROFILES = {{"test.raw": profile}}
class T:
    def binding(self):
        return expected_binding(packet, "raw.baseline")
    def send(self, request):
        (markers / ("sent-" + str(os.getpid()))).write_text("x")
        if sys.argv[3] == "die":
            os._exit(17)
        return code_reply(403, "test_wallet_not_authorized")
try:
    result = actual_runner.run_actual_specimen("raw.baseline", store=AttemptStore(root), transport=T(),
        packet_id=packet.packet_id, profile_id="test.raw", clock=lambda: "2026-10-18T00:00:00Z",
        now_epoch=NOW, started_at_epoch=NOW)
    print("RESULT", result.outcome)
except Exception as error:
    print("REFUSED", type(error).__name__, getattr(error, "code", ""))
"""


def test_concurrent_processes_send_once(store_dir: Path) -> None:
    markers = store_dir / "markers"
    markers.mkdir()
    attempts = store_dir / "attempts"
    attempts.mkdir()
    code = CHILD_PRELUDE.replace("sys.argv[1]", repr(str(attempts))).replace(
        "sys.argv[2]", repr(str(markers))).replace("sys.argv[3]", repr("live"))
    children = [
        subprocess.Popen([sys.executable, "-B", "-s", "-c", code], cwd=CHECKOUT_ROOT, env=dict(os.environ),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(4)
    ]
    outputs = [child.communicate(timeout=60) for child in children]
    assert all(child.returncode == 0 for child in children), outputs
    lines = sorted(out.strip() for out, _ in outputs)
    assert len(list(markers.iterdir())) == 1
    assert sum(line.startswith("RESULT") for line in lines) == 1
    assert sum(line.startswith("REFUSED") for line in lines) == 3


def test_fresh_process_refuses_specimen_lost_after_intent(store_dir: Path) -> None:
    markers = store_dir / "markers"
    markers.mkdir()
    attempts = store_dir / "attempts"
    attempts.mkdir()
    first = run_child(CHILD_PRELUDE.replace("sys.argv[1]", repr(str(attempts))).replace(
        "sys.argv[2]", repr(str(markers))).replace("sys.argv[3]", repr("die")))
    assert first.returncode == 17, first.stderr
    assert len(list(markers.iterdir())) == 1
    assert AttemptStore(attempts).state("raw.baseline") is AttemptState.INTENT_SAVED
    second = run_child(CHILD_PRELUDE.replace("sys.argv[1]", repr(str(attempts))).replace(
        "sys.argv[2]", repr(str(markers))).replace("sys.argv[3]", repr("live")))
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "REFUSED SpecimenRefused ATTEMPT_UNCERTAIN"
    assert len(list(markers.iterdir())) == 1


# ---------------------------------------------------------------- classification


@pytest.mark.parametrize(
    "reply,reason",
    [
        (Reply(403, "text/html", b"<html>Cloudflare 1010</html>"), "NON_JSON"),
        (Reply(403, "application/json", b'{"error":"forbidden"}'), "UNRECOGNIZED_REPLY"),
        (Reply(400, "application/json", b"{not json"), "MALFORMED_JSON"),
        (Reply(400, "application/json", b'["test_policy_violation"]'), "UNRECOGNIZED_REPLY"),
        (Reply(200, "application/json", b'{"data":{}}'), "MALFORMED_SUCCESS"),
        (Reply(500, "application/json", b'{"code":"test_policy_violation"}'), "UNRECOGNIZED_REPLY"),
    ],
)
def test_generic_and_malformed_replies_are_unknown(store_dir: Path, reply: Reply, reason: str) -> None:
    allow_baseline(store_dir)
    result = run_actual("raw.wrong_chain", store_dir, RecordingTransport(reply))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, reason)
    assert result.matches_expectation is False


def test_oversized_reply_is_unknown(store_dir: Path) -> None:
    reply = success_reply()
    body = reply.body + b" " * (actual_runner.MAX_REPLY_BYTES - len(reply.body) + 1)
    result = run_actual("raw.baseline", store_dir,
                        RecordingTransport(Reply(200, "application/json", body)))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "RESPONSE_OVER_BOUND")


def test_deeply_nested_reply_is_unknown(store_dir: Path) -> None:
    allow_baseline(store_dir)
    body = b"[" * 8000 + b"]" * 8000
    result = run_actual("raw.wrong_chain", store_dir, RecordingTransport(Reply(400, "application/json", body)))
    assert result.outcome is Outcome.UNKNOWN
    assert result.reason in {"MALFORMED_JSON", "UNRECOGNIZED_REPLY"}


def test_codes_classify(store_dir: Path) -> None:
    allow_baseline(store_dir)
    policy = run_actual("raw.wrong_chain", store_dir, RecordingTransport(code_reply(400, "test_policy_violation")))
    assert (policy.outcome, policy.matches_expectation) == (Outcome.POLICY_DENY, True)
    authz = run_actual("raw.foreign_wallet", store_dir,
                       RecordingTransport(code_reply(403, "test_wallet_not_authorized")))
    assert (authz.outcome, authz.matches_expectation) == (Outcome.AUTHORIZATION_DENY, True)
    schema = run_actual("raw.gas_limit", store_dir, RecordingTransport(code_reply(400, "test_invalid_field")))
    assert (schema.outcome, schema.matches_expectation) == (Outcome.SCHEMA_REJECTED, False)
    expiry = run_actual("raw.request_expiry", store_dir, RecordingTransport(code_reply(400, "test_request_expired")))
    assert (expiry.outcome, expiry.reason, expiry.matches_expectation) == (Outcome.UNKNOWN, "EXPIRY_REFUSAL", True)
    assert not (store_dir / "STOP.json").exists()


def test_success_on_negative_is_breach(store_dir: Path) -> None:
    allow_baseline(store_dir)
    result = run_actual("raw.wrong_chain", store_dir, RecordingTransport(success_reply()))
    assert (result.outcome, result.reason) == (Outcome.BREACH, "ALLOWED_WHERE_DENIAL_REQUIRED")
    assert (store_dir / "STOP.json").exists()


def test_personal_sign_profile_refused(store_dir: Path) -> None:
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.personal_sign", store_dir, transport)
    assert caught.value.code == "REQUEST_PROFILE_UNQUALIFIED"
    assert transport.requests == []


def test_envelope_variant_profile_refused(store_dir: Path) -> None:
    for specimen_id in ("raw.type1_envelope", "raw.type0_envelope"):
        transport = RecordingTransport(success_reply())
        with pytest.raises(SpecimenRefused) as caught:
            run_actual(specimen_id, store_dir, transport)
        assert caught.value.code == "REQUEST_PROFILE_UNQUALIFIED"
        assert transport.requests == []


def test_signed_field_mismatch_is_breach(store_dir: Path) -> None:
    result = run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()),
                        decoder_factory=mismatched_factory)
    assert (result.outcome, result.reason) == (Outcome.BREACH, "SIGNED_FIELDS_MISMATCH")
    outcome = json.loads((store_dir / "raw.baseline.outcome.json").read_text())
    assert outcome["signed_field_reasons"] == ["SIGNED_CHAINID_MISMATCH"]


def test_decode_failure_on_expected_allow_is_unknown(store_dir: Path) -> None:
    def failing_factory(unsigned, wallet):  # noqa: ANN001
        def decode(raw: bytes) -> SignedDecode:
            raise ValueError("bad rlp")

        return decode

    result = run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()),
                        decoder_factory=failing_factory)
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "DECODE_FAILED")


def test_unexpected_failure_stops_stage(store_dir: Path) -> None:
    allow_baseline(store_dir)
    run_actual("raw.wrong_chain", store_dir, RecordingTransport(Reply(502, "text/html", b"bad gateway")))
    assert (store_dir / "STOP.json").exists()
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_to", store_dir, transport)
    assert caught.value.code == "STAGE_STOPPED"
    assert transport.requests == []


def test_breach_stops_later_specimens(store_dir: Path) -> None:
    allow_baseline(store_dir)
    run_actual("raw.wrong_chain", store_dir, RecordingTransport(success_reply()))
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_to", store_dir, transport)
    assert caught.value.code == "STAGE_STOPPED"
    assert transport.requests == []


# ---------------------------------------------------------------- capture, redaction, durable writes


def test_capture_saved_before_parse(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}
    real_loads = json.loads

    def watching_loads(text, *args, **kwargs):  # noqa: ANN001
        blob = text if isinstance(text, (str, bytes)) else b""
        if "signed_transaction" in blob or '"code"' in blob:
            seen.setdefault("capture_exists_at_parse", (store_dir / "raw.baseline.capture.json").exists())
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(actual_runner.json, "loads", watching_loads)
    result = run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()))
    assert result.outcome is Outcome.ALLOW
    assert seen["capture_exists_at_parse"] is True
    capture = json.loads((store_dir / "raw.baseline.capture.json").read_text())
    assert capture["media_type"] == "application/json"
    assert capture["evidence_class"] == "LOCAL_TESTED"
    assert capture["packet_id"] == make_packet().packet_id
    assert "content_type" not in capture


def test_reply_secrets_never_saved(store_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    leaky = Reply(200, "application/json",
                  json.dumps({"method": "eth_signTransaction",
                              "data": {"signed_transaction": "0x" + "ab" * 100,
                                       "nested": {"secret": CANARY}, "encoding": "rlp"}}).encode())
    results = [run_actual("raw.baseline", store_dir, RecordingTransport(leaky))]
    error = RuntimeError(f"transport failed token={CANARY}")
    results.append(run_actual("raw.wrong_chain", store_dir, RecordingTransport(error=error)))
    surfaces = [all_saved_text(store_dir), capsys.readouterr().out, capsys.readouterr().err]
    surfaces += [repr(r) for r in results] + [str(r) for r in results]
    for surface in surfaces:
        assert CANARY not in surface
    assert results[1].reason == "SEND_FAILED"


def _short_writes(monkeypatch: pytest.MonkeyPatch, marker: bytes, mode: str) -> None:
    real_write = specimens.os.write
    state = {"done": False}

    def write(fd: int, data) -> int:  # noqa: ANN001
        if marker in bytes(data) and not state["done"]:
            state["done"] = True
            if mode == "zero":
                return 0
            raise OSError("disk failed after partial write")
        return real_write(fd, data)

    monkeypatch.setattr(specimens.os, "write", write)


def test_outcome_short_write_is_not_allow(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _short_writes(monkeypatch, b'"matches_expectation"', "zero")
    result = run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "OUTCOME_NOT_PERSISTED")
    monkeypatch.undo()
    assert AttemptStore(store_dir).state("raw.baseline") is not AttemptState.TERMINAL


def test_capture_short_write_is_unknown(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _short_writes(monkeypatch, b'"metadata_valid"', "zero")
    result = run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "CAPTURE_FAILED")
    monkeypatch.undo()
    assert AttemptStore(store_dir).state("raw.baseline") is AttemptState.INTENT_SAVED


def test_capture_failure_does_not_hide_breach(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allow_baseline(store_dir)

    def failing_capture(self, specimen_id, record):  # noqa: ANN001
        raise OSError("capture disk failure")

    monkeypatch.setattr(AttemptStore, "write_capture", failing_capture)
    result = run_actual("raw.wrong_chain", store_dir, RecordingTransport(success_reply()))
    assert (result.outcome, result.reason) == (Outcome.BREACH, "ALLOWED_WHERE_DENIAL_REQUIRED")


def test_capture_failure_keeps_allow_unqualified(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_capture(self, specimen_id, record):  # noqa: ANN001
        raise OSError("capture disk failure")

    monkeypatch.setattr(AttemptStore, "write_capture", failing_capture)
    result = run_actual("raw.baseline", store_dir, RecordingTransport(success_reply()))
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "CAPTURE_FAILED")


# ---------------------------------------------------------------- transport


class _FakeHttp:
    def __init__(self, response=None, error=None):  # noqa: ANN001
        self.response = response
        self.error = error
        self.calls: list = []

    def request(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _transport(http, **overrides):  # noqa: ANN001
    fields = {
        "http": http,
        "destination": URL_A,
        "wallet_id": "synthetic-probe-wallet-a",
        "app_id": "app-test-1",
        "app_secret": "secret-1",
        "authorize": lambda payload: "signature",
        "request_id": "attempt-1:raw.baseline",
        "request_expiry_ms": 1_792_000_000_000,
        "connect_timeout_seconds": 5.0,
        "deadline_monotonic": 10.0,
        "max_response_bytes": 20000,
        "monotonic": lambda: 0.0,
        "wall_clock_ms": lambda: 1_700_000_000_000,
    }
    fields.update(overrides)
    return ActualSignOnlyTransport(**fields)


def test_transport_sends_once_and_rejects_second_send() -> None:
    from edge_os_api.research_history.http_clients.http_transport import HttpResponse

    request = specimens.FROZEN_TABLE.get("raw.baseline").request
    http = _FakeHttp(response=HttpResponse(status=200, headers={}, body=b"{}"))
    transport = _transport(http)
    assert transport.send(request).status == 200
    with pytest.raises(TransportRefused) as caught:
        transport.send(request)
    assert caught.value.code == "TRANSPORT_ALREADY_USED"
    assert len(http.calls) == 1


def test_transport_composes_with_runner(store_dir: Path) -> None:
    from edge_os_api.research_history.http_clients.http_transport import HttpResponse

    body = success_reply().body
    http = _FakeHttp(response=HttpResponse(status=200, headers={"content-type": "application/json"}, body=body))
    transport = _transport(http)
    result = run_actual("raw.baseline", store_dir, transport)
    assert result.outcome is Outcome.ALLOW
    assert len(http.calls) == 1
    capture = json.loads((store_dir / "raw.baseline.capture.json").read_text())
    assert capture["media_type"] == "application/json"
    assert capture["metadata_valid"] is True


def test_transport_refuses_wrong_destination() -> None:
    request = specimens.FROZEN_TABLE.get("raw.baseline").request
    other = "https://api.privy.io/v1/wallets/synthetic-probe-wallet-b/rpc"
    with pytest.raises(TransportRefused) as caught:
        _transport(_FakeHttp(), destination=other, wallet_id="synthetic-probe-wallet-b").send(request)
    assert caught.value.code == "DESTINATION_NOT_APPROVED"


def test_transport_refuses_changed_authorization_payload() -> None:
    request = specimens.FROZEN_TABLE.get("raw.baseline").request

    def mutating(payload):  # noqa: ANN001
        payload["method"] = "PUT"
        return "signature"

    with pytest.raises(TransportRefused) as caught:
        _transport(_FakeHttp(), authorize=mutating).send(request)
    assert caught.value.code == "AUTHORIZATION_PAYLOAD_CHANGED"


def test_transport_refuses_authorizer_failure() -> None:
    request = specimens.FROZEN_TABLE.get("raw.baseline").request

    def failing(payload):  # noqa: ANN001
        raise ValueError("no key")

    with pytest.raises(TransportRefused) as caught:
        _transport(_FakeHttp(), authorize=failing).send(request)
    assert caught.value.code == "AUTHORIZATION_FAILED"


def test_transport_reports_lost_reply() -> None:
    request = specimens.FROZEN_TABLE.get("raw.baseline").request
    with pytest.raises(TransportLost):
        _transport(_FakeHttp(error=TimeoutError("timeout"))).send(request)


def test_transport_constructor_rejects_bad_arguments() -> None:
    for overrides in ({"app_id": ""}, {"request_expiry_ms": 0}, {"destination": 5}):
        with pytest.raises((ValueError, TypeError)):
            _transport(_FakeHttp(), **overrides)


# ---------------------------------------------------------------- gate REVISE1 repairs (F1-F5, F7)


def test_public_run_has_no_caller_approval_parameters() -> None:
    import inspect

    params = inspect.signature(actual_runner.run_actual_specimen).parameters
    for name in ("approvals", "profiles", "type4_authorities"):
        assert name not in params
    assert "approvals" not in inspect.signature(actual_packet.resolve_approved_packet).parameters
    assert "profiles" not in inspect.signature(actual_profile.resolve_qualified_profile).parameters


def test_caller_packet_cannot_dispatch_with_empty_registries(store_dir: Path) -> None:
    packet = make_packet()
    transport = RecordingTransport(success_reply())
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, packet=packet, inject=False)
    assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"
    assert transport.requests == []
    assert list(store_dir.iterdir()) == []


def test_runner_refuses_transport_binding_mismatch(store_dir: Path) -> None:
    packet = make_packet()
    wrong = expected_binding(packet, "raw.baseline")
    wrong["app_id"] = "other-app"
    transport = RecordingTransport(success_reply(), binding=wrong)
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, transport, packet=packet, auto_binding=False)
    assert caught.value.code == "TRANSPORT_BINDING_MISMATCH"
    assert transport.requests == []
    assert list(store_dir.iterdir()) == []


def test_runner_refuses_transport_without_binding(store_dir: Path) -> None:
    class NoBinding:
        def send(self, request):  # noqa: ANN001
            raise AssertionError("must not send")

    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.baseline", store_dir, NoBinding(), auto_binding=False)
    assert caught.value.code == "TRANSPORT_NOT_BOUND"


def test_unsupported_request_profile_refused_before_effect(store_dir: Path) -> None:
    for specimen_id in ("raw.type1_envelope", "raw.type0_envelope", "raw.personal_sign"):
        transport = RecordingTransport(success_reply())
        with pytest.raises(SpecimenRefused) as caught:
            run_actual(specimen_id, store_dir, transport)
        assert caught.value.code == "REQUEST_PROFILE_UNQUALIFIED"
        assert transport.requests == []
        assert list(store_dir.iterdir()) == []


def test_failed_stop_write_blocks_later_send(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_stop(self, record):  # noqa: ANN001
        raise OSError("stop disk failure")

    monkeypatch.setattr(AttemptStore, "stop", failing_stop)
    first = run_actual("raw.baseline", store_dir, RecordingTransport(error=TimeoutError("lost")))
    assert (first.outcome, first.reason) == (Outcome.UNKNOWN, "SEND_FAILED")
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_chain", store_dir, transport)
    assert caught.value.code == "UNRESOLVED_ATTEMPT_IN_STORE"
    assert transport.requests == []


def test_saved_unknown_without_stop_blocks(store_dir: Path) -> None:
    store = AttemptStore(store_dir)
    store.claim_record("raw.baseline", {"specimen_id": "raw.baseline", "state": "INTENT_SAVED"})
    store.write_outcome("raw.baseline", {"specimen_id": "raw.baseline", "outcome": "UNKNOWN", "reason": "SEND_FAILED"})
    assert not (store_dir / "STOP.json").exists()
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_chain", store_dir, transport)
    assert caught.value.code == "STOPPED_AFTER_UNKNOWN"
    assert transport.requests == []


def test_stale_positive_control_refused(store_dir: Path) -> None:
    allow_baseline(store_dir)
    changed = make_packet(profile_policies={"raw": "policy-raw-2", "decoded": "policy-decoded-2"},
                          profile_policy_sha256={"raw": "sha-raw-2", "decoded": "sha-decoded-2"})
    transport = RecordingTransport(code_reply(400, "test_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run_actual("raw.wrong_chain", store_dir, transport, packet=changed)
    assert caught.value.code == "POSITIVE_CONTROL_NOT_QUALIFIED"
    assert transport.requests == []


def test_request_identity_is_the_actual_request(store_dir: Path) -> None:
    base = make_packet()
    transaction = dict(specimens.BASELINE_TRANSACTION)
    transaction["nonce"] = 7
    alt = freeze_request("synthetic-probe-wallet-a",
                         {"method": "eth_signTransaction", "params": {"transaction": transaction}})
    packet = make_packet(requests={**base.requests, "raw.baseline": alt})
    transport = RecordingTransport(success_reply())
    result = run_actual("raw.baseline", store_dir, transport, packet=packet)
    assert result.outcome is Outcome.ALLOW
    assert transport.requests[0] is alt
    intent = json.loads((store_dir / "raw.baseline.intent.json").read_text())
    capture = json.loads((store_dir / "raw.baseline.capture.json").read_text())
    outcome = json.loads((store_dir / "raw.baseline.outcome.json").read_text())
    table_hash = specimens.FROZEN_TABLE.get("raw.baseline").request.request_sha256
    assert alt.request_sha256 != table_hash
    assert intent["request_sha256"] == capture["request_sha256"] == outcome["request_sha256"] == alt.request_sha256
    assert outcome["policy_id"] == packet.profile_policies["raw"]
    assert outcome["policy_sha256"] == packet.profile_policy_sha256["raw"]


def test_transport_refuses_broadcast_operation() -> None:
    base = specimens.FROZEN_TABLE.get("raw.baseline").request
    off = replace_request(base, body=specimens.canonical_json({"method": "eth_sendTransaction", "params": {}}))
    http = _FakeHttp()
    with pytest.raises(TransportRefused) as caught:
        _transport(http).send(off)
    assert caught.value.code == "OPERATION_NOT_APPROVED"
    assert http.calls == []


def test_transport_refuses_unsupported_request_profile() -> None:
    transaction = {"type": 1, "chain_id": 143, "nonce": 0, "to": "0x" + "11" * 20, "value": 0,
                   "data": "0x", "gas_limit": 1, "gas_price": 1}
    off = freeze_request("synthetic-probe-wallet-a",
                         {"method": "eth_signTransaction", "params": {"transaction": transaction}})
    http = _FakeHttp()
    with pytest.raises(TransportRefused) as caught:
        _transport(http).send(off)
    assert caught.value.code == "REQUEST_PROFILE_UNQUALIFIED"
    assert http.calls == []


def test_transport_rejects_non_wallet_destination() -> None:
    with pytest.raises(ValueError):
        _transport(_FakeHttp(), destination="https://api.privy.io/v1/wallets/synthetic-probe-wallet-a/admin")


def test_transport_uses_frozen_expiry_header() -> None:
    from edge_os_api.research_history.http_clients.http_transport import HttpResponse

    request = specimens.FROZEN_TABLE.get("raw.request_expiry").request
    http = _FakeHttp(response=HttpResponse(status=200, headers={}, body=b"{}"))
    transport = _transport(http, request_expiry_ms=1_700_000_000_000, wall_clock_ms=lambda: 1_600_000_000_000)
    transport.send(request)
    assert http.calls[0]["headers"]["privy-request-expiry"] == "1792000000000"


def test_transport_failures_have_no_context() -> None:
    request = specimens.FROZEN_TABLE.get("raw.baseline").request

    def failing(payload):  # noqa: ANN001
        raise ValueError(f"canary {CANARY}")

    cases = [
        (_transport(_FakeHttp(), authorize=failing), TransportRefused),
        (_transport(_FakeHttp(error=TimeoutError(CANARY))), TransportLost),
    ]
    for transport, expected in cases:
        with pytest.raises(expected) as caught:
            transport.send(request)
        assert caught.value.__context__ is None
        assert caught.value.__cause__ is None
        assert CANARY not in repr(caught.value)
        assert CANARY not in str(caught.value)
