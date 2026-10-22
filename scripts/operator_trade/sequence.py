"""The live four-transaction sequence: journal, sign, send once, receipt, next step.

The order is fixed: wrap MON to WMON, approve exactly the input, execute the merged direct-route
swap, revoke the approval to zero. Every send is preceded by an fsynced ``before_send`` record.
An unknown broadcast stops the run: the same step is never sent again. If the swap fails after the
approval succeeded, the revoke is attempted once and reported.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from eth_utils import keccak

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.journal import Journal
from scripts.operator_trade.plan import TradePlan
from scripts.operator_trade.preflight import Preflight, read_balance
from scripts.operator_trade.rpc import OperatorRpc
from scripts.operator_trade.trade_file import OperatorTrade
from scripts.operator_trade.transactions import UnsignedTransaction, build_unsigned

@dataclass(frozen=True)
class StepRecord:
    step: str
    nonce: int
    request_hash: str
    tx_hash: str
    receipt_block: int
    gas_used: int
    status: int


@dataclass(frozen=True)
class SequenceOutcome:
    ok: bool
    steps: tuple[StepRecord, ...]
    failed_step: str | None
    error_code: str | None
    wmon_after_wrap: int | None
    revoke_attempted: bool
    revoke_ok: bool | None
    revoke_error: str | None


class _StepStopped(Exception):
    """A stopped step. ``broadcast`` says whether the signed bytes may have reached the node."""

    def __init__(self, code: str, step: str, record: StepRecord | None = None,
                 broadcast: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.step = step
        self.record = record
        self.broadcast = broadcast


def _signed_transaction(reply: Any) -> str:
    if type(reply) is not dict:
        raise OperatorError("SIGNER_REPLY_INVALID")
    if "error" in reply:
        raise OperatorError("SIGNER_REFUSED")
    data = reply.get("data")
    if type(data) is not dict or set(data) != {"signed_transaction", "encoding"}:
        raise OperatorError("SIGNER_REPLY_INVALID")
    signed = data["signed_transaction"]
    if data["encoding"] != "rlp" or type(signed) is not str:
        raise OperatorError("SIGNER_REPLY_INVALID")
    if not signed.startswith("0x") or len(signed) <= 2 or len(signed) % 2 != 0:
        raise OperatorError("SIGNER_REPLY_INVALID")
    bytes.fromhex(signed[2:])
    return signed


def _reason(error: Exception) -> str:
    text = str(error)
    return text if 0 < len(text) <= 64 and text.replace("_", "").isalnum() else type(error).__name__.upper()


def _wait_for_receipt(rpc: OperatorRpc, tx_hash: str, trade: OperatorTrade, *, now: Callable[[], float],
                      sleep: Callable[[float], None]) -> dict[str, Any] | None:
    deadline = now() + trade.receipt_timeout_seconds
    while now() < deadline:
        receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
        if receipt is not None:
            return receipt
        sleep(trade.receipt_poll_seconds)
    return None


def _run_step(*, rpc: OperatorRpc, trade: OperatorTrade, transaction: UnsignedTransaction,
              signer_factory: Callable[[str, int], Any], journal: Journal, now: Callable[[], float],
              sleep: Callable[[float], None]) -> StepRecord:
    body = transaction.signer_body()
    request_hash = transaction.request_hash()
    journal.append({"event": "prepared", "step": transaction.step, "nonce": transaction.nonce,
                    "request_hash": request_hash, "liability": "NONE"})
    try:
        signer = signer_factory(transaction.step, transaction.nonce)
        reply = signer.rpc(trade.wallet_id, body)
    except Exception as error:  # noqa: BLE001 - a lost signature reply leaves an unknown signing state
        journal.append({"event": "sign_unknown", "step": transaction.step, "nonce": transaction.nonce,
                        "request_hash": request_hash, "liability": "SIGNING_UNKNOWN"})
        raise _StepStopped("SIGNER_REPLY_LOST", transaction.step) from error
    try:
        signed = _signed_transaction(reply)
    except OperatorError as error:
        journal.append({"event": "sign_refused", "step": transaction.step, "nonce": transaction.nonce,
                        "request_hash": request_hash, "reason": error.code, "liability": "NONE"})
        raise _StepStopped(error.code, transaction.step) from None
    signed_hash = "0x" + keccak(bytes.fromhex(signed[2:])).hex()
    journal.append({"event": "before_send", "step": transaction.step, "nonce": transaction.nonce,
                    "request_hash": request_hash, "tx_hash": signed_hash,
                    "signed_sha256": hashlib.sha256(bytes.fromhex(signed[2:])).hexdigest(),
                    "liability": "UNKNOWN"})
    try:
        returned = rpc.send_raw(signed)
    except Exception as error:  # noqa: BLE001 - after a possible dispatch every failure is unknown
        journal.append({"event": "unknown", "step": transaction.step, "nonce": transaction.nonce,
                        "request_hash": request_hash, "tx_hash": signed_hash,
                        "reason": _reason(error), "liability": "UNKNOWN"})
        raise _StepStopped("BROADCAST_UNKNOWN", transaction.step, broadcast=True) from None
    if type(returned) is not str or returned.lower() != signed_hash.lower():
        journal.append({"event": "unknown", "step": transaction.step, "nonce": transaction.nonce,
                        "request_hash": request_hash, "tx_hash": signed_hash,
                        "reason": "HASH_MISMATCH", "liability": "UNKNOWN"})
        raise _StepStopped("BROADCAST_UNKNOWN", transaction.step, broadcast=True)
    journal.append({"event": "sent", "step": transaction.step, "nonce": transaction.nonce,
                    "tx_hash": signed_hash, "liability": "UNKNOWN"})
    receipt = _wait_for_receipt(rpc, signed_hash, trade, now=now, sleep=sleep)
    if receipt is None:
        journal.append({"event": "receipt_timeout", "step": transaction.step, "nonce": transaction.nonce,
                        "tx_hash": signed_hash, "liability": "UNKNOWN"})
        raise _StepStopped("RECEIPT_TIMEOUT", transaction.step, broadcast=True)
    status = int(receipt["status"], 16)
    block = int(receipt["blockNumber"], 16)
    gas_used = int(receipt["gasUsed"], 16)
    journal.append({"event": "confirmed", "step": transaction.step, "nonce": transaction.nonce,
                    "tx_hash": signed_hash, "status": status, "block": block, "gas_used": gas_used,
                    "liability": "NONE"})
    record = StepRecord(step=transaction.step, nonce=transaction.nonce, request_hash=request_hash,
                        tx_hash=signed_hash, receipt_block=block, gas_used=gas_used, status=status)
    if status != 1:
        raise _StepStopped("RECEIPT_STATUS_FAILED", transaction.step, record, broadcast=True)
    return record


def execute(*, rpc: OperatorRpc, trade: OperatorTrade, plan: TradePlan, preflight: Preflight,
            signer_factory: Callable[[str, int], Any], journal: Journal, now: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep) -> SequenceOutcome:
    transactions = build_unsigned(trade, plan, preflight)
    steps: list[StepRecord] = []
    wmon_after_wrap: int | None = None
    for transaction in transactions:
        try:
            record = _run_step(rpc=rpc, trade=trade, transaction=transaction, signer_factory=signer_factory,
                               journal=journal, now=now, sleep=sleep)
        except _StepStopped as stopped:
            if stopped.record is not None:
                steps.append(stopped.record)
            if stopped.step == "swap":
                revoke = transactions[3]
                if not stopped.broadcast:
                    revoke = replace(revoke, nonce=transactions[2].nonce)
                    journal.append({"event": "revoke_reuses_swap_nonce", "step": "revoke",
                                    "nonce": revoke.nonce, "request_hash": revoke.request_hash(),
                                    "reason": stopped.code, "liability": "NONE"})
                ok: bool | None = None
                error_code: str | None = None
                try:
                    steps.append(_run_step(rpc=rpc, trade=trade, transaction=revoke,
                                           signer_factory=signer_factory, journal=journal, now=now, sleep=sleep))
                    ok = True
                except _StepStopped as revoke_stopped:
                    ok = False
                    error_code = revoke_stopped.code
                    if revoke_stopped.record is not None:
                        steps.append(revoke_stopped.record)
                return SequenceOutcome(ok=False, steps=tuple(steps), failed_step="swap",
                                       error_code=stopped.code, wmon_after_wrap=wmon_after_wrap,
                                       revoke_attempted=True, revoke_ok=ok, revoke_error=error_code)
            return SequenceOutcome(ok=False, steps=tuple(steps), failed_step=stopped.step,
                                   error_code=stopped.code, wmon_after_wrap=wmon_after_wrap,
                                   revoke_attempted=False, revoke_ok=None, revoke_error=None)
        steps.append(record)
        if transaction.step == "wrap":
            try:
                wmon_after_wrap = read_balance(rpc, trade.wmon, trade.wallet_address)
            except OperatorError:
                return SequenceOutcome(ok=False, steps=tuple(steps), failed_step="wrap",
                                       error_code="POST_WRAP_READ_FAILED", wmon_after_wrap=None,
                                       revoke_attempted=False, revoke_ok=None, revoke_error=None)
    return SequenceOutcome(ok=True, steps=tuple(steps), failed_step=None, error_code=None,
                           wmon_after_wrap=wmon_after_wrap, revoke_attempted=True, revoke_ok=True,
                           revoke_error=None)
