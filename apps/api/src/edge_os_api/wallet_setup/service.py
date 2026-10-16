"""Owner-scoped wallet setup: prepare, dispatch, cancel, resume and read.

Every operation resolves the owner from the verified `Principal`. A foreign or absent setup is
indistinguishable from a missing one (`404`). The setup identity is persisted before any
creation-capable call. The selected React creation route has no `external_id` and no provider
idempotency, so a lost response stays `UNKNOWN` until an exact retained wallet ID is reconciled.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, invalid, not_found
from edge_os_api.records.models import StrategyRevision
from edge_os_api.wallet_setup.persistence import (WalletSetupRow, bind_wallet, conflicting_binding, insert_event,
                                                  load_setup, mark_unknown, record_denial, to_record, utcnow)
from edge_os_api.wallet_setup.provider import CreationRequest, WalletCreationPort, WalletEvidence, WalletProviderUnavailable
from edge_os_api.wallet_setup.recovery import (evidence_is_wellformed, lookup_wallet_evidence, reconcile,
                                               verify_wallet_evidence)
from edge_os_api.wallet_setup.types import (ACCEPTED_NETWORK_IDS, CancellationIntent, SetupEventType, SetupReason,
                                            SetupRecord, SetupState)

AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")

_SQM = "wallet setup"


def _conflict(code: str, detail: str) -> AppError:
    return AppError(409, "WALLET_SETUP", "CONFLICTED", code, [finding(code, "/", detail)], "NOT_RETRYABLE")


def _validate_agent_id(agent_id: str) -> None:
    if not isinstance(agent_id, str) or not AGENT_ID.fullmatch(agent_id):
        raise invalid("/agent_id", "The agent ID must use 1 to 64 URL-safe characters.", "invalid_agent_id")


def _owned_revision(session: Any, principal: Principal, strategy_id: str, strategy_revision_id: str) -> StrategyRevision:
    """Resolve an exact owned immutable revision server-side. A foreign or absent revision is a 404."""
    if not isinstance(strategy_id, str) or not (1 <= len(strategy_id) <= 200):
        raise invalid("/strategy_id", "The strategy ID must be 1 to 200 characters.", "invalid_strategy_id")
    try:
        revision_uuid = uuid.UUID(str(strategy_revision_id))
    except (ValueError, AttributeError, TypeError):
        raise invalid("/strategy_revision_id", "The strategy revision ID must be a UUID.",
                      "invalid_strategy_revision") from None
    row = session.execute(select(StrategyRevision).where(
        StrategyRevision.owner_id == principal.user_id,
        StrategyRevision.strategy_id == strategy_id,
        StrategyRevision.revision_id == revision_uuid)).scalar_one_or_none()
    if row is None:
        raise not_found("strategy revision")
    return row


def _identity_matches(row: WalletSetupRow, identity: dict[str, Any]) -> bool:
    return (row.network_id == identity["network_id"] and row.strategy_id == identity["strategy_id"]
            and row.strategy_revision_id == identity["strategy_revision_id"]
            and row.content_sha256 == identity["content_sha256"]
            and row.manifest_sha256 == identity["manifest_sha256"])


def prepare_setup(session: Any, principal: Principal, *, agent_id: str, network_id: int, strategy_id: str,
                  strategy_revision_id: str, request_key: str) -> SetupRecord:
    """Persist one setup identity before any creation-capable call. Idempotent per `(owner, agent)`."""
    _validate_agent_id(agent_id)
    if network_id not in ACCEPTED_NETWORK_IDS:
        raise invalid("/network_id", "The requested network must be Monad 143 or testnet 10143.", "invalid_network")
    if not isinstance(request_key, str) or not (1 <= len(request_key) <= 200):
        raise invalid("/request_key", "The request key must be 1 to 200 characters.", "invalid_request_key")
    revision = _owned_revision(session, principal, strategy_id, strategy_revision_id)
    identity = {"network_id": int(network_id), "strategy_id": revision.strategy_id,
                "strategy_revision_id": revision.revision_id, "content_sha256": revision.content_sha256,
                "manifest_sha256": revision.manifest_sha256}
    existing = load_setup(session, principal.user_id, agent_id, lock=False)
    if existing is not None:
        if _identity_matches(existing, identity):
            record = to_record(existing)
            session.rollback()
            return record
        record_denial(session, principal.user_id, agent_id, "CHANGED_SETUP_IDENTITY",
                      {"saved_revision_id": str(existing.strategy_revision_id),
                       "requested_revision_id": str(identity["strategy_revision_id"])})
        session.commit()
        raise _conflict("changed_setup_identity",
                        "This agent already holds a saved setup with a different network or strategy revision.")
    row = WalletSetupRow(setup_id=uuid.uuid4(), owner_id=principal.user_id, agent_id=agent_id,
                         network_id=identity["network_id"], strategy_id=identity["strategy_id"],
                         strategy_revision_id=identity["strategy_revision_id"],
                         content_sha256=identity["content_sha256"], manifest_sha256=identity["manifest_sha256"],
                         state=SetupState.REQUESTED.value, cancellation_intent=CancellationIntent.NONE.value,
                         creation_dispatched=False, request_key=request_key, created_at=utcnow(), updated_at=utcnow())
    try:
        session.add(row)
        session.flush()  # a competing valid prepare hits the unique constraint here, not at commit
        insert_event(session, row, SetupEventType.PREPARED,
                     {"network_id": row.network_id, "strategy_id": row.strategy_id,
                      "strategy_revision_id": str(row.strategy_revision_id)})
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = load_setup(session, principal.user_id, agent_id, lock=False)
        if existing is not None and _identity_matches(existing, identity):
            record = to_record(existing)
            session.rollback()
            return record
        record_denial(session, principal.user_id, agent_id, "CHANGED_SETUP_IDENTITY",
                      {"requested_revision_id": str(identity["strategy_revision_id"])})
        session.commit()
        raise _conflict("changed_setup_identity",
                        "Another request already saved a setup for this agent with a different identity.") from None
    return to_record(row)


def _mark_dispatch_intent(session: Any, row: WalletSetupRow) -> None:
    row.state = SetupState.PENDING.value
    row.creation_dispatched = True
    row.updated_at = utcnow()
    insert_event(session, row, SetupEventType.DISPATCH_INTENT,
                 {"network_id": row.network_id, "strategy_revision_id": str(row.strategy_revision_id)})


def _creation_request(row: WalletSetupRow) -> CreationRequest:
    return CreationRequest(owner_id=row.owner_id, agent_id=row.agent_id, network_id=row.network_id,
                           strategy_id=row.strategy_id, strategy_revision_id=row.strategy_revision_id,
                           content_sha256=row.content_sha256, manifest_sha256=row.manifest_sha256)


def _evidence_dict(evidence: WalletEvidence) -> dict[str, Any]:
    return {"owner_id": str(evidence.owner_id), "chain_type": evidence.chain_type, "address": evidence.address}


def _create_after_intent(session: Any, principal: Principal, row: WalletSetupRow,
                         provider: WalletCreationPort) -> SetupRecord:
    try:
        returned = provider.create_wallet(_creation_request(row))
    except WalletProviderUnavailable:
        return mark_unknown(session, row, SetupReason.PROVIDER_UNAVAILABLE.value)
    except Exception:  # noqa: BLE001 - an authored fake may fail in unknown ways; uncertainty is safe
        return mark_unknown(session, row, SetupReason.PROVIDER_ERROR.value)
    if returned is None:
        return mark_unknown(session, row, SetupReason.RESPONSE_LOST.value)
    if not isinstance(returned, WalletEvidence) or not evidence_is_wellformed(returned):
        return mark_unknown(session, row, SetupReason.MALFORMED_RESULT.value)
    insert_event(session, row, SetupEventType.RESULT_RETURNED,
                 {"wallet_id": returned.wallet_id, **_evidence_dict(returned)})
    session.commit()
    return _verify_and_bind(session, principal, row, returned, provider)


def _verify_and_bind(session: Any, principal: Principal, row: WalletSetupRow, returned: WalletEvidence,
                     provider: WalletCreationPort) -> SetupRecord:
    locked = load_setup(session, principal.user_id, row.agent_id, lock=True)
    if locked is None:
        raise not_found(_SQM)
    if locked.state == SetupState.CONFIRMED.value:
        session.rollback()
        if locked.wallet_id == returned.wallet_id:
            return to_record(locked)
        record_denial(session, locked.owner_id, locked.agent_id, "CONFLICTING_RESULT",
                      {"saved_wallet_id": locked.wallet_id, "returned_wallet_id": returned.wallet_id})
        session.commit()
        return to_record(locked)
    looked_up = lookup_wallet_evidence(provider, returned.wallet_id)
    if looked_up is None:
        return mark_unknown(session, locked, SetupReason.RECONCILE_NO_MATCH.value)
    if not verify_wallet_evidence(locked, returned, looked_up):
        return mark_unknown(session, locked, SetupReason.RECONCILE_WRONG_IDENTITY.value)
    if conflicting_binding(session, locked.owner_id, locked.agent_id, looked_up.wallet_id) is not None:
        record_denial(session, locked.owner_id, locked.agent_id, "SAME_OWNER_CROSS_AGENT",
                      {"wallet_id": looked_up.wallet_id})
        return mark_unknown(session, locked, SetupReason.CONFLICTING_WALLET.value)
    return bind_wallet(session, locked, looked_up.wallet_id, _evidence_dict(looked_up), SetupEventType.WALLET_BOUND)


def _advance(session: Any, principal: Principal, row: WalletSetupRow, provider: WalletCreationPort) -> SetupRecord:
    if row.state in (SetupState.CONFIRMED.value, SetupState.FAILED.value):
        session.rollback()
        return to_record(row)
    if row.cancellation_intent == CancellationIntent.REQUESTED_BEFORE_DISPATCH.value and not row.creation_dispatched:
        session.rollback()
        return to_record(row)
    if row.creation_dispatched:
        return reconcile(session, principal, row, provider)
    _mark_dispatch_intent(session, row)
    session.commit()
    return _create_after_intent(session, principal, row, provider)


def dispatch_setup(session: Any, principal: Principal, *, agent_id: str, provider: WalletCreationPort) -> SetupRecord:
    """Dispatch a prepared setup exactly once. A replay, concurrency or prior dispatch never creates again."""
    _validate_agent_id(agent_id)
    row = load_setup(session, principal.user_id, agent_id, lock=True)
    if row is None:
        raise not_found(_SQM)
    return _advance(session, principal, row, provider)


def resume_setup(session: Any, principal: Principal, *, agent_id: str, provider: WalletCreationPort) -> SetupRecord:
    """Resume or reconcile an existing setup without creating a second wallet."""
    return dispatch_setup(session, principal, agent_id=agent_id, provider=provider)


def cancel_setup(session: Any, principal: Principal, *, agent_id: str) -> SetupRecord:
    """Record cancellation intent separately. A proved pre-dispatch cancel causes zero creation calls."""
    _validate_agent_id(agent_id)
    row = load_setup(session, principal.user_id, agent_id, lock=True)
    if row is None:
        raise not_found(_SQM)
    if row.state == SetupState.CONFIRMED.value:
        row.cancellation_intent = CancellationIntent.REQUESTED_AFTER_DISPATCH.value
        row.updated_at = utcnow()
        insert_event(session, row, SetupEventType.CANCELLATION_REQUESTED, {"dispatched": True})
        session.commit()
        return to_record(row)
    if not row.creation_dispatched:
        row.cancellation_intent = CancellationIntent.REQUESTED_BEFORE_DISPATCH.value
        row.state = SetupState.FAILED.value
        row.reason = SetupReason.CANCELLED_BEFORE_DISPATCH.value
        row.updated_at = utcnow()
        insert_event(session, row, SetupEventType.CANCELLED_BEFORE_DISPATCH, {})
        session.commit()
        return to_record(row)
    row.cancellation_intent = CancellationIntent.REQUESTED_AFTER_DISPATCH.value
    row.updated_at = utcnow()
    insert_event(session, row, SetupEventType.CANCELLATION_REQUESTED, {"dispatched": True})
    session.commit()
    return to_record(row)


def complete_from_browser(session: Any, principal: Principal, *, agent_id: str, wallet_id: str,
                          provider: WalletCreationPort, address: str | None = None) -> SetupRecord:
    """Record a wallet id returned by owner-linked browser creation, then bind it only after independent lookup.

    The browser's wallet id is an untrusted claim, retained as evidence before the lookup. The browser keeps its
    wallet id, so after a lost lookup reply the browser repeats this completion; `resume_setup` cannot bind it,
    because the browser claim carries no provider address. The setup binds only when the provider's own
    record names this verified owner, an Ethereum wallet and no other agent of this owner. A completion for a
    confirmed setup never replaces its wallet; a completion after a proved pre-dispatch cancellation, or for a
    setup this owner does not hold, binds nothing. No server-side creation runs on this path.
    """
    _validate_agent_id(agent_id)
    if not evidence_is_wellformed(WalletEvidence(wallet_id=wallet_id, owner_id=principal.user_id,
                                                 chain_type="ethereum", address="claim")) or len(wallet_id) > 200:
        raise invalid("/wallet_id", "The wallet ID must be 1 to 200 storable characters.", "invalid_wallet_id")
    row = load_setup(session, principal.user_id, agent_id, lock=True)
    if row is None:
        raise not_found(_SQM)
    if row.state == SetupState.CONFIRMED.value:
        if row.wallet_id != wallet_id:
            record_denial(session, row.owner_id, row.agent_id, "CONFLICTING_RESULT",
                          {"saved_wallet_id": row.wallet_id, "returned_wallet_id": wallet_id,
                           "source": "BROWSER_COMPLETION"})
            session.commit()
        else:
            session.rollback()
        return to_record(row)
    if row.cancellation_intent == CancellationIntent.REQUESTED_BEFORE_DISPATCH.value and not row.creation_dispatched:
        record_denial(session, row.owner_id, row.agent_id, "LATE_RESULT_AFTER_CANCEL",
                      {"returned_wallet_id": wallet_id, "source": "BROWSER_COMPLETION"})
        session.commit()
        return to_record(row)
    if not row.creation_dispatched:
        _mark_dispatch_intent(session, row)
    insert_event(session, row, SetupEventType.RESULT_RETURNED,
                 {"wallet_id": wallet_id, "owner_id": str(principal.user_id), "chain_type": "ethereum",
                  "address": None, "claimed_address": address if isinstance(address, str) else None,
                  "source": "BROWSER_COMPLETION", "trusted": False})
    session.commit()
    looked_up = lookup_wallet_evidence(provider, wallet_id)
    locked = load_setup(session, principal.user_id, agent_id, lock=True)
    assert locked is not None
    if locked.state == SetupState.CONFIRMED.value:  # a concurrent completion or resume bound first
        session.rollback()
        return to_record(locked)
    if looked_up is None:
        return mark_unknown(session, locked, SetupReason.RECONCILE_NO_MATCH.value)
    if not (looked_up.wallet_id == wallet_id and looked_up.owner_id == locked.owner_id
            and looked_up.chain_type == "ethereum"
            and (address is None or looked_up.address.lower() == address.lower())):
        record_denial(session, locked.owner_id, locked.agent_id, "BROWSER_RESULT_WRONG_IDENTITY",
                      {"returned_wallet_id": wallet_id})
        return mark_unknown(session, locked, SetupReason.RECONCILE_WRONG_IDENTITY.value)
    if conflicting_binding(session, locked.owner_id, locked.agent_id, looked_up.wallet_id) is not None:
        record_denial(session, locked.owner_id, locked.agent_id, "SAME_OWNER_CROSS_AGENT",
                      {"wallet_id": looked_up.wallet_id})
        return mark_unknown(session, locked, SetupReason.CONFLICTING_WALLET.value)
    return bind_wallet(session, locked, looked_up.wallet_id, _evidence_dict(looked_up), SetupEventType.WALLET_BOUND)


def get_setup(session: Any, principal: Principal, *, agent_id: str) -> SetupRecord:
    """Owner-scoped read. A foreign or absent setup is a 404."""
    _validate_agent_id(agent_id)
    row = load_setup(session, principal.user_id, agent_id, lock=False)
    if row is None:
        raise not_found(_SQM)
    record = to_record(row)
    session.rollback()
    return record
