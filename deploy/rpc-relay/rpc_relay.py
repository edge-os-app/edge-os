"""The keyless `/rpc` relay in front of the Monad mainnet provider. Standard library only. See
docs/qualification/inapp-trade/RPC_RELAY.md.

The provider URL holds the key in its path. It lives only in this process's configuration
(`EDGE_OS_RPC_RELAY_UPSTREAM_URL`); the execution worker sees only `https://rpc-a.edgeos.fun/rpc` (observer and quote)
and `https://rpc-b.edgeos.fun/rpc` (broadcast). Coolify's Traefik terminates TLS for both names and forwards each one to
its own port here, so the role is chosen by the listening socket and never by anything the caller sends:

    8545  observer  reads for the quote, the observer and the dry run
    8546  broadcast eth_sendRawTransaction and the two reads it needs

Each request is ONE JSON-RPC call object (no batch, no notification) of at most `MAX_REQUEST_BYTES`. Its method must be
in that role's table and its params must match the method's shape. The relay re-serializes the call and POSTs it once
to the provider; it never forwards a caller header and never follows a redirect. The provider's reply passes through
(a result, or the provider's own JSON-RPC error) only when it is one well-formed reply to that call and names neither
the key, the provider host nor the URL; anything else becomes a fixed relay error. Logs are one JSON line per request
with the role, an allowlisted method name, the outcome, statuses, sizes and duration: never a URL, a param, a body or
an exception message.

Who may call: only Coolify's Traefik (`coolify-proxy`, resolved on the shared network) is admitted at the socket;
Traefik admits only `EDGE_OS_RPC_RELAY_ALLOWED_SOURCES` (the worker's hairpin source). Per role, a token bucket and a
concurrency cap bound the provider spend. `GET /healthz` answers locally for the container health check.

Usage: python rpc_relay.py (configuration from the environment).
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import os
import re
import signal
import socket
import ssl
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

__all__ = ["ConfigError", "METHODS", "ProxyGate", "RelayConfig", "RelayCore", "Reply", "ROLES", "Upstream",
           "UpstreamClient", "UpstreamFailure", "UpstreamReply", "build_server", "load_config", "log_line", "main"]

ROLES = {"observer": 8545, "broadcast": 8546}
MAX_REQUEST_BYTES = 32 * 1024  # a 8 KiB raw transaction is 16,386 hex characters; the worker sends far less
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RAW_TRANSACTION_CHARS = 16386  # the worker's own bound (transaction_rpc_client._allowed)
MAX_FEE_HISTORY_BLOCKS = 1024
MAX_PERCENTILES = 100
RATE_LIMITS = {"observer": (20.0, 60), "broadcast": (2.0, 10)}  # (requests per second, burst)
MAX_CONCURRENT = {"observer": 8, "broadcast": 2}
MAX_CONNECTIONS = 32  # open sockets per role, each with its own thread; more are closed at once
REQUEST_READ_SECONDS = 10.0  # the whole request head and body, from accept; a slower caller is cut off
KEY_FRAGMENT_CHARS = 16  # any echo of this many consecutive key characters withholds a reply
UPSTREAM_CONNECT_SECONDS = 10.0
UPSTREAM_DEADLINE_SECONDS = 15.0
CLIENT_SOCKET_SECONDS = 10.0
PROXY_CACHE_SECONDS = 30.0
PROXY_FAILURE_SECONDS = 2.0  # a failed lookup is retried after this, so an outage cannot stall the accept loop
DEFAULT_TRUSTED_PROXY = "coolify-proxy"
UPSTREAM_ENV, PROXY_ENV = "EDGE_OS_RPC_RELAY_UPSTREAM_URL", "EDGE_OS_RPC_RELAY_TRUSTED_PROXY"

_QUANTITY = re.compile(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_DATA = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
_STRING_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
_HOSTNAME = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]")
_KEY_PATH = re.compile(r"/[A-Za-z0-9._~/-]+")
_PROXY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
_TAGS = frozenset({"latest", "pending", "safe", "finalized", "earliest"})
_MAX_SAFE_ID = 2 ** 53 - 1


# --- configuration -------------------------------------------------------------------------------------------------


class ConfigError(Exception):
    """A refused setting. The message is the stable code only; it never repeats a value."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, repr=False)
