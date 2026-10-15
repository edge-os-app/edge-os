"""Transport construction identity and per-call receipts in the recorder's `transport-receipts.json` sidecar.

The real `StdlibHttpTransport` runs through the recorder-owned fixture construction path. The default tests use an
in-memory connection and open no socket. The loopback tests at the end use an owned 127.0.0.1 HTTPServer and run only
with EDGE_OS_LOOPBACK_QUALIFICATION=1. Every value is a synthetic fixture. Nothing here is provider, chain or market
evidence, and every handoff and sidecar stays SYNTHETIC.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import socket
import socketserver
import stat
import threading
import time
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

import edge_os_api.research_history.http_clients.http_transport as http_transport_module
from edge_os_api.records.contract_adapter import canonical_bytes
from edge_os_api.research_history.http_clients.client_config import HttpProviderError
from edge_os_api.research_history.http_clients.http_transport import (
    HttpResponse,
    StdlibHttpTransport,
    refuse_provider_status,
)
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceTimeout
from scripts.forward_history_recorder import (
    TRANSPORT_RECEIPTS_FILE,
    TRANSPORT_RECEIPTS_SCHEMA,
    AdmissionRefused,
    AttemptExists,
    AttemptJournal,
    RecordingTransport,
    SystemClock,
    local_fixture_transport,
    owned_stdlib_transport,
    recover_attempt,
    run_attempt,
    transport_identity,
)
from tests.test_forward_history_recorder import (
    HS_TOKEN,
    HS_URL,
    QN_PATH_SECRET,
    QN_URL,
    SECRETS,
    T0,
    Credentials,
    FakeClock,
    SyntheticProviders,
    _rpc,
    all_bytes,
    recorder_input,
)

STDLIB_NAME = "edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport"
STDLIB_SHA256 = hashlib.sha256(Path(http_transport_module.__file__).read_bytes()).hexdigest()
RECEIPT_KEYS = {"call_id", "transport_binding_sha256", "request_sha256", "outcome", "status", "body_sha256",
                "body_bytes", "received_at_utc_us", "elapsed_us"}
# The first admitted call of every full synthetic run: the QuickNode client's literal eth_chainId request.
CHAIN_ID_REQUEST = b'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'


class FixtureResponse:
    def __init__(self, reply: HttpResponse) -> None:
        self.status = reply.status
        self._body = io.BytesIO(reply.body)
        self._headers = list(reply.headers.items())

    def read(self, size: int) -> bytes:
        return self._body.read(size)

    def getheaders(self) -> list[tuple[str, str]]:
        return self._headers


class FixtureConnection:
    """An in-memory `http.client` connection: the real transport code runs, the bytes come from the providers."""

    def __init__(self, providers: SyntheticProviders, scheme: str, host: str, port: int | None) -> None:
        self.providers, self.base = providers, f"{scheme}://{host}" + ("" if port is None else f":{port}")
        self.sock = None
        self.reply: HttpResponse | None = None

    def request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> None:
        self.reply = self.providers.request(method=method, url=self.base + path, headers=headers, body=body,
                                            timeout=0.0, deadline=0.0, max_response_bytes=0)

    def getresponse(self) -> FixtureResponse:
        assert self.reply is not None
        return FixtureResponse(self.reply)

    def close(self) -> None:
        return


class FixtureConnector:
    def __init__(self, providers: SyntheticProviders) -> None:
        self.providers = providers

    def __call__(self, scheme: str, host: str, port: int | None, timeout: float) -> FixtureConnection:
        return FixtureConnection(self.providers, scheme, host, port)


Factory = Callable[[SyntheticProviders, FakeClock], Any]


def fixture_transport(providers: SyntheticProviders, clock: FakeClock) -> StdlibHttpTransport:
    return local_fixture_transport(FixtureConnector(providers), clock.monotonic)


def run_with(tmp_path: Path, factory: Factory, *, configure: Callable[..., None] | None = None,
             credentials: Credentials | None = None, **input_changes: Any
             ) -> tuple[dict[str, Any], SyntheticProviders, Path, Any]:
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    transport = factory(providers, clock)
    if configure:
        configure(providers, clock, transport)
    result = run_attempt(recorder_input(tmp_path, **input_changes), transport=transport, clock=clock,
                         credentials=credentials or Credentials())
    return result, providers, tmp_path / "attempts" / "synthetic-attempt-1", transport


def sidecar_of(attempt: Path) -> tuple[dict[str, Any], bytes]:
    body = (attempt / TRANSPORT_RECEIPTS_FILE).read_bytes()
    return json.loads(body), body


def journal_records(attempt: Path, event: str) -> list[dict[str, Any]]:
    lines = (attempt / "journal.jsonl").read_text().splitlines()
    return [record for record in map(json.loads, lines) if record["event"] == event]


def binding_sha(construction: str, implementation: str | None, implementation_sha256: str | None) -> str:
    return hashlib.sha256(canonical_bytes({"construction": construction, "implementation": implementation,
                                           "implementation_sha256": implementation_sha256})).hexdigest()


OWNED_BINDING = binding_sha("OWNED_STDLIB", STDLIB_NAME, STDLIB_SHA256)
FIXTURE_BINDING = binding_sha("LOCAL_FIXTURE", STDLIB_NAME, STDLIB_SHA256)
INJECTED_BINDING = binding_sha("INJECTED", None, None)


# Construction identity


@pytest.mark.parametrize("requested", ["SYNTHETIC", "ACTUAL"])
def test_owned_construction_is_recorded_but_never_promotes_evidence(tmp_path: Path, requested: str) -> None:
    owned = owned_stdlib_transport()
    assert type(owned) is StdlibHttpTransport
    # A foreign QuickNode host stops the attempt before any request, so the owned socket transport never sends.
    result, providers, attempt, _ = run_with(tmp_path, lambda providers, clock: owned, evidence_class=requested,
                                             credentials=Credentials("https://other.example.invalid/x/"))
    assert result["status"] == "DESTINATION_MISMATCH" and providers.calls == []
    sidecar, body = sidecar_of(attempt)
    handoff_body = Path(result["handoff_path"]).read_bytes()
    assert body == canonical_bytes(sidecar)
    assert sidecar == {
        "schema_version": TRANSPORT_RECEIPTS_SCHEMA, "attempt_id": "synthetic-attempt-1",
        "handoff_sha256": hashlib.sha256(handoff_body).hexdigest(),
        "recorder_code_sha256": json.loads(handoff_body)["recorder_code_sha256"], "evidence_class": "SYNTHETIC",
        "transport": {"construction": "OWNED_STDLIB", "implementation": STDLIB_NAME,
                      "implementation_sha256": STDLIB_SHA256},
        "receipts": []}
    assert TRANSPORT_RECEIPTS_SCHEMA == "edge-os.forward-history-transport-receipts/1"
    assert json.loads(handoff_body)["evidence_class"] == "SYNTHETIC"
    assert json.loads(handoff_body)["schema_version"] == "edge-os.forward-history-handoff/1"
    assert result["transport_receipts_status"] == "WRITTEN"
    assert result["transport_receipts_sha256"] == hashlib.sha256(body).hexdigest()
    assert stat.S_IMODE(os.stat(attempt / TRANSPORT_RECEIPTS_FILE).st_mode) == 0o600


class _StdlibSubclass(StdlibHttpTransport):
    pass


class _Wrapper:
    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def request(self, **kwargs: Any) -> HttpResponse:
        return self.inner.request(**kwargs)


def _advertises_actual(providers: SyntheticProviders, clock: FakeClock) -> SyntheticProviders:
    providers.construction, providers.implementation = "OWNED_STDLIB", STDLIB_NAME  # type: ignore[attr-defined]
    providers.implementation_sha256, providers.evidence_class = STDLIB_SHA256, "ACTUAL"  # type: ignore[attr-defined]
    return providers


INJECTED_FACTORIES: dict[str, Factory] = {
    "synthetic-providers": lambda providers, clock: providers,
    "caller-stdlib-with-test-connector": lambda providers, clock: StdlibHttpTransport(
        connect=FixtureConnector(providers), clock=clock.monotonic),
    "stdlib-subclass": lambda providers, clock: _StdlibSubclass(connect=FixtureConnector(providers),
                                                                clock=clock.monotonic),
    "wrapper-around-fixture": lambda providers, clock: _Wrapper(fixture_transport(providers, clock)),
    "advertises-actual": _advertises_actual,
}


@pytest.mark.parametrize("name", sorted(INJECTED_FACTORIES))
def test_caller_injected_objects_always_have_injected_provenance(tmp_path: Path, name: str) -> None:
    result, providers, attempt, _ = run_with(tmp_path, INJECTED_FACTORIES[name], evidence_class="ACTUAL")
    assert result["status"] == "COMPLETED" and len(providers.calls) == 22
    sidecar, _ = sidecar_of(attempt)
    assert sidecar["transport"] == {"construction": "INJECTED", "implementation": None,
                                    "implementation_sha256": None}
    assert sidecar["evidence_class"] == "SYNTHETIC"
    assert {receipt["transport_binding_sha256"] for receipt in sidecar["receipts"]} == {INJECTED_BINDING}
    handoff = json.loads(Path(result["handoff_path"]).read_bytes())
    assert handoff["evidence_class"] == "SYNTHETIC" and "ACTUAL_NOT_ESTABLISHED" in handoff["evidence_notice"]


def test_owned_and_fixture_paths_register_only_their_own_objects() -> None:
    clock = FakeClock(T0)
    fixture = fixture_transport(SyntheticProviders(clock), clock)
    identities = [transport_identity(owned_stdlib_transport()), transport_identity(fixture),
                  transport_identity(StdlibHttpTransport()), transport_identity(_StdlibSubclass())]
    assert [item["construction"] for item in identities] == ["OWNED_STDLIB", "LOCAL_FIXTURE", "INJECTED", "INJECTED"]


# Literal receipts through the real stdlib transport


def test_fixture_run_records_literal_receipts_bound_to_the_final_handoff(tmp_path: Path) -> None:
    result, providers, attempt, _ = run_with(tmp_path, fixture_transport)
    assert result["status"] == "COMPLETED" and len(providers.calls) == 22
    sidecar, body = sidecar_of(attempt)
    handoff_body = Path(result["handoff_path"]).read_bytes()
    handoff = json.loads(handoff_body)
    assert sidecar["handoff_sha256"] == hashlib.sha256(handoff_body).hexdigest() == result["handoff_sha256"]
    assert sidecar["transport"] == {"construction": "LOCAL_FIXTURE", "implementation": STDLIB_NAME,
                                    "implementation_sha256": STDLIB_SHA256}
    receipts = sidecar["receipts"]
    assert [set(receipt) for receipt in receipts] == [RECEIPT_KEYS] * 22
    assert [receipt["call_id"] for receipt in receipts] == [call["call_id"] for call in handoff["calls"]]
    for receipt, call in zip(receipts, handoff["calls"], strict=True):
        assert receipt["transport_binding_sha256"] == FIXTURE_BINDING
        for key in ("request_sha256", "outcome", "status", "body_sha256", "body_bytes"):
            assert receipt[key] == call[key]
    resolved = journal_records(attempt, "RESOLVED")
    assert [r["received_at_utc_us"] for r in receipts] == [r["received_utc_us"] for r in resolved]
    assert [r["elapsed_us"] for r in receipts] == [250_000] * 22
    first = receipts[0]
    assert first["call_id"] == "01-P1-quicknode"
    assert first["request_sha256"] == hashlib.sha256(CHAIN_ID_REQUEST).hexdigest() == (
        "09fabe0af56b7726f1666ddd147482df4d951f86f66124b936716c53ab0e8471")
    assert providers.calls[0]["body"] == json.loads(CHAIN_ID_REQUEST)
    assert first["status"] == 200 and first["outcome"] == "REPLY_RECEIVED"
    assert first["body_sha256"] == hashlib.sha256(_rpc("0x8f")).hexdigest() == (
        "297e3000506f347fcae580843cdf2272e5f7c69bcbcc0498cda4a774038ec821")
    assert first["body_bytes"] == len(_rpc("0x8f")) == 45
    assert first["received_at_utc_us"] == (T0 - 600) * 1_000_000 + 250_000
    assert FIXTURE_BINDING == binding_sha("LOCAL_FIXTURE", STDLIB_NAME, STDLIB_SHA256)
    assert body == canonical_bytes(sidecar)


def test_missing_reply_keeps_null_receipt_fields_and_unknown_liability(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def stall(call: dict[str, Any]) -> None:
            raise SourceTimeout("synthetic timeout")
        providers.overrides[9] = stall
    result, providers, attempt, _ = run_with(tmp_path, fixture_transport, configure=configure)
    sidecar, _ = sidecar_of(attempt)
    missing = sidecar["receipts"][8]
    assert missing["outcome"] == "UNKNOWN"
    assert {key: missing[key] for key in ("status", "body_sha256", "body_bytes", "received_at_utc_us",
                                          "elapsed_us")} == dict.fromkeys(
        ("status", "body_sha256", "body_bytes", "received_at_utc_us", "elapsed_us"))
    assert missing["request_sha256"] is not None
    handoff = json.loads(Path(result["handoff_path"]).read_bytes())
    assert handoff["accounting"]["unknown_liability"] == 1
    assert sum(1 for call in providers.calls if call["url"] == HS_URL and call["index"] == 8) == 1


@pytest.mark.parametrize("where", ["body", "exception"])
def test_credential_incident_receipt_exposes_no_body_digest_or_secret(tmp_path: Path, where: str) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def echo(call: dict[str, Any]) -> HttpResponse:
            if where == "body":
                return HttpResponse(200, {}, _rpc(f"see {QN_URL}"))
            raise OSError(f"connect failed for {QN_URL}")
        providers.overrides[2] = echo
    result, providers, attempt, _ = run_with(tmp_path, fixture_transport, configure=configure)
    assert result["stop_reason"] == "CREDENTIAL_INCIDENT" and len(providers.calls) == 2
    sidecar, body = sidecar_of(attempt)
    incident = sidecar["receipts"][1]
    assert incident["outcome"] == "CREDENTIAL_INCIDENT" and incident["body_sha256"] is None
    if where == "exception":
        assert incident["status"] is None and incident["received_at_utc_us"] is None
    for secret in SECRETS:
        assert secret.encode() not in body
    assert HS_TOKEN.encode() not in all_bytes(attempt) and QN_PATH_SECRET.encode() not in all_bytes(attempt)


def test_oversized_reply_receipt_keeps_no_body_digest(tmp_path: Path) -> None:
    clock = FakeClock(T0)
    inner = SyntheticProviders(clock)
    inner.overrides[1] = lambda call: HttpResponse(200, {}, b"y" * 2_097_153)
    journal = AttemptJournal.create(tmp_path / "attempt")
    wrapper = RecordingTransport(inner, journal, clock, quicknode_url=QN_URL, hypersync_url=HS_URL, secrets=SECRETS)
    wrapper.label(phase="P1", slot="test", provider="quicknode")
    clock.advance(1.0)
    with pytest.raises(Exception) as caught:
        wrapper.request(method="POST", url=QN_URL, headers={}, body=CHAIN_ID_REQUEST, timeout=15.0,
                        deadline=clock.mono + 60, max_response_bytes=2_097_152)
    assert getattr(caught.value, "code", None) == "OVERSIZED_RESPONSE"
    receipt = wrapper.receipts_document("synthetic-attempt-1", "0" * 64)["receipts"][0]
    assert receipt["outcome"] == "OVERSIZED_REFUSED" and receipt["body_sha256"] is None
    assert receipt["status"] == 200 and receipt["body_bytes"] == 2_097_153


# Substitution, clocks, interruption and the sidecar write


def _swap_instance_request(transport: Any) -> None:
    transport.request = lambda **kwargs: HttpResponse(200, {}, _rpc("0x8f"))


def _swap_connect(transport: Any) -> None:
    transport._connect = FixtureConnector(SyntheticProviders(FakeClock(T0)))


def _swap_class(transport: Any) -> None:
    transport.__class__ = _StdlibSubclass


SUBSTITUTIONS: dict[str, Callable[[Any], None]] = {
    "instance-request": _swap_instance_request, "connector": _swap_connect, "class": _swap_class}


@pytest.mark.parametrize("name", sorted(SUBSTITUTIONS))
@pytest.mark.parametrize("call_number", [3, 12])
def test_method_substitution_after_binding_refuses_every_later_send(tmp_path: Path, name: str,
                                                                    call_number: int) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def substitute(call: dict[str, Any]) -> None:
            SUBSTITUTIONS[name](transport)
        providers.overrides[call_number] = substitute
    result, providers, attempt, _ = run_with(tmp_path, fixture_transport, configure=configure)
    assert result["status"] == "SAFETY_STOP" and result["stop_reason"] == "ADMISSION_TRANSPORT_SUBSTITUTED"
    assert len(providers.calls) == call_number
    sidecar, _ = sidecar_of(attempt)
    assert len(sidecar["receipts"]) == call_number
    assert {receipt["transport_binding_sha256"] for receipt in sidecar["receipts"]} == {FIXTURE_BINDING}
    assert recover_attempt(attempt)["unknown_liability"] == 0


def test_class_level_method_patch_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        original = StdlibHttpTransport.request

        def patch(call: dict[str, Any]) -> None:
            monkeypatch.setattr(StdlibHttpTransport, "request", lambda self, **kwargs: original(self, **kwargs))
        providers.overrides[2] = patch
    result, providers, _, _ = run_with(tmp_path, fixture_transport, configure=configure)
    assert result["stop_reason"] == "ADMISSION_TRANSPORT_SUBSTITUTED" and len(providers.calls) == 2


def test_injected_request_substitution_is_refused(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def substitute(call: dict[str, Any]) -> None:
            transport.request = lambda **kwargs: HttpResponse(200, {}, _rpc("0x8f"))
        providers.overrides[4] = substitute
    result, providers, attempt, _ = run_with(tmp_path, lambda providers, clock: providers, configure=configure)
    assert result["stop_reason"] == "ADMISSION_TRANSPORT_SUBSTITUTED" and len(providers.calls) == 4
    assert len(sidecar_of(attempt)[0]["receipts"]) == 4


def test_construction_altered_before_binding_never_sends(tmp_path: Path) -> None:
    def factory(providers: SyntheticProviders, clock: FakeClock) -> Any:
        transport = fixture_transport(providers, clock)
        transport._clock = clock.monotonic  # an equal-looking but different bound method is still a substitution
        return transport
    result, providers, attempt, _ = run_with(tmp_path, factory)
    assert result["stop_reason"] == "ADMISSION_TRANSPORT_SUBSTITUTED" and providers.calls == []
    sidecar, _ = sidecar_of(attempt)
    assert sidecar["transport"]["construction"] == "INJECTED" and sidecar["receipts"] == []


def test_backward_clock_at_receipt_records_no_receipt_time_and_stops(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def reverse(call: dict[str, Any]) -> None:
            clock.now -= 5.0
            clock.mono -= 5.0
        providers.overrides[3] = reverse
    result, providers, attempt, _ = run_with(tmp_path, fixture_transport, configure=configure)
    assert result["status"] == "CLOCK_UNTRUSTED" and len(providers.calls) == 3
    receipt = sidecar_of(attempt)[0]["receipts"][2]
    assert receipt["received_at_utc_us"] is None and receipt["elapsed_us"] is None
    assert receipt["outcome"] == "REPLY_RECEIVED" and receipt["status"] == 200


class Crash(BaseException):
    pass


def test_interrupted_journal_writes_no_sidecar_and_never_resends(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def crash(call: dict[str, Any]) -> None:
            raise Crash()
        providers.overrides[10] = crash
    with pytest.raises(Crash):
        run_with(tmp_path, fixture_transport, configure=configure)
    attempt = tmp_path / "attempts" / "synthetic-attempt-1"
    summary = recover_attempt(attempt)
    assert summary["unknown_liability"] == 1 and summary["handoff_present"] is False
    assert not (attempt / TRANSPORT_RECEIPTS_FILE).exists()
    clock = FakeClock(T0 + 700)
    providers = SyntheticProviders(clock)
    with pytest.raises(AttemptExists):
        run_attempt(recorder_input(tmp_path), transport=fixture_transport(providers, clock), clock=clock,
                    credentials=Credentials())
    assert providers.calls == [] and not (attempt / TRANSPORT_RECEIPTS_FILE).exists()
    assert recover_attempt(attempt) == summary


def test_duplicate_attempt_leaves_the_existing_sidecar_unchanged(tmp_path: Path) -> None:
    _, _, attempt, _ = run_with(tmp_path, fixture_transport)
    before = all_bytes(attempt)
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    credentials = Credentials()
    with pytest.raises(AttemptExists):
        run_attempt(recorder_input(tmp_path, evidence_class="ACTUAL"), transport=owned_stdlib_transport(),
                    clock=clock, credentials=credentials)
    assert providers.calls == [] and credentials.reads == [] and all_bytes(attempt) == before


def test_sidecar_write_failure_keeps_the_completed_handoff_and_never_resends(tmp_path: Path) -> None:
    placeholder = b"not a receipt"

    def configure(providers: SyntheticProviders, clock: FakeClock, transport: Any) -> None:
        def occupy(call: dict[str, Any]) -> None:
            (tmp_path / "attempts" / "synthetic-attempt-1" / TRANSPORT_RECEIPTS_FILE).write_bytes(placeholder)
        providers.overrides[22] = occupy
    result, providers, attempt, _ = run_with(tmp_path, fixture_transport, configure=configure)
    assert result["status"] == "COMPLETED" and len(providers.calls) == 22
    assert result["transport_receipts_status"] == "WRITE_FAILED" and result["transport_receipts_sha256"] is None
    assert (attempt / TRANSPORT_RECEIPTS_FILE).read_bytes() == placeholder
    handoff_body = Path(result["handoff_path"]).read_bytes()
    assert hashlib.sha256(handoff_body).hexdigest() == result["handoff_sha256"]
    assert len(journal_records(attempt, "ADMITTED")) == 22
    assert journal_records(attempt, "HANDOFF_WRITTEN") == [{"event": "HANDOFF_WRITTEN",
                                                             "sha256": result["handoff_sha256"]}]


def test_not_ready_input_writes_no_sidecar(tmp_path: Path) -> None:
    value = recorder_input(tmp_path, plans={"quicknode": "", "hypersync": "plan-ref-hs"})
    clock = FakeClock(T0 - 600)
    result = run_attempt(value, transport=owned_stdlib_transport(), clock=clock, credentials=Credentials())
    assert result["status"] == "NOT_READY" and list((tmp_path / "attempts").iterdir()) == []


# Owned loopback qualification: the real recorder wrapper and stdlib transport over a 127.0.0.1 HTTPServer.
#
# Runs only with EDGE_OS_LOOPBACK_QUALIFICATION=1. The server is bound to 127.0.0.1 port 0 and serves authored bytes.
# The recorder keeps its invalid logical URLs; only the fixture connector reaches the loopback port, so every receipt
# is LOCAL_FIXTURE and every handoff stays SYNTHETIC. No DNS, TLS, provider or real credential is used.

loopback = pytest.mark.skipif(os.environ.get("EDGE_OS_LOOPBACK_QUALIFICATION") != "1",
                              reason="owned loopback qualification runs only under its separate grant")
MAX_HANDLER_SECONDS = 5.0  # every authored server action ends within this bound
Script = Callable[["LoopbackServer", int, bytes, Any], None]


class _RawHandler(socketserver.StreamRequestHandler):
    """Captures the exact request bytes, then runs the test's authored reply script."""

    def handle(self) -> None:
        server: LoopbackServer = self.server  # type: ignore[assignment]
        self.connection.settimeout(MAX_HANDLER_SECONDS)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.connection.recv(65_536)
            if not chunk:
                return
            head += chunk
        header_end = head.index(b"\r\n\r\n") + 4
        length = 0
        for line in head[:header_end].split(b"\r\n")[1:]:
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1])
        raw = head
        while len(raw) < header_end + length:
            chunk = self.connection.recv(65_536)
            if not chunk:
                break
            raw += chunk
        with server.lock:
            index = len(server.requests)
            server.requests.append(raw)
        try:
            server.script(server, index, raw, self.connection)
        except OSError:
            pass  # the client closed or the transport shut its socket at a deadline


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = False  # server_close joins every handler thread
    block_on_close = True

    def __init__(self, script: Script) -> None:
        super().__init__(("127.0.0.1", 0), _RawHandler)
        self.script = script
        self.requests: list[bytes] = []
        self.lock = threading.Lock()
        self.port = self.server_address[1]
        self.thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05},
                                       name="l4-loopback-server", daemon=True)

    def connect(self, scheme: str, host: str, port: int | None, timeout: float) -> http.client.HTTPConnection:
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)


