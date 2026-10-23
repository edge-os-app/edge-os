"""The relay's configuration, request rules, upstream handling, limits and logs. Pure: fakes only, no socket."""

from __future__ import annotations

import json
from typing import Any

import pytest

import rpc_relay as relay
from relay_support import SENTINEL_HOST, SENTINEL_KEY, SENTINEL_URL

SECRETS = (SENTINEL_KEY, SENTINEL_HOST, SENTINEL_URL)


class FakeUpstream:
    """Records every forwarded body and answers from a script (a callable or a fixed reply)."""

    def __init__(self, answer: Any = None) -> None:
        self.bodies: list[bytes] = []
        self.answer = answer

    def __call__(self, body: bytes) -> relay.UpstreamReply:
        self.bodies.append(body)
        if callable(self.answer):
            return self.answer(json.loads(body))
        if isinstance(self.answer, relay.UpstreamReply):
            return self.answer
        request = json.loads(body)
        return reply_for(request, {"result": "0x8f"})


def reply_for(request: dict[str, Any], fields: dict[str, Any], status: int = 200,
              headers: dict[str, str] | None = None) -> relay.UpstreamReply:
    body = json.dumps({"jsonrpc": "2.0", "id": request["id"], **fields}).encode()
    return relay.UpstreamReply(status=status, headers=headers or {"content-type": "application/json"}, body=body)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_core(role: str, upstream: FakeUpstream | None = None, clock: Clock | None = None,
              logs: list[dict[str, Any]] | None = None) -> relay.RelayCore:
    config = relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL})
    return relay.RelayCore(role=role, upstream=upstream or FakeUpstream(), secrets=config.upstream.secrets(),
                           clock=clock or Clock(), log=(logs.append if logs is not None else lambda record: None))


def call(method: str, params: Any = None, ident: Any = 7, **extra: Any) -> bytes:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": ident, "method": method, **extra}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload).encode()


def error_of(reply: relay.Reply) -> dict[str, Any]:
    body = json.loads(reply.body)
    assert set(body) == {"jsonrpc", "id", "error"}, body
    return body["error"]


def assert_no_secret(*texts: Any) -> None:
    for text in texts:
        rendered = text.decode("utf-8", "replace") if isinstance(text, bytes) else json.dumps(text, default=str)
        lowered = rendered.lower()
        for secret in SECRETS:
            assert secret.lower() not in lowered, f"secret leaked: {rendered[:200]}"


ADDRESS = "0x" + "ab" * 20
HASH = "0x" + "cd" * 32
CALL = {"to": ADDRESS, "data": "0x0902f1ac"}


# --- configuration -----------------------------------------------------------------------------------------------


def test_the_upstream_url_loads_and_never_appears_in_a_repr():
    config = relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL})
    assert config.upstream.host == SENTINEL_HOST
    assert config.upstream.port == 443
    assert config.upstream.path == f"/{SENTINEL_KEY}/"
    assert config.trusted_proxy == "coolify-proxy"
    assert_no_secret(repr(config), str(config), repr(config.upstream), str(config.upstream))


@pytest.mark.parametrize("value, code", [
    (None, "RELAY_UPSTREAM_URL_MISSING"),
    ("", "RELAY_UPSTREAM_URL_MISSING"),
    (f"http://{SENTINEL_HOST}/{SENTINEL_KEY}/", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://{SENTINEL_HOST}/", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://{SENTINEL_HOST}", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://{SENTINEL_HOST}/{SENTINEL_KEY}/?k=1", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://{SENTINEL_HOST}/{SENTINEL_KEY}/#f", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://user:pw@{SENTINEL_HOST}/{SENTINEL_KEY}/", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://{SENTINEL_HOST}/{SENTINEL_KEY}/ x", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://{SENTINEL_HOST}:0/{SENTINEL_KEY}/", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https://127.0.0.1/{SENTINEL_KEY}/", "RELAY_UPSTREAM_URL_INVALID"),
    (f"https:///{SENTINEL_KEY}/", "RELAY_UPSTREAM_URL_INVALID"),
])
def test_a_bad_upstream_url_is_refused_without_repeating_it(value, code):
    environ = {} if value is None else {"EDGE_OS_RPC_RELAY_UPSTREAM_URL": value}
    with pytest.raises(relay.ConfigError) as caught:
        relay.load_config(environ)
    assert caught.value.code == code
    assert str(caught.value) == code
    assert_no_secret(str(caught.value), repr(caught.value), caught.value.args)


@pytest.mark.parametrize("name", ["", "a b", "x" * 254, "-bad", "bad/name"])
def test_a_bad_trusted_proxy_name_is_refused(name):
    with pytest.raises(relay.ConfigError) as caught:
        relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL, "EDGE_OS_RPC_RELAY_TRUSTED_PROXY": name})
    assert caught.value.code == "RELAY_TRUSTED_PROXY_INVALID"


