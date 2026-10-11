"""Owner-scoped local funding: declare, prepare, observe, reconcile and read.

Every operation resolves the owner from the verified `Principal`. A foreign or absent wallet binding
is indistinguishable from a missing one (`404`). The confirmed agent-wallet binding comes from the
accepted P17 wallet-setup interface, read only. This package writes no admission, mandate, stop,
allowance, position or execution record. A deposit is an external capital flow, never profit.

Credit is once-only on the exact `(wallet, network, asset, transaction-event identity)`. A unique
constraint plus a per-wallet advisory transaction lock make a replay, a concurrent process, a lost
commit response or a fresh process unable to credit the same event twice.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, invalid, not_found
from edge_os_api.funding.accounting import (InvalidFundingValue, asset_belongs_to_network, canonical_raw,
                                            classify_asset, declared_amount, parse_asset_amount, storable_text,
                                            validate_address, validate_decimals, validate_identifier)
from edge_os_api.funding.observation import DepositObservation, DepositObservationPort, ObservationUnavailable
from edge_os_api.funding.persistence import (FundingCreditRow, FundingFlowRow, FundingProfileRow, credit_for_identity,
                                             credits_for_wallet, flows_for_wallet, insert_observation, list_flows,
                                             load_flow, load_flow_by_reference, load_profile, record_denial, to_credit,
                                             to_flow, to_observation, to_profile, utcnow)
from edge_os_api.funding.types import (ACCEPTED_NETWORK_IDS, AssetAmount, AssetClass, CreditRecord, FlowKind, FlowState,
                                       FundingBalance, FundingFlowRecord, FundingProfileRecord, FundingReason,
                                       ObservationRecord, ObservationStatus, ReconciliationResult)
from edge_os_api.wallet_setup.persistence import load_setup as load_wallet_setup
from edge_os_api.wallet_setup.types import SetupState

_SUPPORTED_KINDS = (FlowKind.DEPOSIT,)
_SUPPORTED_CLASSES = (AssetClass.NATIVE_GAS, AssetClass.TRADING)
_SQM = "wallet setup"


@dataclass(frozen=True)
class WalletBinding:
    """The confirmed P17 binding: one owner-owned wallet for one agent on one network."""

    wallet_id: str
    network_id: int


def resolve_wallet_binding(session: Any, owner_id: uuid.UUID, agent_id: str) -> WalletBinding | None:
    """Read the accepted P17 confirmed binding. A missing or unconfirmed setup returns `None`."""
    row = load_wallet_setup(session, owner_id, agent_id, lock=False)
    if row is None or row.state != SetupState.CONFIRMED.value or not row.wallet_id:
        return None
    return WalletBinding(wallet_id=row.wallet_id, network_id=row.network_id)


def _require_binding(session: Any, principal: Principal, agent_id: str) -> WalletBinding:
    binding = resolve_wallet_binding(session, principal.user_id, agent_id)
    if binding is None:
        raise not_found(_SQM)
    return binding


def _conflict(code: str, detail: str) -> AppError:
    return AppError(409, "FUNDING", "CONFLICTED", code, [finding(code, "/", detail)], "NOT_RETRYABLE")


def _validate_agent_id(agent_id: object) -> str:
    return validate_identifier(agent_id, field="agent_id", max_length=64)


def _validate_network(network_id: object) -> int:
    if isinstance(network_id, bool) or not isinstance(network_id, int) or network_id not in ACCEPTED_NETWORK_IDS:
        raise invalid("/network_id", "The requested network must be Monad 143 or testnet 10143.", "invalid_network")
    return network_id


def _lock_keys(owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: int) -> tuple[int, int]:
    digest = hashlib.sha256(f"{owner}:{agent_id}:{wallet_id}:{network_id}".encode()).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    return int4(0), int4(4)


def _acquire_wallet_lock(session: Any, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: int) -> None:
    key_a, key_b = _lock_keys(owner, agent_id, wallet_id, network_id)
    session.execute(text("SELECT pg_advisory_xact_lock(:key_a, :key_b)"), {"key_a": key_a, "key_b": key_b})


def declare_funding_assets(session: Any, principal: Principal, *, agent_id: str, network_id: int,
                           trading_asset_id: str, trading_decimals: int, gas_asset_id: str, gas_decimals: int,
                           compute_asset_id: str | None = None, compute_decimals: int | None = None
                           ) -> FundingProfileRecord:
    """Persist the declared supported assets for one confirmed agent wallet. Idempotent per agent."""
    agent_id = _validate_agent_id(agent_id)
    _validate_network(network_id)
    try:
        trading_id = validate_identifier(trading_asset_id, field="trading_asset_id")
        trading_dp = validate_decimals(trading_decimals)
        gas_id = validate_identifier(gas_asset_id, field="gas_asset_id")
        gas_dp = validate_decimals(gas_decimals)
        compute_id = validate_identifier(compute_asset_id, field="compute_asset_id") if compute_asset_id is not None else None
        compute_dp = validate_decimals(compute_decimals) if compute_decimals is not None else None
    except InvalidFundingValue as error:
        raise invalid("/declaration", str(error), "invalid_declaration") from None
    if (compute_id is None) != (compute_dp is None):
        raise invalid("/compute_asset", "A compute asset needs both an id and decimals.", "invalid_declaration")
    declared_ids = [trading_id, gas_id] + ([compute_id] if compute_id is not None else [])
    for declared_id in declared_ids:
        if not asset_belongs_to_network(declared_id, network_id):
            raise invalid("/declaration", "Every declared asset must belong to the requested Monad network.",
                          "wrong_network_asset")
    if len(set(declared_ids)) != len(declared_ids):
        raise invalid("/declaration", "The gas, trading and compute assets must be distinct.",
                      "duplicate_declared_asset")
    binding = _require_binding(session, principal, agent_id)
    if binding.network_id != network_id:
        record_denial(session, principal.user_id, agent_id, FundingReason.NETWORK_MISMATCH.value,
                      {"bound_network": binding.network_id, "requested_network": network_id})
        session.commit()
        raise _conflict("network_mismatch", "The requested network does not match the confirmed wallet binding.")
    existing = load_profile(session, principal.user_id, agent_id, lock=True)
    if existing is not None:
        unchanged = (existing.wallet_id == binding.wallet_id and existing.network_id == binding.network_id
                     and existing.trading_asset_id == trading_id and int(existing.trading_decimals) == trading_dp
                     and existing.gas_asset_id == gas_id and int(existing.gas_decimals) == gas_dp
                     and existing.compute_asset_id == compute_id
                     and (existing.compute_decimals is None or compute_dp is None or int(existing.compute_decimals) == compute_dp))
        if unchanged:
            record = to_profile(existing)
            session.rollback()
            return record
        record_denial(session, principal.user_id, agent_id, FundingReason.CHANGED_DECLARATION.value,
                      {"saved_trading_asset": existing.trading_asset_id, "requested_trading_asset": trading_id})
        session.commit()
        raise _conflict("changed_declaration", "This agent wallet already holds a different asset declaration.")
    now = utcnow()
    row = FundingProfileRow(profile_id=uuid.uuid4(), owner_id=principal.user_id, agent_id=agent_id,
                            wallet_id=binding.wallet_id, network_id=network_id, trading_asset_id=trading_id,
                            trading_decimals=trading_dp, gas_asset_id=gas_id, gas_decimals=gas_dp,
                            compute_asset_id=compute_id, compute_decimals=compute_dp, created_at=now, updated_at=now)
    session.add(row)
    session.commit()
    return to_profile(row)


def prepare_funding(session: Any, principal: Principal, *, agent_id: str, kind: FlowKind | str, asset_id: str,
                    raw: str, decimals: int, transport: str, reference: str, sender: str | None = None,
                    recipient: str | None = None, declared_fee_asset_id: str | None = None,
                    declared_fee_raw: str | None = None, declared_fee_decimals: int | None = None) -> FundingFlowRecord:
    """Persist one reviewed funding flow before any transfer. Idempotent per `(owner, agent, reference)`."""
    agent_id = _validate_agent_id(agent_id)
    try:
        flow_kind = FlowKind(kind)
    except ValueError:
        raise invalid("/kind", "The flow kind must be DEPOSIT or WITHDRAWAL.", "invalid_kind") from None
    try:
        clean_transport = validate_identifier(transport, field="transport")
        clean_reference = validate_identifier(reference, field="reference")
        clean_sender = validate_address(sender, field="sender") if sender is not None else None
        clean_recipient = validate_address(recipient, field="recipient") if recipient is not None else None
        amount = parse_asset_amount(asset_id, raw, decimals)
        fee = _parse_declared_fee(declared_fee_asset_id, declared_fee_raw, declared_fee_decimals)
    except InvalidFundingValue as error:
        raise invalid("/flow", str(error), "invalid_flow") from None
    binding = _require_binding(session, principal, agent_id)
    if flow_kind not in _SUPPORTED_KINDS:
        record_denial(session, principal.user_id, agent_id, FundingReason.UNSUPPORTED_KIND.value,
                      {"kind": flow_kind.value})
        session.commit()
        raise _conflict("unsupported_kind", "This local stage prepares deposits only.")
    if not asset_belongs_to_network(amount.asset_id, binding.network_id):
        record_denial(session, principal.user_id, agent_id, FundingReason.WRONG_NETWORK.value,
                      {"asset_id": amount.asset_id, "network_id": binding.network_id})
        session.commit()
        raise _conflict("wrong_network_asset", "The flow asset does not belong to the wallet network.")
    profile_row = load_profile(session, principal.user_id, agent_id, lock=False)
    if profile_row is None:
        raise not_found("funding declaration")
    profile = to_profile(profile_row)
    asset_class = classify_asset(profile, amount.asset_id)
    declared = declared_amount(profile, amount.asset_id)
    if asset_class is None or asset_class not in _SUPPORTED_CLASSES or declared is None:
        record_denial(session, principal.user_id, agent_id, FundingReason.UNSUPPORTED_ASSET.value,
                      {"asset_id": amount.asset_id})
        session.commit()
        raise _conflict("unsupported_asset", "The asset is not a declared trading asset or native gas asset.")
    if amount.decimals != declared.decimals:
        record_denial(session, principal.user_id, agent_id, FundingReason.DECIMALS_MISMATCH.value,
                      {"declared_decimals": declared.decimals, "requested_decimals": amount.decimals})
        session.commit()
        raise _conflict("decimals_mismatch", "The amount decimals do not match the declared asset decimals.")
    if fee is not None:
        fee_declared = declared_amount(profile, fee.asset_id)
        if fee_declared is None or classify_asset(profile, fee.asset_id) not in _SUPPORTED_CLASSES:
            record_denial(session, principal.user_id, agent_id, FundingReason.UNSUPPORTED_ASSET.value,
                          {"fee_asset_id": fee.asset_id})
            session.commit()
            raise _conflict("unsupported_fee_asset", "The fee asset is not a declared asset for this wallet.")
        if fee.decimals != fee_declared.decimals:
            record_denial(session, principal.user_id, agent_id, FundingReason.DECIMALS_MISMATCH.value,
                          {"fee_declared_decimals": fee_declared.decimals, "fee_requested_decimals": fee.decimals})
            session.commit()
            raise _conflict("fee_decimals_mismatch", "The fee decimals do not match the declared fee asset decimals.")
    existing = load_flow_by_reference(session, principal.user_id, binding.wallet_id, binding.network_id, clean_reference)
    if existing is not None:
        if _flow_matches(existing, flow_kind, amount, clean_transport, clean_sender, clean_recipient, fee):
            record = to_flow(existing)
            session.rollback()
            return record
        record_denial(session, principal.user_id, agent_id, FundingReason.CHANGED_FLOW_IDENTITY.value,
                      {"reference": clean_reference})
        session.commit()
        raise _conflict("changed_flow_identity", "This reference already holds a different reviewed flow.")
    now = utcnow()
    row = FundingFlowRow(flow_id=uuid.uuid4(), owner_id=principal.user_id, agent_id=agent_id,
                         wallet_id=binding.wallet_id, network_id=binding.network_id, kind=flow_kind.value,
                         asset_id=amount.asset_id, declared_raw=int(amount.raw), decimals=amount.decimals,
                         declared_fee_raw=int(fee.raw) if fee is not None else None,
                         declared_fee_decimals=fee.decimals if fee is not None else None,
                         declared_fee_asset_id=fee.asset_id if fee is not None else None, transport=clean_transport,
                         sender=clean_sender, recipient=clean_recipient, state=FlowState.PENDING.value,
                         reference=clean_reference, transaction_reference=None, reason=None, created_at=now,
                         updated_at=now)
    try:
        session.add(row)
        session.flush()
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = load_flow_by_reference(session, principal.user_id, binding.wallet_id, binding.network_id,
                                          clean_reference)
        if existing is not None and _flow_matches(existing, flow_kind, amount, clean_transport, clean_sender,
                                                  clean_recipient, fee):
            record = to_flow(existing)
            session.rollback()
            return record
        record_denial(session, principal.user_id, agent_id, FundingReason.CHANGED_FLOW_IDENTITY.value,
                      {"reference": clean_reference})
        session.commit()
        raise _conflict("changed_flow_identity", "Another request saved a different flow for this reference.") from None
    return to_flow(row)


def _flow_matches(row: FundingFlowRow, kind: FlowKind, amount: AssetAmount, transport: str, sender: str | None,
                  recipient: str | None, fee: AssetAmount | None) -> bool:
    return (row.kind == kind.value and row.asset_id == amount.asset_id and int(row.declared_raw) == int(amount.raw)
            and int(row.decimals) == amount.decimals and row.transport == transport and row.sender == sender
            and row.recipient == recipient and _row_fee(row) == (int(fee.raw) if fee is not None else None)
            and row.declared_fee_asset_id == (fee.asset_id if fee is not None else None)
            and (row.declared_fee_decimals is None or fee is None or int(row.declared_fee_decimals) == fee.decimals))


def _parse_declared_fee(asset_id: str | None, raw: str | None, decimals: int | None) -> AssetAmount | None:
    """A declared fee needs an explicit asset id, raw amount and decimals, or it stays unknown.

    The fee keeps its own asset identity, so a native MON network fee stays separate from a trading
    asset fee. A partially specified fee is rejected rather than stored under a false asset.
    """
    if asset_id is None and raw is None and decimals is None:
        return None
    if asset_id is None or raw is None or decimals is None:
        raise InvalidFundingValue("a declared fee needs an asset id, a raw amount and decimals")
    return parse_asset_amount(asset_id, raw, decimals)


def _row_fee(row: FundingFlowRow) -> int | None:
    return None if row.declared_fee_raw is None else int(row.declared_fee_raw)


def get_funding(session: Any, principal: Principal, *, agent_id: str, flow_id: str) -> FundingFlowRecord:
    """Owner-scoped read. A foreign or absent flow is a 404."""
    agent_id = _validate_agent_id(agent_id)
    try:
        clean_id = uuid.UUID(str(flow_id))
    except (ValueError, AttributeError, TypeError):
        raise invalid("/flow_id", "The flow ID must be a UUID.", "invalid_flow_id") from None
    row = load_flow(session, principal.user_id, agent_id, clean_id, lock=False)
    if row is None:
        raise not_found("funding flow")
    record = to_flow(row)
    session.rollback()
    return record


def list_funding(session: Any, principal: Principal, *, agent_id: str) -> list[FundingFlowRecord]:
    """Owner-scoped list of the agent's funding flows."""
    agent_id = _validate_agent_id(agent_id)
    rows = list_flows(session, principal.user_id, agent_id)
    records = [to_flow(row) for row in rows]
    session.rollback()
    return records


