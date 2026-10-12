"""Concrete injected QuickNode Monad JSON-RPC client.

This client implements the accepted ``QuickNodeRpcClient.call(method, params)``
protocol that ``read_chain_id`` and ``corroborate_records`` use. It turns one call
into one JSON-RPC 2.0 request and returns the envelope's ``result``. It makes
exactly one call per ``call`` and never retries, never follows a redirect and never
falls back to another endpoint.

It owns its endpoint and headers as constructor inputs and reads no environment
variable or credential file. The credential lives in the endpoint path (QuickNode)
or an explicit injected header; it never appears in an error, a message or any
returned value. Only a caller-selected subset of the documented *read-only* methods
is allowed, and never a signing or broadcast method.

Strictness that the accepted corroboration needs: a reply must be a JSON object
with ``jsonrpc`` ``"2.0"``, the exact request ``id`` and exactly one of ``result``
or ``error``. A provider ``error`` becomes a refused provider reply; a malformed
envelope is refused; neither is repaired or retried.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from edge_os_api.research_history.http_clients.client_config import (
    ClientBounds,
    ClientConfigError,
    HttpProviderError,
    safe_endpoint,
    validate_endpoint,
)
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, HttpTransport
from edge_os_api.research_history.provider_transport import SourceCancelled

# The documented read-only methods the accepted corroboration and the collection
# packet's identity reads need. No signing, broadcast, account or state-changing
# method is listed, and a caller can only narrow this set, never widen it.
READ_ONLY_METHODS = frozenset({
    "eth_chainId",
    "eth_blockNumber",
    "eth_getCode",
    "eth_call",
    "eth_getBalance",
    "eth_getTransactionReceipt",
    "eth_getTransactionByHash",
    "eth_getBlockByNumber",
    "eth_getBlockByHash",
    "eth_getLogs",
})

_JSONRPC_VERSION = "2.0"


def _sanitized_error_message(error: Any) -> str:
    if isinstance(error, Mapping):
        code = error.get("code")
        message = error.get("message")
        text = message if isinstance(message, str) else ""
    else:
        code = None
        text = ""
    text = "".join(character for character in text if character.isprintable())[:200]
    return f"rpc error code={code!r} message={text!r}"


class HttpQuickNodeRpcClient:
    """A bounded QuickNode JSON-RPC ``QuickNodeRpcClient`` over an injected transport."""

    def __init__(self, *, endpoint: str, transport: HttpTransport, bounds: ClientBounds,
                 headers: Mapping[str, str] | None = None,
                 allowed_methods: Iterable[str] = READ_ONLY_METHODS,
                 clock: Callable[[], float] = time.monotonic,
                 cancel: Callable[[], bool] | None = None) -> None:
        validate_endpoint(endpoint)
        if not isinstance(bounds, ClientBounds):
            raise ClientConfigError("bounds must be a ClientBounds")
        bounds.validate()
        if not hasattr(transport, "request"):
            raise ClientConfigError("transport must provide a request() method")
        requested = frozenset(allowed_methods)
        if not requested:
            raise ClientConfigError("allowed_methods must not be empty")
        if not requested <= READ_ONLY_METHODS:
            extra = ", ".join(sorted(requested - READ_ONLY_METHODS))
            raise ClientConfigError(f"allowed_methods may only narrow the read-only set; removed: {extra}")
        if not callable(clock):
            raise ClientConfigError("clock must be callable")
        if cancel is not None and not callable(cancel):
            raise ClientConfigError("cancel must be callable or None")
        supplied = dict(headers) if headers is not None else {}
        if not all(isinstance(name, str) and isinstance(value, str) for name, value in supplied.items()):
            raise ClientConfigError("headers must map text names to text values")
        self._endpoint = endpoint
        self._transport = transport
        self._bounds = bounds
        self._clock = clock
        self._cancel = cancel
        self._allowed = requested
        self._headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "accept-encoding": "identity",
            **supplied,
        }
        self._next_id = 0
        self._attempts = 0
        self._completed = 0

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def allowed_methods(self) -> frozenset[str]:
        return self._allowed

    @property
    def attempts(self) -> int:
        return self._attempts

    def accounting(self) -> dict[str, int]:
        """Local attempt accounting; see ``HttpEnvioQueryClient.accounting``."""
        return {"attempted_requests": self._attempts, "completed_requests": self._completed,
                "unknown_liability": self._attempts - self._completed}

    def call(self, method: str, params: Sequence[Any]) -> Any:
        if not isinstance(method, str) or method not in self._allowed:
            raise ClientConfigError(f"method {method!r} is not an allowed read-only method")
        if isinstance(params, (str, bytes)) or not isinstance(params, Sequence):
            raise ClientConfigError("params must be a JSON array")
        call_id = self._next_id + 1
        try:
            body = json.dumps({"jsonrpc": _JSONRPC_VERSION, "id": call_id, "method": method,
                               "params": list(params)}, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ClientConfigError("params are not JSON data") from error
        if len(body) > self._bounds.max_request_bytes:
            raise ClientConfigError(
                f"request body {len(body)} exceeds max_request_bytes {self._bounds.max_request_bytes}")
        if self._cancel is not None and self._cancel():
            raise SourceCancelled("the caller cancelled the request")
        self._next_id = call_id
        self._attempts += 1
        deadline = self._clock() + self._bounds.deadline_seconds
        response = self._transport.request(
            method="POST", url=self._endpoint, headers=self._headers, body=body,
            timeout=self._bounds.connect_timeout_seconds, deadline=deadline,
            max_response_bytes=self._bounds.max_response_bytes, cancel=self._cancel)
        self._raise_for_status(response)
        result = self._parse(response, call_id)
        self._completed += 1
        return result

    def _raise_for_status(self, response: HttpResponse) -> None:
        status = response.status
        if 200 <= status < 300:
            return
        where = f"the JSON-RPC call to {safe_endpoint(self._endpoint)}"
        if 300 <= status < 400:
            raise HttpProviderError("REDIRECT_REFUSED", f"{where} returned redirect status {status}")
        if status in (401, 403):
            raise HttpProviderError("AUTH_DENIED", f"{where} was denied (status {status})")
        if status == 402:
            raise HttpProviderError("PAYMENT_REQUIRED", f"{where} requires payment (status 402)")
        if status == 429:
            raise HttpProviderError("RATE_LIMITED", f"{where} was rate limited (status 429)")
        raise HttpProviderError("HTTP_STATUS", f"{where} returned status {status}")

    def _parse(self, response: HttpResponse, call_id: int) -> Any:
        encoding = response.headers.get("content-encoding")
        if encoding is not None and encoding.lower() != "identity":
            raise HttpProviderError("UNSUPPORTED_CONTENT_ENCODING",
                                    f"reply used content-encoding {encoding!r}")
        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not valid UTF-8") from error
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not valid JSON") from error
        if not isinstance(parsed, Mapping):
            raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not a JSON object")
        if parsed.get("jsonrpc") != _JSONRPC_VERSION:
            raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not JSON-RPC 2.0")
        if parsed.get("id") != call_id:
            raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply id does not match the request")
        has_result = "result" in parsed
        has_error = "error" in parsed
        if has_result == has_error:
            raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply must carry exactly one of result or error")
        if has_error:
            raise HttpProviderError("PROVIDER_ERROR", _sanitized_error_message(parsed["error"]))
        return parsed["result"]