def test_the_trusted_proxy_name_can_be_set():
    config = relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL,
                                "EDGE_OS_RPC_RELAY_TRUSTED_PROXY": "edge-proxy"})
    assert config.trusted_proxy == "edge-proxy"


def test_the_secrets_cover_the_url_host_and_key():
    secrets = relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL}).upstream.secrets()
    assert SENTINEL_KEY in secrets and SENTINEL_HOST in secrets and SENTINEL_URL in secrets


# --- method tables -----------------------------------------------------------------------------------------------


def test_the_method_tables_are_the_reviewed_sets():
    assert set(relay.METHODS["observer"]) == {
        "eth_chainId", "eth_blockNumber", "eth_call", "eth_estimateGas", "eth_getBalance", "eth_getCode",
        "eth_getTransactionCount", "eth_getBlockByNumber", "eth_getTransactionReceipt", "eth_getTransactionByHash",
        "eth_gasPrice", "eth_maxPriorityFeePerGas", "eth_feeHistory"}
    assert set(relay.METHODS["broadcast"]) == {"eth_chainId", "eth_getTransactionCount", "eth_sendRawTransaction"}
    assert set(relay.ROLES) == {"observer", "broadcast"}
    assert relay.ROLES == {"observer": 8545, "broadcast": 8546}


OBSERVER_CALLS = [
    ("eth_chainId", []),
    ("eth_chainId", None),
    ("eth_blockNumber", []),
    ("eth_gasPrice", []),
    ("eth_maxPriorityFeePerGas", []),
    ("eth_call", [CALL, "latest"]),
    ("eth_call", [CALL, "finalized"]),
    ("eth_call", [CALL, "0x1a2b"]),
    ("eth_estimateGas", [{"from": ADDRESS, "to": ADDRESS, "data": "0x", "value": "0x0"}]),
    ("eth_estimateGas", [{"from": ADDRESS, "to": ADDRESS, "data": "0x095ea7b3"}, "latest"]),
    ("eth_getBalance", [ADDRESS, "finalized"]),
    ("eth_getCode", [ADDRESS, "latest"]),
    ("eth_getTransactionCount", [ADDRESS, "pending"]),
    ("eth_getBlockByNumber", ["finalized", False]),
    ("eth_getBlockByNumber", ["0x10", False]),
    ("eth_getTransactionReceipt", [HASH]),
    ("eth_getTransactionByHash", [HASH]),
    ("eth_feeHistory", ["0x4", "latest", [25, 50, 75]]),
    ("eth_feeHistory", [4, "latest"]),
]


@pytest.mark.parametrize("method, params", OBSERVER_CALLS)
def test_the_observer_forwards_each_allowed_read_once_in_canonical_form(method, params):
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(call(method, params))
    assert reply.status == 200, reply.body
    assert json.loads(reply.body) == {"jsonrpc": "2.0", "id": 7, "result": "0x8f"}
    assert len(upstream.bodies) == 1
    forwarded = json.loads(upstream.bodies[0])
    assert forwarded == {"jsonrpc": "2.0", "id": 7, "method": method, "params": params if params is not None else []}


RAW = "0x02f8" + "ab" * 100


@pytest.mark.parametrize("method, params", [
    ("eth_chainId", []),
    ("eth_getTransactionCount", [ADDRESS, "pending"]),
    ("eth_getTransactionCount", [ADDRESS, "latest"]),
    ("eth_sendRawTransaction", [RAW]),
])
def test_the_broadcast_endpoint_forwards_only_its_methods(method, params):
    upstream = FakeUpstream()
    reply = make_core("broadcast", upstream).handle(call(method, params))
    assert reply.status == 200, reply.body
    assert len(upstream.bodies) == 1


