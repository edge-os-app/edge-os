"""#58 RESEARCH-RUNTIME-LOCAL review repair: host-only proof of release validation and the per-call deadline.

These tests use no database, API, Docker, browser or network. They drive the release validator, the runtime
composition, the credential reads and the hashing transport through their public seams with in-process stand-ins
and an injected monotonic clock. Findings: review A F1 / B B3 (per-call deadline), B B1 / A F2 (release kind),
B B2 (runtime trust), B B4 (malformed QuickNode URL), B B5 (source id collision), B B6 (credential-source errors),
B B7 (hash alignment) and A F3 (verifier cleanup isolation).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from typing import Any

import pytest

import forward_history_stand_in as bound
import harness
import operating_release_stand_in as stand_in
from edge_os_api.core.research import operating_release
from edge_os_api.core.research.operating_release import OperatingRelease, ReleaseRefused, check_release
from edge_os_api.core.research.released_source_runtime import (
    ReleasedSourceRuntime,
    open_released_runtime,
    prepare_history,
    release_view,
)
from edge_os_api.research import history_dataset, history_payload_binding
from edge_os_api.research_history.http_clients import HttpResponse, StdlibHttpTransport
from edge_os_api.research_history.provider_transport import SourceTimeout

LOCAL = type("Local", (), {"env": "local"})()
PRODUCTION = type("Production", (), {"env": "production"})()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TimedInner:
    """An inner transport that records each call's remaining whole-call bound and advances the clock."""

    def __init__(self, clock: Clock, *, step: float = 0.0, lose_at: int | None = None) -> None:
        self.clock, self.step, self.lose_at = clock, step, lose_at
        self.bounds: list[float] = []

    def request(self, **kwargs: Any) -> HttpResponse:
        self.bounds.append(kwargs["deadline"] - self.clock())
        self.clock.now += self.step
        if self.lose_at is not None and len(self.bounds) == self.lose_at:
            raise OSError("stand-in: the reply was lost")
        call_id = json.loads(kwargs["body"])["id"]
        return HttpResponse(status=200, headers={"content-type": "application/json"},
                            body=json.dumps({"jsonrpc": "2.0", "id": call_id, "result": "0x8f"}).encode())


def runtime_with(inner: TimedInner) -> ReleasedSourceRuntime:
    return open_released_runtime(LOCAL, stand_in.stand_in_release(nansen=False), credentials=stand_in.credentials(),
                                 http_transport=lambda: inner)


# --------------------------------------------------------------------------- A F1 / B B3: per-call deadline

def test_every_later_call_is_bounded_by_the_time_the_job_has_left():
    clock = Clock()
    inner = TimedInner(clock, step=1.5)
    _, quicknode, _ = prepare_history(runtime_with(inner)).clients(2.0, lambda: False, clock=clock)
    quicknode.call("eth_chainId", [])
    with pytest.raises(SourceTimeout):  # the second call starts with 0.5 s left and ends past the job deadline
        quicknode.call("eth_chainId", [])
    assert inner.bounds[0] == pytest.approx(2.0)
    assert inner.bounds[1] == pytest.approx(0.5)  # not the 2.0 s the first call had


def test_a_call_after_the_job_deadline_is_refused_before_it_is_sent():
    clock = Clock()
    inner = TimedInner(clock, step=2.5)
    _, quicknode, transport = prepare_history(runtime_with(inner)).clients(2.0, lambda: False, clock=clock)
    with pytest.raises(SourceTimeout):
        quicknode.call("eth_chainId", [])  # sent, but its reply arrives after the job deadline
    with pytest.raises(SourceTimeout):
        quicknode.call("eth_chainId", [])  # never sent
    assert len(inner.bounds) == 1
    assert transport.facts()["request_sha256"] == transport.request_sha256 and len(transport.request_sha256) == 1
    assert quicknode.accounting()["unknown_liability"] >= 1  # a possible effect stays unknown, never zero


# --------------------------------------------------------------------------- B B7: hash alignment

def test_request_status_and_reply_hashes_stay_aligned_after_a_lost_reply():
    clock = Clock()
    inner = TimedInner(clock, lose_at=1)
    _, quicknode, transport = prepare_history(runtime_with(inner)).clients(60.0, lambda: False, clock=clock)
    with pytest.raises(OSError):
        quicknode.call("eth_chainId", [])
    quicknode.call("eth_chainId", [])
    assert len(transport.request_sha256) == len(transport.response_status) == len(transport.response_sha256) == 2
    assert transport.response_status[0] is None and transport.response_sha256[0] is None
    assert transport.response_status[1] == 200 and transport.response_sha256[1]


