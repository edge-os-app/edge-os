"""Pure funding validation and amount arithmetic. No database access.

Runtime field validation for caller and observation values. A dataclass annotation does not
validate a value, so every public funding boundary calls these functions before persisting. A
malformed value becomes a typed denial, never a stored `0` or a `500`.
"""

from __future__ import annotations

from edge_os_api.funding.types import (MAX_ADDRESS, MAX_DECIMALS, MAX_IDENTIFIER, MAX_RAW_DIGITS, RAW_PATTERN,
                                       AssetAmount, AssetClass, FundingProfileRecord)


class InvalidFundingValue(ValueError):
    """A caller or observation value is not a valid funding field."""


def storable_text(value: object) -> bool:
    """A non-empty string PostgreSQL can store. A NUL or unpaired surrogate breaks a UTF-8 write."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def validate_identifier(value: object, *, field: str, max_length: int = MAX_IDENTIFIER) -> str:
    if not storable_text(value) or len(value) > max_length:  # type: ignore[arg-type]
        raise InvalidFundingValue(f"{field} must be 1 to {max_length} storable characters")
    return value  # type: ignore[return-value]


def validate_address(value: object, *, field: str) -> str:
    return validate_identifier(value, field=field, max_length=MAX_ADDRESS)


def canonical_raw(value: object) -> str:
    """Return the canonical non-negative base-10 integer string, or raise.

    Rejects bool, float, negative, leading-zero and over-long values. `raw` records the exact
    base-unit quantity; a boolean or a float is not an amount.
    """
    if isinstance(value, bool):
        raise InvalidFundingValue("raw must be a canonical integer string, not a boolean")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise InvalidFundingValue("raw must be a canonical non-negative integer string")
    if not RAW_PATTERN.fullmatch(text):
        raise InvalidFundingValue("raw must be a canonical non-negative base-10 integer string")
    if len(text) > MAX_RAW_DIGITS:
        raise InvalidFundingValue(f"raw must be at most {MAX_RAW_DIGITS} digits")
    return text


def validate_decimals(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidFundingValue("decimals must be an integer")
    if value < 0 or value > MAX_DECIMALS:
        raise InvalidFundingValue(f"decimals must be between 0 and {MAX_DECIMALS}")
    return value


def parse_asset_amount(asset_id: object, raw: object, decimals: object) -> AssetAmount:
    """Validate and return one `{asset_id, raw, decimals}` amount, or raise."""
    clean_asset = validate_identifier(asset_id, field="asset_id")
    return AssetAmount(asset_id=clean_asset, raw=canonical_raw(raw), decimals=validate_decimals(decimals))


def classify_asset(profile: FundingProfileRecord, asset_id: str) -> AssetClass | None:
    """Return the declared class for an asset id, or `None` when it is unsupported."""
    if asset_id == profile.gas_asset.asset_id:
        return AssetClass.NATIVE_GAS
    if asset_id == profile.trading_asset.asset_id:
        return AssetClass.TRADING
    if profile.compute_asset is not None and asset_id == profile.compute_asset.asset_id:
        return AssetClass.COMPUTE
    return None


def declared_amount(profile: FundingProfileRecord, asset_id: str) -> AssetAmount | None:
    """The declared amount identity (asset id and decimals) for a supported asset, if any."""
    for amount in (profile.gas_asset, profile.trading_asset, profile.compute_asset):
        if amount is not None and amount.asset_id == asset_id:
            return amount
    return None


def credit_identity_key(wallet_id: str, network_id: int, asset_id: str, event_id: str) -> tuple[str, int, str, str]:
    """The once-only credit identity: exact wallet, network, asset and transaction-event identity."""
    return wallet_id, network_id, asset_id, event_id
