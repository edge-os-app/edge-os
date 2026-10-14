"""The host turn runner with an ACTUAL route (CONTRACT A6): only with an approved release record whose request shape the
policy matches, and a counted result only when the relay recorded a provider cost within the attempt's reservation.
A fake job and written relay records stand in for the containers: no network, no Docker, no key."""

from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import relay_admission
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from provider_guard import GuardPolicy
from provider_transport import ActualProviderUnavailable, TransportRoute
from relay_admission import ActualRelease, RelaySubject, load_actual_release
from relay_harness import PRICE, RELEASE, ROUTE
from relay_turn_runner import RelayEndpoint, build_relay_job
from spend_ledger import SpendLedger

SCHEMA = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {"type": "object"}}}
ROUTING = {"only": ["synthetic-slug"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 1, "completion": 2}}
EXTRA = {"stream": False, "provider": ROUTING, "reasoning": {"effort": "low"}, "response_format": SCHEMA}
POLICY = GuardPolicy(model="fixture-model/1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500,
                     required_extra=EXTRA)
USAGE = Usage(1423, 611, 2034, "PROVIDER_REPORTED")
TURN = HermesTurn("att-1", "system prompt", "user task", POLICY.model, "relay", POLICY.max_output_tokens)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture
def actual(monkeypatch: pytest.MonkeyPatch) -> ActualRelease:
    raw = json.dumps({
        "release_id": "rel-synthetic-1", "route_id": "route-synthetic", "kind": "ACTUAL",
        "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
        "destination": {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"},
        "ca_bundle_sha256": "b" * 64, "model": "fixture-model/1", "provider": ROUTING, "max_tokens": 4096,
        "reasoning": {"effort": "low"}, "response_format_sha256": hashlib.sha256(canonical(SCHEMA)).hexdigest(),
        "stream": False, "allowed_fields": ["model", "messages", "stream", "response_format", "provider", "reasoning",
                                            "max_tokens", "session_id"],
        "max_request_bytes": 12_000, "max_reply_bytes": 65_536, "timeout_seconds": 90,
        "price_snapshot_sha256": "c" * 64}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({sha}))
    return load_actual_release(raw, sha)


def route(release: ActualRelease, **changes: Any) -> TransportRoute:
    fields = {"route_id": "route-synthetic", "kind": "ACTUAL", "endpoint_url": release.endpoint_url,
              "max_reply_bytes": 65_536, **changes}
    return TransportRoute(**fields)


def build(tmp_path: Path, actual: ActualRelease | None, the_route: TransportRoute, *, release: Any = None,
          policy: GuardPolicy = POLICY, ledger: Any = None) -> Any:
    return build_relay_job(the_route, release=release or (actual.release if actual else RELEASE), actual=actual,
                           endpoint=RelayEndpoint(*(tmp_path / n for n in ("grants", "revocations", "state", "key")), "jobs"),
                           subject_for=lambda turn: RelaySubject("owner-a", "intake-1"), policy=policy, ledger=ledger,
                           scope_for=lambda turn: "scope-1", image="unused", run_id="run-1",
                           evidence_dir=tmp_path / "jobs", script_for=lambda turn: {}, close_budget_seconds=0.3)


def test_construction_with_an_approved_record_does_no_io(tmp_path: Path, actual: ActualRelease) -> None:
    build(tmp_path, actual, route(actual))
    assert list(tmp_path.iterdir()) == []


def test_an_actual_route_without_its_record_or_an_authored_route_with_one_is_refused(
        tmp_path: Path, actual: ActualRelease) -> None:
    with pytest.raises(ActualProviderUnavailable):
        build(tmp_path, None, route(actual), release=RELEASE)
    with pytest.raises(ValueError):
        build(tmp_path, actual, ROUTE, release=actual.release)


@pytest.mark.parametrize("route_change, policy_change", [
    ({"endpoint_url": "https://openrouter.ai/api/v1/other"}, {}),
    ({"max_reply_bytes": 1024}, {}),
    ({}, {"required_extra": {**EXTRA, "provider": {**ROUTING, "allow_fallbacks": True}}}),
    ({}, {"required_extra": {**EXTRA, "stream": True}}),
    ({}, {"required_extra": {k: v for k, v in EXTRA.items() if k != "reasoning"}}),
    ({}, {"required_extra": {**EXTRA, "response_format": {"type": "json_object"}}}),
])
def test_a_route_or_policy_that_differs_from_the_record_is_refused(tmp_path: Path, actual: ActualRelease,
                                                                    route_change: dict[str, Any],
                                                                    policy_change: dict[str, Any]) -> None:
    policy = GuardPolicy(**{**{"model": POLICY.model, "max_output_tokens": 4096, "max_request_bytes": 12_000,
                               "max_envelope_chars": 2_500, "required_extra": EXTRA}, **policy_change})
    with pytest.raises(ValueError):
        build(tmp_path, actual, route(actual, **route_change), policy=policy)


class Rig:
    def __init__(self, tmp_path: Path, actual: ActualRelease, finished: dict[str, Any]) -> None:
        state = tmp_path / "state"
        for folder in ("grants", "revocations", "state"):
            (tmp_path / folder).mkdir()
        (tmp_path / "key").write_bytes(b"a" * 32)
        (state / "heartbeat.json").write_text(json.dumps({"release": actual.release.settings(), "at": time.time(),
                                                          "started_at": 0}))
        self.spend = SpendLedger(tmp_path / "spend.sqlite", cap_usd=Decimal("0.20"), price=PRICE)
        self.job = build(tmp_path, actual, route(actual), ledger=self.spend)

        def run_turn(turn: HermesTurn) -> HermesTurnResult:
            folder = state / turn.attempt_id
            folder.mkdir()
            (folder / "closed.json").write_text(json.dumps({"started": True}))
            (folder / "finished.json").write_text(json.dumps(finished))
            observed = {"guard_admitted": 1, "transport_attempt_id": turn.attempt_id,
                        "transport_route_id": "route-synthetic", "transport_sent": 1,
                        "transport_request_attempt_ids": [turn.attempt_id]}
            return HermesTurnResult(status="RETURNED", text="{}", usage=USAGE, request_count=1, observed=observed,
                                    error_class=None)

        self.job.supervision.run_turn = run_turn  # type: ignore[method-assign]


def reply_record(**changes: Any) -> dict[str, Any]:
    return {"outcome": "reply", "status": 200, "usage": {"prompt_tokens": 1423, "completion_tokens": 611,
                                                         "total_tokens": 2034},
            "cost": 0.0012, "generation_id": "gen-synthetic-1", **changes}


def test_a_complete_reply_with_a_cost_within_the_reservation_counts(tmp_path: Path, actual: ActualRelease) -> None:
    result = Rig(tmp_path, actual, reply_record()).job.runner.run_turn(TURN)
    assert result.status == "RETURNED" and result.observed["spend_state"] == "SETTLED"
    assert (result.observed["relay_cost"], result.observed["relay_generation_id"]) == (0.0012, "gen-synthetic-1")


@pytest.mark.parametrize("cost", [0.06, None, "0.001", float("inf")])  # reservation here is USD 0.054848
def test_a_cost_above_the_reservation_or_not_a_number_keeps_the_full_liability(tmp_path: Path, actual: ActualRelease,
                                                                                cost: Any) -> None:
    rig = Rig(tmp_path, actual, reply_record(cost=cost))
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.error_class, result.request_count) == ("UNKNOWN", "RelayCostUnverified", None)
    assert rig.spend.state("att-1") == "UNKNOWN" and rig.spend.liability_usd("att-1") == Decimal("0.054848")
