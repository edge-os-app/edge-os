"""Atomic contention: two separate DB sessions must not double-reserve the same
funds or inventory, and an unknown outcome must block a second economic action."""

from __future__ import annotations

import threading

from admission._builders import (
    approval_a,
    context_a,
    intent_entry,
    intent_exit,
    new_action_id,
)


def _run_concurrently(count: int, target) -> list:
    barrier = threading.Barrier(count)
    results: list = [None] * count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = target(index)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_two_sessions_cannot_double_reserve_capital(admission_service, fresh_owner) -> None:
    approval = approval_a(quote_approved_raw="500")
    context = context_a()

    def admit(index: int):
        intent = intent_entry(quantity_raw="10", quote_input_raw="300",
                              position_id=f"position-a-{index + 1}",
                              action_id=new_action_id())
        return admission_service.admit_and_reserve(fresh_owner, intent, approval, context).status

    statuses = _run_concurrently(2, admit)
    assert sorted(statuses) == ["ADMITTED", "DENIED"]


def test_two_sessions_cannot_double_reserve_inventory(admission_service, fresh_owner) -> None:
    approval = approval_a()
    context = context_a(position_inventory="10")

    def admit_exit(index: int):
        intent = intent_exit(quantity_raw="6", action_id=new_action_id())
        return admission_service.admit_and_reserve(fresh_owner, intent, approval, context).status

    statuses = _run_concurrently(2, admit_exit)
    assert sorted(statuses) == ["ADMITTED", "DENIED"]


def test_contender_denial_is_persisted(admission_service, admission_engine, fresh_owner) -> None:
    from sqlalchemy import text

    approval = approval_a(quote_approved_raw="500")
    context = context_a()

    def admit(index: int):
        intent = intent_entry(quantity_raw="10", quote_input_raw="300",
                              position_id=f"position-a-{index + 1}",
                              action_id=new_action_id())
        return admission_service.admit_and_reserve(fresh_owner, intent, approval, context).status

    statuses = _run_concurrently(2, admit)
    assert sorted(statuses) == ["ADMITTED", "DENIED"]
    with admission_engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT status FROM admission_decisions WHERE owner_id = :owner ORDER BY status"
        ), {"owner": str(fresh_owner)}).scalars().all()
        reservations = connection.execute(text(
            "SELECT count(*) FROM admission_reservations WHERE owner_id = :owner AND state = 'RESERVED'"
        ), {"owner": str(fresh_owner)}).scalar_one()
    assert sorted(rows) == ["ADMITTED", "DENIED"]
    assert reservations == 4  # only one winner reserved its four atoms