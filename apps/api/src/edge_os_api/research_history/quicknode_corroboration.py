"""Injected QuickNode Monad JSON-RPC corroboration for retained history records.

The accepted P07 adapter needs an independent corroboration of the history records.
This module supplies that check over an injected QuickNode JSON-RPC client. The
client owns the endpoint and any key; this module reads no credential, opens no
socket and reaches no network. Tests inject an authored client that replays recorded
RPC results.

Corroboration is by *sample*: for a deterministic, caller-declared set of retained
records, fetch ``eth_getTransactionReceipt`` and prove the record's identity against
the receipt. A record is corroborated only when the receipt's transaction hash,
transaction index, block number, block hash and the matching log (address, topics,
data, log index, not removed) all agree. Any absent required fact, contradiction,
removed log, unidentifiable record, missing receipt or RPC failure is counted as a
mismatch and is never repaired. One RPC call is made per sample and there is no retry.

The served chain is the independent ``read_chain_id`` result, not a caller
assumption. A chain that is not Monad mainnet (143) yields ``class`` ``NONE`` with
``chain_verified`` false and no receipt calls.

The result matches the accepted ``evidence["corroboration"]`` shape (``class``,
``provider``, ``sample_size``, ``population_size``, ``mismatches``) plus portable
entries and counts. ``class`` is ``COMPLETE`` when every record was compared,
``SAMPLED`` when only part was, and ``NONE`` when there were no records or the chain
was not verified.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from edge_os_api.research_history.provider_transport import SourceCancelled, SourceFailure, SourceTimeout

QUICKNODE_PROVIDER = "QUICKNODE_JSON_RPC"
MONAD_NETWORK = "MONAD"
MONAD_CHAIN_ID = 143
RECEIPT_METHOD = "eth_getTransactionReceipt"


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _quantity(value: Any) -> int | None:
    """A numeric quantity: a non-negative integer, or a ``0x``/decimal string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = int(text, 16) if text[:2].lower() == "0x" else int(text, 10)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


@runtime_checkable
class QuickNodeRpcClient(Protocol):
    """The injected JSON-RPC client. One call per sample; it must not retry."""

    def call(self, method: str, params: Sequence[Any]) -> Any: ...


def read_chain_id(client: QuickNodeRpcClient) -> dict[str, Any]:
    """Read ``eth_chainId`` and classify the served network. One call, no retry."""
    result = client.call("eth_chainId", [])
    chain_id = _quantity(result)
    return {
        "method": "eth_chainId",
        "chain_id": chain_id,
        "network": MONAD_NETWORK if chain_id == MONAD_CHAIN_ID else None,
        "attempts": 1,
    }


def _sample_indices(population: int, sample_size: int) -> list[int]:
    """A deterministic spread of sample positions over the population."""
    if population <= 0 or sample_size <= 0:
        return []
    if sample_size >= population:
        return list(range(population))
    step = population / sample_size
    return sorted({int(index * step) for index in range(sample_size)})


def _record_topics(record: Mapping[str, Any]) -> list[str] | None:
    supplied = record.get("topics")
    if isinstance(supplied, list) and supplied and all(isinstance(topic, str) for topic in supplied):
        return list(supplied)
    topics = [record[key] for key in ("topic0", "topic1", "topic2") if isinstance(record.get(key), str)]
    return topics or None


def _identity(record: Any) -> str | None:
    if not isinstance(record, Mapping):
        return None
    block = record.get("block_number")
    tx_index = record.get("transaction_index")
    log_index = record.get("log_index")
    if not (_is_nonneg_int(block) and _is_nonneg_int(tx_index) and _is_nonneg_int(log_index)):
        return None
    return f"{MONAD_CHAIN_ID}:{block}:{tx_index}:{log_index}"


