"""One-shot bounded sign-only transport for the unfunded actual proof runner.

LOCAL only. This transport sends at most one ``POST`` to one exact approved
wallet-RPC destination. It reuses the accepted HTTP transport seam
(``HttpTransport``/``HttpResponse``/``HttpProviderError``) and the accepted
compact sorted-key ASCII serialization (``canonical_json``). It never retries,
follows a redirect, renews an expiry or an idempotency key, falls back to
another endpoint, or issues a policy-administration or cleanup request.

The authorization signature comes from an injected callable (for production,
``edge_os_api.execution.privy_signer.make_p256_authorizer``). It signs only the
exact payload this transport builds; if the callback changes that payload the
transport refuses before HTTP. Construction reads no environment, file or
network and holds no default host. A second ``send`` on the same transport
raises and sends nothing: the first call may have produced a signature.
"""

from __future__ import annotations

import base64
import copy
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from edge_os_api.research_history.http_clients.client_config import HttpProviderError
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, HttpTransport
from scripts.privy_unfunded_proof.specimens import FrozenRequest, canonical_json, refuse_module_run

REQUEST_BYTES_LIMIT = 65_536
SIGNATURE_LIMIT = 4_096
_PRINTABLE = re.compile(r"[\x21-\x7e]+")
_WALLET_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_APP_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,256}")
_SIGNATURE = re.compile(r"[A-Za-z0-9+/=,]+")
_EXPIRY = re.compile(r"[1-9][0-9]*")
_RPC_URL = re.compile(r"https://api\.privy\.io/v1/wallets/([A-Za-z0-9_-]{1,128})/rpc")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_DATA = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
TRANSACTION_FIELDS = frozenset({"type", "chain_id", "nonce", "to", "value", "data", "gas_limit",
                                "max_fee_per_gas", "max_priority_fee_per_gas"})
QUANTITY_FIELDS = ("chain_id", "nonce", "value", "gas_limit", "max_fee_per_gas", "max_priority_fee_per_gas")
MAX_SAFE_INTEGER = 2**53 - 1
MAX_UINT256 = 2**256 - 1
_CANONICAL_QUANTITY_HEX = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")


def wire_quantity(value: int) -> int | str:
    """The exact wire form: a small quantity stays a number, a larger one is a canonical lowercase hex string."""
    if not _is_int(value) or not 0 <= value <= MAX_UINT256:
        raise ValueError("quantity outside the accepted range")
    return value if value <= MAX_SAFE_INTEGER else hex(value)


def decode_wire_quantity(value: object) -> int | None:
    """The exact integer from a wire number or a canonical lowercase hex string, or None."""
    if _is_int(value) and 0 <= value <= MAX_SAFE_INTEGER:
        return value
    if isinstance(value, str) and _CANONICAL_QUANTITY_HEX.fullmatch(value):
        parsed = int(value, 16)
        return parsed if MAX_SAFE_INTEGER < parsed <= MAX_UINT256 else None
    return None


def accepted_request_profile(body: Any) -> bool:
    """The narrow accepted authorizer profile: exactly one type-2 eth_signTransaction body.

    A quantity at or below 2**53 - 1 is a JSON number. A larger quantity is a canonical lowercase ``0x`` string
    with no leading zeros, so the transport never emits a JSON number above 2**53 - 1. ``chain_id`` stays a JSON
    number in the safe-integer range.
    """
    if not isinstance(body, Mapping) or set(body) != {"method", "params"}:
        return False
    if body["method"] != "eth_signTransaction":
        return False
    params = body["params"]
    if not isinstance(params, Mapping) or set(params) != {"transaction"}:
        return False
    transaction = params["transaction"]
    if not isinstance(transaction, Mapping) or set(transaction) != TRANSACTION_FIELDS:
        return False
    if not _is_int(transaction["type"]) or transaction["type"] != 2:
        return False
    for name in QUANTITY_FIELDS:
        if name == "chain_id":
            value = transaction[name]
            if not _is_int(value) or not 1 <= value <= MAX_SAFE_INTEGER:
                return False
        else:
            value = decode_wire_quantity(transaction[name])
            if value is None:
                return False
    return (_ADDRESS.fullmatch(transaction["to"]) is not None and _DATA.fullmatch(transaction["data"]) is not None)


