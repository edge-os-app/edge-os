"""Per-job research provider clients, composed by the application (#58 RESEARCH-PORTS-LOCAL).

The application is the only place that chooses an endpoint, a credential and a transport for a research provider.
No setting, request or saved row can supply one. This module builds, for one job:

- the accepted P07 ``HttpEnvioQueryClient`` and ``HttpQuickNodeRpcClient`` over ``AuthoredHttpTransport``;
- a ``NansenTransport`` over ``AuthoredNansenTransport``.

Both transports are AUTHORED: they answer from the repository's recorded fixtures, open no socket, read no
credential and never claim ``ACTUAL_PROVIDER``. They exist so the application provably drives the actual client
classes and wire formats. Real transports need a separately approved actual packet and are not composed here; in
production both paths stay unavailable (settings refuse the local modes).
"""

from __future__ import annotations

import functools
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from edge_os_api.nansen_research import NansenCancelled, NansenResponse, NansenTimeout
from edge_os_api.nansen_research.errors import NansenTransportError
from edge_os_api.research_history.http_clients import (
    ClientBounds,
    HttpEnvioQueryClient,
    HttpQuickNodeRpcClient,
    HttpResponse,
)
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceTimeout

HTTP_TRANSPORT_LABEL = "AUTHORED_HTTP_TRANSPORT"
NANSEN_TRANSPORT_LABEL = "AUTHORED_NANSEN_TRANSPORT"
NANSEN_EVIDENCE_CLASS = "AUTHORED_FIXTURE"
# Application-owned constants. `.invalid` names can never resolve; the bearer value is authored and not a secret.
AUTHORED_ENVIO_ENDPOINT = "https://hypersync.authored.invalid"
AUTHORED_QUICKNODE_ENDPOINT = "https://quicknode.authored.invalid/authored"
AUTHORED_BEARER = "authored-local-fixture"
MAX_REQUEST_BYTES = 65_536
NANSEN_FIXTURE_PATH = (Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "nansen_research_authored"
                       / "nansen_authored_v1.json")
NANSEN_FIXTURE_VERSION = "edge-os.nansen-authored-fixture/1"


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class AuthoredHttpTransport:
    """An ``HttpTransport`` that answers the P07 HTTP clients from one native recording.

    ``POST <envio>/query`` returns the recorded HyperSync pages in order (a recorded ``SOURCE_FAILURE`` page is an
    HTTP 503, a ``SOURCE_TIMEOUT`` page raises ``SourceTimeout``). A JSON-RPC 2.0 post to the QuickNode endpoint
    answers ``eth_chainId`` and ``eth_getTransactionReceipt`` from the recording (a recorded ``RPC_FAILED`` receipt is
    a JSON-RPC error). It keeps only the SHA-256 of each reply body it returns, never a request header.
    """

    def __init__(self, source: Mapping[str, Any]) -> None:
        self._pages = list(source["envio_pages"])
        self._rpc = source["quicknode"]
        self._page = 0
        self.response_sha256: list[str] = []

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float,
                deadline: float, max_response_bytes: int, cancel: Callable[[], bool] | None = None) -> HttpResponse:
        if cancel is not None and cancel():
            raise SourceCancelled("the caller cancelled the request")
        if time.monotonic() >= deadline:
            raise SourceTimeout("the request exceeded its time bound")
        if method != "POST":
            return self._reply(405, {"error": "method"})
        if url == AUTHORED_ENVIO_ENDPOINT + "/query":
            return self._envio()
        if url == AUTHORED_QUICKNODE_ENDPOINT:
            return self._quicknode(body)
        return self._reply(404, {"error": "not found"})

    def _envio(self) -> HttpResponse:
        if self._page >= len(self._pages):
            return self._reply(200, {"archive_height": None, "next_block": None, "data": []})
        page = self._pages[self._page]
        self._page += 1
        fault = page.get("fault") if isinstance(page, Mapping) else None
        if fault == "SOURCE_FAILURE":
            return self._reply(503, {"error": "authored provider failure"})
        if fault == "SOURCE_TIMEOUT":
            raise SourceTimeout("authored provider timeout")
        return self._reply(200, page)

    def _quicknode(self, body: bytes) -> HttpResponse:
        call = json.loads(body)
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": call.get("id")}
        if call.get("method") == "eth_chainId":
            reply["result"] = self._rpc["eth_chainId"]
        elif call.get("method") == "eth_getTransactionReceipt":
            tx_hash = (call.get("params") or [None])[0]
            if self._rpc.get("rpc_faults", {}).get(tx_hash) == "RPC_FAILED":
                reply["error"] = {"code": -32000, "message": "authored RPC failure"}
            else:
                reply["result"] = self._rpc["receipts"].get(tx_hash)
        else:
            reply["error"] = {"code": -32601, "message": "method not found"}
        return self._reply(200, reply)

    def _reply(self, status: int, payload: Any) -> HttpResponse:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.response_sha256.append(_sha256(body))
        return HttpResponse(status=status, headers={"content-type": "application/json"}, body=body)


