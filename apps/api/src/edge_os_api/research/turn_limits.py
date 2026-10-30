"""Per-owner and global interpretation turn limits.

The limits are counts over the append-only attempt table. One PostgreSQL session advisory lock serializes the count and
the attempt start, so two processes cannot both admit a turn that would cross the limit. The lock is held only for the
count and the attempt insert; the provider call runs after the lock is released.

Limits: one unsettled attempt per owner, two unsettled attempts across all owners, and ten new attempts per owner in a
rolling sixty minutes. A refused turn writes no attempt row and no spend reservation.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_UNSETTLED_PER_OWNER = 1
MAX_UNSETTLED_TOTAL = 2
MAX_STARTS_PER_WINDOW = 10
WINDOW_SECONDS = 60 * 60
LIMIT_LOCK_KEY = 0x4845524D45534C31  # "HERMESL1", one fixed key for every process

LIMIT_DETAIL = {
    "attempt_in_flight": "An earlier attempt for this request has not finished.",
    "turn_in_flight": "An earlier interpretation turn for this account is still running. Wait for it to finish.",
    "turn_capacity_full": "The demo interpretation service is busy. Try again shortly.",
    "turn_limit_reached": "This account reached the interpretation limit for the last hour. Try again later.",
}


class TurnLimitReached(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = LIMIT_DETAIL[reason]


class TurnLimits:
    """Counts and admits a turn under one fixed advisory lock. A caller uses `admission` around the attempt insert."""

    def __init__(self, session_factory: Callable[[], Session], *,
                 now: Callable[[], dt.datetime] | None = None) -> None:
        self._factory = session_factory
        self._now = now or (lambda: dt.datetime.now(dt.timezone.utc))

    @contextmanager
    def admission(self, owner_id: str, intake_record_id: str) -> Iterator[None]:
        with self._factory() as session:
            key = {"key": LIMIT_LOCK_KEY}
            session.execute(text("select pg_advisory_lock(:key)"), key)
            try:
                owner = uuid.UUID(owner_id)
                reason = self._refusal(session, owner, uuid.UUID(intake_record_id)) or self.check_window(session, owner)
                if reason is not None:
                    raise TurnLimitReached(reason)
                yield
            finally:
                try:
                    session.execute(text("select pg_advisory_unlock(:key)"), key)
                except Exception:  # noqa: BLE001 - a connection that cannot unlock must not return to the pool
                    session.invalidate()

    @staticmethod
    def _refusal(session: Session, owner: uuid.UUID, intake: uuid.UUID) -> str | None:
        unsettled = ("select count(*) from interpretation_attempts a "
                     "left join interpretation_settlements s "
                     "on s.attempt_id = a.attempt_id and s.owner_id = a.owner_id "
                     "where s.attempt_id is null and a.owner_id = :o")
        count = session.execute(text(unsettled), {"o": owner}).scalar_one()
        if count >= MAX_UNSETTLED_PER_OWNER:
            same = session.execute(text(unsettled + " and a.intake_record_id = :i"),
                                   {"o": owner, "i": intake}).scalar_one()
            return "attempt_in_flight" if count == 1 and same == 1 else "turn_in_flight"
        total_unsettled = session.execute(text(
            "select count(*) from interpretation_attempts a "
            "left join interpretation_settlements s "
            "on s.attempt_id = a.attempt_id and s.owner_id = a.owner_id "
            "where s.attempt_id is null")).scalar_one()
        if total_unsettled >= MAX_UNSETTLED_TOTAL:
            return "turn_capacity_full"
        return None

    def check_window(self, session: Session, owner: uuid.UUID) -> str | None:
        since = self._now() - dt.timedelta(seconds=WINDOW_SECONDS)
        recent = session.execute(text("select count(*) from interpretation_attempts "
                                      "where owner_id = :o and started_at > :since"),
                                 {"o": owner, "since": since}).scalar_one()
        return "turn_limit_reached" if recent >= MAX_STARTS_PER_WINDOW else None
