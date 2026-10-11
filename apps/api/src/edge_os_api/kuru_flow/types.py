"""Strict shared types for the isolated offline Kuru Flow adapter.

This package is a local, offline preparation stage. It accepts a supplied
quote/build response and an explicit approved configuration and returns a
validated immutable unsigned transaction candidate, or a specific blocked or
unknown result. It never loads a secret, constructs a live client, signs,
broadcasts or spends.

The adapter computes no Ethereum hash. Ethereum Keccak-256 (function selectors,
transaction hashes) is not available in this environment and is not substituted
with SHA3-256. The approved selector is supplied as a source-backed constant and
checked by equality. The candidate identity uses the application's canonical
SHA-256, which is a local application identity, not an Ethereum hash.
"""

from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NETWORK_MAINNET = "monad:143"
NETWORK_TESTNET = "monad-testnet:10143"
SUPPORTED_NETWORKS: tuple[str, ...] = (NETWORK_MAINNET, NETWORK_TESTNET)
CHAIN_ID_BY_NETWORK: dict[str, int] = {NETWORK_MAINNET: 143, NETWORK_TESTNET: 10143}

NATIVE_TOKEN_ADDRESS = "0x0000000000000000000000000000000000000000"
ZERO_ADDRESS = NATIVE_TOKEN_ADDRESS

METHOD_EXECUTE_SWAP = "EXECUTE_SWAP"
METHOD_EXECUTE_SWAP_WITH_RECEIVER = "EXECUTE_SWAP_WITH_RECEIVER"
SUPPORTED_METHODS: tuple[str, ...] = (METHOD_EXECUTE_SWAP, METHOD_EXECUTE_SWAP_WITH_RECEIVER)

MAX_FEE_BPS = 10_000
MAX_RAW_DIGITS = 78

_CANONICAL_RAW = re.compile(r"(?:0|[1-9][0-9]*)")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_SELECTOR = re.compile(r"0x[0-9a-fA-F]{8}")
_HEX_BYTES = re.compile(r"0x(?:[0-9a-fA-F]{2})+")


class AdapterError(Exception):
    """A structural or loader failure that is not an action verdict.

    A malformed declaration raises this error and is never coerced into an
    accepted or blocked verdict.
    """


class ResponseProvenance(str, enum.Enum):
    """The provenance label of one supplied provider response.

    ``AUTHORED`` is synthetic and written for this package. ``DOCUMENTATION``
    is derived from a published example. ``RECORDED`` is an actual captured
    provider response and must carry capture metadata; this package invents no
    recorded response.
    """

    AUTHORED = "AUTHORED"
    DOCUMENTATION = "DOCUMENTATION"
    RECORDED = "RECORDED"


class QuoteSchemaVariant(str, enum.Enum):
    """The two documented, currently conflicting quote response shapes.

    ``TRANSACTION_CALLDATA`` is the K2 Monad-guide shape with
    ``transaction.calldata``. ``BUILD_RESPONSE`` is the K3 Kuru OpenAPI shape
    with ``path`` and ``buildResponse``. The conflict is retained.
    """

    TRANSACTION_CALLDATA = "TRANSACTION_CALLDATA"
    BUILD_RESPONSE = "BUILD_RESPONSE"


