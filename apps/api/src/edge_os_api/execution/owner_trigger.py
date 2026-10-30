"""The saved owner-trigger basis for the one in-app action. Pure; no I/O.

The worker calls this only inside `_decide`, from saved rows. A route, request body, request key or provenance
field never sets it. Every other release, consent, recurring job and rule job returns `RULE` and keeps the
market observation path unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from edge_os_api.execution.operating_release import OWNER_TRIGGER_RELEASE_ID, binding_decision_qualified

RULE = "RULE"
OWNER_TRIGGER = "OWNER_TRIGGER"
ALREADY_USED = "OWNER_TRIGGER_ALREADY_USED"


@dataclass(frozen=True)
class OwnerTriggerBasis:
    basis: str
    refusal: str | None = None


def owner_trigger_basis(*, release: Mapping[str, Any], deployment_id: str | None,
                        consent_adoption_id: str, job_consent_adoption_id: str,
                        consent_hash: str, job_consent_hash: str,
                        market_proof: str | None, market_profile: Mapping[str, Any] | None,
                        prior_intent: bool) -> OwnerTriggerBasis:
    """The saved basis for this job. `OWNER_TRIGGER` only for the one approved release and adopted permission."""
    if deployment_id is not None:
        return OwnerTriggerBasis(RULE)
    if release.get("release_id") != OWNER_TRIGGER_RELEASE_ID:
        return OwnerTriggerBasis(RULE)
    limits = release.get("limits")
    if type(limits) is not dict or limits.get("actions") != 1:
        return OwnerTriggerBasis(RULE)
    if not binding_decision_qualified(market_proof, release):
        return OwnerTriggerBasis(RULE)
    if market_profile is not None:
        return OwnerTriggerBasis(RULE)
    if consent_adoption_id != job_consent_adoption_id or consent_hash != job_consent_hash:
        return OwnerTriggerBasis(RULE)
    if prior_intent:
        return OwnerTriggerBasis(OWNER_TRIGGER, ALREADY_USED)
    return OwnerTriggerBasis(OWNER_TRIGGER)
