"""Preparation for the two-hour MOE release: a synthetic 24-bucket anchored release, never registered.

Pure: no database, socket or provider. The recorder fixture is SYNTHETIC; these tests show the release path admits a
7200 s / 24-bucket graph and refuses a changed byte or window. The real recorder run is bound in Phase 2.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.core.research import operating_release, released_runtime_bootstrap
from edge_os_api.core.research.operating_release import (
    BINDING_FACT,
    HistoryRelease,
    OperatingRelease,
    ReleaseRefused,
    check_release,
    release_sha256,
)
from edge_os_api.research import history_payload_binding
from tests.test_history_payload_binding_v2 import two_hour_artifacts

SYNTHETIC_ID = "synthetic-two-hour-release/1"


def synthetic_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HistoryRelease:
    """A HistoryRelease over the recorder's synthetic 7200 s / 24-bucket graph. Never approved."""
    anchor, handoff_bytes, _ = two_hour_artifacts(tmp_path, monkeypatch)
    handoff = json.loads(handoff_bytes)
    profile = {
        "network": {"chain_id": handoff["network"]["chain_id"]},
        "venue": {"pool_address": handoff["market"]["pool"]},
        "pool_tokens": [
            {"address": handoff["market"]["token0"], "role": "QUOTE"},
            {"address": handoff["market"]["token1"], "role": "BASE"},
        ],
        "orientation": "QUOTE_PER_BASE",
        "dataset": {"window": handoff["window"]},
    }
    return HistoryRelease(
        source_id=handoff["source_id"],
        title="Synthetic two-hour history (never registered)",
        envio_endpoint="https://monad.hypersync.xyz",
        envio_credential_slot="HYPERSYNC_API_KEY",
        quicknode_host="virulent-necessary-patina.monad-mainnet.quiknode.pro",
        quicknode_credential_slot="QUICKNODE_API_URL",
        profile=profile,
        scan=handoff["scan"],
        corroboration_sample_size=8,
        provider_facts={BINDING_FACT: anchor},
        limits={"provider_requests": 13, "compute_seconds": 600, "max_pages": 4, "max_rows": 2000,
                "max_bytes": 4194304, "deadline_seconds": 600},
        client_bounds={"deadline_seconds": 120, "connect_timeout_seconds": 15,
                       "max_response_bytes": 2097152, "max_request_bytes": 65536, "max_blocks_per_page": 10000},
    )


def changed_anchor(history: HistoryRelease) -> HistoryRelease:
    value = copy.deepcopy(dict(history.provider_facts[BINDING_FACT]))
    value["handoff_json"] = value["handoff_json"].replace("{", "{ ", 1)  # one added byte, still strict JSON
    value["handoff_sha256"] = hashlib.sha256(value["handoff_json"].encode("utf-8")).hexdigest()
    return dataclasses.replace(history, provider_facts={**history.provider_facts, BINDING_FACT: value})


def test_the_registry_keeps_exactly_one_approved_release() -> None:
    assert len(operating_release.APPROVED_RELEASES) == 1
    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == set(operating_release.APPROVED_RELEASES)
    for release_id, release in released_runtime_bootstrap.RELEASE_DEFINITIONS.items():
        assert release.release_id == release_id
        assert operating_release.APPROVED_RELEASES[release_id] == release_sha256(release)


def test_a_synthetic_two_hour_anchor_is_admitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = synthetic_history(tmp_path, monkeypatch)
    history_payload_binding.check_definition("ACTUAL", history)  # no refusal
    handoff = json.loads(history.provider_facts[BINDING_FACT]["handoff_json"])
    assert len(handoff["buckets"]) == 24
    assert [bucket["status"] for bucket in handoff["buckets"]] == ["DELIVERED"] * 24
    assert (handoff["window"]["start_utc"], handoff["window"]["end_utc"]) == (
        history.profile["dataset"]["window"]["start_utc"], history.profile["dataset"]["window"]["end_utc"])
    assert handoff["scan"] == history.scan


def test_a_synthetic_two_hour_release_reaches_approval_once(tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    history = synthetic_history(tmp_path, monkeypatch)
    release = OperatingRelease(release_id=SYNTHETIC_ID, kind="ACTUAL", history=history)
    digest = release_sha256(release)
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {SYNTHETIC_ID: digest})
    assert check_release(release, network_transport=True) == digest


def test_the_synthetic_two_hour_release_is_never_registered(tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    history = synthetic_history(tmp_path, monkeypatch)
    assert history.source_id not in {
        part.history.source_id for part in released_runtime_bootstrap.RELEASE_DEFINITIONS.values()
        if part.history is not None}
    assert SYNTHETIC_ID not in released_runtime_bootstrap.RELEASE_DEFINITIONS
    assert SYNTHETIC_ID not in operating_release.APPROVED_RELEASES


def test_a_changed_run_byte_refuses_the_synthetic_two_hour_anchor(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    history = synthetic_history(tmp_path, monkeypatch)
    with pytest.raises(ReleaseRefused) as refused:
        history_payload_binding.check_definition("ACTUAL", changed_anchor(history))
    assert refused.value.code == "forward_history_binding_invalid"


def test_a_wrong_window_refuses_the_synthetic_two_hour_anchor(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    history = synthetic_history(tmp_path, monkeypatch)
    profile = copy.deepcopy(dict(history.profile))
    window = profile["dataset"]["window"]
    profile["dataset"]["window"] = {"start_utc": window["start_utc"], "end_utc": window["end_utc"]}
    profile["dataset"]["window"]["start_utc"] = _shift(window["start_utc"], 300)
    profile["dataset"]["window"]["end_utc"] = _shift(window["end_utc"], 300)
    with pytest.raises(ReleaseRefused) as refused:
        history_payload_binding.check_definition("ACTUAL", dataclasses.replace(history, profile=profile))
    assert refused.value.code == "forward_history_binding_invalid"


def _shift(value: str, seconds: int) -> str:
    import datetime as dt

    moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00")) + dt.timedelta(seconds=seconds)
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