# --------------------------------------------------------------------------- B B1 / A F2 and B B2: release kind and trust

@pytest.mark.parametrize("kind", ["actual", "LIVE", "", "stand_in"])
def test_a_release_kind_outside_the_two_known_kinds_is_refused(kind):
    real = stand_in.stand_in_release(envio_endpoint="https://hypersync.example.com",
                                     quicknode_host="quicknode.example.com", nansen=False)
    release = dataclasses.replace(real, kind=kind)
    creds = stand_in.credentials()
    with pytest.raises(ReleaseRefused) as refused:
        check_release(release, network_transport=True)
    assert refused.value.code == "operating_release_invalid"
    for settings in (LOCAL, PRODUCTION):
        with pytest.raises(ReleaseRefused):
            open_released_runtime(settings, release, credentials=creds, http_transport=StdlibHttpTransport)
    assert creds.reads == []


def test_a_runtime_cannot_be_built_around_the_validator():
    release = stand_in.stand_in_release(nansen=False)
    creds = stand_in.credentials()
    good = open_released_runtime(LOCAL, release, credentials=creds, http_transport=stand_in.RecordingStandIn().transport)
    with pytest.raises(ReleaseRefused):  # a forged digest
        ReleasedSourceRuntime(release, "0" * 64, creds, good.http_transport, None, False)
    with pytest.raises(ReleaseRefused):  # a recording claimed to be the network transport
        ReleasedSourceRuntime(release, good.release_sha256, creds, good.http_transport, None, True)
    with pytest.raises(ReleaseRefused):  # an unknown kind with a matching digest of itself
        odd = dataclasses.replace(release, kind="odd")
        ReleasedSourceRuntime(odd, operating_release.release_sha256(odd), creds, good.http_transport, None, False)
    assert creds.reads == []


# --------------------------------------------------------------------------- B B4 and B B6: credential reads

@pytest.mark.parametrize("url", ["https://user:pw@quicknode.stand-in.invalid/stand-in-key-SENTINEL-55e0a1/",
                                 "http://quicknode.stand-in.invalid/stand-in-key-SENTINEL-55e0a1/",
                                 "https://quicknode.stand-in.invalid/key/#fragment"])
def test_a_malformed_quicknode_url_on_the_release_host_is_refused_at_the_credential_read(url):
    runtime = open_released_runtime(LOCAL, stand_in.stand_in_release(nansen=False),
                                    credentials=stand_in.credentials(quicknode=url),
                                    http_transport=stand_in.RecordingStandIn().transport)
    with pytest.raises(ReleaseRefused) as refused:
        prepare_history(runtime)
    assert refused.value.code == "operating_release_endpoint_mismatch"
    assert "SENTINEL" not in str(refused.value)


class BrokenCredentials:
    def __init__(self, error: BaseException) -> None:
        self.error, self.reads = error, 0

    def read(self, slot: str) -> str:
        self.reads += 1
        raise self.error


@pytest.mark.parametrize("error", [PermissionError("secret-store-detail-SENTINEL"), OSError("io"),
                                   ValueError("bad")])
def test_a_credential_source_error_becomes_one_stable_refusal_without_its_detail(error):
    creds = BrokenCredentials(error)
    runtime = open_released_runtime(LOCAL, stand_in.stand_in_release(nansen=False), credentials=creds,
                                    http_transport=stand_in.RecordingStandIn().transport)
    with pytest.raises(ReleaseRefused) as refused:
        prepare_history(runtime)
    assert refused.value.code == "operating_release_credential_unavailable"
    assert "SENTINEL" not in str(refused.value) and creds.reads == 1


# --------------------------------------------------------------------------- B B5: source id collision