@pytest.fixture
def loopback_server() -> Any:
    servers: list[LoopbackServer] = []
    before = set(threading.enumerate())

    def start(script: Script) -> LoopbackServer:
        server = LoopbackServer(script)
        server.thread.start()
        servers.append(server)
        return server
    try:
        yield start
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
            server.thread.join(MAX_HANDLER_SECONDS)
    for server in servers:
        assert not server.thread.is_alive()
        assert server.socket.fileno() == -1
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", server.port), timeout=1.0).close()
    deadline = time.monotonic() + MAX_HANDLER_SECONDS
    while time.monotonic() < deadline and set(threading.enumerate()) - before:
        time.sleep(0.05)  # transport watchdog timers end at their cancel
    assert set(threading.enumerate()) - before == set()


def reply(status: int, body: bytes, headers: dict[str, str] | None = None) -> bytes:
    lines = [f"HTTP/1.1 {status} X".encode(), f"Content-Length: {len(body)}".encode(), b"Connection: close"]
    lines += [f"{name}: {value}".encode() for name, value in (headers or {}).items()]
    return b"\r\n".join(lines) + b"\r\n\r\n" + body


def fixed(status: int, body: bytes, headers: dict[str, str] | None = None) -> Script:
    def script(server: LoopbackServer, index: int, raw: bytes, connection: Any) -> None:
        connection.sendall(reply(status, body, headers))
    return script