def available_credit(session: Any, principal: Principal, *, agent_id: str, asset_id: str) -> AssetAmount:
    """The confirmed, reconciled, spendable credit for one wallet asset. Pending money is unavailable."""
    agent_id = _validate_agent_id(agent_id)
    try:
        clean_asset = validate_identifier(asset_id, field="asset_id")
    except InvalidFundingValue as error:
        raise invalid("/asset_id", str(error), "invalid_asset") from None
    binding = _require_binding(session, principal, agent_id)
    profile_row = load_profile(session, principal.user_id, agent_id, lock=False)
    if profile_row is None:
        raise not_found("funding declaration")
    profile = to_profile(profile_row)
    declared = declared_amount(profile, clean_asset)
    if declared is None:
        raise invalid("/asset_id", "The asset is not declared for this wallet.", "unsupported_asset")
    total = sum(int(row.actual_raw) for row in credits_for_wallet(session, principal.user_id, binding.wallet_id,
                                                                  binding.network_id, clean_asset))
    session.rollback()
    return AssetAmount(asset_id=clean_asset, raw=str(total), decimals=declared.decimals)


def wallet_funding_summary(session: Any, principal: Principal, *, agent_id: str) -> list[FundingBalance]:
    """Confirmed available and unavailable pending amounts per asset class, never pooled across wallets."""
    agent_id = _validate_agent_id(agent_id)
    binding = _require_binding(session, principal, agent_id)
    profile_row = load_profile(session, principal.user_id, agent_id, lock=False)
    if profile_row is None:
        raise not_found("funding declaration")
    profile = to_profile(profile_row)
    balances: list[FundingBalance] = []
    for asset_class, declared in ((AssetClass.NATIVE_GAS, profile.gas_asset),
                                  (AssetClass.TRADING, profile.trading_asset),
                                  (AssetClass.COMPUTE, profile.compute_asset)):
        if declared is None:
            continue
        credits = credits_for_wallet(session, principal.user_id, binding.wallet_id, binding.network_id,
                                     declared.asset_id)
        available = sum(int(row.actual_raw) for row in credits)
        pending = sum(int(row.declared_raw) for row in flows_for_wallet(session, principal.user_id, binding.wallet_id,
                                                                        binding.network_id)
                      if row.state == FlowState.PENDING.value and row.asset_id == declared.asset_id)
        balances.append(FundingBalance(asset_class=asset_class, asset_id=declared.asset_id,
                                       available=AssetAmount(asset_id=declared.asset_id, raw=str(available),
                                                             decimals=declared.decimals),
                                       pending=AssetAmount(asset_id=declared.asset_id, raw=str(pending),
                                                           decimals=declared.decimals)))
    session.rollback()
    return balances


