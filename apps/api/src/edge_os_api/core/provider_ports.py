"""Trusted provider ports for the connected financial journey, with their fixture and unavailable adapters.

Ordinary HTTP callers never supply an observation, quote, holding, receipt or removal result. The server
reads each one through a port chosen by configuration:

- `unavailable` (production): every port raises `ProviderUnavailable`. No funded action can run, and
  the service records the missing qualification instead of a success.
- `fixture` (local and test only, refused in production): authored adapters return SYNTHETIC_FIXTURE
  evidence. They are never provider, chain or financial evidence.
- `controlled` (local and test only): only an exact registered release can supply bounded clients.
  The actual registry is empty; selecting this mode grants no authority.

Fixture fault scenarios are selected by reserved markers in the agent id, the same convention the accepted
wallet fixture uses. The fixture records every submission effect in an append-only `FixtureChain`, outside the
application database, so a restarted process reconciles the original action and a verifier can count effects
independently of HTTP or UI responses.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from types import MappingProxyType
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.execution.current_holdings import HoldingsObservation, HoldingsUnavailable, read_rpc_holdings
from edge_os_api.execution.original_recordings import OriginalRecordings, RecordedObservationRpc
from edge_os_api.execution.original_transaction import (EVIDENCE_CLASS, OriginalClients, RouteProfile,
                                                        OriginalContext, RpcError, TradeSteps, validate_signed,
                                                        wallet_address)
from edge_os_api.execution.operating_release import BoundRelease, ReleaseRefused
from edge_os_api.execution.transport import FixtureAcknowledgementLost, PreparedSubmission, TransportOutcome
from edge_os_api.execution.types import AssetAmount, EvaluationInputs, InputObservation
from edge_os_api.funding.observation import DepositObservation, ObservationUnavailable
from edge_os_api.funding.persistence import FundingCreditRow, FundingFlowRow
from edge_os_api.funding.types import FlowState, ObservationStatus
from edge_os_api.research.forward_observation import ForwardObservation

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
# Selects the recorded original-transaction path (only with local `original_recordings_dir`).
MARKER_ORIGINAL = "fx-original"

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
    forward: ForwardObservation | None = None


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
    # The saved owner, agent and consent the quote is for. A controlled quote answers only from their own binding.
    owner_id: str | None = None
    agent_id: str | None = None
    consent_adoption_id: str | None = None


@dataclass(frozen=True)
class QuoteResult:
    """An exact output estimate for one reviewed input. `source_ref` is provenance, never authority."""

    output: AssetAmount
    observed_at: dt.datetime
    expires_at: dt.datetime
    source_ref: str
    basis: str = "ESTIMATE"


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
                assets: list[tuple[str, int]]) -> HoldingsObservation: ...


class FixtureHoldings:
    """Current fixture holdings: confirmed deposit credits plus the authored fixture effects.

    This is the fixture's own account of the wallet, independent of admission reservations. It is never a
    chain balance. A live port must read actual wallet holdings instead of deposit history.
    """

    source_id = "fixture-holdings/1"

    def __init__(self, factory: sessionmaker[Session], chain: FixtureChain) -> None:
        self._factory, self._chain = factory, chain

    def observe(self, *, owner_id: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                assets: list[tuple[str, int]]) -> HoldingsObservation:
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
        # The authored account is computed at the caller's read; it carries no supplied observation time.
        return HoldingsObservation(
            assets={asset_id: AssetAmount(asset_id=asset_id, raw=str(max(totals[asset_id], 0)), decimals=decimals)
                    for asset_id, decimals in assets},
            observed_at=None, source=self.source_id, evidence_class=FIXTURE_EVIDENCE, finality="AUTHORED")


class RecordedOriginalHoldings:
    """Holdings for `fx-original` agents, read through the recorded observation RPC at the bound wallet address."""

    source_id = "recorded-holdings/1"

    def __init__(self, factory: sessionmaker[Session], recordings: OriginalRecordings, fallback: Any,
                 clock: Callable[[], dt.datetime]) -> None:
        self._factory, self._recordings, self._fallback, self._clock = factory, recordings, fallback, clock

    def observe(self, *, owner_id: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                assets: list[tuple[str, int]]) -> HoldingsObservation:
        if MARKER_ORIGINAL not in agent_id:
            return self._fallback.observe(owner_id=owner_id, agent_id=agent_id, wallet_id=wallet_id,
                                          network_id=network_id, assets=assets)
        with self._factory() as session:
            address = wallet_address(session, owner_id, agent_id, wallet_id)
        if address is None:
            raise ProviderUnavailable("holdings")
        try:
            return read_rpc_holdings(RecordedObservationRpc(self._recordings, self._clock), wallet_address=address,
                                     assets=assets, source=self.source_id, evidence_class=EVIDENCE_CLASS)
        except HoldingsUnavailable:
            raise ProviderUnavailable("holdings") from None


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

@dataclass(frozen=True)
class ControlledRuntime:
    """Server-owned release and injected transports. Construction reads no credential and makes no request."""

    binding: BoundRelease
    http: Any = field(repr=False)
    quote_token: Callable[[], str] | None = field(default=None, repr=False)
    signer_access: Callable[[], Mapping[str, Any]] | None = field(default=None, repr=False)
    clock: Callable[[], dt.datetime] = utc_now
    monotonic: Callable[[], float] = time.monotonic
    synthetic_bindings: Mapping[str, str] | None = field(default=None, repr=False)
    market_source: MarketObservationPort | None = field(default=None, repr=False)
    steps: TradeSteps | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.synthetic_bindings is not None:
            object.__setattr__(self, "synthetic_bindings", MappingProxyType(dict(self.synthetic_bindings)))

    def read_only(self) -> "ControlledRuntime":
        return replace(self, quote_token=None, signer_access=None)

    def observe_market(self, request: MarketObservationRequest) -> MarketObservations:
        profile, identity = self.binding.market_profile(), self.binding.identity()
        if (profile is None or self.market_source is None or request.agent_id != identity["agent_id"]
                or request.market_binding_id != identity["market_binding_id"]
                or request.warmup_buckets != profile["warmup_buckets"]):
            raise ProviderUnavailable("current_observations")
        result = None
        try:
            self.binding.admit(identity, now=self.clock(), synthetic_bindings=self.synthetic_bindings)
            observed = self.market_source.observe(request)
            now = self.clock()  # collection age is checked after the source returns
            f, p = observed.forward, observed.provenance
            route = self.binding.release.content()["route"]
            evidence = self.binding.release.content()["evidence_class"]
            collected = dt.datetime.fromisoformat(f.collected_at.replace("Z", "+00:00"))
            count = request.warmup_buckets + 1
            ends = [request.decision_time - dt.timedelta(minutes=5 * (count - 1 - i)) for i in range(count)]
            good = (isinstance(f, ForwardObservation) and f.availability == "AVAILABLE" and f.reason is None
                and f.network == identity["network_id"] and f.market_binding_id == identity["market_binding_id"]
                and f.base_asset == route["output_asset"]["asset_id"] and f.quote_asset == route["input_asset"]["asset_id"]
                and f.units == "QUOTE_PER_BASE" and type(f.event) is str and bool(f.event)
                and f.observed_at == request.decision_time.isoformat() and f.finality == profile["finality"]
                and f.coverage == "COMPLETE" and f.evidence_class == evidence
                and type(f.age_seconds) is int and 0 <= f.age_seconds <= profile["max_collection_age_seconds"]
                and request.decision_time <= collected <= now
                and (now - collected).total_seconds() <= profile["max_collection_age_seconds"]
                and p.get("evidence_class") == evidence and p.get("binding_sha256") == self.binding.sha256
                and p.get("source") == profile["source_id"] and p.get("finality") == profile["finality"]
                and p.get("qualification_proof_sha256") == self.binding.proofs()["market_proof_sha256"]
                and p.get("delivery_profile_sha256") == profile["delivery_profile_sha256"]
                and p.get("availability_basis") == "FORWARD_OBSERVED" and p.get("warmup_buckets") == request.warmup_buckets
                and p.get("collected_at") == f.collected_at and p.get("market_binding_id") == request.market_binding_id
                and observed.inputs.observed_at() == request.decision_time and observed.inputs.position == count - 1
                and observed.inputs.position_open == request.position_open
                and observed.inputs.scheduled_bucket_ends == [iso(end) for end in ends]
                and all(len(rows) == count and all(row is not None and row.qualified and row.bucket_end == iso(end)
                    for row, end in zip(rows, ends)) for rows in (observed.inputs.prices, observed.inputs.quote_volumes)))
            if good:
                saved = {key: p[key] for key in ("source", "evidence_class", "market_binding_id", "collected_at",
                    "availability_basis", "finality", "binding_sha256", "qualification_proof_sha256",
                    "delivery_profile_sha256", "warmup_buckets")}
                result = MarketObservations(observed.inputs, {**saved, "forward_observation": asdict(f)}, f)
        except Exception:
            pass
        if result is None:
            raise ProviderUnavailable("current_observations")
        return result

    def profile(self) -> RouteProfile:
        release = self.binding.release.content()
        route, gas, freshness = release["route"], release["gas"], release["route"]["freshness"]
        return RouteProfile(chain_id=143, entrypoint=route["entrypoint_address"], method=route["method"],
            selector=route["selector"], program_hex=route["approved_program_hex"],
            fee_bps=route["fees"]["fee_bps"], referrer_fee_bps=route["fees"]["referrer_fee_bps"],
            fee_collector=route["fees"]["fee_collector_address"], referrer=route["fees"]["referrer_address"],
            is_in_token_fee=route["fees"]["is_in_token_fee"], min_output_bps=10000,
            max_quote_age_seconds=freshness["max_quote_age_seconds"], max_input_age_seconds=freshness["max_input_age_seconds"],
            gas_limit=gas["gas_limit"], max_fee_per_gas=gas["max_fee_per_gas"],
            max_priority_fee_per_gas=gas["max_priority_fee_per_gas"])

    def observer(self) -> Any:
        """One finite read-only plan per recovery or holdings reading, with a shared absolute deadline."""
        from edge_os_api.execution.transaction_rpc_client import TransactionRpcClient

        release = self.binding.release.content()
        destination, limits = release["observer"], release["limits"]
        deadline = self.monotonic() + limits["deadline_seconds"]
        runtime = self.read_only()

        class Observer:
            count = 0

            def call(self, method: str, params: list[Any]) -> Any:
                if self.count >= limits["observer_requests"]:
                    raise RpcError("OBSERVER_LIMIT_REACHED")
                self.count += 1
                client = None
                try:
                    client = TransactionRpcClient(role="observer", destination_id=destination["destination_id"],
                        endpoint=destination["endpoint"], plan=[(method, params)], http=runtime.http,
                        deadline_monotonic=deadline, connect_timeout_seconds=limits["deadline_seconds"],
                        max_request_bytes=limits["max_request_bytes"], max_response_bytes=limits["max_response_bytes"],
                        monotonic=runtime.monotonic)
                except ValueError:
                    pass
                if client is None:
                    raise RpcError("OBSERVER_CALL_REFUSED")
                return client.call(method, params)

        return Observer()

    def clients(self, factory: sessionmaker[Session], context: OriginalContext,
                controls: Callable[[], list[str]], *, role: str,
                steps: TradeSteps | None = None) -> OriginalClients:
        """Mount the accepted clients; load credentials only after the saved ownership checks.

        With a release step plan every client reads the record of the step that is signing or broadcasting now.
        The plan must match the bound release's own steps, start asset and swap gas before any client exists.
        """
        direct_source = self.binding.release.content()["quote"].get("source") == "DIRECT_V2_PROGRAM"
        if role != "worker" or self.signer_access is None or (self.quote_token is None and not direct_source):
            raise ProviderUnavailable("transport")
        identity = {**context.identity, "owner_id": context.owner_id, "agent_id": context.agent_id,
                    "wallet_id": context.wallet_id, "wallet_address": context.wallet_address, "network_id": context.network_id}
        identity = {key: identity.get(key) for key in self.binding.identity()}
        try:
            self.binding.admit(identity, now=self.clock(), synthetic_bindings=self.synthetic_bindings)
        except ReleaseRefused:
            raise ProviderUnavailable("release") from None
        from edge_os_api.execution.kuru_quote_client import KuruQuoteClient
        from edge_os_api.execution.privy_signer import PrivySignerClient
        from edge_os_api.execution.transaction_rpc_client import TransactionRpcClient
        from edge_os_api.execution.models import ClaimRow, IntentRow, SubmissionAttemptRow
        from edge_os_api.admission.models import DecisionRow as AdmissionDecisionRow
        from edge_os_api.admission.types import parse_utc

        release = self.binding.release.content()
        limits = release["limits"]
        plan = self.steps if steps is None else steps
        if plan is not None:
            from edge_os_api.execution.operating_release import release_steps

            if (release_steps(self.binding.release) != plan.order
                    or plan.input_asset_id != release["route"]["input_asset"]["asset_id"]
                    or plan.gas_limits["swap"] != release["gas"]["gas_limit"]):
                raise ProviderUnavailable("release")
        deadline = self.monotonic() + limits["deadline_seconds"]
        stopped = lambda: bool(controls())
        holder: dict[str, Any] = {}

        def step_of(prepared: PreparedSubmission | None) -> str | None:
            """The step a prefixed signer request names; the swap keeps the plain attempt id."""
            if plan is None or prepared is None or not prepared.attempt_id:
                return None
            suffix = prepared.attempt_id.rsplit(":", 1)[-1]
            return suffix if suffix in ("approve", "revoke") else "swap"

        def saved(stage: str | None, prepared: PreparedSubmission | None = None) -> dict[str, Any]:
            original = None
            try:
                with factory() as session:
                    attempt = session.execute(select(SubmissionAttemptRow).where(
                        SubmissionAttemptRow.owner_id == uuid.UUID(context.owner_id),
                        SubmissionAttemptRow.attempt_id == uuid.UUID(holder["attempt_id"]))).scalar_one_or_none()
                    if (attempt is None or attempt.state != "IN_FLIGHT" or attempt.transport_id != "original-transaction/1"
                            or (str(attempt.owner_id), str(attempt.attempt_id), attempt.agent_id, attempt.action_id,
                                attempt.wallet_id, attempt.network_id, attempt.payload_hash) != (
                                context.owner_id, holder["attempt_id"], context.agent_id, context.action_id,
                                context.wallet_id, context.network_id, context.payload_hash)):
                        raise ValueError("attempt mismatch")
                    claim = session.execute(select(ClaimRow).where(
                        ClaimRow.owner_id == attempt.owner_id, ClaimRow.queue_id == attempt.queue_id,
                        ClaimRow.action_id == context.action_id, ClaimRow.agent_id == context.agent_id,
                        ClaimRow.wallet_id == context.wallet_id, ClaimRow.network_id == context.network_id,
                        ClaimRow.state == "ACTIVE", ClaimRow.released_at.is_(None))).scalar_one_or_none()
                    admission = session.execute(select(AdmissionDecisionRow).where(
                        AdmissionDecisionRow.owner_id == attempt.owner_id, AdmissionDecisionRow.action_id == context.action_id,
                        AdmissionDecisionRow.agent_id == context.agent_id, AdmissionDecisionRow.wallet_id == context.wallet_id,
                        AdmissionDecisionRow.network_id == context.network_id)).scalar_one_or_none()
                    value = attempt.content.get("original_transaction") or {}
                    step = step_of(prepared)
                    record = value if step in (None, "swap") else (value.get(step) or {})
                    if (claim is None or claim.state != "ACTIVE" or admission is None
                            or admission.status != "SUBMISSION_UNKNOWN"):
                        raise ValueError("ownership mismatch")
                    if step in ("approve", "revoke"):
                        request = record.get("signing_request") or {}
                        if (record.get("stage") != stage
                                or request.get("request_id") != prepared.attempt_id):
                            raise ValueError("step ownership mismatch")
                    elif stage is not None and value.get("stage") != stage:
                        raise ValueError("ownership mismatch")
                    if stage is not None:
                        self.binding.qualify_original(value, synthetic_bindings=self.synthetic_bindings)
                        if value.get("attempt_id") != holder["attempt_id"]:
                            raise ValueError("saved identity mismatch")
                    original = dict(value)
            except Exception:
                pass
            if original is None:
                raise RpcError("SAVED_ATTEMPT_UNAVAILABLE")
            return original

        def begin(prepared: PreparedSubmission) -> None:
            if holder:
                raise RpcError("ATTEMPT_ALREADY_USED")
            holder["attempt_id"] = prepared.attempt_id
            saved(None)
            available = False
            try:
                with factory() as session:
                    prior = session.execute(select(SubmissionAttemptRow.attempt_id).join(IntentRow,
                        (IntentRow.owner_id == SubmissionAttemptRow.owner_id)
                        & (IntentRow.action_id == SubmissionAttemptRow.action_id)).where(
                            SubmissionAttemptRow.owner_id == uuid.UUID(context.owner_id),
                            SubmissionAttemptRow.agent_id == context.agent_id,
                            SubmissionAttemptRow.wallet_id == context.wallet_id,
                            SubmissionAttemptRow.network_id == context.network_id,
                            IntentRow.mandate_id == identity["consent_adoption_id"],
                            SubmissionAttemptRow.attempt_id != uuid.UUID(prepared.attempt_id)).limit(1)
                    ).scalar_one_or_none()
                    available = prior is None
            except Exception:
                pass
            if not available:
                raise RpcError("RELEASE_ATTEMPT_ALREADY_USED")

        runtime = self

        class AttemptRoute:
            def quote(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
                saved(None)
                if "quote" not in holder:
                    runtime.binding.admit(identity, now=runtime.clock(), synthetic_bindings=runtime.synthetic_bindings)
                    accepted = {"chain_id":143, "sell_token":context.sell.token, "buy_token":context.buy.token,
                                "amount":str(context.sell.raw), "user":context.wallet_address}
                    evidence = "SYNTHETIC_FIXTURE" if release["kind"] == "SYNTHETIC_FIXTURE" else "PROVIDER_UNQUALIFIED"
                    if release["quote"].get("source") == "DIRECT_V2_PROGRAM":
                        from edge_os_api.execution.direct_route_quote_client import (
                            DirectRoutePins, DirectRouteQuoteClient)
                        holder["quote"] = DirectRouteQuoteClient(DirectRoutePins.from_release(release),
                            accepted_request=accepted, slippage_bps=release["quote"]["slippage_bps"],
                            http=runtime.http, deadline_monotonic=deadline,
                            connect_timeout_seconds=limits["deadline_seconds"],
                            max_request_bytes=limits["max_request_bytes"],
                            max_response_bytes=limits["max_response_bytes"], evidence_class=evidence,
                            cancel=stopped, wall_clock=runtime.clock, monotonic=runtime.monotonic)
                    else:
                        holder["quote"] = KuruQuoteClient(endpoint=release["quote"]["endpoint"],
                            bearer_token=runtime.quote_token(), accepted_request=accepted,
                            slippage_bps=release["quote"]["slippage_bps"], http=runtime.http,
                            deadline_monotonic=deadline, connect_timeout_seconds=limits["deadline_seconds"],
                            max_request_bytes=limits["max_request_bytes"],
                            max_response_bytes=limits["max_response_bytes"], evidence_class=evidence,
                            cancel=stopped, wall_clock=runtime.clock, monotonic=runtime.monotonic)
                return holder["quote"].quote(request)

        def signer(prepared: PreparedSubmission) -> Any:
            saved("SIGN_REQUESTED", prepared)
            self.binding.admit(identity, now=self.clock(), synthetic_bindings=self.synthetic_bindings)
            if stopped():
                raise RpcError("SIGNER_STOPPED")
            access = self.signer_access()
            return PrivySignerClient(app_id=access["app_id"], app_secret=access["app_secret"], authorize=access["authorize"],
                request_id=prepared.attempt_id, request_expiry_ms=int(parse_utc(release["transaction"]["request_expires_at"]).timestamp()*1000),
                http=self.http, connect_timeout_seconds=limits["deadline_seconds"], deadline_monotonic=deadline,
                max_response_bytes=limits["max_response_bytes"], cancel=stopped,
                wall_clock_ms=lambda: int(self.clock().timestamp()*1000), monotonic=self.monotonic)

        def original_bytes() -> str:
            value = saved(None)
            current = {"APPROVE_BROADCAST_REQUESTED": "approve", "BROADCAST_REQUESTED": "swap",
                       "REVOKE_BROADCAST_REQUESTED": "revoke"}.get(value.get("stage"))
            if plan is not None and current is None:
                raise RpcError("SAVED_ATTEMPT_UNAVAILABLE")
            record = value if current in (None, "swap") else (value.get(current) or {})
            if (value.get("attempt_id") != holder["attempt_id"]
                    or (plan is not None and record.get("stage") != "BROADCAST_REQUESTED")):
                raise RpcError("SAVED_ATTEMPT_UNAVAILABLE")
            try:
                self.binding.qualify_original(value, synthetic_bindings=self.synthetic_bindings)
            except Exception:
                raise RpcError("SAVED_ATTEMPT_UNAVAILABLE") from None
            if current in ("approve", "revoke"):
                expected = str(context.sell.raw) if current == "approve" else "0"
                if (str(record.get("token", "")).lower() != context.sell.token.lower()
                        or str(record.get("amount_raw")) != expected
                        or str(record.get("spender", "")).lower() != release["route"]["entrypoint_address"].lower()
                        or str((record.get("unsigned") or {}).get("to", "")).lower() != context.sell.token.lower()):
                    raise RpcError("SAVED_BYTES_MISMATCH")
            tx_hash, reasons = validate_signed(record.get("signed_bytes"), record.get("unsigned"),
                                               context.wallet_address)
            if reasons or tx_hash != record.get("transaction_hash"):
                raise RpcError("SAVED_BYTES_MISMATCH")
            return record["signed_bytes"]

        destination = release["broadcast"]
        broadcast = TransactionRpcClient(role="broadcast", destination_id=destination["destination_id"], endpoint=destination["endpoint"],
            plan=[("eth_getTransactionCount", [context.wallet_address, "pending"]), ("eth_sendRawTransaction", None)],
            http=self.http, deadline_monotonic=deadline, connect_timeout_seconds=limits["deadline_seconds"],
            max_request_bytes=limits["max_request_bytes"], max_response_bytes=limits["max_response_bytes"],
            cancel=stopped, monotonic=self.monotonic, original_bytes=original_bytes)
        return OriginalClients(route=AttemptRoute(), signer=None, broadcast=broadcast, observer=self.observer(),
                               signer_for_attempt=signer, begin_attempt=begin)

class _Unavailable:
    """A fail-closed port. Its refusal names the port, so a saved reason reads e.g. HOLDINGS_UNAVAILABLE."""

    def __init__(self, port: str) -> None:
        self._port = port

    def __getattr__(self, name: str) -> Any:
        def refuse(*_: Any, **__: Any) -> Any:
            raise ProviderUnavailable(self._port)
        return refuse


class _ControlledMarkets:
    def __init__(self, runtimes: Mapping[str, ControlledRuntime]) -> None:
        self._runtimes = runtimes

    def observe(self, request: MarketObservationRequest) -> MarketObservations:
        runtime = self._runtimes.get(request.agent_id)
        if runtime is None:
            raise ProviderUnavailable("current_observations")
        return runtime.observe_market(request)


class _ControlledQuotes:
    def __init__(self, runtimes: Mapping[str, ControlledRuntime]) -> None:
        self._runtimes = runtimes

    def quote(self, request: QuoteRequest) -> QuoteResult:
        # Only the requesting agent's own runtime, and only when its binding names the same owner, agent and consent.
        runtime = None if request.agent_id is None else self._runtimes.get(request.agent_id)
        identity = None if runtime is None else runtime.binding.identity()
        route = None if runtime is None else runtime.binding.release.content()["route"]
        if (identity is None or request.owner_id is None or request.consent_adoption_id is None
                or (str(request.owner_id), request.agent_id, str(request.consent_adoption_id)) != (
                    identity["owner_id"], identity["agent_id"], identity["consent_adoption_id"])
                or request.operation != "ENTRY" or request.base_input_raw is not None
                or (request.quote_asset_id, request.quote_decimals, request.base_asset_id, request.base_decimals,
                    request.quote_input_raw) != (route["input_asset"]["asset_id"], route["input_asset"]["decimals"],
                    route["output_asset"]["asset_id"], route["output_asset"]["decimals"], route["approved_input_raw"])):
            raise ProviderUnavailable("approved_minimum")
        try:
            runtime.binding.admit(runtime.binding.identity(), now=runtime.clock(), synthetic_bindings=runtime.synthetic_bindings)
        except ReleaseRefused:
            raise ProviderUnavailable("release") from None
        from edge_os_api.admission.types import parse_utc

        release = runtime.binding.release.content()
        route = release["route"]
        return QuoteResult(AssetAmount(asset_id=route["output_asset"]["asset_id"], decimals=route["output_asset"]["decimals"],
            raw=route["approved_min_output_raw"]), runtime.clock(), parse_utc(release["valid_until"]),
            "approved-minimum:" + runtime.binding.sha256, "APPROVED_MINIMUM")


class _ControlledHoldings:
    def __init__(self, runtimes: Mapping[str, ControlledRuntime]) -> None:
        self._runtimes = runtimes

    def observe(self, *, owner_id: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                assets: list[tuple[str, int]]) -> HoldingsObservation:
        runtime = self._runtimes.get(agent_id)
        if runtime is None:
            raise ProviderUnavailable("holdings")
        identity = runtime.binding.identity()
        if (str(owner_id), agent_id, wallet_id, network_id) != (
                identity["owner_id"], identity["agent_id"], identity["wallet_id"], identity["network_id"]):
            raise ProviderUnavailable("holdings_identity")
        from edge_os_api.execution.provider_observations import RpcHoldingsObserver

        release = runtime.binding.release.content()
        return RpcHoldingsObserver(observer=runtime.observer(), wallet_address=identity["wallet_address"], chain_id=143,
            assets=assets, source=release["observer"]["destination_id"], evidence_class=release["evidence_class"],
            clock=runtime.clock, binding=runtime.binding, synthetic_bindings=runtime.synthetic_bindings).read()


# Populated only by a separately reviewed server release. A mode or environment value cannot register authority.
CONTROLLED_RUNTIMES: Mapping[str, ControlledRuntime] = MappingProxyType({})


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
    original: OriginalRecordings | None = None
    clock: Callable[[], dt.datetime] = utc_now  # the recorded original clients' replay clock
    role: str = "api"
    controlled: Mapping[str, ControlledRuntime] = field(default_factory=dict)
    # The unreduced runtimes `controlled` was built from, so another role is never built from a read-only copy.
    controlled_source: Mapping[str, ControlledRuntime] | None = field(default=None, repr=False)

    def for_role(self, role: str) -> "ProviderPorts":
        if self.mode == "controlled":
            source = self.controlled if self.controlled_source is None else self.controlled_source
            return build_provider_ports("controlled", None, role=role, controlled=source)
        ports = replace(self, role=role)
        if self.original is not None and isinstance(self.holdings, RecordedOriginalHoldings):
            ports.holdings = RecordedOriginalHoldings(self.holdings._factory, self.original, self.holdings._fallback,
                                                     lambda: ports.clock())
        return ports

    def transport(self, *, agent_id: str, plan: PlannedFixtureEffect, operation: str) -> Any:
        if self.chain is None:
            raise ProviderUnavailable("transport")
        return FixtureSubmissionTransport(self.chain, agent_id, plan, operation)

    def original_clients(self, agent_id: str) -> tuple[OriginalClients, RouteProfile] | None:
        """The injected original-transaction clients for a reserved `fx-original` agent, else None."""
        if self.role != "worker" or self.original is None or MARKER_ORIGINAL not in agent_id:
            return None
        return self.original.clients(self.clock), self.original.profile

    def original_observer(self, agent_id: str) -> Any:
        """Recovery constructs only an observer, regardless of the process's execution role."""
        if agent_id in self.controlled:
            return self.controlled[agent_id].observer()
        if self.original is None or MARKER_ORIGINAL not in agent_id:
            raise ProviderUnavailable("receipt")
        return RecordedObservationRpc(self.original, self.clock)

    def describe(self) -> dict[str, Any]:
        return {"mode": self.mode, "evidence_class": FIXTURE_EVIDENCE if self.mode == FIXTURE_MODE else None,
                "fixture_effects": len(self.chain.effects()) if self.chain is not None else None}


