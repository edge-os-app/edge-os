"""Public-seam tests for the injected QuickNode corroboration.

Everything is injected and offline: authored records and an authored JSON-RPC client.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import _support as support
from edge_os_api.research_history import SourceFailure
from edge_os_api.research_history.quicknode_corroboration import corroborate_records, read_chain_id


def _record(index: int, event: Mapping[str, Any]) -> dict[str, Any]:
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


def _receipt_for(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "blockNumber": hex(event["block_number"]),
        "blockHash": event["block_hash"],
        "logs": [{
            "address": event["address"],
            "topics": [event["topic0"], event["topic1"], event["topic2"]],
            "data": event["data"],
            "logIndex": hex(event["log_index"]),
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


def test_read_chain_id_classifies_monad() -> None:
    result = read_chain_id(FakeRpc({}))
    assert result["chain_id"] == 143
    assert result["network"] == "MONAD"
    assert result["attempts"] == 1


def test_full_corroboration_is_complete() -> None:
    records = [_record(0, support.EVENT_QUOTE_IN), _record(1, support.EVENT_BASE_IN)]
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN),
                   support.EVENT_BASE_IN["transaction_hash"]: _receipt_for(support.EVENT_BASE_IN)})
    result = corroborate_records(rpc, records, sample_size=8)
    assert result["class"] == "COMPLETE"
    assert result["mismatches"] == 0
    assert result["sample_size"] == 2
    assert result["population_size"] == 2
    assert result["provider"] == "QUICKNODE_JSON_RPC"
    assert rpc.calls == 2


def test_sampled_corroboration_is_sampled() -> None:
    records = [_record(0, support.EVENT_QUOTE_IN), _record(1, support.EVENT_BASE_IN)]
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN)})
    result = corroborate_records(rpc, records, sample_size=1)
    assert result["class"] == "SAMPLED"
    assert result["sample_size"] == 1
    assert result["mismatches"] == 0


def test_corroboration_counts_mismatch_when_log_is_absent() -> None:
    records = [_record(0, support.EVENT_QUOTE_IN)]
    receipt = _receipt_for(support.EVENT_BASE_IN)  # wrong log
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, records, sample_size=1)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "LOG_NOT_FOUND"


def test_corroboration_mismatch_is_not_repaired() -> None:
    records = [_record(0, support.EVENT_QUOTE_IN)]
    receipt = _receipt_for(support.EVENT_QUOTE_IN)
    receipt["blockNumber"] = "0x2a"  # a different block
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: receipt})
    result = corroborate_records(rpc, records, sample_size=1)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "BLOCK_MISMATCH"


def test_corroboration_receipt_missing_is_a_mismatch() -> None:
    records = [_record(0, support.EVENT_QUOTE_IN)]
    result = corroborate_records(FakeRpc({}), records, sample_size=1)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECEIPT_MISSING"


def test_corroboration_rpc_failure_is_unresolved() -> None:
    class Broken:
        def call(self, method: str, params: Sequence[Any]) -> Any:
            raise SourceFailure("503")

    records = [_record(0, support.EVENT_QUOTE_IN)]
    result = corroborate_records(Broken(), records, sample_size=1)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RPC_FAILED"
    assert result["missingness"]["rpc_failed"] == 1


def test_empty_corroboration_is_none() -> None:
    result = corroborate_records(FakeRpc({}), [], sample_size=8)
    assert result["class"] == "NONE"
    assert result["sample_size"] == 0
    assert result["population_size"] == 0


def test_unidentifiable_record_counts_as_mismatch() -> None:
    records = [{"address": support.POOL}]
    result = corroborate_records(FakeRpc({}), records, sample_size=1)
    assert result["mismatches"] == 1
    assert result["records"][0]["reason"] == "RECORD_NOT_IDENTIFIABLE"


def test_corroboration_makes_one_call_per_identified_sample() -> None:
    records = [_record(0, support.EVENT_QUOTE_IN), _record(1, support.EVENT_BASE_IN)]
    rpc = FakeRpc({support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN),
                   support.EVENT_BASE_IN["transaction_hash"]: _receipt_for(support.EVENT_BASE_IN)})
    result = corroborate_records(rpc, records, sample_size=8)
    assert result["attempted_requests"] == 2
    assert rpc.calls == 2
