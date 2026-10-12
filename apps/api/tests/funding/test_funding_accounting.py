"""Pure amount and asset validation. No database access."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from edge_os_api.funding.accounting import (InvalidFundingValue, canonical_raw, classify_asset, credit_identity_key,
                                            parse_asset_amount, storable_text, validate_decimals)
from edge_os_api.funding.types import AssetAmount, AssetClass, FundingProfileRecord


def _profile() -> FundingProfileRecord:
    return FundingProfileRecord(
        owner_id=uuid.uuid4(), agent_id="agent-a", wallet_id="wallet-a", network_id=143,
        trading_asset=AssetAmount(asset_id="monad:143/asset:USDC", raw="0", decimals=6),
        gas_asset=AssetAmount(asset_id="monad:143/native", raw="0", decimals=18),
        compute_asset=AssetAmount(asset_id="monad:143/compute:credits", raw="0", decimals=0),
        updated_at=dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc))


def test_canonical_raw_accepts_only_canonical_integers():
    assert canonical_raw("0") == "0"
    assert canonical_raw("1234567890") == "1234567890"
    assert canonical_raw(42) == "42"
    for bad in ("00", "01", "-1", "1.0", "1e3", "", " 5", "0x10", True, False, 1.5, None, "9" * 79):
        with pytest.raises(InvalidFundingValue):
            canonical_raw(bad)


def test_validate_decimals_rejects_boolean_float_and_range():
    assert validate_decimals(0) == 0
    assert validate_decimals(255) == 255
    for bad in (True, 1.5, -1, 256, "6", None):
        with pytest.raises(InvalidFundingValue):
            validate_decimals(bad)


def test_parse_asset_amount_validates_every_field():
    amount = parse_asset_amount("monad:143/asset:USDC", "500", 6)
    assert amount == AssetAmount(asset_id="monad:143/asset:USDC", raw="500", decimals=6)
    with pytest.raises(InvalidFundingValue):
        parse_asset_amount("", "500", 6)
    with pytest.raises(InvalidFundingValue):
        parse_asset_amount("monad:143/asset:USDC", "500", -1)


def test_storable_text_rejects_nul_and_surrogate():
    assert storable_text("monad:143/native")
    assert not storable_text("")
    assert not storable_text("bad\x00text")
    assert not storable_text("\ud800")


def test_classify_asset_separates_classes():
    profile = _profile()
    assert classify_asset(profile, "monad:143/native") is AssetClass.NATIVE_GAS
    assert classify_asset(profile, "monad:143/asset:USDC") is AssetClass.TRADING
    assert classify_asset(profile, "monad:143/compute:credits") is AssetClass.COMPUTE
    assert classify_asset(profile, "monad:143/asset:OTHER") is None


def test_credit_identity_key_is_exact():
    assert credit_identity_key("wallet-a", 143, "monad:143/asset:USDC", "0x1") == \
        ("wallet-a", 143, "monad:143/asset:USDC", "0x1")
