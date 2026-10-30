"""OWNER-TRIGGER-L3: the one owner-triggered action runs without a market observation.

Seam: owner route -> saved job -> worker -> controlled runtime with no market source -> one saved action.
Every other job keeps the observation requirement. Expected values are the authored release input and the
recorded original transaction, not the code under test.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest
from sqlalchemy import select

import financial_flows as ff
from execution.test_mounted_controlled_execution import (MountedHttp, compose_controlled, controlled_agent,
                                                         detail, reconcile, run_job, submit)
from test_original_transaction_journey import original, original_of, recordings
from execution.test_privy_signer import original as pure_original
from execution.test_saved_attempt_signing import bound_original
from edge_os_api.core.provider_ports import ControlledRuntime
from edge_os_api.execution.connected_identity import adopted_consent, resolve_agent, saved_release_identity
from edge_os_api.execution.models import SubmissionAttemptRow
from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
from edge_os_api.execution.original_transaction import wallet_address
from edge_os_api.execution.worker import decision_slot
from edge_os_api.wallet_setup.persistence import WalletSetupRow
from edge_os_api.wallet_setup.provider import WalletEvidence

RELEASE_ID = "actual-inapp-wmon-moe-20261022/1"
DECISION_HASH = "7" * 64
REASON = "NO_FORWARD_SOURCE_BUILDER_DECISION"


def owner_triggered_agent(client, headers, tmp_path, clock, monkeypatch):
    """The controlled agent of the mounted test, with no market source and the owner-trigger decision binding."""
    from edge_os_api.execution import operating_release
    monkeypatch.setattr(operating_release, "APPROVED_BINDING_DECISIONS",
                        frozenset({("market_proof_sha256", REASON, DECISION_HASH)}), raising=False)
    agent_id = f"owner-trigger-fx-{uuid.uuid4().hex[:8]}"
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
    ff.confirmed_agent(client, headers, agent_id, network_id=143)
    declaration = ff.funded(client, headers, agent_id)
    factory = client.app.state.session_factory
    expiry = (decision_slot(clock()) + dt.timedelta(minutes=5)).isoformat()
    seed = tmp_path / f"seed-{agent_id}"; seed.mkdir()
    transport, data, _ = pure_original(seed, None)
    prior, _ = bound_original(transport)
    release = prior.release.content()
    release.pop("schema")
    release.update(release_id=RELEASE_ID, valid_until=expiry)
    release["transaction"]["request_expires_at"] = expiry
    release["route"]["freshness"].update(intent_expires_at=expiry, mandate_expires_at=expiry)
    release["gas"]["budget_raw"] = "900000000000000"
    terms = ff.connected_terms(declaration, expiry=expiry)
    terms.update(terms_version="connected-one-action/1", supported_actions=["ENTRY"], signer=release["signer_id"],
        policy={"policy_id":release["policy_id"], "status":"UNQUALIFIED", "content_sha256":release["policy_content_sha256"]},
        route={"adapter":"KURU_FLOW_FIXED_INPUT", "identity_state":"KNOWN", "identity":release["route"]["entrypoint_address"]})
    review = client.post(f"/v1/agents/{agent_id}/consent/review", headers=headers, json={"terms":terms})
    assert review.status_code == 200, review.text
    adoption = client.post(f"/v1/agents/{agent_id}/consent/adopt", headers=headers,
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
    proofs = {**prior.proofs(), "market_proof_sha256": DECISION_HASH, "exit_capacity_proof_sha256":"a"*64,
              "valuation_proof_sha256":"b"*64, "cost_model_proof_sha256":"c"*64}
    binding = BoundRelease(OperatingRelease(release), identity, **proofs, market_profile=None)
    http = MountedHttp(factory, data.data, clock)
    acquired = []
    def credentials():
        with factory() as session:
            saved = session.execute(select(SubmissionAttemptRow).where(
                SubmissionAttemptRow.agent_id == agent_id, SubmissionAttemptRow.state == "IN_FLIGHT")).scalar_one()
            assert saved.content["original_transaction"]["stage"] == "SIGN_REQUESTED"
            acquired.append(str(saved.attempt_id))
        return {"app_id":"fake_app", "app_secret":"fake_worker_secret", "authorize":lambda payload:"ZmFrZQ=="}
    runtime = ControlledRuntime(binding=binding, http=http, clock=clock, quote_token=lambda:"fake_quote_token",
        signer_access=credentials, market_source=None,
        synthetic_bindings={binding.sha256: release_sha256(binding.release)})
    return type("Case", (), {"client":client, "headers":headers, "agent":agent_id, "http":http,
        "acquired":acquired, "factory":factory, "runtime":runtime, "terms":terms})()


class SpyRuntime:
    """Delegates every runtime attribute and counts market-observation calls."""

    def __init__(self, runtime):
        self._runtime = runtime
        self.observe_calls = 0

    def __getattr__(self, name):
        return getattr(self._runtime, name)

    def observe_market(self, request):
        self.observe_calls += 1
        return self._runtime.observe_market(request)


@pytest.fixture
def owner_triggered(original, owner_a, tmp_path, settings, monkeypatch):
    original_clock = original.app.state.execution_worker.connected._clock
    offset = [dt.timedelta()]
    clock = lambda: original_clock() + offset[0]
    case = owner_triggered_agent(original, owner_a, tmp_path, clock, monkeypatch)
    case.offset = offset
    case.market = SpyRuntime(case.runtime)
    case.compose = compose_controlled(original, settings, clock, {case.agent: case.market})
    return case


def test_owner_triggered_entry_completes_without_a_market_source(owner_triggered):
    case = owner_triggered
    job = submit(case)
    assert job["state"] == "SUBMITTED", job
    assert job["outcome"] == "SUBMITTED_UNKNOWN", job
    assert case.market.observe_calls == 0
    body = detail(case, job)
    assert body["decision"]["basis"] == "OWNER_TRIGGER", body["decision"]
    assert body["queue"]["state"] == "SUBMITTED_UNKNOWN"
    saved = original_of(body)
    assert saved["stage"] == "BROADCAST_RETURNED"
    result = reconcile(case, job)
    assert (result["receipt_outcome"], result["case_state"]) == ("CONFIRMED", "CONFIRMED"), result


@pytest.fixture
def other_release(original, owner_a, tmp_path, settings):
    """A normal controlled agent whose market source is absent. Its release is not the owner-triggered one."""
    original_clock = original.app.state.execution_worker.connected._clock
    offset = [dt.timedelta()]
    clock = lambda: original_clock() + offset[0]
    case = controlled_agent(original, owner_a, tmp_path, clock)
    case.offset = offset
    case.market = SpyRuntime(dataclasses.replace(case.runtime, market_source=None))
    case.compose = compose_controlled(original, settings, clock, {case.agent: case.market})
    return case


def test_another_release_and_its_market_path_still_require_the_observation(other_release):
    case = other_release
    job = submit(case)
    assert (job["state"], job["outcome"], job["reason"]) == ("UNAVAILABLE", "UNAVAILABLE", "OBSERVATIONS_UNAVAILABLE"), job
    assert job["action_id"] is None
    assert case.market.observe_calls == 1
    assert case.acquired == []


def test_a_second_trigger_under_the_same_permission_is_denied(owner_triggered):
    case = owner_triggered
    first = submit(case)
    assert first["state"] == "SUBMITTED", first
    case.offset[0] += dt.timedelta(minutes=5)
    second = submit(case)
    assert (second["state"], second["outcome"], second["reason"]) == (
        "COMPLETED", "DENIED", "OWNER_TRIGGER_ALREADY_USED"), second
    assert second["action_id"] is None
    assert case.market.observe_calls == 0
    assert len(case.acquired) == 1


def test_replaying_the_same_trigger_reuses_the_same_job(owner_triggered):
    case = owner_triggered
    scheduled = ff.schedule(case.client, case.headers, case.agent, "same-key")
    first = run_job(case.client, scheduled.json())
    assert first["state"] == "SUBMITTED", first
    again = ff.schedule(case.client, case.headers, case.agent, "same-key")
    assert again.status_code == 200 and again.json()["job_id"] == scheduled.json()["job_id"]
    rerun = run_job(case.client, again.json())
    assert rerun["job_id"] == first["job_id"]
    assert len(case.acquired) == 1


def test_an_expired_release_refuses_before_any_signature(owner_triggered):
    case = owner_triggered
    case.offset[0] += dt.timedelta(minutes=10)
    job = submit(case)
    assert job["outcome"] != "SUBMITTED_CONFIRMED", job
    assert case.acquired == []
    assert case.market.observe_calls == 0


def test_a_request_field_cannot_set_the_decision_basis(owner_triggered):
    case = owner_triggered
    response = case.client.post(f"/v1/agents/{case.agent}/actions", headers=case.headers,
        json={"request_key": "forged", "decision_basis": "OWNER_TRIGGER"})
    assert response.status_code == 422, response.text


def test_another_owner_cannot_trigger_this_agents_action(owner_triggered, owner_b):
    case = owner_triggered
    response = ff.schedule(case.client, owner_b, case.agent)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "agent_not_ready"
    assert case.acquired == []


def test_a_restart_after_enqueue_reuses_the_saved_intent(owner_triggered, monkeypatch):
    from edge_os_api.execution.worker import ConnectedExecution

    case = owner_triggered
    real = ConnectedExecution._submit
    calls = {"n": 0}

    def stop_once(self, job, agent, consent):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("fake stop after enqueue")
        return real(self, job, agent, consent)

    monkeypatch.setattr(ConnectedExecution, "_submit", stop_once)
    scheduled = ff.schedule(case.client, case.headers, case.agent, "restart")
    with pytest.raises(RuntimeError):
        run_job(case.client, scheduled.json())
    job = run_job(case.client, scheduled.json())
    assert job["state"] == "SUBMITTED", job
    assert len(case.acquired) == 1
