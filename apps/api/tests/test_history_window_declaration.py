"""HISTORY-WINDOW-L2: the declaration must fit the MOE source's real window and readable partition.

The live failure was the fixed one-hour partition split in the web builder: on a twenty-minute window its holdout
started after it ended, so the real validator refused the declaration. The second failure was the schedule: it was
fitted to the whole window, but comparison reads only the TRAINING (or DESCRIPTIVE) partition. These tests replay the
old body, prove the crash with the real comparison engine, and run the accepted descriptive declaration end to end on
a MOE-shaped dataset. No provider, credential or network is used.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research.comparison_runs import compare_history
from research_flows import history_body, investigation_request

MOE = "actual-moe-wmon-fwd2h/1"
MOE_WINDOW = {"start": "2026-10-22T21:40:00Z", "end": "2026-10-22T23:40:00Z"}
BUCKET = dt.timedelta(minutes=5)
HORIZON = dt.timedelta(minutes=5)
FLOOR = 2
RELEASE = "actual-moe-history2h-nansen-20261022/1"
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


def _derive(window: dict[str, str], lookback: int, direction: str) -> dict[str, Any] | None:
    """The web builder's derivation: schedule inside the readable partition, floors required."""
    start, end = _moment(window["start"]), _moment(window["end"])
    buckets = int((end - start) / BUCKET)
    if direction == "DESCRIPTIVE":
        partitions = [{"partition_id": "described", "role": "DESCRIPTIVE", "start": _text(start), "end": _text(end)}]
    else:
        validate = max(1, buckets // 4)
        holdout = max(1, buckets // 4)
        train = buckets - validate - holdout
        if train < 1:
            return None
        train_end, validate_end = start + train * BUCKET, start + (train + validate) * BUCKET
        partitions = [
            {"partition_id": "train", "role": "TRAINING", "start": _text(start), "end": _text(train_end)},
            {"partition_id": "validate", "role": "VALIDATION", "start": _text(train_end), "end": _text(validate_end)},
            {"partition_id": "holdout", "role": "HOLDOUT", "start": _text(validate_end), "end": _text(end)},
        ]
    readable_start, readable_end = _moment(partitions[0]["start"]), _moment(partitions[0]["end"])
    last_grid = int((readable_end - HORIZON - dt.timedelta(seconds=60) - readable_start) / BUCKET)
    last_decision = readable_start + last_grid * BUCKET
    required = 1 if direction == "DESCRIPTIVE" else FLOOR
    max_lookback = last_grid - required
    if max_lookback < 1 or lookback > max_lookback:
        return None
    schedule_start = readable_start + (lookback + 1) * BUCKET
    schedule_end = last_decision + BUCKET
    decisions = last_grid - lookback
    if decisions < required:
        return None
    return {"partitions": partitions, "decisions": decisions,
            "schedule": {"version": "p09.decision-clock/1", "start": _text(schedule_start), "end": _text(schedule_end),
                         "interval_seconds": 300}}


def _body(client, headers, *, direction: str, lookback: int, partitions: list[dict[str, Any]] | None = None,
          schedule: dict[str, Any] | None = None):
    bundle = investigation_request(client, headers)
    source = _source(client, headers)
    if partitions is None:
        derived = _derive(source["window"], lookback, direction)
        assert derived is not None, "the page must refuse this declaration"
        partitions, schedule = derived["partitions"], derived["schedule"]
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


def _moe_dataset() -> dict[str, Any]:
    """A QUALIFIED MOE-shaped two-hour window: 24 buckets and trades on every half-minute."""
    start = _moment(MOE_WINDOW["start"])
    closes = ["1", "2", "1.5", "2.5"] * 6
    buckets = []
    for index, close in enumerate(closes):
        bucket_end = start + (index + 1) * BUCKET
        buckets.append({"bucket_start": _text(bucket_end - BUCKET), "bucket_end": _text(bucket_end),
                        "status": "COMPLETE_OCCUPIED", "reasons": [], "available_at": _text(bucket_end),
                        "close": close, "quote_volume": "10"})
    trades = []
    for index in range(240):
        event_time = start + index * dt.timedelta(seconds=30)
        trades.append({"event_id": f"moe-trade-{index}", "event_time": _text(event_time), "price": "2",
                       "quote_amount": "1", "base_amount": "0.5", "pool_side": "BASE_TO_QUOTE",
                       "block_number": 100 + index, "transaction_index": 0, "log_index": index,
                       "available_at": _text(event_time), "qualified": True})
    quote = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
    return {"unavailable_states": [], "verdict": {"overall": "QUALIFIED"}, "buckets": buckets, "trades": trades,
            "strategy_market": {"network": "MONAD", "quote_unit": f"QUOTE:{quote}",
                                "research_binding": {"quote_asset": quote}}}


def _declaration(body: dict[str, Any]) -> dict[str, Any]:
    return {"configuration": body["configuration"], "rule_map": body["configuration"]["rule_map"]}


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


def test_predictive_moe_supports_lookback_eight_with_two_decisions():
    derived = _derive(MOE_WINDOW, 8, "OUTPERFORM")
    assert derived is not None
    assert derived["decisions"] == 2
    assert derived["schedule"]["start"] == "2026-10-22T22:25:00Z"
    assert derived["schedule"]["end"] == "2026-10-22T22:35:00Z"
    assert derived["partitions"][0] == {"partition_id": "train", "role": "TRAINING",
                                        "start": "2026-10-22T21:40:00Z", "end": "2026-10-22T22:40:00Z"}
    assert _derive(MOE_WINDOW, 9, "OUTPERFORM") is None


def test_the_old_predictive_schedule_crashes_the_comparison_engine(research, owner_a):
    """The old accepted body: a 07:50 schedule on a TRAINING partition that ends at 07:45."""
    _bundle, body = _body(research, owner_a, direction="DESCRIPTIVE", lookback=1)
    configuration = body["configuration"]
    configuration["direction"] = "OUTPERFORM"
    configuration["partitions"] = [
        {"partition_id": "train", "role": "TRAINING", "start": "2026-10-22T07:35:00Z", "end": "2026-10-22T07:45:00Z"},
        {"partition_id": "validate", "role": "VALIDATION", "start": "2026-10-22T07:45:00Z",
         "end": "2026-10-22T07:50:00Z"},
        {"partition_id": "holdout", "role": "HOLDOUT", "start": "2026-10-22T07:50:00Z", "end": "2026-10-22T07:55:00Z"},
    ]
    configuration["evaluation_plan"][0]["partition_ids"] = ["train"]
    configuration["schedule"] = {"version": "p09.decision-clock/1", "start": "2026-10-22T07:50:00Z",
                                 "end": "2026-10-22T07:55:00Z", "interval_seconds": 300}
    with pytest.raises(ValueError, match="positive interval and ordered UTC bounds"):
        compare_history(_declaration(body), _moe_dataset())


def test_the_accepted_descriptive_moe_declaration_compares_end_to_end(research, owner_a):
    bundle, body = _body(research, owner_a, direction="DESCRIPTIVE", lookback=1)
    saved = _save(research, owner_a, bundle, body)
    assert saved.status_code == 201, saved.text
    content = saved.json()["declaration"]["content"]
    assert content["configuration"]["partitions"] == [
        {"partition_id": "described", "role": "DESCRIPTIVE", "start": "2026-10-22T21:40:00Z",
         "end": "2026-10-22T23:40:00Z"}]
    assert content["configuration"]["schedule"] == {
        "version": "p09.decision-clock/1", "start": "2026-10-22T21:50:00Z", "end": "2026-10-22T23:35:00Z",
        "interval_seconds": 300}
    report = compare_history(content, _moe_dataset())
    variant = report["variants"][0]
    assert report["outcome"] == "DESCRIBED", report
    assert variant["triggered_observed"] + variant["control_observed"] >= 1


def test_a_forced_lookback_two_descriptive_schedule_keeps_no_usable_decision(research, owner_a):
    """Evidence for the cap: at lookback 2 the only grid decision loses its one-minute response window."""
    _bundle, body = _body(research, owner_a, direction="DESCRIPTIVE", lookback=1)
    body["configuration"]["schedule"] = {"version": "p09.decision-clock/1", "start": "2026-10-22T07:50:00Z",
                                         "end": "2026-10-22T07:55:00Z", "interval_seconds": 300}
    report = compare_history(_declaration(body), _moe_dataset())
    variant = report["variants"][0]
    assert report["outcome"] == "INSUFFICIENT_DATA"
    assert variant["triggered_observed"] + variant["control_observed"] == 0


def test_the_synthetic_schedule_stays_inside_training_and_refuses_the_old_crash_class():
    window = {"start": "2026-09-25T10:00:00Z", "end": "2026-09-25T12:00:00Z"}
    derived = _derive(window, 2, "OUTPERFORM")
    assert derived is not None
    assert derived["schedule"]["end"] == "2026-09-25T10:55:00Z"
    assert derived["schedule"]["end"] <= derived["partitions"][0]["end"]
    assert _derive(window, 9, "OUTPERFORM") is None
