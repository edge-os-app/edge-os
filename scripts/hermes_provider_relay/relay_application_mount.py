"""The relay job behind the saved Research path, with the shared PostgreSQL spend ledger. LOCAL only.

`open_relay_mount` mirrors the accepted `open_transport_mount` (same refusals, same ledger, same intake scope, the same
startup recovery pass) and swaps the accepted transport job for `build_relay_job`. It adds no runner of its own beyond
the relay's. The owner and saved request of each grant are read from the saved attempt row and must equal the owner and
saved request the reservation copied from it; anything else gets no grant.

Give `mount.runner` to `create_app(settings, hermes_runner=...)` with `EDGE_OS_INTERPRETER=hermes_local`. The relay
itself is started separately (`RelaySupervisor`); the mount reads no key and starts nothing but its one recovery pass.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from edge_os_api.core.database import make_engine, make_session_factory, require_head
from edge_os_api.core.settings import Settings
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnRunner
from edge_os_api.research.hermes_transport_mount import AUTHORED_ROUTE, DEFAULT_POLICY, MountRefused
from edge_os_api.research.interpretation_workflow import LOCAL_FAKE_CONFIG
from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, SpendLimits
from guarded_docker_runner import GuardedDockerTurnRunner
from provider_guard import GuardPolicy
from provider_transport import ActualProviderUnavailable, TransportRoute
from relay_admission import RelayRelease, RelaySubject
from relay_turn_runner import RelayEndpoint, build_relay_job

__all__ = ["HermesRelayMount", "open_relay_mount"]


@dataclass
class HermesRelayMount:
    runner: HermesTurnRunner
    supervision: GuardedDockerTurnRunner
    spend: PostgresSpendLedger
    engine: Engine
    startup_recovery: list[dict[str, Any]] = field(default_factory=list)

    def close(self) -> None:
        self.engine.dispose()


def _saved_attempt(engine: Engine, attempt_id: str) -> tuple[Any, Any]:
    with engine.connect() as connection:
        return tuple(connection.execute(text(
            "SELECT owner_id, intake_record_id FROM interpretation_attempts WHERE attempt_id = :a"),
            {"a": uuid.UUID(attempt_id)}).one())  # raises: no grant, nothing sent


def _intake_scope(engine: Engine) -> Callable[[HermesTurn], str]:
    def scope_for(turn: HermesTurn) -> str:
        return f"intake:{_saved_attempt(engine, turn.attempt_id)[1]}"
    return scope_for


def _subject(engine: Engine) -> Callable[[HermesTurn], RelaySubject]:
    """The saved attempt's owner and request, required to equal what the reservation copied from that same row."""
    def subject_for(turn: HermesTurn) -> RelaySubject:
        owner, intake = _saved_attempt(engine, turn.attempt_id)
        with engine.connect() as connection:
            reserved = connection.execute(text(
                "SELECT owner_id, intake_record_id, scope FROM usage_local.provider_spend_reservations "
                "WHERE attempt_id = :a"), {"a": uuid.UUID(turn.attempt_id)}).one()
        if tuple(map(str, reserved)) != (str(owner), str(intake), f"intake:{intake}"):
            raise LookupError("the reservation does not belong to this attempt's owner and saved request")
        return RelaySubject(str(owner), str(intake))
    return subject_for


def open_relay_mount(settings: Settings, *, limits: SpendLimits, release: RelayRelease, endpoint: RelayEndpoint,
                     image: str, run_id: str, evidence_dir: Path, script_for: Callable[[HermesTurn], Mapping[str, Any]],
                     route: TransportRoute = AUTHORED_ROUTE, policy: GuardPolicy = DEFAULT_POLICY,
                     timeout_seconds: float = 90, run_budget_seconds: int = 60, seal_grace_seconds: float = 5.0,
                     recovery_budget_seconds: float = 5.0, close_budget_seconds: float = 2.0) -> HermesRelayMount:
    if settings.env == "production":
        raise MountRefused("the Hermes relay mount is LOCAL only and is refused in production")
    if settings.interpreter != "hermes_local":
        raise MountRefused("the Hermes relay mount needs EDGE_OS_INTERPRETER=hermes_local")
    if route.kind != "AUTHORED":
        raise ActualProviderUnavailable("no actual provider route exists in this candidate; it needs an approval packet")
    if (policy.model, policy.max_output_tokens) != (LOCAL_FAKE_CONFIG.model, LOCAL_FAKE_CONFIG.max_output_tokens):
        raise MountRefused("the guard policy must match the application's interpreter model and output limit")
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    try:
        require_head(engine)
        spend = PostgresSpendLedger(make_session_factory(engine), limits)
        job = build_relay_job(route, release=release, endpoint=endpoint, subject_for=_subject(engine), policy=policy,
                              ledger=spend, scope_for=_intake_scope(engine), image=image, run_id=run_id,
                              evidence_dir=evidence_dir, script_for=script_for, timeout_seconds=timeout_seconds,
                              run_budget_seconds=run_budget_seconds, seal_grace_seconds=seal_grace_seconds,
                              recovery_budget_seconds=recovery_budget_seconds, close_budget_seconds=close_budget_seconds)
        recovered = job.supervision.recover_pending(recovery_budget_seconds)
    except BaseException:
        engine.dispose()
        raise
    return HermesRelayMount(job.runner, job.supervision, spend, engine, recovered)