class Upstream:
    url: str
    host: str
    port: int
    path: str

    def __repr__(self) -> str:
        return "Upstream(<redacted>)"

    __str__ = __repr__

    def secrets(self) -> tuple[str, ...]:
        """Every text whose presence in a reply would reveal the key or the account endpoint."""
        netloc = self.host if self.port == 443 else f"{self.host}:{self.port}"
        found = {self.url, f"https://{netloc}{self.path}", self.host, netloc, self.path, self.path.strip("/")}
        segments = [segment for segment in self.path.split("/") if len(segment) >= 8]
        found.update(segments)
        for segment in segments:  # partial and hex-encoded echoes of the key
            found.add(segment.encode().hex())
            found.update(segment[i:i + KEY_FRAGMENT_CHARS] for i in range(len(segment) - KEY_FRAGMENT_CHARS + 1))
        return tuple(sorted(value for value in found if value and value != "/"))


@dataclass(frozen=True)
class RelayConfig:
    upstream: Upstream = field(repr=False)
    trusted_proxy: str


def _upstream(value: str | None) -> Upstream:
    if not value:
        raise ConfigError("RELAY_UPSTREAM_URL_MISSING")
    invalid = False
    upstream = None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        port = 443 if parts.port is None else parts.port
        invalid = (not value.isprintable() or any(c.isspace() for c in value) or "?" in value or "#" in value
                   or parts.scheme != "https" or parts.username is not None or parts.password is not None
                   or not _HOSTNAME.fullmatch(host) or not 0 < port < 65536 or parts.netloc.lower() not in (
                       host, f"{host}:{port}")
                   or not _KEY_PATH.fullmatch(parts.path) or parts.path.strip("/") == ""
                   or "/../" in f"{parts.path}/" or "/./" in f"{parts.path}/")
        if not invalid:
            upstream = Upstream(url=value, host=host, port=port, path=parts.path)
    except ValueError:
        invalid = True
    if invalid or upstream is None:
        raise ConfigError("RELAY_UPSTREAM_URL_INVALID")
    return upstream


def load_config(environ: Mapping[str, str]) -> RelayConfig:
    upstream = _upstream(environ.get(UPSTREAM_ENV))
    proxy = environ.get(PROXY_ENV, DEFAULT_TRUSTED_PROXY)
    if type(proxy) is not str or not _PROXY_NAME.fullmatch(proxy):
        raise ConfigError("RELAY_TRUSTED_PROXY_INVALID")
    return RelayConfig(upstream=upstream, trusted_proxy=proxy)


# --- method tables -------------------------------------------------------------------------------------------------


def _match(pattern: re.Pattern[str], value: Any) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _tag(value: Any) -> bool:
    return type(value) is str and (value in _TAGS or _QUANTITY.fullmatch(value) is not None)


_CALL_FIELDS: dict[str, re.Pattern[str]] = {
    "from": _ADDRESS, "to": _ADDRESS, "gas": _QUANTITY, "gasPrice": _QUANTITY, "maxFeePerGas": _QUANTITY,
    "maxPriorityFeePerGas": _QUANTITY, "value": _QUANTITY, "data": _DATA, "input": _DATA, "nonce": _QUANTITY,
    "type": _QUANTITY, "chainId": _QUANTITY,
}


def _call_object(value: Any) -> bool:
    return (type(value) is dict and bool(value) and set(value) <= set(_CALL_FIELDS)
            and all(_match(_CALL_FIELDS[key], item) for key, item in value.items()))


def _no_params(params: list[Any]) -> bool:
    return params == []


def _call(params: list[Any]) -> bool:  # no third (state override) argument
    return len(params) == 2 and _call_object(params[0]) and _tag(params[1])


def _estimate(params: list[Any]) -> bool:
    return len(params) in (1, 2) and _call_object(params[0]) and (len(params) == 1 or _tag(params[1]))