def reconcile_funding(session: Any, principal: Principal, *, agent_id: str, observer: DepositObservationPort
                      ) -> list[ReconciliationResult]:
    """Reconcile the agent wallet against the controlled observation boundary.

    Only a CONFIRMED observation credits an actual amount, once, for the exact
    `(wallet, network, asset, transaction-event identity)`. Pending, unknown, failed, duplicate,
    unsupported, wrong-wallet and wrong-network observations stay unavailable and inspectable.
    """
    agent_id = _validate_agent_id(agent_id)
    binding = _require_binding(session, principal, agent_id)
    _acquire_wallet_lock(session, principal.user_id, agent_id, binding.wallet_id, binding.network_id)
    profile_row = load_profile(session, principal.user_id, agent_id, lock=False)
    profile = to_profile(profile_row) if profile_row is not None else None
    try:
        observations = list(observer.observe(binding.wallet_id, binding.network_id))
    except ObservationUnavailable:
        record_denial(session, principal.user_id, agent_id, "OBSERVATION_UNAVAILABLE", {"wallet_id": binding.wallet_id})
        session.commit()
        return []
    results: dict[uuid.UUID, ReconciliationResult] = {}
    for observation in observations:
        _apply_observation(session, principal, agent_id, binding, profile, observation, results)
    session.commit()
    return list(results.values())