def loopback_wrapper(tmp_path: Path, server: LoopbackServer) -> tuple[RecordingTransport, AttemptJournal, Path]:
    clock = SystemClock()
    transport = local_fixture_transport(server.connect, time.monotonic)
    attempt = tmp_path / "attempt"
    journal = AttemptJournal.create(attempt)
    wrapper = RecordingTransport(transport, journal, clock, quicknode_url=QN_URL, hypersync_url=HS_URL,
                                 secrets=SECRETS)
    wrapper.label(phase="P1", slot="loopback", provider="quicknode")
    return wrapper, journal, attempt


def loopback_send(wrapper: RecordingTransport, *, seconds: float = 3.0,
                  cancel: Callable[[], bool] | None = None) -> HttpResponse:
    return wrapper.request(method="POST", url=QN_URL, headers={"content-type": "application/json"},
                           body=CHAIN_ID_REQUEST, timeout=2.0, deadline=time.monotonic() + seconds,
                           max_response_bytes=2_097_152, cancel=cancel)


def only_receipt(wrapper: RecordingTransport) -> dict[str, Any]:
    receipts = wrapper.receipts_document("loopback", "0" * 64)["receipts"]
    assert len(receipts) == 1
    return receipts[0]


def admissions(attempt: Path) -> tuple[int, int]:
    summary = recover_attempt(attempt)
    return summary["admitted"], summary["resolved"]


