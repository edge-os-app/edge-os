"""The saved owner-trigger basis for the one in-app action. Pure; no I/O.

The worker calls this only inside `_decide`, from saved rows. A route, request body, request key or provenance
field never sets it. Every other release, consent, recurring job and rule job returns `RULE` and keeps the
market observation path unchanged.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from edge_os_api.execution.operating_release import OWNER_TRIGGER_RELEASE_ID, binding_decision_qualified

RULE = "RULE"
OWNER_TRIGGER = "OWNER_TRIGGER"
ALREADY_USED = "OWNER_TRIGGER_ALREADY_USED"
PERMISSION_CHANGED = "OWNER_TRIGGER_PERMISSION_CHANGED"
FINISHED_JOB_STATES = frozenset({"UNAVAILABLE", "COMPLETED"})
UNSENT_QUEUE_STATES = frozenset({"ADMISSION_DENIED", "DENIED_UNSENT", "REVALIDATION_DENIED"})


@dataclass(frozen=True)
class OwnerTriggerBasis:
    basis: str
    refusal: str | None = None
    attempt: int | None = None


@dataclass(frozen=True)
class SavedAttempt:
    """The saved facts of one owner-triggered decision."""

    number: int
    binding_sha256: str
    job_states: tuple[str, ...]
    has_intent: bool
    queue_state: str | None
    submission_attempts: int


def attempt_released(attempt: SavedAttempt) -> bool:
    """Only positive proof that nothing can be signed or sent releases the action; anything else keeps it used.

    A submission attempt row is saved before any signature, so its absence proves nothing was signed or sent.
    """
    if not attempt.job_states or not FINISHED_JOB_STATES.issuperset(attempt.job_states):
        return False
    if attempt.submission_attempts:
        return False
    return not attempt.has_intent or attempt.queue_state in UNSENT_QUEUE_STATES


def prior_refusal(attempts: Iterable[SavedAttempt], *, binding_sha256: str, foreign_intent: bool) -> str | None:
    """The refusal a new owner trigger gets from the saved attempts, or None when every one is released."""
    held = [attempt for attempt in attempts if not attempt_released(attempt)]
    if any(attempt.binding_sha256 != binding_sha256 for attempt in held):
        return PERMISSION_CHANGED
    return ALREADY_USED if held or foreign_intent else None


def next_attempt(attempts: Iterable[SavedAttempt]) -> int:
    return max((attempt.number for attempt in attempts), default=0) + 1


def owner_trigger_basis(*, release: Mapping[str, Any], deployment_id: str | None,
                        consent_adoption_id: str, job_consent_adoption_id: str,
                        consent_hash: str, job_consent_hash: str,
                        market_proof: str | None, market_profile: Mapping[str, Any] | None,
                        refusal: str | None, attempt: int) -> OwnerTriggerBasis:
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
    return OwnerTriggerBasis(OWNER_TRIGGER, refusal, attempt)
