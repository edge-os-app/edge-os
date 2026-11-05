"""OWNER-TRIGGER-L3: the saved owner-trigger basis is exact and cannot come from a request.

Pure checks only: no database, network, container or provider. The mounted journey test covers the worker path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from edge_os_api.execution import operating_release
from edge_os_api.execution.owner_trigger import ALREADY_USED, OWNER_TRIGGER, RULE, owner_trigger_basis

ARTIFACT = Path(__file__).parents[4] / "docs" / "qualification" / "inapp-trade" / "owner-trigger-market.decision.json"
RELEASE = "actual-inapp-wmon-moe-20261022/1"
PROOF = "780668a764ee1eaec9bf0e1643e441efe3df4caaaaa54ddbc2ca88696d853567"
CONSENT = "11111111-1111-4111-8111-111111111111"


def release(**changes):
    value = {"release_id": RELEASE, "kind": "ACTUAL", "limits": {"actions": 1}}
    value.update(changes)
    return value


def basis(**changes):
    fields = {"release": release(), "deployment_id": None, "consent_adoption_id": CONSENT,
              "job_consent_adoption_id": CONSENT, "consent_hash": "sha256:" + "a" * 64,
              "job_consent_hash": "sha256:" + "a" * 64, "market_proof": PROOF, "market_profile": None,
              "refusal": None, "attempt": 1}
    fields.update(changes)
    return owner_trigger_basis(**fields)


def test_the_exact_release_permission_and_proof_form_the_owner_trigger_basis():
    result = basis()
    assert (result.basis, result.refusal) == (OWNER_TRIGGER, None)


@pytest.mark.parametrize("change", [
    {"deployment_id": "22222222-2222-4222-8222-222222222222"},
    {"release": release(release_id="another-release/1")},
    {"release": release(limits={"actions": 2})},
    {"release": release(limits={})},
    {"market_proof": "9" * 64},
    {"market_proof": None},
    {"market_profile": {"source_id": "forward/1"}},
    {"consent_adoption_id": "33333333-3333-4333-8333-333333333333"},
    {"consent_hash": "sha256:" + "b" * 64},
])
def test_any_other_saved_fact_keeps_the_rule_path(change):
    assert basis(**change).basis == RULE


def test_a_saved_refusal_is_refused_not_rerun():
    result = basis(refusal=ALREADY_USED)
    assert (result.basis, result.refusal) == (OWNER_TRIGGER, ALREADY_USED)


def test_only_the_code_owned_triple_for_the_exact_release_qualifies_a_binding_decision():
    assert operating_release.binding_decision_qualified(PROOF, release())
    assert not operating_release.binding_decision_qualified(PROOF, release(release_id="another-release/1"))
    assert not operating_release.binding_decision_qualified("9" * 64, release())
    assert not operating_release.binding_decision_qualified(None, release())


def test_the_committed_artifact_hash_is_the_registered_triple():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    import hashlib

    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    assert artifact["release_id"] == RELEASE
    assert artifact["slot"] == "market_proof_sha256"
    assert artifact["reason_code"] == operating_release.OWNER_TRIGGER_DECISION_REASON
    assert (("market_proof_sha256", artifact["reason_code"], digest)
            in operating_release.APPROVED_BINDING_DECISIONS)
    assert digest == PROOF
