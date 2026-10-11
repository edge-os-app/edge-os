"""A local, durable spend ledger for provider requests. Test and qualification support only.

A request may start only after `reserve` has recorded its worst-case cost. Known usage replaces the reservation with the
exact charge. Everything else keeps the full reservation as liability: missing or invalid usage, an unclear transport
failure, a killed process and an interrupted settlement. Only `release_unsent` frees a reservation, and only while it
is still `RESERVED`. Late evidence is recorded in `reconcile`. It never frees liability silently and never charges twice.

Money is stored as integer nano-USD (10^-9 USD). Token prices are exact `Decimal` values. No binary float is used.

What this proves: LOCAL accounting. It cannot prove that the provider's own billing will stop at the cap. A killed
client may leave an upstream request running, and usage can arrive late. A provider-side limit is a separate release
decision. This module is not wired into the application or to PostgreSQL.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Context, Decimal
from pathlib import Path

__all__ = ["CapExceeded", "Event", "LedgerConfigMismatch", "NotReserved", "Reservation", "ReservationExists",
           "ScopeBlocked", "Settlement", "SpendLedger", "TokenPrice", "Unresolved"]

NANO = Decimal(10) ** 9
MAX_TOKENS = 10 ** 12
EXACT = Context(prec=80)  # wide enough that no product or sum is rounded; every rounding below is explicit
LIABLE_STATES = ("RESERVED", "UNKNOWN")
SCHEMA = """
create table if not exists meta (key text primary key, value text not null);
create table if not exists reservation (
    attempt_id text primary key, scope text not null, state text not null,
    reserved_nano_usd integer not null, charged_nano_usd integer,
    max_input_tokens integer not null, max_output_tokens integer not null,
    created_at text not null, updated_at text not null);
create table if not exists event (
    id integer primary key autoincrement, attempt_id text not null, kind text not null, detail text not null,
    nano_usd integer, at text not null);
