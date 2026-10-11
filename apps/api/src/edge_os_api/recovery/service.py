"""RecoveryService: durable original-action recovery and controlled reconciliation.

Recovery reopens the original saved P23 intent, queue entry, attempt and claim by
owner and exact action, then reconciles controlled, labelled local outcome
evidence for that same action through the accepted P22 `AdmissionService`. It
never submits, never re-signs and never creates a second economic action.

The service is idempotent and crash-safe. A durable per-action case records the
frozen references and the applied outcome. A re-delivered outcome is applied to
the P22 ledger once, and an action already settled in P22 is converged in the P23
queue without another reconciliation. Unknown, missing, malformed or unqualified
evidence keeps the P22 reservations and the exclusive claim in force.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.service import AdmissionService
from edge_os_api.admission.types import IdentityBinding, parse_utc
from edge_os_api.execution.models import ClaimRow, IntentRow, QueueRow, SubmissionAttemptRow
from edge_os_api.execution.service import ExecutionService
from edge_os_api.execution.types import QueueEntryView
from edge_os_api.recovery.models import RecoveryCaseRow, RecoveryEvidenceRow
from edge_os_api.recovery.types import (
    OutcomeEvidence,
    RecoveryCaseView,
    RecoveryError,
    RecoveryEvidenceView,
    RecoveryResult,
)

# P22 receipt outcome -> the local transport code the accepted P23 queue mapping uses.
_OUTCOME_TO_TRANSPORT = {
    "CONFIRMED": "CONFIRMED",
    "REVERTED": "REVERTED",
    "PREBROADCAST_DENIED": "DEFINITELY_UNSENT",
    "SUBMISSION_UNKNOWN": "SUBMISSION_POSSIBLE",
}
# P22 receipt outcome -> the settled P22 decision status it must produce.
_OUTCOME_TO_DECISION = {
    "CONFIRMED": "CONFIRMED",
    "REVERTED": "REVERTED",
    "PREBROADCAST_DENIED": "DENIED",
    "SUBMISSION_UNKNOWN": "SUBMISSION_UNKNOWN",
}
# A settled P22 decision cannot be re-reconciled; recovery converges the queue instead.
_SETTLED_DECISIONS = {"CONFIRMED", "REVERTED", "DENIED", "CANCELLED", "BREACHED"}
# The converged P23 queue state -> the recovery case state shown to the owner.
_QUEUE_TO_CASE = {
    "SUBMITTED_CONFIRMED": "CONFIRMED",
    "SUBMITTED_REVERTED": "REVERTED",
    "DENIED_UNSENT": "DENIED_UNSENT",
    "SUBMITTED_UNKNOWN": "UNKNOWN",
    "BREACHED": "BREACHED",
    "RECONCILE_MISMATCH": "RECONCILE_MISMATCH",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


def _case_lock(session: Session, owner: uuid.UUID, action_id: str) -> None:
    """Serialize recovery for one owner and action with a transaction-scoped advisory lock.

    The key namespace is distinct from the P22 admission wallet lock and the P23
    execution wallet lock, so a recovery never inverts an order those two use.
    """
    digest = hashlib.sha256(f"p24-recovery:{owner}:{action_id}".encode()).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    session.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": int4(0), "b": int4(4)})


@dataclass
class _Context:
    intent: IntentRow
    queue: QueueRow | None
    attempt: SubmissionAttemptRow | None
    claim: ClaimRow | None
    decision_status: str | None


# A queue state that proves the original action reached a submission-capable
# step. A merely admitted or queued action has not been attempted.
_SUBMISSION_OWNED_STATES = {"CLAIMED", "SUBMITTED_UNKNOWN", "BREACHED", "RECONCILE_MISMATCH"}


def _submission_owned(context: _Context) -> bool:
    """True when the original action reached a submission-capable state.

    Recovery settles only an action that was actually attempted: it has a saved
    P23 submission attempt, an active exclusive claim, a submission-owned P22
    decision, or a submission-owned queue state. An action that was only admitted
    or queued has no original attempt to recover.
    """
    if context.attempt is not None:
        return True
    if context.claim is not None:
        return True
    if context.decision_status == "SUBMISSION_UNKNOWN":
        return True
    return context.queue is not None and context.queue.state in _SUBMISSION_OWNED_STATES


class RecoveryService:
    def __init__(self, session_factory: sessionmaker[Session], admission: AdmissionService,
                 execution: ExecutionService, *, clock=None) -> None:
        self._factory = session_factory
        self._admission = admission
        self._execution = execution
        self._clock = clock or _utc_now

    # ------------------------------------------------------------------ recover

    def reconcile(
        self,
        verified_owner_id: uuid.UUID,
        action_id: str,
        evidence: OutcomeEvidence,
    ) -> RecoveryResult:
        """Reconcile controlled local outcome evidence for one original action.

        Foreign or altered evidence is rejected and recorded. A re-delivered
        outcome is a no-op. An action already settled in P22 is converged in the
        P23 queue without another reconciliation. Accounting is applied once.
        """
        if evidence.action_id != action_id:
            raise RecoveryError("evidence action_id does not match the requested action")
        with self._factory() as session:
            try:
                _case_lock(session, verified_owner_id, action_id)
                context = self._load_context(session, verified_owner_id, action_id)
                if context is None:
                    raise RecoveryError(f"no saved action {action_id} for this owner")
                case = self._ensure_case(session, verified_owner_id, context)
                now = self._clock()

                fingerprint = evidence.fingerprint()
                existing = self._evidence(session, verified_owner_id, action_id, fingerprint)
                # A recorded outcome is never re-applied. An accepted record is a
                # duplicate no-op; a rejected record returns its recorded rejection
                # instead of escalating on replay. The economic content therefore
                # stays applied at most once.
                if existing is not None and existing.state in {"ACCEPTED", "REJECTED"}:
                    session.commit()
                    return RecoveryResult(case=self._case_view(session, case), applied=False,
                                          duplicate=True, decision_status=context.decision_status or "",
                                          detail=existing.rejection_reason)

                # Foreign or altered evidence is rejected before it can reach the
                # P22 ledger.
                reference = self._reference_error(context, evidence)
                if reference is not None:
                    if existing is None:
                        existing = self._record_evidence(session, case, evidence, "REJECTED", reference, now)
                    existing.state = "REJECTED"
                    existing.rejection_reason = reference
                    case.state = "DISCREPANCY"
                    case.blocking_reason = f"EVIDENCE_REJECTED:{reference}"
                    case.updated_at = now
                    session.commit()
                    return RecoveryResult(case=self._case_view(session, case), applied=False,
                                          duplicate=False, decision_status=context.decision_status or "",
                                          detail=reference)

                # Recovery only settles an action that actually reached a
                # submission-capable original state. An admitted but never
                # attempted action has nothing to reconcile, so it is blocked
                # rather than confirmed.
                if not _submission_owned(context):
                    if existing is None:
                        existing = self._record_evidence(
                            session, case, evidence, "REJECTED", "NO_SUBMISSION_ATTEMPT", now)
                    existing.state = "REJECTED"
                    existing.rejection_reason = "NO_SUBMISSION_ATTEMPT"
                    case.state = "NO_SUBMISSION_ATTEMPT"
                    case.blocking_reason = "NO_SUBMISSION_ATTEMPT"
                    case.updated_at = now
                    session.commit()
                    return RecoveryResult(case=self._case_view(session, case), applied=False,
                                          duplicate=False, decision_status=context.decision_status or "",
                                          detail="NO_SUBMISSION_ATTEMPT")

                if existing is None:
                    existing = self._record_evidence(session, case, evidence, "PENDING", None, now)

                decision_status = context.decision_status
                expected = _OUTCOME_TO_DECISION[evidence.outcome]

                # An outcome that contradicts an already-settled action is a visible
                # discrepancy, never a false confirmation. This applies on a first
                # delivery and on a resumed delivery after a crash.
                if decision_status in _SETTLED_DECISIONS and decision_status != expected:
                    return self._block(session, case, existing,
                                       f"P22_SETTLED_MISMATCH:{decision_status}", decision_status, now)

                if decision_status in _SETTLED_DECISIONS:
                    # Crash convergence: P22 settled but the P23 queue is stale. The
                    # saved P22 receipt is authoritative, so the evidence actuals
                    # must match it before the queue converges.
                    mismatch = self._terminal_receipt_mismatch(
                        verified_owner_id, action_id, evidence)
                    if mismatch is not None:
                        return self._block(session, case, existing, mismatch, decision_status, now)
                    effective_status, effective_reason = decision_status, None
                else:
                    reconciliation = self._admission.reconcile(
                        verified_owner_id, action_id, evidence.receipt())
                    effective_status = reconciliation.decision_status
                    effective_reason = reconciliation.reason
                    # Close the interleaving: a concurrent P22 service can commit a
                    # terminal settlement between the initial read and this call. The
                    # authoritative terminal result must match the delivered evidence
                    # before acceptance, or the action would report one outcome while
                    # P22 retains incompatible actuals. A genuine breach is not a
                    # mismatch; it converges to the blocked BREACHED state.
                    if effective_status in _SETTLED_DECISIONS and effective_status != "BREACHED":
                        if effective_status != expected:
                            return self._block(session, case, existing,
                                               f"P22_SETTLED_MISMATCH:{effective_status}",
                                               effective_status, now)
                        mismatch = self._terminal_receipt_mismatch(
                            verified_owner_id, action_id, evidence)
                        if mismatch is not None:
                            return self._block(session, case, existing, mismatch, effective_status, now)

                queue = self._execution.converge_reconciled_outcome(
                    verified_owner_id, action_id=action_id,
                    outcome_code=_OUTCOME_TO_TRANSPORT[evidence.outcome], detail=evidence.detail,
                    decision_status=effective_status, reconciliation_reason=effective_reason,
                    event_at=now)

                existing.state = "ACCEPTED"
                existing.rejection_reason = None
                case.state = _QUEUE_TO_CASE[queue.state]
                case.blocking_reason = queue.blocking_reason
                case.decision_status = effective_status
                case.queue_state = queue.state
                case.claim_held = self._claim_held(session, verified_owner_id, context.intent)
                case.delayed_exit = queue.delayed_exit
                case.updated_at = now
                if case.state in {"CONFIRMED", "REVERTED", "DENIED_UNSENT", "UNKNOWN"}:
                    case.reconciled_at = now
                session.commit()
                return RecoveryResult(case=self._case_view(session, case), applied=True,
                                      duplicate=False, decision_status=effective_status)
            except SQLAlchemyError:
                session.rollback()
                raise

    # ------------------------------------------------------------------- status

    def status(self, verified_owner_id: uuid.UUID, action_id: str) -> RecoveryCaseView:
        """Expose the owner-scoped recovery status for one original action."""
        with self._factory() as session:
            try:
                _case_lock(session, verified_owner_id, action_id)
                context = self._load_context(session, verified_owner_id, action_id)
                if context is None:
                    raise RecoveryError(f"no saved action {action_id} for this owner")
                case = self._ensure_case(session, verified_owner_id, context)
                self._refresh_case(session, case, context)
                session.commit()
                return self._case_view(session, case)
            except SQLAlchemyError:
                session.rollback()
                raise

    def list_cases(self, verified_owner_id: uuid.UUID) -> list[RecoveryCaseView]:
        """Expose every owner-scoped recovery case, newest first."""
        with self._factory() as session:
            rows = session.execute(select(RecoveryCaseRow).where(
                RecoveryCaseRow.owner_id == verified_owner_id,
            ).order_by(RecoveryCaseRow.opened_at.desc(),
                       RecoveryCaseRow.case_id.desc())).scalars().all()
            return [self._case_view(session, row) for row in rows]

    # ------------------------------------------------------------------ helpers

    def _load_context(self, session: Session, owner: uuid.UUID, action_id: str) -> _Context | None:
        intent = session.execute(select(IntentRow).where(
            IntentRow.owner_id == owner, IntentRow.action_id == action_id)).scalar_one_or_none()
        if intent is None:
            return None
        queue = session.execute(select(QueueRow).where(
            QueueRow.owner_id == owner, QueueRow.action_id == action_id)).scalar_one_or_none()
        attempt = session.execute(select(SubmissionAttemptRow).where(
            SubmissionAttemptRow.owner_id == owner, SubmissionAttemptRow.action_id == action_id,
        ).order_by(SubmissionAttemptRow.started_at.desc(),
                   SubmissionAttemptRow.attempt_id.desc()).limit(1)).scalar_one_or_none()
        # The exclusive claim is keyed by the requested action, not just the wallet.
        # Another action's active claim must not prove this action was submitted.
        claim = session.execute(select(ClaimRow).where(
            ClaimRow.owner_id == owner, ClaimRow.agent_id == intent.agent_id,
            ClaimRow.wallet_id == intent.wallet_id, ClaimRow.network_id == intent.network_id,
            ClaimRow.action_id == action_id, ClaimRow.released_at.is_(None))).scalar_one_or_none()
        decisions = self._admission.retrieve_decisions(owner, action_id=action_id)
        decision_status = decisions[0].status if decisions else None
        return _Context(intent=intent, queue=queue, attempt=attempt, claim=claim,
                        decision_status=decision_status)

    @staticmethod
    def _reference_error(context: _Context, evidence: OutcomeEvidence) -> str | None:
        intent = context.intent
        expected_binding = IdentityBinding(
            agent_id=intent.agent_id, wallet_id=intent.wallet_id, network_id=intent.network_id,
            strategy_revision=intent.revision_id, mandate_id=intent.mandate_id)
        if evidence.binding != expected_binding:
            return "FOREIGN_IDENTITY"
        if evidence.operation != intent.operation:
            return "OPERATION_MISMATCH"
        if evidence.revision_id != intent.revision_id:
            return "REVISION_MISMATCH"
        if evidence.policy_binding != intent.policy_binding:
            return "POLICY_MISMATCH"
        if evidence.payload_hash != intent.payload_hash:
            return "PAYLOAD_MISMATCH"
        return None

    def _ensure_case(self, session: Session, owner: uuid.UUID,
                     context: _Context) -> RecoveryCaseRow:
        case = session.execute(select(RecoveryCaseRow).where(
            RecoveryCaseRow.owner_id == owner,
            RecoveryCaseRow.action_id == context.intent.action_id)).scalar_one_or_none()
        if case is not None:
            return case
        intent = context.intent
        now = self._clock()
        case = RecoveryCaseRow(
            case_id=uuid.uuid4(), owner_id=owner, action_id=intent.action_id,
            agent_id=intent.agent_id, wallet_id=intent.wallet_id, network_id=intent.network_id,
            operation=intent.operation, revision_id=intent.revision_id,
            policy_binding=intent.policy_binding, payload_hash=intent.payload_hash,
            state="OPEN", blocking_reason=None, decision_status=context.decision_status or "UNKNOWN",
            queue_state=context.queue.state if context.queue is not None else None,
            claim_held=context.claim is not None,
            delayed_exit=bool(context.queue is not None and context.queue.state in {"CLAIMED", "SUBMITTED_UNKNOWN"}),
            opened_at=now, updated_at=now, reconciled_at=None)
        session.add(case)
        session.flush()
        return case

    def _refresh_case(self, session: Session, case: RecoveryCaseRow, context: _Context) -> None:
        if case.state in {"OPEN", "UNKNOWN"}:
            decision_status = context.decision_status or "UNKNOWN"
            queue = context.queue
            case.decision_status = decision_status
            case.queue_state = queue.state if queue is not None else None
            case.claim_held = context.claim is not None
            case.delayed_exit = bool(queue is not None and queue.state in {"CLAIMED", "SUBMITTED_UNKNOWN"})
            if queue is not None and queue.state in _QUEUE_TO_CASE:
                case.state = _QUEUE_TO_CASE[queue.state]
            elif decision_status == "SUBMISSION_UNKNOWN":
                case.state = "UNKNOWN"
            case.blocking_reason = queue.blocking_reason if queue is not None else None
            case.updated_at = self._clock()

    def _record_evidence(self, session: Session, case: RecoveryCaseRow, evidence: OutcomeEvidence,
                         state: str, rejection_reason: str | None, now: dt.datetime) -> RecoveryEvidenceRow:
        row = session.execute(pg_insert(RecoveryEvidenceRow).values(
            evidence_id=uuid.uuid4(), case_id=case.case_id, owner_id=case.owner_id,
            action_id=case.action_id, fingerprint=evidence.fingerprint(), outcome=evidence.outcome,
            state=state, rejection_reason=rejection_reason, source_ref=evidence.source_ref,
            observed_at=parse_utc(evidence.observed_at),
            content=evidence.model_dump(mode="json"), created_at=now,
        ).on_conflict_do_nothing(
            index_elements=["owner_id", "action_id", "fingerprint"],
        ).returning(RecoveryEvidenceRow.evidence_id)).scalar_one_or_none()
        if row is None:
            # A competing recoverer inserted the same fingerprint; reuse its row.
            session.flush()
            return self._evidence(session, case.owner_id, case.action_id, evidence.fingerprint())
        session.flush()
        return self._evidence(session, case.owner_id, case.action_id, evidence.fingerprint())

    def _evidence(self, session: Session, owner: uuid.UUID, action_id: str,
                  fingerprint: str) -> RecoveryEvidenceRow | None:
        return session.execute(select(RecoveryEvidenceRow).where(
            RecoveryEvidenceRow.owner_id == owner, RecoveryEvidenceRow.action_id == action_id,
            RecoveryEvidenceRow.fingerprint == fingerprint)).scalar_one_or_none()

    @staticmethod
    def _claim_held(session: Session, owner: uuid.UUID, intent: IntentRow) -> bool:
        return session.execute(select(ClaimRow.claim_id).where(
            ClaimRow.owner_id == owner, ClaimRow.agent_id == intent.agent_id,
            ClaimRow.wallet_id == intent.wallet_id, ClaimRow.network_id == intent.network_id,
            ClaimRow.released_at.is_(None)).limit(1)).scalar_one_or_none() is not None

    @staticmethod
    def _amount_dict(amount) -> dict[str, object] | None:
        if amount is None:
            return None
        return {"asset_id": amount.asset_id, "raw": amount.raw, "decimals": amount.decimals}

    def _block(self, session: Session, case: RecoveryCaseRow, existing: RecoveryEvidenceRow,
               reason: str, decision_status: str, now: dt.datetime) -> RecoveryResult:
        """Record a blocked discrepancy and leave the queue, claim and ledger unchanged."""
        existing.state = "REJECTED"
        existing.rejection_reason = reason
        case.state = "DISCREPANCY"
        case.blocking_reason = reason
        case.decision_status = decision_status
        case.updated_at = now
        session.commit()
        return RecoveryResult(case=self._case_view(session, case), applied=False, duplicate=False,
                              decision_status=decision_status, detail=reason)

    def _terminal_receipt_mismatch(self, owner: uuid.UUID, action_id: str,
                                   evidence: OutcomeEvidence) -> str | None:
        """Compare evidence actuals with the saved P22 terminal receipt.

        A settled P22 receipt is authoritative. Crash convergence must not accept
        evidence whose outcome or actual input, output or gas differs from that
        receipt, so a mismatch stays visible and blocked.
        """
        receipts = [row for row in self._admission.retrieve_receipts(
            owner, action_id=action_id) if row.outcome == evidence.outcome]
        if not receipts:
            return "P22_RECEIPT_MISSING"
        saved = receipts[-1].content
        for name in ("actual_input", "actual_output", "actual_gas"):
            if saved.get(name) != self._amount_dict(getattr(evidence, name)):
                return f"P22_RECEIPT_MISMATCH:{name}"
        return None

    def _case_view(self, session: Session, case: RecoveryCaseRow) -> RecoveryCaseView:
        evidence = session.execute(select(RecoveryEvidenceRow).where(
            RecoveryEvidenceRow.owner_id == case.owner_id,
            RecoveryEvidenceRow.action_id == case.action_id,
        ).order_by(RecoveryEvidenceRow.created_at, RecoveryEvidenceRow.evidence_id)).scalars().all()
        return RecoveryCaseView(
            case_id=case.case_id, owner_id=case.owner_id, action_id=case.action_id,
            agent_id=case.agent_id, wallet_id=case.wallet_id, network_id=case.network_id,
            operation=case.operation, revision_id=case.revision_id,
            policy_binding=case.policy_binding, payload_hash=case.payload_hash,
            state=case.state, blocking_reason=case.blocking_reason,
            decision_status=case.decision_status, queue_state=case.queue_state,
            claim_held=bool(case.claim_held), delayed_exit=bool(case.delayed_exit),
            opened_at=_iso(case.opened_at), updated_at=_iso(case.updated_at),
            reconciled_at=_iso(case.reconciled_at) if case.reconciled_at else None,
            evidence=[RecoveryEvidenceView(
                evidence_id=row.evidence_id, fingerprint=row.fingerprint, outcome=row.outcome,
                state=row.state, rejection_reason=row.rejection_reason, source_ref=row.source_ref,
                observed_at=_iso(row.observed_at), created_at=_iso(row.created_at)) for row in evidence])
