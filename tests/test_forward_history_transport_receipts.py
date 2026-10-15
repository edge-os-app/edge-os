"""Transport construction identity and per-call receipts in the recorder's `transport-receipts.json` sidecar.

The real `StdlibHttpTransport` runs through the recorder-owned fixture construction path with an in-memory connection
that serves authored synthetic bytes; no socket is opened. Every value is a synthetic fixture. Nothing here is provider,
chain or market evidence, and every handoff and sidecar stays SYNTHETIC.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import edge_os_api.research_history.http_clients.http_transport as http_transport_module
from edge_os_api.records.contract_adapter import canonical_bytes
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, StdlibHttpTransport
from edge_os_api.research_history.provider_transport import SourceTimeout
from scripts.forward_history_recorder import (
    TRANSPORT_RECEIPTS_FILE,
    TRANSPORT_RECEIPTS_SCHEMA,
    AttemptExists,
    AttemptJournal,
    RecordingTransport,
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
