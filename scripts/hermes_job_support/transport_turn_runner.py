"""The host side of the Hermes transport job: one constructor, one `HermesTurnRunner`, one supervision handle.

`build_transport_job` composes the accepted P05 parts and adds nothing that runs a job or spends:

    GuardedTurnRunner (policy check, spend reservation, settlement)
      -> TransportTurnRunner (the job's report must name this attempt and this route, or nothing is used)
        -> GuardedDockerTurnRunner with the transport job entry (deadline D, stop, sealing, quarantine, recovery C)

Construction does no I/O: no file is read or written, no credential is read and no process starts. An ACTUAL route is
refused before anything is built; this candidate has no actual provider transport. The credential file is read by the
accepted runner when a turn starts, and only the transport inside the job sees its value.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult, HermesTurnRunner
from guarded_docker_runner import GuardedDockerTurnRunner, JobEntry
from guarded_turn_runner import GuardedTurnRunner
from provider_guard import GuardPolicy
from provider_transport import HERMES_CLIENT_URL, ActualProviderUnavailable, TransportRoute
from spend_ledger import SpendLedger

__all__ = ["TransportJob", "TransportTurnRunner", "build_transport_job", "transport_job_entry"]

HERE = Path(__file__).resolve().parent
JOB_FOLDER = "/opt/p05job"
JOB_FILES = ("transport_turn_job.py", "provider_transport.py", "authored_transport.py")


def transport_job_entry(route: TransportRoute) -> JobEntry:
    files = tuple((HERE / name, f"{JOB_FOLDER}/{name}") for name in JOB_FILES)
    return JobEntry(f"{JOB_FOLDER}/transport_turn_job.py", files,
                    {"transport": {"route": route.settings(), "client_url": HERMES_CLIENT_URL}})


class TransportTurnRunner:
    """Uses a job's result only when the job reports this attempt, this route and at most the one request it counted.

    Anything else is withheld as UNKNOWN with no request count, so the spend reservation stays as liability.
    """

    def __init__(self, delegate: HermesTurnRunner, route: TransportRoute) -> None:
        self._delegate, self._route = delegate, route

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        result = self._delegate.run_turn(turn)
        observed = result.observed
        if "transport_attempt_id" not in observed:  # no job report: nothing started, or the outcome is already unknown
            if result.request_count == 0 or result.status in ("UNKNOWN", "TIMED_OUT"):
                return result
            return self._withheld(result)
        sent = observed.get("transport_request_attempt_ids")
        same = (observed["transport_attempt_id"] == turn.attempt_id
                and observed.get("transport_route_id") == self._route.route_id
                and sent in ([], [turn.attempt_id]) and observed.get("transport_sent") == len(sent)
                and (result.request_count is None or result.request_count == len(sent)))
        return result if same else self._withheld(result)

    @staticmethod
    def _withheld(result: HermesTurnResult) -> HermesTurnResult:
        return replace(result, status="UNKNOWN", text=None, request_count=None, error_class="TransportIdentityMismatch")


@dataclass(frozen=True)
class TransportJob:
    runner: GuardedTurnRunner  # give this to HermesInterpreter
    supervision: GuardedDockerTurnRunner  # recover_pending, pending_cleanup, retry_exhausted, purge_quarantine


def build_transport_job(route: TransportRoute, *, policy: GuardPolicy, ledger: SpendLedger,
                        scope_for: Callable[[HermesTurn], str], image: str, run_id: str, evidence_dir: Path,
                        script_for: Callable[[HermesTurn], Mapping[str, Any]], credential_file: Path | None = None,
                        forbidden: Sequence[str] = (), timeout_seconds: float = 90, run_budget_seconds: int = 60,
                        seal_grace_seconds: float = 5.0, recovery_budget_seconds: float = 5.0) -> TransportJob:
    if route.kind != "AUTHORED":
        raise ActualProviderUnavailable("no actual provider transport exists in this candidate; it needs an approval packet")
    supervision = GuardedDockerTurnRunner(
        image=image, run_id=run_id, evidence_dir=evidence_dir, script_for=script_for, forbidden=forbidden,
        timeout_seconds=timeout_seconds, run_budget_seconds=run_budget_seconds, policy=policy,
        credential_file=credential_file, seal_grace_seconds=seal_grace_seconds,
        recovery_budget_seconds=recovery_budget_seconds, job_entry=transport_job_entry(route))
    return TransportJob(GuardedTurnRunner(TransportTurnRunner(supervision, route), ledger, policy, scope_for), supervision)