NULL_RECEIPT = dict.fromkeys(("status", "body_sha256", "body_bytes", "received_at_utc_us", "elapsed_us"))


@loopback
def test_loopback_exact_wire_bytes_and_receipt_hashes(tmp_path: Path, loopback_server: Any) -> None:
    body = _rpc("0x8f")
    server = loopback_server(fixed(200, body, {"Content-Type": "application/json"}))
    wrapper, _, attempt = loopback_wrapper(tmp_path, server)
    response = loopback_send(wrapper)
    assert response.status == 200 and response.body == body
    (raw,) = server.requests
    head, wire_body = raw.split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    assert lines[0] == f"POST /{QN_PATH_SECRET}/ HTTP/1.1".encode()
    assert sorted(lines[1:]) == sorted([f"Host: 127.0.0.1:{server.port}".encode(), b"Accept-Encoding: identity",
                                        b"content-type: application/json",
                                        f"Content-Length: {len(CHAIN_ID_REQUEST)}".encode()])
    assert wire_body == CHAIN_ID_REQUEST
    receipt = only_receipt(wrapper)
    assert receipt["request_sha256"] == hashlib.sha256(wire_body).hexdigest()
    assert receipt["body_sha256"] == hashlib.sha256(body).hexdigest() and receipt["body_bytes"] == len(body)
    assert receipt["outcome"] == "REPLY_RECEIVED" and receipt["status"] == 200
    assert receipt["transport_binding_sha256"] == FIXTURE_BINDING
    assert receipt["received_at_utc_us"] is not None and 0 <= receipt["elapsed_us"] < 3_000_000
    assert (attempt / "bodies" / f"{receipt['call_id']}.bin").read_bytes() == body
    assert admissions(attempt) == (1, 1)


