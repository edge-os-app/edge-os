"""Trusted provider ports for the connected financial journey, with their fixture and unavailable adapters.

Ordinary HTTP callers never supply an observation, quote, holding, receipt or removal result. The server
reads each one through a port chosen by configuration:

- `unavailable` (production): every port raises `ProviderUnavailable`. No funded action can run, and
  the service records the missing qualification instead of a success.
- `fixture` (local and test only, refused in production): authored adapters return SYNTHETIC_FIXTURE
  evidence. They are never provider, chain or financial evidence.

Fixture fault scenarios are selected by reserved markers in the agent id, the same convention the accepted
wallet fixture uses. The fixture records every submission effect in an append-only `FixtureChain`, outside the
application database, so a restarted process reconciles the original action and a verifier can count effects
independently of HTTP or UI responses.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.execution.transport import FixtureAcknowledgementLost, PreparedSubmission, TransportOutcome
from edge_os_api.execution.types import AssetAmount, EvaluationInputs, InputObservation
from edge_os_api.funding.observation import DepositObservation, ObservationUnavailable
from edge_os_api.funding.persistence import FundingCreditRow, FundingFlowRow
from edge_os_api.funding.types import FlowState, ObservationStatus

FIXTURE_EVIDENCE = "SYNTHETIC_FIXTURE"
FIXTURE_MODE, UNAVAILABLE_MODE = "fixture", "unavailable"

# Reserved agent-id markers for authored fixture scenarios. They select fixture data only.
MARKER_NO_SIGNAL = "fx-nosignal"
MARKER_INELIGIBLE = "fx-ineligible"
MARKER_FALLING = "fx-falling"
MARKER_LOST_ACK = "fx-lost-ack"
MARKER_UNKNOWN = "fx-unknown"
MARKER_REVERT = "fx-revert"
MARKER_DENY = "fx-deny"
MARKER_DEPOSIT_PENDING = "fx-deposit-pending"
MARKER_REMOVAL_PENDING = "fx-removal-pending"

FIXTURE_PRICE_QUOTE_PER_BASE = 2  # one authored constant price; never a market fact


class ProviderUnavailable(RuntimeError):
    """The port cannot answer. The caller keeps the action unavailable, unknown or ineligible."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


# ---------------------------------------------------------------- market observations (IC02)

@dataclass(frozen=True)
class MarketObservationRequest:
    """The exact decision the observations are for. The port answers for this market binding only."""

    agent_id: str
    market_binding_id: str
    decision_time: dt.datetime
    warmup_buckets: int
    position_open: bool


@dataclass(frozen=True)
class MarketObservations:
    inputs: EvaluationInputs
    provenance: dict[str, Any]


class MarketObservationPort(Protocol):
    def observe(self, request: MarketObservationRequest) -> MarketObservations: ...


class FixtureMarketObservations:
    """Authored five-minute observations for the exact decision. Rising prices by default."""

    source_id = "fixture-market/1"

    def observe(self, request: MarketObservationRequest) -> MarketObservations:
        count = request.warmup_buckets + 1
        ends = [request.decision_time - dt.timedelta(minutes=5 * (count - 1 - index)) for index in range(count)]
        agent = request.agent_id
        if MARKER_NO_SIGNAL in agent:
            prices: list[str | None] = ["2.00"] * count
        elif MARKER_INELIGIBLE in agent:
            prices = [None] * count
        elif MARKER_FALLING in agent or request.position_open:
            prices = [f"{2.40 - 0.04 * index:.2f}" for index in range(count)]
        else:
            prices = [f"{2.00 + 0.04 * index:.2f}" for index in range(count)]

        def row(value: str | None, end: dt.datetime) -> InputObservation | None:
            return None if value is None else InputObservation(value=value, bucket_end=iso(end), qualified=True)

        inputs = EvaluationInputs(
            decision_time=iso(request.decision_time), position=count - 1, position_open=request.position_open,
            scheduled_bucket_ends=[iso(end) for end in ends],
            prices=[row(value, end) for value, end in zip(prices, ends)],
            quote_volumes=[row(None if value is None else "1000", end) for value, end in zip(prices, ends)])
        provenance = {"source": self.source_id, "evidence_class": FIXTURE_EVIDENCE,
                      "market_binding_id": request.market_binding_id, "availability_basis": "AUTHORED",
                      "finality": "AUTHORED", "collected_at": iso(request.decision_time)}
        return MarketObservations(inputs=inputs, provenance=provenance)


