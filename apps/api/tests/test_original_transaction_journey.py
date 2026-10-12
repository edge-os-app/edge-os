"""The original transaction through mounted routes, the bounded worker and public reconciliation (ORIGINAL-LOCAL).

Seam: authenticated route → saved job → worker → injected recorded clients → saved/reopened action. Expected values
are independent literals: the published eth-account example key's sender, the transaction hashes frozen in the
authored recording, the revision sizing (100 quote units) and the authored receipt amounts. SQL is read only as
independent evidence that the private bytes were saved; assertions go through the public routes.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

import financial_flows as ff
from edge_os_api.execution.original_transaction import JournalError, ReplyLost, RpcError

RECORDINGS = Path(__file__).parent / "fixtures" / "original_transaction" / "original_transaction_v1.json"
PUBLISHED_SENDER = "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23"  # eth-account docs example key's address
ENTRY_NONCE0_HASH = "0x7067b4c886f172b32b1c2839bcd70a45186817e3ade5648bb34fc0d6ea7aa28d"
EXIT_NONCE1_HASH = "0x55b5277b4b8fcd0c3f23b2f05b23f78bc0c37934a7bcbf509e1805872045dcc7"
RECEIPT_GAS = "300000000000000"  # authored gasUsed 150000 × effectiveGasPrice 2 gwei


@pytest.fixture
def recordings(tmp_path) -> Path:
    directory = tmp_path / "original"
    directory.mkdir()
    shutil.copy(RECORDINGS, directory / RECORDINGS.name)
    return directory


@pytest.fixture
def original(settings, tmp_path, recordings):
    configured = ff.fixture_settings(settings, tmp_path / "effects.jsonl").model_copy(
        update={"original_recordings_dir": str(recordings)})
    from fastapi.testclient import TestClient
    from edge_os_api.main import create_app

    with TestClient(create_app(configured)) as client:
        # A fixed start 30 s into a future five-minute decision slot, advancing with real elapsed time: no run can
        # cross a slot boundary and be refused for an expired intent or stale input instead of the case under test.
        from edge_os_api.execution.worker import decision_slot

        start = decision_slot(dt.datetime.now(dt.timezone.utc)) + dt.timedelta(minutes=5, seconds=30)
        began = time.monotonic()
        clock = lambda: start + dt.timedelta(seconds=time.monotonic() - began)  # noqa: E731
        client.app.state.financial.connected._clock = clock
        client.app.state.financial.ports.clock = clock
        yield client


def calls(recordings: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    path = recordings / "calls.jsonl"
    for line in path.read_text().splitlines() if path.exists() else []:
        name = json.loads(line)["call"]
        counts[name] = counts.get(name, 0) + 1
    return counts


def ready(client, headers, agent_id: str) -> dict[str, Any]:
    agent = ff.confirmed_agent(client, headers, agent_id, network_id=143)
    declaration = ff.funded(client, headers, agent_id)
    consent = ff.adopted(client, headers, agent_id, declaration)
    return {**agent, "declaration": declaration, "consent": consent}


def submitted(client, headers, agent_id: str) -> dict[str, Any]:
    ready(client, headers, agent_id)
    return ff.run_job(client, ff.schedule(client, headers, agent_id).json())


def original_of(action: dict[str, Any]) -> dict[str, Any]:
    return action["attempts"][-1]["content"]["original_transaction"]


@pytest.fixture
def engine(settings):
    from edge_os_api.core.database import make_engine

    created = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    yield created
    created.dispose()


def test_the_original_transaction_is_saved_before_each_effect_and_settles_once(original, owner_a, recordings,
                                                                               engine):
    job = submitted(original, owner_a, "orig-fx-original")
    assert (job["state"], job["outcome"]) == ("SUBMITTED", "SUBMITTED_UNKNOWN"), job["reason"]

    response = original.get(f"/v1/actions/{job['action_id']}", headers=owner_a)
    assert response.status_code == 200
    body = original_of(response.json())
    assert body["stage"] == "BROADCAST_RETURNED"
    assert [item["stage"] for item in body["stages"]] == [
        "PREPARED", "SIGN_REQUESTED", "SIGNED", "BROADCAST_REQUESTED", "BROADCAST_RETURNED"]
    assert body["transaction_hash"] == ENTRY_NONCE0_HASH
    assert body["wallet_address"] == PUBLISHED_SENDER and body["chain_id"] == 143 and body["nonce"] == 0
    assert body["candidate_hash"].startswith("sha256:") and body["candidate_hash"] != body["transaction_hash"]
    assert body["fee_envelope"] == {"gas_limit": 300000, "max_fee_per_gas": 3000000000,
                                    "max_priority_fee_per_gas": 1000000000}
    assert body["signing_request_id"] == response.json()["attempts"][-1]["attempt_id"]
    assert "signed_bytes" not in body and "signing_request" not in body and "unsigned" not in body
    signed = next(item["response"]["data"]["signed_transaction"] for item in json.loads(RECORDINGS.read_text())[
        "signatures"] if item["operation"] == "ENTRY" and item["nonce"] == 0)
    assert signed[2:] not in response.text  # raw signed bytes never reach the owner response
    assert calls(recordings) == {"route.quote": 1, "broadcast.eth_getTransactionCount": 1, "signer.rpc": 1,
                                 "broadcast.eth_sendRawTransaction": 1, "observer.eth_chainId": 2,
                                 "observer.eth_getBlockByNumber": 2, "observer.eth_getBalance": 2,
                                 "observer.eth_call": 8}
    with engine.connect() as connection:  # independent evidence: the private bytes were saved before broadcast
        saved = connection.execute(text(
            "SELECT content->'original_transaction' FROM execution_local.execution_submission_attempts "
            "WHERE action_id = :a"), {"a": job["action_id"]}).scalar_one()
    assert saved["signed_bytes"] == signed and saved["transaction_hash"] == ENTRY_NONCE0_HASH

    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a)
    assert settled.status_code == 200, settled.text
    assert (settled.json()["receipt_outcome"], settled.json()["case_state"]) == ("CONFIRMED", "CONFIRMED")
    action = original.get(f"/v1/actions/{job['action_id']}", headers=owner_a).json()
    receipt = action["receipts"][-1]
    assert receipt["outcome"] == "CONFIRMED"
    assert (receipt["content"]["actual_input"]["raw"], receipt["content"]["actual_output"]["raw"],
            receipt["content"]["actual_gas"]["raw"]) == (ff.ENTRY_QUOTE_INPUT, ff.ENTRY_BASE_OUTPUT, RECEIPT_GAS)
    again = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (again["applied"], again["duplicate"]) == (False, True)
    assert calls(recordings)["broadcast.eth_sendRawTransaction"] == 1 and calls(recordings)["signer.rpc"] == 1


# ------------------------------------------------------------------------------------------- fault matrix

class Inject:
    """Replace one injected original client for `fx-original` agents with an authored fault wrapper."""

    def __init__(self, client, **wrappers):
        ports = client.app.state.financial.ports
        clients, profile = ports.original.clients(ports.clock), ports.original.profile
        clients = dataclasses.replace(clients, **{name: wrap(getattr(clients, name)) for name, wrap in wrappers.items()})
        ports.original_clients = lambda agent_id: (clients, profile) if "fx-original" in agent_id else None


class Delegate:
    def __init__(self, inner, *, before=None, after=None):
        self._inner, self._before, self._after = inner, before, after

    def _run(self, method, *args):
        if self._before is not None:
            replaced = self._before(*args)
            if replaced is not None:
                return replaced
        result = getattr(self._inner, method)(*args)
        return result if self._after is None else self._after(result, *args)

    def rpc(self, wallet_id, body):
        return self._run("rpc", wallet_id, body)

    def quote(self, request):
        return self._run("quote", request)

    def call(self, method, params):
        return self._run("call", method, params)


def lost(*_):
    raise ReplyLost("authored: reply lost")


def action(client, headers, action_id):
    response = client.get(f"/v1/actions/{action_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def reservation_states(body) -> set[str]:
    return {row["state"] for row in body["reservations"]}


def test_a_signer_refusal_sends_nothing_and_releases_the_reservations(original, owner_a, recordings):
    Inject(original, signer=lambda inner: Delegate(inner, before=lambda *_: {"error": {"code": "policy_violation"}}))
    job = submitted(original, owner_a, "refuse-fx-original")
    assert (job["state"], job["outcome"]) == ("COMPLETED", "DENIED_UNSENT"), job["reason"]
    body = action(original, owner_a, job["action_id"])
    assert original_of(body)["stage"] == "REFUSED_UNSENT" and original_of(body)["reason"] == "SIGNER_REFUSED"
    assert "RESERVED" not in reservation_states(body)
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


def test_a_lost_signer_reply_keeps_the_liability_and_a_restart_makes_no_second_call(original, owner_a, recordings):
    job = submitted(original, owner_a, "sign-fx-original-fx-lost-sign")
    assert (job["state"], job["outcome"]) == ("SUBMITTED", "SUBMITTED_UNKNOWN"), job["reason"]
    body = action(original, owner_a, job["action_id"])
    assert original_of(body)["stage"] == "SIGNING_UNKNOWN" and "transaction_hash" not in original_of(body)
    assert "RESERVED" in reservation_states(body)
    before = calls(recordings)
    rerun = ff.run_job(original, job)
    assert rerun["state"] == "SUBMITTED" and calls(recordings) == before
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (settled["receipt_outcome"], settled["case_state"]) == ("SUBMISSION_UNKNOWN", "UNKNOWN")
    assert "RESERVED" in reservation_states(action(original, owner_a, job["action_id"]))
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


@pytest.mark.parametrize("reply,reason", [
    ({"method": "eth_signTransaction", "data": {"signed_transaction": "0x00", "encoding": "rlp"}},
     "TRANSACTION_TYPE_UNSUPPORTED"),
    ({"method": "eth_signTransaction", "data": {"signed_transaction": "0x02zz", "encoding": "rlp"}},
     "SIGNED_BYTES_MALFORMED"),
    ({"method": "eth_signTransaction", "data": {"signed_transaction": "0x02" + "00" * 9000, "encoding": "rlp"}},
     "SIGNED_BYTES_OVERSIZE")])
def test_rejected_signed_bytes_are_never_broadcast_and_keep_the_liability(original, owner_a, recordings, reply,
                                                                         reason):
    Inject(original, signer=lambda inner: Delegate(inner, after=lambda *_: reply))
    job = submitted(original, owner_a, f"bytes-{reason.lower()[:12]}-fx-original")
    assert (job["state"], job["outcome"]) == ("SUBMITTED", "SUBMITTED_UNKNOWN"), job["reason"]
    body = original_of(action(original, owner_a, job["action_id"]))
    assert body["stage"] == "SIGNED_RESPONSE_REJECTED" and body["reasons"] == [reason]
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


def test_signed_bytes_for_another_nonce_are_rejected(original, owner_a, recordings):
    other = next(item["response"] for item in json.loads(RECORDINGS.read_text())["signatures"]
                 if item["operation"] == "ENTRY" and item["nonce"] == 3)
    Inject(original, signer=lambda inner: Delegate(inner, after=lambda *_: other))
    job = submitted(original, owner_a, "nonce-fx-original")
    body = original_of(action(original, owner_a, job["action_id"]))
    assert body["stage"] == "SIGNED_RESPONSE_REJECTED" and body["reasons"] == ["SIGNED_NONCE_MISMATCH"]
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


@pytest.mark.parametrize("failing_stage,signs,outcome", [("PREPARED", 0, "DENIED_UNSENT"),
                                                          ("SIGN_REQUESTED", 0, "DENIED_UNSENT"),
                                                          ("SIGNED", 1, "SUBMITTED_UNKNOWN"),
                                                          ("BROADCAST_REQUESTED", 1, "SUBMITTED_UNKNOWN")])
def test_a_failed_save_stops_before_the_next_effect(original, owner_a, recordings, failing_stage, signs, outcome):
    execution = original.app.state.financial.execution
    journal = execution._journal

    def failing(owner, attempt_id):
        save = journal(owner, attempt_id)

        def guarded(stage, values):
            if stage == failing_stage:
                raise JournalError("authored: database unavailable")
            save(stage, values)
        return guarded

    execution._journal = failing
    try:
        job = submitted(original, owner_a, f"save-{failing_stage.lower().replace('_', '-')}-fx-original")
    finally:
        execution._journal = journal
    assert job["outcome"] == outcome, job["reason"]
    assert calls(recordings).get("signer.rpc", 0) == signs
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


def test_a_lost_broadcast_reply_reconciles_the_original_from_its_receipt(original, owner_a, recordings):
    Inject(original, broadcast=lambda inner: Delegate(
        inner, after=lambda result, method, params: lost() if method == "eth_sendRawTransaction" else result))
    job = submitted(original, owner_a, "ack-fx-original")
    assert job["outcome"] == "SUBMITTED_UNKNOWN"
    assert original_of(action(original, owner_a, job["action_id"]))["stage"] == "BROADCAST_UNKNOWN"
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (settled["receipt_outcome"], settled["case_state"]) == ("CONFIRMED", "CONFIRMED")
    assert calls(recordings)["broadcast.eth_sendRawTransaction"] == 1


def test_a_broadcast_reply_with_another_hash_is_kept_unknown(original, owner_a, recordings):
    Inject(original, broadcast=lambda inner: Delegate(
        inner, after=lambda result, method, params: "0x" + "ab" * 32 if method == "eth_sendRawTransaction"
        else result))
    job = submitted(original, owner_a, "hash-fx-original")
    body = original_of(action(original, owner_a, job["action_id"]))
    assert (job["outcome"], body["stage"]) == ("SUBMITTED_UNKNOWN", "BROADCAST_HASH_MISMATCH")


def test_a_stop_recorded_after_signing_prevents_the_broadcast(original, owner_a, recordings):
    def stop_then_return(result, *_):
        stopped = original.post("/v1/agents/stop-fx-original/stops", headers=owner_a,
                                json={"mode": "HALT_ALL_SWAPS", "scope": "AGENT_WALLET_NETWORK"})
        assert stopped.status_code in (200, 201), stopped.text
        return result

    Inject(original, signer=lambda inner: Delegate(inner, after=stop_then_return))
    job = submitted(original, owner_a, "stop-fx-original")
    body = original_of(action(original, owner_a, job["action_id"]))
    assert job["outcome"] == "SUBMITTED_UNKNOWN" and body["stage"] == "STOPPED_AFTER_SIGNING"
    assert body["transaction_hash"] == ENTRY_NONCE0_HASH  # saved before the stop was seen
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


class Crash(BaseException):
    """An authored process death inside the injected boundary (not an application exception)."""


def test_a_crash_after_signing_leaves_one_original_that_a_restart_never_resends(original, owner_a, recordings):
    Inject(original, broadcast=lambda inner: Delegate(
        inner, before=lambda method, params: (_ for _ in ()).throw(Crash()) if method == "eth_sendRawTransaction"
        else None))
    ready(original, owner_a, "crash-fx-original")
    scheduled = ff.schedule(original, owner_a, "crash-fx-original").json()
    with pytest.raises(Crash):
        original.app.state.financial.connected.run_job(uuid.UUID(scheduled["job_id"]))
    before = calls(recordings)
    Inject(original)  # the restarted process uses ordinary recorded clients
    rerun = ff.run_job(original, scheduled)
    assert rerun["state"] == "SUBMITTED" and calls(recordings) == before
    body = action(original, owner_a, rerun["action_id"])
    assert body["attempts"][-1]["state"] == "IN_FLIGHT" and len(body["attempts"]) == 1
    assert original_of(body)["stage"] == "BROADCAST_REQUESTED"
    settled = original.post(f"/v1/actions/{rerun['action_id']}/reconcile", headers=owner_a).json()
    assert settled["receipt_outcome"] == "SUBMISSION_UNKNOWN"  # nothing was accepted by the recorded chain
    assert "RESERVED" in reservation_states(action(original, owner_a, rerun["action_id"]))


def receipt_edit(edit):
    def after(result, method, params):
        if method == "eth_getTransactionReceipt" and result is not None:
            return edit(json.loads(json.dumps(result)))
        return result
    return lambda inner: Delegate(inner, after=after)


@pytest.mark.parametrize("edit,reason", [
    (lambda r: {**r, "transactionHash": "0x" + "cd" * 32}, "OBS_BINDING_MISSING"),
    (lambda r: {**r, "from": "0x" + "ef" * 20}, "OBS_WALLET_MISMATCH")])
def test_a_receipt_for_another_transaction_or_wallet_applies_nothing(original, owner_a, edit, reason):
    job = submitted(original, owner_a, f"tuple-{reason[4:10].lower()}-fx-original")
    Inject(original, observer=receipt_edit(edit))
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (settled["receipt_outcome"], settled["applied"], settled["detail"]) == ("REJECTED", False, reason)
    assert "RESERVED" in reservation_states(action(original, owner_a, job["action_id"]))


def test_a_receipt_on_another_chain_applies_nothing(original, owner_a):
    job = submitted(original, owner_a, "chain-fx-original")
    Inject(original, observer=lambda inner: Delegate(
        inner, after=lambda result, method, params: "0x1" if method == "eth_chainId" else result))
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (settled["receipt_outcome"], settled["detail"]) == ("REJECTED", "OBS_NETWORK_MISMATCH")


@pytest.mark.parametrize("edit,breach", [
    (lambda r: {**r, "logs": r["logs"][:1]}, "MISSING_RECONCILED"),
    (lambda r: {**r, "logs": r["logs"][1:]}, "MISSING_RECONCILED_INPUT"),
    (lambda r: {**r, "status": "0x0", "gasUsed": None}, "MISSING_RECONCILED_GAS"),
    (lambda r: {**r, "gasUsed": None}, "MISSING_RECONCILED_GAS"),
    (lambda r: {**r, "logs": [{**log, "data": hex(int(log["data"], 16))} for log in r["logs"]]},
     "MISSING_RECONCILED_INPUT")])
def test_a_receipt_without_every_actual_never_releases_the_liability(original, owner_a, edit, breach):
    job = submitted(original, owner_a, f"partial-{uuid.uuid4().hex[:8]}-fx-original")
    Inject(original, observer=receipt_edit(edit))
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    body = action(original, owner_a, job["action_id"])
    assert settled["decision_status"] == "BREACHED", settled
    assert body["admission"][0]["reason"].startswith(breach)
    assert "RESERVED" in reservation_states(body)


def test_changed_evidence_after_settlement_cannot_rewrite_the_original_outcome(original, owner_a):
    job = submitted(original, owner_a, "changed-fx-original")
    first = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert first["case_state"] == "CONFIRMED"

    def more_output(receipt):
        receipt["logs"][1]["data"] = "0x" + format(int(receipt["logs"][1]["data"], 16) + 1, "064x")
        return receipt

    Inject(original, observer=receipt_edit(more_output))
    changed = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (changed["applied"], changed["case_state"]) == (False, "DISCREPANCY")
    receipts = action(original, owner_a, job["action_id"])["receipts"]
    assert [item["content"]["actual_output"]["raw"] for item in receipts if item["outcome"] == "CONFIRMED"] == [
        ff.ENTRY_BASE_OUTPUT]


QUOTE_TOKEN = "0x2222222222222222222222222222222222222222"
BASE_TOKEN = "0x1111111111111111111111111111111111111111"


def word(value: int) -> str:
    return "0x" + format(value, "064x")


@pytest.mark.parametrize("case,change,reason", [
    ("stale", lambda h: {**h, "age_seconds": 600}, "HOLDINGS_STALE"),
    ("decimals", lambda h: {**h, "decimals": {**h["decimals"], QUOTE_TOKEN: word(18)}}, "HOLDINGS_INCOMPLETE"),
    ("missing", lambda h: {**h, "tokens": {BASE_TOKEN: h["tokens"][BASE_TOKEN]}}, "HOLDINGS_INCOMPLETE"),
    # A JSON-RPC `QUANTITY` where an `eth_call` returns a 32-byte `DATA` word is not read as a balance.
    ("quantity-form", lambda h: {**h, "tokens": {**h["tokens"], QUOTE_TOKEN: hex(1000000000)}}, "HOLDINGS_INCOMPLETE")])
def test_unusable_holdings_admit_nothing_and_show_unavailable(original, owner_a, recordings, case, change, reason):
    data = original.app.state.financial.ports.original.data
    saved = data["holdings"]
    data["holdings"] = change(saved)
    try:
        job = submitted(original, owner_a, f"hold-{case}-fx-original")
        funding = original.get(f"/v1/agents/{job['agent_id']}/funding", headers=owner_a).json()
    finally:
        data["holdings"] = saved
    assert (job["state"], job["reason"], job["action_id"]) == ("UNAVAILABLE", reason, None)
    assert funding["current_holdings"]["state"] == "UNAVAILABLE" and funding["current_holdings"]["reason"] == reason
    assert calls(recordings).get("signer.rpc", 0) == 0


def test_recorded_holdings_carry_their_observation_identity_apart_from_deposits(original, owner_a):
    ready(original, owner_a, "view-fx-original")
    funding = original.get("/v1/agents/view-fx-original/funding", headers=owner_a).json()
    holdings = funding["current_holdings"]
    assert (holdings["state"], holdings["source"], holdings["finality"], holdings["wallet_address"],
            holdings["chain_id"], holdings["block_number"]) == (
        "OBSERVED", "recorded-holdings/1", "FINALIZED", PUBLISHED_SENDER, 143, 2000000)
    assert {item["asset_id"].rsplit("/", 1)[1]: item["raw"] for item in holdings["assets"]} == {
        "0x2222222222222222222222222222222222222222": "1000000000",
        "0x1111111111111111111111111111111111111111": "50000000000000000000", "native": "1000000000000000000"}
    credited = {b["asset_id"]: b["credited_deposits"]["raw"] for b in funding["deposit_balances"]}
    assert set(credited.values()) == {ff.TRADING_DEPOSIT, ff.GAS_DEPOSIT}  # deposit history stays separate


def test_another_owner_cannot_read_or_reconcile_and_makes_no_call(original, owner_a, owner_b, recordings):
    job = submitted(original, owner_a, "owner-fx-original")
    before = calls(recordings)
    assert original.get(f"/v1/actions/{job['action_id']}", headers=owner_b).status_code == 404
    assert original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_b).status_code == 404
    assert calls(recordings) == before


def test_the_exit_is_one_more_original_transaction_with_the_next_nonce(original, owner_a, recordings):
    entry = submitted(original, owner_a, "exit-fx-original")
    original.post(f"/v1/actions/{entry['action_id']}/reconcile", headers=owner_a)
    connected, ports = original.app.state.financial.connected, original.app.state.financial.ports
    clock, ports_clock = connected._clock, ports.clock
    connected._clock = ports.clock = lambda: clock() + dt.timedelta(minutes=5)
    try:
        exit_job = ff.run_job(original, ff.schedule(original, owner_a, "exit-fx-original", "exit-slot").json())
    finally:
        connected._clock, ports.clock = clock, ports_clock
    body = action(original, owner_a, exit_job["action_id"])
    assert body["operation"] == "EXIT"
    assert (original_of(body)["nonce"], original_of(body)["transaction_hash"]) == (1, EXIT_NONCE1_HASH)
    assert calls(recordings)["broadcast.eth_sendRawTransaction"] == 2


def test_holdings_observed_on_another_chain_admit_nothing(original, owner_a, recordings):
    ff.confirmed_agent(original, owner_a, "testnet-fx-original", network_id=10143)
    declaration = ff.funded(original, owner_a, "testnet-fx-original")
    ff.adopted(original, owner_a, "testnet-fx-original", declaration)
    job = ff.run_job(original, ff.schedule(original, owner_a, "testnet-fx-original").json())
    assert (job["state"], job["reason"], job["action_id"]) == ("UNAVAILABLE", "HOLDINGS_WRONG_CHAIN", None)
    assert calls(recordings).get("route.quote", 0) == 0 and calls(recordings).get("signer.rpc", 0) == 0


def test_a_route_the_recording_does_not_hold_is_blocked_before_signing(original, owner_a, recordings):
    Inject(original, route=lambda inner: Delegate(inner, after=lambda *_: {"status": "error", "error": "NO_ROUTE"}))
    job = submitted(original, owner_a, "route-fx-original")
    body = original_of(action(original, owner_a, job["action_id"]))
    assert (job["outcome"], body["reason"]) == ("DENIED_UNSENT", "ROUTE_BLOCKED")
    assert calls(recordings).get("signer.rpc", 0) == 0


@pytest.mark.parametrize("case,reply", [
    ("camel", {"method": "eth_signTransaction", "data": {"signedTransaction": "0x02", "encoding": "rlp"}}),
    ("missing", {"method": "eth_signTransaction", "data": {"encoding": "rlp"}}),
    ("not-object", "0x02f8")])
def test_an_unrecognized_signer_reply_keeps_the_liability_and_is_never_sent(original, owner_a, recordings, case,
                                                                         reply):
    Inject(original, signer=lambda inner: Delegate(inner, after=lambda *_: reply))  # the signer did sign
    job = submitted(original, owner_a, f"reply-{case}-fx-original")
    body = action(original, owner_a, job["action_id"])
    assert job["outcome"] == "SUBMITTED_UNKNOWN", job["reason"]
    assert (original_of(body)["stage"], original_of(body)["reasons"]) == (
        "SIGNED_RESPONSE_REJECTED", ["SIGNER_REPLY_UNRECOGNIZED"])
    assert "RESERVED" in reservation_states(body)
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


def test_an_unmarked_placeholder_wallet_is_refused_as_another_signer_and_never_sent(original, owner_a, recordings):
    """Amendment A1: the placeholder fixture address has no key, so the authored signature names another sender."""
    ports = original.app.state.financial.ports
    clients = (ports.original.clients(ports.clock), ports.original.profile)
    ports.original_clients = lambda agent_id: clients
    job = submitted(original, owner_a, "placeholder-wallet")
    body = action(original, owner_a, job["action_id"])
    assert job["outcome"] == "SUBMITTED_UNKNOWN", job["reason"]
    assert original_of(body)["wallet_address"] != PUBLISHED_SENDER
    assert (original_of(body)["stage"], original_of(body)["reasons"]) == (
        "SIGNED_RESPONSE_REJECTED", ["SIGNED_SENDER_MISMATCH"])
    assert "RESERVED" in reservation_states(body)
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


def test_a_removal_recorded_after_signing_prevents_the_broadcast(original, owner_a, recordings):
    def remove_then_return(result, *_):
        removed = original.post("/v1/agents/remove-fx-original/removal", headers=owner_a,
                                json={"request_key": "remove-after-signing", "reason": "owner removed the agent"})
        assert removed.status_code in (200, 201), removed.text
        return result

    Inject(original, signer=lambda inner: Delegate(inner, after=remove_then_return))
    job = submitted(original, owner_a, "remove-fx-original")
    body = original_of(action(original, owner_a, job["action_id"]))
    assert job["outcome"] == "SUBMITTED_UNKNOWN" and body["stage"] == "STOPPED_AFTER_SIGNING"
    assert "REMOVAL_REQUESTED" in body["reason"]
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


def test_concurrent_runs_of_one_job_sign_and_send_once(original, owner_a, recordings):
    import threading

    ready(original, owner_a, "twice-fx-original")
    first = ff.schedule(original, owner_a, "twice-fx-original", "same").json()
    again = ff.schedule(original, owner_a, "twice-fx-original", "same").json()
    assert again["job_id"] == first["job_id"]
    connected = original.app.state.financial.connected
    threads = [threading.Thread(target=connected.run_job, args=(uuid.UUID(first["job_id"]),)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ff.run_job(original, first)
    assert (calls(recordings)["signer.rpc"], calls(recordings)["broadcast.eth_sendRawTransaction"]) == (1, 1)


def test_a_reconcile_during_signing_observes_nothing_and_never_interrupts_the_original(original, owner_a, recordings):
    seen = {}

    def reconcile_mid_sign(result, *_):
        actions = original.get("/v1/agents/midsign-fx-original/actions", headers=owner_a).json()
        seen["reply"] = original.post(f"/v1/actions/{actions['jobs'][0]['action_id']}/reconcile",
                                      headers=owner_a).json()
        return result

    Inject(original, signer=lambda inner: Delegate(inner, after=reconcile_mid_sign))
    job = submitted(original, owner_a, "midsign-fx-original")
    assert (seen["reply"]["receipt_outcome"], seen["reply"]["detail"], seen["reply"]["applied"]) == (
        "NOT_OBSERVED", "ORIGINAL_IN_FLIGHT", False)
    body = original_of(action(original, owner_a, job["action_id"]))
    assert (body["stage"], body["transaction_hash"]) == ("BROADCAST_RETURNED", ENTRY_NONCE0_HASH)


def test_reconciling_a_refused_original_adds_no_evidence(original, owner_a):
    Inject(original, signer=lambda inner: Delegate(inner, before=lambda *_: {"error": {"code": "policy_violation"}}))
    job = submitted(original, owner_a, "refused-again-fx-original")
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert (settled["receipt_outcome"], settled["detail"], settled["applied"]) == (
        "NOT_OBSERVED", "ORIGINAL_REFUSED_UNSENT", False)
    assert settled["case_state"] != "DISCREPANCY"


def test_holdings_whose_chain_cannot_be_read_admit_nothing(original, owner_a, recordings):
    Inject(original, observer=lambda inner: Delegate(
        inner, after=lambda result, method, params: "chain-143" if method == "eth_chainId" else result))
    ports = original.app.state.financial.ports
    observer = ports.original_clients("x-fx-original")[0].observer
    holdings, saved = ports.holdings, ports.holdings._recordings.clients
    ports.holdings._recordings.clients = lambda clock: dataclasses.replace(saved(clock), observer=observer)
    try:
        job = submitted(original, owner_a, "chainless-fx-original")
    finally:
        ports.holdings._recordings.clients = saved
    assert (job["state"], job["reason"], job["action_id"]) == ("UNAVAILABLE", "HOLDINGS_UNAVAILABLE", None)


# ------------------------------------------------------------------- gate review 1 (e5496ec) repairs

def signed_entry_nonce0() -> str:
    return next(item["response"]["data"]["signed_transaction"] for item in json.loads(RECORDINGS.read_text())[
        "signatures"] if item["operation"] == "ENTRY" and item["nonce"] == 0)


@pytest.mark.parametrize("case", ["returned-raw", "error-raw", "error-credential"])
def test_a_broadcast_reply_that_echoes_bytes_or_secrets_is_never_saved_or_shown(original, owner_a, case, engine,
                                                                               caplog):
    signed = signed_entry_nonce0()

    def echo(result, method, params):
        if method != "eth_sendRawTransaction":
            return result
        if case == "returned-raw":
            return params[0]
        raise RpcError("request rejected: " + (params[0] if case == "error-raw" else "Authorization: Bearer sk-test-xyz"))

    Inject(original, broadcast=lambda inner: Delegate(inner, after=echo))
    job = submitted(original, owner_a, f"echo-{case}-fx-original")
    response = original.get(f"/v1/actions/{job['action_id']}", headers=owner_a)
    body = original_of(response.json())
    assert job["outcome"] == "SUBMITTED_UNKNOWN" and body["broadcast_returned"] is None
    assert body["stage"] in ("BROADCAST_HASH_MISMATCH", "BROADCAST_ERROR")
    for leak in (signed[2:42], "sk-test-xyz", "Bearer"):
        assert leak not in response.text and leak not in caplog.text
    with engine.connect() as connection:  # nor in the saved envelope beyond the private signed bytes themselves
        saved = connection.execute(text(
            "SELECT content->'original_transaction' FROM execution_local.execution_submission_attempts "
            "WHERE action_id = :a"), {"a": job["action_id"]}).scalar_one()
    rest = json.dumps({key: value for key, value in saved.items() if key not in ("signed_bytes", "unsigned",
                                                                                 "signing_request", "candidate")})
    assert signed[2:42] not in rest and "sk-test-xyz" not in rest
    assert "RESERVED" in reservation_states(action(original, owner_a, job["action_id"]))


@pytest.mark.parametrize("case,topic", [
    ("short-word", lambda address: address),
    ("wrong-prefix", lambda address: "zz" + "0" * 24 + address[2:]),
    ("dirty-padding", lambda address: "0x" + "1" * 24 + address[2:])])
def test_malformed_indexed_transfer_addresses_prove_no_amount(original, owner_a, case, topic):
    job = submitted(original, owner_a, f"topic-{case}-fx-original")

    def bend(receipt):
        for log in receipt["logs"]:
            log["topics"] = [log["topics"][0]] + [topic("0x" + item[-40:]) for item in log["topics"][1:]]
        return receipt

    Inject(original, observer=receipt_edit(bend))
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    body = action(original, owner_a, job["action_id"])
    assert settled["decision_status"] == "BREACHED" and body["admission"][0]["reason"].startswith("MISSING_RECONCILED")
    assert "RESERVED" in reservation_states(body)


@pytest.mark.parametrize("delay,expected", [
    ("route", ("DENIED_UNSENT", "REFUSED_UNSENT", 0)),
    ("nonce", ("DENIED_UNSENT", "REFUSED_UNSENT", 0)),
    ("signer", ("SUBMITTED_UNKNOWN", "STOPPED_AFTER_SIGNING", 1))])
def test_a_mandate_that_expires_during_the_lifecycle_allows_no_next_effect(original, owner_a, recordings, delay,
                                                                           expected):
    from edge_os_api.execution.worker import decision_slot

    connected, ports = original.app.state.financial.connected, original.app.state.financial.ports
    start = decision_slot(dt.datetime.now(dt.timezone.utc)) + dt.timedelta(minutes=5, seconds=30)
    moment = {"now": start}
    connected._clock = ports.clock = lambda: moment["now"]
    expiry = (start + dt.timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def expire(result, *_):
        moment["now"] = start + dt.timedelta(seconds=11)  # the mandate expires; the intent is still valid
        return result

    def expire_after_nonce(result, method, params):
        return expire(result) if method == "eth_getTransactionCount" else result

    wrappers = {"route": {"route": lambda inner: Delegate(inner, after=expire)},
                "nonce": {"broadcast": lambda inner: Delegate(inner, after=expire_after_nonce)},
                "signer": {"signer": lambda inner: Delegate(inner, after=expire)}}[delay]
    Inject(original, **wrappers)
    agent = f"expiry-{delay}-fx-original"
    ff.confirmed_agent(original, owner_a, agent, network_id=143)
    ff.adopted(original, owner_a, agent, ff.funded(original, owner_a, agent), expiry=expiry)
    job = ff.run_job(original, ff.schedule(original, owner_a, agent).json())
    body = action(original, owner_a, job["action_id"])
    outcome, stage, signs = expected
    assert (job["outcome"], original_of(body)["stage"]) == (outcome, stage), job["reason"]
    assert "MANDATE_EXPIRED" in original_of(body)["reason"]
    assert calls(recordings).get("signer.rpc", 0) == signs
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == 0


# ------------------------------------------------------- review B on dac088a: malformed logs in a split leg

def split_sell_leg(malform):
    """Split the sell-token Transfer into 60 % and 40 % logs, then malform only the 40 % log."""
    def edit(receipt):
        sell = receipt["logs"][0]
        amount = int(sell["data"], 16)
        first = {**sell, "data": word(amount * 6 // 10)}
        second = malform({**sell, "topics": list(sell["topics"]), "data": word(amount - amount * 6 // 10)})
        receipt["logs"] = [first, second, *receipt["logs"][1:]]
        return receipt
    return edit


@pytest.mark.parametrize("case,malform", [
    ("topic0-no-prefix", lambda log: {**log, "topics": [log["topics"][0][2:], *log["topics"][1:]]}),
    ("address-no-prefix", lambda log: {**log, "address": log["address"][2:]}),
    ("topic-short", lambda log: {**log, "topics": [log["topics"][0], log["topics"][1][:40], log["topics"][2]]})])
def test_a_malformed_log_anywhere_in_the_receipt_proves_no_amount(original, owner_a, case, malform):
    job = submitted(original, owner_a, f"split-{case}-fx-original")
    Inject(original, observer=receipt_edit(split_sell_leg(malform)))
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    body = action(original, owner_a, job["action_id"])
    assert settled["decision_status"] == "BREACHED" and body["admission"][0]["reason"].startswith("MISSING_RECONCILED")
    assert "RESERVED" in reservation_states(body)


def test_a_well_formed_split_leg_sums_to_the_whole_amount(original, owner_a):
    job = submitted(original, owner_a, "split-clean-fx-original")
    Inject(original, observer=receipt_edit(split_sell_leg(lambda log: log)))
    settled = original.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert settled["case_state"] == "CONFIRMED"
    receipt = action(original, owner_a, job["action_id"])["receipts"][-1]
    assert receipt["content"]["actual_input"]["raw"] == ff.ENTRY_QUOTE_INPUT


def test_a_hash_shaped_slice_of_the_signed_bytes_is_never_saved_or_shown(original, owner_a):
    signed = signed_entry_nonce0()
    fragment = "0x" + signed[10:74]  # 32 bytes of the signed serialization, shaped like a hash
    Inject(original, broadcast=lambda inner: Delegate(
        inner, after=lambda result, method, params: fragment if method == "eth_sendRawTransaction" else result))
    job = submitted(original, owner_a, "slice-fx-original")
    response = original.get(f"/v1/actions/{job['action_id']}", headers=owner_a)
    assert original_of(response.json())["stage"] == "BROADCAST_HASH_MISMATCH"
    assert fragment[2:] not in response.text


def test_an_unexpected_client_error_reaches_the_log_without_its_text(original, owner_a, caplog):
    signed = signed_entry_nonce0()

    def explode(result, method, params):
        if method == "eth_sendRawTransaction":
            raise ValueError("unexpected reply for " + params[0])
        return result

    Inject(original, broadcast=lambda inner: Delegate(inner, after=explode))
    ready(original, owner_a, "explode-fx-original")
    ff.schedule(original, owner_a, "explode-fx-original")
    with caplog.at_level("INFO"):
        original.app.state.financial.connected.run_pending(limit=50)
    assert "worker job" in caplog.text and "ValueError" in caplog.text
    assert signed[2:42] not in caplog.text


# ------------------------------------------- A3: authority changes while a stage save is in progress

@pytest.mark.parametrize("stage,change,expected", [
    ("SIGN_REQUESTED", "expiry", ("DENIED_UNSENT", "REFUSED_UNSENT", 0, "MANDATE_EXPIRED")),
    ("SIGN_REQUESTED", "stop", ("DENIED_UNSENT", "REFUSED_UNSENT", 0, "STOPPED")),
    ("SIGN_REQUESTED", "removal", ("DENIED_UNSENT", "REFUSED_UNSENT", 0, "REMOVAL_REQUESTED")),
    ("BROADCAST_REQUESTED", "expiry", ("SUBMITTED_UNKNOWN", "STOPPED_AFTER_SIGNING", 1, "MANDATE_EXPIRED")),
    ("BROADCAST_REQUESTED", "stop", ("SUBMITTED_UNKNOWN", "STOPPED_AFTER_SIGNING", 1, "STOPPED")),
    ("BROADCAST_REQUESTED", "removal", ("SUBMITTED_UNKNOWN", "STOPPED_AFTER_SIGNING", 1, "REMOVAL_REQUESTED")),
    ("BROADCAST_REQUESTED", "none", ("SUBMITTED_UNKNOWN", "BROADCAST_RETURNED", 1, None))])
def test_an_authority_change_during_a_stage_save_allows_no_next_effect(original, owner_a, recordings, stage,
                                                                      change, expected):
    connected, ports = original.app.state.financial.connected, original.app.state.financial.ports
    execution = original.app.state.financial.execution
    start = connected._clock()
    moment = {"now": start}
    connected._clock = ports.clock = lambda: moment["now"]
    agent = f"save-{stage[:4].lower()}-{change}-fx-original"
    expiry = (start + dt.timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    journal = execution._journal

    def slow_save(owner, attempt_id):
        save = journal(owner, attempt_id)

        def saved_then_changed(name, values):
            save(name, values)  # the commit completes; the change lands while the worker was waiting on it
            if name != stage:
                return
            if change == "expiry":
                moment["now"] = start + dt.timedelta(seconds=11)
            elif change == "stop":
                original.post(f"/v1/agents/{agent}/stops", headers=owner_a,
                              json={"mode": "HALT_ALL_SWAPS", "scope": "AGENT_WALLET_NETWORK"})
            elif change == "removal":
                original.post(f"/v1/agents/{agent}/removal", headers=owner_a,
                              json={"request_key": f"{agent}-removal", "reason": "owner removed the agent"})
        return saved_then_changed

    execution._journal = slow_save
    try:
        ff.confirmed_agent(original, owner_a, agent, network_id=143)
        ff.adopted(original, owner_a, agent, ff.funded(original, owner_a, agent), expiry=expiry)
        job = ff.run_job(original, ff.schedule(original, owner_a, agent).json())
    finally:
        execution._journal = journal
    body = action(original, owner_a, job["action_id"])
    outcome, final_stage, signs, reason = expected
    assert (job["outcome"], original_of(body)["stage"]) == (outcome, final_stage), job["reason"]
    if reason is not None:
        assert reason in original_of(body)["reason"]
    assert calls(recordings).get("signer.rpc", 0) == signs
    assert calls(recordings).get("broadcast.eth_sendRawTransaction", 0) == (1 if change == "none" else 0)
    states = reservation_states(body)
    assert ("RESERVED" in states) == (outcome == "SUBMITTED_UNKNOWN")  # released only when no signature exists
