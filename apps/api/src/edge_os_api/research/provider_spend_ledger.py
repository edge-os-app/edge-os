"""Provider spend on PostgreSQL: the accepted `SpendLedger` rules, shared by every API process, with owner and global caps.

It has the methods, results and exceptions of `scripts/hermes_interpretation/spend_ledger.py`, so the accepted
`GuardedTurnRunner` uses it unchanged. A request may start only after `reserve` has recorded its worst-case cost against
both the owner's cap and the global cap. Known usage replaces the reservation with the exact charge. Everything else keeps
the full reservation as liability. Only `release_unsent` frees a reservation, and only while it is still RESERVED. Late
evidence is recorded by `reconcile`; it never frees liability and never charges twice.

Every write is one transaction that first locks the single settings row, so all writes are serialized across threads
and processes, as `BEGIN IMMEDIATE` serializes the SQLite file. Caps and prices are frozen in that row at first use. A
different configured cap or price later refuses new reservations (`LedgerConfigMismatch`) until `change_caps` records an
explicit decision; existing reservations always settle at the frozen prices.

A reservation names a saved interpretation attempt: its owner and saved request are copied from that row inside the
reserving transaction. That row is append-only (an immutability trigger rejects updates and deletes), so the copy cannot
drift; there is no database foreign key between the two tables. Money is integer nano-USD and prices are exact decimals, as in the accepted ledger.

What this proves: shared LOCAL accounting. It cannot prove that a provider's own billing stops at the cap. LOCAL only:
the accepted ledger types live under `scripts/`, which this module adds to the import path; the application factory
does not import it.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

SUPPORT = Path(__file__).resolve().parents[5] / "scripts" / "hermes_interpretation"
if str(SUPPORT) not in sys.path:
    sys.path.append(str(SUPPORT))

# The accepted ledger's types, and its own usage checks, so both ledgers apply exactly the same rules.
from spend_ledger import (  # noqa: E402
    NANO, CapExceeded, Event, LedgerConfigMismatch, NotReserved, Reservation, ReservationExists, ScopeBlocked,
    Settlement, TokenPrice, Unresolved, _usd, _valid_tokens, _valid_usage,
)

__all__ = ["AttemptNotSaved", "PostgresSpendLedger", "SpendLimits"]

SCHEMA = "usage_local"
OPERATOR_SOURCE = "operator:"
LIABILITY = ("coalesce(sum(CASE WHEN state = 'SETTLED' THEN charged_nano_usd "
             "WHEN state IN ('RESERVED', 'UNKNOWN') THEN reserved_nano_usd ELSE 0 END), 0)")


class AttemptNotSaved(LookupError):
    """A reservation must name a saved interpretation attempt. Nothing is reserved for anything else."""


@dataclass(frozen=True)
class SpendLimits:
    global_cap_usd: Decimal  # every owner together
    owner_cap_usd: Decimal  # each owner on their own
    price: TokenPrice


@dataclass(frozen=True)
class _Frozen:
    global_cap: int
    owner_cap: int
    price: TokenPrice


def _nano(amount: Decimal, label: str) -> int:
    value = amount * NANO
    if not value.is_finite() or value != value.to_integral_value() or value < 0:
        raise ValueError(f"{label} must be a non-negative amount in whole nano-USD")
    return int(value)


def _attempt(attempt_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(attempt_id)
    except (ValueError, TypeError, AttributeError):
        return None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class PostgresSpendLedger:
    def __init__(self, session_factory: Callable[[], Session], limits: SpendLimits) -> None:
        """No I/O: nothing is read or written until the first call."""
        self._factory = session_factory
        self._configured = _Frozen(_nano(limits.global_cap_usd, "the global cap"),
                                   _nano(limits.owner_cap_usd, "the owner cap"), limits.price)

    @contextmanager
    def _write(self) -> Iterator[Session]:
        """One transaction. It commits only when the block ends normally; any exception rolls everything back."""
        with self._factory() as session:
            yield session
            session.commit()

    def _locked(self, session: Session, *, check: bool) -> _Frozen:
        """Freeze the settings at first use, then lock them: every write waits here, in every process.

        The cap check relies on PostgreSQL's default READ COMMITTED isolation: each statement after this lock sees every
        write committed before the lock was granted. Under REPEATABLE READ the snapshot could predate the wait.
        """
        configured, now = self._configured, _now()
        session.execute(text(
            f"INSERT INTO {SCHEMA}.provider_spend_settings VALUES (1, :g, :o, :p, :c, 'configuration-at-first-use', :now, :now) "
            "ON CONFLICT (settings_id) DO NOTHING"),
            {"g": configured.global_cap, "o": configured.owner_cap, "now": now,
             "p": str(configured.price.prompt_usd_per_million), "c": str(configured.price.completion_usd_per_million)})
        row = session.execute(text(
            f"SELECT global_cap_nano_usd, owner_cap_nano_usd, prompt_usd_per_million, completion_usd_per_million, cap_source "
            f"FROM {SCHEMA}.provider_spend_settings WHERE settings_id = 1 FOR UPDATE")).one()
        frozen = _Frozen(row[0], row[1], TokenPrice(Decimal(row[2]), Decimal(row[3])))
        if check:
            if frozen.price != configured.price:
                raise LedgerConfigMismatch("the spend ledger was frozen with different token prices")
            if not row[4].startswith(OPERATOR_SOURCE) and (frozen.global_cap, frozen.owner_cap) != (
                    configured.global_cap, configured.owner_cap):
                raise LedgerConfigMismatch("the configured caps differ from the frozen caps; record a cap change first")
        return frozen

    @staticmethod
    def _event(session: Session, attempt: uuid.UUID | None, kind: str, detail: str = "", nano: int | None = None) -> None:
        session.execute(text(f"INSERT INTO {SCHEMA}.provider_spend_events (attempt_id, kind, detail, nano_usd, created_at) "
                             "VALUES (:a, :k, :d, :n, :at)"), {"a": attempt, "k": kind, "d": detail, "n": nano, "at": _now()})

    @staticmethod
    def _liability(session: Session, owner: Any = None) -> int:
        # shortcut: sums every reservation (indexed by owner) under the lock; keep running totals if reservations grow large
        where = " WHERE owner_id = :o" if owner is not None else ""
        return session.execute(text(f"SELECT {LIABILITY} FROM {SCHEMA}.provider_spend_reservations{where}"),
                               {"o": owner}).scalar_one()

    # --- Reading ---------------------------------------------------------------------------------------------------

    def _read(self, statement: str, **params: Any) -> list[Any]:
        with self._factory() as session:
            return list(session.execute(text(statement), params).all())

    def committed_usd(self, owner_id: str | None = None) -> Decimal:
        """All liability, or one owner's."""
        with self._factory() as session:
            return _usd(self._liability(session, uuid.UUID(owner_id) if owner_id is not None else None))

    def liability_usd(self, attempt_id: str) -> Decimal | None:
        """What this attempt holds now: its charge when settled, its reservation while unresolved, otherwise zero."""
        attempt = _attempt(attempt_id)
        rows = [] if attempt is None else self._read(
            f"SELECT {LIABILITY} FROM {SCHEMA}.provider_spend_reservations WHERE attempt_id = :a GROUP BY attempt_id", a=attempt)
        return _usd(rows[0][0]) if rows else None

    def state(self, attempt_id: str) -> str | None:
        attempt = _attempt(attempt_id)
        rows = [] if attempt is None else self._read(
            f"SELECT state FROM {SCHEMA}.provider_spend_reservations WHERE attempt_id = :a", a=attempt)
        return rows[0][0] if rows else None

    def unresolved(self) -> list[Unresolved]:
        rows = self._read(f"SELECT attempt_id, scope, state, reserved_nano_usd FROM {SCHEMA}.provider_spend_reservations "
                          "WHERE state IN ('RESERVED', 'UNKNOWN') ORDER BY created_at, attempt_id")
        return [Unresolved(str(attempt), scope, state, _usd(nano)) for attempt, scope, state, nano in rows]

    def events(self, attempt_id: str) -> list[Event]:
        attempt = _attempt(attempt_id)
        rows = [] if attempt is None else self._read(
            f"SELECT kind, detail, created_at FROM {SCHEMA}.provider_spend_events WHERE attempt_id = :a ORDER BY seq", a=attempt)
        return [Event(kind, detail, at.isoformat()) for kind, detail, at in rows]

    # --- Reserving and settling --------------------------------------------------------------------------------------

    def reserve(self, attempt_id: str, *, scope: str, max_input_tokens: int, max_output_tokens: int) -> Reservation:
        """Record the worst-case cost BEFORE a request may start. Raises, and writes nothing, when it may not."""
        if not _valid_tokens(max_input_tokens, max_output_tokens):
            raise ValueError("token bounds must be whole numbers within range")
        attempt = _attempt(attempt_id)
        if attempt is None:
            raise AttemptNotSaved("a reservation needs the id of a saved interpretation attempt")
        with self._write() as session:
            frozen = self._locked(session, check=True)
            amount = frozen.price.nano_usd(max_input_tokens, max_output_tokens)
            if session.execute(text(f"SELECT 1 FROM {SCHEMA}.provider_spend_reservations WHERE attempt_id = :a"),
                               {"a": attempt}).first():
                raise ReservationExists(attempt_id)
            saved = session.execute(text("SELECT owner_id, intake_record_id FROM interpretation_attempts WHERE attempt_id = :a"),
                                    {"a": attempt}).first()
            if saved is None:
                raise AttemptNotSaved("a reservation needs the id of a saved interpretation attempt")
            if session.execute(text(f"SELECT 1 FROM {SCHEMA}.provider_spend_reservations "
                                    "WHERE scope = :s AND state IN ('RESERVED', 'UNKNOWN') LIMIT 1"), {"s": scope}).first():
                raise ScopeBlocked(scope)
            owner, total = self._liability(session, saved[0]), self._liability(session)
            if owner + amount > frozen.owner_cap:
                raise CapExceeded(_usd(owner), _usd(amount), _usd(frozen.owner_cap))
            if total + amount > frozen.global_cap:
                raise CapExceeded(_usd(total), _usd(amount), _usd(frozen.global_cap))
            now = _now()
            session.execute(text(
                f"INSERT INTO {SCHEMA}.provider_spend_reservations VALUES "
                "(:a, :o, :i, :s, 'RESERVED', :n, NULL, :mi, :mo, :now, :now)"),
                {"a": attempt, "o": saved[0], "i": saved[1], "s": scope, "n": amount, "mi": max_input_tokens,
                 "mo": max_output_tokens, "now": now})
            self._event(session, attempt, "RESERVED", scope, amount)
        return Reservation(attempt_id, scope, _usd(amount))

    def settle(self, attempt_id: str, *, input_tokens: object, output_tokens: object) -> Settlement:
        """Replace the reservation with the exact charge. Unusable usage keeps the whole reservation as liability."""
        with self._write() as session:
            frozen = self._locked(session, check=False)
            attempt, row = self._row(session, attempt_id)
            if row["state"] == "SETTLED":
                return self._compare_evidence(session, frozen, attempt, row, input_tokens, output_tokens)
            if row["state"] != "RESERVED":
                raise NotReserved(f"{attempt_id} is {row['state']}")
            if not _valid_usage(input_tokens, output_tokens):
                self._to_unknown(session, attempt, "INVALID_USAGE")
                return Settlement("UNKNOWN", _usd(row["reserved"]))
            return self._charge(session, frozen, attempt, row, input_tokens, output_tokens, "")  # type: ignore[arg-type]

    def mark_unknown(self, attempt_id: str, *, reason: str) -> None:
        """The outcome is not known. The full reservation stays as liability and its scope stays blocked."""
        with self._write() as session:
            self._locked(session, check=False)
            attempt, row = self._row(session, attempt_id)
            if row["state"] == "RESERVED":
                self._to_unknown(session, attempt, reason)

    def release_unsent(self, attempt_id: str, *, reason: str) -> None:
        """Free a reservation whose request was provably never admitted. Nothing else frees liability."""
        with self._write() as session:
            self._locked(session, check=False)
            attempt, row = self._row(session, attempt_id)
            if row["state"] != "RESERVED":
                raise NotReserved(f"{attempt_id} is {row['state']}")
            session.execute(text(f"UPDATE {SCHEMA}.provider_spend_reservations SET state = 'RELEASED', updated_at = :now "
                                 "WHERE attempt_id = :a"), {"a": attempt, "now": _now()})
            self._event(session, attempt, "RELEASED", reason)

    def reconcile(self, attempt_id: str, *, input_tokens: int, output_tokens: int, source: str) -> Settlement:
        """Late evidence about an attempt. It records what arrived and never frees or doubles liability."""
        if not _valid_usage(input_tokens, output_tokens):
            raise ValueError("late evidence needs whole token counts, with at least one input token")
        with self._write() as session:
            frozen = self._locked(session, check=False)
            attempt, row = self._row(session, attempt_id)
            if row["state"] == "SETTLED":
                return self._compare_evidence(session, frozen, attempt, row, input_tokens, output_tokens)
            kind = "RECONCILED" if row["state"] in ("RESERVED", "UNKNOWN") else "CONFLICTING_EVIDENCE"
            return self._charge(session, frozen, attempt, row, input_tokens, output_tokens, source, kind)

    def change_caps(self, *, global_cap_usd: Decimal, owner_cap_usd: Decimal, reason: str) -> None:
        """The only way to change a frozen cap: an explicit, recorded decision. Prices never change."""
        if not reason.strip():
            raise ValueError("a cap change needs a reason")
        global_cap, owner_cap = _nano(global_cap_usd, "the global cap"), _nano(owner_cap_usd, "the owner cap")
        with self._write() as session:
            frozen = self._locked(session, check=False)
            session.execute(text(f"UPDATE {SCHEMA}.provider_spend_settings SET global_cap_nano_usd = :g, "
                                 "owner_cap_nano_usd = :o, cap_source = :src, updated_at = :now WHERE settings_id = 1"),
                            {"g": global_cap, "o": owner_cap, "src": f"{OPERATOR_SOURCE}{reason}", "now": _now()})
            self._event(session, None, "CAP_CHANGED", f"global {frozen.global_cap} -> {global_cap}; "
                                                      f"owner {frozen.owner_cap} -> {owner_cap}; {reason}")

    # --- Steps inside a transaction ----------------------------------------------------------------------------------

    @staticmethod
    def _row(session: Session, attempt_id: str) -> tuple[uuid.UUID, dict[str, Any]]:
        attempt = _attempt(attempt_id)
        found = None if attempt is None else session.execute(text(
            f"SELECT state, reserved_nano_usd, charged_nano_usd FROM {SCHEMA}.provider_spend_reservations "
            "WHERE attempt_id = :a FOR UPDATE"), {"a": attempt}).first()
        if attempt is None or found is None:
            raise NotReserved(f"{attempt_id} has no reservation")
        return attempt, {"state": found[0], "reserved": found[1], "charged": found[2]}

    def _to_unknown(self, session: Session, attempt: uuid.UUID, reason: str) -> None:
        session.execute(text(f"UPDATE {SCHEMA}.provider_spend_reservations SET state = 'UNKNOWN', updated_at = :now "
                             "WHERE attempt_id = :a"), {"a": attempt, "now": _now()})
        self._event(session, attempt, "UNKNOWN", reason)

    def _charge(self, session: Session, frozen: _Frozen, attempt: uuid.UUID, row: dict[str, Any], input_tokens: int,
                output_tokens: int, detail: str, kind: str = "SETTLED") -> Settlement:
        cost = frozen.price.nano_usd(input_tokens, output_tokens)
        session.execute(text(f"UPDATE {SCHEMA}.provider_spend_reservations SET state = 'SETTLED', charged_nano_usd = :c, "
                             "updated_at = :now WHERE attempt_id = :a"), {"a": attempt, "c": cost, "now": _now()})
        self._event(session, attempt, kind, detail, cost)
        if cost > row["reserved"]:
            self._event(session, attempt, "OVERRUN", "the charge passed its reservation", cost)
        return Settlement("SETTLED", _usd(cost))

    def _compare_evidence(self, session: Session, frozen: _Frozen, attempt: uuid.UUID, row: dict[str, Any],
                          input_tokens: object, output_tokens: object) -> Settlement:
        charged: int = row["charged"]
        if not _valid_usage(input_tokens, output_tokens):
            self._event(session, attempt, "INVALID_EVIDENCE", "unusable usage after settlement")
            return Settlement("SETTLED", _usd(charged))
        cost = frozen.price.nano_usd(input_tokens, output_tokens)  # type: ignore[arg-type]
        if cost == charged:
            self._event(session, attempt, "DUPLICATE_EVIDENCE", "", cost)
            return Settlement("SETTLED", _usd(charged))
        higher = max(cost, charged)  # the evidence disagrees: keep the higher charge until a person decides
        session.execute(text(f"UPDATE {SCHEMA}.provider_spend_reservations SET charged_nano_usd = :c, updated_at = :now "
                             "WHERE attempt_id = :a"), {"a": attempt, "c": higher, "now": _now()})
        self._event(session, attempt, "CONFLICTING_EVIDENCE", f"recorded {charged}, late {cost}", higher)
        return Settlement("SETTLED", _usd(higher))