"""


class CapExceeded(Exception):
    """The reservation, with all liability, would pass the cap."""

    def __init__(self, committed_usd: Decimal, requested_usd: Decimal, cap_usd: Decimal) -> None:
        super().__init__(f"reservation refused: committed {committed_usd} + requested {requested_usd} > cap {cap_usd}")
        self.committed_usd, self.requested_usd, self.cap_usd = committed_usd, requested_usd, cap_usd


class ScopeBlocked(Exception):
    """An earlier attempt in this scope has liability that is not settled. No automatic retry."""


class ReservationExists(Exception):
    """An attempt identifier reserves once. A restart never spends it again."""


class NotReserved(Exception):
    """The attempt has no reservation, or the reservation is not in a state that allows this step."""


class LedgerConfigMismatch(Exception):
    """A ledger file keeps the cap and prices it was created with. Reopening cannot change them."""


@dataclass(frozen=True)
class TokenPrice:
    prompt_usd_per_million: Decimal
    completion_usd_per_million: Decimal

    def nano_usd(self, input_tokens: int, output_tokens: int) -> int:
        """The cost of these tokens, rounded up to a whole nano-USD."""
        total = EXACT.multiply(EXACT.add(EXACT.multiply(Decimal(input_tokens), self.prompt_usd_per_million),
                                         EXACT.multiply(Decimal(output_tokens), self.completion_usd_per_million)), Decimal(1000))
        return int(total.to_integral_value(rounding=ROUND_CEILING, context=EXACT))


@dataclass(frozen=True)
class Reservation:
    attempt_id: str
    scope: str
    amount_usd: Decimal


@dataclass(frozen=True)
class Settlement:
    state: str
    cost_usd: Decimal


@dataclass(frozen=True)
class Unresolved:
    attempt_id: str
    scope: str
    state: str
    amount_usd: Decimal


@dataclass(frozen=True)
class Event:
    kind: str
    detail: str
    at: str


def _usd(nano: int) -> Decimal:
    return Decimal(nano) / NANO


def _valid_tokens(*counts: object) -> bool:
    return all(isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= MAX_TOKENS for count in counts)


def _valid_usage(input_tokens: object, output_tokens: object) -> bool:
    """Reported usage that can fix a charge. A request that carried a prompt has at least one input token."""
    return _valid_tokens(input_tokens, output_tokens) and input_tokens >= 1  # type: ignore[operator]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SpendLedger:
    def __init__(self, path: Path | str, *, cap_usd: Decimal, price: TokenPrice) -> None:
        self._path = str(path)
        self._price = price
        cap_nano = cap_usd * NANO
        if cap_nano != cap_nano.to_integral_value() or cap_nano < 0:
            raise ValueError("the cap must be a non-negative amount in whole nano-USD")
        self._cap_nano = int(cap_nano)
        with self._write() as connection:
            for statement in filter(None, (part.strip() for part in SCHEMA.split(";"))):
                connection.execute(statement)
            for key, value in (("cap_nano_usd", str(self._cap_nano)), ("prompt_usd_per_million", str(price.prompt_usd_per_million)),
                               ("completion_usd_per_million", str(price.completion_usd_per_million))):
                connection.execute("insert or ignore into meta values (?, ?)", (key, value))
                stored = connection.execute("select value from meta where key = ?", (key,)).fetchone()[0]
                if key == "cap_nano_usd" and int(stored) != self._cap_nano or (
                        key != "cap_nano_usd" and Decimal(stored) != Decimal(value)):
                    raise LedgerConfigMismatch(f"this ledger file was created with a different {key}")

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One immediate transaction. Every step of the ledger is atomic, across threads and processes."""
        with closing(sqlite3.connect(self._path, timeout=60, isolation_level=None)) as connection:
            connection.execute("pragma synchronous = full")
            connection.execute("begin immediate")
            try:
                yield connection
            except BaseException:
                connection.execute("rollback")
                raise
            connection.execute("commit")

    def _read(self, statement: str, *params: object) -> list[tuple]:
        with closing(sqlite3.connect(self._path, timeout=60)) as connection:
            return connection.execute(statement, params).fetchall()

    @staticmethod
    def _event(connection: sqlite3.Connection, attempt_id: str, kind: str, detail: str = "", nano: int | None = None) -> None:
        connection.execute("insert into event (attempt_id, kind, detail, nano_usd, at) values (?, ?, ?, ?, ?)",
                           (attempt_id, kind, detail, nano, _now()))

    @staticmethod
    def _liability_nano(connection: sqlite3.Connection) -> int:
        return connection.execute(
            "select coalesce(sum(case when state = 'SETTLED' then charged_nano_usd "
            "when state in ('RESERVED', 'UNKNOWN') then reserved_nano_usd else 0 end), 0) from reservation").fetchone()[0]

    # --- Reading ---------------------------------------------------------------------------------------------------

    def committed_usd(self) -> Decimal:
        with closing(sqlite3.connect(self._path, timeout=60)) as connection:
            return _usd(self._liability_nano(connection))

    def liability_usd(self, attempt_id: str) -> Decimal | None:
        """What this attempt holds now: its charge when settled, its reservation while unresolved, otherwise zero."""
        rows = self._read("select case when state = 'SETTLED' then charged_nano_usd when state in ('RESERVED', 'UNKNOWN') "
                          "then reserved_nano_usd else 0 end from reservation where attempt_id = ?", attempt_id)
        return _usd(rows[0][0]) if rows else None

    def state(self, attempt_id: str) -> str | None:
        rows = self._read("select state from reservation where attempt_id = ?", attempt_id)
        return rows[0][0] if rows else None

    def unresolved(self) -> list[Unresolved]:
        rows = self._read("select attempt_id, scope, state, reserved_nano_usd from reservation "
                          "where state in ('RESERVED', 'UNKNOWN') order by created_at, attempt_id")
        return [Unresolved(attempt, scope, state, _usd(nano)) for attempt, scope, state, nano in rows]

    def events(self, attempt_id: str) -> list[Event]:
        return [Event(kind, detail, at) for kind, detail, at in self._read(
            "select kind, detail, at from event where attempt_id = ? order by id", attempt_id)]

    # --- Reserving and settling --------------------------------------------------------------------------------------

    def reserve(self, attempt_id: str, *, scope: str, max_input_tokens: int, max_output_tokens: int) -> Reservation:
        """Record the worst-case cost BEFORE a request may start. Raises, and writes nothing, when the cap would pass."""
        if not _valid_tokens(max_input_tokens, max_output_tokens):
            raise ValueError("token bounds must be whole numbers within range")
        amount = self._price.nano_usd(max_input_tokens, max_output_tokens)
        with self._write() as connection:
            if connection.execute("select 1 from reservation where attempt_id = ?", (attempt_id,)).fetchone():
                raise ReservationExists(attempt_id)
            if connection.execute("select 1 from reservation where scope = ? and state in ('RESERVED', 'UNKNOWN')",
                                  (scope,)).fetchone():
                raise ScopeBlocked(scope)
            committed = self._liability_nano(connection)
            if committed + amount > self._cap_nano:
                raise CapExceeded(_usd(committed), _usd(amount), _usd(self._cap_nano))
            now = _now()
            connection.execute("insert into reservation values (?, ?, 'RESERVED', ?, null, ?, ?, ?, ?)",
                               (attempt_id, scope, amount, max_input_tokens, max_output_tokens, now, now))
            self._event(connection, attempt_id, "RESERVED", scope, amount)
        return Reservation(attempt_id, scope, _usd(amount))

    def settle(self, attempt_id: str, *, input_tokens: object, output_tokens: object) -> Settlement:
        """Replace the reservation with the exact charge. Unusable usage keeps the whole reservation as liability."""
        with self._write() as connection:
            row = self._row(connection, attempt_id)
            if row["state"] == "SETTLED":
                return self._compare_evidence(connection, attempt_id, row, input_tokens, output_tokens)
            if row["state"] != "RESERVED":
                raise NotReserved(f"{attempt_id} is {row['state']}")
            if not _valid_usage(input_tokens, output_tokens):
                self._to_unknown(connection, attempt_id, "INVALID_USAGE")
                return Settlement("UNKNOWN", _usd(row["reserved"]))
            return self._charge(connection, attempt_id, row, input_tokens, output_tokens, "SETTLED", "")  # type: ignore[arg-type]

    def mark_unknown(self, attempt_id: str, *, reason: str) -> None:
        """The outcome is not known. The full reservation stays as liability and its scope stays blocked."""
        with self._write() as connection:
            row = self._row(connection, attempt_id)
            if row["state"] == "RESERVED":
                self._to_unknown(connection, attempt_id, reason)

    def release_unsent(self, attempt_id: str, *, reason: str) -> None:
        """Free a reservation whose request was provably never admitted. Nothing else frees liability."""
        with self._write() as connection:
            row = self._row(connection, attempt_id)
            if row["state"] != "RESERVED":
                raise NotReserved(f"{attempt_id} is {row['state']}")
            connection.execute("update reservation set state = 'RELEASED', updated_at = ? where attempt_id = ?",
                               (_now(), attempt_id))
            self._event(connection, attempt_id, "RELEASED", reason)

    def reconcile(self, attempt_id: str, *, input_tokens: int, output_tokens: int, source: str) -> Settlement:
        """Late evidence about an attempt. It records what arrived and never frees or doubles liability."""
        if not _valid_usage(input_tokens, output_tokens):
            raise ValueError("late evidence needs whole token counts, with at least one input token")
        with self._write() as connection:
            row = self._row(connection, attempt_id)
            if row["state"] == "SETTLED":
                return self._compare_evidence(connection, attempt_id, row, input_tokens, output_tokens)
            kind = "RECONCILED" if row["state"] in LIABLE_STATES else "CONFLICTING_EVIDENCE"
            return self._charge(connection, attempt_id, row, input_tokens, output_tokens, "SETTLED", source, kind)

    # --- Steps inside a transaction ----------------------------------------------------------------------------------

    @staticmethod
    def _row(connection: sqlite3.Connection, attempt_id: str) -> dict[str, object]:
        found = connection.execute("select state, reserved_nano_usd, charged_nano_usd from reservation where attempt_id = ?",
                                   (attempt_id,)).fetchone()
        if found is None:
            raise NotReserved(f"{attempt_id} has no reservation")
        return {"state": found[0], "reserved": found[1], "charged": found[2]}

    def _to_unknown(self, connection: sqlite3.Connection, attempt_id: str, reason: str) -> None:
        connection.execute("update reservation set state = 'UNKNOWN', updated_at = ? where attempt_id = ?", (_now(), attempt_id))
        self._event(connection, attempt_id, "UNKNOWN", reason)

    def _charge(self, connection: sqlite3.Connection, attempt_id: str, row: dict[str, object], input_tokens: int,
                output_tokens: int, state: str, detail: str, kind: str | None = None) -> Settlement:
        cost = self._price.nano_usd(input_tokens, output_tokens)
        connection.execute("update reservation set state = ?, charged_nano_usd = ?, updated_at = ? where attempt_id = ?",
                           (state, cost, _now(), attempt_id))
        self._event(connection, attempt_id, kind or "SETTLED", detail, cost)
        if cost > row["reserved"]:  # type: ignore[operator]
            self._event(connection, attempt_id, "OVERRUN", "the charge passed its reservation", cost)
        return Settlement(state, _usd(cost))

    def _compare_evidence(self, connection: sqlite3.Connection, attempt_id: str, row: dict[str, object],
                          input_tokens: object, output_tokens: object) -> Settlement:
        charged: int = row["charged"]  # type: ignore[assignment]
        if not _valid_usage(input_tokens, output_tokens):
            self._event(connection, attempt_id, "INVALID_EVIDENCE", "unusable usage after settlement")
            return Settlement("SETTLED", _usd(charged))
        cost = self._price.nano_usd(input_tokens, output_tokens)  # type: ignore[arg-type]
        if cost == charged:
            self._event(connection, attempt_id, "DUPLICATE_EVIDENCE", "", cost)
            return Settlement("SETTLED", _usd(charged))
        higher = max(cost, charged)  # the evidence disagrees: keep the higher charge until a person decides
        connection.execute("update reservation set charged_nano_usd = ?, updated_at = ? where attempt_id = ?",
                           (higher, _now(), attempt_id))
        self._event(connection, attempt_id, "CONFLICTING_EVIDENCE", f"recorded {charged}, late {cost}", higher)
        return Settlement("SETTLED", _usd(higher))