def build_provider_ports(mode: str, factory: sessionmaker[Session], effects_path: str | None = None,
                         original_dir: str | None = None, *, role: str = "api",
                         controlled: Mapping[str, ControlledRuntime] | None = None) -> ProviderPorts:
    if role not in ("api", "worker", "recurring"):
        raise ValueError("unknown financial service role")
    if mode == FIXTURE_MODE:
        chain = FixtureChain(effects_path)
        holdings: Any = FixtureHoldings(factory, chain)
        original = OriginalRecordings.load(original_dir) if original_dir else None
        ports = ProviderPorts(mode=FIXTURE_MODE, market=FixtureMarketObservations(), quotes=FixtureQuotes(),
                              holdings=holdings, receipts=FixtureReceipts(chain),
                              deposits=FixtureDepositObserver(factory), removals=FixtureRemovalObserver(),
                              chain=chain, original=original, role=role)
        if original is not None:  # the recorded holdings follow the ports' replay clock
            ports.holdings = RecordedOriginalHoldings(factory, original, holdings, lambda: ports.clock())
        return ports
    source = MappingProxyType(dict(CONTROLLED_RUNTIMES if controlled is None else controlled))
    runtimes = MappingProxyType({key: runtime if role == "worker" else runtime.read_only()
        for key, runtime in source.items()}) if mode == "controlled" else {}
    if mode == "controlled":
        from edge_os_api.execution.provider_observations import UnqualifiedDepositObserver, UnqualifiedRemovalObserver

        return ProviderPorts(mode="controlled", market=_ControlledMarkets(runtimes), quotes=_ControlledQuotes(runtimes),
            holdings=_ControlledHoldings(runtimes), receipts=_Unavailable("receipt"), deposits=UnqualifiedDepositObserver(),
            removals=UnqualifiedRemovalObserver(), role=role, controlled=runtimes, controlled_source=source)
    return ProviderPorts(mode="controlled" if mode == "controlled" else UNAVAILABLE_MODE,
                         market=_Unavailable("observations"), quotes=_Unavailable("quote"),
                         holdings=_Unavailable("holdings"), receipts=_Unavailable("receipt"),
                         deposits=UnavailableDepositObserver(), removals=_Unavailable("removal"), role=role, controlled=runtimes)
