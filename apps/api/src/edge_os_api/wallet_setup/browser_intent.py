"""Atomic permission for one owner-linked browser wallet creation.

The browser may call the provider SDK only after this module commits the setup's dispatch intent. The
row lock makes the first claim the only claim: a duplicate begin, a second tab, a lost permission reply
or a proved pre-dispatch cancellation never receives a second permission. It reuses the service's
existing `_mark_dispatch_intent`, so the five setup states and the append-only events are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import not_found
from edge_os_api.wallet_setup import service
from edge_os_api.wallet_setup.persistence import load_setup, to_record
from edge_os_api.wallet_setup.types import CancellationIntent, SetupRecord, SetupState


@dataclass(frozen=True)
class BrowserBegin:
    """`create_permitted` is true for exactly one begin per setup; every later begin is false."""

    record: SetupRecord
    create_permitted: bool


def begin_browser_creation(session: Any, principal: Principal, *, agent_id: str) -> BrowserBegin:
    """Commit the dispatch intent before the browser may create. Only the first claim is permitted."""
    service._validate_agent_id(agent_id)  # noqa: SLF001 - same package, one shared validation rule
    row = load_setup(session, principal.user_id, agent_id, lock=True)
    if row is None:
        raise not_found("wallet setup")
    permitted = (row.state == SetupState.REQUESTED.value and not row.creation_dispatched
                 and row.cancellation_intent == CancellationIntent.NONE.value)
    if not permitted:
        record = to_record(row)
        session.rollback()
        return BrowserBegin(record=record, create_permitted=False)
    service._mark_dispatch_intent(session, row)  # noqa: SLF001
    session.commit()
    return BrowserBegin(record=to_record(row), create_permitted=True)