def _account_at(params: list[Any]) -> bool:
    return len(params) == 2 and _match(_ADDRESS, params[0]) and _tag(params[1])


def _block(params: list[Any]) -> bool:  # header and hashes only: never full transaction bodies
    return len(params) == 2 and _tag(params[0]) and params[1] is False


def _by_hash(params: list[Any]) -> bool:
    return len(params) == 1 and _match(_HASH, params[0])


def _fee_history(params: list[Any]) -> bool:
    if len(params) not in (2, 3) or not _tag(params[1]):
        return False
    count = params[0]
    if type(count) is str and _QUANTITY.fullmatch(count):
        count = int(count, 16)
    if type(count) is not int or not 1 <= count <= MAX_FEE_HISTORY_BLOCKS:
        return False
    if len(params) == 3:
        percentiles = params[2]
        if type(percentiles) is not list or len(percentiles) > MAX_PERCENTILES:
            return False
        previous = 0.0
        for item in percentiles:
            if type(item) not in (int, float) or not math.isfinite(item) or not previous <= item <= 100:
                return False
            previous = item
    return True


def _raw_transaction(params: list[Any]) -> bool:
    return (len(params) == 1 and _match(_DATA, params[0])
            and 2 < len(params[0]) <= MAX_RAW_TRANSACTION_CHARS)


METHODS: dict[str, dict[str, Callable[[list[Any]], bool]]] = {
    "observer": {
        "eth_chainId": _no_params, "eth_blockNumber": _no_params, "eth_gasPrice": _no_params,
        "eth_maxPriorityFeePerGas": _no_params, "eth_call": _call, "eth_estimateGas": _estimate,
        "eth_getBalance": _account_at, "eth_getCode": _account_at, "eth_getTransactionCount": _account_at,
        "eth_getBlockByNumber": _block, "eth_getTransactionReceipt": _by_hash, "eth_getTransactionByHash": _by_hash,
        "eth_feeHistory": _fee_history,
    },
    "broadcast": {
        "eth_chainId": _no_params, "eth_getTransactionCount": _account_at,
        "eth_sendRawTransaction": _raw_transaction,
    },
}
LOGGED_METHODS = frozenset({"-"}.union(*METHODS.values()))


# --- the relay core ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class UpstreamReply:
    status: int
    headers: Mapping[str, str]
    body: bytes


class UpstreamFailure(Exception):
    """The provider could not be reached or read. It carries no detail on purpose."""

    def __init__(self) -> None:
        super().__init__("UPSTREAM_UNREACHABLE")


@dataclass(frozen=True)
class Reply:
    status: int
    body: bytes
    outcome: str