def _record(session: Any, principal: Principal, agent_id: str, binding: WalletBinding, observation: DepositObservation,
            *, status: ObservationStatus, flow_id: uuid.UUID | None, reason: str | None,
            asset_id: str | None, actual: AssetAmount | None, fee: AssetAmount | None,
            event_id: str | None) -> ObservationRecord:
    row = insert_observation(session, flow_id=flow_id, owner_id=principal.user_id, agent_id=agent_id,
                             wallet_id=binding.wallet_id, network_id=binding.network_id, asset_id=asset_id,
                             actual_raw=int(actual.raw) if actual is not None else None,
                             decimals=actual.decimals if actual is not None else None,
                             fee_raw=int(fee.raw) if fee is not None else None,
                             fee_decimals=fee.decimals if fee is not None else None,
                             fee_asset_id=fee.asset_id if fee is not None else None, event_id=event_id,
                             transaction_reference=observation.reference, status=status.value, sender=observation.sender,
                             recipient=observation.recipient, reason=reason, observed_at=observation.observed_at)
    return to_observation(row)


def _malformed(session: Any, principal: Principal, agent_id: str, binding: WalletBinding, observation: DepositObservation,
               reason: str) -> None:
    record_denial(session, principal.user_id, agent_id, reason, {"reference": observation.reference})
    _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN, flow_id=None,
            reason=reason, asset_id=None, actual=None, fee=None, event_id=None)