@loopback
@pytest.mark.parametrize("size", [2_097_152, 2_097_153])
def test_loopback_reply_cap_at_and_over_2_mib(tmp_path: Path, loopback_server: Any, size: int) -> None:
    server = loopback_server(fixed(200, b"y" * size))
    wrapper, _, attempt = loopback_wrapper(tmp_path, server)
    if size == 2_097_152:
        assert len(loopback_send(wrapper).body) == size
        assert only_receipt(wrapper)["body_bytes"] == size and admissions(attempt) == (1, 1)
        return
    with pytest.raises(HttpProviderError) as caught:
        loopback_send(wrapper)
    assert caught.value.code == "OVERSIZED_RESPONSE"
    receipt = only_receipt(wrapper)
    assert receipt["outcome"] == "UNKNOWN" and {key: receipt[key] for key in NULL_RECEIPT} == NULL_RECEIPT
    assert b"y" * 1000 not in all_bytes(attempt) and admissions(attempt) == (1, 0)
    assert len(server.requests) == 1


def _drip(phase: str) -> Script:
    def script(server: LoopbackServer, index: int, raw: bytes, connection: Any) -> None:
        if phase == "header":
            connection.sendall(b"HTTP/1.1 200 X\r\n")
            payload = b"X-Slow: " + b"a" * 40
        else:
            connection.sendall(b"HTTP/1.1 200 X\r\nContent-Length: 40\r\nConnection: close\r\n\r\n")
            payload = b"b" * 40
        for byte in payload:  # one byte every 100 ms: never idle long enough for a per-read socket timeout
            connection.sendall(bytes([byte]))
            time.sleep(0.1)
    return script


