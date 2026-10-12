"""Public-seam tests for the injected Envio HyperSync source transport.

Everything is injected and offline: an authored native HyperSync response and an
authored client. No network, credential or provider is touched.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

import pytest

import _support as support
from edge_os_api.research_history import (
    CollectionLimits,
    EnvioHypersyncSource,
    HistoryRequest,
    ResponseSource,
    SourceCancelled,
    SourceContext,
    SourceContractError,
    SourceFailure,
    SourceTimeout,
    collect,
    normalize,
)

_NATIVE_FIELDS = ("address", "topic0", "topic1", "topic2", "data", "block_number", "block_hash",
                  "transaction_hash", "transaction_index", "log_index", "removed")


def _native_log(event: Mapping[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in _NATIVE_FIELDS if key in event}


def _native_page(from_block: int, next_block: int, logs: list[Any] | None, blocks: list[dict[str, Any]],
                 *, guard: dict[str, Any] | None = None, network: str | None = None,
                 chain_id: int | None = None, include_logs: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {"blocks": blocks}
    if include_logs:
        data["logs"] = logs if logs is not None else []
    response: dict[str, Any] = {
        "archive_height": support.ARCHIVE_HEIGHT,
        "next_block": next_block,
        "total_execution_time": 3,
        "data": data,
    }
    if guard is not None:
        response["rollback_guard"] = guard
    if network is not None:
        response["network"] = network
    if chain_id is not None:
        response["chain_id"] = chain_id
    return response


def _page1(logs: list[Any] | None = None, *, guard: dict[str, Any] | None = None,
           network: str | None = None, chain_id: int | None = None,
           blocks: list[dict[str, Any]] | None = None, include_logs: bool = True) -> dict[str, Any]:
    default_guard = {"block_number": 103, "timestamp": support.P1_LAST_TS, "hash": support.HASH_103,
                     "first_block_number": 100, "first_parent_hash": "0x" + "44" * 32}
    default_blocks = [{"number": 100, "timestamp": support.P1_FIRST_TS},
                      {"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS},
                      {"number": 103, "timestamp": support.P1_LAST_TS}]
    return _native_page(100, 104, logs if logs is not None else [_native_log(support.EVENT_QUOTE_IN)],
                        blocks if blocks is not None else default_blocks,
                        guard=guard if guard is not None else default_guard,
                        network=network, chain_id=chain_id, include_logs=include_logs)


def _page2(logs: list[Any] | None = None, *, guard: dict[str, Any] | None = None,
           network: str | None = None, chain_id: int | None = None,
           blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    default_guard = {"block_number": 110, "timestamp": support.P2_LAST_TS, "hash": support.HASH_110,
                     "first_block_number": 104, "first_parent_hash": support.HASH_103}
    default_blocks = [{"number": 104, "timestamp": support.P2_FIRST_TS},
                      {"number": support.EVENT_BASE_IN["block_number"], "timestamp": support.E2_TS},
                      {"number": 110, "timestamp": support.P2_LAST_TS}]
    return _native_page(104, 111, logs if logs is not None else [_native_log(support.EVENT_BASE_IN)],
                        blocks if blocks is not None else default_blocks,
                        guard=guard if guard is not None else default_guard,
                        network=network, chain_id=chain_id)


class FakeClient:
    """An authored native client. It records its calls and never retries."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls = 0
        self.requests: list[HistoryRequest] = []

    def query(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        self.calls += 1
        self.requests.append(request)
        if not self._responses:
            return None
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _limits(**overrides: Any) -> CollectionLimits:
    return CollectionLimits(**support.limits(**overrides))


def _scan() -> dict[str, int]:
    return dict(support.SCAN)


def _request() -> HistoryRequest:
    return HistoryRequest(provider="ENVIO_HYPERSYNC", address=support.POOL, topic0=support.TOPIC0,
                          from_block=100, to_block_exclusive=111, cursor_after=None, max_rows=64)


def test_transport_satisfies_the_response_source_protocol() -> None:
    source = EnvioHypersyncSource(FakeClient([]))
    assert isinstance(source, ResponseSource)


def test_complete_collection_frames_native_pages() -> None:
    client = FakeClient([_page1(), _page2()])
    source = EnvioHypersyncSource(client, clock=lambda: support.COLLECTED_AT)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "COMPLETE"
    assert result["page_count"] == 2
    assert result["row_count"] == 2
    assert [page["from_block"] for page in result["pages"]] == [100, 104]
    assert [page["next_block"] for page in result["pages"]] == [104, 111]
    assert client.calls == 2
    record = source.transport_record()
    assert record["attempted_requests"] == 2
    assert record["pages_framed"] == 2
    assert record["records_framed"] == 2
    assert record["missingness"] == {"order_field": 0, "identity_field": 0, "time_field": 0}
    assert record["units"] == "RAW_INTEGER_WORD"
    assert len(record["content_sha256"]) == 2


def test_transport_composes_into_normalize() -> None:
    source = EnvioHypersyncSource(FakeClient([_page1(), _page2()]), clock=lambda: support.COLLECTED_AT)
    collection = collect(support.profile(), source, _scan(), _limits())
    result = normalize(support.profile(), collection, support.evidence_facts())
    assert result["overall"] in ("QUALIFIED", "LIMITED")
    assert result["collection"]["status"] == "COMPLETE"
    assert len(result["trades"]) == 2


def test_page_content_hash_binds_the_page() -> None:
    client = FakeClient([_page1(), _page2()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    hashes = [page["sha256"] for page in result["pages"]]
    assert all(len(value) == 64 for value in hashes)
    assert hashes == source.transport_record()["content_sha256"]

    changed = support.EVENT_QUOTE_IN.copy()
    changed["data"] = "0x" + "00" * 32 + support.EVENT_QUOTE_IN["data"][2 + 64:]
    client2 = FakeClient([_page1(logs=[_native_log(changed)]), _page2()])
    result2 = collect(support.profile(), EnvioHypersyncSource(client2), _scan(), _limits())
    assert result2["pages"][0]["sha256"] != hashes[0]


def test_query_definition_is_echoed_from_the_request() -> None:
    client = FakeClient([_page1(), _page2()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["pages"][0]["from_block"] == 100
    assert client.requests[0].address == support.POOL
    assert client.requests[0].topic0 == support.TOPIC0
    assert client.requests[1].cursor_after == 104


def test_hexadecimal_quantities_are_accepted() -> None:
    def hexify(page: dict[str, Any]) -> dict[str, Any]:
        page = copy.deepcopy(page)
        page["next_block"] = hex(page["next_block"])
        for block in page["data"]["blocks"]:
            block["number"] = hex(block["number"])
            block["timestamp"] = hex(block["timestamp"])
        for log in page["data"]["logs"]:
            log["block_number"] = hex(log["block_number"])
        guard = page.get("rollback_guard")
        if guard is not None:
            guard["block_number"] = hex(guard["block_number"])
            guard["first_block_number"] = hex(guard["first_block_number"])
            guard["timestamp"] = hex(guard["timestamp"])
        return page

    client = FakeClient([hexify(_page1()), hexify(_page2())])
    result = collect(support.profile(), EnvioHypersyncSource(client), _scan(), _limits())
    assert result["status"] == "COMPLETE"
    assert result["row_count"] == 2


def test_contradictory_guard_bounds_are_refused() -> None:
    bad_guard = {"block_number": 102, "timestamp": support.P1_LAST_TS, "hash": support.HASH_103,
                 "first_block_number": 102, "first_parent_hash": "0x" + "44" * 32}
    client = FakeClient([_page1(guard=bad_guard), _page2()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "PROVIDER_ERROR"
    assert result["page_count"] == 0


def test_missing_logs_list_is_refused_not_proved_empty() -> None:
    client = FakeClient([_page1(include_logs=False), _page2()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "PROVIDER_ERROR"


def test_duplicate_conflicting_block_fact_is_refused() -> None:
    blocks = [{"number": 100, "timestamp": support.P1_FIRST_TS},
              {"number": 100, "timestamp": support.P1_FIRST_TS + 1},
              {"number": 103, "timestamp": support.P1_LAST_TS}]
    client = FakeClient([_page1(blocks=blocks), _page2()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "PROVIDER_ERROR"


def test_wrong_network_is_refused() -> None:
    bad = _page1(chain_id=1)
    source = EnvioHypersyncSource(FakeClient([bad]), context=SourceContext())
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "WRONG_NETWORK"
    assert source.transport_record()["attempted_requests"] == 1


def test_matching_network_echo_is_recorded() -> None:
    good = _page1(network="MONAD", chain_id=143)
    source = EnvioHypersyncSource(FakeClient([good]))
    source.next_response(_request())
    assert source.transport_record()["network_echo"] == "PRESENT"


def test_malformed_native_response_is_a_source_failure() -> None:
    source = EnvioHypersyncSource(FakeClient(["not-an-object"]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_page_facts_incomplete_is_refused() -> None:
    page = _page1(blocks=[])
    page.pop("rollback_guard")
    source = EnvioHypersyncSource(FakeClient([page]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "PAGE_FACTS_INCOMPLETE"


def test_missing_fields_are_counted_not_repaired() -> None:
    partial = _native_log(support.EVENT_QUOTE_IN)
    partial.pop("transaction_index")
    partial["block_number"] = 999  # no block timestamp for 999
    source = EnvioHypersyncSource(FakeClient([_page1(logs=[partial])]))
    source.next_response(_request())
    record = source.transport_record()["missingness"]
    assert record["order_field"] == 1
    assert record["time_field"] == 1


def test_client_failure_is_a_partial_result() -> None:
    client = FakeClient([SourceFailure("boom"), _page1(), _page2()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "PROVIDER_ERROR"
    assert result["source_invocations"]["measured_local_attempts"] == 1
    assert client.calls == 1


def test_client_timeout_and_cancel_are_partial() -> None:
    for error, reason in ((SourceTimeout("slow"), "TIMEOUT"), (SourceCancelled("stop"), "CANCELLED")):
        source = EnvioHypersyncSource(FakeClient([error]))
        result = collect(support.profile(), source, _scan(), _limits())
        assert result["status"] == "PARTIAL"
        assert result["stop_reason"] == reason


def test_rate_limit_is_one_attempt_no_retry() -> None:
    client = FakeClient([SourceFailure("429 rate limited"), _page1()])
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["stop_reason"] == "PROVIDER_ERROR"
    assert client.calls == 1
    assert source.transport_record()["attempted_requests"] == 1


def test_programmer_defect_from_the_client_propagates() -> None:
    source = EnvioHypersyncSource(FakeClient([ValueError("bug")]))
    with pytest.raises(ValueError):
        collect(support.profile(), source, _scan(), _limits())


def test_no_hidden_retry_when_pages_are_exhausted() -> None:
    client = FakeClient([_page1()])  # a single page, no completion
    source = EnvioHypersyncSource(client)
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "PARTIAL"
    assert client.calls == 2  # one page + one exhaustion probe
    assert source.transport_record()["attempted_requests"] == 2


def test_out_of_range_block_fact_is_refused() -> None:
    blocks = [{"number": 99, "timestamp": support.P1_FIRST_TS - 10},
              {"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS},
              {"number": 103, "timestamp": support.P1_LAST_TS}]
    source = EnvioHypersyncSource(FakeClient([_page1(blocks=blocks)]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "OUT_OF_RANGE_BLOCK_FACT"


def test_absent_boundary_block_fact_is_refused() -> None:
    blocks = [{"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS},
              {"number": 103, "timestamp": support.P1_LAST_TS}]
    source = EnvioHypersyncSource(FakeClient([_page1(blocks=blocks)]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "PAGE_FACTS_INCOMPLETE"


def test_absent_page_end_fact_is_refused() -> None:
    blocks = [{"number": 100, "timestamp": support.P1_FIRST_TS},
              {"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS}]
    source = EnvioHypersyncSource(FakeClient([_page1(blocks=blocks)]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "PAGE_FACTS_INCOMPLETE"


def test_page_past_the_requested_end_is_refused() -> None:
    page = _page1()
    page["next_block"] = 112
    page["rollback_guard"]["block_number"] = 111
    source = EnvioHypersyncSource(FakeClient([page]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "PAGE_BOUNDS_CONTRADICTED"


def test_reversed_page_is_refused() -> None:
    page = _page1()
    page["next_block"] = 100
    page["rollback_guard"]["block_number"] = 99
    source = EnvioHypersyncSource(FakeClient([page]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "PAGE_BOUNDS_CONTRADICTED"


def test_conflicting_guard_timestamp_is_refused() -> None:
    bad_guard = {"block_number": 103, "timestamp": support.P1_LAST_TS + 1000, "hash": support.HASH_103,
                 "first_block_number": 100, "first_parent_hash": "0x" + "44" * 32}
    source = EnvioHypersyncSource(FakeClient([_page1(guard=bad_guard), _page2()]))
    result = collect(support.profile(), source, _scan(), _limits())
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "PROVIDER_ERROR"
    assert result["page_count"] == 0


def test_conflicting_guard_hash_is_refused() -> None:
    blocks = [{"number": 100, "timestamp": support.P1_FIRST_TS},
              {"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS},
              {"number": 103, "timestamp": support.P1_LAST_TS, "hash": "0x" + "55" * 32}]
    source = EnvioHypersyncSource(FakeClient([_page1(blocks=blocks)]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "PAGE_FACTS_CONFLICT"


def test_malformed_guard_fact_is_refused_not_discarded() -> None:
    bad_guard = {"block_number": "not-a-number", "timestamp": support.P1_LAST_TS, "hash": support.HASH_103,
                 "first_block_number": 100, "first_parent_hash": "0x" + "44" * 32}
    source = EnvioHypersyncSource(FakeClient([_page1(guard=bad_guard)]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_non_mapping_guard_is_refused_not_discarded() -> None:
    page = _page1()
    page["rollback_guard"] = "not-an-object"
    source = EnvioHypersyncSource(FakeClient([page]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_malformed_chain_echo_is_refused_and_recorded_present() -> None:
    page = _page1(chain_id=True)
    source = EnvioHypersyncSource(FakeClient([page]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"
    assert source.transport_record()["network_echo"] == "PRESENT"


def test_malformed_block_timestamp_is_refused() -> None:
    blocks = [{"number": 100, "timestamp": support.P1_FIRST_TS},
              {"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS},
              {"number": 103, "timestamp": "not-a-number"}]
    source = EnvioHypersyncSource(FakeClient([_page1(blocks=blocks)]))
    with pytest.raises(SourceContractError) as raised:
        source.next_response(_request())
    assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"
