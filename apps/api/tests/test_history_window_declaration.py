"""HISTORY-WINDOW-L2: the declaration must fit the MOE source's real twenty-minute window.

The live failure was the fixed one-hour partition split in the web builder: on a twenty-minute window its holdout
started after it ended, so the real validator refused the declaration. These tests replay that old body and the
window-derived body against the real endpoint and validator. No provider, credential or network is used.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from research_flows import history_body, investigation_request

MOE = "actual-moe-wmon-fwd20m/1"
BUCKET = dt.timedelta(minutes=5)
HORIZON = dt.timedelta(minutes=5)
RELEASE = "actual-moe-history-nansen-20261022/1"
UNKNOWNS = [f"Recorded responses come from the named providers under the approved release {RELEASE}. "
            "Costs are not modelled; the window is short."]


@pytest.fixture(scope="module")
def research(env, migrated):
    settings = load_settings({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"})
    with TestClient(create_app(settings)) as client:
        yield client


def _moment(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def _text(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _source(client, headers) -> dict[str, Any]:
    sources = client.get("/v1/research/history-sources", headers=headers).json()["sources"]
    return next(item for item in sources if item["source_id"] == MOE)


def _plan(window: dict[str, str], lookback: int, direction: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The same derivation the web builder uses: proportional split, schedule from lookback and horizon."""
    start, end = _moment(window["start"]), _moment(window["end"])
    buckets = int((end - start) / BUCKET)
    if direction == "DESCRIPTIVE":
        partitions = [{"partition_id": "described", "role": "DESCRIPTIVE", "start": _text(start), "end": _text(end)}]
    else:
        validate = max(1, buckets // 4)
        holdout = max(1, buckets // 4)
        train = buckets - validate - holdout
        train_end, validate_end = start + train * BUCKET, start + (train + validate) * BUCKET
        partitions = [
            {"partition_id": "train", "role": "TRAINING", "start": _text(start), "end": _text(train_end)},
            {"partition_id": "validate", "role": "VALIDATION", "start": _text(train_end), "end": _text(validate_end)},
            {"partition_id": "holdout", "role": "HOLDOUT", "start": _text(validate_end), "end": _text(end)},
        ]
    schedule = {"version": "p09.decision-clock/1", "start": _text(start + lookback * BUCKET),
                "end": _text(min(end, end - HORIZON + BUCKET)), "interval_seconds": 300}
    return partitions, schedule


def _body(client, headers, *, direction: str, lookback: int, partitions: list[dict[str, Any]] | None = None,
          schedule: dict[str, Any] | None = None):
    bundle = investigation_request(client, headers)
    source = _source(client, headers)
    if partitions is None:
        partitions, schedule = _plan(source["window"], lookback, direction)
    unit = f"QUOTE:{source['market']['quote_asset']}"
    rules = [({"op": "gt", "args": [{"op": "price_return", "lookback_buckets": lookback},
                                    {"op": "constant", "value": "0.015", "unit": "DIMENSIONLESS"}]},
              {"op": "gt", "args": [{"op": "quote_volume"},
                                    {"op": "constant", "value": "1", "unit": unit}]})]
    body = history_body(client, headers, bundle, source_id=MOE, direction=direction, rules=rules,
                        bounds=dict(source["release"]["history"]["limits"]), partitions=partitions,
                        schedule=schedule, unknowns=UNKNOWNS)
    return bundle, body


def _save(client, headers, bundle, body):
    return client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                       headers=headers, json=body)


def test_the_old_fixed_hour_split_is_refused_for_the_moe_window(research, owner_a):
    old_partitions = [
        {"partition_id": "train", "role": "TRAINING", "start": "2026-10-22T07:35:00Z", "end": "2026-10-22T08:35:00Z"},
        {"partition_id": "validate", "role": "VALIDATION", "start": "2026-10-22T08:35:00Z",
         "end": "2026-10-22T09:05:00Z"},
        {"partition_id": "holdout", "role": "HOLDOUT", "start": "2026-10-22T09:05:00Z", "end": "2026-10-22T07:55:00Z"},
    ]
    old_schedule = {"version": "p09.decision-clock/1", "start": "2026-10-22T07:50:00Z",
                    "end": "2026-10-22T07:45:00Z", "interval_seconds": 300}
    bundle, body = _body(research, owner_a, direction="OUTPERFORM", lookback=1,
                         partitions=old_partitions, schedule=old_schedule)
    refused = _save(research, owner_a, bundle, body)
    assert refused.status_code == 422, refused.text
    assert "Partition boundaries must be ordered UTC timestamps." in refused.text


@pytest.mark.parametrize("lookback", [1, 3])
def test_the_window_derived_split_is_accepted_for_lookback_one_and_three(research, owner_a, lookback):
    bundle, body = _body(research, owner_a, direction="OUTPERFORM", lookback=lookback)
    saved = _save(research, owner_a, bundle, body)
    assert saved.status_code == 201, saved.text
    content = saved.json()["declaration"]["content"]
    assert content["configuration"]["partitions"] == body["configuration"]["partitions"]
    assert content["configuration"]["schedule"] == body["configuration"]["schedule"]
    assert content["edge_spec"]["unknowns"] == UNKNOWNS


def test_a_descriptive_declaration_on_the_moe_window_is_accepted(research, owner_a):
    bundle, body = _body(research, owner_a, direction="DESCRIPTIVE", lookback=1)
    saved = _save(research, owner_a, bundle, body)
    assert saved.status_code == 201, saved.text
    content = saved.json()["declaration"]["content"]
    assert content["configuration"]["partitions"] == [
        {"partition_id": "described", "role": "DESCRIPTIVE", "start": "2026-10-22T07:35:00Z",
         "end": "2026-10-22T07:55:00Z"}]
    assert content["configuration"]["direction"] == "DESCRIPTIVE"
