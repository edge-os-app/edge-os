"""Red/green slice 1: typed validation of amounts, bindings and intents.

Expected values are authored literals, not recomputed by the code under test.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from edge_os_api.admission.types import (
    ActionIntent,
    ApprovalSnapshot,
    AssetAmount,
    IdentityBinding,
)

from admission._builders import intent_entry


def test_asset_amount_rejects_leading_zero() -> None:
    with pytest.raises(ValidationError):
        AssetAmount(asset_id="monad:143/asset:MOE", raw="0300", decimals=0)


def test_asset_amount_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        AssetAmount(asset_id="monad:143/asset:MOE", raw="-1", decimals=0)


def test_asset_amount_rejects_boolean_as_number() -> None:
    with pytest.raises(ValidationError):
        AssetAmount(asset_id="monad:143/asset:MOE", raw=True, decimals=0)  # type: ignore[arg-type]


def test_asset_amount_rejects_floating_point() -> None:
    with pytest.raises(ValidationError):
        AssetAmount(asset_id="monad:143/asset:MOE", raw="1.5", decimals=0)


def test_asset_amount_rejects_negative_decimals() -> None:
    with pytest.raises(ValidationError):
        AssetAmount(asset_id="monad:143/asset:MOE", raw="1", decimals=-1)


def test_asset_amount_accepts_zero_and_positive() -> None:
    zero = AssetAmount(asset_id="monad:143/asset:MOE", raw="0", decimals=0)
    nine = AssetAmount(asset_id="monad:143/asset:MOE", raw="9", decimals=0)
    assert zero.raw == "0"
    assert nine.as_int() == 9


def test_identity_binding_rejects_unknown_network() -> None:
    with pytest.raises(ValidationError):
        IdentityBinding(agent_id="agent-a", wallet_id="wallet-a", network_id="ethereum:1",
                        strategy_revision="s", mandate_id="m")


def test_intent_rejects_caller_supplied_owner() -> None:
    data = intent_entry().model_dump()
    data["owner_id"] = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValidationError):
        ActionIntent.model_validate(data)


def test_intent_requires_canonical_review_hash() -> None:
    with pytest.raises(ValidationError):
        intent_entry(review_hash="sha256:short")


def test_intent_requires_quote_input_for_entry() -> None:
    with pytest.raises(ValidationError):
        intent_entry(quote_input_raw=None)


def test_intent_requires_position_id() -> None:
    data = intent_entry().model_dump()
    del data["position_id"]
    with pytest.raises(ValidationError):
        ActionIntent.model_validate(data)


def test_intent_quote_must_use_declared_quote_asset() -> None:
    data = intent_entry().model_dump()
    data["input"]["quote_input"] = {"asset_id": "monad:143/asset:OTHER", "raw": "110", "decimals": 0}
    with pytest.raises(ValidationError):
        ActionIntent.model_validate(data)


def test_intent_operation_is_typed() -> None:
    intent = intent_entry()
    assert intent.operation in {"ENTRY", "ADDITION", "EXIT"}


def test_approval_snapshot_must_be_labelled_authority() -> None:
    with pytest.raises(ValidationError):
        ApprovalSnapshot(
            approval_id="a", binding=intent_entry().binding,
            state="ACTIVE", policy_binding="p", expires_at="2030-01-01T00:00:00Z",
            actions=["ENTRY"], quote_allowance=None, base_allowance=None, gas=None,
            per_action_gas=None, fixture_label="",
        )


def test_approval_snapshot_rejects_unsupported_authority_state() -> None:
    with pytest.raises(ValidationError):
        ApprovalSnapshot(
            approval_id="a", binding=intent_entry().binding,
            state="RUNNING", policy_binding="p", expires_at="2030-01-01T00:00:00Z",
            actions=["ENTRY"], quote_allowance=None, base_allowance=None, gas=None,
            per_action_gas=None, fixture_label="SYNTHETIC_AUTHORED",
        )