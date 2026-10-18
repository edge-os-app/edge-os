"""#58 R58-RESEARCH-MOUNT-L2: the accepted Nansen HTTP transport mounted in the operating-release runtime, and the
server bootstrap that the API and the worker share.

Host only: no database, Docker, browser or network outside 127.0.0.1. Keys are the stand-in sentinels. The loopback
provider is an owned 127.0.0.1 server; only an injected connector moves the adapter's fixed `https://api.nansen.ai`
origin to it, so it can never be the network factory. An actual Nansen release is registered in the code-owned default,
but this module makes no actual provider request. Contract: `docs/qualification/research-provider-composition/CONTRACT.md`
section 12; credential delivery: `CREDENTIAL_DELIVERY.md` beside it.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

import pytest

import operating_release_stand_in as stand_in
from edge_os_api.core.request_schemas import NansenReportBody
from edge_os_api.core.research import operating_release, provider_composition, released_runtime_bootstrap
from edge_os_api.core.research.operating_release import OperatingRelease, ReleaseRefused, release_sha256
from edge_os_api.core.research.released_source_runtime import (
    NansenHttpFactory,
    ReleasedNansenTransport,
    ReleasedSourceRuntime,
    open_released_runtime,
    prepare_nansen,
)
from edge_os_api.nansen_research import NansenResponse, NansenTimeout, run_research
from edge_os_api.nansen_research.http_transport import NANSEN_ORIGIN
from edge_os_api.research import investigation_jobs, nansen_reports

LOCAL = type("Local", (), {"env": "local"})()
QUESTION = "Which holder records does MOE return, and what do basic flow records show?"
ACTUAL_ENVIO, ACTUAL_QUICKNODE = "https://hypersync.actual-test.example", "quicknode.actual-test.example"


def actual_release(*, history: bool = True, nansen: bool = True, nansen_endpoint: str = NANSEN_ORIGIN,
                   release_id: str = "actual-mount-test/1") -> OperatingRelease:
    """An ACTUAL definition for composition checks only. Its hosts are `.example`; no job runs over it."""
    base = stand_in.stand_in_release(envio_endpoint=ACTUAL_ENVIO, quicknode_host=ACTUAL_QUICKNODE, history=history,
                                     nansen=nansen, nansen_endpoint=nansen_endpoint)
    return OperatingRelease(release_id, "ACTUAL", history=base.history, nansen=base.nansen)


def approve(monkeypatch, *releases: OperatingRelease) -> None:
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES",
                        {release.release_id: release_sha256(release) for release in releases})


def define(monkeypatch, *releases: OperatingRelease) -> None:
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS",
                        {release.release_id: release for release in releases})


@pytest.fixture
def no_sockets(monkeypatch):
    """Any socket the code under test tries to open fails the test."""
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> None:
        opened.append(args)
        raise AssertionError("a socket was opened")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return opened


# --------------------------------------------------------------------------------------------- bootstrap

def test_the_default_server_composes_the_one_approved_release_and_reads_no_key_or_opens_no_socket(no_sockets):
    # The code-owned default now carries exactly the one accepted Nansen-only ACTUAL release and its approved SHA-256.
    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == set(operating_release.APPROVED_RELEASES)
    assert released_runtime_bootstrap.RELEASE_DEFINITIONS != {}
    creds = stand_in.credentials()
    runtime = released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=creds)
    assert runtime is not None and runtime.release.history is None and runtime.release.nansen is not None
    assert runtime.release_sha256 == operating_release.APPROVED_RELEASES[runtime.release.release_id]
    assert creds.reads == [] and no_sockets == []


def test_an_explicitly_emptied_registry_composes_no_release_reads_no_key_and_opens_no_socket(monkeypatch, no_sockets):
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})
    creds = stand_in.credentials()
    assert released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=creds) is None
    assert released_runtime_bootstrap.server_research_runtime(LOCAL) is None
    assert creds.reads == [] and no_sockets == []


def test_an_approved_definition_gives_one_immutable_runtime_and_reads_no_key(monkeypatch, no_sockets):
    release = actual_release()
    define(monkeypatch, release)
    approve(monkeypatch, release)
    creds = stand_in.credentials()
    api = released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=creds)
    worker = released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=creds)
    assert api is not None and worker is not None
    assert api.release_sha256 == worker.release_sha256 == release_sha256(release)
    assert (api.evidence_class, api.transport_kind, api.nansen_transport_kind) == (
        "PROVIDER_ACTUAL", "PROVIDER_HTTP", "PROVIDER_HTTP")
    assert api.network_transport is True and api.nansen_network is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        api.release_sha256 = "0" * 64  # type: ignore[misc]
    assert creds.reads == [] and no_sockets == []


def test_the_bootstrap_composes_the_environment_source_by_default_and_refuses_two_releases(monkeypatch, no_sockets):
    first, second = actual_release(), actual_release(release_id="actual-mount-test/2")
    define(monkeypatch, first)
    approve(monkeypatch, first)
    looked_up: list[str] = []

    class WatchedEnviron(dict[str, str]):
        def get(self, key: str, default: Any = None) -> Any:
            looked_up.append(key)
            return default

    monkeypatch.setattr(os, "environ", WatchedEnviron())
    runtime = released_runtime_bootstrap.server_research_runtime(LOCAL)  # no source passed: the environment source
    assert runtime is not None and (type(runtime.credentials).__module__, type(runtime.credentials).__qualname__) == (
        "edge_os_api.core.research.environment_credentials", "EnvironmentCredentialSource")
    assert looked_up == [] and no_sockets == []
    define(monkeypatch, first, second)
    approve(monkeypatch, first, second)
    creds = stand_in.credentials()
    with pytest.raises(ReleaseRefused) as refused:
        released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=creds)
    assert refused.value.code == "operating_release_invalid" and creds.reads == []


def test_only_an_exactly_approved_actual_definition_is_composed(monkeypatch):
    release = actual_release()
    changed = dataclasses.replace(release, nansen=dataclasses.replace(release.nansen, deadline_seconds=601))
    define(monkeypatch, changed)
    approve(monkeypatch, release)  # approved under the earlier digest
    assert released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=stand_in.credentials()) is None
    local = stand_in.stand_in_release()
    define(monkeypatch, local)
    approve(monkeypatch, local)  # a stand-in is never a server release, even with a recorded digest
    assert released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=stand_in.credentials()) is None
    misnamed = {"another-id/1": release}
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", misnamed)
    approve(monkeypatch, release)
    with pytest.raises(ReleaseRefused) as refused:
        released_runtime_bootstrap.server_research_runtime(LOCAL, credentials=stand_in.credentials())
    assert refused.value.code == "operating_release_invalid"


def test_the_worker_process_uses_the_server_bootstrap(monkeypatch):
    composed = object()
    seen: dict[str, Any] = {}

    class Recorder:
        def __init__(self, factory: Any, settings: Any, **kwargs: Any) -> None:
            seen.update(kwargs)

        def run_pending(self) -> list[Any]:
            return []

    from edge_os_api.core import database, settings as settings_module, worker_loop

    monkeypatch.setattr(sys, "argv", ["investigation_jobs", "--once"])
    monkeypatch.setattr(settings_module, "load_settings", lambda: type("S", (), {
        "database_url": "postgresql://unused", "database_statement_timeout_ms": 1})())
    monkeypatch.setattr(database, "make_engine", lambda *args: "engine")
    monkeypatch.setattr(database, "make_session_factory", lambda engine: "factory")
    monkeypatch.setattr(worker_loop, "run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(worker_loop, "exit_with", lambda code: None)
    monkeypatch.setattr(investigation_jobs, "InvestigationWorker", Recorder)
    monkeypatch.setattr(released_runtime_bootstrap, "server_research_runtime", lambda settings: composed)
    investigation_jobs.main()
    assert seen["research_runtime"] is composed


def test_create_app_consults_the_server_bootstrap_before_any_database(monkeypatch):
    from edge_os_api import main
    from edge_os_api.core.settings import ConfigError

    def refuse(settings: Any) -> None:
        raise ReleaseRefused("operating_release_credential_unavailable", "no credential source")

    def no_database(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the database was reached")

    settings = type("S", (), {"interpreter": "fixture", "env": "local"})()
    monkeypatch.setattr(released_runtime_bootstrap, "server_research_runtime", refuse)
    monkeypatch.setattr(main, "make_engine", no_database)
    with pytest.raises(ConfigError, match="operating_release_credential_unavailable"):
        main.create_app(settings)


# --------------------------------------------------------------------------------------------- composition rules

def test_an_actual_nansen_part_needs_the_network_factory_and_the_fixed_origin(monkeypatch, no_sockets):
    release = actual_release(history=False)
    approve(monkeypatch, release)
    creds = stand_in.credentials()
    for factory in (stand_in.StandInNansen().transport, NansenHttpFactory(connect=lambda *args: None)):
        with pytest.raises(ReleaseRefused) as refused:
            open_released_runtime(LOCAL, release, credentials=creds, nansen_transport=factory)
        assert refused.value.code == "actual_nansen_transport_missing"
    runtime = open_released_runtime(LOCAL, release, credentials=creds, nansen_transport=NansenHttpFactory())
    assert (runtime.evidence_class, runtime.nansen_transport_kind, runtime.nansen_network) == (
        "PROVIDER_ACTUAL", "PROVIDER_HTTP", True)
    elsewhere = actual_release(history=False, nansen_endpoint="https://nansen.actual-test.example")
    approve(monkeypatch, elsewhere)
    with pytest.raises(ReleaseRefused) as refused:
        open_released_runtime(LOCAL, elsewhere, credentials=creds, nansen_transport=NansenHttpFactory())
    assert refused.value.code == "operating_release_invalid"
    assert creds.reads == [] and no_sockets == []


def test_a_stand_in_nansen_part_never_uses_the_network_factory(no_sockets):
    release = stand_in.stand_in_release(history=False)
    creds = stand_in.credentials()
    with pytest.raises(ReleaseRefused) as refused:
        open_released_runtime(LOCAL, release, credentials=creds, nansen_transport=NansenHttpFactory())
    assert refused.value.code == "stand_in_endpoint_not_local"
    loopback = open_released_runtime(LOCAL, release, credentials=creds,
                                     nansen_transport=NansenHttpFactory(connect=lambda *args: None))
    assert (loopback.evidence_class, loopback.nansen_transport_kind, loopback.nansen_network) == (
        "RELEASE_STAND_IN_RESPONSE", "LOOPBACK_HTTP", False)
    recording = open_released_runtime(LOCAL, release, credentials=creds,
                                      nansen_transport=stand_in.StandInNansen().transport)
    assert recording.nansen_transport_kind == "IN_PROCESS_RECORDING"
    with pytest.raises(ReleaseRefused) as refused:  # a runtime cannot claim a network factory it does not hold
        ReleasedSourceRuntime(release, loopback.release_sha256, creds, None, loopback.nansen_transport, False, True)
    assert refused.value.code == "operating_release_invalid"
    assert creds.reads == [] and no_sockets == []


@pytest.mark.parametrize("bounds", [
    {"connect_timeout_seconds": 15, "max_request_bytes": 65_536},
    {"connect_timeout_seconds": 15, "max_request_bytes": 65_536, "max_response_bytes": 200_000, "extra": 1},
    {"connect_timeout_seconds": 0, "max_request_bytes": 65_536, "max_response_bytes": 200_000},
    {"connect_timeout_seconds": True, "max_request_bytes": 65_536, "max_response_bytes": 200_000},
    {"connect_timeout_seconds": 15, "max_request_bytes": 65_536, "max_response_bytes": 200_001},
])
def test_nansen_client_bounds_are_checked_whole_release_bounds(bounds):
    release = stand_in.stand_in_release(history=False)
    bad = dataclasses.replace(release, nansen=dataclasses.replace(release.nansen, client_bounds=bounds))
    with pytest.raises(ReleaseRefused) as refused:
        operating_release.check_release(bad)
    assert refused.value.code == "operating_release_invalid"


def test_the_nansen_client_bounds_are_inside_the_release_digest():
    release = stand_in.stand_in_release(history=False)
    tighter = dataclasses.replace(release, nansen=dataclasses.replace(release.nansen, client_bounds={
        "connect_timeout_seconds": 5, "max_request_bytes": 65_536, "max_response_bytes": 200_000}))
    assert release_sha256(tighter) != release_sha256(release)


# --------------------------------------------------------------------------------------------- deadline mapping

class Calls:
    """Fake wall and monotonic clocks that record the order in which they are read."""

    def __init__(self, wall: dt.datetime, mono: float) -> None:
        self.wall, self.mono, self.order = wall, mono, []

    def wall_clock(self) -> dt.datetime:
        self.order.append("wall")
        return self.wall

    def monotonic(self) -> float:
        self.order.append("mono")
        return self.mono


def recording_runtime(nansen: stand_in.StandInNansen | None = None):
    nansen = nansen or stand_in.StandInNansen()
    runtime = open_released_runtime(LOCAL, stand_in.stand_in_release(history=False), credentials=stand_in.credentials(),
                                    nansen_transport=nansen.transport)
    return runtime, nansen


START = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("elapsed,deadline,connect", [(4, 506.0, 6.0), (8, 502.0, 2.0), (30, 480.0, 0.001)])
def test_the_saved_deadline_maps_to_one_earlier_monotonic_anchor_and_bounds_the_connect_time(elapsed, deadline,
                                                                                             connect):
    runtime, nansen = recording_runtime()
    calls = Calls(START + dt.timedelta(seconds=elapsed), 500.0)
    cancel = lambda: False  # noqa: E731
    transport = investigation_jobs.release_nansen_transport(
        prepare_nansen(runtime), START + dt.timedelta(seconds=10), calls.wall_clock, cancel, clock=calls.monotonic)
    assert calls.order[:2] == ["mono", "wall"]  # the anchor is read first, so the mapped deadline is never later
    assert nansen.bounds == [{"deadline_monotonic": deadline, "connect_timeout_seconds": connect, "cancel": cancel}]
    assert transport.deadline == deadline


class SteppingInner:
    """An inner Nansen transport whose reply takes `step` seconds on the fake clock."""

    def __init__(self, calls: Calls, step: float) -> None:
        self.calls, self.step, self.sent = calls, step, 0

    def request(self, operation: str, path: str, body: Any) -> NansenResponse:
        self.sent += 1
        self.calls.mono += self.step
        return NansenResponse(status=200, headers={}, body=json.dumps({"n": self.sent}).encode())


def test_a_late_reply_is_incomplete_and_a_later_request_is_never_sent():
    calls = Calls(START, 100.0)
    inner = SteppingInner(calls, 1.5)
    transport = ReleasedNansenTransport(inner, 102.0, calls.monotonic)
    transport.request("holders", "/api/v1/tgm/holders", {})
    with pytest.raises(NansenTimeout) as late:  # starts with 0.5 s left and returns after the deadline
        transport.request("flows", "/api/v1/tgm/flows", {})
    assert late.value.code == "TIMEOUT"
    with pytest.raises(NansenTimeout) as refused:
        transport.request("flows", "/api/v1/tgm/flows", {})
    assert refused.value.code == "DEADLINE"
    assert inner.sent == 2 and len(transport.response_sha256) == 1  # the late reply keeps no hash
    assert transport.deadline_passed() is True


def test_a_malformed_key_is_refused_before_any_request(tmp_path):
    provider = stand_in.LoopbackStandInNansen(tmp_path / "nansen.log").start()
    try:
        creds = stand_in.StandInCredentials({stand_in.NANSEN_SLOT: "stand-in key with spaces"})
        runtime, _ = stand_in.nansen_loopback_runtime(LOCAL, provider, creds=creds)
        with pytest.raises(ReleaseRefused) as refused:
            investigation_jobs.release_nansen_transport(prepare_nansen(runtime), START + dt.timedelta(minutes=5),
                                                        lambda: START, lambda: False)
        assert refused.value.code == "operating_release_credential_unavailable"
        assert "spaces" not in str(refused.value) and provider.entries() == []
    finally:
        provider.stop()


# --------------------------------------------------------------------------------------------- loopback wire

@pytest.fixture
def provider(tmp_path: Path):
    server = stand_in.LoopbackStandInNansen(tmp_path / "nansen.log").start()
    yield server
    server.stop()


def run_release(provider: stand_in.LoopbackStandInNansen, *, seconds_left: float = 30.0,
                cancel: Any = lambda transport: False) -> dict[str, Any]:
    """The worker's release path without a database: credential read, transport, guard, package, settlement.

    `cancel` receives the job's transport, so a test can cancel after a given reply."""
    runtime, creds = stand_in.nansen_loopback_runtime(LOCAL, provider)
    now = dt.datetime.now(dt.timezone.utc)
    deadline_at = now + dt.timedelta(seconds=seconds_left)
    state: dict[str, Any] = {}
    cancelled = lambda: "transport" in state and cancel(state["transport"])  # noqa: E731
    transport = investigation_jobs.release_nansen_transport(prepare_nansen(runtime), deadline_at,
                                                            lambda: dt.datetime.now(dt.timezone.utc), cancelled)
    state["transport"] = transport
    guard = provider_composition.GuardedNansenTransport(transport, cancelled, transport.deadline_passed)
    body = NansenReportBody.model_validate({"operation_id": "00000000-0000-4000-8000-000000000001",
                                            "request_key": "mount", **released_nansen_request(runtime)})
    request = nansen_reports.build_request(body, QUESTION, (deadline_at + dt.timedelta(seconds=1))
                                           .strftime("%Y-%m-%dT%H:%M:%SZ"))
    started = time.monotonic()
    run = run_research(request, guard)
    return {"run": run, "settled": nansen_reports.settlement(run.evidence, guard.sent), "guard": guard,
            "transport": transport, "creds": creds, "elapsed": time.monotonic() - started,
            "outcomes": [(outcome.operation, outcome.status, outcome.stop_reason) for outcome in run.outcomes]}