@loopback
@pytest.mark.parametrize("phase", ["header", "body"])
def test_loopback_drip_past_the_deadline_times_out_with_unknown_liability(
        tmp_path: Path, loopback_server: Any, phase: str) -> None:
    server = loopback_server(_drip(phase))
    wrapper, _, attempt = loopback_wrapper(tmp_path, server)
    started = time.monotonic()
    with pytest.raises(SourceTimeout):
        loopback_send(wrapper, seconds=1.0)
    assert time.monotonic() - started < 2.5
    receipt = only_receipt(wrapper)
    assert receipt["outcome"] == "UNKNOWN" and {key: receipt[key] for key in NULL_RECEIPT} == NULL_RECEIPT
    assert admissions(attempt) == (1, 0) and len(server.requests) == 1


@loopback
def test_loopback_redirect_is_not_followed(tmp_path: Path, loopback_server: Any) -> None:
    server = loopback_server(fixed(302, b"", {"Location": f"http://127.0.0.1:{1}/elsewhere"}))
    wrapper, _, attempt = loopback_wrapper(tmp_path, server)
    response = loopback_send(wrapper)
    assert response.status == 302 and len(server.requests) == 1
    with pytest.raises(HttpProviderError) as caught:
        refuse_provider_status(response.status, "loopback")
    assert caught.value.code == "REDIRECT_REFUSED"
    assert only_receipt(wrapper)["status"] == 302 and admissions(attempt) == (1, 1)


