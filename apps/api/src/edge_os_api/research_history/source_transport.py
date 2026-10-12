"""Injected Envio HyperSync history transport.

The accepted collector takes a caller-supplied ``ResponseSource``. This module
supplies one *actual-source* implementation, ``EnvioHypersyncSource``, over an
injected client seam. The client owns the endpoint and the bearer token; this
module never reads a credential, opens a socket or reaches a network. Tests inject
an authored client that replays recorded native responses.

The transport frames one native Envio HyperSync ``QueryResponse`` into the
adapter's recorded-response shape and records the facts the accepted collector
retains: the request and cursor identity, the page identity, the page content
hash, the collection time, the block/log ordering fields, the raw amount units
and any missing order, identity or time field. It does not invent a page, a
timestamp or a value the response does not carry.

Pinned native shape (documentation 2026-10-12; not verified against a live
response): ``{archive_height, next_block, total_execution_time, data:{blocks,
logs}, rollback_guard:{block_number, timestamp, hash, first_block_number,
first_parent_hash}}``. ``next_block`` is the block after the last served block.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from edge_os_api.research_history.provider_transport import (
    HistoryRequest,
    SourceFailure,
)
from edge_os_api.research_history.qualification_engine import raw_bytes

ENVIO_PROVIDER = "ENVIO_HYPERSYNC"
ENVIO_PROVIDER_VERSION = "envio-hypersync/1"
ENVIO_ENDPOINT = "https://monad.hypersync.xyz"
MONAD_NETWORK = "MONAD"
MONAD_CHAIN_ID = 143

LOG_FIELDS = ("address", "topic0", "topic1", "topic2", "topic3", "data", "block_number",
              "block_hash", "transaction_hash", "transaction_index", "log_index", "removed")
ORDER_FIELDS = ("block_number", "transaction_index", "log_index")
IDENTITY_FIELDS = ("address", "transaction_hash")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _hex_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


class SourceContractError(SourceFailure):
    """The provider response violates the pinned transport contract.

    A subclass of the accepted ``SourceFailure`` so the collector records a partial
    ``PROVIDER_ERROR`` result. The ``code`` lets a caller or test branch without
    reading message text. It is raised before the response is framed, so no page,
    row or byte of a refused response is retained.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SourceContext:
    """The served network, chain and provider identity. Owned by the caller."""

    network: str = MONAD_NETWORK
    chain_id: int = MONAD_CHAIN_ID
    provider: str = ENVIO_PROVIDER
    provider_version: str = ENVIO_PROVIDER_VERSION
    endpoint: str = ENVIO_ENDPOINT

    def validate(self) -> None:
        if not isinstance(self.network, str) or not self.network:
            raise SourceContractError("CONTEXT_INVALID", "network must be non-empty text")
        if not _is_nonneg_int(self.chain_id) or self.chain_id == 0:
            raise SourceContractError("CONTEXT_INVALID", "chain_id must be a positive integer")
        if self.provider != ENVIO_PROVIDER:
            raise SourceContractError("CONTEXT_INVALID", f"provider must be {ENVIO_PROVIDER}")
        if not isinstance(self.provider_version, str) or not self.provider_version:
            raise SourceContractError("CONTEXT_INVALID", "provider_version must be non-empty text")


@runtime_checkable
class EnvioQueryClient(Protocol):
    """The injected native HyperSync client. One call per ``query``.

    The client owns the endpoint and the bearer token. It returns a native
    ``QueryResponse`` mapping, or ``None`` when the scan is exhausted. It raises
    ``SourceFailure`` for an expected provider failure, ``SourceTimeout`` for a
    time bound, ``SourceCancelled`` for cancellation and ``OSError`` for a
    transport failure. It must not retry.
    """

    def query(self, request: HistoryRequest) -> Mapping[str, Any] | None: ...


