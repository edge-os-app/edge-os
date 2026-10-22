"""Privy sign-only HTTP adapter for the original-transaction `SignerClient` seam (#58 Stage 3, LOCAL).

`PrivySignerClient.rpc` sends one `eth_signTransaction` request for one original transaction to
`POST https://api.privy.io/v1/wallets/{wallet_id}/rpc` through an injected `HttpTransport`. It accepts only the exact
type-2 body `OriginalTransactionTransport` builds and never rewrites, fills or converts a value. It is unmounted: no
caller, setting or factory constructs it, and it reads no environment, file or network at import or construction.

The `privy-authorization-signature` value comes from an injected callable. `make_p256_authorizer` builds one from an
already loaded P-256 private-key object: it accepts only the payload this adapter builds, serializes it with the same
compact sorted-key JSON, and signs those bytes with ECDSA SHA-256. That serialization equals RFC 8785 only for the
accepted value domain (fixed ASCII keys, ASCII strings, small integers and canonical large-quantity hex strings); it
is not a general RFC 8785 implementation. A quantity field may be any exact unsigned integer from 0 to 2**256 - 1.
The wire body keeps a value at or below 2**53 - 1 as a JSON number and sends a larger value as a canonical lowercase
``0x`` string with no leading zeros, so no JSON number above 2**53 - 1 is ever sent. The fields that can be hex
strings are ``chain_id``, ``nonce``, ``value``, ``gas_limit``, ``max_fee_per_gas`` and ``max_priority_fee_per_gas``;
``type`` stays the integer 2.
The authorizer signs Privy API requests only. It never signs a wallet transaction and loads, stores or creates no key.

Outcomes, matched to the caller's existing vocabulary:
- nothing was sent (invalid input, stop or authorization failure before HTTP) → the `LOCAL_UNSENT` error envelope,
  the only reply `is_signer_refusal` treats as a refusal;
- a request may have been sent and its reply did not arrive → `ReplyLost`;
- any reply other than the documented success, including every Privy error → `RpcError`.
No provider reply becomes a refusal: Privy documents error codes but not an error body shape. Errors carry a stable
code only and are raised outside exception handlers, so no cause or context keeps provider text, credentials, the
authorization signature or signed bytes.
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

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from edge_os_api.execution.original_transaction import SIGNED_BYTES_LIMIT, ReplyLost, RpcError
from edge_os_api.research_history.http_clients.client_config import HttpProviderError
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, HttpTransport

PRIVY_API_ORIGIN = "https://api.privy.io"
METHOD = "eth_signTransaction"
TRANSACTION_FIELDS = frozenset({"type", "chain_id", "nonce", "to", "value", "data", "gas_limit", "max_fee_per_gas",
                                "max_priority_fee_per_gas"})
QUANTITY_FIELDS = ("chain_id", "nonce", "value", "gas_limit", "max_fee_per_gas", "max_priority_fee_per_gas")
# RFC 8785 writes numbers as IEEE doubles: a larger integer must not be a JSON number.
MAX_SAFE_INTEGER = 2**53 - 1
MAX_UINT256 = 2**256 - 1
_CANONICAL_QUANTITY_HEX = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")
REQUEST_BYTES_LIMIT = 65_536
SIGNATURE_LIMIT = 4_096
_WALLET_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_APP_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,256}")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_DATA = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
_SIGNED = re.compile(r"0x(?:[0-9a-fA-F]{2})+")
_SIGNATURE = re.compile(r"[A-Za-z0-9+/=,]+")
_RPC_URL = re.compile(r"https://api\.privy\.io/v1/wallets/([A-Za-z0-9_-]{1,128})/rpc")
_EXPIRY = re.compile(r"[1-9][0-9]*")
SIGNED_HEADERS = frozenset({"privy-app-id", "privy-idempotency-key", "privy-request-expiry"})


def _printable(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and all("!" <= character <= "~" for character in value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _local_unsent(reason: str) -> dict[str, Any]:
    """Nothing reached Privy. The caller records this as `SIGNER_REFUSED`, which is not a provider denial."""
    return {"error": {"code": "LOCAL_UNSENT", "reason": reason}}


class PrivySignerClient:
    """One Privy `eth_signTransaction` request for one original transaction. No retry, redirect or renewal."""

    def __init__(self, *, app_id: str, app_secret: str, authorize: Callable[[Mapping[str, Any]], str],
                 request_id: str, request_expiry_ms: int, http: HttpTransport, connect_timeout_seconds: float,
                 deadline_monotonic: float, max_response_bytes: int, cancel: Callable[[], bool] | None = None,
                 wall_clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(app_id, str) or not _APP_ID.fullmatch(app_id):
            raise ValueError("app_id must be 1-128 characters of [A-Za-z0-9_-]")
        if not _printable(app_secret):
            raise ValueError("app_secret must be non-empty printable ASCII without spaces")
        if not callable(authorize):
            raise ValueError("authorize must be callable")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ValueError("request_id must be 1-256 characters of [A-Za-z0-9._:-]")
        if not _is_int(request_expiry_ms) or request_expiry_ms <= 0:
            raise ValueError("request_expiry_ms must be a positive integer of Unix milliseconds")
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
        self._app_id = app_id
        self._basic = base64.b64encode(f"{app_id}:{app_secret}".encode("ascii")).decode("ascii")
        self._secrets = (app_secret, self._basic)
        self._authorize = authorize
        self._request_id = request_id
        self._expiry = str(request_expiry_ms)
        self._expiry_ms = request_expiry_ms
        self._http = http
        self._connect_timeout = connect_timeout_seconds
        self._deadline = deadline_monotonic
        self._max_response_bytes = max_response_bytes
        self._cancel = cancel
        self._wall_clock_ms = wall_clock_ms
        self._monotonic = monotonic
        self._used = False

    def __repr__(self) -> str:
        return f"PrivySignerClient(origin={PRIVY_API_ORIGIN!r}, max_response_bytes={self._max_response_bytes})"

    def rpc(self, wallet_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._used:
            # The first call may have produced a signature: a second call is never a definite refusal.
            raise RpcError("PRIVY_ADAPTER_ALREADY_USED")
        self._used = True
        request_body: dict[str, Any] | None = None
        wire = b""
        try:
            refusal = _refuse_request(wallet_id, body)
            if refusal is None:
                request_body = _wire_body(body)
                wire = _encode(request_body).encode("ascii")
        except Exception:  # noqa: BLE001 - a body that cannot be read, copied or encoded leaves nothing sent
            refusal = "BODY_INVALID"
        if refusal is not None or request_body is None:
            return _local_unsent(refusal or "BODY_INVALID")
        if len(wire) > REQUEST_BYTES_LIMIT:
            return _local_unsent("REQUEST_TOO_LARGE")
        stop = self._stop()
        if stop is not None:
            return _local_unsent(stop)

        url = f"{PRIVY_API_ORIGIN}/v1/wallets/{wallet_id}/rpc"
        privy_headers = {"privy-app-id": self._app_id, "privy-idempotency-key": self._request_id,
                         "privy-request-expiry": self._expiry}
        payload = {"version": 1, "method": "POST", "url": url, "body": request_body, "headers": privy_headers}
        expected = _encode(payload)
        given = copy.deepcopy(payload)
        signature: Any = None
        failed = False
        try:
            signature = self._authorize(given)
        except Exception:  # noqa: BLE001 - any signer failure leaves nothing sent; its text is not kept
            failed = True
        if failed:
            return _local_unsent("AUTHORIZATION_FAILED")
        # Compared as encoded JSON, not with ==: 0 == False and 7 == 7.0 in Python but sign different bytes.
        changed = True
        try:
            changed = _encode(given) != expected
        except Exception:  # noqa: BLE001 - a payload the callback made unencodable was changed
            pass
        if changed:
            return _local_unsent("AUTHORIZATION_PAYLOAD_CHANGED")
        if (not isinstance(signature, str) or len(signature) > SIGNATURE_LIMIT
                or not _SIGNATURE.fullmatch(signature)):
            return _local_unsent("AUTHORIZATION_INVALID")
        # After the local authorization, immediately before the send: no grace interval for a slow signer.
        stop = self._stop()
        if stop is not None:
            return _local_unsent(stop)

        headers = {"authorization": f"Basic {self._basic}", "content-type": "application/json",
                   "privy-authorization-signature": signature, **privy_headers}
        lost = False
        refused = False
        response: Any = None
        try:
            response = self._http.request(method="POST", url=url, headers=headers, body=wire,
                                          timeout=self._connect_timeout, deadline=self._deadline,
                                          max_response_bytes=self._max_response_bytes, cancel=self._cancel)
        except HttpProviderError:
            refused = True
        except Exception:  # noqa: BLE001 - after a possible dispatch every failure keeps the signing liability
            lost = True
        # Raised outside the handlers: the original text may carry provider or credential text.
        if refused:
            raise RpcError("PRIVY_REPLY_REFUSED")
        if lost:
            raise ReplyLost("PRIVY_REPLY_LOST")
        return self._accept(response, signature)

    def _stop(self) -> str | None:
        try:
            if self._cancel is not None and self._cancel():
                return "CANCELLED"
            if self._monotonic() >= self._deadline:
                return "DEADLINE_PASSED"
            if self._wall_clock_ms() >= self._expiry_ms:
                return "REQUEST_EXPIRED"
        except Exception:  # noqa: BLE001 - a failing stop check before send leaves nothing sent; text not kept
            return "STOP_CHECK_FAILED"
        return None

    def _accept(self, response: Any, signature: str) -> Mapping[str, Any]:
        if not isinstance(response, HttpResponse):
            raise RpcError("PRIVY_REPLY_NOT_A_RESPONSE")
        status, headers, raw = response.status, response.headers, response.body
        if (not _is_int(status) or not isinstance(headers, Mapping) or not isinstance(raw, bytes)
                or len(raw) > self._max_response_bytes):
            raise RpcError("PRIVY_REPLY_MALFORMED")
        if self._echoes(headers, raw, signature):
            raise RpcError("PRIVY_REPLY_ECHOED_CREDENTIAL")
        if status != 200:
            raise RpcError("PRIVY_REPLY_STATUS")
        encoding = next((value for name, value in headers.items() if str(name).lower() == "content-encoding"), None)
        if encoding is not None and str(encoding).lower() != "identity":
            raise RpcError("PRIVY_REPLY_ENCODING")
        parsed = _parse(raw)
        if (not isinstance(parsed, dict) or set(parsed) != {"method", "data"} or parsed["method"] != METHOD
                or not isinstance(parsed["data"], dict) or set(parsed["data"]) != {"signed_transaction", "encoding"}):
            raise RpcError("PRIVY_REPLY_UNRECOGNIZED")
        signed, signed_encoding = parsed["data"]["signed_transaction"], parsed["data"]["encoding"]
        if (signed_encoding != "rlp" or not isinstance(signed, str) or not _SIGNED.fullmatch(signed)
                or len(signed) > 2 + 2 * SIGNED_BYTES_LIMIT):
            raise RpcError("PRIVY_REPLY_UNRECOGNIZED")
        return {"data": {"signed_transaction": signed, "encoding": signed_encoding}}

    def _echoes(self, headers: Mapping[Any, Any], raw: bytes, signature: str) -> bool:
        """Whether the reply repeats the app secret, the Basic token or the signature, raw or JSON-decoded."""
        secrets = [item.lower() for item in (*self._secrets, signature)]
        texts = [raw.decode("utf-8", "replace").lower()]
        texts.extend(f"{name} {value}".lower() for name, value in headers.items())
        decoded = _parse(raw)
        pending = [decoded]
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                texts.append(value.lower())
            elif isinstance(value, dict):
                texts.extend(str(key).lower() for key in value)
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        return any(secret in text for secret in secrets for text in texts)


def make_p256_authorizer(*, private_key: ec.EllipticCurvePrivateKey) -> Callable[[Mapping[str, Any]], str]:
    """The `authorize` callable for `PrivySignerClient`, signing with an owned, already loaded P-256 key object.

    The callable refuses any payload outside the request profile this adapter builds (`ValueError`, before signing),
    signs the canonical UTF-8 bytes with ECDSA SHA-256 and returns the DER signature as standard padded Base64.
    It reads the payload without changing it. Construction signs nothing; the caller owns key loading and custody.

    Raises:
        TypeError: `private_key` is not an EC private-key object on SECP256R1 (P-256).
    """
    if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(private_key.curve, ec.SECP256R1):
        raise TypeError("private_key must be an EC P-256 (SECP256R1) private-key object")

    def authorize(payload: Mapping[str, Any]) -> str:
        message = _authorization_message(payload)
        signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(signature).decode("ascii")

    return authorize


def _authorization_message(payload: Any) -> bytes:
    """The bytes to sign for an accepted authorization payload. Raises `ValueError` without input text otherwise."""
    # shortcut: only the accepted ASCII and safe-integer request profile is canonicalized; use a reviewed JCS
    # (RFC 8785) implementation before widening it.
    message = None
    try:
        if _accepted_authorization_payload(payload):
            message = _encode(payload).encode("utf-8")
    except Exception:  # noqa: BLE001 - an unreadable or unencodable payload is refused; its text is not kept
        pass
    # Raised outside the handler: no cause or context keeps payload values.
    if message is None:
        raise ValueError("authorization payload is outside the accepted request profile")
    return message


def _accepted_authorization_payload(payload: Any) -> bool:
    """Whether the payload is exactly what `PrivySignerClient.rpc` signs: fixed ASCII keys, ASCII strings, small
    integers and canonical large-quantity hex strings."""
    if not isinstance(payload, Mapping) or set(payload) != {"version", "method", "url", "body", "headers"}:
        return False
    if not _is_int(payload["version"]) or payload["version"] != 1 or payload["method"] != "POST":
        return False
    url = payload["url"]
    match = _RPC_URL.fullmatch(url) if isinstance(url, str) else None
    if match is None or _refuse_request(match.group(1), payload["body"]) is not None:
        return False
    if not _wire_quantities(payload["body"]):
        return False
    if len(_encode(payload["body"]).encode("ascii")) > REQUEST_BYTES_LIMIT:
        return False
    headers = payload["headers"]
    if not isinstance(headers, Mapping) or set(headers) != SIGNED_HEADERS:
        return False
    app_id, request_id, expiry = (headers["privy-app-id"], headers["privy-idempotency-key"],
                                  headers["privy-request-expiry"])
    return (isinstance(app_id, str) and _APP_ID.fullmatch(app_id) is not None
            and isinstance(request_id, str) and _REQUEST_ID.fullmatch(request_id) is not None
            and isinstance(expiry, str) and _EXPIRY.fullmatch(expiry) is not None)


def _encode(value: Any) -> str:
    """Compact sorted-key ASCII JSON of the accepted value domain. Raises for anything outside it."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("repeated key")  # a contradictory reply: no value is chosen, even an identical one
    return dict(pairs)


