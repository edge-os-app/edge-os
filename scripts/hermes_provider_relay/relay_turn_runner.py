"""The host side of the Hermes provider relay: the constructor, the grant/close turn runner and the job entry.

`build_relay_job` composes the accepted parts and adds one runner, `RelayTurnRunner`:

    GuardedTurnRunner (accepted: policy check, spend reservation, settlement)
      -> RelayTurnRunner (grant before the job; close, then the relay's own record decides what the count may be)
        -> TransportTurnRunner (accepted: the job's report must name this attempt and this route)
          -> GuardedDockerTurnRunner, relay job entry, NO credential (accepted: no network, deadline D, sealing, C)

The job never holds a key or a network path: its one request goes through the job channel to the relay, which holds
the synthetic key and is the only component that can reach the AUTHORED provider. Construction does no I/O: no file is
read or written, no key is read and nothing starts. An ACTUAL route is refused before anything is built unless the
caller gives the approved release record it came from (CONTRACT A6); none is approved in this candidate. With an ACTUAL
record the caller must also give the ledger's own TokenPrice, and a counted result needs the provider-reported cost,
rounded up to a whole nano-USD, to EQUAL that price's charge for the reported usage, within the held reservation.
See `docs/qualification/hermes-provider-relay/CONTRACT.md`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult, HermesTurnRunner
from edge_os_api.research.interpretation_attempts import Usage
from guarded_docker_runner import GuardedDockerTurnRunner, JobEntry
from guarded_turn_runner import GuardedTurnRunner
from provider_guard import GuardPolicy
from provider_transport import HERMES_CLIENT_URL, ActualProviderUnavailable, TransportRoute
from relay_admission import CLOCK_SKEW_SECONDS, ActualRelease, RelayRelease, RelaySubject, issue_grant
from spend_ledger import EXACT, NANO, SpendLedger, TokenPrice
from transport_turn_runner import TransportTurnRunner

__all__ = ["RelayEndpoint", "RelayJob", "RelayTurnRunner", "build_relay_job", "relay_job_entry"]

HERE = Path(__file__).resolve().parent
JOB_SUPPORT = HERE.parent / "hermes_job_support"
JOB_FOLDER = "/opt/p05job"
JOB_FILES = ((HERE, "relay_turn_job.py"), (HERE, "relay_job_channel.py"), (JOB_SUPPORT, "provider_transport.py"))
MAX_RECORD_BYTES = 64 * 1024
MAX_KEY_BYTES = 1024
CLOSE_POLL_SECONDS = 0.02
COUNTED = ("RETURNED", "TRUNCATED")


def relay_job_entry(route: TransportRoute, release: RelayRelease) -> JobEntry:
    files = tuple((folder / name, f"{JOB_FOLDER}/{name}") for folder, name in JOB_FILES)
    return JobEntry(f"{JOB_FOLDER}/relay_turn_job.py", files,
                    {"transport": {"route": route.settings(), "client_url": HERMES_CLIENT_URL},
                     "relay": {"release_id": release.release_id}})


@dataclass(frozen=True)
class RelayEndpoint:
    """The host paths shared with the relay (never with the job) and this job's channel root name."""

    grants: Path
    revocations: Path
    state: Path
    admission_key_file: Path
    channel_root: str
    heartbeat_max_age_seconds: float = 2.0


def _read_bounded(path: Path, limit: int) -> bytes | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, limit + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data if len(data) <= limit else None


def _read_json(path: Path) -> dict[str, Any] | None:
    data = _read_bounded(path, MAX_RECORD_BYTES)
    try:
        value = json.loads(data) if data is not None else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _refused(error_class: str) -> HermesTurnResult:
    """Nothing was granted, so nothing can have been sent: count 0 and the guard's 0, as the accepted runner requires."""
    return HermesTurnResult(status="PROVIDER_FAILED", text=None, usage=Usage(), request_count=0,
                            observed={"guard_admitted": 0, "refusal": error_class}, error_class=error_class)


