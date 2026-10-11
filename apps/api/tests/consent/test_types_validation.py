"""Red/green slice: strict typed validation of the reviewed terms and requests.

Expected values are authored literals. The tests prove that a missing or unknown
limit stays distinct from an explicit zero and that the request boundary rejects an
owner, malformed identifiers, coercion and non-UTC times.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from consent import _support as support

from edge_os_api.consent.types import (AdoptionRequest, AllowanceTerm, AssetAmount, ReviewedRoute, ReviewedTerms,
                                       ReviewRequest)


def test_asset_amount_rejects_leading_zero_negative_boolean_and_float() -> None:
    for raw in ("0300", "-1", "1.5"):
        with pytest.raises(ValidationError):
            AssetAmount(asset_id=support.QUOTE, raw=raw, decimals=0)
    with pytest.raises(ValidationError):
        AssetAmount(asset_id=support.QUOTE, raw=True, decimals=0)  # type: ignore[arg-type]


def test_asset_amount_rejects_negative_decimals_and_over_long_raw() -> None:
    with pytest.raises(ValidationError):
        AssetAmount(asset_id=support.QUOTE, raw="1", decimals=-1)
    with pytest.raises(ValidationError):
        AssetAmount(asset_id=support.QUOTE, raw="1" * 79, decimals=0)


def test_asset_amount_accepts_explicit_zero() -> None:
    assert AssetAmount(asset_id=support.QUOTE, raw="0", decimals=0).as_int() == 0


def test_missing_required_limit_is_rejected_but_zero_is_a_value() -> None:
    with pytest.raises(ValidationError):
        support.terms(attempt_budget=None)  # type: ignore[arg-type]
    zero = support.terms(attempt_budget=0)
    assert zero.attempt_budget == 0


def test_attempt_budget_rejects_boolean_negative_and_non_integer() -> None:
    for value in (True, -1, "2"):
        with pytest.raises(ValidationError):
            support.terms(attempt_budget=value)  # type: ignore[arg-type]


def test_expiry_must_be_utc_and_required() -> None:
    with pytest.raises(ValidationError):
        support.terms(expiry="2030-01-01T00:00:00")  # no offset
    ok = support.terms(expiry="2030-01-01T00:00:00Z")
    assert ok.expiry.endswith("Z")


def test_gas_budget_stays_separate_from_allocated_capital() -> None:
    with pytest.raises(ValidationError):
        ReviewedTerms(
            terms_version="v", operating_purpose="ONGOING", allocation=[AssetAmount(asset_id=support.NATIVE, raw="1", decimals=0)],
            allowances=[AllowanceTerm(name="A", amount=AssetAmount(asset_id=support.QUOTE, raw="1", decimals=0))],
            attempt_budget=1, gas_budget=AssetAmount(asset_id=support.NATIVE, raw="1", decimals=0), expiry=support.EXPIRY,
            supported_actions=["ENTRY"], supported_assets=[support.QUOTE], supported_routes=["r"],
            route=ReviewedRoute(adapter="KADR"), evidence=support.terms().evidence, stop_effects=["x"])


def test_allocation_and_allowances_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms().model_dump(), "allocation": []})
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms().model_dump(), "allowances": []})


def test_route_qualification_cannot_claim_qualified() -> None:
    with pytest.raises(ValidationError):
        ReviewedRoute(adapter="KADR", qualification="QUALIFIED")  # type: ignore[arg-type]


def test_route_known_identity_requires_a_value() -> None:
    with pytest.raises(ValidationError):
        ReviewedRoute(adapter="KADR", identity_state="KNOWN")


def test_trial_objective_rules() -> None:
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms(purpose="TRIAL").model_dump(), "trial_objective": None})
    assert support.terms(purpose="TRIAL").trial_objective is not None
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms(purpose="ONGOING").model_dump(), "trial_objective": "learn"})


def test_unsupported_approved_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        support.terms(supported_actions=("ENTRY", "SHORT"))


def test_review_request_rejects_a_caller_supplied_owner_and_blank_agent() -> None:
    revision = {"strategy_id": "s", "revision_id": "00000000-0000-0000-0000-000000000001"}
    payload = {"agent_id": support.AGENT_A, "strategy_id": "s", "strategy_revision_id": revision["revision_id"],
               "network_id": support.NETWORK, "terms": support.terms().model_dump()}
    with pytest.raises(ValidationError):
        ReviewRequest.model_validate({**payload, "owner_id": "00000000-0000-0000-0000-000000000009"})
    with pytest.raises(ValidationError):
        ReviewRequest.model_validate({**payload, "agent_id": ""})


def test_adoption_request_requires_a_canonical_review_hash() -> None:
    with pytest.raises(ValidationError):
        AdoptionRequest(review_id="00000000-0000-0000-0000-000000000001", expected_review_hash="sha256:short")
    ok = AdoptionRequest(review_id="00000000-0000-0000-0000-000000000001", expected_review_hash="sha256:" + "a" * 64)
    assert ok.expected_review_hash.startswith("sha256:")


def test_blank_non_asset_identifiers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewedRoute(adapter="   ")
    with pytest.raises(ValidationError):
        AllowanceTerm(name=" ", amount=AssetAmount(asset_id=support.QUOTE, raw="1", decimals=0))
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms().model_dump(), "supported_routes": ["  "]})
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms().model_dump(), "stop_effects": ["  "]})
    with pytest.raises(ValidationError):
        ReviewedTerms.model_validate({**support.terms().model_dump(), "signer": "  "})


def test_unlike_assets_are_never_combined() -> None:
    reviewed = support.terms()
    asset_ids = {amount.asset_id for amount in reviewed.allocation} | {term.amount.asset_id for term in reviewed.allowances}
    assert len(asset_ids) >= 2
    assert all(not hasattr(term.amount, "total") for term in reviewed.allowances)
