"""Red/green slice: the grouped review groups the exact selected revision, wallet and limits.

It shows the rules, evidence status and material limitations, the resolved
wallet/network/route, the explicit allocation, the per-asset allowances, attempts,
gas, expiry and stop effects. It never substitutes the latest revision, never treats
the wallet balance as allocation, and stays INACTIVE.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from consent import _support as support

from edge_os_api.consent.records import ConsentDenialRow, ConsentReviewRow
from edge_os_api.consent.service import ConsentConflict, ConsentDenied, ConsentNotFound


def test_review_groups_the_exact_selected_revision_wallet_and_limits(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)

    view = consent_service.review(support.OWNER_A, support.review_request(revision))

    assert view.status == "INACTIVE"
    assert view.strategy_id == revision["strategy_id"]
    assert str(view.strategy_revision_id) == str(revision["revision_id"])
    assert view.content_sha256 == revision["content_sha256"]
    assert view.manifest_sha256 == revision["manifest_sha256"]
    assert view.wallet_id == support.WALLET_A
    assert view.network_id == support.NETWORK

    review = view.content["review"]
    expected_rule_keys = {
        "strategy_id", "schema_version", "domain", "data_inputs", "decision_interval_seconds", "market", "entry",
        "exit", "invalidation", "sizing", "action_scope", "additions", "partial_exits", "risk_limits",
        "cost_assumptions", "warmup_buckets", "semantic_manifest", "execution_permission",
    }
    assert set(review["strategy"].keys()) == expected_rule_keys
    assert review["strategy"]["strategy_id"] == revision["strategy_id"]
    assert review["strategy"]["entry"] == revision["strategy"]["entry"]
    assert review["strategy"]["sizing"] == revision["strategy"]["sizing"]
    assert review["strategy"]["decision_interval_seconds"] == revision["strategy"]["decision_interval_seconds"]
    assert review["strategy"]["semantic_manifest"] == revision["strategy"]["semantic_manifest"]
    assert review["strategy"]["execution_permission"] == {"state": "NOT_GRANTED", "mandate_ref": None}
    assert review["allocation"][0]["asset_id"] == support.QUOTE
    allowance_assets = {item["amount"]["asset_id"] for item in review["allowances"]}
    assert allowance_assets == {support.QUOTE, support.BASE}
    assert review["attempt_budget"] == 5
    assert review["gas_budget"]["asset_id"] == support.NATIVE
    assert review["expiry"] == support.EXPIRY
    assert review["stop_effects"] == ["STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"]
    assert review["evidence"]["status"] == "UNRESOLVED"
    assert review["evidence"]["historical_success_required"] is False
    assert "route_unqualified" in review["evidence"]["material_limitations"]
    assert review["route"]["qualification"] == "UNQUALIFIED"
    assert review["authority"] == "INACTIVE"
    assert review["inactive"] is True
    assert "allocation_is_not_wallet_balance" in review["notes"]
    assert "no_live_operational_gate_is_claimed" in review["notes"]


def test_wallet_balance_is_shown_separately_from_allocation(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)
    support.seed_funding_credit(consent_engine, support.OWNER_A, raw="4000")

    view = consent_service.review(support.OWNER_A, support.review_request(revision, reviewed_terms=support.terms(allocation_raw="5000")))

    review = view.content["review"]
    assert review["allocation"][0]["raw"] == "5000"
    balances = {item["asset_id"]: item for item in review["funding"]}
    assert balances[support.QUOTE]["available"]["raw"] == "4000"
    assert review["allocation"][0]["raw"] != balances[support.QUOTE]["available"]["raw"]


def test_repeated_review_is_idempotent(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)

    first = consent_service.review(support.OWNER_A, support.review_request(revision))
    second = consent_service.review(support.OWNER_A, support.review_request(revision))

    assert first.review_id == second.review_id
    assert first.review_hash == second.review_hash


def test_changed_terms_for_the_same_revision_conflict(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)

    first = consent_service.review(support.OWNER_A, support.review_request(revision))
    with pytest.raises(ConsentConflict) as error:
        consent_service.review(support.OWNER_A, support.review_request(revision, reviewed_terms=support.terms(quote_raw="900")))
    assert error.value.code == "changed_review"
    # The original reviewed meaning survives unchanged and is still adoptable.
    assert consent_service.read_review(support.OWNER_A, str(first.review_id)).review_hash == first.review_hash


def test_another_owner_cannot_review_or_read_the_revision(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)

    with pytest.raises(ConsentNotFound):
        consent_service.review(support.OWNER_B, support.review_request(revision))
    view = consent_service.review(support.OWNER_A, support.review_request(revision))
    with pytest.raises(ConsentNotFound):
        consent_service.read_review(support.OWNER_B, str(view.review_id))


def test_a_foreign_revision_is_indistinguishable_from_a_missing_one(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)
    foreign = {"strategy_id": revision["strategy_id"], "revision_id": "11111111-1111-1111-1111-111111111111"}

    with pytest.raises(ConsentNotFound):
        consent_service.review(support.OWNER_A, support.review_request(foreign))


def test_mismatched_network_wrong_network_asset_and_wallet_revision_are_denied(consent_engine, consent_service, session) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)

    with pytest.raises(ConsentDenied) as network_error:
        consent_service.review(support.OWNER_A, support.review_request(revision, network_id="monad-testnet:10143"))
    assert network_error.value.code == "network_mismatch"

    wrong_asset = support.terms()
    wrong_asset = wrong_asset.model_copy(update={
        "allocation": [wrong_asset.allocation[0].model_copy(update={"asset_id": "monad-testnet:10143/asset:USDC"})]})
    with pytest.raises(ConsentDenied) as asset_error:
        consent_service.review(support.OWNER_A, support.review_request(revision, reviewed_terms=wrong_asset))
    assert asset_error.value.code == "wrong_network_asset"

    other = support.seed_revision(consent_engine, support.OWNER_A, strategy_id="strategy-consent-2")
    # Rebind the wallet to a different revision than the requested one.
    with session:
        from edge_os_api.wallet_setup.persistence import WalletSetupRow
        row = session.execute(select(WalletSetupRow).where(WalletSetupRow.owner_id == support.OWNER_A)).scalar_one()
        row.strategy_revision_id = other["revision_id"]
        row.content_sha256 = other["content_sha256"]
        session.commit()
    with pytest.raises(ConsentDenied) as drift_error:
        consent_service.review(support.OWNER_A, support.review_request(revision))
    assert drift_error.value.code == "revision_wallet_mismatch"

    denials = set(session.execute(select(ConsentDenialRow.code)).scalars())
    assert {"NETWORK_MISMATCH", "WRONG_NETWORK_ASSET", "REVISION_WALLET_MISMATCH"} <= denials


def test_unconfirmed_wallet_is_not_reviewable(consent_engine, consent_service, session) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision, state="UNKNOWN")

    with pytest.raises(ConsentNotFound):
        consent_service.review(support.OWNER_A, support.review_request(revision))
    assert session.execute(select(ConsentReviewRow)).scalars().all() == []
    assert "WALLET_NOT_CONFIRMED" in set(session.execute(select(ConsentDenialRow.code)).scalars())


def test_review_surfaces_stops_and_unknown_pending_actions(consent_engine, consent_service) -> None:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)
    support.seed_stop(consent_engine, support.OWNER_A, mode="HALT_ALL_SWAPS")
    action_id = support.seed_allowance_and_unknown_decision(consent_engine, support.OWNER_A)

    view = consent_service.review(support.OWNER_A, support.review_request(revision))

    review = view.content["review"]
    assert any(stop["mode"] == "HALT_ALL_SWAPS" for stop in review["stops"])
    unknown = [item for item in review["existing_decisions"] if item["action_id"] == action_id]
    assert unknown and unknown[0]["status"] == "SUBMISSION_UNKNOWN"
    assert any(item["asset_id"] == support.QUOTE for item in review["existing_allowances"])