# --------------------------------------------------------------------------- action quotes

@dataclass(frozen=True)
class QuoteRequest:
    operation: str
    quote_asset_id: str
    quote_decimals: int
    base_asset_id: str
    base_decimals: int
    quote_input_raw: str | None
    base_input_raw: str | None
    observed_at: dt.datetime


@dataclass(frozen=True)
class QuoteResult:
    """An exact output estimate for one reviewed input. `source_ref` is provenance, never authority."""

    output: AssetAmount
    observed_at: dt.datetime
    expires_at: dt.datetime
    source_ref: str


class ActionQuotePort(Protocol):
    def quote(self, request: QuoteRequest) -> QuoteResult: ...


class FixtureQuotes:
    source_id = "fixture-quote/1"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        if request.operation == "ENTRY":
            assert request.quote_input_raw is not None
            raw = (int(request.quote_input_raw) * 10 ** request.base_decimals
                   // (FIXTURE_PRICE_QUOTE_PER_BASE * 10 ** request.quote_decimals))
            output = AssetAmount(asset_id=request.base_asset_id, raw=str(raw), decimals=request.base_decimals)
        else:
            assert request.base_input_raw is not None
            raw = (int(request.base_input_raw) * FIXTURE_PRICE_QUOTE_PER_BASE * 10 ** request.quote_decimals
                   // 10 ** request.base_decimals)
            output = AssetAmount(asset_id=request.quote_asset_id, raw=str(raw), decimals=request.quote_decimals)
        return QuoteResult(output=output, observed_at=request.observed_at,
                           expires_at=request.observed_at + dt.timedelta(minutes=5),
                           source_ref=f"{self.source_id}:{FIXTURE_EVIDENCE}")


# --------------------------------------------------------- submission effects and receipts (IC06/IC07)

@dataclass(frozen=True)
class ChainEffect:
    """One authored fixture effect for one exact original action. Unknown amounts stay None."""

    sequence: int
    action_id: str
    owner_id: str
    wallet_id: str
    network_id: str
    outcome: str  # APPLIED_CONFIRMED, APPLIED_REVERTED or REFUSED_UNSENT
    actual_input: dict[str, Any] | None
    actual_output: dict[str, Any] | None
    actual_gas: dict[str, Any] | None
    recorded_at: str
    evidence_class: str = FIXTURE_EVIDENCE


class FixtureChain:
    """Append-only authored effect record. One line per submit call that reached the fixture boundary."""

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path) if path else None
        self._memory: list[ChainEffect] = []
        self._lock = threading.Lock()

    def effects(self) -> list[ChainEffect]:
        with self._lock:
            if self._path is None:
                return list(self._memory)
            if not self._path.exists():
                return []
            return [ChainEffect(**json.loads(line)) for line in self._path.read_text().splitlines() if line]

    def append(self, **values: Any) -> ChainEffect:
        with self._lock:
            existing = self._memory if self._path is None else (
                [ChainEffect(**json.loads(line)) for line in self._path.read_text().splitlines() if line]
                if self._path.exists() else [])
            effect = ChainEffect(sequence=len(existing) + 1, recorded_at=iso(utc_now()), **values)
            if self._path is None:
                self._memory.append(effect)
            else:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a") as handle:
                    handle.write(json.dumps(asdict(effect), sort_keys=True) + "\n")
            return effect

    def for_action(self, action_id: str) -> list[ChainEffect]:
        return [effect for effect in self.effects() if effect.action_id == action_id]


@dataclass(frozen=True)
class PlannedFixtureEffect:
    """The authored effect the fixture applies for one action. It is fixture input, never a live actual."""

    actual_input: AssetAmount
    actual_output: AssetAmount
    actual_gas: AssetAmount


def _amount_dict(amount: AssetAmount | None) -> dict[str, Any] | None:
    return None if amount is None else amount.model_dump(mode="json")


def _amount(value: dict[str, Any] | None) -> AssetAmount | None:
    return None if value is None else AssetAmount.model_validate(value)


def original_references_unavailable(prepared: PreparedSubmission, transport_id: str) -> dict[str, Any]:
    """IC06 original-transaction references. The fixture signs nothing, so every chain identity is absent.

    Absent identities are recorded as explicit nulls with the reason, never invented. A qualified live port
    must fill `signing_request_id`, `nonce`, `fee_envelope`, `unsigned_bytes`, `signed_bytes`,
    `transaction_hash` and `provider_reference` before its effect boundary.
    """
    return {"schema_version": "edge-os.original-transaction-references/1", "transport_id": transport_id,
            "evidence_class": FIXTURE_EVIDENCE, "signing_request_id": None, "nonce": None, "fee_envelope": None,
            "unsigned_bytes": None, "signed_bytes": None, "transaction_hash": None,
            "provider_reference": f"fixture:{prepared.action_id}",
            "absent_reason": "FIXTURE_TRANSPORT_SIGNS_NOTHING"}


class FixtureSubmissionTransport:
    """The connected fixture transport for one action. It records the effect, then answers per the scenario."""

    transport_id = "fixture-connected/1"

    def __init__(self, chain: FixtureChain, agent_id: str, plan: PlannedFixtureEffect, operation: str) -> None:
        self._chain, self._agent, self._plan, self._operation = chain, agent_id, plan, operation

    def original_references(self, prepared: PreparedSubmission) -> dict[str, Any]:
        return original_references_unavailable(prepared, self.transport_id)

    def submit(self, prepared: PreparedSubmission) -> TransportOutcome:
        identity = {"action_id": prepared.action_id, "owner_id": prepared.owner_id,
                    "wallet_id": prepared.wallet_id, "network_id": prepared.network_id}
        if MARKER_DENY in self._agent:
            self._chain.append(outcome="REFUSED_UNSENT", actual_input=None, actual_output=None, actual_gas=None,
                               **identity)
            return TransportOutcome(outcome="DEFINITELY_UNSENT", detail="fixture refused before any send")
        if MARKER_REVERT in self._agent:
            self._chain.append(outcome="APPLIED_REVERTED", actual_input=None, actual_output=None,
                               actual_gas=_amount_dict(self._plan.actual_gas), **identity)
            return TransportOutcome(outcome="REVERTED", detail="fixture reverted", actual_gas=self._plan.actual_gas)
        self._chain.append(outcome="APPLIED_CONFIRMED", actual_input=_amount_dict(self._plan.actual_input),
                           actual_output=_amount_dict(self._plan.actual_output),
                           actual_gas=_amount_dict(self._plan.actual_gas), **identity)
        if MARKER_LOST_ACK in self._agent:
            raise FixtureAcknowledgementLost(prepared.action_id)
        if MARKER_UNKNOWN in self._agent:
            return TransportOutcome(outcome="SUBMISSION_POSSIBLE", detail="fixture outcome unknown to the caller")
        return TransportOutcome(outcome="CONFIRMED", detail="fixture confirmed", actual_input=self._plan.actual_input,
                                actual_output=self._plan.actual_output, actual_gas=self._plan.actual_gas)


@dataclass(frozen=True)
class ReceiptObservation:
    """An independently observed outcome for one original action. Missing actuals stay None."""

    outcome: str  # CONFIRMED, REVERTED, PREBROADCAST_DENIED or SUBMISSION_UNKNOWN
    actual_input: AssetAmount | None
    actual_output: AssetAmount | None
    actual_gas: AssetAmount | None
    observed_at: dt.datetime
    source_ref: str


class ReceiptPort(Protocol):
    def observe(self, *, action_id: str, wallet_id: str, network_id: str) -> ReceiptObservation: ...


class FixtureReceipts:
    """Reads the fixture chain for the exact action, wallet and network. Absence stays SUBMISSION_UNKNOWN."""

    source_id = "fixture-receipt/1"

    def __init__(self, chain: FixtureChain) -> None:
        self._chain = chain

    def observe(self, *, action_id: str, wallet_id: str, network_id: str) -> ReceiptObservation:
        effects = [effect for effect in self._chain.for_action(action_id)
                   if effect.wallet_id == wallet_id and effect.network_id == network_id]
        now = utc_now()
        if len(effects) != 1:
            # No record, or two records for one action: neither proves an outcome.
            return ReceiptObservation("SUBMISSION_UNKNOWN", None, None, None, now,
                                      f"{self.source_id}:effects={len(effects)}")
        effect = effects[0]
        outcome = {"APPLIED_CONFIRMED": "CONFIRMED", "APPLIED_REVERTED": "REVERTED",
                   "REFUSED_UNSENT": "PREBROADCAST_DENIED"}[effect.outcome]
        return ReceiptObservation(outcome, _amount(effect.actual_input), _amount(effect.actual_output),
                                  _amount(effect.actual_gas), now, f"{self.source_id}:seq={effect.sequence}")


# -------------------------------------------------------------------------- holdings (IC03)

class HoldingsPort(Protocol):
    def observe(self, *, owner_id: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                assets: list[tuple[str, int]]) -> dict[str, AssetAmount]: ...


class FixtureHoldings:
    """Current fixture holdings: confirmed deposit credits plus the authored fixture effects.

    This is the fixture's own account of the wallet, independent of admission reservations. It is never a
    chain balance. A live port must read actual wallet holdings instead of deposit history.
    """

    source_id = "fixture-holdings/1"

    def __init__(self, factory: sessionmaker[Session], chain: FixtureChain) -> None:
        self._factory, self._chain = factory, chain

    def observe(self, *, owner_id: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                assets: list[tuple[str, int]]) -> dict[str, AssetAmount]:
        totals = {asset_id: 0 for asset_id, _ in assets}
        with self._factory() as session:
            for row in session.execute(select(FundingCreditRow).where(
                    FundingCreditRow.owner_id == owner_id, FundingCreditRow.agent_id == agent_id,
                    FundingCreditRow.wallet_id == wallet_id)).scalars():
                if row.asset_id in totals:
                    totals[row.asset_id] += int(row.actual_raw)
        for effect in self._chain.effects():
            if effect.owner_id != str(owner_id) or effect.wallet_id != wallet_id or effect.network_id != network_id:
                continue
            spent = [effect.actual_gas]
            if effect.outcome == "APPLIED_CONFIRMED":
                spent.append(effect.actual_input)
                if effect.actual_output and effect.actual_output["asset_id"] in totals:
                    totals[effect.actual_output["asset_id"]] += int(effect.actual_output["raw"])
            for amount in spent:
                if amount and amount["asset_id"] in totals:
                    totals[amount["asset_id"]] -= int(amount["raw"])
        return {asset_id: AssetAmount(asset_id=asset_id, raw=str(max(totals[asset_id], 0)), decimals=decimals)
                for asset_id, decimals in assets}


# --------------------------------------------------------------------- deposits and removal

class FixtureDepositObserver:
    """Observes each reviewed PENDING flow of the exact wallet as an authored CONFIRMED deposit."""

    source_id = "fixture-deposits/1"

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def observe(self, wallet_id: str, network_id: int) -> list[DepositObservation]:
        with self._factory() as session:
            flows = session.execute(select(FundingFlowRow).where(
                FundingFlowRow.wallet_id == wallet_id, FundingFlowRow.network_id == network_id,
                FundingFlowRow.state == FlowState.PENDING.value)).scalars().all()
        observed = []
        for flow in flows:
            pending = MARKER_DEPOSIT_PENDING in flow.agent_id
            observed.append(DepositObservation(
                wallet_id=wallet_id, network_id=network_id, reference=flow.reference,
                status=ObservationStatus.PENDING if pending else ObservationStatus.CONFIRMED,
                asset_id=flow.asset_id, raw=None if pending else str(int(flow.declared_raw)),
                decimals=None if pending else int(flow.decimals),
                event_id=None if pending else f"fixture-deposit:{flow.flow_id}", sender=flow.sender,
                recipient=flow.recipient, fee_asset_id=None, fee_raw=None, fee_decimals=None,
                observed_at=utc_now()))
        return observed


class UnavailableDepositObserver:
    def observe(self, wallet_id: str, network_id: int) -> list[DepositObservation]:
        raise ObservationUnavailable()


@dataclass(frozen=True)
class RemovalStatus:
    observed_state: str
    signer_identity: str | None
    source_ref: str


class RemovalObservationPort(Protocol):
    def observe(self, *, agent_id: str, wallet_id: str, network_id: str) -> RemovalStatus: ...


class FixtureRemovalObserver:
    source_id = "fixture-removal/1"

    def observe(self, *, agent_id: str, wallet_id: str, network_id: str) -> RemovalStatus:
        if MARKER_REMOVAL_PENDING in agent_id:
            return RemovalStatus("PENDING", None, f"{self.source_id}:{FIXTURE_EVIDENCE}")
        return RemovalStatus("CONFIRMED", f"fixture-signer:{wallet_id}", f"{self.source_id}:{FIXTURE_EVIDENCE}")


# ------------------------------------------------------------------------------ the bundle

class _Unavailable:
    """A fail-closed port. Its refusal names the port, so a saved reason reads e.g. HOLDINGS_UNAVAILABLE."""

    def __init__(self, port: str) -> None:
        self._port = port

    def __getattr__(self, name: str) -> Any:
        def refuse(*_: Any, **__: Any) -> Any:
            raise ProviderUnavailable(self._port)
        return refuse


@dataclass
class ProviderPorts:
    """Every trusted port the connected journey reads. `mode` is reported to the browser."""

    mode: str
    market: Any
    quotes: Any
    holdings: Any
    receipts: Any
    deposits: Any
    removals: Any
    chain: FixtureChain | None = None
    labels: dict[str, str] = field(default_factory=dict)

    def transport(self, *, agent_id: str, plan: PlannedFixtureEffect, operation: str) -> Any:
        if self.chain is None:
            raise ProviderUnavailable("transport")
        return FixtureSubmissionTransport(self.chain, agent_id, plan, operation)

    def describe(self) -> dict[str, Any]:
        return {"mode": self.mode, "evidence_class": FIXTURE_EVIDENCE if self.mode == FIXTURE_MODE else None,
                "fixture_effects": len(self.chain.effects()) if self.chain is not None else None}


def build_provider_ports(mode: str, factory: sessionmaker[Session], effects_path: str | None = None) -> ProviderPorts:
    if mode == FIXTURE_MODE:
        chain = FixtureChain(effects_path)
        return ProviderPorts(mode=FIXTURE_MODE, market=FixtureMarketObservations(), quotes=FixtureQuotes(),
                             holdings=FixtureHoldings(factory, chain), receipts=FixtureReceipts(chain),
                             deposits=FixtureDepositObserver(factory), removals=FixtureRemovalObserver(),
                             chain=chain)
    return ProviderPorts(mode=UNAVAILABLE_MODE, market=_Unavailable("observations"), quotes=_Unavailable("quote"),
                         holdings=_Unavailable("holdings"), receipts=_Unavailable("receipt"),
                         deposits=UnavailableDepositObserver(), removals=_Unavailable("removal"))