def test_a_release_source_id_that_names_a_recorded_source_is_refused():
    runtime = open_released_runtime(LOCAL, stand_in.stand_in_release(source_id="native-syn-qualified/1", nansen=False),
                                    credentials=stand_in.credentials(),
                                    http_transport=stand_in.RecordingStandIn().transport)
    with pytest.raises(ReleaseRefused) as refused:
        history_dataset.check_release_source(runtime)
    assert refused.value.code == "operating_release_invalid"
    distinct = open_released_runtime(LOCAL, stand_in.stand_in_release(nansen=False), credentials=stand_in.credentials(),
                                     http_transport=stand_in.RecordingStandIn().transport)
    history_dataset.check_release_source(distinct)  # the default stand-in id is its own
    assert history_dataset.served_sources()["native-syn-qualified/1"]["evidence_class"] == "RECORDED_NATIVE_RESPONSE"


# --------------------------------------------------------------------------- A F3: verifier cleanup isolation

def _verify_run():
    sys.path.insert(0, str(harness.REPO / "scripts" / "p03"))
    import verify_run

    return verify_run


@pytest.mark.parametrize("line,kept", [
    ("unlabelled-user-container\t\t", True),                       # an unrelated change stays visible
    ("edge-os-test-pg-pmine\tpmine\t", True),                      # this run's own resource stays visible
    ("edge-os-test-pg-pmine\tpmine\tl4dev3", True),                # own label wins over any rehearsal label
    ("edge-os-test-pg-pother\tpother\t", False),                   # another labelled test run
    ("priceless_diffie\t\tl4dev3", False),                         # another lane's labelled rehearsal
    ("edge-os-test-pg-pother\tpother\tl4dev3", False),             # another run, whatever else it carries
])
def test_the_cleanup_comparison_hides_only_other_runs_labelled_resources(line, kept):
    assert (verify_run_names(line) == [line.split("\t")[0]]) is kept


def verify_run_names(listing: str) -> list[str]:
    return _verify_run().comparable_names(listing, "pmine")


# --------------------------------------------------------------------------- controller dw-l2-clock3.md

def test_a_delayed_client_build_keeps_the_saved_job_deadline():
    """Review B R2-N2: the clients the worker builds after a setup delay keep the job's SAVED deadline."""
    import datetime as dt

    from edge_os_api.research import investigation_jobs

    t0 = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
    clock = Clock()  # monotonic 1000.0 == wall t0
    wall = lambda: t0 + dt.timedelta(seconds=clock.now - 1000.0)  # noqa: E731
    deadline_at = t0 + dt.timedelta(seconds=1.0)  # saved deadline == monotonic 1001.0
    inner = TimedInner(clock, step=0.2)
    factory = investigation_jobs.release_http_clients(prepare_history(runtime_with(inner)), deadline_at, wall,
                                                      clock=clock)
    clock.now = 1000.25  # the attempt commit and setup delay before the clients exist
    _, quicknode, _ = factory(None, None, lambda: False)
    clock.now = 1000.9  # admitted before the saved deadline; the reply arrives at 1001.1
    with pytest.raises(SourceTimeout):
        quicknode.call("eth_chainId", [])
    assert inner.bounds == [pytest.approx(0.1)]  # 1001.0 - 1000.9, not 1001.25 - 1000.9


def test_a_production_worker_refuses_a_stand_in_runtime():
    """Review A N1: the worker seam applies the same production refusal as open_released_runtime and create_app."""
    from edge_os_api.research.investigation_jobs import InvestigationWorker

    runtime = ReleasedSourceRuntime(stand_in.stand_in_release(nansen=False),
                                    operating_release.release_sha256(stand_in.stand_in_release(nansen=False)),
                                    stand_in.credentials(), stand_in.RecordingStandIn().transport, None, False)
    with pytest.raises(ReleaseRefused) as refused:
        InvestigationWorker(None, PRODUCTION, research_runtime=runtime)
    assert refused.value.code == "stand_in_refused_in_production"
    InvestigationWorker(None, LOCAL, research_runtime=runtime)  # local composition is unchanged


# --------------------------------------------------------------------------- SAVED-HISTORY-BINDING-L2: binding admission

def _bound_admission(binding: Any, *, kind: str = "STAND_IN") -> tuple[pytest.ExceptionInfo, Any]:
    release = bound.bound_release(nansen=False, binding=binding)
    if kind != "STAND_IN":  # an actual release names provider hosts, so only the binding rule can refuse it
        release = bound.bound_release(nansen=False, binding=binding, kind=kind,
                                      envio_endpoint="https://hypersync.example.com",
                                      quicknode_host="quicknode.example.com")
    creds = stand_in.credentials()
    with pytest.raises(ReleaseRefused) as refused:
        open_released_runtime(LOCAL, release, credentials=creds, http_transport=lambda: TimedInner(Clock()))
    assert creds.reads == []  # refused before any credential read
    return refused, creds