def _parse(raw: bytes) -> Any:
    """The decoded JSON value, or None for a reply that is not UTF-8 JSON, repeats a key or nests too deeply."""
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def _quantity(value: Any) -> int | None:
    """An exact unsigned quantity from a Python int or a canonical large-value lowercase `0x` string, or None.

    A string is the wire form of a value above 2**53 - 1 only. A small value stays a JSON number, so a small hex
    string is not the accepted input shape and is refused.
    """
    if type(value) is int:
        return value
    if isinstance(value, str) and _CANONICAL_QUANTITY_HEX.fullmatch(value):
        parsed = int(value, 16)
        return parsed if parsed > MAX_SAFE_INTEGER else None
    return None


def _is_wire_quantity(name: str, value: Any) -> bool:
    """Whether a quantity is exactly the wire form: a small number or a canonical large-value hex string."""
    minimum = 1 if name == "chain_id" else 0
    if type(value) is int:
        return minimum <= value <= MAX_SAFE_INTEGER
    if isinstance(value, str) and _CANONICAL_QUANTITY_HEX.fullmatch(value):
        parsed = int(value, 16)
        return MAX_SAFE_INTEGER < parsed <= MAX_UINT256 and parsed >= minimum
    return False


def _wire_quantities(body: Any) -> bool:
    """The authorizer signs only a body whose quantities are already in the exact wire form."""
    try:
        transaction = body["params"]["transaction"]
    except (KeyError, TypeError):
        return False
    if not isinstance(transaction, Mapping):
        return False
    return all(_is_wire_quantity(name, transaction.get(name)) for name in QUANTITY_FIELDS)