def released_nansen_request(runtime: ReleasedSourceRuntime) -> dict[str, Any]:
    from edge_os_api.core.research.released_source_runtime import nansen_request

    return nansen_request(runtime.release.nansen)


def leaked(result: dict[str, Any]) -> bool:
    text = json.dumps(result["run"].evidence.to_dict()) + json.dumps(result["run"].report.to_dict())
    return any(value in text for value in stand_in.SENTINELS)


def test_a_complete_run_crosses_the_accepted_adapter_and_settles_known(provider):
    result = run_release(provider)
    entries = provider.entries()
    assert result["outcomes"] == [("holders", "COMPLETE", None), ("flows", "COMPLETE", None)]
    assert [(entry["operation"], entry["authorized"], entry["status"]) for entry in entries] == [
        ("holders", True, 200), ("flows", True, 200)]
    assert provider.targets == [("https", "api.nansen.ai", None)] * 2
    assert result["settled"]["provider_requests"] == {"state": "KNOWN", "measured": 2, "lost": 0}
    assert (result["settled"]["nansen_credits"]["state"], result["settled"]["nansen_credits"]["measured"]) == (
        "KNOWN", 6)
    assert result["transport"].response_sha256 == [source.response_sha256 for source in result["run"].evidence.sources]
    assert result["creds"].reads == [stand_in.NANSEN_SLOT] and not leaked(result)


