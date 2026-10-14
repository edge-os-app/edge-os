"""Native Nansen HTTP transport over the existing bounded HTTP seam.

``NansenHttpTransport`` satisfies ``NansenTransport``. It sends one admitted
operation to the fixed origin ``https://api.nansen.ai`` through an injected
``HttpTransport`` (production passes ``StdlibHttpTransport``). The trusted caller
supplies the key; this module reads no environment, file or network at import or
construction, and no representation, message or exception chain carries the key.

The adapter owns the wire: the exact operation/path pair, canonical JSON, the
request and response byte caps, one absolute monotonic deadline, cancellation,
redirect and credential-echo refusal and the mapping of transport failures to the
package's error types. ``NansenClient`` stays the owner of body pinning,
reservations, status mapping and retained headers. One admitted request makes one
HTTP attempt; there is no retry, redirect follow, pagination or payment path.
"""

from __future__ import annotations

import http.client
import math
import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from edge_os_api.nansen_research.errors import (
    NansenCancelled,
    NansenContractError,
    NansenInputError,
    NansenLimitError,
    NansenProtocolError,
    NansenProviderError,
    NansenRequestError,
    NansenTimeout,
    NansenTransportError,
)
from edge_os_api.nansen_research.serialization import canonical_bytes, load_provider_json
from edge_os_api.nansen_research.transport import NansenResponse
from edge_os_api.research_history.http_clients.client_config import HttpProviderError
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, HttpTransport
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceFailure, SourceTimeout

NANSEN_ORIGIN = "https://api.nansen.ai"
ROUTES: dict[str, str] = {
    "holders": "/api/v1/tgm/holders",
    "flows": "/api/v1/tgm/flows",
}
# The stable codes the shared HTTP layer raises. Any other code is replaced, so
# injected text never reaches a public error or a saved failure field.
_CONTRACT_CODES = frozenset({"OVERSIZED_RESPONSE", "MALFORMED_PROVIDER_RESPONSE"})
_PROVIDER_CODES = frozenset({"UNSUPPORTED_CONTENT_ENCODING", "REDIRECT_REFUSED", "AUTH_DENIED",
                             "PAYMENT_REQUIRED", "RATE_LIMITED", "HTTP_STATUS"})


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _decoded_texts(body: bytes) -> list[str]:
    """Every string value and member name the consumer's JSON decoding would produce.

    A body that is not UTF-8 JSON returns nothing: the client refuses it as malformed
    with its own stable error. A body nested deeper than the decoder accepts raises
    ``RecursionError``, which the client does not handle, so the caller refuses it here.
    """
    try:
        pending: list[Any] = [load_provider_json(body)]
    except (UnicodeDecodeError, ValueError):
        return []
    texts: list[str] = []
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            texts.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return texts