def _wire_body(body: Mapping[str, Any]) -> dict[str, Any]:
    """The exact body to send: small quantities stay numbers, larger ones become canonical hex strings."""
    wire = copy.deepcopy(dict(body))
    transaction: Any = wire["params"]["transaction"]
    for name in QUANTITY_FIELDS:
        value = _quantity(transaction[name])
        if value is None or value > MAX_UINT256:
            raise ValueError("quantity outside the accepted range")
        transaction[name] = value if value <= MAX_SAFE_INTEGER else hex(value)
    return wire


def _refuse_request(wallet_id: Any, body: Any) -> str | None:
    """The stable reason this request is outside the accepted shape, or None. Reads only; never changes the body.

    Every quantity may be an exact unsigned integer from 0 to 2**256 - 1. A canonical lowercase ``0x`` string is the
    wire form of a value above 2**53 - 1; a smaller hex string is refused. ``_wire_body`` keeps a smaller value as a
    number and sends a larger value as the canonical string.
    """
    if not isinstance(wallet_id, str) or not _WALLET_ID.fullmatch(wallet_id):
        return "WALLET_ID_INVALID"
    if not isinstance(body, Mapping):
        return "BODY_INVALID"
    if set(body) - {"method", "params"}:
        return "FIELD_UNSUPPORTED"
    if "method" in body and body["method"] != METHOD:
        return "METHOD_UNSUPPORTED"
    if set(body) != {"method", "params"}:
        return "FIELD_MISSING"
    params = body["params"]
    if not isinstance(params, Mapping):
        return "BODY_INVALID"
    if set(params) != {"transaction"}:
        return "FIELD_UNSUPPORTED" if set(params) - {"transaction"} else "FIELD_MISSING"
    transaction = params["transaction"]
    if not isinstance(transaction, Mapping):
        return "BODY_INVALID"
    if "authorization_list" in transaction:
        return "DELEGATION_UNSUPPORTED"
    if set(transaction) - TRANSACTION_FIELDS:
        return "FIELD_UNSUPPORTED"
    if set(transaction) != TRANSACTION_FIELDS:
        return "FIELD_MISSING"
    if not _is_int(transaction["type"]) or transaction["type"] != 2:
        return "TRANSACTION_TYPE_UNSUPPORTED"
    for name in QUANTITY_FIELDS:
        value = _quantity(transaction[name])
        if value is None or not (1 if name == "chain_id" else 0) <= value <= MAX_UINT256:
            return "QUANTITY_UNSUPPORTED"
    if not isinstance(transaction["to"], str) or not _ADDRESS.fullmatch(transaction["to"]):
        return "ADDRESS_INVALID"
    if not isinstance(transaction["data"], str) or not _DATA.fullmatch(transaction["data"]):
        return "DATA_INVALID"
    return None