def _apply_observation(session: Any, principal: Principal, agent_id: str, binding: WalletBinding,
                       profile: FundingProfileRecord | None, observation: DepositObservation,
                       results: dict[uuid.UUID, ReconciliationResult]) -> None:
    if not isinstance(observation, DepositObservation):
        return
    if observation.wallet_id != binding.wallet_id:
        _malformed(session, principal, agent_id, binding, observation, FundingReason.WRONG_WALLET.value)
        return
    if observation.network_id != binding.network_id:
        _malformed(session, principal, agent_id, binding, observation, FundingReason.WRONG_NETWORK.value)
        return
    flow = load_flow_by_reference(session, principal.user_id, binding.wallet_id, binding.network_id,
                                  observation.reference) if storable_text(observation.reference) else None
    if flow is None:
        _malformed(session, principal, agent_id, binding, observation, FundingReason.NO_MATCHING_FLOW.value)
        return
    if storable_text(observation.asset_id) and not asset_belongs_to_network(observation.asset_id, binding.network_id):
        record_denial(session, principal.user_id, agent_id, FundingReason.WRONG_NETWORK.value,
                      {"asset_id": observation.asset_id, "network_id": binding.network_id})
        _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN,
                flow_id=flow.flow_id, reason=FundingReason.WRONG_NETWORK.value, asset_id=None, actual=None, fee=None,
                event_id=None)
        return
    if profile is None or not storable_text(observation.asset_id) or observation.asset_id != flow.asset_id \
            or classify_asset(profile, observation.asset_id) not in _SUPPORTED_CLASSES:
        record_denial(session, principal.user_id, agent_id, FundingReason.UNSUPPORTED_ASSET.value,
                      {"asset_id": observation.asset_id})
        _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN, flow_id=flow.flow_id,
                reason=FundingReason.UNSUPPORTED_ASSET.value, asset_id=None, actual=None, fee=None, event_id=None)
        return
    actual, fee = _parse_observed_amounts(observation, flow, profile)
    if observation.status == ObservationStatus.CONFIRMED:
        _credit_confirmed(session, principal, agent_id, binding, flow, observation, actual, fee, results)
    elif observation.status == ObservationStatus.DUPLICATE:
        _record(session, principal, agent_id, binding, observation, status=ObservationStatus.DUPLICATE,
                flow_id=flow.flow_id, reason=FundingReason.DUPLICATE_EVENT.value, asset_id=flow.asset_id,
                actual=actual, fee=fee, event_id=observation.event_id)
    else:
        record = _record(session, principal, agent_id, binding, observation, status=observation.status,
                         flow_id=flow.flow_id, reason=None, asset_id=flow.asset_id, actual=actual, fee=fee,
                         event_id=observation.event_id)
        if flow.state != FlowState.CONFIRMED.value:
            flow.state = observation.status.value
            flow.updated_at = utcnow()
        _add_result(results, flow, record)