def _match_receipt(record: Mapping[str, Any], receipt: Any) -> str | None:
    """Return a mismatch reason, or None when the record's identity is corroborated.

    The receipt's top level and the selected log must both prove the transaction and
    block identity. A removed fact that is absent or not a boolean is missing evidence,
    never proof that the log is live.
    """
    want_topics = _record_topics(record)
    if (want_topics is None or not isinstance(record.get("address"), str)
            or not isinstance(record.get("transaction_hash"), str)
            or not isinstance(record.get("block_hash"), str)
            or not (_is_nonneg_int(record.get("block_number"))
                    and _is_nonneg_int(record.get("transaction_index"))
                    and _is_nonneg_int(record.get("log_index")))):
        return "RECORD_NOT_IDENTIFIABLE"
    if not isinstance(receipt, Mapping):
        return "RECEIPT_MALFORMED"
    tx_hash = receipt.get("transactionHash")
    tx_index = _quantity(receipt.get("transactionIndex"))
    block_number = _quantity(receipt.get("blockNumber"))
    block_hash = receipt.get("blockHash")
    logs = receipt.get("logs")
    if (not isinstance(tx_hash, str) or tx_index is None or block_number is None
            or not isinstance(block_hash, str) or not isinstance(logs, list)):
        return "RECEIPT_MISSING_FACT"
    if tx_hash != record["transaction_hash"] or tx_index != record["transaction_index"]:
        return "TRANSACTION_MISMATCH"
    if block_number != record["block_number"] or block_hash != record["block_hash"]:
        return "BLOCK_MISMATCH"
    for log in logs:
        if not isinstance(log, Mapping):
            return "RECEIPT_MALFORMED"
        if log.get("address") != record["address"]:
            continue
        log_tx_hash = log.get("transactionHash")
        log_tx_index = _quantity(log.get("transactionIndex"))
        log_block_number = _quantity(log.get("blockNumber"))
        log_block_hash = log.get("blockHash")
        if (not isinstance(log_tx_hash, str) or log_tx_index is None or log_block_number is None
                or not isinstance(log_block_hash, str)):
            return "RECEIPT_MISSING_FACT"
        if log_tx_hash != record["transaction_hash"] or log_tx_index != record["transaction_index"]:
            return "TRANSACTION_MISMATCH"
        if log_block_number != record["block_number"] or log_block_hash != record["block_hash"]:
            return "BLOCK_MISMATCH"
        topics = log.get("topics")
        if not isinstance(topics, list) or not all(isinstance(topic, str) for topic in topics):
            return "RECEIPT_MALFORMED"
        if topics != want_topics or log.get("data") != record.get("data"):
            continue
        if _quantity(log.get("logIndex")) != record["log_index"]:
            continue
        removed = log.get("removed")
        if not isinstance(removed, bool):
            return "RECEIPT_MISSING_FACT"
        return "LOG_REMOVED" if removed else None
    return "LOG_NOT_FOUND"


def corroborate_records(client: QuickNodeRpcClient, records: Sequence[Any], *,
                        population_size: int | None = None, sample_size: int = 8,
                        chain_id: int | None = None,
                        clock: Callable[[], str] = _utc_now) -> dict[str, Any]:
    """Corroborate a deterministic sample of retained records against QuickNode receipts.

    ``chain_id`` is the independent ``read_chain_id`` result. When it is not Monad mainnet
    the corroboration is ``NONE`` and no receipt is fetched.
    """
    population = len(records) if population_size is None else population_size
    if not _is_nonneg_int(population):
        raise ValueError("population_size must be a non-negative integer")
    indices = _sample_indices(population, sample_size)

    common = {
        "provider": QUICKNODE_PROVIDER,
        "chain_id": chain_id,
        "population_size": population,
        "collected_at_utc": clock(),
    }
    if chain_id != MONAD_CHAIN_ID:
        return {**common, "network": None, "chain_verified": False, "class": "NONE",
                "reason": "CHAIN_NOT_MONAD", "sample_size": 0, "mismatches": len(indices),
                "records": [], "missingness": {"unidentifiable": 0, "rpc_failed": 0, "not_present": 0},
                "attempted_requests": 0}

    entries: list[dict[str, Any]] = []
    mismatches = 0
    unidentifiable = 0
    rpc_failed = 0
    not_present = 0
    attempts = 0
    for index in indices:
        if index >= len(records):
            not_present += 1
            mismatches += 1
            entries.append({"index": index, "identity": None, "matched": False, "reason": "RECORD_NOT_PRESENT"})
            continue
        record = records[index]
        identity = _identity(record)
        tx_hash = record.get("transaction_hash") if isinstance(record, Mapping) else None
        if identity is None or not isinstance(tx_hash, str):
            unidentifiable += 1
            mismatches += 1
            entries.append({"index": index, "identity": identity, "matched": False, "reason": "RECORD_NOT_IDENTIFIABLE"})
            continue
        attempts += 1
        try:
            receipt = client.call(RECEIPT_METHOD, [tx_hash])
        except (SourceFailure, SourceTimeout, SourceCancelled, OSError):
            rpc_failed += 1
            mismatches += 1
            entries.append({"index": index, "identity": identity, "matched": False, "reason": "RPC_FAILED"})
            continue
        if receipt is None:
            mismatches += 1
            entries.append({"index": index, "identity": identity, "matched": False, "reason": "RECEIPT_MISSING"})
            continue
        reason = _match_receipt(record, receipt)
        if reason is None:
            entries.append({"index": index, "identity": identity, "matched": True, "reason": None})
        else:
            mismatches += 1
            entries.append({"index": index, "identity": identity, "matched": False, "reason": reason})

    if population == 0:
        class_ = "NONE"
    elif len(indices) >= population:
        class_ = "COMPLETE"
    else:
        class_ = "SAMPLED"

    return {**common, "network": MONAD_NETWORK, "chain_verified": True, "class": class_,
            "sample_size": len(indices), "mismatches": mismatches, "records": entries,
            "missingness": {"unidentifiable": unidentifiable, "rpc_failed": rpc_failed, "not_present": not_present},
            "attempted_requests": attempts}
