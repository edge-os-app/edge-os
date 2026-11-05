"""OWNER-TRIGGER-L3 repair 2: which saved attempts release the one action. Pure table, fail closed."""
from __future__ import annotations

import pytest

from edge_os_api.execution.owner_trigger import (ALREADY_USED, PERMISSION_CHANGED, SavedAttempt, attempt_released,
                                                 next_attempt, prior_refusal)

BINDING = "a" * 64


def attempt(**changes):
    fields = {"number": 1, "binding_sha256": BINDING, "job_states": ("UNAVAILABLE",), "has_intent": False,
              "queue_state": None, "submission_attempts": 0}
    fields.update(changes)
    return SavedAttempt(**fields)


def test_a_finished_job_with_no_intent_releases():
    assert attempt_released(attempt())


@pytest.mark.parametrize("queue_state", ["ADMISSION_DENIED", "DENIED_UNSENT", "REVALIDATION_DENIED"])
def test_a_finished_unsent_intent_releases(queue_state):
    assert attempt_released(attempt(job_states=("COMPLETED",), has_intent=True, queue_state=queue_state))


@pytest.mark.parametrize("queue_state", [
    "QUEUED", "CLAIMED", "BREACHED", "RECONCILE_MISMATCH", "SUBMISSION_NOT_OWNED", "SUBMITTED_CONFIRMED",
    "SUBMITTED_REVERTED", "SUBMITTED_UNKNOWN", "A_FUTURE_STATE", None])
def test_any_other_queue_state_keeps_the_action_used(queue_state):
    assert not attempt_released(attempt(job_states=("COMPLETED",), has_intent=True, queue_state=queue_state))


@pytest.mark.parametrize("job_states", [(), ("QUEUED",), ("DECIDED",), ("ENQUEUED",), ("SUBMITTED",),
                                        ("COMPLETED", "QUEUED"), ("A_FUTURE_STATE",)])
def test_a_missing_or_unfinished_job_keeps_the_action_used(job_states):
    assert not attempt_released(attempt(job_states=job_states))


@pytest.mark.parametrize("queue_state", ["ADMISSION_DENIED", "DENIED_UNSENT", "REVALIDATION_DENIED"])
def test_any_submission_attempt_row_keeps_the_action_used(queue_state):
    assert not attempt_released(attempt(job_states=("COMPLETED",), has_intent=True, queue_state=queue_state,
                                        submission_attempts=1))


def test_no_earlier_attempt_has_no_refusal():
    assert prior_refusal((), binding_sha256=BINDING, foreign_intent=False) is None


def test_released_attempts_have_no_refusal_even_under_a_new_permission():
    assert prior_refusal((attempt(),), binding_sha256="b" * 64, foreign_intent=False) is None


def test_a_held_attempt_under_the_same_permission_is_already_used():
    held = attempt(job_states=("SUBMITTED",))
    assert prior_refusal((attempt(), held), binding_sha256=BINDING, foreign_intent=False) == ALREADY_USED


def test_a_held_attempt_under_another_permission_is_a_changed_permission():
    held = attempt(job_states=("SUBMITTED",))
    assert prior_refusal((held,), binding_sha256="b" * 64, foreign_intent=False) == PERMISSION_CHANGED


def test_an_intent_outside_every_attempt_is_already_used():
    assert prior_refusal((attempt(),), binding_sha256=BINDING, foreign_intent=True) == ALREADY_USED


def test_the_next_attempt_follows_the_highest_saved_number():
    assert next_attempt(()) == 1
    assert next_attempt((attempt(number=1), attempt(number=3))) == 4