FORBIDDEN_EVERYWHERE = ["eth_sendTransaction", "eth_sign", "eth_signTransaction", "eth_signTypedData_v4",
                        "eth_accounts", "eth_getLogs", "eth_newFilter", "eth_subscribe", "debug_traceTransaction",
                        "trace_block", "admin_peers", "personal_unlockAccount", "txpool_content", "qn_getBlockWithReceipts",
                        "net_version", "web3_clientVersion", "ETH_CHAINID", "eth_chainId ", "rpc.discover", ""]


@pytest.mark.parametrize("role", ["observer", "broadcast"])
@pytest.mark.parametrize("method", FORBIDDEN_EVERYWHERE)
def test_a_method_outside_the_table_is_refused_before_the_upstream(role, method):
    upstream = FakeUpstream()
    logs: list[dict[str, Any]] = []
    reply = make_core(role, upstream, logs=logs).handle(call(method, []))
    assert reply.status == 403
    assert error_of(reply)["code"] == -32601
    assert upstream.bodies == []
    assert all(record["method"] in relay.LOGGED_METHODS for record in logs)


@pytest.mark.parametrize("method, params", [
    ("eth_sendRawTransaction", [RAW]),
])
def test_the_observer_never_broadcasts(method, params):
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(call(method, params))
    assert reply.status == 403 and upstream.bodies == []


@pytest.mark.parametrize("method, params", [
    ("eth_call", [CALL, "latest"]),
    ("eth_getBalance", [ADDRESS, "latest"]),
    ("eth_getTransactionReceipt", [HASH]),
    ("eth_estimateGas", [CALL]),
    ("eth_getCode", [ADDRESS, "latest"]),
])
def test_the_broadcast_endpoint_serves_no_general_reads(method, params):
    upstream = FakeUpstream()
    reply = make_core("broadcast", upstream).handle(call(method, params))
    assert reply.status == 403 and upstream.bodies == []


@pytest.mark.parametrize("method, params", [
    ("eth_chainId", [1]),
    ("eth_chainId", {}),
    ("eth_call", [CALL]),
    ("eth_call", [CALL, "latest", {ADDRESS: {"balance": "0x1"}}]),  # state override
    ("eth_call", [{**CALL, "extra": "0x1"}, "latest"]),
    ("eth_call", [{"to": "0x1234", "data": "0x"}, "latest"]),
    ("eth_call", [{"to": ADDRESS, "data": "0x123"}, "latest"]),
    ("eth_call", [CALL, "earliestish"]),
    ("eth_call", [CALL, {"blockHash": HASH}]),
    ("eth_call", [CALL, "0x01"]),
    ("eth_call", ["not an object", "latest"]),
    ("eth_estimateGas", [CALL, "latest", {}]),
    ("eth_getBalance", [ADDRESS]),
    ("eth_getBalance", ["0xzz" + "a" * 38, "latest"]),
    ("eth_getBlockByNumber", ["latest", True]),
    ("eth_getBlockByNumber", ["latest"]),
    ("eth_getTransactionReceipt", ["0x1234"]),
    ("eth_getTransactionReceipt", [HASH, HASH]),
    ("eth_feeHistory", ["0x401", "latest", []]),
    ("eth_feeHistory", [1025, "latest"]),
    ("eth_feeHistory", [True, "latest"]),
    ("eth_feeHistory", ["0x4", "latest", [50] * 101]),
    ("eth_feeHistory", ["0x4", "latest", [101]]),
])
def test_bad_observer_params_are_refused(method, params):
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(call(method, params))
    assert reply.status == 400, reply.body
    assert error_of(reply)["code"] == -32602
    assert upstream.bodies == []


@pytest.mark.parametrize("params", [
    [], ["0x"], ["0x0"], ["02f8ab"], ["0x" + "zz" * 10], [RAW, RAW], ["0x" + "ab" * 8193], [123],
])
def test_bad_raw_transactions_are_refused(params):
    upstream = FakeUpstream()
    reply = make_core("broadcast", upstream).handle(call("eth_sendRawTransaction", params))
    assert reply.status == 400 and error_of(reply)["code"] == -32602 and upstream.bodies == []