@loopback
def test_loopback_cancellation_between_body_reads_stops_the_call(tmp_path: Path, loopback_server: Any) -> None:
    server = loopback_server(fixed(200, b"z" * 300_000))
    wrapper, _, attempt = loopback_wrapper(tmp_path, server)
    checks = {"count": 0}

    def cancel() -> bool:  # admission, pre-connect, first read; then cancelled before the second chunk
        checks["count"] += 1
        return checks["count"] >= 4
    with pytest.raises(SourceCancelled):
        loopback_send(wrapper, cancel=cancel)
    receipt = only_receipt(wrapper)
    assert receipt["outcome"] == "UNKNOWN" and {key: receipt[key] for key in NULL_RECEIPT} == NULL_RECEIPT
    assert admissions(attempt) == (1, 0) and len(server.requests) == 1
    with pytest.raises(AdmissionRefused):
        wrapper.request(method="POST", url=QN_URL, headers={}, body=CHAIN_ID_REQUEST, timeout=2.0,
                        deadline=time.monotonic() + 3, max_response_bytes=2_097_152, cancel=lambda: True)
    assert len(server.requests) == 1


@loopback
@pytest.mark.parametrize("where", ["body", "header"])
def test_loopback_secret_echo_is_an_incident_without_digest(tmp_path: Path, loopback_server: Any,
                                                             where: str) -> None:
    if where == "body":
        script = fixed(200, json.dumps({"error": f"bad token {HS_TOKEN}"}).encode())
    else:
        script = fixed(200, _rpc("0x8f"), {"X-Debug": f"path /{QN_PATH_SECRET}/"})
    server = loopback_server(script)
    wrapper, _, attempt = loopback_wrapper(tmp_path, server)
    with pytest.raises(Exception) as caught:
        loopback_send(wrapper)
    assert getattr(caught.value, "code", None) == "CREDENTIAL_INCIDENT"
    receipt = only_receipt(wrapper)
    assert receipt["outcome"] == "CREDENTIAL_INCIDENT" and receipt["body_sha256"] is None
    stored = all_bytes(attempt) + canonical_bytes(wrapper.receipts_document("loopback", "0" * 64))
    for secret in SECRETS:
        assert secret.encode() not in stored
    assert len(server.requests) == 1


