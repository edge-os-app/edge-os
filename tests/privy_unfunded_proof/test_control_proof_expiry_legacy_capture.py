"""The expiry gate accepts the real 2026-10-23 earlier capture, written before the error fields existed.

``_CAPTURE_KEYS`` gained ``error_code`` and ``error_type`` in CLOUD-CONTROL-PROOFS-2 (2053ea2). The earlier
expiry capture in the controller's store predates that change, so it has the 13-key legacy set. These tests
copy both real key sets and require the legacy set to work only for the earlier attempt, only through an
identical body, byte count and content-type hash in a current-set re-run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.privy_unfunded_proof import control_proofs

from tests.privy_unfunded_proof.test_control_proof_expiry_decision import (
    EXPIRY,
    LIVE_BODY_SHA256,
    REPO,
    _build,
    _capture,
    _recorded,
    _recite,
)

CURRENT_KEYS = frozenset({"specimen_id", "profile", "packet_id", "policy_id", "request_sha256", "status",
                          "media_type", "content_type_sha256", "byte_count", "raw_body_sha256", "error_code",
                          "error_type", "metadata_valid", "captured_at", "evidence_class"})
LEGACY_KEYS = CURRENT_KEYS - {"error_code", "error_type"}
WORKSPACE = Path(__file__).resolve().parents[5]
STORE = WORKSPACE / ".scratch/control-proofs-20261023"


def _without_error_fields(state: dict, which: str = "earlier") -> dict:
    """Make the named capture the real pre-CP2 shape, then re-cite every hash that covers it."""
    capture = state["expiry_captures"][which]
    capture.pop("error_code", None)
    capture.pop("error_type", None)
    return _recite(state)


def _entry(state: dict) -> dict:
    return _build(state)["decision_required"]["expiry_freshness"]


# ---------------------------------------------------------------- the two real key sets


def test_the_earlier_capture_in_the_legacy_key_set_still_gives_the_readable_decision() -> None:
    entry = _entry(_without_error_fields(_recorded()))
    assert entry["reason"] == "PRIVY_REFUSAL_REASON_NOT_READABLE"
    reply = entry["artifact"]["findings"]["provider_reply"]
    assert reply["earlier_capture_schema"] == "pre_error_fields"
    assert reply["earlier_error_fields"] == "derived_from_identical_body"
    assert reply["raw_body_sha256"] == LIVE_BODY_SHA256 and reply["error_code"] is None
    assert [item["attempt"] for item in reply["attempts"]] == ["earlier", "rerun"]


def test_a_current_set_earlier_capture_still_gives_the_same_decision_and_names_its_schema() -> None:
    entry = _entry(_recite(_recorded()))
    reply = entry["artifact"]["findings"]["provider_reply"]
    assert reply["earlier_capture_schema"] == "current"
    assert reply["earlier_error_fields"] == "recorded"


@pytest.mark.parametrize("changes", [
    {"raw_body_sha256": "1" * 64},
    {"byte_count": 114},
    {"content_type_sha256": "2" * 64},
])
def test_a_legacy_earlier_capture_whose_body_differs_from_the_rerun_stays_unproven(
        changes: dict[str, Any]) -> None:
    state = _without_error_fields(_recorded())
    state["expiry_captures"]["earlier"].update(changes)
    result = _build(_recite(state))
    assert result["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


def test_a_legacy_re_run_capture_stays_unproven() -> None:
    result = _build(_without_error_fields(_recorded(), "rerun"))
    assert result["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


@pytest.mark.parametrize("changes", [
    {"error_code": None},
    {"error_type": None},
    {"error_code": None, "error_type": None, "body": "{...}"},
    {"error_code": None, "error_type": None, "raw_body": "..."},
])
def test_an_earlier_capture_with_one_error_key_or_an_extra_key_stays_unproven(
        changes: dict[str, Any]) -> None:
    state = _recorded()
    del state["expiry_captures"]["earlier"]["error_code"]
    del state["expiry_captures"]["earlier"]["error_type"]
    state["expiry_captures"]["earlier"].update(changes)
    assert _build(_recite(state))["unproven"]["expiry_freshness"] == {"reason": "PRIVY_RECORD_INVALID"}


def test_the_legacy_fixture_copies_the_key_sets_of_the_real_captures() -> None:
    assert set(_capture("2026-10-23T00:00:00+00:00")) == CURRENT_KEYS
    assert set(_capture("2026-10-23T00:00:00+00:00")) - {"error_code", "error_type"} == LEGACY_KEYS


# ---------------------------------------------------------------- the controller's read-only store


def _real_captures() -> tuple[dict, dict]:
    earlier = json.loads((STORE / "privy-store-1" / f"{EXPIRY}.capture.json").read_text(encoding="utf-8"))
    rerun = json.loads((STORE / "privy-store-1.expiry-rerun" / f"{EXPIRY}.capture.json").read_text(encoding="utf-8"))
    return earlier, rerun


@pytest.mark.skipif(not (STORE / "privy-store-1.expiry-rerun" / f"{EXPIRY}.capture.json").exists(),
                    reason="the controller's read-only Privy store is not on this host")
def test_the_real_earlier_capture_uses_the_legacy_set_and_the_real_rerun_the_current_set() -> None:
    earlier, rerun = _real_captures()
    assert set(earlier) == LEGACY_KEYS and set(rerun) == CURRENT_KEYS
    assert rerun["error_code"] is None and rerun["error_type"] is None
    assert [earlier[key] for key in ("raw_body_sha256", "byte_count", "content_type_sha256")] == [
        rerun[key] for key in ("raw_body_sha256", "byte_count", "content_type_sha256")]


@pytest.mark.skipif(not ((STORE / "privy-store-1" / f"{EXPIRY}.capture.json").exists()
                         and (STORE / "privy-store-1.expiry-rerun" / f"{EXPIRY}.capture.json").exists()
                         and (STORE / "chain-store-1" / "chain_results.json").exists()),
                    reason="the controller's read-only proof stores are not on this host")
def test_the_real_stores_build_the_decision_with_the_legacy_earlier_capture() -> None:
    records, captures = control_proofs.load_privy_store(STORE / "privy-store-1")
    earlier = control_proofs.merge_expiry_rerun(records, captures, STORE / "privy-store-1")
    result = control_proofs.build_control_proofs(
        authored=json.loads((REPO / "docs/qualification/inapp-trade/release.authored.json")
                            .read_text(encoding="utf-8")),
        privy_records=records, privy_capture_sha256=captures,
        chain_records=control_proofs.load_chain_store(STORE / "chain-store-1"),
        privy_earlier_records=earlier,
        privy_expiry_captures=control_proofs.load_expiry_captures(STORE / "privy-store-1"))
    entry = result["decision_required"]["expiry_freshness"]
    assert entry["reason"] == "PRIVY_REFUSAL_REASON_NOT_READABLE"
    assert entry["artifact"]["findings"]["provider_reply"]["earlier_capture_schema"] == "pre_error_fields"
