"""RemovalService: durable local removal request, observation reconciliation and read.

The owner is always the verified caller. A request resolves the actual saved
wallet binding through an accepted owner-scoped read and is persisted before any
controlled effect. Ownership, agent, wallet, network, signer and policy
identities are validated; a mismatch is refused. Every mutation for one wallet is
serialized by the same per-wallet PostgreSQL advisory lock the accepted P22
admission path and the P25 stop path use, so a stale binding or a concurrent
observation cannot silently confirm or restore removal.

This service writes only `revocation_local` tables. It never writes holdings,
allowances, reservations, claims, recovery cases, funding flows, stops, inactive
consent or a wallet binding. A local record is not confirmed provider removal.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.service import acquire_wallet_lock
from edge_os_api.revocation.records import (
    RemovalObservationRow,
    RemovalRequestRow,
    RemovalStateRow,
)
from edge_os_api.revocation.types import (
    DENIAL_REASON,
    DENYING_STATES,
    ReconcileOutcome,
    RemovalError,
    RemovalObservation,
    RemovalRequest,
    RemovalView,
    parse_utc,
)
from edge_os_api.wallet_setup.persistence import WalletSetupRow

NETWORK_TO_INT = {"monad:143": 143, "monad-testnet:10143": 10143}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class WalletBinding:
    """The current saved wallet binding resolved for one verified owner and agent."""

    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str


class WalletBindingReader(Protocol):
    def current_binding(
        self, session: Session, verified_owner_id: uuid.UUID, *,
        agent_id: str, network_id: str, lock: bool = False,
    ) -> WalletBinding | None: ...


class SavedWalletBindingReader:
    """Reader of the accepted saved `wallet_setups` binding row.

    With `lock=True` it takes the same `FOR UPDATE` row lock the accepted wallet
    setup writer uses, so a concurrent binding change cannot commit between the
    validation and the removal save. The read order is the shared per-wallet
    advisory lock first, then this binding row lock; the wallet setup writer takes
    only the row lock, so the ordering has no cycle.
    """

    def current_binding(
        self, session: Session, verified_owner_id: uuid.UUID, *,
        agent_id: str, network_id: str, lock: bool = False,
    ) -> WalletBinding | None:
        network_int = NETWORK_TO_INT.get(network_id)
        if network_int is None:
            return None
        statement = select(WalletSetupRow).where(
            WalletSetupRow.owner_id == verified_owner_id,
            WalletSetupRow.agent_id == agent_id,
            WalletSetupRow.network_id == network_int,
            WalletSetupRow.state == "CONFIRMED",
        )
        if lock:
            statement = statement.with_for_update(of=WalletSetupRow)
        row = session.execute(statement).scalar_one_or_none()
        if row is None or row.wallet_id is None:
            return None
        return WalletBinding(owner_id=verified_owner_id, agent_id=agent_id,
                             wallet_id=row.wallet_id, network_id=network_id)


class RemovalService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        wallet_bindings: WalletBindingReader | None = None,
        clock=None,
    ) -> None:
        self._factory = session_factory
        self._bindings: WalletBindingReader = wallet_bindings or SavedWalletBindingReader()
        self._clock = clock or _utc_now

    # ------------------------------------------------------------------ request

    def request_removal(self, verified_owner_id: uuid.UUID, request: RemovalRequest) -> RemovalView:
        """Persist one durable removal request before any controlled effect.

        An exact repeated request is idempotent: the same durable record is
        returned and no second row is written. A different request key for the
        same removal identity is refused, so no new identity appears on restart.
        """
        with self._factory() as session:
            try:
                binding = self._bindings.current_binding(
                    session, verified_owner_id, agent_id=request.agent_id, network_id=request.network_id)
                if binding is None:
                    raise RemovalError("no confirmed saved wallet binding for this agent and network")
                if request.expected_wallet_id is not None and request.expected_wallet_id != binding.wallet_id:
                    raise RemovalError("the requested wallet does not match the saved wallet binding")
                session.rollback()
                acquire_wallet_lock(session, verified_owner_id, request.agent_id,
                                    binding.wallet_id, request.network_id)
                session.expire_all()
                # Re-read the binding under the accepted row lock and hold it
                # through commit, so a concurrent binding change cannot commit
                # between this validation and the durable request write.
                current = self._bindings.current_binding(
                    session, verified_owner_id, agent_id=request.agent_id,
                    network_id=request.network_id, lock=True)
                if current is None or current.wallet_id != binding.wallet_id:
                    raise RemovalError("the saved wallet binding changed during the request")
                now = self._clock()
                session.execute(pg_insert(RemovalRequestRow).values(
                    request_id=uuid.uuid4(), owner_id=verified_owner_id, agent_id=request.agent_id,
                    wallet_id=binding.wallet_id, network_id=request.network_id,
                    request_key=request.request_key, reason=request.reason,
                    signer_identity=request.signer_identity, policy_identity=request.policy_identity,
                    provenance=request.provenance.model_dump(mode="json"),
                    requested_at=parse_utc(request.requested_at), created_at=now,
                ).on_conflict_do_nothing(
                    index_elements=["owner_id", "agent_id", "wallet_id", "network_id"]))
                session.flush()
                row = session.execute(select(RemovalRequestRow).where(
                    RemovalRequestRow.owner_id == verified_owner_id,
                    RemovalRequestRow.agent_id == request.agent_id,
                    RemovalRequestRow.wallet_id == binding.wallet_id,
                    RemovalRequestRow.network_id == request.network_id,
                )).scalar_one()
                # An exact repeat is idempotent. A changed request key or changed
                # material content for the same removal identity is refused, so a
                # lost-reply retry can never appear to request a new signer.
                if (row.request_key != request.request_key
                        or row.signer_identity != request.signer_identity
                        or row.policy_identity != request.policy_identity
                        or row.reason != request.reason):
                    raise RemovalError("this wallet already has a different removal request")
                self._ensure_state(session, row, now)
                session.commit()
                return self._view(session, row)
            except SQLAlchemyError:
                session.rollback()
                raise
            except RemovalError:
                session.rollback()
                raise

    # --------------------------------------------------------------- reconcile

    def reconcile(self, verified_owner_id: uuid.UUID, observation: RemovalObservation) -> ReconcileOutcome:
        """Reconcile one provider-style observation against its original request.

        Only an exact matched observation plus the current wallet binding can
        produce a fixture-confirmed removal. A mismatched, stale, wrong-wallet,
        wrong-signer or wrong-network observation is recorded with its denial
        code and changes nothing. A late observation that contradicts a
        confirmed removal is retained without restoring removed permission.
        """
        with self._factory() as session:
            try:
                row = session.execute(select(RemovalRequestRow).where(
                    RemovalRequestRow.owner_id == verified_owner_id,
                    RemovalRequestRow.request_id == observation.request_id,
                )).scalar_one_or_none()
                if row is None:
                    raise RemovalError("removal request not found for the verified owner")
                acquire_wallet_lock(session, verified_owner_id, row.agent_id, row.wallet_id, row.network_id)
                session.expire_all()
                row = session.execute(select(RemovalRequestRow).where(
                    RemovalRequestRow.owner_id == verified_owner_id,
                    RemovalRequestRow.request_id == observation.request_id,
                ).with_for_update().execution_options(populate_existing=True)).scalar_one()
                state = session.execute(select(RemovalStateRow).where(
                    RemovalStateRow.request_id == row.request_id,
                ).with_for_update().execution_options(populate_existing=True)).scalar_one()
                binding = self._bindings.current_binding(
                    session, verified_owner_id, agent_id=row.agent_id,
                    network_id=row.network_id, lock=True)
                # An exact observation repeat is idempotent: return its recorded
                # outcome and replay nothing. A changed reuse of the same key is
                # refused, so an uncertain result is never hidden or re-applied.
                existing = session.execute(select(RemovalObservationRow).where(
                    RemovalObservationRow.owner_id == verified_owner_id,
                    RemovalObservationRow.observation_key == observation.observation_key,
                )).scalar_one_or_none()
                if existing is not None:
                    if self._observation_identical(existing, observation):
                        # Return the recorded outcome of the original observation, not
                        # the later derived state, and replay nothing.
                        session.commit()
                        return ReconcileOutcome(request_id=row.request_id, accepted=bool(existing.matched),
                                                denial_code=existing.denial_code,
                                                state=existing.derived_state or state.state,
                                                reason=existing.derived_reason or state.reason,
                                                view=self._view(session, row))
                    raise RemovalError("this observation key was already used with different content")
                denial = self._denial_code(row, state, observation, binding)
                now = self._clock()
                if denial is not None:
                    self._record_observation(session, row, observation, matched=False,
                                             contradictory=False, denial_code=denial, now=now,
                                             derived_state=state.state, derived_reason=state.reason)
                    session.commit()
                    return ReconcileOutcome(request_id=row.request_id, accepted=False, denial_code=denial,
                                            state=state.state, reason=state.reason,
                                            view=self._view(session, row))
                new_state, reason, evidenced_signer, evidenced_policy = self._derive(row, observation)
                if state.state == "CONFIRMED":
                    # The confirmed removal is sticky. A later observation that does
                    # not re-confirm the exact same evidenced target, including one
                    # that omits the evidence, is retained as a contradiction and
                    # never replaces the confirmed signer.
                    conflict = self._confirms_a_different_target(
                        state, observation, evidenced_signer, evidenced_policy)
                    self._record_observation(session, row, observation, matched=True,
                                             contradictory=conflict, denial_code=None, now=now,
                                             derived_state=state.state, derived_reason=state.reason)
                    if conflict:
                        state.contradictory = True
                        state.updated_at = now
                    session.commit()
                    return ReconcileOutcome(request_id=row.request_id, accepted=True, denial_code=None,
                                            state=state.state, reason=state.reason,
                                            view=self._view(session, row))
                observation_id = self._record_observation(session, row, observation, matched=True,
                                                          contradictory=False, denial_code=None, now=now,
                                                          derived_state=new_state, derived_reason=reason)
                state.state = new_state
                state.reason = reason
                state.evidenced_signer = evidenced_signer
                state.evidenced_policy = evidenced_policy
                state.last_observation_id = observation_id
                state.updated_at = now
                session.commit()
                return ReconcileOutcome(request_id=row.request_id, accepted=True, denial_code=None,
                                        state=state.state, reason=state.reason,
                                        view=self._view(session, row))
            except SQLAlchemyError:
                session.rollback()
                raise
            except RemovalError:
                session.rollback()
                raise

    # -------------------------------------------------------------------- read

    def read_removal(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str | None = None,
        wallet_id: str | None = None,
        network_id: str | None = None,
    ) -> list[RemovalView]:
        """Expose the owner-scoped durable removal records, oldest first.

        Another owner sees nothing. Broad retrieval returns every owner record,
        optionally filtered by agent, wallet or network.
        """
        with self._factory() as session:
            statement = select(RemovalRequestRow).where(RemovalRequestRow.owner_id == verified_owner_id)
            if agent_id is not None:
                statement = statement.where(RemovalRequestRow.agent_id == agent_id)
            if wallet_id is not None:
                statement = statement.where(RemovalRequestRow.wallet_id == wallet_id)
            if network_id is not None:
                statement = statement.where(RemovalRequestRow.network_id == network_id)
            rows = session.execute(
                statement.order_by(RemovalRequestRow.requested_at, RemovalRequestRow.request_id)).scalars().all()
            return [self._view(session, row) for row in rows]

    # ----------------------------------------------------- local P30 enforcement

    def submission_denial(
        self,
        session: Session,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
    ) -> list[str]:
        """The derived removal reasons that deny a new agent submission.

        The lookup reads the persisted state rows inside the caller's
        transaction, so it observes every committed removal and never a
        caller-supplied value. A record for another owner, agent, wallet or
        network is never returned.
        """
        rows = session.execute(select(RemovalStateRow).where(
            RemovalStateRow.owner_id == verified_owner_id,
            RemovalStateRow.agent_id == agent_id,
            RemovalStateRow.wallet_id == wallet_id,
            RemovalStateRow.network_id == network_id,
            RemovalStateRow.state.in_(DENYING_STATES),
        )).scalars().all()
        return sorted({DENIAL_REASON[row.state] for row in rows})

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _denial_code(
        row: RemovalRequestRow,
        state: RemovalStateRow,
        observation: RemovalObservation,
        binding: WalletBinding | None,
    ) -> str | None:
        if binding is None or binding.wallet_id != row.wallet_id:
            return "STALE_WALLET_BINDING"
        if (observation.agent_id, observation.wallet_id, observation.network_id) != (
                row.agent_id, row.wallet_id, row.network_id):
            return "OBSERVATION_IDENTITY_MISMATCH"
        if parse_utc(observation.observed_at) < state.updated_at:
            return "STALE_OBSERVATION"
        if (row.signer_identity is not None and observation.signer_identity is not None
                and row.signer_identity != observation.signer_identity):
            return "WRONG_SIGNER"
        if (row.policy_identity is not None and observation.policy_identity is not None
                and row.policy_identity != observation.policy_identity):
            return "WRONG_POLICY"
        return None

    @staticmethod
    def _observation_identical(existing: RemovalObservationRow, observation: RemovalObservation) -> bool:
        """True when a repeated observation key carries the same material content."""
        return (
            existing.request_id == observation.request_id
            and existing.observed_state == observation.observed_state
            and existing.agent_id == observation.agent_id
            and existing.wallet_id == observation.wallet_id
            and existing.network_id == observation.network_id
            and existing.signer_identity == observation.signer_identity
            and existing.policy_identity == observation.policy_identity
            and existing.observed_at == parse_utc(observation.observed_at)
        )

    @staticmethod
    def _confirms_a_different_target(
        state: RemovalStateRow, observation: RemovalObservation,
        evidenced_signer: str | None, evidenced_policy: str | None,
    ) -> bool:
        """True when a later observation contradicts an already confirmed removal.

        The later evidenced target must equal the confirmed target exactly,
        including when the later observation omits the signer or policy evidence.
        """
        if observation.observed_state != "CONFIRMED":
            return True
        if evidenced_signer != state.evidenced_signer:
            return True
        if evidenced_policy != state.evidenced_policy:
            return True
        return False

    @staticmethod
    def _derive(
        row: RemovalRequestRow, observation: RemovalObservation,
    ) -> tuple[str, str, str | None, str | None]:
        if observation.observed_state != "CONFIRMED":
            return observation.observed_state, f"OBSERVED_{observation.observed_state}", None, None
        signer = row.signer_identity or observation.signer_identity
        policy = row.policy_identity or observation.policy_identity
        if signer is None and policy is None:
            # Unknown signer and policy evidence can never fabricate confirmation.
            return "UNKNOWN", "SIGNER_EVIDENCE_UNKNOWN", None, None
        return "CONFIRMED", "PROVIDER_REMOVAL_CONFIRMED", signer, policy

    def _ensure_state(self, session: Session, row: RemovalRequestRow, now: dt.datetime) -> None:
        session.execute(pg_insert(RemovalStateRow).values(
            request_id=row.request_id, owner_id=row.owner_id, agent_id=row.agent_id,
            wallet_id=row.wallet_id, network_id=row.network_id, state="REQUESTED",
            reason="OWNER_REQUESTED", evidenced_signer=None, evidenced_policy=None,
            contradictory=False, last_observation_id=None, updated_at=now,
        ).on_conflict_do_nothing(index_elements=["request_id"]))
        session.flush()

    @staticmethod
    def _record_observation(
        session: Session,
        row: RemovalRequestRow,
        observation: RemovalObservation,
        *,
        matched: bool,
        contradictory: bool,
        denial_code: str | None,
        now: dt.datetime,
        derived_state: str,
        derived_reason: str,
    ) -> uuid.UUID:
        observation_id = uuid.uuid4()
        session.add(RemovalObservationRow(
            observation_id=observation_id, request_id=row.request_id, owner_id=row.owner_id,
            observation_key=observation.observation_key, observed_state=observation.observed_state,
            agent_id=observation.agent_id, wallet_id=observation.wallet_id,
            network_id=observation.network_id, signer_identity=observation.signer_identity,
            policy_identity=observation.policy_identity, matched=matched, contradictory=contradictory,
            denial_code=denial_code, derived_state=derived_state, derived_reason=derived_reason,
            provenance=observation.provenance.model_dump(mode="json"),
            observed_at=parse_utc(observation.observed_at), created_at=now,
        ))
        session.flush()
        return observation_id

    def _view(self, session: Session, row: RemovalRequestRow) -> RemovalView:
        state = session.execute(select(RemovalStateRow).where(
            RemovalStateRow.request_id == row.request_id)).scalar_one_or_none()
        denied = session.execute(select(func.count()).select_from(RemovalObservationRow).where(
            RemovalObservationRow.request_id == row.request_id,
            RemovalObservationRow.matched.is_(False))).scalar_one()
        last = session.execute(select(RemovalObservationRow).where(
            RemovalObservationRow.request_id == row.request_id,
        ).order_by(RemovalObservationRow.sequence.desc()).limit(1)).scalar_one_or_none()
        return RemovalView(
            request_id=row.request_id, owner_id=row.owner_id, agent_id=row.agent_id,
            wallet_id=row.wallet_id, network_id=row.network_id,
            state=state.state if state is not None else "REQUESTED",
            reason=state.reason if state is not None else "OWNER_REQUESTED",
            request_key=row.request_key, signer_identity=row.signer_identity,
            policy_identity=row.policy_identity,
            evidenced_signer=state.evidenced_signer if state is not None else None,
            evidenced_policy=state.evidenced_policy if state is not None else None,
            contradictory=bool(state.contradictory) if state is not None else False,
            denied_observations=int(denied),
            request_provenance=row.provenance,
            last_observation_state=last.observed_state if last is not None else None,
            last_observation_provenance=last.provenance if last is not None else None,
            requested_at=_iso(row.requested_at),
            updated_at=_iso(state.updated_at) if state is not None else _iso(row.created_at),
        )
