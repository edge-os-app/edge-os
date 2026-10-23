"""Expiry refusal on a 401, the saved error fields, and the one-row expiry re-run. Recorded fakes only; no network."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.privy_unfunded_proof import actual_packet, actual_run, control_proofs
from scripts.privy_unfunded_proof.actual_packet import CONTROL_PROOF_ORDER, CONTROL_PROOF_PACKET, CONTROL_PROOF_TABLE
from scripts.privy_unfunded_proof.actual_profile import (
    PRIVY_POLICY_CODES,
    error_fields,
    is_expiry_refusal,
    safe_reply_field,
)
from scripts.privy_unfunded_proof.actual_runner import run_actual_specimen
from scripts.privy_unfunded_proof.specimens import AttemptStore, SpecimenRefused, canonical_json

from tests.privy_unfunded_proof._actual_support import (
    Reply,
    code_reply,
    injected,
    make_profile,
    matched_factory,
    success_reply,
)
from tests.privy_unfunded_proof._control_support import authored, privy_captures, privy_records, recorded_chain

NOW = 1_792_800_000  # 2026-10-23T08:00:00Z
EXPIRY = "raw.ctl_deny_expired_request"
POSITIVE = "raw.ctl_allow_revoke_zero"
DENIALS = ("raw.ctl_deny_approve_moe_entrypoint", "raw.ctl_deny_swap_receiver_wallet",
           "raw.ctl_deny_moe_transfer_sink")
SIGNATURE_HEX = "0x" + "ab" * 100


def _json_reply(status: int, body: object) -> Reply:
    return Reply(status=status, content_type="application/json", body=json.dumps(body).encode("utf-8"))


class _Transport:
    def __init__(self, specimen_id: str, reply: object) -> None:
        self.specimen_id, self.reply, self.sent = specimen_id, reply, []

    def binding(self) -> dict:
        return {"method": "POST", "destination": CONTROL_PROOF_PACKET.signing_url,
                "wallet_id": CONTROL_PROOF_PACKET.wallet_id, "app_id": CONTROL_PROOF_PACKET.app_id,
                "request_id": CONTROL_PROOF_PACKET.attempt_identity_for(self.specimen_id),
                "request_expiry_ms": int(CONTROL_PROOF_PACKET.auth_header_expiry)}

    def send(self, request):  # noqa: ANN001, ANN201
        self.sent.append(request)
        return self.reply


def _run(store: AttemptStore, specimen_id: str, reply: object, rerun_of: AttemptStore | None = None):  # noqa: ANN202
    transport = _Transport(specimen_id, reply)
    result = run_actual_specimen(specimen_id, store=store, transport=transport,
                                 packet_id=CONTROL_PROOF_PACKET.packet_id,
                                 profile_id=actual_packet.UNFUNDED_POLICY_PROFILE_ID,
                                 clock=lambda: "2026-10-24T00:00:00Z", now_epoch=NOW, started_at_epoch=NOW,
                                 table=CONTROL_PROOF_TABLE, rerun_of=rerun_of)
    return result, transport


@pytest.fixture
def privy():  # noqa: ANN201
    profile = make_profile("raw", decoder_factory=matched_factory, codes=dict(PRIVY_POLICY_CODES))
    with injected(CONTROL_PROOF_PACKET, {actual_packet.UNFUNDED_POLICY_PROFILE_ID: profile}):
        yield


def _store(path: Path) -> AttemptStore:
    path.mkdir()
    return AttemptStore(path)


def _first_four(store: AttemptStore) -> None:
    assert _run(store, POSITIVE, success_reply())[0].matches_expectation
    for specimen_id in DENIALS:
        assert _run(store, specimen_id, code_reply(400, "policy_violation"))[0].matches_expectation


def _earlier_live_store(tmp_path: Path, expiry_reply: object = None) -> AttemptStore:
    """The live run of 2026-10-23: four matched rows, then a 401 whose code the runner did not know."""
    store = _store(tmp_path / "earlier")
    _first_four(store)
    result, _ = _run(store, EXPIRY, expiry_reply or code_reply(401, "unlisted_code"))
    assert (result.outcome.value, result.reason) == ("UNKNOWN", "UNRECOGNIZED_REPLY")
    assert store.is_stopped()
    return store


def _files(root: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(root.iterdir())}


# ---------------------------------------------------------------- which 401 codes say the request expired


@pytest.mark.parametrize("body", [
    {"code": "request_expired"}, {"code": "authorization_signature_expired"}, {"code": "expired_request"},
    {"code": "REQUEST_EXPIRED"}, {"code": "request_expiry_exceeded"}, {"code": "expired_authorization"},
    {"error": "request_expired"}, {"error": {"code": "authorization_signature_expired", "type": "unauthorized"}},
])
def test_a_401_whose_code_says_the_request_or_its_signature_expired_is_an_expiry_refusal(body: dict) -> None:
    assert is_expiry_refusal(401, body) is True


@pytest.mark.parametrize("status,body", [
    (401, {"code": "invalid_authorization_signature"}), (401, {"code": "unauthorized"}),
    (401, {"code": "access_token_expired"}), (401, {"code": "expired_session"}), (401, {"code": "jwt_expired"}),
    (401, {"code": "invalid_request_expiry"}), (401, {"code": "request_expiry_too_far_in_future"}),
    (401, {"code": "missing_request_expiry"}), (401, {"code": "app_secret_expired"}),
    (401, {"error": "Request expired"}), (401, {"message": "request_expired"}), (401, {"type": "request_expired"}),
    (401, {"code": "request_expired", "data": {"signature": SIGNATURE_HEX}}),
    (401, {"code": "request_expired", "method": "eth_signTransaction"}),
    (401, {"code": "request_expired_1"}), (401, ["request_expired"]), (401, None),
    (403, {"code": "request_expired"}), (400, {"code": "authorization_signature_expired"}),
    (500, {"code": "request_expired"}), ("401", {"code": "request_expired"}),
])
def test_any_other_reply_is_not_an_expiry_refusal(status: object, body: object) -> None:
    assert is_expiry_refusal(status, body) is False


@pytest.mark.parametrize("value", ["policy_violation", "request_expired", "Unauthorized", "a" * 24])
def test_identifier_shaped_fields_are_kept(value: str) -> None:
    assert safe_reply_field(value) == value


@pytest.mark.parametrize("value", [
    "Request expired", "request expired at 1792000000000", "0x" + "ab" * 32, "ab" * 32, "a" * 25,
    "_".join(["abc"] * 17), "request__expired", "_request", "request_", "key=value", "é_expired",
    "c2VjcmV0LWtleQ==", "sk_live_51Hxx", "", None, 401, {"code": "x"},
])
def test_free_text_keys_hashes_and_non_strings_are_withheld(value: object) -> None:
    assert safe_reply_field(value) is None


def test_error_fields_keep_only_the_code_and_the_type() -> None:
    assert error_fields({"code": "request_expired", "type": "unauthorized", "message": "secret text"}) == {
        "error_code": "request_expired", "error_type": "unauthorized"}
    assert error_fields({"error": {"code": "policy_violation", "type": "invalid_request", "detail": "x"}}) == {
        "error_code": "policy_violation", "error_type": "invalid_request"}
    assert error_fields({"error": "Request expired"}) == {"error_code": None, "error_type": None}
    assert error_fields(["request_expired"]) == {"error_code": None, "error_type": None}


# ---------------------------------------------------------------- the capture keeps the structured fields only


def test_a_401_capture_keeps_status_code_and_type_next_to_the_hash(tmp_path: Path, privy) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    _first_four(store)
    body = {"error": {"code": "invalid_authorization_signature", "type": "unauthorized",
                      "message": "signature 0xdeadbeef over secret-material did not verify"}}
    raw = json.dumps(body).encode("utf-8")
    reply = SimpleNamespace(status=401, headers={"content-type": "application/json",
                                                 "set-cookie": "session=very-secret-cookie",
                                                 "privy-authorization-signature": "MEUCIQ-secret-sig"},
                            body=raw)
    result, _ = _run(store, EXPIRY, reply)
    assert (result.outcome.value, result.reason) == ("UNKNOWN", "UNRECOGNIZED_REPLY")
    saved = (tmp_path / "store" / f"{EXPIRY}.capture.json").read_bytes()
    capture = json.loads(saved)
    assert capture["status"] == 401 and capture["media_type"] == "application/json"
    assert capture["error_code"] == "invalid_authorization_signature" and capture["error_type"] == "unauthorized"
    assert capture["raw_body_sha256"] == hashlib.sha256(raw).hexdigest() and capture["byte_count"] == len(raw)
    for secret in (b"deadbeef", b"secret", b"MEUCIQ", b"cookie", b"message"):
        assert secret not in saved
    outcome = store.read_outcome(EXPIRY)
    assert outcome["capture_record_sha256"] == hashlib.sha256(saved).hexdigest()


def test_a_success_capture_never_parses_or_keeps_the_signature(tmp_path: Path, privy) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    assert _run(store, POSITIVE, success_reply(SIGNATURE_HEX))[0].matches_expectation
    saved = (tmp_path / "store" / f"{POSITIVE}.capture.json").read_bytes()
    capture = json.loads(saved)
    assert capture["error_code"] is None and capture["error_type"] is None
    assert SIGNATURE_HEX[2:].encode() not in saved and b"eth_signTransaction" not in saved


@pytest.mark.parametrize("reply", [
    Reply(status=401, content_type="text/plain", body=b'{"code": "request_expired"}'),
    Reply(status=401, content_type="application/json", body=b"{not json"),
    Reply(status=401, content_type="application/json", body=b'{"code": "Request expired at 1792000000000"}'),
    Reply(status=401, content_type="application/json", body=json.dumps({"code": "x" * 20000}).encode()),
])
def test_unparsable_oversized_or_free_text_errors_save_no_fields(tmp_path: Path, privy, reply: Reply) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    _first_four(store)
    result, _ = _run(store, EXPIRY, reply)
    assert result.outcome.value == "UNKNOWN" and result.reason != "EXPIRY_REFUSAL"
    capture = json.loads((tmp_path / "store" / f"{EXPIRY}.capture.json").read_bytes())
    assert capture["error_code"] is None and capture["error_type"] is None and capture["status"] == 401


# ---------------------------------------------------------------- the runner's verdict on a 401


@pytest.mark.parametrize("code", ["request_expired", "authorization_signature_expired"])
def test_the_expiry_row_with_a_401_expiry_code_matches_and_does_not_stop(tmp_path: Path, privy, code: str) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    _first_four(store)
    result, _ = _run(store, EXPIRY, code_reply(401, code))
    assert (result.outcome.value, result.reason, result.matches_expectation) == ("UNKNOWN", "EXPIRY_REFUSAL", True)
    assert not store.is_stopped() and actual_run.should_stop(result) is False
    assert json.loads((tmp_path / "store" / f"{EXPIRY}.capture.json").read_bytes())["error_code"] == code


def test_any_other_401_on_the_expiry_row_stays_unknown_and_stops(tmp_path: Path, privy) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    _first_four(store)
    result, _ = _run(store, EXPIRY, code_reply(401, "invalid_authorization_signature"))
    assert (result.outcome.value, result.reason) == ("UNKNOWN", "UNRECOGNIZED_REPLY")
    assert store.is_stopped() and actual_run.should_stop(result) is True


def test_a_401_expiry_code_on_a_policy_row_is_not_an_expiry_refusal(tmp_path: Path, privy) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    assert _run(store, POSITIVE, success_reply())[0].matches_expectation
    result, _ = _run(store, DENIALS[0], code_reply(401, "request_expired"))
    assert (result.outcome.value, result.reason, result.matches_expectation) == (
        "UNKNOWN", "UNRECOGNIZED_REPLY", False)
    assert store.is_stopped()


def test_the_documented_400_request_expired_still_matches(tmp_path: Path, privy) -> None:  # noqa: ANN001
    store = _store(tmp_path / "store")
    _first_four(store)
    result, _ = _run(store, EXPIRY, code_reply(400, "request_expired"))
    assert (result.reason, result.matches_expectation) == ("EXPIRY_REFUSAL", True)


# ---------------------------------------------------------------- the one-row re-run


def test_the_rerun_sends_only_the_expiry_row_into_a_new_store_and_cites_the_earlier_store(
        tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    before = _files(earlier.root)
    new = _store(tmp_path / "rerun")
    result, transport = _run(new, EXPIRY, code_reply(401, "request_expired"), rerun_of=earlier)
    assert (result.outcome.value, result.reason, result.matches_expectation) == ("UNKNOWN", "EXPIRY_REFUSAL", True)
    assert [request.request_sha256 for request in transport.sent] == [
        CONTROL_PROOF_PACKET.requests[EXPIRY].request_sha256]
    assert _files(earlier.root) == before
    assert sorted(_files(new.root)) == [f"{EXPIRY}.capture.json", f"{EXPIRY}.intent.json", f"{EXPIRY}.outcome.json"]
    outcome = new.read_outcome(EXPIRY)
    cited = {"earlier_outcome_record_sha256": hashlib.sha256(canonical_json(earlier.read_outcome(EXPIRY))).hexdigest(),
             "positive_control_outcome_record_sha256": hashlib.sha256(
                 (earlier.root / f"{POSITIVE}.outcome.json").read_bytes()).hexdigest()}
    assert outcome["rerun_of"] == cited
    assert json.loads((new.root / f"{EXPIRY}.intent.json").read_bytes())["rerun_of"] == cited
    assert cited["earlier_outcome_record_sha256"] == hashlib.sha256(
        (earlier.root / f"{EXPIRY}.outcome.json").read_bytes()).hexdigest()


def test_a_rerun_that_is_still_unrecognized_stops_its_own_store(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    new = _store(tmp_path / "rerun")
    result, _ = _run(new, EXPIRY, code_reply(401, "unlisted_code"), rerun_of=earlier)
    assert result.reason == "UNRECOGNIZED_REPLY" and new.is_stopped()


def _refused_rerun(new: AttemptStore, specimen_id: str, earlier: AttemptStore) -> str:
    with pytest.raises(SpecimenRefused) as refused:
        _run(new, specimen_id, code_reply(401, "request_expired"), rerun_of=earlier)
    assert not (new.root / f"{specimen_id}.intent.json").exists()
    return refused.value.code


def test_only_the_expiry_row_can_be_rerun(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    new = _store(tmp_path / "rerun")
    for specimen_id in DENIALS:
        assert _refused_rerun(new, specimen_id, earlier) == "RERUN_NOT_ALLOWED"


def test_a_rerun_needs_an_earlier_unrecognized_401(tmp_path: Path, privy) -> None:  # noqa: ANN001
    matched = _store(tmp_path / "matched")
    _first_four(matched)
    assert _run(matched, EXPIRY, code_reply(400, "request_expired"))[0].matches_expectation
    assert _refused_rerun(_store(tmp_path / "a"), EXPIRY, matched) == "RERUN_EARLIER_ATTEMPT_NOT_ELIGIBLE"
    other_status = _store(tmp_path / "status")
    _first_four(other_status)
    assert _run(other_status, EXPIRY, code_reply(400, "unlisted_code"))[0].reason == "UNRECOGNIZED_REPLY"
    assert _refused_rerun(_store(tmp_path / "b"), EXPIRY, other_status) == "RERUN_EARLIER_ATTEMPT_NOT_ELIGIBLE"
    never = _store(tmp_path / "never")
    _first_four(never)
    assert _refused_rerun(_store(tmp_path / "c"), EXPIRY, never) == "RERUN_EARLIER_ATTEMPT_NOT_ELIGIBLE"


def test_a_rerun_needs_every_other_earlier_row_matched(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _store(tmp_path / "earlier")
    assert _run(earlier, POSITIVE, success_reply())[0].matches_expectation
    for specimen_id in DENIALS[:2]:
        assert _run(earlier, specimen_id, code_reply(400, "policy_violation"))[0].matches_expectation
    assert _run(earlier, EXPIRY, code_reply(401, "unlisted_code"))[0].reason == "UNRECOGNIZED_REPLY"
    assert _refused_rerun(_store(tmp_path / "rerun"), EXPIRY, earlier) == "RERUN_EARLIER_ROW_NOT_MATCHED"


def test_a_rerun_refuses_a_tampered_earlier_capture_and_the_same_store(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    capture = earlier.root / f"{EXPIRY}.capture.json"
    original = capture.read_bytes()
    capture.write_bytes(original.replace(b'"status":401', b'"status":402'))
    assert _refused_rerun(_store(tmp_path / "rerun"), EXPIRY, earlier) == "RERUN_EARLIER_ATTEMPT_NOT_ELIGIBLE"
    capture.write_bytes(original)
    with pytest.raises(SpecimenRefused):
        _run(earlier, EXPIRY, code_reply(401, "request_expired"), rerun_of=earlier)


def test_a_rerun_without_a_qualified_earlier_positive_control_is_refused(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    (earlier.root / f"{POSITIVE}.outcome.json").unlink()
    assert _refused_rerun(_store(tmp_path / "rerun"), EXPIRY, earlier) == "POSITIVE_CONTROL_NOT_QUALIFIED"


# ---------------------------------------------------------------- the operator command


def test_the_rerun_flag_is_for_the_control_packet_and_an_existing_store(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    new = tmp_path / "new"
    assert actual_run.main(["--packet", "policy-v3", "--store", str(new), "--confirm-unfunded",
                            "--rerun-expiry-from", str(tmp_path)]) == 2
    assert "RERUN_PACKET_UNSUPPORTED" in capsys.readouterr().out
    assert actual_run.main(["--packet", "control-proofs", "--store", str(new), "--confirm-unfunded",
                            "--rerun-expiry-from", str(tmp_path / "missing")]) == 2
    assert "RERUN_STORE_MISSING" in capsys.readouterr().out
    assert not new.exists()


def test_the_rerun_command_runs_only_the_expiry_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    earlier = tmp_path / "earlier"
    earlier.mkdir()
    called: list = []

    class _FrozenTime:
        @staticmethod
        def time() -> int:
            return NOW

        @staticmethod
        def monotonic() -> float:
            return 0.0

    def fake_run(specimen_id, **kwargs):  # noqa: ANN001, ANN003, ANN202
        called.append((specimen_id, kwargs["rerun_of"].root, kwargs["store"].root))
        from scripts.privy_unfunded_proof.evidence import Outcome, RunResult

        return RunResult(specimen_id, "raw", "EXPIRY_REFUSAL", Outcome.UNKNOWN, "EXPIRY_REFUSAL", True,
                         "LOCAL_TESTED", "UNQUALIFIED")

    monkeypatch.setattr(actual_run, "time", _FrozenTime)
    monkeypatch.setattr(actual_run, "_credentials", lambda: ("app", "secret", tmp_path / "key.pem"))
    monkeypatch.setattr(actual_run, "load_pem_private_key", lambda data, password: object())
    monkeypatch.setattr(actual_run, "make_p256_authorizer", lambda private_key: (lambda payload: "sig"))
    monkeypatch.setattr(actual_run, "run_actual_specimen", fake_run)
    (tmp_path / "key.pem").write_bytes(b"not read by the fake")
    new = tmp_path / "rerun"
    assert actual_run.main(["--packet", "control-proofs", "--store", str(new), "--confirm-unfunded",
                            "--rerun-expiry-from", str(earlier)]) == 0
    assert called == [(EXPIRY, earlier, new)]
    assert f"{EXPIRY} expected=EXPIRY_REFUSAL outcome=UNKNOWN reason=EXPIRY_REFUSAL" in capsys.readouterr().out


# ---------------------------------------------------------------- the proof builder reads the re-run


def _rerun_records() -> tuple[dict, dict]:
    """Outcome records for the earlier store (expiry UNRECOGNIZED_REPLY) and the re-run record citing them."""
    records = privy_records(**{EXPIRY: {"reason": "UNRECOGNIZED_REPLY", "matches_expectation": False}})
    earlier = {EXPIRY: records[EXPIRY]}
    rerun = privy_records()[EXPIRY]
    rerun["rerun_of"] = {
        "earlier_outcome_record_sha256": hashlib.sha256(canonical_json(earlier[EXPIRY])).hexdigest(),
        "positive_control_outcome_record_sha256": hashlib.sha256(canonical_json(records[POSITIVE])).hexdigest()}
    return {**records, EXPIRY: rerun}, earlier


def _build(records: dict, earlier: dict | None) -> dict:
    return control_proofs.build_control_proofs(authored=authored(), privy_records=records,
                                               privy_capture_sha256=privy_captures(), chain_records=recorded_chain(),
                                               privy_earlier_records=earlier)


def test_the_builder_counts_a_rerun_that_cites_the_earlier_store() -> None:
    records, earlier = _rerun_records()
    result = _build(records, earlier)
    entry = result["decision_required"]["expiry_freshness"]
    assert entry["reason"] == "PROVIDER_COVERS_SIGNING_CUTOFF_ONLY"
    cited = {item["operation"]: item for item in entry["artifact"]["evidence"]}
    assert cited[EXPIRY]["rerun_of"] == records[EXPIRY]["rerun_of"]
    assert "rerun_of" not in cited[POSITIVE]


@pytest.mark.parametrize("change", [
    lambda records, earlier: records[EXPIRY]["rerun_of"].update(earlier_outcome_record_sha256="0" * 64),
    lambda records, earlier: records[EXPIRY]["rerun_of"].update(positive_control_outcome_record_sha256="0" * 64),
    lambda records, earlier: records[EXPIRY]["rerun_of"].update(extra="x"),
    lambda records, earlier: records[EXPIRY].pop("rerun_of"),
    lambda records, earlier: earlier.clear(),
    lambda records, earlier: earlier[EXPIRY].update(reason="EXPIRY_REFUSAL"),
    lambda records, earlier: records[POSITIVE].update(completed_at="2026-10-25T00:00:00Z"),
])
def test_a_rerun_that_does_not_cite_its_earlier_store_exactly_does_not_count(change) -> None:  # noqa: ANN001
    records, earlier = _rerun_records()
    change(records, earlier)
    result = _build(records, earlier)
    assert result["unproven"]["expiry_freshness"]["reason"] == "PRIVY_RECORD_INVALID"


def test_an_earlier_record_without_a_rerun_or_a_rerun_of_another_row_does_not_count() -> None:
    records = privy_records()
    result = _build(records, {EXPIRY: records[EXPIRY]})
    assert result["unproven"]["expiry_freshness"]["reason"] == "PRIVY_RECORD_INVALID"
    changed = privy_records(**{DENIALS[2]: {"rerun_of": {"earlier_outcome_record_sha256": "0" * 64,
                                                         "positive_control_outcome_record_sha256": "0" * 64}}})
    assert _build(changed, None)["unproven"]["recipient"]["reason"] == "PRIVY_RECORD_INVALID"


def test_runner_stores_feed_the_builder_end_to_end(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    new = _store(tmp_path / "rerun")
    assert _run(new, EXPIRY, code_reply(401, "request_expired"), rerun_of=earlier)[0].matches_expectation
    records, captures = control_proofs.load_privy_store(earlier.root)
    prior = control_proofs.merge_expiry_rerun(records, captures, new.root)
    result = control_proofs.build_control_proofs(authored=authored(), privy_records=records,
                                                 privy_capture_sha256=captures, chain_records=recorded_chain(),
                                                 privy_earlier_records=prior)
    assert "expiry_freshness" in result["decision_required"]
    without = control_proofs.load_privy_store(earlier.root)
    alone = control_proofs.build_control_proofs(authored=authored(), privy_records=without[0],
                                                privy_capture_sha256=without[1], chain_records=recorded_chain())
    assert alone["unproven"]["expiry_freshness"]["reason"] == "PRIVY_RECORD_INVALID"


def test_a_rerun_store_with_any_other_row_is_refused(tmp_path: Path, privy) -> None:  # noqa: ANN001
    earlier = _earlier_live_store(tmp_path)
    new = _store(tmp_path / "rerun")
    assert _run(new, EXPIRY, code_reply(401, "request_expired"), rerun_of=earlier)[0].matches_expectation
    (new.root / f"{DENIALS[0]}.outcome.json").write_bytes((earlier.root / f"{DENIALS[0]}.outcome.json").read_bytes())
    records, captures = control_proofs.load_privy_store(earlier.root)
    with pytest.raises(control_proofs.ProofRefused) as refused:
        control_proofs.merge_expiry_rerun(records, captures, new.root)
    assert refused.value.code == "RERUN_STORE_INVALID"
    assert set(CONTROL_PROOF_ORDER) >= set(records)
