"""Injected QuickNode Monad JSON-RPC corroboration for retained history records.

The accepted P07 adapter needs an independent corroboration of the history records.
This module supplies that check over an injected QuickNode JSON-RPC client. The
client owns the endpoint and any API key; this module reads no credential, opens no
socket and reaches no network. Tests inject an authored client that replays recorded
RPC results.

Corroboration is by *sample*: for a deterministic, caller-declared set of retained
records, fetch ``eth_getTransactionReceipt`` and check that the record's log appears
in the receipt with the same address, topics, data, block number and position. A
record that cannot be identified, a missing receipt, a log that is absent from its
receipt and a block disagreement are each counted as a mismatch, never repaired. One
RPC call is made per sample and there is no retry.

The result matches the accepted ``evidence["corroboration"]`` shape
(``class``, ``provider``, ``sample_size``, ``population_size``, ``mismatches``) plus
portable entries and counts. ``class`` is ``COMPLETE`` when every record was
compared, ``SAMPLED`` when only part was, and ``NONE`` when there were no records.
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


@runtime_checkable
class QuickNodeRpcClient(Protocol):
    """The injected JSON-RPC client. One call per sample; it must not retry."""

    def call(self, method: str, params: Sequence[Any]) -> Any: ...


def read_chain_id(client: QuickNodeRpcClient) -> dict[str, Any]:
    """Read ``eth_chainId`` and classify the served network. One call, no retry."""
    result = client.call("eth_chainId", [])
    chain_id: int | None = None
    if isinstance(result, str):
        try:
            chain_id = int(result, 16)
        except ValueError:
            chain_id = None
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


def _topics(record: Mapping[str, Any]) -> list[str]:
    if isinstance(record.get("topics"), Sequence) and not isinstance(record["topics"], (str, bytes)):
        return [topic for topic in record["topics"] if isinstance(topic, str)]
    return [record[key] for key in ("topic0", "topic1", "topic2") if isinstance(record.get(key), str)]


def _hex_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16)
        except ValueError:
            return None
    return None


def _match_receipt(record: Mapping[str, Any], receipt: Mapping[str, Any]) -> str | None:
    """Return a mismatch reason, or None when the record's log is corroborated."""
    try:
        want_topics = _topics(record)
        want_data = record.get("data")
        want_index = _hex_int(record.get("log_index"))
    except (TypeError, AttributeError):
        return "RECORD_NOT_IDENTIFIABLE"
    logs = receipt.get("logs")
    if not isinstance(logs, Sequence) or isinstance(logs, (str, bytes)):
        return "RECEIPT_MALFORMED"
    for log in logs:
        if not isinstance(log, Mapping):
            continue
        if log.get("address") != record.get("address"):
            continue
        if list(log.get("topics") or []) != want_topics:
            continue
        if log.get("data") != want_data:
            continue
        if want_index is not None and _hex_int(log.get("logIndex")) != want_index:
            continue
        block_number = _hex_int(receipt.get("blockNumber"))
        if _hex_int(record.get("block_number")) is not None and block_number != _hex_int(record.get("block_number")):
            return "BLOCK_MISMATCH"
        block_hash = receipt.get("blockHash")
        if isinstance(record.get("block_hash"), str) and block_hash is not None and block_hash != record.get("block_hash"):
            return "BLOCK_MISMATCH"
        return None
    return "LOG_NOT_FOUND"


def _identity(record: Any) -> str | None:
    if not isinstance(record, Mapping):
        return None
    block = record.get("block_number")
    tx_index = record.get("transaction_index")
    log_index = record.get("log_index")
    if block is None or tx_index is None or log_index is None:
        return None
    return f"143:{block}:{tx_index}:{log_index}"


def corroborate_records(client: QuickNodeRpcClient, records: Sequence[Any], *,
                        population_size: int | None = None, sample_size: int = 8,
                        chain_id: int | None = None,
                        clock: Callable[[], str] = _utc_now) -> dict[str, Any]:
    """Corroborate a deterministic sample of retained records against QuickNode receipts."""
    population = len(records) if population_size is None else population_size
    if not isinstance(population, int) or isinstance(population, bool) or population < 0:
        raise ValueError("population_size must be a non-negative integer")
    indices = _sample_indices(population, sample_size)

    entries: list[dict[str, Any]] = []
    mismatches = 0
    unidentifiable = 0
    rpc_failed = 0
    attempts = 0
    for index in indices:
        if index >= len(records):
            entry = {"index": index, "identity": None, "matched": False, "reason": "RECORD_NOT_PRESENT"}
            mismatches += 1
            entries.append(entry)
            continue
        record = records[index]
        identity = _identity(record)
        tx_hash = record.get("transaction_hash") if isinstance(record, Mapping) else None
        if identity is None or not isinstance(tx_hash, str):
            unidentifiable += 1
            mismatches += 1
            entries.append({"index": index, "identity": identity, "matched": False,
                            "reason": "RECORD_NOT_IDENTIFIABLE"})
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
        if not isinstance(receipt, Mapping):
            mismatches += 1
            entries.append({"index": index, "identity": identity, "matched": False, "reason": "RECEIPT_MALFORMED"})
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

    return {
        "provider": QUICKNODE_PROVIDER,
        "network": MONAD_NETWORK,
        "chain_id": chain_id,
        "class": class_,
        "sample_size": len(indices),
        "population_size": population,
        "mismatches": mismatches,
        "records": entries,
        "missingness": {"unidentifiable": unidentifiable, "rpc_failed": rpc_failed,
                        "not_present": sum(1 for entry in entries if entry["reason"] == "RECORD_NOT_PRESENT")},
        "attempted_requests": attempts,
        "collected_at_utc": clock(),
    }
