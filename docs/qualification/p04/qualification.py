"""Offline P04 qualification fixtures; they do not exercise Hermes or a host boundary."""

from __future__ import annotations

import asyncio
import json
import runpy
import tempfile
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

_P02 = runpy.run_path(str(Path(__file__).resolve().parents[3] / "docs/contracts/p02/check_contract.py"))


class IdempotencyConflict(ValueError):
    """The same owner/agent request key was reused for different input."""


class ProviderTimeout(TimeoutError):
    """A local provider fixture exceeded its caller deadline."""


@dataclass(frozen=True)
class TaskIdentity:
    owner_id: str
    agent_id: str
    job_id: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.owner_id, self.agent_id, self.job_id)):
            raise ValueError("task identity fields must be nonempty")


@dataclass(frozen=True)
class MemoryEntry:
    text: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class MemorySnapshot:
    version: int
    entries: tuple[MemoryEntry, ...]


class MemoryStore:
    """Small in-memory stand-in for owner- and agent-scoped application storage."""

    # ponytail: in-memory fixture only; replace with transactional owner-scoped storage before runtime use.
    def __init__(self) -> None:
        self._owner_by_agent: dict[str, str] = {}
        self._versions: dict[tuple[str, str], int] = {}
        self._entries: dict[tuple[str, str], tuple[MemoryEntry, ...]] = {}
        self._history: dict[tuple[str, str], tuple[MemorySnapshot, ...]] = {}
        self._enabled: dict[tuple[str, str], bool] = {}
        self._suggestions: dict[str, tuple[str, str, MemoryEntry]] = {}

    def _key(self, owner_id: str, agent_id: str) -> tuple[str, str]:
        if not owner_id.strip() or not agent_id.strip():
            raise ValueError("owner and agent IDs must be nonempty")
        known_owner = self._owner_by_agent.get(agent_id)
        if known_owner is not None and known_owner != owner_id:
            raise PermissionError("agent is not owned by this principal")
        return owner_id, agent_id

    def correct(
        self, owner_id: str, agent_id: str, text: str, source_refs: list[str]
    ) -> int:
        key = self._key(owner_id, agent_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("memory text must be nonempty")
        if not isinstance(source_refs, list) or not all(
            isinstance(ref, str) and ref.strip() for ref in source_refs
        ):
            raise ValueError("memory source references must be nonempty strings")
        if len(text.encode("utf-8")) > 2048 or len(source_refs) > 8:
            raise ValueError("memory entry exceeds the fixture limits")
        entry = MemoryEntry(text.strip(), tuple(source_refs))
        version = self._versions.get(key, 0) + 1
        entries = (*self._entries.get(key, ()), entry)
        if len(entries) > 32:
            raise ValueError("memory record exceeds the fixture entry limit")
        record = {
            "schema": "edge-agent-context/1",
            "owner_id": owner_id,
            "agent_id": agent_id,
            "version": version,
            "enabled": True,
            "entries": [
                {"text": item.text, "source_refs": list(item.source_refs)} for item in entries
            ],
        }
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > 16_384:
            raise ValueError("memory record exceeds the fixture byte limit")
        snapshot = MemorySnapshot(version, entries)
        self._owner_by_agent[agent_id] = owner_id
        self._versions[key] = version
        self._entries[key] = entries
        self._history[key] = (*self._history.get(key, ()), snapshot)[-32:]
        self._enabled[key] = True
        return version

    def suggest(
        self, owner_id: str, agent_id: str, text: str, source_refs: list[str]
    ) -> str:
        key = self._key(owner_id, agent_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("suggestion text must be nonempty")
        if not isinstance(source_refs, list) or not all(
            isinstance(ref, str) and ref.strip() for ref in source_refs
        ):
            raise ValueError("suggestion source references must be nonempty strings")
        if len(text.encode("utf-8")) > 2048 or len(source_refs) > 8:
            raise ValueError("suggestion exceeds the fixture entry limits")
        self._owner_by_agent[agent_id] = owner_id
        suggestion_id = uuid.uuid4().hex
        self._suggestions[suggestion_id] = (key[0], key[1], MemoryEntry(text, tuple(source_refs)))
        return suggestion_id

    def adopt_suggestion(self, owner_id: str, agent_id: str, suggestion_id: str) -> int:
        key = self._key(owner_id, agent_id)
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion is None or suggestion[:2] != key:
            raise PermissionError("suggestion is not available to this agent")
        entry = suggestion[2]
        version = self.correct(owner_id, agent_id, entry.text, list(entry.source_refs))
        self._suggestions.pop(suggestion_id)
        return version

    def retrieve(self, owner_id: str, agent_id: str) -> MemorySnapshot | None:
        key = self._key(owner_id, agent_id)
        if not self._enabled.get(key, False) or key not in self._versions:
            return None
        return self._history[key][-1]

    def task_snapshot(self, owner_id: str, agent_id: str) -> MemorySnapshot | None:
        return self.retrieve(owner_id, agent_id)

    def history(self, owner_id: str, agent_id: str) -> tuple[MemorySnapshot, ...]:
        key = self._key(owner_id, agent_id)
        return self._history.get(key, ())

    def disable(self, owner_id: str, agent_id: str) -> None:
        self._enabled[self._key(owner_id, agent_id)] = False

    def enable(self, owner_id: str, agent_id: str) -> None:
        key = self._key(owner_id, agent_id)
        if key not in self._versions:
            raise KeyError("memory record does not exist")
        self._enabled[key] = True

    def clear(self, owner_id: str, agent_id: str) -> None:
        key = self._key(owner_id, agent_id)
        version = self._versions.get(key, 0) + 1
        self._versions[key] = version
        self._entries[key] = ()
        self._history[key] = (MemorySnapshot(version, ()),)
        self._enabled[key] = False
        for suggestion_id, (suggestion_owner, suggestion_agent, _) in tuple(self._suggestions.items()):
            if (suggestion_owner, suggestion_agent) == key:
                self._suggestions.pop(suggestion_id)


class JobRegistry:
    """Fixture idempotency map keyed from trusted owner/agent context."""

    def __init__(self) -> None:
        self._requests: dict[tuple[str, str, str], tuple[str, str]] = {}

    def submit(self, owner_id: str, agent_id: str, request_key: str, fingerprint: str) -> str:
        if not all(value.strip() for value in (owner_id, agent_id, request_key, fingerprint)):
            raise ValueError("job identity and request fingerprint must be nonempty")
        key = (owner_id, agent_id, request_key)
        existing = self._requests.get(key)
        if existing is not None:
            job_id, old_fingerprint = existing
            if old_fingerprint != fingerprint:
                raise IdempotencyConflict("request key reused with different input")
            return job_id
        job_id = uuid.uuid4().hex
        self._requests[key] = (job_id, fingerprint)
        return job_id


class TaskWorkspace:
    """Path guard for one fixture directory; not an OS security boundary."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError("path escapes the task workspace") from exc
        return target

    def write_text(self, relative: str, text: str) -> None:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def read_text(self, relative: str) -> str:
        return self.path(relative).read_text(encoding="utf-8")


@dataclass
class UsageRecord:
    estimate_usd: Decimal
    status: str = "RESERVED"
    actual_usd: Decimal | None = None
    actual_tokens: int | None = None


class UsageLedger:
    """Fixture ledger that keeps unknown provider charges reserved."""

    # ponytail: process-local ledger only; durable reservation/settlement belongs to the application store.
    def __init__(self) -> None:
        self._records: dict[str, UsageRecord] = {}

    @property
    def reserved_usd(self) -> Decimal:
        return sum(
            (record.estimate_usd for record in self._records.values() if record.status != "SETTLED"),
            Decimal("0"),
        )

    def reserve(self, job_id: str, estimate_usd: Decimal | str | float) -> UsageRecord:
        estimate = Decimal(str(estimate_usd))
        if not job_id.strip() or not estimate.is_finite() or estimate <= 0:
            raise ValueError("job ID and positive finite estimate are required")
        if job_id in self._records:
            raise IdempotencyConflict("usage already reserved for this job")
        self._records[job_id] = UsageRecord(estimate)
        return self._records[job_id]

    def settle(
        self, job_id: str, *, actual_usd: Decimal | str | float | None, actual_tokens: int | None
    ) -> UsageRecord:
        record = self._records[job_id]
        if record.status != "RESERVED":
            raise ValueError("usage is already terminal")
        if actual_usd is None or actual_tokens is None:
            record.status = "UNKNOWN"
            return record
        actual, tokens = _validated_usage(actual_usd, actual_tokens)
        record.actual_usd = actual
        record.actual_tokens = tokens
        record.status = "SETTLED"
        return record

    def reconcile(
        self, job_id: str, *, actual_usd: Decimal | str | float, actual_tokens: int
    ) -> UsageRecord:
        record = self._records[job_id]
        if record.status != "UNKNOWN":
            raise ValueError("only unknown usage can be reconciled")
        actual, tokens = _validated_usage(actual_usd, actual_tokens)
        record.actual_usd = actual
        record.actual_tokens = tokens
        record.status = "SETTLED"
        return record


def _validated_usage(actual_usd: Decimal | str | float, actual_tokens: int) -> tuple[Decimal, int]:
    try:
        actual = Decimal(str(actual_usd))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("reported usage must be a valid finite amount") from exc
    if (
        not actual.is_finite() or actual < 0
        or isinstance(actual_tokens, bool) or not isinstance(actual_tokens, int)
        or actual_tokens < 0
    ):
        raise ValueError("reported usage must be nonnegative and finite")
    return actual, actual_tokens


def validate_outcome(payload: str) -> dict[str, object]:
    """Validate Outcome record content with the accepted P02 checker."""
    try:
        value = _P02["strict_loads"](payload)
        _P02["validate_record"]("Outcome", value)
    except (TypeError, ValueError) as exc:
        raise ValueError("provider output does not match the P02 Outcome record") from exc
    return value


def safe_error(code: str, untrusted_detail: str) -> dict[str, str]:
    """Return a stable public error without persisting provider/exception text."""
    if not code.strip():
        raise ValueError("error code must be nonempty")
    del untrusted_detail
    return {"code": code, "message": "Provider request failed."}


async def run_bounded(awaitable: Awaitable[T], *, timeout: float) -> T:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except TimeoutError as exc:
        raise ProviderTimeout("provider fixture timed out") from exc


async def run_with_workspace(
    root: str | Path,
    job_id: str,
    call: Callable[[TaskWorkspace], Awaitable[T]],
    *,
    timeout: float,
) -> T:
    if not job_id or any(char in job_id for char in "/\\"):
        raise ValueError("job ID must be a simple path component")
    with tempfile.TemporaryDirectory(prefix=f"{job_id}-", dir=root) as directory:
        return await run_bounded(call(TaskWorkspace(Path(directory))), timeout=timeout)