class PreparationOutcome(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ObservationState(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    REVERTED = "REVERTED"
    PENDING = "PENDING"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    ACKNOWLEDGEMENT_LOST = "ACKNOWLEDGEMENT_LOST"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"


class FlowMethod(str, enum.Enum):
    EXECUTE_SWAP = METHOD_EXECUTE_SWAP
    EXECUTE_SWAP_WITH_RECEIVER = METHOD_EXECUTE_SWAP_WITH_RECEIVER


R_ENTRYPOINT_NOT_ALLOWED = "ENTRYPOINT_NOT_ALLOWED"
R_SELECTOR_NOT_ALLOWED = "SELECTOR_NOT_ALLOWED"
R_METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
R_ASSET_NOT_ALLOWED = "ASSET_NOT_ALLOWED"
R_INPUT_NOT_APPROVED = "INPUT_NOT_APPROVED"
R_MIN_OUTPUT_INVALID = "MIN_OUTPUT_INVALID"
R_QUOTE_UNKNOWN = "QUOTE_UNKNOWN"
R_RECIPIENT_NOT_ALLOWED = "RECIPIENT_NOT_ALLOWED"
R_VALUE_NOT_APPROVED = "VALUE_NOT_APPROVED"
R_NATIVE_VALUE_INSUFFICIENT = "NATIVE_VALUE_INSUFFICIENT"
R_ERC20_VALUE_NOT_ZERO = "ERC20_VALUE_NOT_ZERO"
R_ALLOWANCE_UNKNOWN = "ALLOWANCE_UNKNOWN"
R_ALLOWANCE_NOT_APPROVED = "ALLOWANCE_NOT_APPROVED"
R_PROGRAM_MISSING = "PROGRAM_MISSING"
R_PROGRAM_NOT_APPROVED = "PROGRAM_NOT_APPROVED"
R_FEE_NOT_APPROVED = "FEE_NOT_APPROVED"
R_FEE_BOUND_EXCEEDED = "FEE_BOUND_EXCEEDED"
R_FEE_COLLECTOR_NOT_ALLOWED = "FEE_COLLECTOR_NOT_ALLOWED"
R_REFERRER_NOT_ALLOWED = "REFERRER_NOT_ALLOWED"
R_FEE_MODE_MISMATCH = "FEE_MODE_MISMATCH"
R_FRESHNESS_UNKNOWN = "FRESHNESS_UNKNOWN"
R_STALE_QUOTE = "STALE_QUOTE"
R_INPUT_FRESHNESS_UNKNOWN = "INPUT_FRESHNESS_UNKNOWN"
R_STALE_INPUT = "STALE_INPUT"
R_EXPIRY_UNKNOWN = "EXPIRY_UNKNOWN"
R_INTENT_EXPIRED = "INTENT_EXPIRED"
R_MANDATE_EXPIRED = "MANDATE_EXPIRED"
R_SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"
R_SCHEMA_AMBIGUOUS = "SCHEMA_AMBIGUOUS"
R_QUOTE_STATUS_ERROR = "QUOTE_STATUS_ERROR"
R_CALLDATA_MISSING = "CALLDATA_MISSING"
R_CALLDATA_NOT_HEX = "CALLDATA_NOT_HEX"
R_TRUNCATED_ABI = "TRUNCATED_ABI"
R_INCONSISTENT_ABI = "INCONSISTENT_ABI"
R_NON_CANONICAL_WORD = "NON_CANONICAL_WORD"
R_NON_CANONICAL_PADDING = "NON_CANONICAL_PADDING"
R_CONFLICTING_SUMMARY = "CONFLICTING_SUMMARY"
R_METHOD_LAYOUT_UNKNOWN = "METHOD_LAYOUT_UNKNOWN"
R_PROVENANCE_INVALID = "PROVENANCE_INVALID"


def canonical_raw(value: str) -> bool:
    return _CANONICAL_RAW.fullmatch(value) is not None


def is_address(value: str) -> bool:
    return _ADDRESS.fullmatch(value) is not None


def is_selector(value: str) -> bool:
    return _SELECTOR.fullmatch(value) is not None


def is_nonempty_hex(value: str) -> bool:
    return _HEX_BYTES.fullmatch(value) is not None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def dedupe(items: list[str]) -> list[str]:
    """Return the items in order with duplicates removed."""
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _require_optional_nonneg_int(value: int | None, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdapterError(f"{field} must be an integer")
    if value < 0:
        raise AdapterError(f"{field} must not be negative")
    return value


class AdapterAsset(StrictModel):
    """One approved asset: identity, on-chain token address and display precision."""

    asset_id: str = Field(min_length=1, max_length=200)
    token_address: str = Field(min_length=42, max_length=42)
    decimals: int = Field(ge=0, le=255)

    @field_validator("asset_id")
    @classmethod
    def asset_id_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("asset_id must not be empty or whitespace")
        return value

    @field_validator("token_address")
    @classmethod
    def address_is_canonical(cls, value: str) -> str:
        if not is_address(value):
            raise ValueError("token_address must be a 0x-prefixed 20-byte hex address")
        return value

    def is_native(self) -> bool:
        return self.token_address.lower() == ZERO_ADDRESS


class ApprovedFeeCollection(StrictModel):
    fee_bps: int
    referrer_fee_bps: int
    fee_collector_address: str
    referrer_address: str
    is_in_token_fee: bool

    @field_validator("fee_bps", "referrer_fee_bps")
    @classmethod
    def fees_are_bounded(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("fee values must be integers")
        if value < 0 or value > MAX_FEE_BPS:
            raise ValueError(f"fee must be between 0 and {MAX_FEE_BPS}")
        return value

    @field_validator("fee_collector_address", "referrer_address")
    @classmethod
    def addresses_are_canonical(cls, value: str) -> str:
        if not is_address(value):
            raise ValueError("fee addresses must be 0x-prefixed 20-byte hex addresses")
        return value

    @model_validator(mode="after")
    def fee_bound_holds(self) -> "ApprovedFeeCollection":
        if self.fee_bps + self.referrer_fee_bps > MAX_FEE_BPS:
            raise ValueError("fee_bps + referrer_fee_bps must not exceed 10000")
        return self


class ApprovedFreshness(StrictModel):
    max_quote_age_seconds: int | None = None
    max_input_age_seconds: int | None = None
    intent_expires_at: str | None = None
    mandate_expires_at: str | None = None

    @model_validator(mode="after")
    def bounds_are_nonneg(self) -> "ApprovedFreshness":
        for name in ("max_quote_age_seconds", "max_input_age_seconds"):
            _require_optional_nonneg_int(getattr(self, name), name)
        return self


class ApprovedAdapterConfiguration(StrictModel):
    """The explicit approved configuration a candidate must exactly match.

    Every field is an adopted value, not a derived or guessed value. Unknown
    consequential values are ``None`` and keep the affected check unknown.
    """

    network_id: str = Field(min_length=1, max_length=40)
    entrypoint_address: str = Field(min_length=42, max_length=42)
    method: str = Field(min_length=1, max_length=40)
    selector: str = Field(min_length=10, max_length=10)
    input_asset: AdapterAsset
    output_asset: AdapterAsset
    recipient: str
    approved_input_raw: str
    approved_min_output_raw: str
    approved_program_hex: str
    fees: ApprovedFeeCollection
    approved_allowance_raw: str | None = None
    freshness: ApprovedFreshness = Field(default_factory=ApprovedFreshness)
    supported_schema_variants: list[str] = Field(min_length=1)

    @field_validator("network_id")
    @classmethod
    def network_is_supported(cls, value: str) -> str:
        if value not in SUPPORTED_NETWORKS:
            raise ValueError(f"network_id must name Monad 143 or testnet 10143, got {value!r}")
        return value

    @field_validator("entrypoint_address")
    @classmethod
    def entrypoint_is_address(cls, value: str) -> str:
        if not is_address(value):
            raise ValueError("entrypoint_address must be a 0x-prefixed 20-byte hex address")
        return value

    @field_validator("selector")
    @classmethod
    def selector_is_canonical(cls, value: str) -> str:
        if not is_selector(value):
            raise ValueError("selector must be a 0x-prefixed 4-byte hex value")
        return value

    @field_validator("method")
    @classmethod
    def method_is_supported(cls, value: str) -> str:
        if value not in SUPPORTED_METHODS:
            raise ValueError(f"method must be one of {SUPPORTED_METHODS}, got {value!r}")
        return value

    @field_validator("recipient")
    @classmethod
    def recipient_is_address(cls, value: str) -> str:
        if not is_address(value):
            raise ValueError("recipient must be a 0x-prefixed 20-byte hex address")
        return value

    @field_validator("approved_input_raw", "approved_min_output_raw")
    @classmethod
    def approved_amounts_are_canonical(cls, value: str) -> str:
        if not canonical_raw(value):
            raise ValueError("approved amounts must be canonical non-negative base-10 strings")
        if len(value) > MAX_RAW_DIGITS:
            raise ValueError(f"approved amount exceeds the {MAX_RAW_DIGITS}-digit storage bound")
        return value

    @field_validator("approved_program_hex")
    @classmethod
    def program_is_nonempty_hex(cls, value: str) -> str:
        if not is_nonempty_hex(value):
            raise ValueError("approved_program_hex must be non-empty even-length hex")
        return value

    @field_validator("approved_allowance_raw")
    @classmethod
    def allowance_is_optional_canonical(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not canonical_raw(value):
            raise ValueError("approved_allowance_raw must be canonical non-negative base-10 or null")
        return value

    @field_validator("supported_schema_variants")
    @classmethod
    def variants_are_known(cls, values: list[str]) -> list[str]:
        known = tuple(variant.value for variant in QuoteSchemaVariant)
        for value in values:
            if value not in known:
                raise ValueError(f"unsupported schema variant {value!r}; known {known}")
        if len(set(values)) != len(values):
            raise ValueError("supported_schema_variants must be unique")
        return values

    @property
    def chain_id(self) -> int:
        return CHAIN_ID_BY_NETWORK[self.network_id]

    def input_is_native(self) -> bool:
        return self.input_asset.is_native()


class DecodedFlowIntent(FrozenModel):
    """The decoded ``SwapIntent`` fields, in pinned-source field order."""

    token_user_buys: str
    min_amount_user_buys: str
    token_user_sells: str
    amount_user_sells: str

    @field_validator("token_user_buys", "token_user_sells")
    @classmethod
    def tokens_are_addresses(cls, value: str) -> str:
        if not is_address(value):
            raise ValueError("intent token addresses must be canonical")
        return value

    @field_validator("min_amount_user_buys", "amount_user_sells")
    @classmethod
    def amounts_are_canonical(cls, value: str) -> str:
        if not canonical_raw(value):
            raise ValueError("intent amounts must be canonical non-negative base-10 strings")
        return value


class DecodedFeeCollection(FrozenModel):
    fee_collector_address: str
    fee_bps: int
    referrer_address: str
    referrer_fee_bps: int
    is_in_token_fee: bool

    def fee_total(self) -> int:
        return self.fee_bps + self.referrer_fee_bps


class DecodedFlowCall(StrictModel):
    """One bounded decode of the exact Flow entrypoint calldata."""

    selector: str
    method: str
    intent: DecodedFlowIntent
    fees: DecodedFeeCollection
    program_hex: str
    receiver: str | None = None


class UnsignedTransactionCandidate(FrozenModel):
    """A validated immutable unsigned transaction candidate.

    ``candidate_hash`` is the application canonical SHA-256 identity of the
    normalized candidate. It is not an Ethereum transaction hash.
    """

    candidate_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    chain_id: int
    to: str
    value_raw: str
    data_hex: str
    selector: str
    method: str
    intent: DecodedFlowIntent
    fees: DecodedFeeCollection
    program_hex: str
    receiver: str | None
    response_provenance: ResponseProvenance
    schema_variant: QuoteSchemaVariant


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def candidate_identity(payload: Any) -> str:
    """Application canonical identity. Never an Ethereum Keccak hash."""
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def parse_utc(value: str) -> dt.datetime:
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AdapterError("timestamps must be RFC 3339 UTC") from error
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise AdapterError("timestamps must carry an explicit UTC offset")
    return moment.astimezone(dt.timezone.utc)