def _synthetic_script(providers: SyntheticProviders, interrupt_at: int | None = None) -> Script:
    def script(server: LoopbackServer, index: int, raw: bytes, connection: Any) -> None:
        head, body = raw.split(b"\r\n\r\n", 1)
        path = head.split(b"\r\n")[0].split(b" ")[1].decode()
        url = HS_URL if path == "/query" else QN_URL
        produced = providers.request(method="POST", url=url, headers={}, body=body, timeout=0.0, deadline=0.0,
                                     max_response_bytes=0)
        connection.sendall(reply(produced.status, produced.body, dict(produced.headers)))
    return script


def loopback_run(tmp_path: Path, loopback_server: Any, cancel: Callable[[], bool] | None = None
                 ) -> tuple[dict[str, Any], LoopbackServer, Path]:
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    server = loopback_server(_synthetic_script(providers))
    transport = local_fixture_transport(server.connect, clock.monotonic)
    result = run_attempt(recorder_input(tmp_path), transport=transport, clock=clock, credentials=Credentials(),
                         cancel=cancel)
    return result, server, tmp_path / "attempts" / "synthetic-attempt-1"


@loopback
def test_loopback_full_attempt_has_one_durable_admission_per_wire_request(tmp_path: Path,
                                                                          loopback_server: Any) -> None:
    result, server, attempt = loopback_run(tmp_path, loopback_server)
    assert result["status"] == "COMPLETED"
    sidecar, _ = sidecar_of(attempt)
    assert sidecar["transport"]["construction"] == "LOCAL_FIXTURE" and sidecar["evidence_class"] == "SYNTHETIC"
    assert json.loads(Path(result["handoff_path"]).read_bytes())["evidence_class"] == "SYNTHETIC"
    wire_bodies = [raw.split(b"\r\n\r\n", 1)[1] for raw in server.requests]
    assert len(wire_bodies) == len(sidecar["receipts"]) == len(journal_records(attempt, "ADMITTED")) == 22
    assert [hashlib.sha256(body).hexdigest() for body in wire_bodies] == [
        receipt["request_sha256"] for receipt in sidecar["receipts"]]
    assert admissions(attempt) == (22, 22)


@loopback
def test_loopback_interrupted_attempt_is_never_resumed_or_resent(tmp_path: Path, loopback_server: Any) -> None:
    class Interrupt(BaseException):
        pass
    holder: dict[str, LoopbackServer] = {}

    def cancel() -> bool:  # interrupts in the read loop after the tenth request reached the wire
        server = holder.get("server")
        if server is not None and len(server.requests) == 10 and not holder.get("fired"):
            holder["fired"] = True  # type: ignore[assignment]
            raise Interrupt()
        return False
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    server = loopback_server(_synthetic_script(providers))
    holder["server"] = server
    with pytest.raises(Interrupt):
        run_attempt(recorder_input(tmp_path), transport=local_fixture_transport(server.connect, clock.monotonic),
                    clock=clock, credentials=Credentials(), cancel=cancel)
    attempt = tmp_path / "attempts" / "synthetic-attempt-1"
    summary = recover_attempt(attempt)
    assert summary["admitted"] == 10 and summary["unknown_liability"] == 1 and len(server.requests) == 10
    assert not (attempt / TRANSPORT_RECEIPTS_FILE).exists() and summary["handoff_present"] is False
    with pytest.raises(AttemptExists):
        run_attempt(recorder_input(tmp_path), transport=local_fixture_transport(server.connect, clock.monotonic),
                    clock=clock, credentials=Credentials())
    assert len(server.requests) == 10 and recover_attempt(attempt) == summary
