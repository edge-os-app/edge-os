"""Funding identities, capital-flow states and asset amounts for local funding reconciliation.

Local preparation only. This package is not production wiring and the application exposes no
funding route. It creates no transfer, provider call, signer, mandate or trading action. Every
deposit observation used in this local task is an authored fake; it is never provider or chain
evidence.

The record meanings follow the accepted P15 capital-flow contract: a funding flow binds to the
owner, agent, wallet, network, asset, raw amount, decimals, kind, state and available transaction
reference. An amount is `{asset_id, raw, decimals}` where `raw` is a canonical non-negative base-10
integer string. Amounts with different `asset_id` values are never added. Native MON gas, the
declared trading asset and compute usage stay separate.
"""

from __future__ import annotations

import datetime as dt
import enum
import re
import uuid
from dataclasses import dataclass


class NetworkId(enum.IntEnum):
    """The two accepted Monad networks. Approval for one does not approve the other."""

    MONAD_MAINNET = 143
    MONAD_TESTNET = 10143


ACCEPTED_NETWORK_IDS = frozenset(member.value for member in NetworkId)

MONAD_NETWORK_PREFIX = {NetworkId.MONAD_MAINNET.value: "monad:143",
                        NetworkId.MONAD_TESTNET.value: "monad-testnet:10143"}


class FlowKind(enum.StrEnum):
    """The capital-flow kinds. This local stage prepares deposits only."""

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class FlowState(enum.StrEnum):
    """The four accepted P15 capital-flow states. No other state is added here."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class AssetClass(enum.StrEnum):
    """The three separate funding classes. One never substitutes for another."""

    NATIVE_GAS = "NATIVE_GAS"
    TRADING = "TRADING"
    COMPUTE = "COMPUTE"


class ObservationStatus(enum.StrEnum):
    """A controlled deposit observation. `DUPLICATE` marks a replayed event identity."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    DUPLICATE = "DUPLICATE"


class FundingReason(enum.StrEnum):
    """Stable reason codes recorded on a denial, an unavailable flow or a credit refusal."""

    WALLET_NOT_CONFIRMED = "WALLET_NOT_CONFIRMED"
    NETWORK_MISMATCH = "NETWORK_MISMATCH"
    UNSUPPORTED_ASSET = "UNSUPPORTED_ASSET"
    UNSUPPORTED_KIND = "UNSUPPORTED_KIND"
    CHANGED_DECLARATION = "CHANGED_DECLARATION"
    CHANGED_FLOW_IDENTITY = "CHANGED_FLOW_IDENTITY"
    NO_MATCHING_FLOW = "NO_MATCHING_FLOW"
    WRONG_OWNER = "WRONG_OWNER"
    WRONG_WALLET = "WRONG_WALLET"
    WRONG_NETWORK = "WRONG_NETWORK"
    MALFORMED_OBSERVATION = "MALFORMED_OBSERVATION"
    CONFLICTING_TERMINAL_EVIDENCE = "CONFLICTING_TERMINAL_EVIDENCE"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    DECIMALS_MISMATCH = "DECIMALS_MISMATCH"


RAW_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\Z")
MAX_RAW_DIGITS = 78
MAX_DECIMALS = 255
MAX_IDENTIFIER = 200
MAX_ADDRESS = 200


@dataclass(frozen=True)
class AssetAmount:
    """`{asset_id, raw, decimals}`. `raw` is a canonical non-negative base-10 integer string."""

    asset_id: str
    raw: str
    decimals: int


@dataclass(frozen=True)
class FundingProfileRecord:
    """The declared supported assets for one confirmed agent wallet and network."""

    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: int
    trading_asset: AssetAmount
    gas_asset: AssetAmount
    compute_asset: AssetAmount | None
    updated_at: dt.datetime


@dataclass(frozen=True)
class FundingFlowRecord:
    """One reviewed funding flow. A reviewed transport/address is not a sent transfer."""

    flow_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: int
    kind: FlowKind
    asset: AssetAmount
    declared_fee: AssetAmount | None
    transport: str
    sender: str | None
    recipient: str | None
    state: FlowState
    reference: str
    transaction_reference: str | None
    reason: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


@dataclass(frozen=True)
class ObservationRecord:
    """One appended deposit observation. Request and actual amounts stay distinguishable."""

    observation_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: int
    asset_id: str | None
    actual: AssetAmount | None
    fee: AssetAmount | None
    event_id: str | None
    transaction_reference: str | None
    status: ObservationStatus
    flow_id: uuid.UUID | None
    reason: str | None
    observed_at: dt.datetime


@dataclass(frozen=True)
class CreditRecord:
    """One once-only credit of a reconciled actual amount."""

    credit_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: int
    asset_id: str
    amount: AssetAmount
    fee: AssetAmount | None
    event_id: str
    flow_id: uuid.UUID
    observation_id: uuid.UUID
    created_at: dt.datetime


@dataclass(frozen=True)
class FundingBalance:
    """One asset class's confirmed available amount and its unavailable pending amount."""

    asset_class: AssetClass
    asset_id: str
    available: AssetAmount
    pending: AssetAmount


@dataclass(frozen=True)
class ReconciliationResult:
    """The outcome of reconciling one flow against the controlled observation boundary."""

    flow: FundingFlowRecord
    observations: list[ObservationRecord]
    credits: list[CreditRecord]
    denials: list[str]
