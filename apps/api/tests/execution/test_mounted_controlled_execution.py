"""Mounted controlled clients over saved PostgreSQL state; all external replies are synthetic.

These tests use the ordinary owner routes and trusted worker. The public documentation key's
recorded signature never represents a real wallet or a live provider qualification.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import financial_flows as ff
from test_original_transaction_journey import original, recordings, original_of, run_job, reservation_states
from execution.test_privy_signer import original as pure_original, recorded_signature, ENTRY_NONCE0_HASH
from execution.test_saved_attempt_signing import bound_original
from edge_os_api.core.financial_services import build_financial_services
from edge_os_api.core.provider_ports import (ControlledRuntime, FixtureMarketObservations, MarketObservations,
                                            build_provider_ports)
from edge_os_api.execution.connected_identity import resolve_agent, adopted_consent, saved_release_identity
from edge_os_api.execution.models import SubmissionAttemptRow
from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
from edge_os_api.execution.original_transaction import wallet_address, JournalError
from edge_os_api.execution.worker import decision_slot
from edge_os_api.research.forward_observation import ForwardObservation
from edge_os_api.research_history.http_clients.http_transport import HttpResponse
from edge_os_api.research_history.provider_transport import SourceTimeout
from edge_os_api.wallet_setup.persistence import WalletSetupRow
from edge_os_api.wallet_setup.provider import WalletEvidence

BLOCK = "0x" + "ab" * 32
FINAL = "0x" + "cd" * 32


class MountedHttp:
    """Scripted HTTP boundary that independently checks durable state before signature and send."""

    def __init__(self, factory, data, clock):
        self.factory, self.data, self.clock = factory, data, clock
        self.calls, self.stages = [], []
        self.fault = None
        self.after_quote = self.after_sign = None

    def saved(self):
        with self.factory() as session:
            return session.execute(select(SubmissionAttemptRow).where(
                SubmissionAttemptRow.attempt_id == uuid.UUID(self.attempt_id))).scalar_one()

    def request(self, **request):
        body = json.loads(request["body"])
        method = body.get("method", "quote")
        self.calls.append((request["url"], method, copy.deepcopy(body)))
        if method == "quote":
            result = copy.deepcopy(self.data["routes"][0]["response"])
            result["transaction"]["value"] = "0"
            result.update(type="quote", status="success", gasPrices={k:"2000000000"
                for k in ("slow", "standard", "fast", "rapid", "extreme")})
            if self.after_quote is not None:
                self.after_quote()
            return HttpResponse(200, {}, json.dumps(result).encode())
        if method == "eth_signTransaction":
            self.attempt_id = request["headers"]["privy-idempotency-key"]
            saved = self.saved()
            assert saved.state == "IN_FLIGHT"
            assert saved.content["original_transaction"]["stage"] == "SIGN_REQUESTED"
            self.stages.append("SIGN_REQUESTED")
            if self.fault == "lost-sign":
                raise SourceTimeout("fake lost signature reply")
            signed = recorded_signature("ENTRY", 0)
            if self.fault == "malformed-sign":
                signed = "0x02zz"
            if self.after_sign is not None:
                self.after_sign()
            result = {"method":method, "data":{"signed_transaction":signed, "encoding":"rlp"}}
            return HttpResponse(200, {}, json.dumps(result).encode())
        if method == "eth_sendRawTransaction":
            saved = self.saved().content["original_transaction"]
            assert saved["stage"] == "BROADCAST_REQUESTED"
            assert saved["signed_bytes"] == body["params"][0] == recorded_signature("ENTRY", 0)
            assert saved["transaction_hash"] == ENTRY_NONCE0_HASH
            self.stages.append("BROADCAST_REQUESTED")
            if self.fault == "lost-send":
                raise SourceTimeout("fake lost send reply")
            result = ENTRY_NONCE0_HASH
        elif method == "eth_getTransactionCount":
            result = "0x0"
        elif method == "eth_chainId":
            result = "0x8f"
        elif method == "eth_getBlockByNumber":
            number = "0x1e8482" if body["params"][0] == "finalized" else body["params"][0]
            block_hash = FINAL if number == "0x1e8482" else BLOCK
            if self.fault == "bad-canonical" and number != "0x1e8482":
                block_hash = FINAL
            result = {"number":number, "hash":block_hash, "baseFeePerGas":"0x3b9aca00",
                      "timestamp":hex(int(self.clock().timestamp()) - 1)}
        elif method == "eth_getBalance":
            result = self.data["holdings"]["native"]
        elif method == "eth_call":
            call = body["params"][0]
            key = "decimals" if call["data"].startswith("0x313ce567") else "tokens"
            result = self.data["holdings"][key][call["to"].lower()]
        elif method == "eth_getTransactionReceipt":
            assert body["params"] == [ENTRY_NONCE0_HASH]
            result = copy.deepcopy(self.data["receipts"][ENTRY_NONCE0_HASH])
            result.update(blockHash=BLOCK, transactionIndex="0x0")
            result["logs"] = [{**log, "blockNumber":result["blockNumber"], "blockHash":BLOCK,
                "transactionHash":ENTRY_NONCE0_HASH, "transactionIndex":"0x0", "logIndex":hex(i), "removed":False}
                for i, log in enumerate(result["logs"])]
            if self.fault == "incomplete-effects":
                result["logs"] = result["logs"][:1]
            elif self.fault == "extra-wallet-asset":
                extra = copy.deepcopy(result["logs"][0])
                extra.update(address="0x" + "99" * 20, logIndex=hex(len(result["logs"])))
                result["logs"].append(extra)
            elif self.fault == "log-transaction-index":
                result["logs"][0]["transactionIndex"] = "0x1"
        else:
            pytest.fail(f"unexpected fake RPC method {method}")
        return HttpResponse(200, {}, json.dumps({"jsonrpc":"2.0", "id":body["id"], "result":result}).encode())

    def count(self, method):
        return sum(name == method for _, name, _ in self.calls)


class CurrentSource:
    def __init__(self, binding, clock):
        self.binding, self.clock = binding, clock
        self.qualified = True

    def observe(self, request):
        authored = FixtureMarketObservations().observe(request)
        identity, route = self.binding.identity(), self.binding.release.content()["route"]
        collected = self.clock().isoformat()
        forward = ForwardObservation(network=identity["network_id"], market_binding_id=request.market_binding_id,
            base_asset=route["output_asset"]["asset_id"], quote_asset=route["input_asset"]["asset_id"],
            units="QUOTE_PER_BASE", event="test-current-event", collected_at=collected,
            observed_at=request.decision_time.isoformat(), finality="finalized", coverage="COMPLETE",
            evidence_class="SYNTHETIC_FIXTURE", age_seconds=0, availability="AVAILABLE", reason=None)
        profile = self.binding.market_profile()
        provenance = {**authored.provenance, "collected_at":collected, "source":profile["source_id"],
            "availability_basis":"FORWARD_OBSERVED", "finality":"finalized", "binding_sha256":self.binding.sha256,
            "qualification_proof_sha256":self.binding.proofs()["market_proof_sha256"],
            "delivery_profile_sha256":profile["delivery_profile_sha256"], "warmup_buckets":request.warmup_buckets}
        if not self.qualified:
            provenance["availability_basis"] = "DELAYED_HYPOTHETICAL_REPLAY"
        return MarketObservations(authored.inputs, provenance, forward)


@pytest.fixture
def mounted(original, owner_a, tmp_path, settings):
    client, agent_id = original, f"controlled-fx-original-{uuid.uuid4().hex[:8]}"
    class TestWallet:
        def create_wallet(self, request):
            self.evidence = WalletEvidence(wallet_id="test-wallet-" + uuid.uuid4().hex,
                owner_id=request.owner_id, chain_type="ethereum",
                address="0x2c7536E3605D9C16a7a3D7b1898e529396a65c23")
            return self.evidence
        def lookup_wallet(self, wallet_id):
            assert wallet_id == self.evidence.wallet_id
            return self.evidence
    client.app.state.wallet_provider = TestWallet()
    ff.confirmed_agent(client, owner_a, agent_id, network_id=143)
    declaration = ff.funded(client, owner_a, agent_id)
    factory = client.app.state.session_factory
    original_clock = client.app.state.execution_worker.connected._clock
    offset = [dt.timedelta()]
    clock = lambda: original_clock() + offset[0]
    expiry = (decision_slot(clock()) + dt.timedelta(minutes=5)).isoformat()
    seed = tmp_path / "seed"; seed.mkdir()
    transport, data, _ = pure_original(seed, None)
    prior, _ = bound_original(transport)
    release = prior.release.content()
    release.update(valid_until=expiry)
    release["transaction"]["request_expires_at"] = expiry
    release["route"]["freshness"].update(intent_expires_at=expiry, mandate_expires_at=expiry)
    release["gas"]["budget_raw"] = "900000000000000"
    terms = ff.connected_terms(declaration, expiry=expiry)
    terms.update(terms_version="connected-one-action/1", supported_actions=["ENTRY"], signer=release["signer_id"],
        policy={"policy_id":release["policy_id"], "status":"UNQUALIFIED", "content_sha256":release["policy_content_sha256"]},
        route={"adapter":"KURU_FLOW_FIXED_INPUT", "identity_state":"KNOWN", "identity":release["route"]["entrypoint_address"]})
    review = client.post(f"/v1/agents/{agent_id}/consent/review", headers=owner_a, json={"terms":terms})
    assert review.status_code == 200, review.text
    adoption = client.post(f"/v1/agents/{agent_id}/consent/adopt", headers=owner_a,
        json={"review_id":review.json()["review_id"], "expected_review_hash":review.json()["review_hash"]})
    assert adoption.status_code == 200, adoption.text
    with factory() as session:
        setup = session.execute(select(WalletSetupRow).where(WalletSetupRow.agent_id == agent_id)).scalar_one()
        agent = resolve_agent(session, setup.owner_id, agent_id)
        consent = adopted_consent(session, agent)
        address = wallet_address(session, agent.owner_id, agent_id, agent.wallet_id)
        identity = saved_release_identity(agent, consent, address)
    release.update(wallet_id=agent.wallet_id, wallet_address=address)
    release["route"]["recipient"] = address
    binding = BoundRelease(OperatingRelease(release), identity, **prior.proofs(),
        exit_capacity_proof_sha256="a"*64, valuation_proof_sha256="b"*64, cost_model_proof_sha256="c"*64,
        market_profile={"source_id":"test-current/1", "delivery_profile_sha256":"d"*64,
            "finality":"finalized", "warmup_buckets":agent.revision.warmup_buckets, "max_collection_age_seconds":30})
    http = MountedHttp(factory, data.data, clock)
    source = CurrentSource(binding, clock)
    acquired = []
    def credentials():
        with factory() as session:
            saved = session.execute(select(SubmissionAttemptRow).where(
                SubmissionAttemptRow.agent_id == agent_id, SubmissionAttemptRow.state == "IN_FLIGHT")).scalar_one()
            assert saved.content["original_transaction"]["stage"] == "SIGN_REQUESTED"
            acquired.append(str(saved.attempt_id))
        return {"app_id":"fake_app", "app_secret":"fake_worker_secret", "authorize":lambda payload:"ZmFrZQ=="}
    runtime = ControlledRuntime(binding=binding, http=http, clock=clock, quote_token=lambda:"fake_quote_token",
        signer_access=credentials, market_source=source, synthetic_bindings={binding.sha256:release_sha256(binding.release)})
    configured = settings.model_copy(update={"execution_mode":"controlled"})
    def compose(role):
        ports = build_provider_ports("controlled", factory, role=role, controlled={agent_id:runtime})
        services = build_financial_services(factory, configured, ports, role=role)
        services.connected._clock, services.ports.clock = clock, clock
        return services
    client.app.state.financial = compose("api")
    client.app.state.execution_worker = compose("worker")
    return SimpleNamespace(client=client, headers=owner_a, agent=agent_id, http=http, source=source,
        acquired=acquired, compose=compose, factory=factory, runtime=runtime, offset=offset, terms=terms)


def submit(case):
    queued = ff.schedule(case.client, case.headers, case.agent)
    assert queued.status_code in (200, 201, 202), queued.text
    return run_job(case.client, queued.json())


def detail(case, job):
    response = case.client.get(f"/v1/actions/{job['action_id']}", headers=case.headers)
    assert response.status_code == 200, response.text
    return response.json()


def reconcile(case, job):
    response = case.client.post(f"/v1/actions/{job['action_id']}/reconcile", headers=case.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_mounted_original_and_restart_reconcile_without_credentials(mounted):
    case = mounted
    consent = case.client.get(f"/v1/agents/{case.agent}/consent", headers=case.headers).json()
    assert consent["activation"]["state"] == "CONTROLLED_QUALIFIED"
    assert consent["controlled_action"]["minimum_output"]["raw"] == "49500000000000000000"
    assert case.acquired == [] and case.http.count("quote") == 0
    job = submit(case)
    assert job["outcome"] == "SUBMITTED_UNKNOWN", job
    body = detail(case, job)
    saved = original_of(body)
    assert saved["stage"] == "BROADCAST_RETURNED"
    assert saved["signing_request_id"] == case.acquired[0] == body["attempts"][0]["attempt_id"]
    assert saved["approved_minimum"]["raw"] == "49500000000000000000"
    assert "signed_bytes" not in saved and "fake_worker_secret" not in json.dumps(body)
    assert case.http.stages == ["SIGN_REQUESTED", "BROADCAST_REQUESTED"]
    case.client.app.state.financial = case.compose("api")  # reopened services over the same durable database
    api_runtime = case.client.app.state.financial.ports.controlled[case.agent]
    assert api_runtime.signer_access is None and api_runtime.quote_token is None
    result = reconcile(case, job)
    assert (result["receipt_outcome"], result["case_state"]) == ("CONFIRMED", "CONFIRMED")
    receipt = detail(case, job)["receipts"][-1]["content"]
    assert receipt["actual_gas"]["raw"] == "600000000000000"  # gasLIMIT, not the recording's gasUsed
    assert receipt["source_ref"].endswith(":finalized:" + BLOCK)
    assert reconcile(case, job)["duplicate"] is True
    assert case.http.count("eth_signTransaction") == case.http.count("eth_sendRawTransaction") == 1


@pytest.mark.parametrize("fault", ["lost-sign", "malformed-sign", "lost-send", "bad-canonical", "incomplete-effects", "extra-wallet-asset", "log-transaction-index"])
def test_mounted_uncertainty_keeps_reservations_and_never_repeats_sign_or_send(mounted, fault):
    case = mounted; case.http.fault = fault
    job = submit(case)
    assert job["state"] == "SUBMITTED", job
    case.client.app.state.financial = case.compose("api")
    result = reconcile(case, job)
    if fault == "lost-send":
        assert result["receipt_outcome"] == "CONFIRMED"
    else:
        assert result["receipt_outcome"] == "SUBMISSION_UNKNOWN"
        assert "RESERVED" in reservation_states(detail(case, job))
    run_job(case.client, job)
    assert case.http.count("eth_signTransaction") == 1
    assert case.http.count("eth_sendRawTransaction") == (0 if fault in ("lost-sign", "malformed-sign") else 1)


def test_mounted_unqualified_current_input_never_loads_credentials(mounted):
    case = mounted; case.source.qualified = False
    job = submit(case)
    assert job["state"] == "COMPLETED", job
    assert case.acquired == [] and case.http.count("quote") == case.http.count("eth_signTransaction") == 0


@pytest.mark.parametrize("boundary", ["PREPARED", "SIGN_REQUESTED", "SIGNED", "BROADCAST_REQUESTED"])
def test_mounted_failed_journal_save_prevents_the_next_effect(mounted, monkeypatch, boundary):
    from edge_os_api.execution.service import ExecutionService
    case = mounted
    journal = ExecutionService._journal
    def fail(self, owner, attempt):
        save = journal(self, owner, attempt)
        def stage_save(stage, values):
            if stage == boundary:
                raise JournalError("fake durable save failure")
            save(stage, values)
        return stage_save
    monkeypatch.setattr(ExecutionService, "_journal", fail)
    job = submit(case)
    assert case.http.count("eth_sendRawTransaction") == 0
    if boundary in ("PREPARED", "SIGN_REQUESTED"):
        assert case.acquired == []
    else:
        assert "RESERVED" in reservation_states(detail(case, job))


@pytest.mark.parametrize("control", ["stop", "removal"])
@pytest.mark.parametrize("boundary", ["quote", "signed"])
def test_mounted_concurrent_owner_control_denies_next_effect(mounted, control, boundary):
    case = mounted
    def deny():
        if control == "stop":
            response = case.client.post(f"/v1/agents/{case.agent}/stops", headers=case.headers,
                json={"mode":"HALT_ALL_SWAPS", "scope":"AGENT_WALLET_NETWORK"})
        else:
            response = case.client.post(f"/v1/agents/{case.agent}/removal", headers=case.headers,
                json={"request_key":"test-remove", "reason":"test owner removal"})
        assert response.status_code == 200, response.text
    if boundary == "quote":
        case.http.after_quote = deny
    else:
        case.http.after_sign = deny
    job = submit(case)
    assert case.http.count("eth_sendRawTransaction") == 0
    if boundary == "quote":
        assert case.acquired == [] and case.http.count("eth_signTransaction") == 0
    else:
        assert case.http.count("eth_signTransaction") == 1
        assert "RESERVED" in reservation_states(detail(case, job))


@pytest.mark.parametrize("failure", ["expired", "unapproved", "consent-changed"])
def test_mounted_missing_authority_denies_before_credential_io(mounted, failure):
    case = mounted
    if failure == "expired":
        case.offset[0] = dt.timedelta(minutes=10)
    elif failure == "unapproved":
        case.runtime = dataclasses.replace(case.runtime, synthetic_bindings={})
        # Replace only the worker's injected registry; no actual registry is modified.
        ports = build_provider_ports("controlled", case.factory, role="worker", controlled={case.agent:case.runtime})
        worker = case.client.app.state.execution_worker
        worker.ports = worker.connected._ports = ports
    else:
        changed = {**case.terms, "trial_objective":"changed exact consent"}
        review = case.client.post(f"/v1/agents/{case.agent}/consent/review", headers=case.headers, json={"terms":changed})
        assert review.status_code == 200, review.text
        adopted = case.client.post(f"/v1/agents/{case.agent}/consent/adopt", headers=case.headers,
            json={"review_id":review.json()["review_id"], "expected_review_hash":review.json()["review_hash"]})
        assert adopted.status_code == 200, adopted.text
    job = submit(case)
    assert job["state"] == "COMPLETED", job
    assert case.acquired == [] and case.http.count("quote") == case.http.count("eth_signTransaction") == 0


def test_mounted_failed_submission_ownership_never_calls_an_execution_client(mounted, monkeypatch):
    case = mounted
    worker = case.client.app.state.execution_worker
    monkeypatch.setattr(worker.admission, "acquire_submission", lambda *args: "CANCELLED")
    job = submit(case)
    assert job["state"] == "COMPLETED", job
    assert case.acquired == []
    assert case.http.count("quote") == case.http.count("eth_signTransaction") == case.http.count("eth_sendRawTransaction") == 0