def _parse_observed_amounts(observation: DepositObservation, flow: FundingFlowRow,
                            profile: FundingProfileRecord) -> tuple[AssetAmount | None, AssetAmount | None]:
    try:
        actual = None
        if observation.raw is not None and observation.decimals is not None:
            actual = AssetAmount(asset_id=flow.asset_id, raw=canonical_raw(observation.raw),
                                 decimals=validate_decimals(observation.decimals))
    except InvalidFundingValue:
        return None, None
    return actual, _parse_observed_fee(observation, profile)


def _parse_observed_fee(observation: DepositObservation, profile: FundingProfileRecord) -> AssetAmount | None:
    """An observed fee keeps its own asset identity and declared decimals, or it stays unknown.

    A fee with no asset id, a non-declared asset, malformed values or non-matching decimals is left
    unknown rather than stored under the transfer's asset. The actual credit amount is unaffected.
    """
    if observation.fee_asset_id is None or observation.fee_raw is None or observation.fee_decimals is None:
        return None
    try:
        raw = canonical_raw(observation.fee_raw)
        decimals = validate_decimals(observation.fee_decimals)
    except InvalidFundingValue:
        return None
    fee_declared = declared_amount(profile, observation.fee_asset_id)
    if fee_declared is None or classify_asset(profile, observation.fee_asset_id) not in _SUPPORTED_CLASSES:
        return None
    if decimals != fee_declared.decimals:
        return None
    return AssetAmount(asset_id=observation.fee_asset_id, raw=raw, decimals=decimals)


