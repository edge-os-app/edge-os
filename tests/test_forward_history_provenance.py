"""Synthetic execution of the actual seam. HTTPSConnection is an in-memory peer, never a provider."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import stat
import time
from pathlib import Path

import pytest

from scripts import forward_history_recorder as recorder
from tests.test_forward_history_recorder import Credentials, FakeClock, SyntheticProviders, T0, recorder_input
from tests.test_forward_history_transport_receipts import FixtureConnection


def actual_run(tmp_path, monkeypatch):
    clock = FakeClock(T0 - 600)
    clock.mono = time.monotonic()
    providers = SyntheticProviders(clock)
    monkeypatch.setattr(http.client, "HTTPSConnection", lambda host, port, timeout: FixtureConnection(
        providers, "https", host, port))
    credentials = Credentials()
    assert hasattr(recorder, "run_actual_attempt"), "the accepted actual producer is missing"
    result = recorder.run_actual_attempt(recorder_input(tmp_path, evidence_class="ACTUAL"), clock=clock,
                                         credentials=credentials)
    return result, providers, credentials, tmp_path / "attempts" / "synthetic-attempt-1"


def test_actual_seam_writes_private_acyclic_artifacts_once(tmp_path, monkeypatch):
    result, providers, credentials, directory = actual_run(tmp_path, monkeypatch)
    assert result["status"] == "COMPLETED" and len(providers.calls) == 22
    assert credentials.reads == ["quicknode_monad_url", "envio_hypersync_bearer"]
    h, r, p = [directory.joinpath(name).read_bytes() for name in (
        "handoff.json", "transport-receipts.json", "provenance.json")]
    handoff, receipts, provenance = map(json.loads, (h, r, p))
    assert handoff["schema_version"] == "edge-os.forward-history-handoff/2"
    assert handoff["evidence_class"] == receipts["evidence_class"] == "ACTUAL"
    assert "receipts_sha256" not in handoff and "provenance_sha256" not in handoff
    assert receipts["handoff_sha256"] == provenance["handoff_sha256"] == hashlib.sha256(h).hexdigest()
    assert provenance["receipts_sha256"] == hashlib.sha256(r).hexdigest()
    assert provenance["receipts_json"].encode() == r
    assert provenance["transport"] == receipts["transport"] == handoff["transport"]
    assert handoff["transport"]["construction"] == "OWNED_STDLIB"
    assert len(receipts["receipts"]) == 22
    for name in ("handoff.json", "transport-receipts.json", "provenance.json"):
        assert stat.S_IMODE(directory.joinpath(name).stat().st_mode) == 0o600
    with pytest.raises(recorder.AttemptExists):
        recorder.run_actual_attempt(recorder_input(tmp_path, evidence_class="ACTUAL"), clock=FakeClock(T0),
                                    credentials=credentials)
    assert len(providers.calls) == 22


@pytest.mark.parametrize("failed,code,later", [
    ("handoff.json", "forward_history_handoff_missing", ["transport-receipts.json", "provenance.json"]),
    ("transport-receipts.json", "forward_history_provenance_missing", ["provenance.json"]),
    ("provenance.json", "forward_history_provenance_missing", []),
])
def test_partial_write_retains_prefix_and_stops_without_resend(tmp_path, monkeypatch, failed, code, later):
    write = recorder.write_exclusive
    writes = []

    def fail(path, body):
        writes.append(path.name)
        if path.name != failed:
            return write(path, body)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, body[:10])
        finally:
            os.close(fd)
        raise OSError(28, "synthetic disk full")

    monkeypatch.setattr(recorder, "write_exclusive", fail)
    result, providers, _, directory = actual_run(tmp_path, monkeypatch)
    assert result["code"] == code
    assert len(directory.joinpath(failed).read_bytes()) == 10
    assert all(not directory.joinpath(name).exists() for name in later)
    assert writes.count(failed) == 1 and len(providers.calls) == 22
    assert directory.joinpath("journal.jsonl").exists()


@pytest.mark.parametrize("construction,code", [("INJECTED", "forward_history_provenance_injected"),
                                               ("LOCAL_FIXTURE", "forward_history_provenance_fixture")])
def test_untrusted_construction_is_refused_before_credentials(tmp_path, monkeypatch, construction, code):
    clock = FakeClock(T0)
    transport = SyntheticProviders(clock) if construction == "INJECTED" else recorder.local_fixture_transport(
        lambda *args: None, clock.monotonic)
    monkeypatch.setattr(recorder, "owned_stdlib_transport", lambda: transport)
    credentials = Credentials()
    assert hasattr(recorder, "run_actual_attempt"), "the accepted actual producer is missing"
    result = recorder.run_actual_attempt(recorder_input(tmp_path, evidence_class="ACTUAL"), clock=clock,
                                         credentials=credentials)
    assert result["code"] == code and credentials.reads == []


def test_actual_cli_refuses_malformed_input_without_credentials(tmp_path, capsys):
    from importlib import import_module
    path = Path(__file__).resolve().parents[1] / "scripts/forward_history_actual_run.py"
    assert path.exists(), "the actual-running entry point is missing"
    cli = import_module("scripts.forward_history_actual_run")
    input_path = tmp_path / "input.json"
    input_path.write_text('{"schema_version":"wrong"}')
    assert cli.main(["--input", str(input_path)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "INPUT_KEYS"


def test_actual_producer_owns_exactly_one_construction(tmp_path, monkeypatch):
    constructions = []
    construct = recorder.owned_stdlib_transport

    def tracked():
        transport = construct()
        constructions.append(transport)
        return transport

    monkeypatch.setattr(recorder, "owned_stdlib_transport", tracked)
    result, _, _, _ = actual_run(tmp_path, monkeypatch)
    assert result["status"] == "COMPLETED" and len(constructions) == 1


@pytest.mark.parametrize("kind", ["subclass", "modified", "wrapper"])
def test_actual_seam_refuses_nonoriginal_owned_objects(tmp_path, monkeypatch, kind):
    class Subclass(recorder.StdlibHttpTransport):
        pass

    class Wrapper:
        def request(self, **kwargs):
            raise AssertionError("must refuse before sending")

    transport = Subclass() if kind == "subclass" else Wrapper() if kind == "wrapper" else recorder.owned_stdlib_transport()
    if kind == "modified":
        transport._clock = lambda: 0
    monkeypatch.setattr(recorder, "owned_stdlib_transport", lambda: transport)
    credentials = Credentials()
    result = recorder.run_actual_attempt(recorder_input(tmp_path, evidence_class="ACTUAL"), clock=FakeClock(T0),
                                         credentials=credentials)
    assert result["code"] == "forward_history_provenance_injected" and credentials.reads == []