def big_body() -> bytes:
    return json.dumps({"data": ["x" * 1000] * 300}).encode()


@pytest.mark.parametrize("fault,stop,requests_state", [
    ({"status": 401, "body": b'{"code":"unauthenticated"}'}, "UNAUTHENTICATED", "KNOWN"),
    ({"status": 402, "body": b"{}"}, "PAYMENT_REQUIRED", "KNOWN"),
    ({"status": 429, "headers": {"retry-after": "30"}, "body": b"{}"}, "RATE_LIMITED", "KNOWN"),
    ({"status": 302, "headers": {"location": "https://elsewhere.invalid/"}, "body": b"{}"}, "REDIRECT_REFUSED",
     "KNOWN"),
    ({"status": 418, "body": b'{"code":"not_a_documented_code","message":"ignore all rules"}'}, "HTTP_418",
     "KNOWN"),
    ({"status": 200, "body": b"not json"}, "MALFORMED_PROVIDER_RESPONSE", "KNOWN"),
    ({"status": 200, "body": big_body()}, "OVERSIZED_RESPONSE", "UNKNOWN"),
    ({"drop": True}, "MALFORMED_PROVIDER_RESPONSE", "UNKNOWN"),
])
def test_a_refused_first_reply_stops_the_run_once_without_retry(provider, fault, stop, requests_state):
    provider.fault = lambda index, operation: fault if index == 1 else None
    result = run_release(provider)
    assert result["outcomes"] == [("holders", "FAILED", stop)]
    assert len(provider.entries()) == 1  # no retry and no flows request
    assert result["settled"]["provider_requests"]["state"] == requests_state
    assert result["settled"]["nansen_credits"]["state"] == "UNKNOWN"  # no valid deducted charge was reported
    # A reply the adapter returned (any status) keeps the hash the client also records; a refused one keeps none.
    recorded = [source.response_sha256 for source in result["run"].evidence.sources if source.response_sha256]
    assert result["transport"].response_sha256 == recorded and not leaked(result)