class EnvioHypersyncSource:
    """A ``ResponseSource`` that frames native HyperSync pages over an injected client."""

    def __init__(self, client: EnvioQueryClient, *, context: SourceContext | None = None,
                 clock: Callable[[], str] = _utc_now) -> None:
        self._context = context or SourceContext()
        self._context.validate()
        self._client = client
        self._clock = clock
        self._attempted = 0
        self._pages = 0
        self._records = 0
        self._missing_order = 0
        self._missing_identity = 0
        self._missing_time = 0
        self._network_echo = "ABSENT"
        self._content_hashes: list[str] = []

    @property
    def context(self) -> SourceContext:
        return self._context

    def transport_record(self) -> dict[str, Any]:
        """The transport facts of every attempt so far, for the caller's evidence.

        The accepted collector retains the request/cursor/page/hash/served facts in
        its own result. This record adds the framing facts the collector does not
        keep: the attempted request count and the missingness counts.
        """
        return {
            "provider": self._context.provider,
            "provider_version": self._context.provider_version,
            "endpoint": self._context.endpoint,
            "network": self._context.network,
            "chain_id": self._context.chain_id,
            "network_echo": self._network_echo,
            "ordering": list(ORDER_FIELDS),
            "units": "RAW_INTEGER_WORD",
            "attempted_requests": self._attempted,
            "pages_framed": self._pages,
            "records_framed": self._records,
            "content_sha256": list(self._content_hashes),
            "missingness": {"order_field": self._missing_order,
                            "identity_field": self._missing_identity,
                            "time_field": self._missing_time},
        }

    def next_response(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        # The attempted request is counted before the client call, so a call that
        # raises still counts. There is exactly one client call per step and no retry.
        self._attempted += 1
        raw = self._client.query(request)
        if raw is None:
            return None
        return self._frame(request, raw)

    def _check_network(self, raw: Mapping[str, Any]) -> None:
        network = raw.get("network")
        chain_id = raw.get("chain_id")
        if network is None and chain_id is None:
            return
        self._network_echo = "PRESENT"
        if network is not None and network != self._context.network:
            raise SourceContractError("WRONG_NETWORK", f"expected {self._context.network}, got {network!r}")
        if chain_id is not None and chain_id != self._context.chain_id:
            raise SourceContractError("WRONG_NETWORK", f"expected chain {self._context.chain_id}, got {chain_id!r}")

    def _block_index(self, data: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
        index: dict[int, Mapping[str, Any]] = {}
        blocks = data.get("blocks", [])
        if isinstance(blocks, Sequence) and not isinstance(blocks, (str, bytes)):
            for block in blocks:
                if isinstance(block, Mapping) and _is_nonneg_int(block.get("number")):
                    index[block["number"]] = block
        return index

    def _frame(self, request: HistoryRequest, raw: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise SourceContractError("MALFORMED_PROVIDER_RESPONSE", "response is not an object")
        self._check_network(raw)

        data = raw.get("data")
        if not isinstance(data, Mapping):
            raise SourceContractError("MALFORMED_PROVIDER_RESPONSE", "data is not an object")
        logs = data.get("logs", [])
        if not isinstance(logs, Sequence) or isinstance(logs, (str, bytes)):
            raise SourceContractError("MALFORMED_PROVIDER_RESPONSE", "data.logs is not a list")

        next_block = raw.get("next_block")
        if not _is_nonneg_int(next_block) or next_block <= 0:
            raise SourceContractError("MALFORMED_PROVIDER_RESPONSE", "next_block must be a positive integer")

        blocks = self._block_index(data)
        from_block = request.cursor_after if request.cursor_after is not None else request.from_block
        guard = raw.get("rollback_guard")
        guard = guard if isinstance(guard, Mapping) else {}

        first_block = blocks.get(from_block)
        first_ts = first_block.get("timestamp") if isinstance(first_block, Mapping) else None
        last_ts = guard.get("timestamp")
        if not _is_nonneg_int(last_ts):
            last_block = blocks.get(next_block - 1)
            last_ts = last_block.get("timestamp") if isinstance(last_block, Mapping) else None
        if not _is_nonneg_int(first_ts) or not _is_nonneg_int(last_ts):
            raise SourceContractError("PAGE_FACTS_INCOMPLETE",
                                      "the response does not prove the page edge timestamps")
        if last_ts < first_ts:
            raise SourceContractError("PAGE_FACTS_INCOMPLETE", "page edge timestamps fall")

        events = self._frame_logs(logs, blocks)
        content_sha256 = self._content_sha256(from_block, next_block, events)
        self._content_hashes.append(content_sha256)
        self._pages += 1

        page = {
            "page_id": f"envio:{from_block}-{next_block}",
            "from_block": from_block,
            "next_block": next_block,
            "sha256": content_sha256,
            "first_block_timestamp": first_ts,
            "last_block_timestamp": last_ts,
        }
        first_parent_hash = _hex_text(guard.get("first_parent_hash"))
        last_block_hash = _hex_text(guard.get("hash")) or _hex_text(
            (blocks.get(next_block - 1) or {}).get("hash") if isinstance(blocks.get(next_block - 1), Mapping) else None)
        if first_parent_hash is not None:
            page["first_parent_hash"] = first_parent_hash
        if last_block_hash is not None:
            page["last_block_hash"] = last_block_hash

        query = {
            "address": request.address,
            "topic0": request.topic0,
            "from_block": request.from_block,
            "to_block_exclusive": request.to_block_exclusive,
        }
        return {
            "provider": self._context.provider,
            "provider_version": self._context.provider_version,
            "served_utc": self._clock(),
            "query": query,
            "page": page,
            "cursor": {"before": request.cursor_after, "after": next_block},
            "complete": next_block >= request.to_block_exclusive,
            "events": events,
        }

    def _frame_logs(self, logs: Sequence[Any], blocks: Mapping[int, Mapping[str, Any]]) -> list[Any]:
        framed: list[Any] = []
        for log in logs:
            if not isinstance(log, Mapping):
                framed.append(log)  # ingest() rejects a non-object with NOT_AN_OBJECT
                self._records += 1
                continue
            record = {key: log[key] for key in LOG_FIELDS if key in log}
            number = log.get("block_number")
            block = blocks.get(number) if _is_nonneg_int(number) else None
            if isinstance(block, Mapping) and _is_nonneg_int(block.get("timestamp")):
                record["block_timestamp"] = str(block["timestamp"])
            else:
                self._missing_time += 1
            if any(key not in record for key in ORDER_FIELDS):
                self._missing_order += 1
            if any(key not in record for key in IDENTITY_FIELDS):
                self._missing_identity += 1
            framed.append(record)
            self._records += 1
        return framed

    def _content_sha256(self, from_block: int, next_block: int, events: Sequence[Any]) -> str:
        try:
            body = raw_bytes({"from_block": from_block, "next_block": next_block, "logs": list(events)})
        except (TypeError, ValueError) as error:
            raise SourceContractError("NON_JSON_PROVIDER_VALUE",
                                      "a provider value is not JSON data") from error
        return hashlib.sha256(body).hexdigest()
