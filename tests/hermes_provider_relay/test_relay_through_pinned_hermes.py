"""ACTUAL pinned Hermes (commit 54bc5e5) in a no-network job; its one request leaves only through the relay.

The relay runs in its own container on an internal Docker network shared only with the AUTHORED provider, and is the
only holder of the synthetic key. Each test runs the saved interpretation path (`HermesInterpreter`) over
`build_relay_job` and checks the job report against the relay's records and the provider's receipts. Needs Docker.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research.hermes_interpreter import HermesTurn, Interpreted, Unavailable
from leak_scan import find_leaks
from relay_admission import RelaySubject
from relay_harness import (
    EXACT_CHARGE, POLICY, PRICE, RELEASE, RESERVATION, ROUTE, Rig, case, counts, provider_receipts, relay_events,
    relay_record,
)
from relay_turn_runner import build_relay_job
from spend_ledger import SpendLedger

from conftest import SENTINEL


def test_one_admitted_request_leaves_through_the_relay_with_the_relay_key_and_is_charged_exactly(
        relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, "valid", case())

    result = rig.run_case()

    assert isinstance(result, Interpreted) and result.attempt_id == "valid-1"
    saved, container = rig.saved(), rig.container_result("valid-1")
    observed = saved.settlement.runtime_observed
    assert (observed["transport_attempt_id"], observed["transport_request_attempt_ids"]) == ("valid-1", ["valid-1"])
    assert (observed["relay_release_id"], observed["relay_started"], observed["relay_outcome"]) == (
        RELEASE.release_id, True, "reply")
    assert observed["spend_state"] == "SETTLED" and rig.spend.committed_usd() == EXACT_CHARGE
    assert saved.settlement.request_count == 1 and counts(relay, "valid-1") == (1, 1)
    [receipt] = provider_receipts(relay, "valid-1")
    assert receipt["bearer_matches"] is True and receipt["path"] == "/v1/chat/completions"
    assert "authorization" in receipt["header_names"] and not {"x-stainless-retry-count", "user-agent"} & set(
        receipt["header_names"])  # nothing of Hermes' own headers passes
    assert container["sandbox"]["network"]["blocked"] is True and container["sandbox"]["credential_mounted"] is False
    assert container["transport"]["credential_attached"] is False
    assert relay_record(relay, "valid-1", "closed")["started"] is True
    assert relay_record(relay, "valid-1", "finished")["usage"] == {"prompt_tokens": 1423, "completion_tokens": 611,
                                                                    "total_tokens": 2034}
    assert ROUTE.route_id == json.loads((relay.path("grants") / "valid-1.json").read_text())["route_id"]
    assert find_leaks(evidence_root / "jobs", SENTINEL) == []


# --- refusals before the relay: nothing sent, released on the relay's own closed-not-started record -------------------


def test_a_request_the_job_guard_refuses_never_reaches_the_relay_and_is_released_on_the_relay_record(
        relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, "guard-refused", case())
    rig.job.supervision.policy = replace(POLICY, max_output_tokens=2048)  # the job is told a different output limit

    result = rig.run_case()

    assert isinstance(result, Unavailable)
    container = rig.container_result("guard-refused-1")
    assert container["transport"]["sent"] == [] and container["hermes"]["request_count"] == 0
    assert counts(relay, "guard-refused-1") == (0, 0) and relay_record(relay, "guard-refused-1", "closed")["started"] is False
    assert rig.spend.state("guard-refused-1") == "RELEASED" and rig.spend.committed_usd() == 0


def test_with_the_relay_down_no_grant_is_issued_no_job_starts_and_the_reservation_is_released(
        relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, "relay-down", case())
    relay.kill_relay()
    try:
        time.sleep(2.5)  # the heartbeat ages past its limit
        result = rig.run_case()
    finally:
        relay.start_relay()
    assert isinstance(result, Unavailable) and not list(rig.evidence.glob("turn-*-relay-down-1"))
    assert rig.saved().settlement.error_class == "RelayUnavailable" and rig.spend.state("relay-down-1") == "RELEASED"
    assert not (relay.path("grants") / "relay-down-1.json").exists() and counts(relay, "relay-down-1") == (0, 0)


# --- a possible request: the full reservation stays ----------------------------------------------------------------


@pytest.mark.parametrize("name, script, outcome", [
    ("lost", {"kind": "lost_reply"}, "lost"),
    ("oversized", {"kind": "oversized_reply", "bytes": 70_000}, "refused_reply"),
    ("redirect", {"kind": "redirect"}, "refused_reply"),
    ("provider-error", {"kind": "http_error", "status": 500, "message": "upstream failed"}, "reply"),
    ("no-usage", {"usage": None}, "reply"),
])
def test_a_request_that_may_have_cost_without_a_usable_reply_publishes_nothing_and_keeps_the_full_reservation(
        relay, pinned_hermes_image, evidence_root, name, script, outcome) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, name, {**case(), **script})

    result = rig.run_case()

    attempt = f"{name}-1"
    assert isinstance(result, Unavailable)
    assert counts(relay, attempt) == (1, 1) and relay_record(relay, attempt, "finished")["outcome"] == outcome
    assert rig.spend.state(attempt) == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_a_hung_provider_is_cut_at_the_grant_expiry_and_the_job_at_its_deadline_and_the_reservation_stays(
        relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, "hung", {"kind": "hang"}, timeout_seconds=25)
    began = time.monotonic()

    result = rig.run_case()

    elapsed = time.monotonic() - began
    assert isinstance(result, Unavailable) and elapsed < 25 + 5 + 2 + 5  # timeout + grace + close budget + slack
    assert counts(relay, "hung-1") == (1, 1) and relay_record(relay, "hung-1", "closed")["started"] is True
    deadline = time.monotonic() + 10
    while relay_record(relay, "hung-1", "finished") is None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert relay_record(relay, "hung-1", "finished")["outcome"] == "lost"
    assert rig.spend.state("hung-1") == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_a_relay_crash_after_a_possible_request_never_resends_and_the_attempt_stays_unknown(
        relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(relay, pinned_hermes_image, evidence_root, "relay-crash", {"kind": "hang"}, timeout_seconds=60)

    def crash_when_sent() -> None:
        deadline = time.monotonic() + 60
        while not provider_receipts(relay, "relay-crash-1") and time.monotonic() < deadline:
            time.sleep(0.1)
        relay.restart_relay()  # SIGKILL, then a new relay process over the same records

    crasher = threading.Thread(target=crash_when_sent)
    crasher.start()
    result = rig.run_case()
    crasher.join()

    assert isinstance(result, Unavailable)
    assert counts(relay, "relay-crash-1") == (1, 1)
    assert relay_record(relay, "relay-crash-1", "finished")["outcome"] == "unknown_restart"
    assert rig.container_result("relay-crash-1")["hermes"]["request_count"] == 1
    assert rig.spend.state("relay-crash-1") == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_two_attempts_at_once_keep_their_own_grants_requests_and_charges(relay, pinned_hermes_image, evidence_root) -> None:
    first = Rig(relay, pinned_hermes_image, evidence_root, "together-a", case())
    second = Rig(relay, pinned_hermes_image, evidence_root, "together-b", case())
    results: dict[str, Any] = {}
    threads = [threading.Thread(target=lambda r=rig: results.__setitem__(r.name, r.run_case())) for rig in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for rig in (first, second):
        attempt = f"{rig.name}-1"
        assert isinstance(results[rig.name], Interpreted) and counts(relay, attempt) == (1, 1)
        assert json.loads((relay.path("grants") / f"{attempt}.json").read_text())["attempt_id"] == attempt
        assert [r["attempt_id"] for r in provider_receipts(relay, attempt)] == [attempt]
        assert rig.spend.committed_usd() == EXACT_CHARGE


# --- a hostile job: no key, no network, no way around the relay's admission -----------------------------------------


def hostile(relay, image: str, root: Path, name: str, actions: dict[str, Any]) -> tuple[Rig, dict[str, Any]]:
    rig = Rig(relay, image, root, name, {**case(), "hostile": actions})
    entry = rig.job.supervision.job_entry
    rig.job.supervision.job_entry = replace(entry, script="/opt/p05job/hostile_relay_job.py", files=(
        *entry.files, (Path(__file__).parent / "hostile_relay_job.py", "/opt/p05job/hostile_relay_job.py")))
    rig.run_case()
    return rig, json.loads((rig.output(f"{name}-1") / "hostile-result.json").read_text())


def test_a_hostile_job_finds_no_key_and_no_network_path(relay, pinned_hermes_image, evidence_root) -> None:
    targets = [["authored-provider", 8443], [relay.names["relay"], 8443], ["1.1.1.1", 53],
               ["host.docker.internal", 5432]]
    rig, found = hostile(relay, pinned_hermes_image, evidence_root, "hostile-probe",
                         {"probe_key": True, "probe_egress": targets})
    assert found["key"] == {"readable_key_files": [], "key_like_environment": []}
    assert [entry["connected"] for entry in found["egress"]] == [False, False, False, False]
    assert counts(relay, "hostile-probe-1") == (0, 0) and relay_record(relay, "hostile-probe-1", "closed")["started"] is False
    assert rig.spend.state("hostile-probe-1") == "UNKNOWN"  # no counted result from the job: liability is kept


@pytest.mark.parametrize("name, actions, refusal", [
    ("hostile-model", {"message": {}, "body_changes": {"model": "other-model/9"}}, "guard:model_not_as_configured"),
    ("hostile-route", {"message": {"route_id": "other-route"}}, "route_mismatch"),
    ("hostile-release", {"message": {"release_id": "local-relay-2"}}, "release_mismatch"),
    ("hostile-attempt", {"message": {"attempt_id": "valid-1"}}, "attempt_mismatch"),
    ("hostile-header", {"message": {"authorization": "Bearer sk-attacker-supplied"}}, "channel_field_not_permitted"),
    ("hostile-url", {"message": {"url": "https://exfiltrate.invalid/v1"}}, "channel_field_not_permitted"),
    ("hostile-big", {"message": {}, "body_changes": {"padding": "x" * 13_000}}, "request_too_large"),
])
def test_a_hostile_channel_message_is_refused_by_the_relay_before_any_request(
        relay, pinned_hermes_image, evidence_root, name, actions, refusal) -> None:
    rig, found = hostile(relay, pinned_hermes_image, evidence_root, name, actions)
    assert found["replies"] == [{"attempt_id": f"{name}-1", "outcome": "refused", "refusal": refusal, "before_send": True}]
    assert counts(relay, f"{name}-1") == (0, 0)


def test_a_hostile_duplicate_request_is_answered_once_and_sent_once(relay, pinned_hermes_image, evidence_root) -> None:
    rig, found = hostile(relay, pinned_hermes_image, evidence_root, "hostile-twice", {"message": {}, "repeat": 2})
    assert found["replies"][0]["outcome"] == "reply" and found["replies"][1:] == [None, None]
    assert counts(relay, "hostile-twice-1") == (1, 1)
    assert [e["reason"] for e in relay_events(relay, "hostile-twice-1")] == []  # never even handled twice


# --- enforcement, supervision and restart -------------------------------------------------------------------------


def test_the_relay_has_only_the_internal_network_and_only_its_own_mounts(relay) -> None:
    seen = relay.inspect()
    assert seen["relay_networks"] == [relay.names["network"]] and seen["network_internal"] is True
    assert seen["network_members"] == sorted([relay.names["relay"], relay.names["provider"]])
    assert not seen["relay_ports"]
    assert seen["relay_mounts"] == sorted(["/relay/code", "/relay/support/job", "/relay/support/interpretation",
                                           "/relay/config.json", "/relay/secrets/provider-key",
                                           "/relay/secrets/admission-key", "/relay/tls/ca.pem", "/relay/grants",
                                           "/relay/revocations", "/relay/state", "/relay/channels/jobs"])
    probe = {(p["host"], p["port"]): p["reached"] for p in relay.heartbeat()["egress_probe"]}
    assert probe[("authored-provider", 8443)] is True and probe[("1.1.1.1", 53)] is False
    assert probe[("host.docker.internal", 80)] is False and list(probe.values()).count(True) == 1


def test_a_host_killed_mid_turn_is_recovered_its_grant_closes_at_expiry_and_its_reservation_stays(
        relay, pinned_hermes_image, run_id, evidence_root) -> None:
    root = evidence_root / "rigs" / "host-killed"
    root.mkdir(parents=True)
    spend_path, evidence, dead_run = root / "spend.sqlite", evidence_root / "jobs", f"{run_id}-dead"
    relay.path("provider", "scripts", "attempt-dead-1.json").write_text(json.dumps({"kind": "hang"}))
    here = Path(__file__).resolve().parent
    paths = [str(here.parents[1] / "apps" / "api" / "src"), str(here.parents[1] / "scripts" / "hermes_interpretation"),
             str(here.parents[1] / "scripts" / "hermes_job_support"), str(here.parents[1] / "scripts" / "hermes_provider_relay"),
             str(here), str(here.parents[1] / "apps" / "api" / "tests")]
    host = subprocess.Popen([sys.executable, str(here / "relay_turn_host.py"), pinned_hermes_image, dead_run, str(evidence),
                             str(spend_path), str(relay.root)], env={**os.environ, "PYTHONPATH": os.pathsep.join(paths)})
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not provider_receipts(relay, "attempt-dead-1"):
            time.sleep(0.2)
        assert provider_receipts(relay, "attempt-dead-1"), "the request never reached the provider"
    finally:
        host.send_signal(signal.SIGKILL)
        host.wait()
    spend = SpendLedger(spend_path, cap_usd=Decimal("0.20"), price=PRICE)
    assert (spend.state("attempt-dead-1"), spend.committed_usd()) == ("RESERVED", RESERVATION)
    same = build_relay_job(ROUTE, release=RELEASE, endpoint=relay.endpoint("jobs"),
                           subject_for=lambda turn: RelaySubject("o", "r"), policy=POLICY, ledger=spend,
                           scope_for=lambda turn: "case-dead", image=pinned_hermes_image, run_id=dead_run,
                           evidence_dir=evidence, script_for=lambda turn: case())
    [pending] = same.supervision.pending_cleanup()
    assert pending["state"] == "running"  # the dead turn's identity survived the host
    assert same.supervision.recover_pending(30.0) == []  # one supervised pass, one budget C
    deadline = time.monotonic() + 60
    while relay_record(relay, "attempt-dead-1", "closed") is None and time.monotonic() < deadline:
        time.sleep(0.5)
    assert relay_record(relay, "attempt-dead-1", "closed") == {**relay_record(relay, "attempt-dead-1", "closed"),
                                                               "started": True, "why": "expired"}
    assert counts(relay, "attempt-dead-1") == (1, 1) and spend.state("attempt-dead-1") == "RESERVED"
    blocked = same.runner.run_turn(HermesTurn("attempt-next-1", "prompt", "task", POLICY.model, "local", 4096))
    assert blocked.error_class == "SpendScopeBlocked" and counts(relay, "attempt-next-1") == (0, 0)


def test_no_evidence_record_or_log_holds_the_synthetic_key(relay, evidence_root, synthetic_key) -> None:
    assert find_leaks(evidence_root / "jobs", SENTINEL) == []
    assert find_leaks(relay.root, SENTINEL) == []
    assert SENTINEL not in relay.logs()