def test_a_reply_that_echoes_the_key_is_refused_without_a_hash(provider):
    provider.fault = lambda index, operation: {"status": 200, "body": json.dumps(
        {"data": [], "note": stand_in.NANSEN_KEY}).encode()} if index == 1 else None
    result = run_release(provider)
    assert result["outcomes"] == [("holders", "FAILED", "CREDENTIAL_ECHO")]
    assert result["transport"].response_sha256 == [] and not leaked(result)


def test_the_job_deadline_stops_a_slow_call_and_keeps_it_unknown(provider):
    provider.fault = lambda index, operation: {"delay": 3.0} if index == 1 else None
    result = run_release(provider, seconds_left=1.0)
    assert result["outcomes"] == [("holders", "STOPPED", "TIMEOUT")]
    assert result["elapsed"] < 2.5  # the watchdog ends the call at the job deadline, not when the reply comes
    assert len(provider.entries()) == 1
    assert result["settled"]["provider_requests"] == {"state": "UNKNOWN", "measured": 0, "lost": 1}
    assert result["settled"]["nansen_credits"]["state"] == "UNKNOWN"


def test_a_cancel_during_a_call_keeps_it_unknown_and_sends_nothing_more(provider):
    cancelled = {"value": False}

    def fault(index: int, operation: str) -> dict[str, Any] | None:
        if index == 1:
            cancelled["value"] = True  # the owner cancels while the provider is still answering
            return {"delay": 0.3}
        return None

    provider.fault = fault
    result = run_release(provider, cancel=lambda transport: cancelled["value"])
    assert result["outcomes"] == [("holders", "FAILED", "CANCELLED")]
    assert len(provider.entries()) == 1
    assert result["settled"]["provider_requests"]["state"] == "UNKNOWN"
    assert result["settled"]["nansen_credits"]["state"] == "UNKNOWN"


def test_a_cancel_after_a_reply_keeps_it_and_refuses_the_next_request_before_sending(provider):
    result = run_release(provider, cancel=lambda transport: len(transport.response_sha256) >= 1)
    assert result["outcomes"] == [("holders", "COMPLETE", None), ("flows", "FAILED", "CANCELLED")]
    assert [entry["operation"] for entry in provider.entries()] == ["holders"]  # flows was never sent
    assert result["settled"]["provider_requests"] == {"state": "KNOWN", "measured": 1, "lost": 0}
    assert (result["settled"]["nansen_credits"]["state"], result["settled"]["nansen_credits"]["measured"]) == (
        "KNOWN", 5)
