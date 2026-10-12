"""Native-source history collection through the accepted P07 transport (#58 SOURCE-LOCAL).

A `RECORDED_NATIVE_RESPONSE` source holds native Envio HyperSync pages and QuickNode JSON-RPC results. This module
replays them with offline recorded clients through the accepted P07 seams unchanged: `EnvioHypersyncSource` +
`collect` for history, `read_chain_id` + `corroborate_records` for independent corroboration, then `normalize`.

Every injected client call is guarded first: cancellation, the job deadline and the declared request budget are
checked before the call, and a refused call is never made. A made call counts toward usage even when it fails, and
nothing is retried. Facts P07 does not read (decimals, pool tokens, fees, finality, delivery records) stay the
recording's declarations and are labelled so. The clients open no socket and read no credential or environment value.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from edge_os_api.research_history import (
    CollectionLimits,
    EnvioHypersyncSource,
    HistoryRequest,
    SourceCancelled,
    SourceFailure,
    SourceTimeout,
    collect,
    corroborate_records,
    normalize,
    read_chain_id,
)
from edge_os_api.research_history.qualification_engine import epoch

ENVIO = "ENVIO_HYPERSYNC"
QUICKNODE = "QUICKNODE_JSON_RPC"
MONAD_CHAIN_ID = 143
# Facts the application computes through the transport, and facts the recording only declares.
EVIDENCE_BASIS = {
    "history_pages": "ENVIO_TRANSPORT_OVER_RECORDED_RESPONSES",
    "chain_id": "CHECKED_AGAINST_RECORDED_RPC",
    "corroboration": "COMPUTED_FROM_RECORDED_RPC",
    "decimals": "RECORDED_DECLARATION",
    "pool_tokens": "RECORDED_DECLARATION",
    "pool_venue": "RECORDED_DECLARATION",
    "fee_transfer_semantics": "RECORDED_DECLARATION",
    "finality_at_collection": "RECORDED_DECLARATION",
    "delivery_records": "RECORDED_DECLARATION",
    "feasibility_claim": "RECORDED_DECLARATION",
}


class RequestBudget:
    """The job's declared provider-request reservation, shared by every client call of one collection."""

    def __init__(self, limit: int, cancelled: Callable[[], bool], deadline_utc: str | None,
                 clock: Callable[[], str]) -> None:
        self._limit = limit
        self._cancelled = cancelled
        self._deadline = None if deadline_utc is None else epoch(deadline_utc)
        self._clock = clock
        self.calls = {ENVIO: 0, QUICKNODE: 0}

    @property
    def remaining(self) -> int:
        return self._limit - sum(self.calls.values())

    def admit(self, provider: str) -> None:
        """Check before a call; count the call once admitted. A refused call is never made or counted."""
        if self._cancelled():
            raise SourceCancelled("cancellation requested before the next provider call")
        if self._deadline is not None and epoch(self._clock()) >= self._deadline:
            raise SourceTimeout("the job deadline passed before the next provider call")
        if self.remaining < 1:
            raise SourceFailure("REQUEST_BUDGET_EXHAUSTED: the declared provider requests are used")
        self.calls[provider] += 1