def test_the_largest_accepted_raw_transaction_matches_the_worker_bound():
    upstream = FakeUpstream()
    raw = "0x" + "ab" * 8192
    assert len(raw) == 16386
    reply = make_core("broadcast", upstream).handle(call("eth_sendRawTransaction", [raw]))
    assert reply.status == 200 and len(upstream.bodies) == 1


# --- request shape: batch, notifications, parse ------------------------------------------------------------------


@pytest.mark.parametrize("body", [
    b"[]",
    json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}]).encode(),
    json.dumps([{"jsonrpc": "2.0", "id": i, "method": "eth_chainId", "params": []} for i in range(50)]).encode(),
])
@pytest.mark.parametrize("role", ["observer", "broadcast"])
def test_a_batch_is_refused_whatever_it_holds(role, body):
    upstream = FakeUpstream()
    reply = make_core(role, upstream).handle(body)
    assert reply.status == 400
    assert error_of(reply)["code"] == -32600
    assert json.loads(reply.body)["id"] is None
    assert upstream.bodies == []


@pytest.mark.parametrize("body", [
    json.dumps({"jsonrpc": "2.0", "method": "eth_chainId", "params": []}).encode(),  # notification
    json.dumps({"jsonrpc": "2.0", "id": None, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": True, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": 1.5, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": 2 ** 53, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": "x" * 65, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": "a\nb", "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": {}, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "1.0", "id": 1, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"id": 1, "method": "eth_chainId", "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": 1, "method": 5, "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": 1, "params": []}).encode(),
    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": [], "x": 1}).encode(),
    json.dumps("eth_chainId").encode(),
    b"7",
])
def test_a_request_that_is_not_one_plain_call_is_refused(body):
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(body)
    assert reply.status == 400
    assert error_of(reply)["code"] == -32600
    assert upstream.bodies == []


@pytest.mark.parametrize("body", [
    b"", b"{", b"\xff\xfe", b'{"jsonrpc":"2.0","id":1,"id":2,"method":"eth_chainId","params":[]}',
    b'{"jsonrpc":"2.0","id":NaN,"method":"eth_chainId","params":[]}',
    b'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[Infinity]}',
])
def test_unparseable_bodies_are_refused(body):
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(body)
    assert reply.status == 400
    assert error_of(reply)["code"] == -32700
    assert upstream.bodies == []


@pytest.mark.parametrize("body", [b"[" * 16000 + b"]" * 16000, b'{"a":' * 6000 + b"1" + b"}" * 6000,
                                  b'{"jsonrpc":"2.0","id":1,"method":"eth_call","params":' + b"[" * 16000 + b"]" * 16000 + b"}"])
def test_deep_nesting_is_refused_without_a_crash(body):
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(body)
    assert reply.status in (400, 413) and upstream.bodies == []


def test_a_string_id_is_kept():
    upstream = FakeUpstream()
    reply = make_core("observer", upstream).handle(call("eth_chainId", [], ident="q-1"))
    assert json.loads(reply.body)["id"] == "q-1"


def test_an_oversized_body_is_refused_by_the_core_too():
    upstream = FakeUpstream()
    body = call("eth_chainId", []) + b" " * relay.MAX_REQUEST_BYTES
    reply = make_core("observer", upstream).handle(body)
    assert reply.status == 413 and error_of(reply)["code"] == -32005 and upstream.bodies == []


# --- upstream replies ------------------------------------------------------------------------------------------


def test_an_upstream_rpc_error_passes_through_with_the_callers_id():
    upstream = FakeUpstream(lambda r: reply_for(r, {"error": {"code": -32000, "message": "nonce too low",
                                                               "data": "0x"}}))
    reply = make_core("broadcast", upstream).handle(call("eth_sendRawTransaction", [RAW], ident=42))
    assert reply.status == 200
    assert json.loads(reply.body) == {"jsonrpc": "2.0", "id": 42,
                                      "error": {"code": -32000, "message": "nonce too low", "data": "0x"}}


def test_an_upstream_http_error_with_an_rpc_body_keeps_its_status_and_error():
    upstream = FakeUpstream(lambda r: reply_for(r, {"error": {"code": -32007, "message": "request limit reached"}},
                                                status=429))
    reply = make_core("observer", upstream).handle(call("eth_chainId", []))
    assert reply.status == 429
    assert error_of(reply) == {"code": -32007, "message": "request limit reached"}


@pytest.mark.parametrize("leak", [SENTINEL_KEY, SENTINEL_KEY.upper(), SENTINEL_HOST, SENTINEL_URL,
                                  f"https://{SENTINEL_HOST}/{SENTINEL_KEY}"])
@pytest.mark.parametrize("where", ["error", "result"])
def test_an_upstream_reply_that_names_the_key_or_host_is_withheld(leak, where):
    fields = ({"error": {"code": -32000, "message": f"bad request to {leak}"}} if where == "error"
              else {"result": {"note": leak}})
    upstream = FakeUpstream(lambda r: reply_for(r, fields))
    logs: list[dict[str, Any]] = []
    reply = make_core("observer", upstream, logs=logs).handle(call("eth_chainId", []))
    assert reply.status == 502
    assert error_of(reply)["code"] == -32603
    assert_no_secret(reply.body, logs)


@pytest.mark.parametrize("echo", [
    SENTINEL_KEY[:relay.KEY_FRAGMENT_CHARS],
    SENTINEL_KEY[-relay.KEY_FRAGMENT_CHARS:].upper(),
    "bad token " + SENTINEL_KEY[:21],
    "".join(f"%{ord(c):02x}" for c in SENTINEL_KEY),
    "%71%6e" + SENTINEL_KEY[2:],
    SENTINEL_KEY.encode().hex(),
    SENTINEL_KEY.encode().hex().upper(),
])
def test_a_partial_or_encoded_key_echo_is_withheld(echo):
    upstream = FakeUpstream(lambda r: reply_for(r, {"error": {"code": -32000, "message": echo}}))
    reply = make_core("observer", upstream).handle(call("eth_chainId", []))
    assert reply.status == 502 and error_of(reply)["message"] == "upstream reply withheld"


def test_a_short_key_piece_alone_is_not_withheld():
    piece = SENTINEL_KEY[:relay.KEY_FRAGMENT_CHARS - 1]
    upstream = FakeUpstream(lambda r: reply_for(r, {"error": {"code": -32000, "message": piece}}))
    assert make_core("observer", upstream).handle(call("eth_chainId", [])).status == 200


def test_an_escaped_key_in_the_upstream_reply_is_still_withheld():
    escaped = "".join(f"\\u{ord(c):04x}" for c in SENTINEL_KEY)
    raw = ('{"jsonrpc":"2.0","id":7,"error":{"code":-1,"message":"' + escaped + '"}}').encode()
    upstream = FakeUpstream(relay.UpstreamReply(status=200, headers={}, body=raw))
    reply = make_core("observer", upstream).handle(call("eth_chainId", []))
    assert reply.status == 502
    assert_no_secret(reply.body)


@pytest.mark.parametrize("answer", [
    relay.UpstreamReply(status=500, headers={}, body=f"<html>{SENTINEL_URL} failed</html>".encode()),
    relay.UpstreamReply(status=302, headers={"location": SENTINEL_URL}, body=b""),
    relay.UpstreamReply(status=200, headers={}, body=b"not json"),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":8,"result":"0x1"}'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7}'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"result":1,"error":{}}'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"error":"bad"}'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"error":{"code":"x","message":"m"}}'),
    relay.UpstreamReply(status=200, headers={}, body=b'[{"jsonrpc":"2.0","id":7,"result":"0x1"}]'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"result":"0x1","x":1}'),
    relay.UpstreamReply(status=200, headers={"Content-Encoding": "gzip"}, body=b'{"jsonrpc":"2.0","id":7,"result":"0x1"}'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"id":7,"result":"0x1"}'),
    relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"result":NaN}'),
])
def test_an_unusable_upstream_reply_becomes_a_relay_error_without_the_key(answer):
    logs: list[dict[str, Any]] = []
    reply = make_core("observer", FakeUpstream(answer), logs=logs).handle(call("eth_chainId", []))
    assert reply.status == 502
    assert error_of(reply)["code"] == -32603
    assert_no_secret(reply.body, logs)


def test_an_oversized_upstream_reply_is_refused():
    big = relay.UpstreamReply(status=200, headers={}, body=b'{"jsonrpc":"2.0","id":7,"result":"0x' + b"0" * relay.MAX_RESPONSE_BYTES + b'"}')
    reply = make_core("observer", FakeUpstream(big)).handle(call("eth_chainId", []))
    assert reply.status == 502


def test_an_upstream_failure_is_sanitized_even_when_its_message_names_the_key():
    def boom(_: dict[str, Any]) -> relay.UpstreamReply:
        raise OSError(f"connect to {SENTINEL_URL} failed")

    logs: list[dict[str, Any]] = []
    reply = make_core("observer", FakeUpstream(boom), logs=logs).handle(call("eth_chainId", []))
    assert reply.status == 502
    assert error_of(reply)["code"] == -32603
    assert_no_secret(reply.body, logs)
    assert logs[-1]["outcome"] == "upstream_unreachable"


def test_upstream_failure_type_is_sanitized():
    def boom(_: dict[str, Any]) -> relay.UpstreamReply:
        raise relay.UpstreamFailure()

    reply = make_core("observer", FakeUpstream(boom)).handle(call("eth_chainId", []))
    assert reply.status == 502


# --- limits -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["observer", "broadcast"])
def test_the_rate_limit_refuses_after_the_burst_and_refills(role):
    clock = Clock()
    upstream = FakeUpstream()
    core = make_core(role, upstream, clock=clock)
    rate, burst = relay.RATE_LIMITS[role]
    for _ in range(burst):
        assert core.handle(call("eth_chainId", [])).status == 200
    refused = core.handle(call("eth_chainId", []))
    assert refused.status == 429 and error_of(refused)["code"] == -32005
    assert len(upstream.bodies) == burst
    clock.now += 1.0 / rate + 1e-6
    assert core.handle(call("eth_chainId", [])).status == 200


def test_refused_requests_do_not_spend_the_rate_limit():
    clock = Clock()
    core = make_core("broadcast", FakeUpstream(), clock=clock)
    _, burst = relay.RATE_LIMITS["broadcast"]
    for _ in range(burst * 3):
        assert core.handle(b"[]").status == 400
        assert core.handle(call("eth_call", [CALL, "latest"])).status == 403
    for _ in range(burst):
        assert core.handle(call("eth_chainId", [])).status == 200
    assert core.handle(call("eth_chainId", [])).status == 429


def test_the_broadcast_limit_is_tighter_than_the_observer_limit():
    assert relay.RATE_LIMITS["broadcast"][0] < relay.RATE_LIMITS["observer"][0]
    assert relay.RATE_LIMITS["broadcast"][1] < relay.RATE_LIMITS["observer"][1]
    assert relay.MAX_REQUEST_BYTES <= 32 * 1024
    assert relay.MAX_RESPONSE_BYTES <= 4 * 1024 * 1024


# --- logs -------------------------------------------------------------------------------------------------------


def test_each_request_leaves_one_log_line_without_the_key_or_params():
    logs: list[dict[str, Any]] = []
    core = make_core("broadcast", FakeUpstream(), logs=logs)
    core.handle(call("eth_sendRawTransaction", [RAW]))
    core.handle(call("eth_call", [CALL, "latest"]))
    core.handle(b"[]")
    assert len(logs) == 3
    assert [r["outcome"] for r in logs] == ["forwarded", "method_not_allowed", "batch_refused"]
    for record in logs:
        assert set(record) == {"role", "method", "outcome", "status", "upstream_status", "ms", "bytes_in", "bytes_out"}
        json.dumps(record)
    assert RAW not in json.dumps(logs)
    assert logs[0]["method"] == "eth_sendRawTransaction"
    assert logs[1]["method"] == "eth_call"
    assert logs[2]["method"] == "-"
    assert_no_secret(logs)


def test_a_client_method_name_is_never_written_to_the_log():
    logs: list[dict[str, Any]] = []
    make_core("observer", FakeUpstream(), logs=logs).handle(call("evil\nmethod injected", []))
    assert logs[0]["method"] == "-"
    assert "evil" not in json.dumps(logs)


def test_the_default_log_writes_json_lines_to_stdout(capsys):
    relay.log_line({"role": "observer", "method": "eth_chainId", "outcome": "forwarded", "status": 200,
                    "upstream_status": 200, "ms": 1, "bytes_in": 1, "bytes_out": 1})
    line = capsys.readouterr().out.strip()
    assert json.loads(line)["outcome"] == "forwarded"
    assert "at" in json.loads(line)