def _credit_confirmed(session: Any, principal: Principal, agent_id: str, binding: WalletBinding, flow: FundingFlowRow,
                      observation: DepositObservation, actual: AssetAmount | None, fee: AssetAmount | None,
                      results: dict[uuid.UUID, ReconciliationResult]) -> None:
    if not storable_text(observation.event_id) or actual is None:
        record_denial(session, principal.user_id, agent_id, FundingReason.MALFORMED_OBSERVATION.value,
                      {"reference": observation.reference})
        record = _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN,
                         flow_id=flow.flow_id, reason=FundingReason.MALFORMED_OBSERVATION.value, asset_id=flow.asset_id,
                         actual=actual, fee=fee, event_id=observation.event_id)
        _add_result(results, flow, record)
        return
    if actual.decimals != int(flow.decimals):
        record_denial(session, principal.user_id, agent_id, FundingReason.DECIMALS_MISMATCH.value,
                      {"flow_decimals": int(flow.decimals), "observed_decimals": actual.decimals})
        record = _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN,
                         flow_id=flow.flow_id, reason=FundingReason.DECIMALS_MISMATCH.value, asset_id=flow.asset_id,
                         actual=actual, fee=fee, event_id=observation.event_id)
        _add_result(results, flow, record)
        return
    existing = credit_for_identity(session, binding.wallet_id, binding.network_id, flow.asset_id, observation.event_id)
    if existing is not None:
        _record_existing_credit(session, principal, agent_id, binding, flow, observation, actual, fee, existing, results)
        return
    record = _record(session, principal, agent_id, binding, observation, status=ObservationStatus.CONFIRMED,
                     flow_id=flow.flow_id, reason=None, asset_id=flow.asset_id, actual=actual, fee=fee,
                     event_id=observation.event_id)
    credit_row = FundingCreditRow(credit_id=uuid.uuid4(), owner_id=principal.user_id, agent_id=agent_id,
                                  wallet_id=binding.wallet_id, network_id=binding.network_id, asset_id=flow.asset_id,
                                  actual_raw=int(actual.raw), decimals=actual.decimals,
                                  fee_raw=int(fee.raw) if fee is not None else None,
                                  fee_decimals=fee.decimals if fee is not None else None,
                                  fee_asset_id=fee.asset_id if fee is not None else None, event_id=observation.event_id,
                                  flow_id=flow.flow_id, observation_id=record.observation_id, created_at=utcnow())
    try:
        with session.begin_nested():
            session.add(credit_row)
    except IntegrityError:
        existing = credit_for_identity(session, binding.wallet_id, binding.network_id, flow.asset_id,
                                       observation.event_id)
        if existing is not None:
            _record_existing_credit(session, principal, agent_id, binding, flow, observation, actual, fee, existing,
                                    results)
        return
    if flow.state != FlowState.CONFIRMED.value:
        flow.state = FlowState.CONFIRMED.value
    flow.transaction_reference = observation.reference
    flow.reason = None
    flow.updated_at = utcnow()
    session.flush()
    _add_result(results, flow, record, credit=to_credit(credit_row))


