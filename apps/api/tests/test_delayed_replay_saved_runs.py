"""Delayed replay wiring (DELAYED-REPLAY-WIRING-L2-20261017).

The default profile keeps its original request fingerprint, saved identity and output. The delayed
profile is an explicit choice, persists its fixed policy, and reopens from the saved record. This
file mixes pure request-identity checks with PostgreSQL checks; the PostgreSQL cases need the
session database.
"""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.errors import AppError
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.replay import saved_runs
from edge_os_api.core.request_schemas import SpotReplayBody
from flows import compiled_thesis, publish
from research_flows import adoption_body, history_replay_body, reported_dataset
from test_spot_replay_api import _body, _saved_revision

DEFAULT = "p12.spot-replay/1"
DELAYED = "edge-os.delayed-history-replay/1"
POLICY = {
    "schema_version": DELAYED,
    "decision_delay_seconds": 300,
    "fill_rule": "NEXT_BUCKET_DELAYED_CLOSE",
    "fill_label": "Hypothetical stale historical close",
}
OWNER = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _request(**changes: Any) -> SpotReplayBody:
    values: dict[str, Any] = {
        "idempotency_key": "identity-key",
        "strategy_id": "strategy-1",
        "strategy_revision_id": "11111111-1111-4111-8111-111111111111",
        "dataset_fixture_id": "p13.wc01/1",
        "run_configuration_id": "identity-config",
        "window_start": dt.datetime(2026, 10, 1, 12, 5, tzinfo=dt.timezone.utc),
        "window_end": dt.datetime(2026, 10, 1, 12, 35, tzinfo=dt.timezone.utc),
        "initial_cash_quote": "1000",
        "essential_fields": {"entry": {"state": "UNBOUND"}, "exit": {"state": "UNBOUND"}},
    }
    values.update(changes)
    return SpotReplayBody(**values)


def _normalized(body: SpotReplayBody, timing_profile: str) -> dict[str, Any]:
    return saved_runs._request_fields(body, timing_profile)


def _expected_default_request() -> dict[str, Any]:
    """The exact request record the pre-ticket code hashed. Derived by hand, not by the code under test."""
    return {
        "idempotency_key": "identity-key",
        "strategy_id": "strategy-1",
        "strategy_revision_id": "11111111-1111-4111-8111-111111111111",
        "dataset_fixture_id": "p13.wc01/1",
        "run_configuration_id": "identity-config",
        "window_start": "2026-10-01T12:05:00Z",
        "window_end": "2026-10-01T12:35:00Z",
        "initial_cash_quote": "1000",
        "initial_base_amount": "0",
        "initial_basis_quote": "0",
        "essential_fields": {
            "entry": {"state": "UNBOUND", "essential_dependencies": None},
            "exit": {"state": "UNBOUND", "essential_dependencies": None},
        },
    }


# --------------------------------------------------------------------------------------- request identity


def test_omitted_and_explicit_default_profiles_resolve_to_the_default() -> None:
    assert saved_runs.resolve_timing_profile(None) == DEFAULT
    assert saved_runs.resolve_timing_profile(DEFAULT) == DEFAULT
    assert saved_runs.resolve_timing_profile(DELAYED) == DELAYED


@pytest.mark.parametrize("value", ["p99.spot-replay/1", 7, [], {}, True])
def test_unknown_or_non_string_profiles_are_refused_at_the_request_path(value: object) -> None:
    with pytest.raises(AppError) as error:
        saved_runs.resolve_timing_profile(value)

    assert (error.value.status, error.value.code) == (422, "UNSUPPORTED_TIMING_PROFILE")
    assert error.value.findings[0]["path"] == "/timing_profile"


def test_an_omitted_profile_keeps_the_original_request_fingerprint() -> None:
    body = _request()
    fields = _normalized(body, saved_runs.resolve_timing_profile(None))
    expected = record_contract.sha256_hex({
        "owner_id": str(OWNER), "method": "POST", "path": "/v1/spot-replays",
        "request": {key: value for key, value in _expected_default_request().items()
                    if key != "idempotency_key"},
    })

    assert "timing_profile" not in fields
    assert saved_runs.request_fingerprint(OWNER, fields) == expected


def test_an_explicit_default_profile_hashes_like_the_omitted_profile() -> None:
    omitted = _normalized(_request(), DEFAULT)
    explicit = _normalized(_request(timing_profile=DEFAULT), DEFAULT)
    delayed = _normalized(_request(timing_profile=DELAYED), DELAYED)

    assert explicit == omitted
    assert "timing_profile" not in explicit
    assert saved_runs.request_fingerprint(OWNER, explicit) == saved_runs.request_fingerprint(OWNER, omitted)
    assert delayed["timing_profile"] == DELAYED
    assert saved_runs.request_fingerprint(OWNER, delayed) != saved_runs.request_fingerprint(OWNER, omitted)


def test_only_the_delayed_profile_adds_saved_timing_identity_and_policy() -> None:
    assert saved_runs.timing_snapshot(DEFAULT) == {}
    assert saved_runs.timing_snapshot(DELAYED) == {"timing_profile": DELAYED, "timing_policy": POLICY}


# --------------------------------------------------------------------------------------- persistence