class RelayTurnRunner:
    """Issues the attempt's grant before the job and closes it after; the relay's own record limits the job's report.

    A zero-request result stands only when the relay recorded the attempt closed and never started. A counted result
    stands only when the relay started exactly once and received a reply whose reported usage equals the job's.
    Anything else is withheld as UNKNOWN with no request count, so the reservation stays as liability.
    """

    def __init__(self, delegate: HermesTurnRunner, *, endpoint: RelayEndpoint, release: RelayRelease, policy: GuardPolicy,
                 ledger: SpendLedger, scope_for: Callable[[HermesTurn], str],
                 subject_for: Callable[[HermesTurn], RelaySubject], run_id: str, timeout_seconds: float,
                 close_budget_seconds: float, actual: ActualRelease | None = None,
                 price: TokenPrice | None = None) -> None:
        self._delegate, self._endpoint, self._release, self._policy = delegate, endpoint, release, policy
        self._ledger, self._scope_for, self._subject_for = ledger, scope_for, subject_for
        self._run_id, self._timeout, self._close_budget = run_id, timeout_seconds, close_budget_seconds
        self._actual, self._price = actual, price

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        try:
            subject = self._subject_for(turn)
            scope = self._scope_for(turn)
        except Exception:  # noqa: BLE001 - an owner or request that cannot be proved gets no grant
            return _refused("RelaySubjectUnavailable")
        try:
            reserved = self._ledger.state(turn.attempt_id) == "RESERVED"
        except Exception:  # noqa: BLE001 - without a readable reservation nothing may start
            reserved = False
        if not reserved:
            return _refused("RelayReservationMissing")
        if not self._relay_alive():
            return _refused("RelayUnavailable")
        key = _read_bounded(self._endpoint.admission_key_file, MAX_KEY_BYTES)
        if not key:
            return _refused("RelayUnavailable")
        grant = issue_grant(release=self._release, run_id=self._run_id, channel_root=self._endpoint.channel_root,
                            owner_id=subject.owner_id, request_id=subject.request_id, attempt_id=turn.attempt_id,
                            scope=scope, policy={**asdict(self._policy), "required_extra": dict(self._policy.required_extra)},
                            system_prompt=turn.system_prompt, user_message=turn.user_message, issued_at=time.time(),
                            timeout_seconds=self._timeout, key=key)
        if not self._write_once(self._endpoint.grants / f"{turn.attempt_id}.json", grant):
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None,
                                    observed={"relay_grant_id": None}, error_class="RelayGrantExists")
        try:
            result = self._delegate.run_turn(turn)
        except BaseException:
            self._close(turn.attempt_id)  # the job is over either way; the accepted runner keeps the liability
            raise
        closed, finished = self._close(turn.attempt_id)
        return self._limited(result, grant["grant_id"], closed, finished, turn.attempt_id)

    def _relay_alive(self) -> bool:
        beat = _read_json(self._endpoint.state / "heartbeat.json")
        if beat is None or beat.get("release") != self._release.settings():
            return False
        at = beat.get("at")
        age = time.time() - at if isinstance(at, (int, float)) else math.inf
        return -CLOCK_SKEW_SECONDS <= age <= self._endpoint.heartbeat_max_age_seconds  # the relay's clock may run ahead

    @staticmethod
    def _write_once(path: Path, value: dict[str, Any]) -> bool:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError:
            return False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(value, sort_keys=True))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # fails if the name exists: an earlier grant is never replaced
            except FileExistsError:
                return False
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def _close(self, attempt_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Revoke the grant and wait, at most the close budget, for the relay's closed record."""
        self._write_once(self._endpoint.revocations / f"{attempt_id}.json", {"attempt_id": attempt_id, "at": time.time()})
        records = self._endpoint.state / attempt_id
        until = time.monotonic() + self._close_budget
        while True:
            closed = _read_json(records / "closed.json")
            if closed is not None or time.monotonic() >= until:
                break
            time.sleep(CLOSE_POLL_SECONDS)
        return closed, _read_json(records / "finished.json")

    def _cost_equals_charge(self, attempt_id: str, finished: dict[str, Any]) -> bool:
        """E1-COST1: the provider-reported cost, rounded up to a whole nano-USD like the ledger rounds, equals the ledger
        price's charge for the reported usage, and that charge is within the held reservation. Unreadable means no.

        shortcut: other provider prices, cached-token discounts or fees make this UNKNOWN; settling at a reported cost
        needs the ledger owner (CONTRACT A6)."""
        cost, usage = finished.get("cost"), finished.get("usage")
        if (self._price is None or isinstance(cost, bool) or not isinstance(cost, (int, float))
                or not math.isfinite(cost) or cost < 0 or not isinstance(usage, dict)):
            return False
        try:
            reported = int(EXACT.multiply(Decimal(repr(cost)), NANO).to_integral_value(rounding=ROUND_CEILING,
                                                                                        context=EXACT))
            charge = self._price.nano_usd(usage["prompt_tokens"], usage["completion_tokens"])
            liability = self._ledger.liability_usd(attempt_id)
            return reported == charge and liability is not None and EXACT.divide(Decimal(charge), NANO) <= liability
        except Exception:  # noqa: BLE001 - unreadable evidence never counts a result
            return False

    def _limited(self, result: HermesTurnResult, grant_id: str, closed: dict[str, Any] | None,
                 finished: dict[str, Any] | None, attempt_id: str) -> HermesTurnResult:
        started = closed.get("started") if closed is not None else None
        outcome = finished.get("outcome") if finished is not None else None
        observed = {**result.observed, "relay_release_id": self._release.release_id, "relay_grant_id": grant_id,
                    "relay_started": started if isinstance(started, bool) else None, "relay_outcome": outcome}
        if self._actual is not None and finished is not None:
            observed.update(relay_cost=finished.get("cost"), relay_generation_id=finished.get("generation_id"))
        result = replace(result, observed=observed)
        if started is False:
            return result if result.request_count == 0 else self._withheld(result, "RelayCountMismatch")
        if started is not True:
            return self._withheld(result, "RelayStateUnknown")
        if result.status in COUNTED:
            usage = finished.get("usage") if finished is not None else None
            status = finished.get("status") if finished is not None else None
            same = (outcome == "reply" and type(status) is int and 200 <= status < 300  # noqa: E721
                    and result.request_count == 1 and isinstance(usage, dict)
                    and result.usage.source == "PROVIDER_REPORTED"
                    and (usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"))
                    == (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens))
            if not same:
                return self._withheld(result, "RelayCountMismatch")
            if self._actual is not None and not self._cost_equals_charge(attempt_id, finished):
                return self._withheld(result, "RelayCostUnverified")  # the full reservation stays as liability
            return result
        if result.request_count == 0:  # the relay started a request the job says it never sent
            return self._withheld(result, "RelayCountMismatch")
        return result  # UNKNOWN, PROVIDER_FAILED or TIMED_OUT with a request: the accepted runner keeps the liability

    @staticmethod
    def _withheld(result: HermesTurnResult, error_class: str) -> HermesTurnResult:
        return replace(result, status="UNKNOWN", text=None, request_count=None, error_class=error_class)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _check_actual(route: TransportRoute, actual: ActualRelease, policy: GuardPolicy) -> None:
    """The route and the guard policy must be exactly the record's: endpoint, reply bound and request shape."""
    if (route.endpoint_url, route.max_reply_bytes) != (actual.endpoint_url, actual.release.max_reply_bytes):
        raise ValueError("the ACTUAL route must be the record's endpoint and reply bound")
    extra = dict(policy.required_extra)
    expected = {"stream": False, "provider": actual.provider}
    if actual.reasoning is not None:
        expected["reasoning"] = actual.reasoning
    schema = extra.pop("response_format", None)
    schema_ok = (schema is not None and hashlib.sha256(_canonical(schema)).hexdigest() == actual.response_format_sha256
                 if "response_format" in actual.allowed_fields else schema is None)
    if _canonical(extra) != _canonical(expected) or not schema_ok:
        raise ValueError("the guard policy must require exactly the record's request shape")


@dataclass(frozen=True)
class RelayJob:
    runner: GuardedTurnRunner  # give this to HermesInterpreter or create_app(settings, hermes_runner=...)
    supervision: GuardedDockerTurnRunner  # accepted: recover_pending, pending_cleanup, retry_exhausted, purge_quarantine


def build_relay_job(route: TransportRoute, *, release: RelayRelease, endpoint: RelayEndpoint,
                    subject_for: Callable[[HermesTurn], RelaySubject], policy: GuardPolicy, ledger: SpendLedger,
                    scope_for: Callable[[HermesTurn], str], image: str, run_id: str, evidence_dir: Path,
                    script_for: Callable[[HermesTurn], Mapping[str, Any]], forbidden: Sequence[str] = (),
                    timeout_seconds: float = 90, run_budget_seconds: int = 60, seal_grace_seconds: float = 5.0,
                    recovery_budget_seconds: float = 5.0, close_budget_seconds: float = 2.0,
                    actual: ActualRelease | None = None, price: TokenPrice | None = None) -> RelayJob:
    """`price` is required for an ACTUAL route: the SAME TokenPrice the caller gave its ledger (the trusted composition
    owner's obligation; a type check cannot prove it). An AUTHORED route takes no record and no price."""
    if route.kind == "ACTUAL":
        if actual is None or actual.release != release:
            raise ActualProviderUnavailable("an ACTUAL route needs its approved release record (CONTRACT A6)")
        if not isinstance(price, TokenPrice):
            raise ValueError("an ACTUAL route needs the ledger's own TokenPrice (E1-COST1)")
        if isinstance(timeout_seconds, bool) or timeout_seconds != actual.timeout_seconds:
            raise ValueError("an ACTUAL job's timeout_seconds must equal the release record's grant life (R9)")
        _check_actual(route, actual, policy)
    elif route.kind != "AUTHORED" or actual is not None or price is not None or release.kind != "AUTHORED":
        raise ValueError("an AUTHORED route takes an AUTHORED release, no ACTUAL record and no price")
    if (release.route_id, release.max_reply_bytes) != (route.route_id, route.max_reply_bytes) or (
            release.model, release.max_output_tokens, release.max_request_bytes) != (
            policy.model, policy.max_output_tokens, policy.max_request_bytes):
        raise ValueError("the release must name this route and the policy's model, output limit and request bound")
    if (isinstance(close_budget_seconds, bool) or not isinstance(close_budget_seconds, (int, float))
            or not math.isfinite(close_budget_seconds) or close_budget_seconds <= 0):
        raise ValueError("close_budget_seconds must be a finite number above 0")
    supervision = GuardedDockerTurnRunner(
        image=image, run_id=run_id, evidence_dir=evidence_dir, script_for=script_for, forbidden=forbidden,
        timeout_seconds=timeout_seconds, run_budget_seconds=run_budget_seconds, policy=policy, credential_file=None,
        seal_grace_seconds=seal_grace_seconds, recovery_budget_seconds=recovery_budget_seconds,
        job_entry=relay_job_entry(route, release))
    relay = RelayTurnRunner(TransportTurnRunner(supervision, route), endpoint=endpoint, release=release, policy=policy,
                            ledger=ledger, scope_for=scope_for, subject_for=subject_for, run_id=run_id,
                            timeout_seconds=timeout_seconds, close_budget_seconds=close_budget_seconds, actual=actual,
                            price=price)
    return RelayJob(GuardedTurnRunner(relay, ledger, policy, scope_for), supervision)
