"""Public-seam tests for the injected QuickNode corroboration.

Everything is injected and offline: authored records and an authored JSON-RPC client.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import _support as support
from edge_os_api.research_history import SourceFailure
from edge_os_api.research_history.quicknode_corroboration import corroborate_records, read_chain_id

MONAD = 143


def _record(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "address": event["address"],
        "topic0": event["topic0"],
        "topic1": event["topic1"],
        "topic2": event["topic2"],
        "data": event["data"],
        "block_number": event["block_number"],
        "block_hash": event["block_hash"],
        "transaction_hash": event["transaction_hash"],
        "transaction_index": event["transaction_index"],
        "log_index": event["log_index"],
    }


def _receipt_for(event: Mapping[str, Any], *, removed: bool = False) -> dict[str, Any]:
    return {
        "transactionHash": event["transaction_hash"],
        "transactionIndex": hex(event["transaction_index"]),
        "blockNumber": hex(event["block_number"]),
        "blockHash": event["block_hash"],
        "logs": [{
            "address": event["address"],
            "topics": [event["topic0"], event["topic1"], event["topic2"]],
            "data": event["data"],
            "logIndex": hex(event["log_index"]),
            "removed": removed,
        }],
    }


class FakeRpc:
    def __init__(self, mapping: Mapping[str, Any]) -> None:
        self._mapping = mapping
        self.calls = 0

    def call(self, method: str, params: Sequence[Any]) -> Any:
        self.calls += 1
        if method == "eth_chainId":
            return "0x8f"
        return self._mapping.get(params[0])


def _records() -> list[dict[str, Any]]:
    return [_record(support.EVENT_QUOTE_IN), _record(support.EVENT_BASE_IN)]


def test_read_chain_id_classifies_monad() -> None:
    result = read_chain_id(FakeRpc({}))
    assert result["chain_id"] == MONAD
    assert result["network"] == "MONAD"
    assert result["attempts"] == 1


def test_full_corroboration_is_complete() -> None:
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN),
                   support.EVENT_BASE_IN["transaction_hash"]: _receipt_for(support.EVENT_BASE_IN)})
    result = corroborate_records(rpc, _records(), sample_size=8, chain_id=MONAD)
    assert result["class"] == "COMPLETE"
    assert result["mismatches"] == 0
    assert result["sample_size"] == 2
    assert result["population_size"] == 2
    assert result["chain_verified"] is True
    assert rpc.calls == 2


def test_sampled_corroboration_is_sampled() -> None:
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN)})
    result = corroborate_records(rpc, _records(), sample_size=1, chain_id=MONAD)
    assert result["class"] == "SAMPLED"
    assert result["sample_size"] == 1
    assert result["mismatches"] == 0


def test_wrong_chain_is_not_verified_and_fetches_nothing() -> None:
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN)})
    result = corroborate_records(rpc, _records(), sample_size=8, chain_id=1)
    assert result["class"] == "NONE"
    assert result["chain_verified"] is False
    assert result["reason"] == "CHAIN_NOT_MONAD"
    assert rpc.calls == 0


def test_wrong_transaction_hash_is_a_mismatch() -> None:
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt["transactionHash"] = "0x" + "de" * 32
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "TRANSACTION_MISMATCH"


def test_wrong_transaction_index_is_a_mismatch() -> None:
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt["transactionIndex"] = hex(9)
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "TRANSACTION_MISMATCH"


def test_corroboration_counts_mismatch_when_log_is_absent() -> None:
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt["logs"][0]["address"] = "0x" + "ee" * 20
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "LOG_NOT_FOUND"


def test_missing_receipt_block_hash_is_a_missing_fact() -> None:
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt.pop("blockHash")
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECEIPT_MISSING_FACT"


def test_removed_log_is_not_a_match() -> None:
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN, removed=True)})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "LOG_REMOVED"


def test_malformed_topics_do_not_escape_as_an_exception() -> None:
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt["logs"][0]["topics"] = 7
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECEIPT_MALFORMED"


def test_corroboration_mismatch_is_not_repaired() -> None:
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt["blockNumber"] = "0x2a"
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "BLOCK_MISMATCH"


def test_corroboration_receipt_missing_is_a_mismatch() -> None:
    result = corroborate_records(FakeRpc({}), [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECEIPT_MISSING"


def test_corroboration_rpc_failure_is_unresolved() -> None:
    class Broken:
        def call(self, method: str, params: Sequence[Any]) -> Any:
            raise SourceFailure("503")

    result = corroborate_records(Broken(), [_record(support.EVENT_QUOTE_IN)], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RPC_FAILED"
    assert result["missingness"]["rpc_failed"] == 1


def test_empty_corroboration_is_none() -> None:
    result = corroborate_records(FakeRpc({}), [], sample_size=8, chain_id=MONAD)
    assert result["class"] == "NONE"
    assert result["sample_size"] == 0
    assert result["population_size"] == 0


def test_unidentifiable_record_counts_as_mismatch() -> None:
    result = corroborate_records(FakeRpc({}), [{"address": support.POOL}], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECORD_NOT_IDENTIFIABLE"


def test_invalid_numeric_identity_is_not_identifiable() -> None:
    record = _record(support.EVENT_QUOTE_IN)
    record["log_index"] = -1
    result = corroborate_records(FakeRpc({}), [record], sample_size=1, chain_id=MONAD)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECORD_NOT_IDENTIFIABLE"


def test_corroboration_makes_one_call_per_identified_sample() -> None:
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN),
                   support.EVENT_BASE_IN["transaction_hash"]: _receipt_for(support.EVENT_BASE_IN)})
    result = corroborate_records(rpc, _records(), sample_size=8, chain_id=MONAD)
    assert result["attempted_requests"] == 2
    assert rpc.calls == 2