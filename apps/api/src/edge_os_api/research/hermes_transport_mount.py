"""The LOCAL Hermes transport mount: the accepted transport job behind the saved Research path, with shared spend.

`open_transport_mount` composes, and adds no new runner:

    GuardedTurnRunner (accepted: policy check, spend reservation, settlement) over PostgresSpendLedger (shared)
      -> TransportTurnRunner (accepted: the job's report must name this attempt and this route)
        -> GuardedDockerTurnRunner with the transport job entry (accepted: deadline D, sealing, recovery C)

Give `mount.runner` to `create_app(settings, hermes_runner=...)` with `EDGE_OS_INTERPRETER=hermes_local`. Production,
any other interpreter, an ACTUAL route and a policy that does not match the application's interpreter are refused
before any effect: no engine, no file, no Docker command. The only transport is the AUTHORED one in a no-network
container. Each API process uses its own stable `run_id`; a restarted process reuses it to recover its dead turns.

LOCAL only: the accepted job code lives under `scripts/`, which this module adds to the import path; the application
factory does not import it. See `docs/qualification/hermes-app-mount/CONTRACT.md`.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from edge_os_api.core.database import make_engine, make_session_factory, require_head
from edge_os_api.core.settings import Settings
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnRunner
from edge_os_api.research.interpretation_workflow import LOCAL_FAKE_CONFIG
from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, SpendLimits

# `provider_spend_ledger` has already added `scripts/hermes_interpretation`, where the accepted runner code lives.
JOB_SUPPORT = Path(__file__).resolve().parents[5] / "scripts" / "hermes_job_support"
if str(JOB_SUPPORT) not in sys.path:
    sys.path.append(str(JOB_SUPPORT))

from guarded_docker_runner import GuardedDockerTurnRunner  # noqa: E402
from provider_guard import GuardPolicy  # noqa: E402
from provider_transport import ActualProviderUnavailable, TransportRoute  # noqa: E402
from transport_turn_runner import build_transport_job  # noqa: E402

__all__ = ["AUTHORED_ROUTE", "DEFAULT_POLICY", "HermesTransportMount", "MountRefused", "open_transport_mount"]

AUTHORED_ROUTE = TransportRoute("authored-local-1", "AUTHORED", "https://authored-transport.invalid/v1/chat/completions",
                                65_536)
# The application's own interpreter settings: the guard refuses any turn whose model or output limit differs.
DEFAULT_POLICY = GuardPolicy(model=LOCAL_FAKE_CONFIG.model, max_output_tokens=LOCAL_FAKE_CONFIG.max_output_tokens,
                             max_request_bytes=12_000, max_envelope_chars=2_500)


class MountRefused(RuntimeError):
    """The mount is not available in this configuration. Nothing was built."""


@dataclass
class HermesTransportMount:
    runner: HermesTurnRunner
    supervision: GuardedDockerTurnRunner
    spend: PostgresSpendLedger
    engine: Engine
    startup_recovery: list[dict[str, Any]] = field(default_factory=list)

    def close(self) -> None:
        self.engine.dispose()


def _intake_scope(engine: Engine) -> Callable[[HermesTurn], str]:
    """One open liability per saved request: the scope is the saved request of the recorded attempt."""
    def scope_for(turn: HermesTurn) -> str:
        with engine.connect() as connection:
            intake = connection.execute(text("SELECT intake_record_id FROM interpretation_attempts WHERE attempt_id = :a"),
                                        {"a": uuid.UUID(turn.attempt_id)}).scalar_one()  # raises: nothing is reserved
        return f"intake:{intake}"
    return scope_for


def open_transport_mount(settings: Settings, *, limits: SpendLimits, image: str, run_id: str, evidence_dir: Path,
                         script_for: Callable[[HermesTurn], Mapping[str, Any]], credential_file: Path | None = None,
                         route: TransportRoute = AUTHORED_ROUTE, policy: GuardPolicy = DEFAULT_POLICY,
                         timeout_seconds: float = 90, run_budget_seconds: int = 60, seal_grace_seconds: float = 5.0,
                         recovery_budget_seconds: float = 5.0) -> HermesTransportMount:
    if settings.env == "production":
        raise MountRefused("the Hermes transport mount is LOCAL only and is refused in production")
    if settings.interpreter != "hermes_local":
        raise MountRefused("the Hermes transport mount needs EDGE_OS_INTERPRETER=hermes_local")
    if route.kind != "AUTHORED":
        raise ActualProviderUnavailable("no actual provider transport exists in this candidate; it needs an approval packet")
    if (policy.model, policy.max_output_tokens) != (LOCAL_FAKE_CONFIG.model, LOCAL_FAKE_CONFIG.max_output_tokens):
        raise MountRefused("the guard policy must match the application's interpreter model and output limit")
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    try:
        require_head(engine)
        spend = PostgresSpendLedger(make_session_factory(engine), limits)
        job = build_transport_job(route, policy=policy, ledger=spend, scope_for=_intake_scope(engine), image=image,
                                  run_id=run_id, evidence_dir=evidence_dir, script_for=script_for,
                                  credential_file=credential_file, timeout_seconds=timeout_seconds,
                                  run_budget_seconds=run_budget_seconds, seal_grace_seconds=seal_grace_seconds,
                                  recovery_budget_seconds=recovery_budget_seconds)
        # A restarted process cleans up its dead turns now, within one budget C, instead of at its next request.
        recovered = job.supervision.recover_pending(recovery_budget_seconds)
    except BaseException:
        engine.dispose()
        raise
    return HermesTransportMount(job.runner, job.supervision, spend, engine, recovered)