def _bound_definition(**changes: Any) -> dict[str, str]:
    return bound.definition(bound.handoff(**changes))


def test_a_bound_stand_in_release_is_admitted_and_its_handoff_enters_the_release_hash():
    unbound = bound.bound_release(nansen=False, binding=None)
    bound_release = bound.bound_release(nansen=False)
    other = bound.bound_release(nansen=False, binding=_bound_definition(attempt_id="another-synthetic-attempt"))
    digests = {check_release(release) for release in (unbound, bound_release, other)}
    assert len(digests) == 3
    assert operating_release.release_sha256(unbound) == operating_release.release_sha256(
        bound.bound_release(nansen=False, binding=None))  # an unbound release keeps its own hash
    runtime = open_released_runtime(LOCAL, bound_release, credentials=stand_in.credentials(),
                                    http_transport=lambda: TimedInner(Clock()))
    view = release_view(runtime)["history"]["payload_binding"]
    assert view == {"handoff_sha256": bound.definition()["handoff_sha256"], "evidence_class": "SYNTHETIC"}
    assert "payload_binding" not in release_view(runtime_with(TimedInner(Clock())))["history"]


@pytest.mark.parametrize("binding", [
    "not-an-object",
    {"handoff_json": "{}"},
    {"handoff_json": "{}", "handoff_sha256": "x", "extra": "y"},
    {"handoff_json": 7, "handoff_sha256": "x"},
])
def test_a_malformed_binding_is_a_stable_refusal_before_credentials(binding):
    refused, _ = _bound_admission(binding)
    assert refused.value.code == "forward_history_binding_invalid"


def test_a_binding_whose_digest_differs_from_its_bytes_is_refused():
    good = _bound_definition()
    refused, _ = _bound_admission({**good, "handoff_sha256": "0" * 64})
    assert refused.value.code == "forward_history_binding_invalid" and "digest" in refused.value.detail


def test_an_oversized_handoff_is_refused_before_it_is_parsed():
    text = " " * (8 * 1024 * 1024 + 1)
    refused, _ = _bound_admission({"handoff_json": text, "handoff_sha256": hashlib.sha256(text.encode()).hexdigest()})
    assert refused.value.code == "forward_history_binding_invalid" and "ceiling" in refused.value.detail


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":1.5}', "[1]", "not json"])
def test_a_non_strict_or_non_object_handoff_is_refused(text):
    refused, _ = _bound_admission({"handoff_json": text, "handoff_sha256": hashlib.sha256(text.encode()).hexdigest()})
    assert refused.value.code == "forward_history_binding_invalid"


@pytest.mark.parametrize("changes,detail", [
    ({"schema_version": "edge-os.forward-history-handoff/2"}, "schema version"),
    ({"canonicalization_version": "edge-os.forward-history-payload/0"}, "canonicalization"),
    ({"evidence_class": "ACTUAL"}, "SYNTHETIC"),
    ({"source_id": "another-source/1"}, "another source"),
    ({"window": {"start_utc": "2026-09-25T10:05:00Z", "end_utc": "2026-09-25T10:25:00Z", "bucket_seconds": 300}},
     "window"),
    ({"scan": {"from_block": 500, "to_block_exclusive": 507}}, "scan"),
])
def test_a_handoff_for_another_version_source_window_scan_or_class_is_refused(changes, detail):
    refused, _ = _bound_admission(_bound_definition(**changes))
    assert refused.value.code == "forward_history_binding_invalid" and detail in refused.value.detail


def test_a_binding_on_an_actual_release_is_never_admitted():
    refused, _ = _bound_admission(_bound_definition(), kind="ACTUAL")
    assert refused.value.code == "forward_history_binding_not_admitted"


def test_an_unavailable_checker_refuses_a_bound_release(monkeypatch):
    definition = _bound_definition()
    history_payload_binding.checker.cache_clear()
    monkeypatch.setattr(history_payload_binding, "CHECKER_SHA256", "0" * 64)
    try:
        refused, _ = _bound_admission(definition)
        assert refused.value.code == "forward_history_checker_unavailable"
    finally:
        history_payload_binding.checker.cache_clear()
