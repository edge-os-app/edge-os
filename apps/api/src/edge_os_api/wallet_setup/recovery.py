"""Recovery and reconciliation for uncertain wallet setups.

The selected React creation route has no `external_id` and no provider idempotency. A setup is
reconciled only against an exact retained returned server wallet ID plus independently checked
provider owner/chain/address evidence. No first or latest wallet is selected, and creation is
never repeated to resolve uncertainty.
"""

from __future__ import annotations

import uuid
from typing import Any

from edge_os_api.wallet_setup.persistence import (WalletSetupRow, bind_wallet, conflicting_binding, latest_event,
                                                  mark_unknown, record_denial, to_record)
from edge_os_api.wallet_setup.provider import WalletCreationPort, WalletEvidence, WalletProviderUnavailable
from edge_os_api.wallet_setup.types import (EVM_CHAIN_TYPE, SetupEventType, SetupReason, SetupRecord, SetupState)


def evidence_is_wellformed(evidence: WalletEvidence) -> bool:
    """Runtime field validation for provider data. A dataclass annotation does not validate a value.

    It rejects a malformed field before any JSON write or binding, so an invalid result cannot fail the
    retained-event write and leave the setup `PENDING` without a reason.
    """
    return (_storable_text(evidence.wallet_id)
            and isinstance(evidence.owner_id, uuid.UUID)
            and _storable_text(evidence.chain_type)
            and _storable_text(evidence.address))


def _storable_text(value: object) -> bool:
    """A non-empty string PostgreSQL can store.

    A NUL (U+0000) and an unpaired surrogate are valid Python `str` values but break a UTF-8 JSONB
    write. Reject both at the boundary so an unretainable result becomes durable `UNKNOWN`.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def evidence_matches_identity(row: WalletSetupRow, evidence: WalletEvidence) -> bool:
    """An exact, owner-bound, Ethereum, addressed wallet record. Network stays an application binding."""
    return (evidence_is_wellformed(evidence)
            and evidence.owner_id == row.owner_id
            and evidence.chain_type == EVM_CHAIN_TYPE)


def verify_wallet_evidence(row: WalletSetupRow, returned: WalletEvidence, looked_up: WalletEvidence) -> bool:
    """Require the returned result and the independent lookup to describe one identical wallet."""
    return (evidence_matches_identity(row, looked_up)
            and evidence_matches_identity(row, returned)
            and returned.wallet_id == looked_up.wallet_id
            and returned.address == looked_up.address)


def lookup_wallet_evidence(provider: WalletCreationPort, wallet_id: str) -> WalletEvidence | None:
    """One exact provider lookup. Any failure or malformed answer stays `UNKNOWN` (returns `None`)."""
    try:
        result = provider.lookup_wallet(wallet_id)
    except WalletProviderUnavailable:
        return None
    except Exception:  # noqa: BLE001 - an authored fake may fail in unknown ways; uncertainty is safe
        return None
    return result if isinstance(result, WalletEvidence) and evidence_is_wellformed(result) else None


def _retained_evidence(content: dict[str, Any]) -> WalletEvidence | None:
    """Rebuild the retained `RESULT_RETURNED` evidence. A malformed retained record has no exact match."""
    wallet_id, owner_id = content.get("wallet_id"), content.get("owner_id")
    chain_type, address = content.get("chain_type"), content.get("address")
    if not (isinstance(wallet_id, str) and wallet_id and isinstance(address, str) and address):
        return None
    try:
        owner = uuid.UUID(str(owner_id))
    except (ValueError, TypeError):
        return None
    return WalletEvidence(wallet_id=wallet_id, owner_id=owner, chain_type=str(chain_type), address=address)


def _same_wallet(left: WalletEvidence, right: WalletEvidence) -> bool:
    return (left.wallet_id == right.wallet_id and left.owner_id == right.owner_id
            and left.chain_type == right.chain_type and left.address == right.address)


def reconcile(session: Any, principal: Any, row: WalletSetupRow, provider: WalletCreationPort) -> SetupRecord:
    """Resolve a PENDING or UNKNOWN setup. It never invokes creation."""
    if row.state == SetupState.CONFIRMED.value:
        session.rollback()
        return to_record(row)
    if not row.creation_dispatched:
        session.rollback()
        return to_record(row)
    retained = latest_event(session, row, SetupEventType.RESULT_RETURNED)
    retained_evidence = _retained_evidence(retained) if isinstance(retained, dict) else None
    if retained_evidence is None:
        return mark_unknown(session, row, SetupReason.RECONCILE_NO_EXACT_ID.value)
    wallet_id = retained_evidence.wallet_id
    evidence = lookup_wallet_evidence(provider, wallet_id)
    if evidence is None:
        return mark_unknown(session, row, SetupReason.RECONCILE_NO_MATCH.value)
    if not (evidence_matches_identity(row, evidence) and _same_wallet(retained_evidence, evidence)):
        return mark_unknown(session, row, SetupReason.RECONCILE_WRONG_IDENTITY.value)
    if conflicting_binding(session, row.owner_id, row.agent_id, wallet_id) is not None:
        record_denial(session, row.owner_id, row.agent_id, "SAME_OWNER_CROSS_AGENT", {"wallet_id": wallet_id})
        return mark_unknown(session, row, SetupReason.CONFLICTING_WALLET.value)
    return bind_wallet(session, row, wallet_id,
                       {"owner_id": str(evidence.owner_id), "chain_type": evidence.chain_type,
                        "address": evidence.address}, SetupEventType.RECONCILED)
