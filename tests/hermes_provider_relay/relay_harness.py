"""Shared test support for the relay tests: the LOCAL release, one interpreter over a relay job, and independent counts.

Counts come from three places that do not trust each other: the job's own report, the relay's start records and the
AUTHORED provider's fsynced receipts. Only the job's report is written inside the Hermes container.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from authored_cases import load_case, provider_script
from edge_os_api.research.hermes_interpreter import HermesInterpreter, HermesInterpreterConfig
from edge_os_api.research.interpretation_attempts import AttemptLedger
from provider_guard import GuardPolicy
from provider_transport import TransportRoute
from relay_admission import RelayRelease, RelaySubject
from relay_turn_runner import build_relay_job
from spend_ledger import SpendLedger, TokenPrice

PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
CONFIG = HermesInterpreterConfig(model="fixture-model/1", route="local-authored-relay", max_output_tokens=4096)
POLICY = GuardPolicy(model="fixture-model/1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
ROUTE = TransportRoute("authored-local-1", "AUTHORED", "https://authored-transport.invalid/v1/chat/completions", 65_536)
RELEASE = RelayRelease("local-relay-1", ROUTE.route_id, "AUTHORED", POLICY.model, POLICY.max_output_tokens,
                       POLICY.max_request_bytes, ROUTE.max_reply_bytes)
RESERVATION = Decimal("0.054848")  # (12,000 + 64) x 2.00 / 1e6 + 4,096 x 7.50 / 1e6
EXACT_CHARGE = Decimal("0.0074285")  # concrete-thesis reports 1,423 prompt and 611 completion tokens
OWNER, INTAKE = "owner-a-7f3c", "intake-5e21"


def case(name: str = "concrete-thesis", **fault: Any) -> dict[str, Any]:
    return {**provider_script(load_case(name)["provider"]), **fault}


class Rig:
    """One interpreter over a relay job in the session relay's channel root, with its own attempt ids and SQLite ledger."""

    def __init__(self, relay: Any, image: str, root: Path, name: str, script: dict[str, Any], *,
                 spend: SpendLedger | None = None, scope: str | None = None, timeout_seconds: float = 90,
                 owner: str = OWNER, close_budget_seconds: float = 2.0) -> None:
        self.relay, self.name, self.script = relay, name, script
        self.root = root / "rigs" / name
        self.root.mkdir(parents=True)
        self.evidence = root / "jobs"
        self.spend = spend or SpendLedger(self.root / "spend.sqlite", cap_usd=Decimal("0.20"), price=PRICE)
        self.owner = owner
        self.job = build_relay_job(
            ROUTE, release=RELEASE, endpoint=relay.endpoint("jobs"), subject_for=lambda turn: RelaySubject(owner, INTAKE),
            policy=POLICY, ledger=self.spend, scope_for=lambda turn: scope or f"scope-{name}", image=image,
            run_id=f"{relay.run_id}-{name}"[:40], evidence_dir=self.evidence, script_for=self.script_for,
            forbidden=[OWNER, INTAKE], timeout_seconds=timeout_seconds, close_budget_seconds=close_budget_seconds)
        from test_interpretation_attempts import MemoryAttemptStore
        self.store = MemoryAttemptStore()
        counter, ticks = itertools.count(1), itertools.count(0)
        self.ledger = AttemptLedger(self.store, new_id=lambda: f"{name}-{next(counter)}", now=lambda: dt.datetime(
            2026, 10, 13, 12, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=next(ticks)))
        self.interpreter = HermesInterpreter(CONFIG, self.job.runner, self.ledger, monotonic=time.monotonic)

    def script_for(self, turn: Any) -> dict[str, Any]:
        """The AUTHORED provider's script for this attempt, written where only the provider reads it."""
        path = self.relay.path("provider", "scripts", f"{turn.attempt_id}.json")
        path.write_text(json.dumps(self.script), encoding="utf-8")
        return self.script

    def run_case(self, name: str = "concrete-thesis"):
        return self.interpreter.interpret(self.owner, INTAKE, load_case(name)["intake"])

    def output(self, attempt: str) -> Path:
        [path] = list(self.evidence.glob(f"turn-*-{attempt}/output"))
        return path

    def container_result(self, attempt: str) -> dict[str, Any]:
        return json.loads((self.output(attempt) / "container-result.json").read_text())

    def saved(self) -> Any:
        [attempt] = self.ledger.history(self.owner, INTAKE)
        return attempt


def relay_record(relay: Any, attempt: str, name: str) -> dict[str, Any] | None:
    path = relay.path("state", attempt, f"{name}.json")
    return json.loads(path.read_text()) if path.exists() else None


def provider_receipts(relay: Any, attempt: str) -> list[dict[str, Any]]:
    path = relay.path("provider", "receipts", "receipts.jsonl")
    lines = path.read_text().splitlines() if path.exists() else []
    return [record for record in map(json.loads, lines) if record["attempt_id"] == attempt]


def relay_events(relay: Any, attempt: str) -> list[dict[str, Any]]:
    path = relay.path("state", "events.jsonl")
    lines = path.read_text().splitlines() if path.exists() else []
    return [record for record in map(json.loads, lines) if record["attempt_id"] == attempt]


def counts(relay: Any, attempt: str) -> tuple[int, int]:
    """(relay start records, provider receipts) for one attempt: the two counts written outside the job."""
    return int(relay_record(relay, attempt, "started") is not None), len(provider_receipts(relay, attempt))
