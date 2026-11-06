"""The host turn runner with an ACTUAL route (CONTRACT A6, E1-COST1): only with an approved release record whose request
shape the policy matches and the ledger's own TokenPrice; a counted result only when the provider-reported cost, rounded
up to a whole nano-USD, EQUALS the ledger-price charge for the reported usage and that charge is within the held
reservation. A reply that fails only that cost check keeps its answer and request count and holds the full reservation
as UNKNOWN; everything else is withheld as UNKNOWN with the full reservation, through the real runner and SQLite ledger.
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
from spend_ledger import SpendLedger, TokenPrice

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


NO_PRICE = object()


def build(tmp_path: Path, actual: ActualRelease | None, the_route: TransportRoute, *, release: Any = None,
          policy: GuardPolicy = POLICY, ledger: Any = None, price: Any = PRICE, timeout: Any = None,
          min_output_tokens: int | None = None) -> Any:
    extra = {} if price is NO_PRICE else {"price": price}
    if timeout is not None:
        extra["timeout_seconds"] = timeout
    if min_output_tokens is not None:
        extra["min_output_tokens"] = min_output_tokens
    return build_relay_job(the_route, release=release or (actual.release if actual else RELEASE), actual=actual, **extra,
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
        build(tmp_path, None, route(actual), release=RELEASE, price=NO_PRICE)
    with pytest.raises(ValueError):
        build(tmp_path, actual, ROUTE, release=actual.release)


@pytest.mark.parametrize("price", [NO_PRICE, None, Decimal("2.00"), "2.00/7.50", True, (Decimal(2), Decimal("7.5"))])
def test_an_actual_job_without_the_ledgers_token_price_is_refused_before_any_io(tmp_path: Path, actual: ActualRelease,
                                                                                price: Any) -> None:
    with pytest.raises(ValueError, match="TokenPrice"):
        build(tmp_path, actual, route(actual), price=price)
    assert list(tmp_path.iterdir()) == []


def test_an_authored_job_needs_no_price_and_takes_none(tmp_path: Path) -> None:
    from relay_harness import POLICY as AUTHORED_POLICY
    build(tmp_path, None, ROUTE, release=RELEASE, policy=AUTHORED_POLICY, price=NO_PRICE)
    with pytest.raises(ValueError):
        build(tmp_path, None, ROUTE, release=RELEASE, policy=AUTHORED_POLICY, price=PRICE)


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
    def __init__(self, tmp_path: Path, actual: ActualRelease, finished: dict[str, Any], usage: Usage = USAGE, *,
                 cap: Decimal = Decimal("0.20"), min_output_tokens: int | None = None,
                 price: TokenPrice = PRICE) -> None:
        state = tmp_path / "state"
        for folder in ("grants", "revocations", "state"):
            (tmp_path / folder).mkdir(exist_ok=True)
        (tmp_path / "key").write_bytes(b"a" * 32)
        (state / "heartbeat.json").write_text(json.dumps({"release": actual.release.settings(), "at": time.time(),
                                                          "started_at": 0}))
        self.spend = SpendLedger(tmp_path / "spend.sqlite", cap_usd=cap, price=price)
        self.job = build(tmp_path, actual, route(actual), ledger=self.spend, min_output_tokens=min_output_tokens,
                         price=price)
        self.calls, self.turns = 0, []

        def run_turn(turn: HermesTurn) -> HermesTurnResult:
            self.calls += 1
            self.turns.append(turn)
            folder = state / turn.attempt_id
            folder.mkdir()
            (folder / "closed.json").write_text(json.dumps({"started": True}))
            (folder / "finished.json").write_text(json.dumps(finished))
            observed = {"guard_admitted": 1, "transport_attempt_id": turn.attempt_id,
                        "transport_route_id": "route-synthetic", "transport_sent": 1,
                        "transport_request_attempt_ids": [turn.attempt_id]}
            return HermesTurnResult(status="RETURNED", text="{}", usage=usage, request_count=1, observed=observed,
                                    error_class=None)

        self.job.supervision.run_turn = run_turn  # type: ignore[method-assign]


def reply_record(**changes: Any) -> dict[str, Any]:
    return {"outcome": "reply", "status": 200, "usage": {"prompt_tokens": 1423, "completion_tokens": 611,
                                                         "total_tokens": 2034},
            "cost": 0.0074285, "generation_id": "gen-synthetic-1", **changes}


CHARGE = Decimal("0.0074285")  # PRICE (2.00 / 7.50 USD per million) for 1,423 prompt and 611 completion tokens
RESERVATION = Decimal("0.054848")


@pytest.mark.parametrize("cost", [0.0074285, 0.00742849999])  # the second rounds UP to the same whole nano-USD
def test_a_reported_cost_equal_to_the_ledger_charge_counts_and_settles_at_exactly_that_charge(
        tmp_path: Path, actual: ActualRelease, cost: float) -> None:
    rig = Rig(tmp_path, actual, reply_record(cost=cost))
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.text, result.observed["spend_state"]) == ("RETURNED", "{}", "SETTLED")
    assert rig.spend.liability_usd("att-1") == CHARGE and rig.spend.committed_usd() == CHARGE
    assert (result.observed["relay_cost"], result.observed["relay_generation_id"]) == (cost, "gen-synthetic-1")
    assert rig.calls == 1


@pytest.mark.parametrize("cost", [
    0.0012, 0.02,  # the retained reproduction: below and above the token charge
    0.0074284, 0.0074285001,  # one nano-USD (or less) either side of the charge, after rounding up
    0.06,  # above the reservation
    None, "0.0074285", float("inf"), float("nan"), True, -0.0074285, [0.0074285],
])
def test_any_other_reported_cost_keeps_the_answer_and_the_full_reservation_and_never_settles(
        tmp_path: Path, actual: ActualRelease, cost: Any) -> None:
    record = reply_record(cost=cost)
    if cost is None:
        record.pop("cost")
    rig = Rig(tmp_path, actual, record)
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.text, result.request_count, result.error_class) == (
        "RETURNED", "{}", 1, "RelayCostUnverified")
    assert result.usage == USAGE
    assert (result.observed["spend_state"], result.observed["spend_charge_usd"]) == ("UNKNOWN", str(RESERVATION.normalize()))
    assert rig.spend.state("att-1") == "UNKNOWN" and rig.spend.liability_usd("att-1") == RESERVATION
    assert rig.calls == 1 and len(list((tmp_path / "grants").iterdir())) == 1  # one job, one grant: nothing resent


def test_a_matching_cost_whose_charge_exceeds_the_reservation_never_settles(tmp_path: Path, actual: ActualRelease) -> None:
    big = Usage(30_000, 4_096, 34_096, "PROVIDER_REPORTED")  # 0.06 + 0.03072 = 0.09072 > 0.054848
    rig = Rig(tmp_path, actual, reply_record(cost=0.09072, usage={"prompt_tokens": 30_000, "completion_tokens": 4_096,
                                                                   "total_tokens": 34_096}), usage=big)
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.request_count, result.error_class) == ("RETURNED", 1, "RelayCostUnverified")
    assert rig.spend.state("att-1") == "UNKNOWN" and rig.spend.liability_usd("att-1") == RESERVATION


LIST_PRICE = TokenPrice(Decimal("2"), Decimal("10"))
FIRST_CALL_USAGE = Usage(3_442, 228, 3_670, "PROVIDER_REPORTED")  # request f82a30d4


def first_call(cost: float) -> dict[str, Any]:
    return reply_record(cost=cost, usage={"prompt_tokens": 3_442, "completion_tokens": 228, "total_tokens": 3_670})


def test_the_first_paid_calls_reported_cost_settles_exactly_at_the_list_price(tmp_path: Path, actual: ActualRelease) -> None:
    rig = Rig(tmp_path, actual, first_call(0.009164), FIRST_CALL_USAGE, price=LIST_PRICE)
    result = rig.job.runner.run_turn(TURN)
    assert (result.error_class, result.observed["spend_state"]) == (None, "SETTLED")
    assert rig.spend.liability_usd("att-1") == Decimal("0.009164")


def test_a_cost_at_the_retired_price_no_longer_settles(tmp_path: Path, actual: ActualRelease) -> None:
    rig = Rig(tmp_path, actual, first_call(0.0096222), FIRST_CALL_USAGE, price=LIST_PRICE)
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.error_class) == ("RETURNED", "RelayCostUnverified")
    assert rig.spend.state("att-1") == "UNKNOWN"


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": True, "completion_tokens": 611, "total_tokens": 2034},
    {"prompt_tokens": 1423, "completion_tokens": 611},
    {"prompt_tokens": 1423, "completion_tokens": 610, "total_tokens": 2033},
    None,
])
def test_invalid_or_different_usage_stays_withheld_with_the_full_reservation(tmp_path: Path, actual: ActualRelease,
                                                              usage: Any) -> None:
    rig = Rig(tmp_path, actual, reply_record(usage=usage))
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.text, result.request_count, result.error_class) == (
        "UNKNOWN", None, None, "RelayCountMismatch")
    assert rig.spend.state("att-1") == "UNKNOWN" and rig.spend.liability_usd("att-1") == RESERVATION


@pytest.mark.parametrize("timeout", [60, 89.9, 120, True])  # the record's grant life is 90 s
def test_an_actual_job_timeout_other_than_the_records_is_refused_before_any_io(tmp_path: Path, actual: ActualRelease,
                                                                              timeout: Any) -> None:
    with pytest.raises(ValueError, match="timeout"):
        build(tmp_path, actual, route(actual), timeout=timeout)
    assert list(tmp_path.iterdir()) == []


def test_an_actual_job_with_the_records_timeout_is_built(tmp_path: Path, actual: ActualRelease) -> None:
    build(tmp_path, actual, route(actual), timeout=90)
    assert list(tmp_path.iterdir()) == []


# --- The per-call output limit (ORBIO_CREDIT_DESIGN 2b) ----------------------------------------------------------------
# A cap of 0.04 leaves 40,000,000 nano-USD: the input worst case is 12,064 x 2.00 = 24,128,000 and each output token costs
# 7,500, so (40,000,000 - 24,128,000) / 7,500 = 2,116 output tokens fit (39,998,000 nano-USD). The tests set their own
# `min_output_tokens`; no release sets one.
LOWERED = 2_116
LOWERED_RESERVATION = Decimal("0.039998")


def grant_of(tmp_path: Path) -> dict[str, Any]:
    [path] = (tmp_path / "grants").iterdir()
    return json.loads(path.read_text())


def test_the_grant_and_the_job_carry_the_lowered_limit_and_an_equal_cost_still_settles(
        tmp_path: Path, actual: ActualRelease) -> None:
    rig = Rig(tmp_path, actual, reply_record(), cap=Decimal("0.04"), min_output_tokens=1)

    result = rig.job.runner.run_turn(TURN)

    assert rig.spend.reserved_output_tokens("att-1") == LOWERED
    assert grant_of(tmp_path)["policy"]["max_output_tokens"] == LOWERED
    assert [t.max_output_tokens for t in rig.turns] == [LOWERED]
    assert result.observed["granted_max_output_tokens"] == LOWERED
    assert (result.status, result.observed["spend_state"]) == ("RETURNED", "SETTLED")  # E1-COST1, unchanged
    assert rig.spend.liability_usd("att-1") == CHARGE


@pytest.mark.parametrize("cost", [0.0012, 0.02, 0.0074284, 0.0074285001, 0.06])
def test_with_a_lowered_limit_any_other_cost_keeps_the_lowered_reservation(tmp_path: Path, actual: ActualRelease,
                                                                         cost: float) -> None:
    rig = Rig(tmp_path, actual, reply_record(cost=cost), cap=Decimal("0.04"), min_output_tokens=1)
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.error_class) == ("RETURNED", "RelayCostUnverified")
    assert rig.spend.state("att-1") == "UNKNOWN" and rig.spend.liability_usd("att-1") == LOWERED_RESERVATION


def test_without_a_smallest_limit_the_grant_carries_the_release_limit(tmp_path: Path, actual: ActualRelease) -> None:
    rig = Rig(tmp_path, actual, reply_record())
    result = rig.job.runner.run_turn(TURN)
    assert grant_of(tmp_path)["policy"] == {**POLICY.__dict__, "required_extra": dict(POLICY.required_extra)}
    assert result.observed["granted_max_output_tokens"] == 4096 and rig.turns == [TURN]


def test_a_turn_whose_limit_is_not_the_one_reserved_gets_no_grant(tmp_path: Path, actual: ActualRelease) -> None:
    from dataclasses import replace
    rig = Rig(tmp_path, actual, reply_record())
    rig.spend.reserve("att-1", scope="scope-1", max_input_tokens=12_064, max_output_tokens=4096)  # the full limit
    relay = rig.job.runner._delegate  # the RelayTurnRunner the accepted runner wraps

    result = relay.run_turn(replace(TURN, max_output_tokens=LOWERED))

    assert (result.status, result.request_count, result.error_class) == ("PROVIDER_FAILED", 0, "RelayReservationMissing")
    assert list((tmp_path / "grants").iterdir()) == [] and rig.calls == 0


def test_a_started_call_with_a_lowered_limit_is_never_resent_by_a_restarted_runner_with_another_limit_choice(
        tmp_path: Path, actual: ActualRelease) -> None:
    rig = Rig(tmp_path, actual, reply_record(), cap=Decimal("0.04"), min_output_tokens=1)
    receipts: list[str] = []

    def killed(turn: HermesTurn) -> HermesTurnResult:  # the job starts its one request, then the host runner dies
        rig.calls += 1
        folder = tmp_path / "state" / turn.attempt_id
        folder.mkdir()
        (folder / "started.json").write_text(json.dumps({"grant_id": grant_of(tmp_path)["grant_id"]}))
        receipts.append(turn.attempt_id)
        raise KeyboardInterrupt

    rig.job.supervision.run_turn = killed  # type: ignore[method-assign]
    with pytest.raises(KeyboardInterrupt):
        rig.job.runner.run_turn(TURN)
    assert rig.spend.state("att-1") == "UNKNOWN" and rig.spend.reserved_output_tokens("att-1") == LOWERED

    # A restarted host runner whose own limit choice differs (no smallest limit, so it would ask for the full release
    # limit): the same attempt reserves nothing new and gets no second grant. A raised cap (`change_caps`) exists only on
    # PostgreSQL; `test_provider_spend_ledger.py` shows the same refusal there after more headroom.
    restarted = build(tmp_path, actual, route(actual), ledger=rig.spend)
    restarted.supervision.run_turn = killed  # type: ignore[method-assign]
    result = restarted.runner.run_turn(TURN)

    assert (result.status, result.request_count, result.error_class) == ("PROVIDER_FAILED", 0, "ReservationExists")
    assert rig.spend.reserved_output_tokens("att-1") == LOWERED and rig.spend.liability_usd("att-1") == LOWERED_RESERVATION
    assert len(list((tmp_path / "grants").iterdir())) == 1 and len(list((tmp_path / "state" / "att-1").glob("started.json"))) == 1
    assert receipts == ["att-1"] and rig.calls == 1


@pytest.mark.parametrize("limit", [5_000, True])
def test_a_turn_limit_above_the_policy_or_not_a_number_gets_no_grant_even_when_the_ledger_row_matches(
        tmp_path: Path, actual: ActualRelease, limit: Any) -> None:
    from dataclasses import replace
    rig = Rig(tmp_path, actual, reply_record())
    rig.spend.reserve("att-1", scope="scope-1", max_input_tokens=1, max_output_tokens=int(limit))  # the row matches
    relay = rig.job.runner._delegate  # the RelayTurnRunner the accepted runner wraps

    result = relay.run_turn(replace(TURN, max_output_tokens=limit))

    assert (result.request_count, result.error_class) == (0, "RelayReservationMissing")
    assert list((tmp_path / "grants").iterdir()) == [] and rig.calls == 0