def _record_existing_credit(session: Any, principal: Principal, agent_id: str, binding: WalletBinding,
                            flow: FundingFlowRow, observation: DepositObservation, actual: AssetAmount,
                            fee: AssetAmount | None, existing: FundingCreditRow,
                            results: dict[uuid.UUID, ReconciliationResult]) -> None:
    if existing.owner_id != principal.user_id or existing.agent_id != agent_id:
        # The once-only identity already belongs to another owner or agent. The event is not this
        # owner's, so this flow stays unavailable and the foreign event stays inspectable.
        record_denial(session, principal.user_id, agent_id, FundingReason.WRONG_OWNER.value,
                      {"event_id": observation.event_id, "credited_owner": str(existing.owner_id),
                       "credited_agent": existing.agent_id})
        record = _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN,
                         flow_id=flow.flow_id, reason=FundingReason.WRONG_OWNER.value, asset_id=flow.asset_id,
                         actual=actual, fee=fee, event_id=observation.event_id)
        _add_result(results, flow, record)
        return
    if _credit_matches(existing, actual, fee):
        record = _record(session, principal, agent_id, binding, observation, status=ObservationStatus.DUPLICATE,
                         flow_id=flow.flow_id, reason=FundingReason.DUPLICATE_EVENT.value, asset_id=flow.asset_id,
                         actual=actual, fee=fee, event_id=observation.event_id)
        if flow.state != FlowState.CONFIRMED.value:
            flow.state = FlowState.CONFIRMED.value
            flow.updated_at = utcnow()
        _add_result(results, flow, record)
        return
    record_denial(session, principal.user_id, agent_id, FundingReason.CONFLICTING_TERMINAL_EVIDENCE.value,
                  {"event_id": observation.event_id, "credited_raw": str(int(existing.actual_raw)),
                   "observed_raw": actual.raw})
    record = _record(session, principal, agent_id, binding, observation, status=ObservationStatus.UNKNOWN,
                     flow_id=flow.flow_id, reason=FundingReason.CONFLICTING_TERMINAL_EVIDENCE.value,
                     asset_id=flow.asset_id, actual=actual, fee=fee, event_id=observation.event_id)
    _add_result(results, flow, record)


def _credit_matches(existing: FundingCreditRow, actual: AssetAmount, fee: AssetAmount | None) -> bool:
    if int(existing.actual_raw) != int(actual.raw) or int(existing.decimals) != actual.decimals:
        return False
    existing_fee = None if existing.fee_raw is None else (
        existing.fee_asset_id, str(int(existing.fee_raw)),
        int(existing.fee_decimals) if existing.fee_decimals is not None else None)
    new_fee = None if fee is None else (fee.asset_id, fee.raw, fee.decimals)
    return existing_fee == new_fee


def _add_result(results: dict[uuid.UUID, ReconciliationResult], flow: FundingFlowRow,
                observation: ObservationRecord, credit: CreditRecord | None = None) -> None:
    current = results.get(flow.flow_id)
    observations = (current.observations if current is not None else []) + [observation]
    credits = (current.credits if current is not None else []) + ([credit] if credit is not None else [])
    denials = (current.denials if current is not None else []) + ([observation.reason] if observation.reason else [])
    results[flow.flow_id] = ReconciliationResult(flow=to_flow(flow), observations=observations, credits=credits,
                                                 denials=denials)