class TokenBucket:
    def __init__(self, rate: float, burst: int, clock: Callable[[], float]) -> None:
        self.rate, self.burst, self.clock = rate, burst, clock
        self.tokens, self.last = float(burst), clock()
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            now = self.clock()
            self.tokens = min(float(self.burst), self.tokens + max(0.0, now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("duplicate JSON field")
    return dict(pairs)


def _no_constant(_: str) -> Any:
    raise ValueError("non-JSON constant")


def _parse(raw: bytes) -> tuple[bool, Any]:
    try:
        return True, json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except (ValueError, UnicodeError, RecursionError):
        return False, None


def _encode(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _valid_id(value: Any) -> bool:
    return ((type(value) is int and -_MAX_SAFE_ID <= value <= _MAX_SAFE_ID)
            or (type(value) is str and _STRING_ID.fullmatch(value) is not None))


def _error_body(ident: Any, code: int, message: str) -> bytes:
    return _encode({"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}})


# outcome -> (HTTP status, JSON-RPC code, message). Messages are fixed text: nothing from the caller or provider.
REFUSALS: dict[str, tuple[int, int, str]] = {
    "rate_limited": (429, -32005, "rate limit exceeded"),
    "busy": (429, -32005, "too many concurrent requests"),
    "body_too_large": (413, -32005, "request body too large"),
    "parse_error": (400, -32700, "parse error"),
    "batch_refused": (400, -32600, "batch requests are not accepted"),
    "invalid_request": (400, -32600, "invalid request"),
    "method_not_allowed": (403, -32601, "method not allowed on this endpoint"),
    "invalid_params": (400, -32602, "invalid params for this method"),
    "upstream_unreachable": (502, -32603, "upstream unavailable"),
    "upstream_reply_invalid": (502, -32603, "upstream reply invalid"),
    "upstream_reply_withheld": (502, -32603, "upstream reply withheld"),
    "peer_refused": (403, -32600, "caller not admitted"),
    "not_found": (404, -32600, "not found"),
    "method_refused": (405, -32600, "method not allowed"),
    "length_required": (411, -32600, "content length required"),
    "bad_length": (400, -32600, "invalid content length"),
    "unsupported_type": (415, -32600, "content type must be application/json"),
    "body_incomplete": (400, -32600, "request body incomplete"),
    "handler_error": (500, -32603, "internal error"),
}


def refusal(outcome: str, ident: Any = None) -> Reply:
    status, code, message = REFUSALS[outcome]
    return Reply(status=status, body=_error_body(ident, code, message), outcome=outcome)


class RelayCore:
    """One role's rules: limit, parse, check, forward once, check the reply. Upstream, clock and log are injectable."""

    def __init__(self, *, role: str, upstream: Callable[[bytes], UpstreamReply], secrets: tuple[str, ...],
                 clock: Callable[[], float] = time.monotonic,
                 log: Callable[[dict[str, Any]], None] | None = None) -> None:
        if role not in ROLES:
            raise ValueError("RELAY_ROLE_INVALID")
        self.role, self.upstream, self.clock = role, upstream, clock
        self.secrets = tuple(secret.lower() for secret in secrets if secret)
        self.log = log or log_line
        rate, burst = RATE_LIMITS[role]
        self.bucket = TokenBucket(rate, burst, clock)
        self.methods = METHODS[role]

    def record(self, *, method: str, outcome: str, status: int, upstream_status: int | None, started: float,
               bytes_in: int, bytes_out: int) -> None:
        self.log({"role": self.role, "method": method if method in LOGGED_METHODS else "-", "outcome": outcome,
                  "status": status, "upstream_status": upstream_status,
                  "ms": int(max(0.0, self.clock() - started) * 1000), "bytes_in": bytes_in, "bytes_out": bytes_out})

    def refuse(self, outcome: str, *, bytes_in: int = 0, started: float | None = None) -> Reply:
        reply = refusal(outcome)
        self.record(method="-", outcome=outcome, status=reply.status, upstream_status=None,
                    started=self.clock() if started is None else started, bytes_in=bytes_in,
                    bytes_out=len(reply.body))
        return reply

    def handle(self, body: bytes) -> Reply:
        started = self.clock()
        method, upstream_status = "-", None
        reply = self._handle(body)
        if isinstance(reply, tuple):
            reply, method, upstream_status = reply
        self.record(method=method, outcome=reply.outcome, status=reply.status, upstream_status=upstream_status,
                    started=started, bytes_in=len(body), bytes_out=len(reply.body))
        return reply

    def _handle(self, body: bytes) -> Reply | tuple[Reply, str, int | None]:
        if len(body) > MAX_REQUEST_BYTES:
            return refusal("body_too_large")
        parsed, request = _parse(body)
        if not parsed:
            return refusal("parse_error")
        if type(request) is list:
            return refusal("batch_refused")
        if (type(request) is not dict or not {"jsonrpc", "id", "method"} <= set(request)
                or not set(request) <= {"jsonrpc", "id", "method", "params"}
                or request["jsonrpc"] != "2.0" or not _valid_id(request["id"])):
            return refusal("invalid_request")
        ident, method = request["id"], request["method"]
        if type(method) is not str:
            return refusal("invalid_request", ident)
        logged = method if method in LOGGED_METHODS else "-"
        if method not in self.methods:
            return refusal("method_not_allowed", ident), logged, None
        params = request.get("params", [])
        if type(params) is not list or not self.methods[method](params):
            return refusal("invalid_params", ident), logged, None
        if not self.bucket.take():  # only calls that would reach the provider spend the budget
            return refusal("rate_limited", ident), logged, None
        wire = _encode({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        answer = None
        try:
            answer = self.upstream(wire)
        except Exception:
            pass  # the exception text may name the provider; it is dropped, never logged
        if not isinstance(answer, UpstreamReply):
            return refusal("upstream_unreachable", ident), logged, None
        return self._reply(ident, answer), logged, answer.status if type(answer.status) is int else None

    def _leaks(self, text: str) -> bool:
        lowered = text.lower()
        decoded = unquote(lowered).lower()  # a percent-encoded echo
        return any(secret in lowered or secret in decoded for secret in self.secrets)

    def _reply(self, ident: Any, answer: UpstreamReply) -> Reply:
        try:
            if (type(answer.status) is not int or type(answer.body) is not bytes
                    or len(answer.body) > MAX_RESPONSE_BYTES):
                return refusal("upstream_reply_invalid", ident)
            encoding = [value for key, value in dict(answer.headers).items() if str(key).lower() == "content-encoding"]
            if any(str(value).strip().lower() != "identity" for value in encoding):
                return refusal("upstream_reply_invalid", ident)
            if self._leaks(answer.body.decode("utf-8", "replace")):
                return refusal("upstream_reply_withheld", ident)
            parsed, value = _parse(answer.body)
            if not parsed or type(value) is not dict or value.get("jsonrpc") != "2.0":
                return refusal("upstream_reply_invalid", ident)
            if set(value) == {"jsonrpc", "id", "result"}:
                if answer.status != 200 or type(value["id"]) is not type(ident) or value["id"] != ident:
                    return refusal("upstream_reply_invalid", ident)
                out, status = {"jsonrpc": "2.0", "id": ident, "result": value["result"]}, 200
            elif set(value) == {"jsonrpc", "id", "error"}:
                error = value["error"]
                same = value["id"] is None or (type(value["id"]) is type(ident) and value["id"] == ident)
                if (not same or type(error) is not dict or not {"code", "message"} <= set(error)
                        or not set(error) <= {"code", "message", "data"} or type(error["code"]) is not int
                        or type(error["message"]) is not str
                        or not (answer.status == 200 or 400 <= answer.status <= 599)):
                    return refusal("upstream_reply_invalid", ident)
                out, status = {"jsonrpc": "2.0", "id": ident, "error": error}, answer.status
            else:
                return refusal("upstream_reply_invalid", ident)
            encoded = _encode(out)
            if self._leaks(encoded.decode("utf-8")):
                return refusal("upstream_reply_withheld", ident)
            if len(encoded) > MAX_RESPONSE_BYTES:
                return refusal("upstream_reply_invalid", ident)
            return Reply(status=status, body=encoded, outcome="forwarded")
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return refusal("upstream_reply_invalid", ident)


def log_line(record: Mapping[str, Any]) -> None:
    """One JSON line on stdout. Callers pass fixed fields only (see `RelayCore.record`)."""
    print(json.dumps({"at": round(time.time(), 3), **record}, sort_keys=True), flush=True)


# --- the provider client -------------------------------------------------------------------------------------------


class UpstreamClient:
    """One HTTPS POST to the configured provider per call. No redirect, no retry, no caller header."""

    HEADERS = {"Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity",
               "User-Agent": "edge-os-rpc-relay"}

    def __init__(self, upstream: Upstream, *, connect: Callable[..., Any] = http.client.HTTPSConnection,
                 timeout: float = UPSTREAM_CONNECT_SECONDS, deadline: float = UPSTREAM_DEADLINE_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._upstream, self._connect, self._timeout, self._deadline = upstream, connect, timeout, deadline
        self._clock = clock
        self._context = ssl.create_default_context()

    def __repr__(self) -> str:
        return "UpstreamClient(<redacted>)"

    def _bound(self, connection: Any, until: float) -> None:
        """Each socket operation gets only the time left in the whole call, never a renewed timeout."""
        sock = getattr(connection, "sock", None)
        if sock is not None:
            sock.settimeout(max(0.001, min(self._timeout, until - self._clock())))

    def __call__(self, body: bytes) -> UpstreamReply:
        reply, connection = None, None
        until = self._clock() + self._deadline
        try:
            connection = self._connect(self._upstream.host, self._upstream.port, timeout=self._timeout,
                                       context=self._context)
            connection.request("POST", self._upstream.path, body=body, headers=dict(self.HEADERS))
            self._bound(connection, until)
            response = connection.getresponse()
            data = b""
            while len(data) <= MAX_RESPONSE_BYTES and self._clock() < until:
                self._bound(connection, until)
                chunk = response.read(min(64 * 1024, MAX_RESPONSE_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data += chunk
            if self._clock() < until:
                reply = UpstreamReply(status=int(response.status),
                                      headers={str(k).lower(): str(v) for k, v in response.getheaders()}, body=data)
        except Exception:
            reply = None  # never keep the exception: its text or traceback can name the provider
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        if reply is None:
            raise UpstreamFailure()
        return reply


# --- who may call --------------------------------------------------------------------------------------------------


def _resolve(name: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)]


def _address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped if mapped is not None else ip


class ProxyGate:
    """Admits a socket peer only when it is the trusted proxy's current address on the shared network."""

    def __init__(self, name: str, *, resolve: Callable[[str], list[str]] = _resolve,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.name, self.resolve, self.clock = name, resolve, clock
        self.addresses: frozenset[Any] = frozenset()
        self.resolved_at: float | None = None
        self.failed_at: float | None = None
        self.lock = threading.Lock()

    def _current(self) -> frozenset[Any]:
        with self.lock:
            now = self.clock()
            if self.resolved_at is not None and now - self.resolved_at <= PROXY_CACHE_SECONDS:
                return self.addresses
            if self.failed_at is not None and now - self.failed_at <= PROXY_FAILURE_SECONDS:
                return frozenset()
        # The lookup runs outside the lock, so one slow answer never stalls requests that use a fresh cache.
        found: frozenset[Any] = frozenset()
        try:
            answers = [_address(answer) for answer in self.resolve(self.name)]
            if answers and all(answer is not None for answer in answers):
                found = frozenset(answers)
        except Exception:
            found = frozenset()
        with self.lock:  # a failure refuses for PROXY_FAILURE_SECONDS only, never longer
            if found:
                self.addresses, self.resolved_at, self.failed_at = found, now, None
            else:
                self.failed_at = now
        return found

    def __call__(self, peer: str) -> bool:
        address = _address(peer)
        return address is not None and address in self._current()


# --- HTTP ----------------------------------------------------------------------------------------------------------


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address: tuple[str, int], core: RelayCore, admit_peer: Callable[[str], bool]) -> None:
        self.core, self.admit_peer = core, admit_peer
        self.slots = threading.BoundedSemaphore(MAX_CONCURRENT[core.role])
        self.connections = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.reading: dict[Any, float] = {}  # socket -> read deadline, until its request is read
        self.reading_lock = threading.Lock()
        super().__init__(address, RelayHandler)

    def _note(self, outcome: str) -> None:
        self.core.record(method="-", outcome=outcome, status=0, upstream_status=None, started=self.core.clock(),
                         bytes_in=0, bytes_out=0)

    def verify_request(self, request: Any, client_address: Any) -> bool:
        # Before any slot or thread is spent: only the proxy, or loopback (the container's own health check).
        # A loopback caller still meets the proxy check on POST /rpc.
        peer = str(client_address[0])
        address = _address(peer)
        if (address is not None and address.is_loopback) or self.admit_peer(peer):
            return True
        self._note("peer_refused")
        return False

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.connections.acquire(blocking=False):
            self._note("connection_refused")
            self.shutdown_request(request)
            return
        with self.reading_lock:
            self.reading[request] = time.monotonic() + REQUEST_READ_SECONDS
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.request_read(request)
            self.connections.release()  # the thread never started: its slot must not leak
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_read(request)
            self.connections.release()

    def request_read(self, request: Any) -> None:
        with self.reading_lock:
            self.reading.pop(request, None)

    def service_actions(self) -> None:
        # Called by serve_forever between polls: cut off callers still sending their request after the deadline.
        now = time.monotonic()
        with self.reading_lock:
            late = [sock for sock, until in self.reading.items() if until <= now]
            for sock in late:
                self.reading.pop(sock, None)
        for sock in late:
            self._note("read_timeout")
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def handle_error(self, request: Any, client_address: Any) -> None:
        # The default prints a traceback to stderr; only the outcome is written here.
        self.core.record(method="-", outcome="handler_error", status=500, upstream_status=None,
                         started=self.core.clock(), bytes_in=0, bytes_out=0)


class RelayHandler(BaseHTTPRequestHandler):
    server: RelayServer
    protocol_version = "HTTP/1.1"
    server_version = "edge-os-rpc-relay"
    timeout = CLIENT_SOCKET_SECONDS

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base class signature
        return None

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # The base class answers with an HTML page; keep the JSON-RPC error form and fixed text.
        self.close_connection = True
        self._send(code, _error_body(None, -32600, "bad request"))

    def _send(self, status: int, body: bytes) -> None:
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _refuse(self, outcome: str, bytes_in: int = 0) -> None:
        reply = self.server.core.refuse(outcome, bytes_in=bytes_in)
        self._send(reply.status, reply.body)

    def _target(self) -> str:
        """The request target exactly as sent: the base class folds a leading `//` into `/`."""
        words = self.requestline.split(" ")
        return words[1] if len(words) == 3 else ""

    def _wrong_method(self) -> None:
        self._refuse("method_refused" if self._target() in ("/rpc", "/healthz") else "not_found")

    def do_GET(self) -> None:  # noqa: N802 - the base class naming
        if self._target() == "/healthz":
            self._send(200, _encode({"status": "ok", "role": self.server.core.role}))
        else:
            self._wrong_method()

    do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _wrong_method

    def do_POST(self) -> None:  # noqa: N802 - the base class naming
        if self._target() != "/rpc":
            self._wrong_method()
            return
        if not self.server.admit_peer(str(self.client_address[0])):
            self._refuse("peer_refused")
            return
        if self.headers.get_all("Transfer-Encoding"):
            self._refuse("length_required")
            return
        lengths = self.headers.get_all("Content-Length") or []
        if not lengths:
            self._refuse("length_required")
            return
        if len(lengths) != 1 or not re.fullmatch(r"0|[1-9][0-9]{0,15}", lengths[0]):
            self._refuse("bad_length")
            return
        length = int(lengths[0])
        if length > MAX_REQUEST_BYTES:
            self._refuse("body_too_large")
            return
        kind = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if kind != "application/json":
            self._refuse("unsupported_type")
            return
        try:
            body = self.rfile.read(length)
        except OSError:
            body = b""
        self.server.request_read(self.request)
        if len(body) != length:
            self._refuse("body_incomplete", bytes_in=len(body))
            return
        if not self.server.slots.acquire(blocking=False):
            self._refuse("busy", bytes_in=len(body))
            return
        try:
            try:
                reply = self.server.core.handle(body)
            except Exception:
                reply = self.server.core.refuse("handler_error", bytes_in=len(body))
        finally:
            self.server.slots.release()
        self._send(reply.status, reply.body)


def build_server(core: RelayCore, *, admit_peer: Callable[[str], bool], host: str = "0.0.0.0",
                 port: int | None = None) -> RelayServer:
    return RelayServer((host, ROLES[core.role] if port is None else port), core, admit_peer)


def main() -> int:  # pragma: no cover - exercised by the deployment checks in RPC_RELAY.md
    try:
        config = load_config(os.environ)
    except ConfigError as error:
        log_line({"outcome": "config_refused", "code": error.code})
        return 2
    client = UpstreamClient(config.upstream)
    gate = ProxyGate(config.trusted_proxy)
    servers = [build_server(RelayCore(role=role, upstream=client, secrets=config.upstream.secrets()),
                            admit_peer=gate) for role in ROLES]
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        log_line({"outcome": "listening", "role": server.core.role, "port": server.server_address[1]})
    stop.wait()
    for server in servers:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
