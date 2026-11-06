"""Frozen #58 integration contracts (docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md).

Each case checks one frozen interface rule at its public function, with independently stated expectations.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import sessionmaker

import financial_flows as ff
from edge_os_api.consent.types import ReviewedTerms
from edge_os_api.core.database import make_engine
from edge_os_api.core.provider_ports import (FixtureChain, FixtureSubmissionTransport, PlannedFixtureEffect,
                                             build_provider_ports, original_references_unavailable)
from edge_os_api.execution.connected_identity import (CONNECTED_TERMS_VERSION, AdoptedConsent, derive_approval,
                                                      resolve_agent)
from edge_os_api.execution.transport import PreparedSubmission
from edge_os_api.execution.types import AssetAmount
from edge_os_api.execution.worker import decision_slot

NOW = dt.datetime(2026, 10, 12, 1, 7, 31, tzinfo=dt.timezone.utc)


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        yield client


@pytest.fixture
def factory(settings):
    engine = make_engine(settings.database_url)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def test_decision_slot_is_the_latest_five_minute_utc_grid_point():
    assert decision_slot(NOW) == dt.datetime(2026, 10, 12, 1, 5, tzinfo=dt.timezone.utc)
    assert decision_slot(dt.datetime(2026, 10, 12, 1, 10, tzinfo=dt.timezone.utc)).minute == 10


def test_ic01_publication_uuid_resolves_to_one_execution_identity(journey, owner_a, owner_b, factory):
    agent = ff.confirmed_agent(journey, owner_a, "contract-ic01")
    owner_a_id = uuid.UUID(journey.get("/v1/me", headers=owner_a).json()["user_id"])
    owner_b_id = uuid.UUID(journey.get("/v1/me", headers=owner_b).json()["user_id"])
    with factory() as session:
        resolved = resolve_agent(session, owner_a_id, "contract-ic01")
        assert resolve_agent(session, owner_b_id, "contract-ic01") is None  # another owner resolves nothing
        assert resolve_agent(session, owner_a_id, "contract-missing") is None
    assert resolved is not None
    assert str(resolved.publication_revision_id) == agent["revision_id"]
    assert resolved.revision.content_hash == "sha256:" + resolved.content_sha256
    assert resolved.revision.revision_id == f"{agent['strategy_id']}:{resolved.content_sha256[:16]}"
    assert resolved.quote.asset_id == "monad-testnet:10143/0x2222222222222222222222222222222222222222"
    assert (resolved.quote.decimals, resolved.base.decimals, resolved.gas.decimals) == (6, 18, 18)


def _consent(agent, **changes) -> AdoptedConsent:
    declaration = {"trading_asset": {"asset_id": agent.quote.asset_id, "decimals": agent.quote.decimals},
                   "gas_asset": {"asset_id": agent.gas.asset_id, "decimals": agent.gas.decimals}}
    terms = ff.connected_terms(declaration)
    terms.update(changes)
    return AdoptedConsent(adoption_id=uuid.uuid4(), review_id=uuid.uuid4(), consent_hash="sha256:" + "1" * 64,
                          review_hash="sha256:" + "2" * 64, terms=ReviewedTerms.model_validate(terms), adopted_at=NOW)


def test_ic05_only_the_server_fixture_qualification_derives_a_synthetic_approval(journey, owner_a, factory):
    ff.confirmed_agent(journey, owner_a, "contract-ic05")
    owner = uuid.UUID(journey.get("/v1/me", headers=owner_a).json()["user_id"])
    with factory() as session:
        agent = resolve_agent(session, owner, "contract-ic05")
    consent = _consent(agent)
    approval, reason = derive_approval(agent, consent, qualification="fixture", now=NOW)
    assert reason is None and approval is not None
    assert approval.fixture_label == "SYNTHETIC_FIXTURE_QUALIFICATION"
    assert approval.binding.mandate_id == str(consent.adoption_id)
    assert approval.policy_binding == consent.consent_hash
    assert approval.binding.strategy_revision == agent.revision.revision_id
    assert approval.quote_allowance.approved_raw == "500000000"
    assert derive_approval(agent, consent, qualification="unavailable", now=NOW) == (None, "ACTIVATION_UNAVAILABLE")
    assert derive_approval(agent, consent, qualification="fixture", now=dt.datetime(2031, 1, 1, tzinfo=dt.timezone.utc)
                           ) == (None, "CONSENT_EXPIRED")
    other_version = _consent(agent, terms_version="other/1")
    assert derive_approval(agent, other_version, qualification="fixture", now=NOW) == (None, "TERMS_VERSION_UNSUPPORTED")
    missing = _consent(agent, allowances=ff.connected_terms({"trading_asset": {"asset_id": agent.quote.asset_id,
                                                                             "decimals": 6},
                                                           "gas_asset": {"asset_id": agent.gas.asset_id,
                                                                         "decimals": 18}})["allowances"][:3])
    assert derive_approval(agent, missing, qualification="fixture", now=NOW) == (None, "TERMS_INCOMPLETE")
    assert CONNECTED_TERMS_VERSION == "connected-spot/1"


def test_ic03_fixture_holdings_follow_effects_not_deposit_history(factory, tmp_path):
    ports = build_provider_ports("fixture", factory, str(tmp_path / "effects.jsonl"))
    owner = uuid.uuid4()
    assets = [("monad-testnet:10143/q", 6), ("monad-testnet:10143/b", 18), ("monad-testnet:10143/native", 18)]
    empty = ports.holdings.observe(owner_id=owner, agent_id="a", wallet_id="w", network_id="monad-testnet:10143",
                                   assets=assets)
    # IC03 interface (ORIGINAL-LOCAL): the port returns one observation carrying the per-asset amounts.
    assert {asset: amount.raw for asset, amount in empty.assets.items()} == {asset: "0" for asset, _ in assets}
    ports.chain.append(action_id="act", owner_id=str(owner), wallet_id="w", network_id="monad-testnet:10143",
                       outcome="APPLIED_CONFIRMED", actual_input={"asset_id": "monad-testnet:10143/q", "raw": "0",
                                                                  "decimals": 6},
                       actual_output={"asset_id": "monad-testnet:10143/b", "raw": "7", "decimals": 18},
                       actual_gas={"asset_id": "monad-testnet:10143/native", "raw": "0", "decimals": 18})
    after = ports.holdings.observe(owner_id=owner, agent_id="a", wallet_id="w", network_id="monad-testnet:10143",
                                   assets=assets)
    assert after.assets["monad-testnet:10143/b"].raw == "7"


def test_ic06_original_references_never_invent_chain_identities(tmp_path):
    prepared = PreparedSubmission(action_id="p23:x:ENTRY", owner_id="o", wallet_id="w", network_id="n",
                                  operation="ENTRY", payload_hash="sha256:" + "0" * 64)
    references = original_references_unavailable(prepared, "fixture-connected/1")
    assert references["schema_version"] == "edge-os.original-transaction-references/1"
    for name in ("signing_request_id", "nonce", "fee_envelope", "unsigned_bytes", "signed_bytes", "transaction_hash"):
        assert references[name] is None
    assert references["absent_reason"] == "FIXTURE_TRANSPORT_SIGNS_NOTHING"


def test_ic06_fixture_lost_acknowledgement_records_the_effect_before_losing_the_reply(tmp_path):
    chain = FixtureChain(str(tmp_path / "effects.jsonl"))
    amount = AssetAmount(asset_id="a", raw="1", decimals=0)
    transport = FixtureSubmissionTransport(chain, "agent-fx-lost-ack", PlannedFixtureEffect(amount, amount, amount),
                                           "ENTRY")
    prepared = PreparedSubmission(action_id="p23:y:ENTRY", owner_id="o", wallet_id="w", network_id="n",
                                  operation="ENTRY", payload_hash="sha256:" + "0" * 64)
    with pytest.raises(Exception) as lost:
        transport.submit(prepared)
    assert type(lost.value).__name__ == "FixtureAcknowledgementLost"
    assert [effect.outcome for effect in FixtureChain(str(tmp_path / "effects.jsonl")).for_action("p23:y:ENTRY")] == [
        "APPLIED_CONFIRMED"]


def test_unapproved_controlled_release_cannot_derive_approval_before_credentials():
    from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease
    from execution.test_operating_release import definition
    from types import SimpleNamespace
    # Invalid saved identity is denied before term access or provider/credential work.
    release = OperatingRelease(definition())
    identity = {"owner_id": "owner-a", "agent_id": "agent-a", "wallet_id": "synthetic-wallet-a",
        "wallet_address": "0x" + "1" * 40, "network_id": "monad:143", "strategy_id": "strategy-a",
        "publication_revision_id": "revision-a", "execution_revision_id": "execution-a", "market_binding_id": "market-a",
        "content_sha256": "1" * 64, "manifest_sha256": "2" * 64, "consent_adoption_id": "consent-a",
        "consent_hash": "sha256:" + "3" * 64, "review_hash": "sha256:" + "4" * 64, "terms_hash": "sha256:" + "5" * 64}
    bound = BoundRelease(release, identity, position_inventory_proof_sha256="6" * 64,
                         market_proof_sha256="7" * 64, finality_proof_sha256="8" * 64)
    agent = SimpleNamespace(owner_id="foreign", agent_id="agent-a", wallet_id="synthetic-wallet-a", network_id="monad:143",
        identity=lambda: {k:v for k,v in identity.items() if k not in ("owner_id", "wallet_address", "consent_adoption_id",
                                                                  "consent_hash", "review_hash", "terms_hash")})
    consent = SimpleNamespace(adoption_id="consent-a", consent_hash="sha256:" + "3" * 64, review_hash="sha256:" + "4" * 64,
                             terms=SimpleNamespace(content_hash=lambda: "sha256:" + "5" * 64))
    result = derive_approval(agent, consent, qualification="controlled", now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc),
                             binding=bound, wallet_address="0x" + "1" * 40, synthetic_bindings={})
    assert result == (None, "EXECUTION_BINDING_MISMATCH")


def test_controlled_approval_is_explicit_and_keeps_exit_and_inventory_requirements():
    from types import SimpleNamespace
    from edge_os_api.execution.connected_identity import ConnectedAgent, AssetIdentity, saved_release_identity
    from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
    from execution.test_operating_release import definition
    source = definition()
    source["route"]["output_asset"].update(asset_id="monad:143/0x" + "1" * 40, token_address="0x" + "1" * 40)
    release = OperatingRelease(source)
    agent = ConnectedAgent(uuid.uuid4(), "agent-a", source["wallet_id"], 143, "monad:143", "strategy-a", uuid.uuid4(),
        "1" * 64, "2" * 64, SimpleNamespace(revision_id="execution-a", market_binding_id="market-a"),
        AssetIdentity(source["route"]["input_asset"]["asset_id"], 6),
        AssetIdentity(source["route"]["output_asset"]["asset_id"], 18), AssetIdentity("monad:143/native", 18))
    consent = _consent(agent, terms_version="connected-one-action/1", supported_actions=["ENTRY"],
        signer=source["signer_id"], policy={"policy_id":source["policy_id"], "status":"UNQUALIFIED",
                                          "content_sha256":source["policy_content_sha256"]},
        route={"adapter":"KURU_FLOW_FIXED_INPUT", "identity_state":"KNOWN", "identity":source["route"]["entrypoint_address"]})
    identity = saved_release_identity(agent, consent, source["wallet_address"])
    bound = BoundRelease(release, identity, position_inventory_proof_sha256="6" * 64,
        market_proof_sha256="7" * 64, finality_proof_sha256="8" * 64,
        exit_capacity_proof_sha256="9" * 64, valuation_proof_sha256="a" * 64, cost_model_proof_sha256="b" * 64)
    approvals = {bound.sha256: release_sha256(release)}
    now = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
    approval, reason = derive_approval(agent, consent, qualification="controlled", now=now, binding=bound,
        wallet_address=source["wallet_address"], synthetic_bindings=approvals)
    assert reason is None and approval is not None
    assert approval.actions == ["ENTRY"]
    assert approval.controlled.purpose == "CONTROLLED_ONE_ACTION_QUALIFICATION"
    assert approval.controlled.binding_sha256 == bound.sha256
    assert (approval.exit_capacity_qualified, approval.valuation_qualified, approval.cost_model_qualified) == (False, False, False)
    assert approval.quote_allowance.approved_raw == "200"
    assert approval.per_action_gas.approved_raw == "2000000"
    assert approval.attempt_budget == 2  # one submission plus the retained intended-exit protection


def test_controlled_admission_requires_proofs_instead_of_fixture_flags():
    from edge_os_api.admission.accounting import denial_reasons
    from edge_os_api.admission.types import ControlledApproval
    from admission._builders import approval_a, context_a, intent_entry
    approval = approval_a(exit_capacity_qualified=False, valuation_qualified=False, cost_model_qualified=False).model_copy(update={
        "actions": ["ENTRY"], "controlled": ControlledApproval(evidence_class="SYNTHETIC_FIXTURE",
            release_sha256="1" * 64, binding_sha256="2" * 64, position_inventory_proof_sha256="3" * 64,
            exit_capacity_proof_sha256="4" * 64, valuation_proof_sha256="5" * 64, cost_model_proof_sha256="6" * 64)})
    assert denial_reasons(intent_entry(), approval, context_a(), False) == []
    actual = approval.model_copy(update={"controlled": approval.controlled.model_copy(update={"evidence_class":"PROVIDER_ACTUAL"})})
    assert "CONTROLLED_RELEASE_UNAPPROVED" in denial_reasons(intent_entry(), actual, context_a(), False)


def test_activation_exposes_controlled_scope_instead_of_fixture_or_unavailable(monkeypatch):
    from types import SimpleNamespace
    from edge_os_api.consent import routes
    from edge_os_api.admission.types import ControlledApproval
    from admission._builders import approval_a
    approval = approval_a().model_copy(update={"controlled":ControlledApproval(evidence_class="SYNTHETIC_FIXTURE",
        release_sha256="1"*64, binding_sha256="2"*64, position_inventory_proof_sha256="3"*64,
        exit_capacity_proof_sha256="4"*64, valuation_proof_sha256="5"*64, cost_model_proof_sha256="6"*64)})
    monkeypatch.setattr(routes, "resolve_agent", lambda *args: SimpleNamespace())
    monkeypatch.setattr(routes, "adopted_consent", lambda *args: SimpleNamespace())
    financial = SimpleNamespace(ports=SimpleNamespace(mode="controlled"),
        connected=SimpleNamespace(approval=lambda *args, **kwargs:(approval,None)))
    result = routes.activation(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(financial=financial))),
        None, SimpleNamespace(user_id="owner-a"), "agent-a")
    assert result["state"] == "CONTROLLED_QUALIFIED"
    assert result["scope"] == "CONTROLLED_ONE_ACTION_QUALIFICATION"
    assert result["binding_sha256"] == "2"*64


def test_controlled_terms_projection_is_owner_scoped_and_contains_no_client_configuration(tmp_path):
    from types import SimpleNamespace
    from edge_os_api.consent.routes import controlled_profile
    from edge_os_api.core.provider_ports import ControlledRuntime
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    bound, approvals = bound_original(transport)
    identity = bound.identity()
    agent_keys = ("agent_id","wallet_id","network_id","strategy_id","publication_revision_id","execution_revision_id",
                  "market_binding_id","content_sha256","manifest_sha256")
    agent = SimpleNamespace(agent_id="agent-1", identity=lambda:{key:identity[key] for key in agent_keys})
    runtime = ControlledRuntime(binding=bound, http=None, synthetic_bindings=approvals)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(financial=SimpleNamespace(
        ports=SimpleNamespace(controlled={"agent-1":runtime})))))
    result = controlled_profile(request, SimpleNamespace(user_id=identity["owner_id"]), agent)
    assert result["gas"]["gas_limit"] == "300000"
    assert result["gas"]["max_fee_per_gas"] == "3000000000"
    assert result["input"]["raw"] == "100000000"
    assert result["minimum_output"]["raw"] == "49500000000000000000"
    assert result["recurring"] == "UNAVAILABLE" and result["exit_execution"] == "UNAVAILABLE"
    assert "endpoint" not in str(result) and "credential" not in str(result)
    assert controlled_profile(request, SimpleNamespace(user_id="foreign"), agent) is None
