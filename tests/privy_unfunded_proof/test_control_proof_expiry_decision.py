"""Expiry as decision_required when Privy refused the expired request with an unreadable 401. Fakes only; no network.

The recorded shape (controller, 2026-10-26): the earlier run and its one re-run both got HTTP 401,
application/json, 113 bytes, raw_body_sha256 76a0174d..., null error_code and error_type, so both ended
UNKNOWN / UNRECOGNIZED_REPLY; the positive control in the same packet was ALLOW / SIGNED_FIELDS_MATCH.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts.privy_unfunded_proof import actual_packet, chain_proof, control_proofs
from scripts.privy_unfunded_proof.actual_packet import CONTROL_PROOF_PACKET, CONTROL_PROOF_TABLE
from scripts.privy_unfunded_proof.actual_runner import expiry_rerun_store, run_actual_specimen
from scripts.privy_unfunded_proof.specimens import AttemptStore, canonical_json

from tests.privy_unfunded_proof._actual_support import Reply, code_reply
from tests.privy_unfunded_proof._control_support import authored, privy_captures, privy_records, recorded_chain
from tests.privy_unfunded_proof.test_control_proof_expiry_rerun import (  # noqa: F401 - the fixture is used by name
    NOW,
    _first_four,
    _store,
    _Transport,
    privy,
)

EXPIRY = "raw.ctl_deny_expired_request"
POSITIVE = "raw.ctl_allow_revoke_zero"
LIVE_BODY_SHA256 = "76a0174db6daea58159332a34aacd9d9274290b7372b4acb3f3c95066eb95140"
LIVE_POSITIVE_SHA256 = "581ee1c6cdde61213c2a3bf98072d4a46bb24385c39ea9e4e28bdf96635fc442"
REPO = Path(__file__).resolve().parents[2]


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _capture(captured_at: str, **changes: object) -> dict:
    """A capture record shaped as ``actual_runner`` saves it for the recorded 401."""
    packet = CONTROL_PROOF_PACKET
    capture = {"specimen_id": EXPIRY, "profile": "raw", "packet_id": packet.packet_id,
               "policy_id": packet.profile_policies["raw"], "request_sha256": packet.requests[EXPIRY].request_sha256,
               "status": 401, "media_type": "application/json",
               "content_type_sha256": hashlib.sha256(b"application/json").hexdigest(), "byte_count": 113,
               "raw_body_sha256": LIVE_BODY_SHA256, "error_code": None, "error_type": None, "metadata_valid": True,
               "captured_at": captured_at, "evidence_class": actual_packet.ACTUAL_EVIDENCE_CLASS}
    capture.update(changes)
    return capture


def _recorded() -> dict:
    """Records, capture hashes and expiry captures for the recorded live shape, as the builder receives them."""
    first = _capture("2026-10-23T08:00:00.123456+00:00")
    again = _capture("2026-10-26T09:30:00.654321+00:00")
    records = privy_records()
    earlier = {**records[EXPIRY], "reason": "UNRECOGNIZED_REPLY", "matches_expectation": False,
               "capture_record_sha256": _sha(first), "completed_at": "2026-10-23T08:00:00.200000+00:00"}
    rerun = {**records[EXPIRY], "reason": "UNRECOGNIZED_REPLY", "matches_expectation": False,
             "capture_record_sha256": _sha(again), "completed_at": "2026-10-26T09:30:00.700000+00:00",
             "rerun_of": {"earlier_outcome_record_sha256": _sha(earlier),
                          "positive_control_outcome_record_sha256": _sha(records[POSITIVE])}}
    captures = {**privy_captures(), EXPIRY: _sha(again)}
    return {"records": {**records, EXPIRY: rerun}, "earlier": {EXPIRY: earlier}, "captures": captures,
            "expiry_captures": {"earlier": first, "rerun": again}}


def _build(state: dict) -> dict:
    return control_proofs.build_control_proofs(
        authored=authored(), privy_records=state["records"], privy_capture_sha256=state["captures"],
        chain_records=recorded_chain(), privy_earlier_records=state["earlier"],
        privy_expiry_captures=state["expiry_captures"])


def _recite(state: dict) -> dict:
    """Recompute every hash a change would break, so a test changes exactly one fact."""
    records, earlier, captures = state["records"], state["earlier"][EXPIRY], state["expiry_captures"]
    earlier["capture_record_sha256"] = _sha(captures["earlier"])
    records[EXPIRY]["capture_record_sha256"] = state["captures"][EXPIRY] = _sha(captures["rerun"])
    records[EXPIRY]["rerun_of"] = {"earlier_outcome_record_sha256": _sha(earlier),
                                   "positive_control_outcome_record_sha256": _sha(records[POSITIVE])}
    return state


# ---------------------------------------------------------------- the recorded shape


def test_the_recorded_unreadable_401_makes_expiry_decision_required_with_its_evidence() -> None:
    state = _recorded()
    result = _build(state)
    assert "expiry_freshness" not in result["unproven"] and "expiry_freshness" not in result["controls"]
    entry = result["decision_required"]["expiry_freshness"]
    assert entry["reason"] == "PRIVY_REFUSAL_REASON_NOT_READABLE"
    artifact = entry["artifact"]
    assert (artifact["state"], artifact["decision_required"]) == ("DECISION_REQUIRED",
                                                                  "PRIVY_REFUSAL_REASON_NOT_READABLE")
    assert entry["proof_sha256"] == _sha(artifact)
    findings = artifact["findings"]
    reply = findings["provider_reply"]
    assert {key: reply[key] for key in ("status", "media_type", "byte_count", "raw_body_sha256", "error_code",
                                        "error_type")} == {
        "status": 401, "media_type": "application/json", "byte_count": 113, "raw_body_sha256": LIVE_BODY_SHA256,
        "error_code": None, "error_type": None}
    assert [(item["attempt"], item["outcome"], item["reason"]) for item in reply["attempts"]] == [
        ("earlier", "UNKNOWN", "UNRECOGNIZED_REPLY"), ("rerun", "UNKNOWN", "UNRECOGNIZED_REPLY")]
    assert reply["attempts"][0]["outcome_record_sha256"] == _sha(state["earlier"][EXPIRY])
    assert reply["attempts"][1]["outcome_record_sha256"] == _sha(state["records"][EXPIRY])
    assert [item["capture_record_sha256"] for item in reply["attempts"]] == [
        _sha(state["expiry_captures"]["earlier"]), _sha(state["expiry_captures"]["rerun"])]
    assert findings["positive_control"] == {"specimen_id": POSITIVE,
                                            "outcome_record_sha256": _sha(state["records"][POSITIVE]),
                                            "outcome": "ALLOW", "reason": "SIGNED_FIELDS_MATCH"}
    assert findings["refusal_reason_readable"] is False
    assert findings["expired_request_header_ms"] == actual_packet.CONTROL_PROOF_EXPIRED_HEADER
    assert [check["refusal"] for check in findings["app_expiry_checks"]] == [
        "REQUEST_EXPIRED", "INTENT_EXPIRED", "INTENT_EXPIRED", "MANDATE_EXPIRED", "EXECUTION_RELEASE_EXPIRED",
        "INTENT_EXPIRED"]
    cited = {item["operation"]: item for item in artifact["evidence"]}
    assert set(cited) == {POSITIVE, EXPIRY}
    assert cited[EXPIRY]["rerun_of"] == state["records"][EXPIRY]["rerun_of"]
    assert (cited[EXPIRY]["outcome"], cited[EXPIRY]["reason"]) == ("UNKNOWN", "UNRECOGNIZED_REPLY")
    assert artifact["claims"] == list(control_proofs._EXPIRY_UNREADABLE_CLAIMS)
    assert artifact["limits"] == list(control_proofs._EXPIRY_UNREADABLE_LIMITS)
    assert artifact["privy"]["policy_id"] == CONTROL_PROOF_PACKET.profile_policies["raw"]


def test_the_decision_saves_no_signed_bytes_or_reply_text() -> None:
    saved = canonical_json(_build(_recorded())["decision_required"]["expiry_freshness"]["artifact"])
    assert b"signed_bytes_sha256" not in saved and b"cd" * 32 not in saved
    assert b"signature\":" not in saved and b"app_secret" not in saved and b"message" not in saved


def test_the_expired_request_is_a_fresh_request_with_its_expiry_in_the_past() -> None:
    difference = control_proofs.expiry_request_difference()
    request = CONTROL_PROOF_PACKET.requests[EXPIRY]
    assert request.headers == (("privy-request-expiry", actual_packet.CONTROL_PROOF_EXPIRED_HEADER),)
    assert int(difference["sent_request_expiry_ms"]) < int(difference["fresh_request_expiry_ms"]) == int(
        CONTROL_PROOF_PACKET.auth_header_expiry)
    assert difference["fresh_request_differs_in"] == ["privy-request-expiry"]
    assert difference["fresh_request_sent"] is False
    assert difference["body_sha256"] == hashlib.sha256(request.body).hexdigest()
    # The positive control is the only signed request of the packet; it is another transaction.
    assert difference["positive_control_differs_in"] == {
        "transaction_fields": ["data", "gas_limit", "to"], "headers": ["privy-request-expiry",
                                                                       "privy-idempotency-key"]}
    sent = json.loads(request.body)["params"]["transaction"]
    assert sent["to"].lower() == chain_proof.ENTRYPOINT.lower() and sent["value"] in (0, "0x0")
    assert sent["data"] == chain_proof.swap_calldata(min_output_raw=1)
    assert dict(CONTROL_PROOF_TABLE.get(EXPIRY).request.headers) == dict(request.headers)


def test_the_transport_sends_a_frozen_expiry_only_where_the_row_has_one() -> None:
    source = (REPO / "scripts/privy_unfunded_proof/actual_transport.py").read_text(encoding="utf-8")
    assert 'expiry = frozen.get("privy-request-expiry", self._expiry)' in source
    assert ('privy_headers = {"privy-app-id": self._app_id, "privy-idempotency-key": self._request_id,\n'
            '                         "privy-request-expiry": expiry}') in source
    assert [sid for sid, request in CONTROL_PROOF_PACKET.requests.items() if request.headers] == [EXPIRY]


def test_the_recognized_expiry_code_path_is_unchanged() -> None:
    result = control_proofs.build_control_proofs(authored=authored(), privy_records=privy_records(),
                                                 privy_capture_sha256=privy_captures(),
                                                 chain_records=recorded_chain())
    entry = result["decision_required"]["expiry_freshness"]
    assert entry["reason"] == "PROVIDER_COVERS_SIGNING_CUTOFF_ONLY"
    assert set(entry["artifact"]["findings"]) == {"expired_request_header_ms", "signing_cutoff"}
    assert entry["artifact"]["claims"] == list(control_proofs._CLAIMS["expiry_freshness"])
    assert entry["artifact"]["limits"] == list(control_proofs._LIMITS["expiry_freshness"])
    # Captures given or not, a matched EXPIRY_REFUSAL record keeps the same artifact.
    with_captures = control_proofs.build_control_proofs(
        authored=authored(), privy_records=privy_records(), privy_capture_sha256=privy_captures(),
        chain_records=recorded_chain(), privy_expiry_captures=_recorded()["expiry_captures"])
    assert with_captures["decision_required"]["expiry_freshness"] == entry


# ---------------------------------------------------------------- every other shape stays unproven


def _signed(state: dict, where: str) -> None:
    target = state["records"][EXPIRY] if where == "rerun" else state["earlier"][EXPIRY]
    target["signed_bytes_sha256"] = "sha256:" + "ef" * 32


def _capture_change(which: str, **changes: object):  # noqa: ANN202
    return lambda state: state["expiry_captures"][which].update(changes)


CHANGES = {
    # Privy signed, or the reply was not an error.
    "rerun_signed_hash": lambda state: _signed(state, "rerun"),
    "earlier_signed_hash": lambda state: _signed(state, "earlier"),
    "rerun_signed_field_reasons": lambda state: state["records"][EXPIRY].update(signed_field_reasons=["to"]),
    "rerun_200": _capture_change("rerun", status=200),
    "rerun_201": _capture_change("rerun", status=201),
    "earlier_200": _capture_change("earlier", status=200),
    # A status other than 401.
    "rerun_400": _capture_change("rerun", status=400),
    "rerun_403": _capture_change("rerun", status=403),
    "rerun_500": _capture_change("rerun", status=500),
    "earlier_403": _capture_change("earlier", status=403),
    "rerun_status_text": _capture_change("rerun", status="401"),
    "rerun_status_float": _capture_change("rerun", status=401.0),
    "rerun_status_missing": lambda state: state["expiry_captures"]["rerun"].pop("status"),
    # The two replies differ.
    "body_hash_differs": _capture_change("rerun", raw_body_sha256="0" * 64),
    "earlier_body_hash_differs": _capture_change("earlier", raw_body_sha256="1" * 64),
    "byte_count_differs": _capture_change("rerun", byte_count=114),
    "content_type_differs": _capture_change("rerun", content_type_sha256="2" * 64),
    "body_hash_not_hex": _capture_change("rerun", raw_body_sha256="X" * 64),
    "body_hash_upper_case": lambda state: [capture.update(raw_body_sha256=LIVE_BODY_SHA256.upper())
                                           for capture in state["expiry_captures"].values()],
    "empty_body": lambda state: [capture.update(byte_count=0) for capture in state["expiry_captures"].values()],
    # A readable code, so the reason is known and it is not an expiry code.
    "rerun_error_code": _capture_change("rerun", error_code="invalid_authorization_signature"),
    "earlier_error_code": _capture_change("earlier", error_code="unauthorized"),
    "rerun_error_type": _capture_change("rerun", error_type="unauthorized"),
    # The capture is not the runner's JSON capture.
    "rerun_not_json": _capture_change("rerun", media_type="text/plain"),
    "rerun_metadata_invalid": _capture_change("rerun", metadata_valid=False),
    "rerun_extra_body_key": _capture_change("rerun", body="{...}"),
    "rerun_other_specimen": _capture_change("rerun", specimen_id=POSITIVE),
    "rerun_other_request": _capture_change("rerun", request_sha256="3" * 64),
    "rerun_other_packet": _capture_change("rerun", packet_id="4" * 64),
    "rerun_other_policy": _capture_change("rerun", policy_id="other-policy"),
    "captured_before_the_header_expired": _capture_change("earlier", captured_at="2026-10-14T00:00:00+00:00"),
    "rerun_not_after_earlier": _capture_change("rerun", captured_at="2026-10-23T08:00:00.123456+00:00"),
    "captured_at_unreadable": _capture_change("rerun", captured_at="yesterday"),
    "captured_at_not_utc": _capture_change("rerun", captured_at="2026-10-26T09:30:00+01:00"),
    "content_type_hash_null": lambda state: [capture.update(content_type_sha256=None)
                                             for capture in state["expiry_captures"].values()],
    "content_type_hash_not_hex": lambda state: [capture.update(content_type_sha256="hello")
                                                for capture in state["expiry_captures"].values()],
    "rerun_completed_unreadable": lambda state: state["records"][EXPIRY].update(completed_at="yesterday"),
    "earlier_completed_not_text": lambda state: state["earlier"][EXPIRY].update(completed_at={"secret": "x"}),
    "rerun_completed_before_capture": lambda state: state["records"][EXPIRY].update(
        completed_at="2020-01-01T00:00:00Z"),
    "earlier_completed_before_capture": lambda state: state["earlier"][EXPIRY].update(
        completed_at="2026-10-23T08:00:00.100000+00:00"),
    "earlier_completed_after_the_rerun_reply": lambda state: state["earlier"][EXPIRY].update(
        completed_at="2026-10-27T00:00:00+00:00"),
    # The records are not the expected unrecognized attempts.
    "rerun_matched": lambda state: state["records"][EXPIRY].update(matches_expectation=True),
    "rerun_outcome_breach": lambda state: state["records"][EXPIRY].update(outcome="BREACH"),
    "rerun_other_policy_hash": lambda state: state["records"][EXPIRY].update(policy_sha256="5" * 64),
    "earlier_other_reason": lambda state: state["earlier"][EXPIRY].update(reason="NON_JSON"),
    "earlier_other_request": lambda state: state["earlier"][EXPIRY].update(request_sha256="6" * 64),
    "earlier_extra_key": lambda state: state["earlier"][EXPIRY].update(rerun_of={"x": "y"}),
}
UNRECITED = {
    # The evidence does not hang together by hash.
    "capture_file_differs": lambda state: state["captures"].update({EXPIRY: "7" * 64}),
    # Each time stays inside its window, so only the capture-to-record hash refuses these.
    "earlier_capture_changed": _capture_change("earlier", captured_at="2026-10-23T08:00:00.150000+00:00"),
    "rerun_capture_changed": _capture_change("rerun", captured_at="2026-10-26T09:30:00.680000+00:00"),
    "rerun_cites_another_earlier": lambda state: state["records"][EXPIRY]["rerun_of"].update(
        earlier_outcome_record_sha256="8" * 64),
    "rerun_cites_another_positive": lambda state: state["records"][EXPIRY]["rerun_of"].update(
        positive_control_outcome_record_sha256=LIVE_POSITIVE_SHA256),
    "rerun_of_extra_key": lambda state: state["records"][EXPIRY]["rerun_of"].update(extra="x"),
    "no_rerun_of": lambda state: state["records"][EXPIRY].pop("rerun_of"),
    # Missing or mismatched positive control.
    "positive_missing": lambda state: state["records"].pop(POSITIVE),
    "positive_not_signed": lambda state: state["records"][POSITIVE].update(outcome="POLICY_DENY",
                                                                            reason="PRIVY_POLICY_VIOLATION"),
    "positive_no_signed_hash": lambda state: state["records"][POSITIVE].pop("signed_bytes_sha256"),
    "positive_other_policy": lambda state: state["records"][POSITIVE].update(policy_id="other-policy"),
    "positive_other_capture": lambda state: state["captures"].update({POSITIVE: "9" * 64}),
    "positive_changed_after_citation": lambda state: state["records"][POSITIVE].update(
        completed_at="2026-10-26T00:00:00Z"),
    # Missing evidence.
    "no_earlier_record": lambda state: state["earlier"].clear(),
    "no_expiry_captures": lambda state: state.update(expiry_captures=None),
    "no_earlier_capture": lambda state: state["expiry_captures"].pop("earlier"),
    "no_rerun_capture": lambda state: state["expiry_captures"].pop("rerun"),
    "capture_not_a_mapping": lambda state: state["expiry_captures"].update(rerun=[401]),
}


@pytest.mark.parametrize("name", sorted(CHANGES))
def test_a_signed_non_401_differing_or_readable_reply_stays_unproven(name: str) -> None:
    state = _recorded()
    CHANGES[name](state)
    result = _build(_recite(state))
    assert "expiry_freshness" not in result["decision_required"] and "expiry_freshness" not in result["controls"]
    assert result["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


@pytest.mark.parametrize("name", sorted(UNRECITED))
def test_evidence_that_does_not_cite_itself_or_its_positive_control_stays_unproven(name: str) -> None:
    state = _recorded()
    UNRECITED[name](state)
    result = _build(state)
    assert "expiry_freshness" not in result["decision_required"] and "expiry_freshness" not in result["controls"]
    assert result["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


def test_the_recite_helper_alone_keeps_the_decision() -> None:
    assert "expiry_freshness" in _build(_recite(_recorded()))["decision_required"]


def test_the_earlier_store_alone_stays_unproven() -> None:
    state = _recorded()
    records = {**state["records"], EXPIRY: state["earlier"][EXPIRY]}
    result = control_proofs.build_control_proofs(
        authored=authored(), privy_records=records,
        privy_capture_sha256={**state["captures"], EXPIRY: state["earlier"][EXPIRY]["capture_record_sha256"]},
        chain_records=recorded_chain(), privy_expiry_captures=state["expiry_captures"])
    assert result["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


def test_an_unbound_authored_expiry_stays_unproven_first() -> None:
    state = _recorded()
    value = authored()
    value["release"]["transaction"]["request_expires_at"] = "2026-11-01T00:00:00Z"
    result = control_proofs.build_control_proofs(
        authored=value, privy_records=state["records"], privy_capture_sha256=state["captures"],
        chain_records=recorded_chain(), privy_earlier_records=state["earlier"],
        privy_expiry_captures=state["expiry_captures"])
    assert result["unproven"]["expiry_freshness"] == {"reason": "AUTHORED_EXPIRY_NOT_BOUND"}


def test_a_breach_on_the_rerun_stays_a_breach_record_and_unproven() -> None:
    state = _recorded()
    state["records"][EXPIRY].update(outcome="BREACH", reason="ALLOWED_WHERE_DENIAL_REQUIRED",
                                    signed_bytes_sha256="ab" * 32)
    result = _build(state)
    assert result["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


# ---------------------------------------------------------------- the runner's stores, end to end


def _unreadable_401() -> Reply:
    """A JSON 401 of 113 bytes whose only field is free text, so the capture saves no code or type."""
    head, tail = b'{"error": "', b'"}'
    text = b"Request refused by the provider" + b" " * (113 - len(head) - len(tail) - 31)
    body = head + text + tail
    assert len(body) == 113
    return Reply(status=401, content_type="application/json", body=body)


def _run_at(store: AttemptStore, specimen_id: str, reply: object, at: str, rerun_of: AttemptStore | None = None):  # noqa: ANN202
    return run_actual_specimen(specimen_id, store=store, transport=_Transport(specimen_id, reply),
                               packet_id=CONTROL_PROOF_PACKET.packet_id,
                               profile_id=actual_packet.UNFUNDED_POLICY_PROFILE_ID, clock=lambda: at, now_epoch=NOW,
                               started_at_epoch=NOW, table=CONTROL_PROOF_TABLE, rerun_of=rerun_of)


def _stores(tmp_path: Path, first: Reply, second: Reply) -> Path:
    earlier = _store(tmp_path / "earlier")
    _first_four(earlier)
    result = _run_at(earlier, EXPIRY, first, "2026-10-23T08:00:00.100000+00:00")
    assert (result.outcome.value, result.reason) == ("UNKNOWN", "UNRECOGNIZED_REPLY")
    path = expiry_rerun_store(earlier.root)
    path.mkdir()
    result = _run_at(AttemptStore(path), EXPIRY, second, "2026-10-26T09:00:00.100000+00:00", rerun_of=earlier)
    assert (result.outcome.value, result.reason) == ("UNKNOWN", "UNRECOGNIZED_REPLY")
    return earlier.root


def _from_stores(root: Path) -> dict:
    records, captures = control_proofs.load_privy_store(root)
    prior = control_proofs.merge_expiry_rerun(records, captures, root)
    return control_proofs.build_control_proofs(authored=authored(), privy_records=records,
                                               privy_capture_sha256=captures, chain_records=recorded_chain(),
                                               privy_earlier_records=prior,
                                               privy_expiry_captures=control_proofs.load_expiry_captures(root))


def test_runner_stores_with_the_recorded_shape_give_the_decision(tmp_path: Path, privy) -> None:  # noqa: ANN001
    root = _stores(tmp_path, _unreadable_401(), _unreadable_401())
    capture = json.loads((expiry_rerun_store(root) / f"{EXPIRY}.capture.json").read_bytes())
    assert (capture["status"], capture["byte_count"], capture["error_code"], capture["error_type"]) == (
        401, 113, None, None)
    saved = (expiry_rerun_store(root) / f"{EXPIRY}.capture.json").read_bytes()
    assert b"Request refused" not in saved
    entry = _from_stores(root)["decision_required"]["expiry_freshness"]
    assert entry["reason"] == "PRIVY_REFUSAL_REASON_NOT_READABLE"
    assert entry["artifact"]["findings"]["provider_reply"]["raw_body_sha256"] == hashlib.sha256(
        _unreadable_401().body).hexdigest()


@pytest.mark.parametrize("second", [
    Reply(status=401, content_type="application/json", body=_unreadable_401().body.replace(b"provider", b"service!")),
    code_reply(401, "unlisted_code"),
], ids=["other_body", "readable_code"])
def test_runner_stores_with_a_different_or_readable_rerun_stay_unproven(tmp_path: Path, privy, second: Reply) -> None:  # noqa: ANN001
    root = _stores(tmp_path, _unreadable_401(), second)
    assert _from_stores(root)["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


def test_the_command_reads_both_expiry_captures(tmp_path: Path, privy, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN001
    root = _stores(tmp_path, _unreadable_401(), _unreadable_401())
    chain_dir = tmp_path / "chain"
    chain_dir.mkdir()
    (chain_dir / chain_proof.RESULTS_FILE).write_text(
        json.dumps({"schema": chain_proof.RESULTS_SCHEMA, "operations": recorded_chain()}), encoding="utf-8")
    authored_path = tmp_path / "authored.json"
    authored_path.write_text(json.dumps(authored()), encoding="utf-8")
    common = ["--authored", str(authored_path), "--privy-store", str(root), "--chain-store", str(chain_dir)]
    assert control_proofs.main([*common, "--with-expiry-rerun", "--out", str(tmp_path / "with")]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["decision_required"]["expiry_freshness"]["reason"] == "PRIVY_REFUSAL_REASON_NOT_READABLE"
    saved = (tmp_path / "with" / "expiry_freshness.proof.json").read_bytes()
    assert hashlib.sha256(saved).hexdigest() == printed["decision_required"]["expiry_freshness"]["proof_sha256"]
    assert control_proofs.main([*common, "--out", str(tmp_path / "without")]) == 0
    assert json.loads(capsys.readouterr().out)["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}
    (expiry_rerun_store(root) / f"{EXPIRY}.capture.json").unlink()
    assert control_proofs.main([*common, "--with-expiry-rerun", "--out", str(tmp_path / "gone")]) == 2
    assert not (tmp_path / "gone").exists()


# ---------------------------------------------------------------- the app's own expiry refusals


@pytest.mark.parametrize("check", control_proofs.APP_EXPIRY_CHECKS, ids=lambda check: f"{check['refusal']}")
def test_each_cited_app_check_returns_its_refusal_at_the_cited_line_and_its_tests_exist(check: dict) -> None:
    lines = (REPO / check["path"]).read_text(encoding="utf-8").splitlines()
    assert f'"{check["refusal"]}"' in lines[check["line"] - 1]
    for test in check["tests"]:
        path, name = test.split("::")
        assert re.search(rf"^def {re.escape(name.split('[')[0])}\(", (REPO / path).read_text(encoding="utf-8"),
                         re.MULTILINE), test


def test_the_cited_call_order_lines_hold() -> None:
    signer = (REPO / "apps/api/src/edge_os_api/execution/privy_signer.py").read_text(encoding="utf-8").splitlines()
    assert signer[152].strip() == "stop = self._stop()" and signer[182].strip() == "stop = self._stop()"
    assert "self._authorize(given)" in "\n".join(signer[153:182])
    assert "self._http.request(" in "\n".join(signer[183:196])
    flow = (REPO / "apps/api/src/edge_os_api/execution/original_transaction.py").read_text(
        encoding="utf-8").splitlines()
    assert flow[503].strip() == "stop = recheck()" and "signer.rpc(" in flow[512]
    ports = (REPO / "apps/api/src/edge_os_api/core/provider_ports.py").read_text(encoding="utf-8").splitlines()
    assert 'request_expiry_ms=int(parse_utc(release["transaction"]["request_expires_at"])' in ports[734]
    service = (REPO / "apps/api/src/edge_os_api/execution/service.py").read_text(encoding="utf-8").splitlines()
    assert "self._revalidate(" in service[441] and "def _begin_submission(" in service[414]
    assert "def _revalidate(" in service[625]


def test_the_proof_artifact_copies_the_checks_unchanged() -> None:
    checks = _build(_recorded())["decision_required"]["expiry_freshness"]["artifact"]["findings"]["app_expiry_checks"]
    assert checks == [{**check, "tests": list(check["tests"])} for check in copy.deepcopy(
        list(control_proofs.APP_EXPIRY_CHECKS))]


@pytest.mark.parametrize("content", ["[401]", "401", "null"])
def test_an_earlier_capture_that_is_not_an_object_is_refused(tmp_path: Path, privy, content: str) -> None:  # noqa: ANN001
    root = _stores(tmp_path, _unreadable_401(), _unreadable_401())
    (root / f"{EXPIRY}.capture.json").write_text(content, encoding="utf-8")
    records, captures = control_proofs.load_privy_store(root)
    records[EXPIRY]["capture_record_sha256"] = captures[EXPIRY]  # the record cites the file, so only its shape refuses
    with pytest.raises(control_proofs.ProofRefused) as refused:
        control_proofs.merge_expiry_rerun(records, captures, root)
    assert refused.value.code == "RERUN_EARLIER_ATTEMPT_INVALID"


def test_an_earlier_capture_whose_record_cites_it_but_not_a_401_is_refused(tmp_path: Path, privy) -> None:  # noqa: ANN001
    root = _stores(tmp_path, _unreadable_401(), _unreadable_401())
    path = root / f"{EXPIRY}.capture.json"
    path.write_bytes(path.read_bytes().replace(b'"status":401', b'"status":403'))
    records, captures = control_proofs.load_privy_store(root)
    records[EXPIRY]["capture_record_sha256"] = captures[EXPIRY]
    with pytest.raises(control_proofs.ProofRefused) as refused:
        control_proofs.merge_expiry_rerun(records, captures, root)
    assert refused.value.code == "RERUN_EARLIER_ATTEMPT_INVALID"
