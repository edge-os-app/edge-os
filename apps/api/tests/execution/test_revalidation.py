"""Revalidation immediately before submission denies changed or expired inputs."""

from __future__ import annotations

from sqlalchemy import text

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import frozen_entry_exit, gt_constant, scoped_approval
from execution._support import enqueue_entry, transport


def _payload_hash(engine, owner, action_id: str) -> str:
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT payload_hash FROM execution_intents WHERE owner_id = :owner AND action_id = :action"),
            {"owner": str(owner), "action": action_id}).scalar_one()


def _run(execution_service, owner, revision, approval, context, action_id):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, transport=transport("ACCEPT", action_id=action_id))


def test_expired_or_revoked_approval_denies_and_preserves_payload(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    before = _payload_hash(execution_engine, fresh_owner, result.intent.action_id)

    revoked = scoped_approval(revision_id=revision.revision_id, state="REVOKED")
    tick = _run(execution_service, fresh_owner, revision, revoked, context, result.intent.action_id)

    assert tick.status == "REVALIDATION_DENIED"
    assert "APPROVAL_INACTIVE_OR_EXPIRED" in (tick.reason or "")
    assert _payload_hash(execution_engine, fresh_owner, result.intent.action_id) == before
    with execution_engine.connect() as connection:
        attempts = connection.execute(text(
            "SELECT count(*) FROM execution_submission_attempts WHERE owner_id = :owner"),
            {"owner": str(fresh_owner)}).scalar_one()
    assert attempts == 0


def test_changed_policy_binding_denies(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    changed = scoped_approval(revision_id=revision.revision_id, policy_binding="p23-policy-other")

    tick = _run(execution_service, fresh_owner, revision, changed, context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "POLICY_BINDING_CHANGED"


def test_changed_revision_denies(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    other = frozen_entry_exit(entry=gt_constant("101"))

    tick = _run(execution_service, fresh_owner, other, scoped_approval(revision_id=other.revision_id),
                context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "REVISION_CHANGED"


def test_scoped_stop_denies_a_queued_entry(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    stopped = scoped_approval(revision_id=revision.revision_id, stops=("STOP_NEW_ENTRIES",))

    tick = _run(execution_service, fresh_owner, revision, stopped, context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert "STOPPED_NEW_ENTRIES" in (tick.reason or "")
    assert tick.queue_entry is not None and tick.queue_entry.state == "REVALIDATION_DENIED"