class TransportRefused(Exception):
    """Nothing was sent. ``code`` is a fixed string."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TransportLost(Exception):
    """A request may have been sent and its reply did not arrive. ``code`` is fixed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class ActualSignOnlyTransport:
    """One signed ``eth_signTransaction`` request for one approved wallet RPC route."""

    def __init__(
        self,
        *,
        http: HttpTransport,
        destination: str,
        wallet_id: str,
        app_id: str,
        app_secret: str,
        authorize: Callable[[Mapping[str, Any]], str],
        request_id: str,
        request_expiry_ms: int,
        connect_timeout_seconds: float,
        deadline_monotonic: float,
        max_response_bytes: int,
        cancel: Callable[[], bool] | None = None,
        wall_clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(app_id, str) or _APP_ID.fullmatch(app_id) is None:
            raise ValueError("app_id must be 1-128 characters of [A-Za-z0-9_-]")
        if not isinstance(app_secret, str) or _PRINTABLE.fullmatch(app_secret) is None:
            raise ValueError("app_secret must be non-empty printable ASCII without spaces")
        if not isinstance(wallet_id, str) or _WALLET_ID.fullmatch(wallet_id) is None:
            raise ValueError("wallet_id must be 1-128 characters of [A-Za-z0-9_-]")
        match = _RPC_URL.fullmatch(destination) if isinstance(destination, str) else None
        if match is None:
            raise ValueError("destination must be the exact approved wallet RPC URL")
        if match.group(1) != wallet_id:
            raise ValueError("destination wallet id must equal wallet_id")
        if not callable(authorize):
            raise ValueError("authorize must be callable")
        if not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None:
            raise ValueError("request_id must be 1-256 characters of [A-Za-z0-9._:-]")
        if not _is_int(request_expiry_ms) or request_expiry_ms <= 0:
            raise ValueError("request_expiry_ms must be a positive integer")
        if not isinstance(http, HttpTransport):
            raise ValueError("http must implement the HttpTransport seam")
        for name, value in (("connect_timeout_seconds", connect_timeout_seconds),
                            ("deadline_monotonic", deadline_monotonic)):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
        if not _is_int(max_response_bytes) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")
        for name, value in (("cancel", cancel), ("wall_clock_ms", wall_clock_ms), ("monotonic", monotonic)):
            if value is not None and not callable(value):
                raise ValueError(f"{name} must be callable")
        self._http = http
        self._destination = destination
        self._wallet_id = wallet_id
        self._app_id = app_id
        self._basic = base64.b64encode(f"{app_id}:{app_secret}".encode("ascii")).decode("ascii")
        self._authorize = authorize
        self._request_id = request_id
        self._expiry_ms = request_expiry_ms
        self._expiry = str(request_expiry_ms)
        self._connect_timeout = connect_timeout_seconds
        self._deadline = deadline_monotonic
        self._max_response_bytes = max_response_bytes
        self._cancel = cancel
        self._wall_clock_ms = wall_clock_ms
        self._monotonic = monotonic
        self._used = False

    def __repr__(self) -> str:
        return (f"ActualSignOnlyTransport(destination={self._destination!r}, "
                f"max_response_bytes={self._max_response_bytes})")

    def binding(self) -> dict[str, object]:
        """The non-secret wire identity the runner binds to the approved packet and specimen."""
        return {"method": "POST", "destination": self._destination, "wallet_id": self._wallet_id,
                "app_id": self._app_id, "request_id": self._request_id,
                "request_expiry_ms": self._expiry_ms}

    def _stop(self) -> str | None:
        try:
            if self._cancel is not None and self._cancel():
                return "CANCELLED"
            if self._monotonic() >= self._deadline:
                return "DEADLINE_PASSED"
            if self._wall_clock_ms() >= self._expiry_ms:
                return "REQUEST_EXPIRED"
        except Exception:  # noqa: BLE001 - a failing stop check before send sends nothing
            return "STOP_CHECK_FAILED"
        return None

    def send(self, request: FrozenRequest) -> HttpResponse:
        """Send the one allowed request and return the raw bounded reply.

        Raises ``TransportRefused`` when nothing was sent and ``TransportLost``
        when a send may have happened. Every failure is raised outside its
        handler with a fixed code, so no provider or authorizer text is retained
        in ``__cause__`` or ``__context__``.
        """
        if self._used:
            raise TransportRefused("TRANSPORT_ALREADY_USED")
        self._used = True
        if request.http_method != "POST":
            raise TransportRefused("METHOD_NOT_APPROVED")
        if request.url != self._destination:
            raise TransportRefused("DESTINATION_NOT_APPROVED")
        if len(request.body) > REQUEST_BYTES_LIMIT:
            raise TransportRefused("REQUEST_TOO_LARGE")
        body_object: Any = None
        try:
            body_object = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            body_object = None
        if body_object is None:
            raise TransportRefused("BODY_INVALID")
        if not isinstance(body_object, dict) or body_object.get("method") != "eth_signTransaction":
            raise TransportRefused("OPERATION_NOT_APPROVED")
        if not accepted_request_profile(body_object):
            raise TransportRefused("REQUEST_PROFILE_UNQUALIFIED")
        if canonical_json(body_object) != request.body:
            raise TransportRefused("BODY_NOT_CANONICAL")
        stop = self._stop()
        if stop is not None:
            raise TransportRefused(stop)

        frozen = {name: value for name, value in request.headers}
        expiry = frozen.get("privy-request-expiry", self._expiry)
        privy_headers = {"privy-app-id": self._app_id, "privy-idempotency-key": self._request_id,
                         "privy-request-expiry": expiry}
        payload = {"version": 1, "method": "POST", "url": request.url, "body": body_object,
                   "headers": privy_headers}
        given = copy.deepcopy(payload)
        signature: Any = None
        authorized = True
        try:
            signature = self._authorize(given)
        except Exception:  # noqa: BLE001 - any authorizer failure sends nothing; its text is not kept
            authorized = False
        if not authorized:
            raise TransportRefused("AUTHORIZATION_FAILED")
        changed = True
        try:
            changed = canonical_json(given) != canonical_json(payload)
        except Exception:  # noqa: BLE001 - a payload the callback made unencodable was changed
            changed = True
        if changed:
            raise TransportRefused("AUTHORIZATION_PAYLOAD_CHANGED")
        if (not isinstance(signature, str) or len(signature) > SIGNATURE_LIMIT
                or _SIGNATURE.fullmatch(signature) is None):
            raise TransportRefused("AUTHORIZATION_INVALID")
        stop = self._stop()
        if stop is not None:
            raise TransportRefused(stop)

        headers = {"authorization": f"Basic {self._basic}", "content-type": "application/json",
                   "privy-authorization-signature": signature, **privy_headers}
        response: Any = None
        refused = False
        lost = False
        try:
            response = self._http.request(method="POST", url=request.url, headers=headers, body=request.body,
                                          timeout=self._connect_timeout, deadline=self._deadline,
                                          max_response_bytes=self._max_response_bytes, cancel=self._cancel)
        except HttpProviderError:
            refused = True
        except Exception:  # noqa: BLE001 - after a possible dispatch every failure keeps the liability
            lost = True
        if refused:
            raise TransportRefused("TRANSPORT_REFUSED")
        if lost:
            raise TransportLost("TRANSPORT_LOST")
        return response


if __name__ == "__main__":
    refuse_module_run()