class RecordedEnvioClient:
    """An `EnvioQueryClient` that serves recorded native pages in order. `{"fault": ...}` raises that failure."""

    def __init__(self, pages: list[Any], budget: RequestBudget) -> None:
        self._pages = list(pages)
        self._budget = budget
        self._index = 0

    def query(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        self._budget.admit(ENVIO)
        if self._index >= len(self._pages):
            return None
        page = self._pages[self._index]
        self._index += 1
        fault = page.get("fault") if isinstance(page, Mapping) else None
        if fault == "SOURCE_FAILURE":
            raise SourceFailure("recorded provider failure")
        if fault == "SOURCE_TIMEOUT":
            raise SourceTimeout("recorded provider timeout")
        if fault is not None:
            raise ValueError(f"unknown recorded fault {fault!r}")
        return page


class RecordedQuickNodeClient:
    """A `QuickNodeRpcClient` that answers `eth_chainId` and `eth_getTransactionReceipt` from the recording."""

    def __init__(self, recording: Mapping[str, Any], budget: RequestBudget) -> None:
        self._recording = recording
        self._budget = budget

    def call(self, method: str, params: Any) -> Any:
        self._budget.admit(QUICKNODE)
        if method == "eth_chainId":
            return self._recording["eth_chainId"]
        if method == "eth_getTransactionReceipt":
            tx_hash = params[0]
            if self._recording.get("rpc_faults", {}).get(tx_hash) == "RPC_FAILED":
                raise SourceFailure("recorded RPC failure")
            return self._recording["receipts"].get(tx_hash)
        raise ValueError(f"the recording has no {method!r} method")


def _skipped_corroboration(reason: str, population: int, clock: Callable[[], str]) -> dict[str, Any]:
    return {"provider": QUICKNODE, "chain_id": None, "population_size": population, "collected_at_utc": clock(),
            "network": None, "chain_verified": False, "class": "NONE", "reason": reason, "sample_size": 0,
            "mismatches": 0, "records": [], "missingness": {"unidentifiable": 0, "rpc_failed": 0, "not_present": 0},
            "attempted_requests": 0}


def collect_native(source: Mapping[str, Any], bounds: Mapping[str, Any], deadline_utc: str | None,
                   cancelled: Callable[[], bool], clock: Callable[[], str]) -> tuple[dict[str, Any], dict[str, Any],
                                                                                    dict[str, Any]]:
    """Collect, corroborate and qualify one native recording. Returns the collection, the P07 normalized result and
    the transport facts. P07 partial results return; a programmer defect propagates."""
    budget = RequestBudget(bounds["provider_requests"], cancelled, deadline_utc, clock)
    envio = EnvioHypersyncSource(RecordedEnvioClient(source["envio_pages"], budget), clock=clock)
    limits = CollectionLimits(max_pages=bounds["max_pages"], max_rows=bounds["max_rows"],
                              max_bytes=bounds["max_bytes"], deadline_utc=deadline_utc)
    collection = collect(source["profile"], envio, source["scan"], limits, clock=clock)
    records = collection["records"]
    chain_read: dict[str, Any] | None = None
    if not records:
        corroboration = _skipped_corroboration("NO_RECORDS", 0, clock)
    elif budget.remaining < 2:
        corroboration = _skipped_corroboration("REQUEST_BUDGET_EXHAUSTED", len(records), clock)
    else:
        rpc = RecordedQuickNodeClient(source["quicknode"], budget)
        before = budget.calls[QUICKNODE]
        try:
            chain_read = read_chain_id(rpc)
        except (SourceCancelled, SourceTimeout, SourceFailure, OSError) as error:
            # A refused call was never made; a made call that failed still counts.
            chain_read = {"method": "eth_chainId", "chain_id": None, "network": None,
                          "attempts": budget.calls[QUICKNODE] - before, "failure": type(error).__name__}
        sample = min(int(source["corroboration_sample_size"]), budget.remaining)
        if chain_read["chain_id"] is None:
            corroboration = _skipped_corroboration("CHAIN_READ_FAILED", len(records), clock)
        else:
            corroboration = corroborate_records(rpc, records, sample_size=sample, chain_id=chain_read["chain_id"],
                                                clock=clock)
    verified = chain_read is not None and chain_read["chain_id"] == MONAD_CHAIN_ID
    evidence = {**source["provider_facts"],
                "chain_id_source": "PROVIDER_READ" if verified else "UNKNOWN",
                "corroboration": {key: corroboration[key]
                                  for key in ("class", "provider", "sample_size", "population_size", "mismatches")}}
    normalized = normalize(source["profile"], collection, evidence)
    # `client_calls` counts made calls only; the transport's own `attempted_requests` also counts a refused step.
    transport = {"envio": envio.transport_record(), "chain_read": chain_read, "corroboration": corroboration,
                 "client_calls": dict(budget.calls), "request_budget": bounds["provider_requests"],
                 "clients": "RECORDED_NATIVE_CLIENTS_LOCAL", "evidence_basis": dict(EVIDENCE_BASIS)}
    return collection, normalized, transport
