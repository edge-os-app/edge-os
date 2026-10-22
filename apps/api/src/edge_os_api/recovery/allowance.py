"""The allowance an approve -> swap -> revoke action may have left open. Pure, except one optional receipt read.

The original transaction journals each step in its own record (`approve`, `revoke`, and the swap at the top level).
`allowance_status` reads only those saved records. Anything short of a proved state is reported open: an approve that
may have been sent opens the allowance until a bound, successful revoke receipt closes it. A revoke that was never
sent, or whose result is unknown, is never hidden. A single-swap envelope has no allowance record (None).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

STEP_ORDER = ["approve", "swap", "revoke"]
# Approve stages that prove the approve was never signed or sent. Anything else after the signer call may have been.
_NOT_SENT = {None, "PREPARED", "REFUSED_UNSENT"}


def _record(envelope: Mapping[str, Any], step: str) -> Mapping[str, Any]:
    record = envelope.get(step)
    return record if isinstance(record, Mapping) else {}


def _reason(step: str, record: Mapping[str, Any]) -> str | None:
    reason = record.get("reason")
    return f"{step.upper()}:{reason}" if isinstance(reason, str) else None


def allowance_status(envelope: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The allowance state from the saved step records; None for an envelope without the three steps."""
    if not isinstance(envelope, Mapping) or envelope.get("steps") != STEP_ORDER:
        return None
    approve, revoke = _record(envelope, "approve"), _record(envelope, "revoke")
    view = {"token": approve.get("token"), "spender": approve.get("spender"), "approved_raw": approve.get("amount_raw"),
            "approve_stage": approve.get("stage"), "revoke_stage": revoke.get("stage")}
    if approve.get("stage") in _NOT_SENT:
        return {**view, "state": "NOT_APPROVED", "open": False, "reason": _reason("approve", approve)}
    if approve.get("stage") != "BROADCAST_RETURNED":
        return {**view, "state": "APPROVE_UNKNOWN", "open": True, "reason": _reason("approve", approve)}
    if revoke.get("stage") in (None, "NOT_ATTEMPTED", "PREPARED", "REFUSED_UNSENT"):
        state = "REVOKE_NOT_SENT"
    elif revoke.get("stage") == "BROADCAST_RETURNED":
        state = "REVOKE_UNCONFIRMED"  # sent with our own hash; only its receipt closes the allowance
    else:
        state = "REVOKE_UNKNOWN"
    return {**view, "state": state, "open": True, "reason": _reason("revoke", revoke)}


def read_revoke_receipt(envelope: Mapping[str, Any], observer: Any) -> dict[str, Any] | None:
    """Close an unconfirmed revoke only from its own bound receipt; every other reading leaves the allowance open."""
    from edge_os_api.execution.original_transaction import ReplyLost, RpcError, is_hash

    status = allowance_status(envelope)
    if status is None or status["state"] != "REVOKE_UNCONFIRMED":
        return status
    revoke = _record(envelope, "revoke")
    tx_hash, wallet, token = revoke.get("transaction_hash"), envelope.get("wallet_address"), revoke.get("token")
    if not (is_hash(tx_hash) and isinstance(wallet, str) and isinstance(token, str)):
        return status
    try:
        receipt = observer.call("eth_getTransactionReceipt", [tx_hash])
    except (ReplyLost, TimeoutError, OSError, RpcError):
        return status
    if not isinstance(receipt, Mapping):
        return status
    bound = (str(receipt.get("transactionHash") or "").lower() == tx_hash.lower()
             and str(receipt.get("from") or "").lower() == wallet.lower()
             and str(receipt.get("to") or "").lower() == token.lower())
    if not bound:
        return status
    if receipt.get("status") == "0x1":
        return {**status, "state": "CLOSED", "open": False}
    if receipt.get("status") == "0x0":
        return {**status, "state": "REVOKE_REVERTED", "open": True}
    return status
