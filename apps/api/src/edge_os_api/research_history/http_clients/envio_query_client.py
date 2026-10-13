"""Concrete injected Envio HyperSync query client.

This client implements the accepted ``EnvioQueryClient.query(HistoryRequest)``
protocol that ``EnvioHypersyncSource`` frames. It turns one ``HistoryRequest`` into
one Envio HyperSync HTTP ``POST /query`` and returns the parsed native HyperSync
response mapping. It makes exactly one call per ``query`` and never retries, never
follows a redirect and never falls back to another endpoint.

It owns its endpoint and bearer token as constructor inputs. It reads no
environment variable and no credential file, opens no socket itself (the injected
transport does), and performs no I/O at import or construction. The token is only
placed in the request ``Authorization`` header; it never appears in an error, a
message or any returned value.

Pinned wire (public first-party documentation, read 2026-10-12; Monad coverage and
the exact served shape are NOT verified): a JSON body with ``from_block``,
``to_block``, ``logs[]``, ``field_selection``, ``include_all_blocks`` and the
``max_num_*`` limits, against ``<host base>/query``. The bearer token is the
``Authorization: Bearer <token>`` header. The native response carries
``archive_height``, ``next_block``, ``total_execution_time``, ``data`` (``blocks``,
``logs``) and an optional ``rollback_guard``.

The page span is bounded to ``ClientBounds.max_blocks_per_page`` blocks and the log
count to the request's ``max_rows``, so one page cannot grow without a caller
bound. ``include_all_blocks`` is requested so the accepted framing can prove the
page-edge block facts.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from edge_os_api.research_history.http_clients.client_config import (
    ClientBounds,
    ClientConfigError,
    endpoint_has_path,
    endpoint_has_query,
    safe_endpoint,
    validate_endpoint,
)
from edge_os_api.research_history.http_clients.http_transport import (
    HttpResponse,
    HttpTransport,
    decode_json_reply,
    refuse_provider_status,
)
from edge_os_api.research_history.provider_transport import (
    HistoryRequest,
    SourceCancelled,
    SourceTimeout,
)

ENVIO_QUERY_PATH = "/query"
ENVIO_PROVIDER = "ENVIO_HYPERSYNC"

# The accepted framing reads these log and block facts; the request asks for all of
# them so a served log can prove its order, identity and time without missingness.
LOG_FIELD_SELECTION = ("address", "topic0", "topic1", "topic2", "topic3", "data",
                       "block_number", "block_hash", "transaction_hash",
                       "transaction_index", "log_index", "removed")
BLOCK_FIELD_SELECTION = ("number", "timestamp", "hash")


def _is_hex(value: Any, hex_digits: int) -> bool:
    if not isinstance(value, str) or len(value) != 2 + hex_digits or not value.startswith("0x"):
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value[2:])


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class HttpEnvioQueryClient:
    """A bounded Envio HyperSync ``EnvioQueryClient`` over an injected transport."""

    def __init__(self, *, endpoint: str, bearer_token: str, transport: HttpTransport,
                 bounds: ClientBounds, clock: Callable[[], float] = time.monotonic,
                 cancel: Callable[[], bool] | None = None) -> None:
        validate_endpoint(endpoint)
        if endpoint_has_path(endpoint) or endpoint_has_query(endpoint):
            raise ClientConfigError("the HyperSync endpoint must be the host base, without a path or query")
        if not isinstance(bearer_token, str) or not bearer_token:
            raise ClientConfigError("bearer_token must be a non-empty string")
        if not isinstance(bounds, ClientBounds):
            raise ClientConfigError("bounds must be a ClientBounds")
        bounds.validate()
        if not hasattr(transport, "request"):
            raise ClientConfigError("transport must provide a request() method")
        if not callable(clock):
            raise ClientConfigError("clock must be callable")
        if cancel is not None and not callable(cancel):
            raise ClientConfigError("cancel must be callable or None")
        self._endpoint = endpoint
        self._bearer_token = bearer_token
        self._transport = transport
        self._bounds = bounds
        self._clock = clock
        self._cancel = cancel
        self._attempts = 0
        self._completed = 0

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def attempts(self) -> int:
        return self._attempts

    def accounting(self) -> dict[str, int]:
        """Local attempt accounting. ``unknown_liability`` may still be consumed.

        A request is counted before it is sent, so a call that raises still counts.
        ``unknown_liability`` covers every attempt that did not return a valid
        reply; those requests may still have been served by the provider. This is a
        local count, never a durable budget.
        """
        return {"attempted_requests": self._attempts, "completed_requests": self._completed,
                "unknown_liability": self._attempts - self._completed}

    def query(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        body = self._request_body(request)
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "accept-encoding": "identity",
            "authorization": f"Bearer {self._bearer_token}",
        }
        if self._cancel is not None and self._cancel():
            raise SourceCancelled("the caller cancelled the request")
        self._attempts += 1
        deadline = self._clock() + self._bounds.deadline_seconds
        url = self._endpoint.rstrip("/") + ENVIO_QUERY_PATH
        response = self._transport.request(
            method="POST", url=url, headers=headers, body=body,
            timeout=self._bounds.connect_timeout_seconds, deadline=deadline,
            max_response_bytes=self._bounds.max_response_bytes, cancel=self._cancel)
        self._raise_for_status(response)
        parsed = self._parse(response)
        self._check_expiry(deadline)
        self._completed += 1
        return parsed

    def _check_expiry(self, deadline: float) -> None:
        """Reject expired or cancelled work after decode/validation, before success.

        The transport enforces the deadline during I/O, but decode and validation
        happen after it returns. Re-check the same absolute deadline and the cancel
        flag before counting the reply as completed, so an expired or cancelled reply
        never returns success or increments ``completed_requests``.
        """
        if self._cancel is not None and self._cancel():
            raise SourceCancelled("the caller cancelled the request")
        if self._clock() >= deadline:
            raise SourceTimeout("the request exceeded its time bound")

    def _request_body(self, request: HistoryRequest) -> bytes:
        if not isinstance(request, HistoryRequest):
            raise ClientConfigError("request must be a HistoryRequest")
        if request.provider != ENVIO_PROVIDER:
            raise ClientConfigError(f"request provider must be {ENVIO_PROVIDER}")
        if not _is_hex(request.address, 40):
            raise ClientConfigError("request address must be 0x followed by 20 hex bytes")
        if not _is_hex(request.topic0, 64):
            raise ClientConfigError("request topic0 must be 0x followed by 32 hex bytes")
        if not _is_nonneg_int(request.to_block_exclusive) or not _is_nonneg_int(
                request.from_block if request.cursor_after is None else request.cursor_after):
            raise ClientConfigError("request block bounds must be non-negative integers")
        if not _is_nonneg_int(request.max_rows) or request.max_rows < 1:
            raise ClientConfigError("request max_rows must be a positive integer")
        from_block = request.cursor_after if request.cursor_after is not None else request.from_block
        if from_block >= request.to_block_exclusive:
            raise ClientConfigError("request block range must not be empty or reversed")
        to_block = min(request.to_block_exclusive, from_block + self._bounds.max_blocks_per_page)
        payload = {
            "from_block": from_block,
            "to_block": to_block,
            "logs": [{"address": [request.address.lower()], "topics": [[request.topic0.lower()]]}],
            "field_selection": {"log": list(LOG_FIELD_SELECTION), "block": list(BLOCK_FIELD_SELECTION)},
            "include_all_blocks": True,
            "max_num_logs": request.max_rows,
            "max_num_blocks": self._bounds.max_blocks_per_page,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(body) > self._bounds.max_request_bytes:
            raise ClientConfigError(
                f"request body {len(body)} exceeds max_request_bytes {self._bounds.max_request_bytes}")
        return body

    def _raise_for_status(self, response: HttpResponse) -> None:
        refuse_provider_status(response.status, f"the HyperSync query to {safe_endpoint(self._endpoint)}")

    def _parse(self, response: HttpResponse) -> Mapping[str, Any]:
        return decode_json_reply(response)
