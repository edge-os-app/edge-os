"""Per-owner write rate windows in PostgreSQL, shared by every API process.

One row per owner and fixed one-minute window. An atomic upsert counts the request; a count above the configured
limit refuses it with 429 and a `Retry-After` header. No in-process state, so several API processes share the limit.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, Integer, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from edge_os_api.core.errors import AppError, finding
from edge_os_api.usage.quota import UsageBase

WINDOW = dt.timedelta(minutes=1)


class RequestWindowRow(UsageBase):
    __tablename__ = "request_windows"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requests: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (PrimaryKeyConstraint("owner_id", "window_start", name="request_windows_pkey"),)


class RateLimited(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(429, "RATE_LIMIT", "UNAVAILABLE", "rate_limited", [finding(
            "rate_limited", "/", f"Too many changes in a short time. Wait {retry_after} seconds, then check the saved "
                                 "state before you repeat a change.")])
        self.retry_after = retry_after


def count_write(session: Session, owner_id: uuid.UUID, limit: int, now: dt.datetime | None = None) -> int:
    """Count one write for the owner in the current window and commit the count. Raises `RateLimited` over the limit.

    The count commits on its own so a refused or failed request still counts; nothing else is in this transaction.
    """
    moment = now or dt.datetime.now(dt.timezone.utc)
    start = moment.replace(second=0, microsecond=0)
    count = session.execute(pg_insert(RequestWindowRow).values(owner_id=owner_id, window_start=start, requests=1)
                            .on_conflict_do_update(index_elements=["owner_id", "window_start"],
                                                   set_={"requests": RequestWindowRow.requests + 1})
                            .returning(RequestWindowRow.requests)).scalar_one()
    session.commit()
    if count > limit:
        raise RateLimited(max(1, int((start + WINDOW - moment).total_seconds()) + 1))
    return count