def test_a_delayed_replay_saves_its_profile_and_reopens_after_a_restart(client, settings, owner_a) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"delayed-{uuid.uuid4()}")
    body["timing_profile"] = DELAYED

    created = client.post("/v1/spot-replays", headers=owner_a, json=body)

    assert created.status_code == 201, created.text
    saved = created.json()
    content = saved["content"]
    assert content["inputs"]["timing_profile"] == DELAYED
    assert content["inputs"]["timing_policy"] == POLICY
    assert content["result"]["status"] == "COMPLETE", content["result"].get("reason")
    assert content["result"]["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert all(sample["timing_profile"] == DELAYED for sample in content["result"]["samples"])
    fills = [event for event in content["result"]["events"]
             if event.get("status") in {"BUY_FILLED", "SELL_FILLED"}]
    assert fills and all(event["fill_label"] == POLICY["fill_label"] for event in fills)
    assert all(trade["fill_label"] == POLICY["fill_label"] for trade in content["result"]["trades"])

    with TestClient(create_app(settings)) as restarted:
        reopened = restarted.get(f"/v1/spot-replays/{saved['replay_id']}", headers=owner_a)

    assert reopened.status_code == 200, reopened.text
    assert reopened.json() == saved


def test_the_default_saved_record_adds_no_timing_keys_and_keeps_its_result(client, owner_a) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"default-{uuid.uuid4()}")
    explicit = copy.deepcopy(body)
    explicit["idempotency_key"] = f"default-explicit-{uuid.uuid4()}"
    explicit["timing_profile"] = DEFAULT

    first = client.post("/v1/spot-replays", headers=owner_a, json=body)
    second = client.post("/v1/spot-replays", headers=owner_a, json=explicit)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert "timing_profile" not in first.json()["content"]["inputs"]
    assert "timing_policy" not in first.json()["content"]["inputs"]
    assert second.json()["content"]["inputs"] == first.json()["content"]["inputs"]
    assert second.json()["content"]["result"] == first.json()["content"]["result"]


def test_the_delayed_and_default_profiles_never_share_a_repeatability_id(client, owner_a) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    default = client.post("/v1/spot-replays", headers=owner_a,
                          json=_body(strategy, revision, key=f"profile-default-{uuid.uuid4()}"))
    delayed_body = _body(strategy, revision, key=f"profile-delayed-{uuid.uuid4()}")
    delayed_body["timing_profile"] = DELAYED
    delayed = client.post("/v1/spot-replays", headers=owner_a, json=delayed_body)

    assert default.status_code == delayed.status_code == 201
    assert default.json()["content"]["result"]["repeatability_id"]
    assert (default.json()["content"]["result"]["repeatability_id"]
            != delayed.json()["content"]["result"]["repeatability_id"])


def test_the_same_key_with_a_different_profile_is_a_conflict(client, owner_a, pg) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"same-key-{uuid.uuid4()}")
    before = int(pg.psql("select count(*) from spot_replay_runs"))
    first = client.post("/v1/spot-replays", headers=owner_a, json=body)
    changed = copy.deepcopy(body)
    changed["timing_profile"] = DELAYED

    conflict = client.post("/v1/spot-replays", headers=owner_a, json=changed)

    assert first.status_code == 201, first.text
    assert (conflict.status_code, conflict.json()["code"]) == (409, "idempotency_key_reused")
    assert int(pg.psql("select count(*) from spot_replay_runs")) == before + 1


def test_the_same_configuration_id_with_a_different_profile_is_a_conflict(client, owner_a) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"same-config-{uuid.uuid4()}")
    first = client.post("/v1/spot-replays", headers=owner_a, json=body)
    changed = copy.deepcopy(body)
    changed["idempotency_key"] = f"same-config-other-key-{uuid.uuid4()}"
    changed["timing_profile"] = DELAYED

    conflict = client.post("/v1/spot-replays", headers=owner_a, json=changed)

    assert first.status_code == 201, first.text
    assert (conflict.status_code, conflict.json()["code"]) == (409, "run_configuration_id_reused")


def test_an_unknown_profile_saves_nothing(client, owner_a, pg) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"unknown-profile-{uuid.uuid4()}")
    body["timing_profile"] = "p99.spot-replay/1"
    before = int(pg.psql("select count(*) from spot_replay_runs"))

    refused = client.post("/v1/spot-replays", headers=owner_a, json=body)

    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "UNSUPPORTED_TIMING_PROFILE"
    assert refused.json()["findings"][0]["path"] == "/timing_profile"
    assert int(pg.psql("select count(*) from spot_replay_runs")) == before


# --------------------------------------------------------------------------------------- protected data


@pytest.fixture(scope="module")
def recorded(env, migrated):
    settings = load_settings({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded",
                              "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "200",
                              "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "9000"})
    with TestClient(create_app(settings)) as client:
        yield client


def test_a_delayed_window_that_reaches_protected_data_is_refused(recorded, owner_a, pg) -> None:
    dataset_id = reported_dataset(recorded, owner_a, source_id="recorded-syn-qualified/1", direction="OUTPERFORM")
    bundle = compiled_thesis(recorded, owner_a)
    first, _ = publish(recorded, owner_a, bundle)
    parent = first.json()["revision_id"]
    adopted = recorded.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions",
                            headers=owner_a,
                            json=adoption_body(bundle, dataset_id, parent=parent))
    assert adopted.status_code == 201, adopted.text
    second, _ = publish(recorded, owner_a, adopted.json()["bundle"], parent=parent)
    assert second.status_code == 201, second.text
    body = history_replay_body(bundle["head"]["strategy_id"], second.json()["revision_id"], dataset_id,
                               end="2026-09-25T11:05:00Z")
    body["timing_profile"] = DELAYED
    before = int(pg.psql("select count(*) from spot_replay_runs"))

    refused = recorded.post("/v1/spot-replays", headers=owner_a, json=body)

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "protected_partition_not_authorized"
    assert int(pg.psql("select count(*) from spot_replay_runs")) == before