def client_bounds(bounds: Mapping[str, Any], source: Mapping[str, Any]) -> ClientBounds:
    """Finite per-call limits from the declaration's own bounds."""
    deadline = float(bounds["deadline_seconds"])
    scan = source["scan"]
    return ClientBounds(deadline_seconds=deadline, connect_timeout_seconds=min(10.0, deadline),
                        max_response_bytes=int(bounds["max_bytes"]), max_request_bytes=MAX_REQUEST_BYTES,
                        max_blocks_per_page=max(1, int(scan["to_block_exclusive"]) - int(scan["from_block"])))


def http_source_clients(source: Mapping[str, Any], bounds: Mapping[str, Any],
                        cancelled: Callable[[], bool]) -> tuple[HttpEnvioQueryClient, HttpQuickNodeRpcClient,
                                                                AuthoredHttpTransport]:
    """Fresh accepted P07 HTTP clients for one job, over one authored transport. No I/O happens here."""
    transport = AuthoredHttpTransport(source)
    limits = client_bounds(bounds, source)
    envio = HttpEnvioQueryClient(endpoint=AUTHORED_ENVIO_ENDPOINT, bearer_token=AUTHORED_BEARER,
                                 transport=transport, bounds=limits, cancel=cancelled)
    quicknode = HttpQuickNodeRpcClient(endpoint=AUTHORED_QUICKNODE_ENDPOINT, transport=transport, bounds=limits,
                                       allowed_methods=("eth_chainId", "eth_getTransactionReceipt"),
                                       cancel=cancelled)
    return envio, quicknode, transport


# --------------------------------------------------------------------------------------------- Nansen

@functools.lru_cache(maxsize=1)
def _nansen_fixture() -> dict[str, Any]:
    fixture = json.loads(NANSEN_FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != NANSEN_FIXTURE_VERSION or fixture.get("label") != "AUTHORED":
        raise ValueError("not an authored Nansen fixture")
    return fixture


class AuthoredNansenTransport:
    """A ``NansenTransport`` that answers from the authored fixture for one token.

    Replies are keyed by operation and page. A token the fixture does not hold gets an authored empty page. Each
    reply's SHA-256 is kept; the request body is never stored here.
    """

    def __init__(self, token_address: str, scenario: str = "default") -> None:
        fixture = _nansen_fixture()
        tokens = fixture["tokens"]
        self._token = tokens.get(token_address.lower(), tokens.get("*"))
        self._scenario = scenario
        self.calls = 0
        self.response_sha256: list[str] = []

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse:
        self.calls += 1
        page = int((body.get("pagination") or {}).get("page", 1))
        item = ((self._token or {}).get(operation) or {}).get(str(page))
        if item is None:
            item = {"status": 200, "headers": {}, "payload": {"data": [], "pagination": {"page": page,
                                                                                         "is_last_page": True}}}
        if item.get("transport_error"):
            raise NansenTransportError(item["transport_error"], "authored transport fault")
        response_body = json.dumps(item["payload"]).encode("utf-8")
        self.response_sha256.append(_sha256(response_body))
        return NansenResponse(status=int(item["status"]), headers=dict(item.get("headers") or {}),
                              body=response_body)


class GuardedNansenTransport:
    """Refuses the next request after cancellation or the job deadline, before the wrapped transport is called."""

    def __init__(self, inner: Any, cancelled: Callable[[], bool], deadline_passed: Callable[[], bool]) -> None:
        self._inner, self._cancelled, self._deadline_passed = inner, cancelled, deadline_passed

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse:
        if self._cancelled():
            raise NansenCancelled("CANCELLED", "the owner cancelled the job before the next request")
        if self._deadline_passed():
            raise NansenTimeout("DEADLINE", "the job deadline passed before the next request")
        return self._inner.request(operation, path, body)


def nansen_transport(token_address: str) -> AuthoredNansenTransport:
    """A fresh authored Nansen transport for one job."""
    return AuthoredNansenTransport(token_address)