def _refuse_nonfinite_decimal(value: Any) -> None:
    # canonical_bytes refuses floats but writes a nonfinite Decimal as text.
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("a nonfinite decimal is not request data")
    if isinstance(value, Mapping):
        for item in value.values():
            _refuse_nonfinite_decimal(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _refuse_nonfinite_decimal(item)


class NansenHttpTransport:
    """One bounded native Nansen request per ``request`` call. No retry."""

    def __init__(self, *, api_key: str, http: HttpTransport, connect_timeout_seconds: float,
                 deadline_monotonic: float, max_request_bytes: int, max_response_bytes: int,
                 cancel: Callable[[], bool] | None = None) -> None:
        if (not isinstance(api_key, str) or not api_key
                or not all("!" <= character <= "~" for character in api_key)):
            raise NansenInputError("INVALID_CREDENTIAL", "api_key must be non-empty printable ASCII without spaces")
        if not isinstance(http, HttpTransport):
            raise NansenInputError("INVALID_TRANSPORT", "http must implement the HttpTransport seam")
        if not _is_finite_number(connect_timeout_seconds) or connect_timeout_seconds <= 0:
            raise NansenLimitError("connect_timeout_seconds must be a finite positive number")
        if not _is_finite_number(deadline_monotonic):
            raise NansenLimitError("deadline_monotonic must be a finite monotonic instant")
        if not _is_positive_int(max_request_bytes):
            raise NansenLimitError("max_request_bytes must be a positive integer")
        if not _is_positive_int(max_response_bytes):
            raise NansenLimitError("max_response_bytes must be a positive integer")
        if cancel is not None and not callable(cancel):
            raise NansenLimitError("cancel must be callable or None")
        self._api_key = api_key
        self._http = http
        self._connect_timeout = connect_timeout_seconds
        self._deadline = deadline_monotonic
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes
        self._cancel = cancel

    def __repr__(self) -> str:
        return (f"NansenHttpTransport(origin={NANSEN_ORIGIN!r}, "
                f"max_request_bytes={self._max_request_bytes}, max_response_bytes={self._max_response_bytes})")

    def _serialize(self, body: Mapping[str, Any]) -> bytes:
        if not isinstance(body, Mapping):
            raise NansenRequestError("BODY_NOT_SERIALIZABLE", "the request body must be a mapping")
        payload: bytes | None
        try:
            _refuse_nonfinite_decimal(body)
            payload = canonical_bytes(dict(body))
        except (TypeError, ValueError):
            payload = None
        if payload is None:
            # Raised outside the handler so no chained message is retained.
            raise NansenRequestError("BODY_NOT_SERIALIZABLE", "the request body is not canonical finite JSON")
        if len(payload) > self._max_request_bytes:
            raise NansenRequestError("REQUEST_TOO_LARGE", "the request body passes max_request_bytes")
        return payload

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse:
        if not isinstance(operation, str) or ROUTES.get(operation) != path:
            raise NansenRequestError("ROUTE_NOT_ALLOWED", "only the pinned holders and flows routes are allowed")
        payload = self._serialize(body)
        if self._cancel is not None and self._cancel():
            raise NansenCancelled("CANCELLED", "the caller cancelled before dispatch")
        if time.monotonic() >= self._deadline:
            raise NansenTimeout("DEADLINE", "the job deadline passed before dispatch")
        failure: NansenTransportError | None = None
        try:
            reply = self._http.request(
                method="POST",
                url=NANSEN_ORIGIN + path,
                headers={"apikey": self._api_key, "content-type": "application/json",
                         "accept": "application/json"},
                body=payload,
                timeout=self._connect_timeout,
                deadline=self._deadline,
                max_response_bytes=self._max_response_bytes,
                cancel=self._cancel,
            )
        except (SourceTimeout, SourceCancelled, SourceFailure, http.client.HTTPException, OSError) as error:
            failure = _translate(error)
        if failure is not None:
            # Raised outside the handler: the original text may carry provider or key
            # text, so it is kept in neither ``__cause__`` nor ``__context__``.
            raise failure
        return self._accept(reply)

    def _accept(self, reply: Any) -> NansenResponse:
        if not isinstance(reply, HttpResponse):
            raise NansenProtocolError("TRANSPORT_NOT_A_RESPONSE", "the HTTP transport returned a non-response value")
        status, headers, body = reply.status, reply.headers, reply.body
        if (isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599
                or not isinstance(headers, Mapping) or not isinstance(body, bytes)):
            raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "the HTTP reply is malformed")
        if len(body) > self._max_response_bytes:
            raise NansenContractError("OVERSIZED_RESPONSE", "the reply body passes max_response_bytes")
        # Case-insensitive: header names arrive lower-cased and an echo may be re-cased.
        key = self._api_key.lower()
        literal_echo = (key.encode("ascii") in body.lower()
                        or any(key in str(name).lower() or key in str(value).lower()
                               for name, value in headers.items()))
        texts: list[str] | None = []
        if not literal_echo:
            try:
                texts = _decoded_texts(body)
            except RecursionError:
                texts = None
        if texts is None:
            # Raised outside the handler: no decoder diagnostic is chained.
            error = NansenContractError("MALFORMED_PROVIDER_RESPONSE",
                                        "the reply nests deeper than the JSON decoder accepts")
            error.status = status
            raise error
        if literal_echo or any(key in text.lower() for text in texts):
            # Refused rather than redacted: a mutated body must not be hashed as the original.
            error = NansenContractError("CREDENTIAL_ECHO", "the reply echoed the request credential")
            error.status = status
            raise error
        if 300 <= status < 400:
            error = NansenContractError("REDIRECT_REFUSED", f"redirect status {status} is not followed")
            error.status = status
            raise error
        return NansenResponse(status=status, headers=dict(headers), body=body)


def _translate(error: BaseException) -> NansenTransportError:
    """The sanitized Nansen error for an expected HTTP failure. No source text is copied."""
    if isinstance(error, (SourceTimeout, TimeoutError)):
        return NansenTimeout("TIMEOUT", "the HTTP request exceeded its time bound")
    if isinstance(error, SourceCancelled):
        return NansenCancelled("CANCELLED", "the caller cancelled the HTTP request")
    if isinstance(error, HttpProviderError):
        code = error.code if isinstance(error.code, str) else None
        if code in _CONTRACT_CODES:
            return NansenContractError(code, "the HTTP reply was refused")
        if code in _PROVIDER_CODES:
            return NansenProviderError(code, "the HTTP reply was refused")
        return NansenProviderError("UNRECOGNIZED_HTTP_FAILURE", "the HTTP layer reported an unrecognized failure")
    if isinstance(error, http.client.HTTPException):
        return NansenContractError("MALFORMED_PROVIDER_RESPONSE", "the HTTP reply was refused")
    if isinstance(error, SourceFailure):
        return NansenTransportError("TRANSPORT_FAILURE", "the HTTP transport reported a failure")
    return NansenTransportError("NETWORK_ERROR", f"the HTTP connection failed: {type(error).__name__}")
