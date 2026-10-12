"""The qualification proposal package: pinned identities, the case manifest and the words that must stay true.

No request is made. These tests keep the proposal honest: the pinned identities match the code, the manifest has the five
groups, every document labels the work as proposed and not run, and nothing in the package holds a credential.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from qualification_identities import compute

PACKAGE = Path(__file__).resolve().parents[3] / "docs" / "qualification" / "hermes-provider"
MANIFEST = json.loads((PACKAGE / "CASE_MANIFEST.json").read_text())
PROPOSAL = (PACKAGE / "QUALIFICATION_PROPOSAL.md").read_text()


def test_the_committed_identities_equal_the_ones_computed_from_the_code() -> None:
    committed = json.loads((PACKAGE / "IDENTITIES.json").read_text())

    assert compute() == committed  # regenerate with qualification_identities.py after any pinned file changes


def test_the_proposal_states_the_pinned_identities_and_limits() -> None:
    identities = json.loads((PACKAGE / "IDENTITIES.json").read_text())
    for value in (identities["base_commit"], identities["prompt_version"], identities["system_prompt_sha256"],
                  identities["response_shape_sha256"], identities["hermes_commit"], identities["hermes_uv_lock_sha256"],
                  identities["case_manifest_sha256"], identities["p02_manifest_sha256"],
                  identities["reservations"]["per_request_usd"]["first"], identities["reservations"]["per_request_usd"]["follow_up"],
                  identities["reservations"]["with_four_retry_slots_usd"], identities["proposed_limits"]["cumulative_cap_usd"]):
        assert value in PROPOSAL, value


def test_the_manifest_has_the_five_groups_in_the_planned_counts() -> None:
    groups = [case["group"] for case in MANIFEST["cases"]]

    assert {g: groups.count(g) for g in dict.fromkeys(groups)} == {
        "CONCRETE_THESIS": 2, "LOOSE_INTUITION": 2, "BOUNDED_NO_THESIS": 2, "UNSUPPORTED_EXTENSION": 2, "FOLLOW_UP": 3}
    assert len({case["id"] for case in MANIFEST["cases"]}) == 11
    assert len({case.get("intake", {}).get("original_request") or case["reply"] for case in MANIFEST["cases"]}) == 11


def test_the_manifest_literals_are_the_expected_numbers() -> None:
    literals = MANIFEST["literals"]

    assert literals["gt_return15_1pct"]["args"][1]["value"] == "0.01" and literals["gt_return15_1pct"]["args"][0]["lookback_buckets"] == 3
    assert literals["gt_return15_2pct"]["args"][1]["value"] == "0.02"
    assert literals["lt_return5_zero"]["op"] == "lt" and literals["lt_return5_zero"]["args"][0]["lookback_buckets"] == 1


@pytest.mark.parametrize("name", ["QUALIFICATION_PROPOSAL.md", "HOSTING_ASSESSMENT.md", "LIVE_RELEASE_CHECKLIST.md", "README.md"])
def test_each_document_labels_the_work_as_not_run_and_without_authority(name: str) -> None:
    text = (PACKAGE / name).read_text()

    assert "NOT_RUN" in text
    assert re.search(r"no (live )?(request|inference)", text, re.IGNORECASE)
    assert "not authority" in text.lower() or "no authority" in text.lower()


def test_no_file_in_the_package_holds_a_credential_shape() -> None:
    pattern = re.compile(r"sk-(or-)?[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY")
    found = [path.name for path in PACKAGE.iterdir() if path.is_file() and pattern.search(path.read_text())]

    assert found == []
