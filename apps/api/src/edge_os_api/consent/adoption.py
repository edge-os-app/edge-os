"""Durable owner adoption of one reviewed meaning.

Adoption is always INACTIVE. It writes only the owned `consent_local` tables and
never touches holdings, allowances, reservations, claims, recovery cases, funding
flows or stop history. A per-review advisory transaction lock serializes
competing adopters, and a unique `(owner, review)` constraint is the durable
backstop. An identical repeated adoption is idempotent; a different meaning under
the same review identity conflicts.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from edge_os_api.consent.grouped_review import content_hash
from edge_os_api.consent.records import ConsentAdoptionRow, ConsentReviewRow
from edge_os_api.consent.types import CONSENT_STATUS, ConsentView


def _lock_keys(owner_id: uuid.UUID, review_id: uuid.UUID) -> tuple[int, int]:
    digest = hashlib.sha256(f"{owner_id}:{review_id}".encode()).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    return int4(0), int4(4)


def acquire_review_lock(session: Session, owner_id: uuid.UUID, review_id: uuid.UUID) -> None:
    """Serialize competing adopters for one owner and review on the current transaction."""
    key_a, key_b = _lock_keys(owner_id, review_id)
    session.execute(text("SELECT pg_advisory_xact_lock(:key_a, :key_b)"), {"key_a": key_a, "key_b": key_b})


def find_adoption(session: Session, owner_id: uuid.UUID, review_id: uuid.UUID) -> ConsentAdoptionRow | None:
    return session.execute(select(ConsentAdoptionRow).where(
        ConsentAdoptionRow.owner_id == owner_id,
        ConsentAdoptionRow.review_id == review_id,
    )).scalar_one_or_none()


def consent_content(
    *,
    review_row: ConsentReviewRow,
    meaning: dict[str, Any],
    route: dict[str, Any],
    policy: dict[str, Any] | None,
    evidence_status: str,
    operating_purpose: str,
    adopted_at: str,
) -> dict[str, Any]:
    """The clearly INACTIVE consent. It binds the exact reviewed content identities."""
    return {
        "status": CONSENT_STATUS,
        "authority": "INACTIVE",
        "inactive": True,
        "review_id": str(review_row.review_id),
        "review_hash": review_row.review_hash,
        "agent_id": meaning["agent_id"],
        "wallet_id": meaning["wallet_id"],
        "network_id": meaning["network_id"],
        "strategy": meaning["strategy"],
        "terms_version": review_row.terms_version,
        "terms_hash": review_row.terms_hash,
        "route": route,
        "policy": policy,
        "evidence_status": evidence_status,
        "operating_purpose": operating_purpose,
        "adopted_at": adopted_at,
    }


def consent_meaning(content: dict[str, Any]) -> dict[str, Any]:
    """The meaning bound by a consent. Arrival time is not meaning."""
    return {key: value for key, value in content.items() if key != "adopted_at"}


def consent_hash(content: dict[str, Any]) -> str:
    return content_hash(consent_meaning(content))


def save_adoption(session: Session, owner_id: uuid.UUID, review_row: ConsentReviewRow,
                  content: dict[str, Any], *, adopted_at: dt.datetime) -> ConsentAdoptionRow:
    row = ConsentAdoptionRow(
        adoption_id=uuid.uuid4(), owner_id=owner_id, review_id=review_row.review_id,
        review_hash=review_row.review_hash, consent_hash=consent_hash(content),
        status=CONSENT_STATUS, content=content, created_at=adopted_at,
    )
    session.add(row)
    session.flush()
    return row


def to_consent_view(row: ConsentAdoptionRow) -> ConsentView:
    return ConsentView(
        adoption_id=row.adoption_id, owner_id=row.owner_id, review_id=row.review_id,
        review_hash=row.review_hash, consent_hash=row.consent_hash, status=row.status,
        content=row.content, created_at=row.created_at.astimezone(dt.timezone.utc).isoformat(),
    )
