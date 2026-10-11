"""ExecutionService: bounded evaluation, exact intent admission, exclusive submission.

The service persists a decision before any intent, links one exact immutable
intent to that decision, admits it through the accepted P22 `AdmissionService`,
holds one durable exclusive claim per wallet and network, revalidates immediately
before a labelled local fixture call, and records immutable outcome evidence.

It reuses the compiler and the admission service through their public
interfaces. It adds no scheduler, provider call, signing path or wallet
authority.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.accounting import ACQUISITIONS
from edge_os_api.admission.service import AdmissionService
from edge_os_api.admission.types import (
    ActionIntent,
    ActionInput,
    ActionReceipt,
    AdmissionContext,
    AllowanceCap,
    ApprovalSnapshot,
    AssetAmount,
    IdentityBinding,
    parse_utc,
)
from edge_os_api.execution.evaluator import evaluate
from edge_os_api.execution.models import (
    ClaimRow,
    DecisionRow,
    IntentRow,
    QueueRow,
    SubmissionAttemptRow,
)
from edge_os_api.execution.transport import (
    FixtureAcknowledgementLost,
    PreparedSubmission,
    TransportOutcome,
    SubmissionTransport,
)
from edge_os_api.execution.types import (
    DECISION_STATUSES,
    ActionQuote,
    EnqueueResult,
    EvaluationInputs,
    ExecutionError,
    FrozenRevision,
    HealthView,
    IntentPlan,
    IntentTerms,
    QueueEntryView,
    RevalidationOutcome,
    RuleEvaluation,
    SavedDecisionView,
    SubmissionEvidence,
    TickResult,
    canonical_action_id,
    canonical_hash,
    canonical_intent_id,
    utc_iso,
)

_PRIORITY = {"EXIT": 0, "ENTRY": 1}
_TERMINAL_QUEUE = {
    "SUBMITTED_CONFIRMED", "SUBMITTED_REVERTED", "REVALIDATION_DENIED",
    "ADMISSION_DENIED", "DENIED_UNSENT",
}
_DELAYED_EXIT_STATES = {"CLAIMED", "SUBMITTED_UNKNOWN"}
# Local submission-freshness bounds (local assumptions, not live thresholds). An
# intent is valid only until the next scheduled decision, and the submission-time
# context snapshot must be current. The accepted schedule uses five-minute buckets.
_INTENT_VALIDITY = dt.timedelta(minutes=5)
_CONTEXT_FRESHNESS = dt.timedelta(minutes=5)
# The settled P22 admission status a transport outcome must reconcile to.
_EXPECTED_STATUS = {
    "DEFINITELY_UNSENT": "DENIED", "SUBMISSION_POSSIBLE": "SUBMISSION_UNKNOWN",
    "CONFIRMED": "CONFIRMED", "REVERTED": "REVERTED",
}
_QUEUE_BY_OUTCOME = {
    "DEFINITELY_UNSENT": "DENIED_UNSENT",
    "SUBMISSION_POSSIBLE": "SUBMITTED_UNKNOWN",
    "CONFIRMED": "SUBMITTED_CONFIRMED",
    "REVERTED": "SUBMITTED_REVERTED",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


def _wallet_lock(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str) -> None:
    """A per-wallet advisory lock for the execution claim and submission steps.

    The key is namespaced apart from the P22 admission wallet lock. Admission and
    reconciliation acquire their own lock in their own session; sharing a key
    across two live sessions in one process would deadlock. The execution lock
    protects claim acquisition, selection and attempt persistence only.
    """
    digest = hashlib.sha256(f"p23-execution:{owner}:{agent_id}:{wallet_id}:{network_id}".encode()).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    session.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": int4(0), "b": int4(4)})


def _cap_amount(cap: AllowanceCap) -> AssetAmount:
    return AssetAmount(asset_id=cap.asset_id, raw=cap.approved_raw, decimals=cap.decimals)


def _cap_for(approval: ApprovalSnapshot, asset_id: str) -> int | None:
    for cap in (approval.quote_allowance, approval.base_allowance, approval.gas):
        if cap.asset_id == asset_id:
            return cap.as_int()
    return None


class ExecutionService:
    def __init__(self, session_factory: sessionmaker[Session], admission: AdmissionService, *,
                 clock=None) -> None:
        self._factory = session_factory
        self._admission = admission
        self._clock = clock or _utc_now

    # ------------------------------------------------------------------ decision

    def evaluate_and_decide(
        self,
        verified_owner_id: uuid.UUID,
        revision: FrozenRevision,
        inputs: EvaluationInputs,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
    ) -> SavedDecisionView:
        outcome = evaluate(revision, inputs)
        if outcome.status not in DECISION_STATUSES:
            raise ExecutionError(f"unexpected decision status {outcome.status!r}")
        now = self._clock()
        row = DecisionRow(
            decision_id=uuid.uuid4(), owner_id=verified_owner_id, agent_id=agent_id,
            wallet_id=wallet_id, network_id=network_id, strategy_id=revision.strategy_id,
            revision_id=revision.revision_id, content_hash=revision.content_hash,
            manifest_hash=revision.manifest_hash, market_binding_id=revision.market_binding_id,
            decision_at=inputs.observed_at(), status=outcome.status, operation=outcome.operation,
            reasons=list(outcome.reasons),
            rule_results=[item.model_dump(mode="json") for item in outcome.rule_results],
            inputs_hash=outcome.inputs_hash, inputs=inputs.model_dump(mode="json"), created_at=now)
        with self._factory() as session:
            try:
                session.add(row)
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise
        return _decision_view(row)

    def retrieve_decisions(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str | None = None,
        wallet_id: str | None = None,
        network_id: str | None = None,
        limit: int = 100,
    ) -> list[SavedDecisionView]:
        with self._factory() as session:
            statement = select(DecisionRow).where(DecisionRow.owner_id == verified_owner_id)
            if agent_id is not None:
                statement = statement.where(DecisionRow.agent_id == agent_id)
            if wallet_id is not None:
                statement = statement.where(DecisionRow.wallet_id == wallet_id)
            if network_id is not None:
                statement = statement.where(DecisionRow.network_id == network_id)
            rows = session.execute(
                statement.order_by(DecisionRow.decision_at, DecisionRow.decision_id).limit(limit)
            ).scalars().all()
            return [_decision_view(row) for row in rows]

    # ------------------------------------------------------------------- enqueue

    def enqueue(
        self,
        verified_owner_id: uuid.UUID,
        decision_id: uuid.UUID,
        terms: IntentTerms,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> EnqueueResult:
        with self._factory() as session:
            try:
                decision = session.execute(select(DecisionRow).where(
                    DecisionRow.owner_id == verified_owner_id, DecisionRow.decision_id == decision_id,
                )).scalar_one_or_none()
                if decision is None:
                    raise ExecutionError(f"unknown decision {decision_id} for this owner")
                if decision.status != "SIGNAL":
                    raise ExecutionError(f"decision {decision_id} is {decision.status}, not SIGNAL")
                if decision.operation != terms.operation:
                    raise ExecutionError("intent operation does not match its decision")

                intent_id = canonical_intent_id(decision_id, terms.operation)
                action_id = canonical_action_id(decision_id, terms.operation)
                action_intent, review_hash, payload_hash = self._build_intent(decision, terms)

                existing = self._intent_by_id(session, verified_owner_id, intent_id)
                if existing is not None:
                    # A replay of the same decision must never create another
                    # economic action. A replay under changed meaning is refused,
                    # not silently replaced.
                    if existing.review_hash != review_hash:
                        session.rollback()
                        raise ExecutionError(
                            f"intent {intent_id} already exists under different meaning")
                    session.commit()
                    entry = self._queue_by_action(session, verified_owner_id, action_id)
                    return _enqueue_result(existing, entry, self._clock())

                admission = self._admission.admit_and_reserve(
                    verified_owner_id, action_intent, approval, context)
                now = self._clock()
                row = IntentRow(
                    intent_id=intent_id, owner_id=verified_owner_id, decision_id=decision_id,
                    action_id=action_id, review_hash=review_hash, agent_id=decision.agent_id,
                    wallet_id=decision.wallet_id, network_id=decision.network_id,
                    position_id=terms.position_id, operation=terms.operation,
                    revision_id=decision.revision_id, mandate_id=terms.mandate_id,
                    policy_binding=terms.policy_binding, payload_hash=payload_hash,
                    payload=action_intent.model_dump(mode="json"),
                    admission_status=admission.status, admission_reason=admission.reason, created_at=now)
                session.add(row)
                entry = QueueRow(
                    queue_id=uuid.uuid4(), owner_id=verified_owner_id, intent_id=intent_id,
                    action_id=action_id, decision_id=decision_id, agent_id=decision.agent_id,
                    wallet_id=decision.wallet_id, network_id=decision.network_id,
                    position_id=terms.position_id, operation=terms.operation,
                    priority=_PRIORITY[terms.operation],
                    state="QUEUED" if admission.status == "ADMITTED" else "ADMISSION_DENIED",
                    blocking_reason=None if admission.status == "ADMITTED" else admission.reason,
                    revalidation=None, enqueued_at=now, updated_at=now)
                session.add(entry)
                session.commit()
                return _enqueue_result(row, entry, now)
            except SQLAlchemyError:
                session.rollback()
                raise

    def _build_intent(self, decision: DecisionRow, terms: IntentTerms) -> tuple[ActionIntent, str, str]:
        binding = IdentityBinding(
            agent_id=decision.agent_id, wallet_id=decision.wallet_id,
            network_id=decision.network_id, strategy_revision=decision.revision_id,
            mandate_id=terms.mandate_id)
        base = {
            "decision_id": str(decision.decision_id), "operation": terms.operation,
            "position_id": terms.position_id, "policy_binding": terms.policy_binding,
            "binding": binding.model_dump(mode="json"),
            "quantity": terms.quantity.model_dump(mode="json"),
            "quote_input": terms.quote_input.model_dump(mode="json") if terms.quote_input else None,
            "expected_quote": terms.expected_quote.model_dump(mode="json") if terms.expected_quote else None,
            "mark": terms.mark.model_dump(mode="json") if terms.mark else None,
            "quote_status": terms.quote_status,
        }
        review_hash = canonical_hash(base)
        action_intent = ActionIntent(
            action_id=canonical_action_id(decision.decision_id, terms.operation), binding=binding,
            policy_binding=terms.policy_binding, position_id=terms.position_id,
            operation=terms.operation, review_hash=review_hash, quantity=terms.quantity,
            input=ActionInput(
                quote_asset_id=terms.quote_asset_id, quote_input=terms.quote_input, mark=terms.mark,
                quote_status=terms.quote_status, expected_quote=terms.expected_quote))
        payload_hash = canonical_hash(action_intent.model_dump(mode="json"))
        return action_intent, review_hash, payload_hash

    # ---------------------------------------------------------------------- tick

    def tick(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
        revision: FrozenRevision,
        inputs: EvaluationInputs,
        quote: ActionQuote | None,
        transport: SubmissionTransport,
        now: dt.datetime | None = None,
    ) -> TickResult:
        now = now or self._clock()
        prepared, intention, queue_id, attempt_id = self._begin_submission(
            verified_owner_id, agent_id, wallet_id, network_id, approval, context, revision, inputs,
            quote, transport, now)
        if isinstance(prepared, TickResult):
            return prepared

        # P22 submission-ownership guard. Atomically move the exact action from the
        # eligible ADMITTED state to submission-owned before any fixture call. If a
        # prior unknown, breach, cancellation or other change wins, make no call.
        ownership = self._admission.acquire_submission(verified_owner_id, intention.action_id)
        if ownership != "ACQUIRED":
            return self._abort_submission(
                verified_owner_id, agent_id, wallet_id, network_id, queue_id, attempt_id,
                ownership, now)

        try:
            outcome = transport.submit(prepared)
        except FixtureAcknowledgementLost:
            outcome = TransportOutcome(
                outcome="SUBMISSION_POSSIBLE",
                detail="fixture lost the acknowledgement after a possible send")

        return self._finish_submission(
            verified_owner_id, agent_id, wallet_id, network_id, queue_id, attempt_id,
            intention, approval, outcome, now)

    def _abort_submission(
        self, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
        queue_id: uuid.UUID, attempt_id: uuid.UUID, status: str, now: dt.datetime,
    ) -> TickResult:
        """A cancellation won the ownership transition: make no fixture call."""
        with self._factory() as session:
            try:
                _wallet_lock(session, owner, agent_id, wallet_id, network_id)
                entry = self._queue_by_id(session, owner, queue_id)
                assert entry is not None
                attempt = session.execute(select(SubmissionAttemptRow).where(
                    SubmissionAttemptRow.owner_id == owner,
                    SubmissionAttemptRow.attempt_id == attempt_id,
                ).with_for_update().execution_options(populate_existing=True)).scalar_one()
                attempt.state = "TERMINAL"
                attempt.outcome = "DEFINITELY_UNSENT"
                attempt.detail = f"SUBMISSION_NOT_OWNED:{status}"
                attempt.completed_at = now
                entry.state = "SUBMISSION_NOT_OWNED"
                entry.blocking_reason = f"SUBMISSION_NOT_OWNED:{status}"
                entry.updated_at = now
                claim = self._active_claim(session, owner, agent_id, wallet_id, network_id)
                if claim is not None:
                    claim.state = "RELEASED"
                    claim.released_at = now
                session.commit()
                return TickResult(status=entry.state, reason=entry.blocking_reason,
                                  selected_action_id=entry.action_id, queue_entry=_queue_view(entry, now))
            except SQLAlchemyError:
                session.rollback()
                raise

    def _begin_submission(
        self, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
        approval: ApprovalSnapshot, context: AdmissionContext, revision: FrozenRevision,
        inputs: EvaluationInputs, quote: ActionQuote | None, transport: SubmissionTransport,
        now: dt.datetime,
    ) -> tuple[TickResult | PreparedSubmission, ActionIntent | None, uuid.UUID | None, uuid.UUID | None]:
        with self._factory() as session:
            try:
                _wallet_lock(session, owner, agent_id, wallet_id, network_id)
                active = self._active_claim(session, owner, agent_id, wallet_id, network_id)
                if active is not None:
                    entry = self._queue_by_id(session, owner, active.queue_id)
                    reason = entry.blocking_reason if entry else "UNRESOLVED_PRIOR_ACTION"
                    session.commit()
                    return TickResult(status="BLOCKED_UNKNOWN", reason=reason or "UNRESOLVED_PRIOR_ACTION",
                                      selected_action_id=active.action_id), None, None, None

                entry = self._select_next(session, owner, agent_id, wallet_id, network_id)
                if entry is None:
                    session.commit()
                    return TickResult(status="IDLE"), None, None, None

                intent_row = self._intent_by_action(session, owner, entry.action_id)
                if intent_row is None:
                    raise ExecutionError(f"queue entry {entry.action_id} has no intent")
                action_intent = ActionIntent.model_validate(intent_row.payload)

                revalidation = self._revalidate(
                    session, owner, entry, intent_row, action_intent, approval, context, revision,
                    inputs, quote, now)
                entry.revalidation = revalidation.model_dump(mode="json")
                entry.updated_at = now
                if revalidation.status == "DENIED":
                    entry.state = "REVALIDATION_DENIED"
                    entry.blocking_reason = revalidation.reason
                    session.commit()
                    return (TickResult(status="REVALIDATION_DENIED", reason=revalidation.reason,
                                       selected_action_id=entry.action_id, queue_entry=_queue_view(entry, now)),
                            None, None, None)

                claim = ClaimRow(
                    claim_id=uuid.uuid4(), owner_id=owner, agent_id=agent_id, wallet_id=wallet_id,
                    network_id=network_id, queue_id=entry.queue_id, action_id=entry.action_id,
                    state="ACTIVE")
                session.add(claim)
                entry.state = "CLAIMED"
                entry.updated_at = now
                attempt = SubmissionAttemptRow(
                    attempt_id=uuid.uuid4(), owner_id=owner, queue_id=entry.queue_id,
                    action_id=entry.action_id, agent_id=agent_id, wallet_id=wallet_id,
                    network_id=network_id, transport_id=transport.transport_id,
                    payload_hash=intent_row.payload_hash, state="IN_FLIGHT",
                    content={"transport": transport.transport_id, "payload_hash": intent_row.payload_hash},
                    started_at=now, completed_at=None)
                session.add(attempt)
                session.flush()
                attempt_id = attempt.attempt_id
                prepared = PreparedSubmission(
                    action_id=entry.action_id, owner_id=str(owner), wallet_id=wallet_id,
                    network_id=network_id, operation=entry.operation, payload_hash=intent_row.payload_hash)
                session.commit()
                return prepared, action_intent, entry.queue_id, attempt_id
            except SQLAlchemyError:
                session.rollback()
                raise

    def _finish_submission(
        self, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
        queue_id: uuid.UUID, attempt_id: uuid.UUID, action_intent: ActionIntent,
        approval: ApprovalSnapshot, outcome: TransportOutcome, now: dt.datetime,
    ) -> TickResult:
        with self._factory() as session:
            try:
                _wallet_lock(session, owner, agent_id, wallet_id, network_id)
                entry = self._queue_by_id(session, owner, queue_id)
                assert entry is not None
                attempt = session.execute(select(SubmissionAttemptRow).where(
                    SubmissionAttemptRow.owner_id == owner,
                    SubmissionAttemptRow.attempt_id == attempt_id,
                ).with_for_update().execution_options(populate_existing=True)).scalar_one()
                receipt = self._receipt(action_intent, approval, outcome)
                reconciliation = self._admission.reconcile(owner, entry.action_id, receipt)
                status = reconciliation.decision_status
                expected = _EXPECTED_STATUS[outcome.outcome]

                attempt.state = "TERMINAL"
                attempt.outcome = outcome.outcome
                attempt.detail = outcome.detail
                attempt.completed_at = now
                if status == "BREACHED":
                    # A rejected settlement is never a confirmation. Retain the
                    # claim and surface the breach so no next action can submit
                    # until an explicit recovery.
                    entry.state = "BREACHED"
                    entry.blocking_reason = f"BREACHED:{reconciliation.reason or 'UNKNOWN'}"
                    retain_claim = True
                elif status != expected:
                    # A submission-capable attempt cannot be reconciled to a
                    # different settled state (for example an external P22
                    # cancellation in the claim window). Keep the claim and record
                    # unresolved blocking evidence instead of reporting a success.
                    entry.state = "RECONCILE_MISMATCH"
                    entry.blocking_reason = (
                        f"RECONCILE_MISMATCH:{status}:{reconciliation.reason or 'UNRESOLVED'}")
                    retain_claim = True
                else:
                    entry.state = _QUEUE_BY_OUTCOME[outcome.outcome]
                    entry.blocking_reason = (
                        "SUBMISSION_UNKNOWN" if outcome.outcome == "SUBMISSION_POSSIBLE" else None)
                    retain_claim = outcome.outcome == "SUBMISSION_POSSIBLE"
                entry.updated_at = now

                claim = self._active_claim(session, owner, agent_id, wallet_id, network_id)
                if claim is not None and not retain_claim:
                    claim.state = "RELEASED"
                    claim.released_at = now
                session.commit()
                evidence = SubmissionEvidence(
                    attempt_id=attempt_id, outcome=outcome.outcome, detail=outcome.detail,
                    actual_input=receipt.actual_input, actual_output=receipt.actual_output,
                    actual_gas=receipt.actual_gas)
                return TickResult(status=entry.state, reason=entry.blocking_reason,
                                  selected_action_id=entry.action_id, queue_entry=_queue_view(entry, now),
                                  evidence=evidence)
            except SQLAlchemyError:
                session.rollback()
                raise

    def _revalidate(
        self, session: Session, owner: uuid.UUID, entry: QueueRow, intent_row: IntentRow,
        action_intent: ActionIntent, approval: ApprovalSnapshot, context: AdmissionContext,
        revision: FrozenRevision, inputs: EvaluationInputs, quote: ActionQuote | None, now: dt.datetime,
    ) -> RevalidationOutcome:
        decision = session.execute(select(DecisionRow).where(
            DecisionRow.owner_id == owner, DecisionRow.decision_id == entry.decision_id,
        )).scalar_one()
        revision_hash = revision.content_hash
        approval_hash = approval.content_hash()

        def denied(reason: str, validation_identity: str) -> RevalidationOutcome:
            return RevalidationOutcome(
                status="DENIED", reason=reason, revision_hash=revision_hash, approval_hash=approval_hash,
                policy_binding=approval.policy_binding, market_binding_id=decision.market_binding_id,
                validation_identity=validation_identity, submission_at=_iso(now))

        if revision_hash != decision.content_hash:
            return denied("REVISION_CHANGED", "REVISION_CHANGED")
        if revision.revision_id != intent_row.revision_id:
            return denied("REVISION_IDENTITY_CHANGED", "REVISION_IDENTITY_CHANGED")
        if approval.policy_binding != intent_row.policy_binding:
            return denied("POLICY_BINDING_CHANGED", "POLICY_BINDING_CHANGED")
        if not approval.is_active_at(now):
            return denied("APPROVAL_INACTIVE_OR_EXPIRED", "APPROVAL_INACTIVE_OR_EXPIRED")
        # Submission-time freshness. The intent is bounded to before the next
        # scheduled decision, and the current context/quote snapshot must be
        # current. A timestamp that only predates the old decision, or the stored
        # FRESH flag, cannot prove current freshness.
        if now - decision.decision_at >= _INTENT_VALIDITY:
            return denied("INTENT_EXPIRED", "INTENT_EXPIRED")
        checked = parse_utc(context.checked_at)
        if checked > now or now - checked > _CONTEXT_FRESHNESS:
            return denied("STALE_CONTEXT", "STALE_CONTEXT")

        # Qualified submission-time observations for the exact revision and market.
        # Re-evaluate the rules with the current inputs and require the same eligible
        # operation; a newer NO_SIGNAL, a changed or missing quote, or an unqualified
        # observation denies with zero transport calls. This checks changes before
        # the next-decision boundary as well as at it.
        if inputs.observed_at() > now or now - inputs.observed_at() > _CONTEXT_FRESHNESS:
            return denied("STALE_INPUTS", "STALE_INPUTS")
        current = evaluate(revision, inputs)
        if current.status != "SIGNAL" or current.operation != entry.operation:
            identity = f"INPUTS_CHANGED:{current.status}:{current.operation or ''}"
            return denied("INPUTS_CHANGED", identity)

        # Explicit current action-quote evidence for the exact action. A current
        # rule signal is not a current action quote. The authored quote must match
        # the saved intent's quote identity, units and amount, and be fresh and
        # unexpired. A missing, stale or changed quote denies without a call and
        # without silently repricing the saved payload.
        quote_reason = self._check_action_quote(action_intent, quote, now)
        if quote_reason is not None:
            return denied(quote_reason, quote_reason)

        # The saved admission must still be live. A cancelled, denied, reconciled
        # or breached action can never be submitted from the queue.
        saved = self._admission.retrieve_decisions(owner, action_id=action_intent.action_id)
        if not saved:
            return denied("ACTION_NOT_FOUND", "ACTION_NOT_FOUND")
        if saved[0].status != "ADMITTED":
            identity = f"ACTION_NOT_ADMITTED:{saved[0].status}"
            return denied(identity, identity)

        proposal = self._admission.propose(owner, action_intent, approval, context)
        identity = f"{proposal.status}:{proposal.reason or ''}"
        if proposal.status != "PROPOSED":
            return denied(proposal.reason or "REVALIDATION_DENIED", identity)

        durable = self._durable_coverage(owner, action_intent, approval, context)
        if durable is not None:
            return denied(durable, durable)

        return RevalidationOutcome(
            status="PASSED", reason=None, revision_hash=revision_hash, approval_hash=approval_hash,
            policy_binding=approval.policy_binding, market_binding_id=decision.market_binding_id,
            validation_identity=identity, submission_at=_iso(now))

    @staticmethod
    def _check_action_quote(action_intent: ActionIntent, quote: ActionQuote | None,
                           now: dt.datetime) -> str | None:
        if quote is None:
            return "QUOTE_MISSING"
        if quote.quote_asset_id != action_intent.input.quote_asset_id:
            return "QUOTE_IDENTITY_MISMATCH"
        expected = action_intent.input.expected_quote or action_intent.input.quote_input
        if expected is None:
            return "QUOTE_UNSPECIFIED"
        if quote.amount.asset_id != expected.asset_id or quote.amount.decimals != expected.decimals:
            return "QUOTE_UNITS_MISMATCH"
        observed = parse_utc(quote.observed_at)
        if observed > now or now - observed > _CONTEXT_FRESHNESS:
            return "QUOTE_STALE"
        if now > parse_utc(quote.expires_at):
            return "QUOTE_EXPIRED"
        if quote.amount.raw != expected.raw:
            return "QUOTE_CHANGED"
        return None

    def _durable_coverage(
        self, owner: uuid.UUID, action_intent: ActionIntent, approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> str | None:
        """Recheck current authority, durable reservations and holdings before submission.

        The saved admission state, the durable reservation ledger and the current
        holdings must still cover the exact action under the caller's current
        approval. A pure proposal alone cannot prove the saved reservation exists
        or that a lowered successor limit still covers it.
        """
        summaries = {item.asset_id: item for item in self._admission.balances(
            owner, agent_id=action_intent.binding.agent_id, wallet_id=action_intent.binding.wallet_id,
            network_id=action_intent.binding.network_id)}
        for asset_id in self._capital_assets(action_intent, approval):
            cap = _cap_for(approval, asset_id)
            if cap is None:
                return "ALLOWANCE_UNSPECIFIED"
            summary = summaries.get(asset_id)
            consumed = int(summary.consumed_raw) if summary is not None else 0
            reserved = int(summary.reserved_raw) if summary is not None else 0
            if consumed + reserved > cap:
                return "CAPACITY_UNAVAILABLE"
        for asset_id in self._holding_assets(action_intent, approval):
            summary = summaries.get(asset_id)
            reserved = int(summary.reserved_raw) if summary is not None else 0
            holding = context.holdings.balances.get(asset_id)
            if holding is None or holding.as_int() < reserved:
                return "HOLDINGS_SHORTFALL"
        return None

    @staticmethod
    def _capital_assets(action_intent: ActionIntent, approval: ApprovalSnapshot) -> set[str]:
        assets = {action_intent.quantity.asset_id, approval.gas.asset_id}
        if action_intent.operation in ACQUISITIONS and action_intent.input.quote_input is not None:
            assets.add(action_intent.input.quote_asset_id)
        return assets

    @staticmethod
    def _holding_assets(action_intent: ActionIntent, approval: ApprovalSnapshot) -> set[str]:
        assets = {approval.gas.asset_id}
        if action_intent.operation in ACQUISITIONS and action_intent.input.quote_input is not None:
            assets.add(action_intent.input.quote_asset_id)
        return assets

    def _receipt(self, action_intent: ActionIntent, approval: ApprovalSnapshot,
                 outcome: TransportOutcome) -> ActionReceipt:
        binding = action_intent.binding
        if outcome.outcome == "DEFINITELY_UNSENT":
            return ActionReceipt(action_id=action_intent.action_id, binding=binding, outcome="PREBROADCAST_DENIED")
        if outcome.outcome == "SUBMISSION_POSSIBLE":
            return ActionReceipt(action_id=action_intent.action_id, binding=binding, outcome="SUBMISSION_UNKNOWN")
        default_input, default_output, default_gas = self._planned_actuals(action_intent, approval)
        if outcome.outcome == "CONFIRMED":
            return ActionReceipt(
                action_id=action_intent.action_id, binding=binding, outcome="CONFIRMED",
                actual_input=outcome.actual_input or default_input,
                actual_output=outcome.actual_output or default_output,
                actual_gas=outcome.actual_gas or default_gas)
        return ActionReceipt(
            action_id=action_intent.action_id, binding=binding, outcome="REVERTED",
            actual_gas=outcome.actual_gas or default_gas)

    @staticmethod
    def _planned_actuals(action_intent: ActionIntent, approval: ApprovalSnapshot):
        if action_intent.operation == "ENTRY":
            return action_intent.input.quote_input, action_intent.quantity, _cap_amount(approval.per_action_gas)
        return action_intent.quantity, action_intent.input.expected_quote, _cap_amount(approval.per_exit_gas)

    # -------------------------------------------------------------------- queries

    def retrieve_queue(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
    ) -> list[QueueEntryView]:
        with self._factory() as session:
            rows = session.execute(select(QueueRow).where(
                QueueRow.owner_id == verified_owner_id, QueueRow.agent_id == agent_id,
                QueueRow.wallet_id == wallet_id, QueueRow.network_id == network_id,
            ).order_by(QueueRow.priority, QueueRow.enqueued_at, QueueRow.queue_id)).scalars().all()
            now = self._clock()
            return [_queue_view(row, now) for row in rows]

    def status(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
    ) -> HealthView:
        with self._factory() as session:
            decisions = session.execute(select(DecisionRow).where(
                DecisionRow.owner_id == verified_owner_id, DecisionRow.agent_id == agent_id,
                DecisionRow.wallet_id == wallet_id, DecisionRow.network_id == network_id,
            ).order_by(DecisionRow.decision_at)).scalars().all()
            attempts = session.execute(select(SubmissionAttemptRow).where(
                SubmissionAttemptRow.owner_id == verified_owner_id,
                SubmissionAttemptRow.agent_id == agent_id, SubmissionAttemptRow.wallet_id == wallet_id,
                SubmissionAttemptRow.network_id == network_id,
            ).order_by(SubmissionAttemptRow.started_at)).scalars().all()
            queue = session.execute(select(QueueRow).where(
                QueueRow.owner_id == verified_owner_id, QueueRow.agent_id == agent_id,
                QueueRow.wallet_id == wallet_id, QueueRow.network_id == network_id,
            ).order_by(QueueRow.priority, QueueRow.enqueued_at)).scalars().all()
            claim = self._active_claim(session, verified_owner_id, agent_id, wallet_id, network_id)
            now = self._clock()

        last_decision = decisions[-1] if decisions else None
        completed = [a.completed_at for a in attempts if a.completed_at is not None]
        next_scheduled = None
        if last_decision is not None:
            next_scheduled = utc_iso(last_decision.decision_at + dt.timedelta(minutes=5))
        blocked = None
        if claim is not None:
            held = next((row for row in queue if row.queue_id == claim.queue_id), None)
            blocked = (held.blocking_reason if held is not None else None) or "UNRESOLVED_PRIOR_ACTION"
        return HealthView(
            owner_id=verified_owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id,
            last_attempt_at=_iso(attempts[-1].started_at) if attempts else None,
            last_completion_at=_iso(max(completed)) if completed else None,
            last_input_at=_iso(last_decision.decision_at) if last_decision else None,
            last_decision_id=last_decision.decision_id if last_decision else None,
            next_scheduled_at=next_scheduled,
            queue=[_queue_view(row, now) for row in queue],
            blocking_reason=blocked)

    # -------------------------------------------------------------------- helpers

    def _intent_by_id(self, session: Session, owner: uuid.UUID, intent_id: str) -> IntentRow | None:
        return session.execute(select(IntentRow).where(
            IntentRow.owner_id == owner, IntentRow.intent_id == intent_id)).scalar_one_or_none()

    def _intent_by_action(self, session: Session, owner: uuid.UUID, action_id: str) -> IntentRow | None:
        return session.execute(select(IntentRow).where(
            IntentRow.owner_id == owner, IntentRow.action_id == action_id)).scalar_one_or_none()

    def _queue_by_id(self, session: Session, owner: uuid.UUID, queue_id: uuid.UUID) -> QueueRow | None:
        return session.execute(select(QueueRow).where(
            QueueRow.owner_id == owner, QueueRow.queue_id == queue_id)).scalar_one_or_none()

    def _queue_by_action(self, session: Session, owner: uuid.UUID, action_id: str) -> QueueRow | None:
        return session.execute(select(QueueRow).where(
            QueueRow.owner_id == owner, QueueRow.action_id == action_id)).scalar_one_or_none()

    def _active_claim(self, session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                      network_id: str) -> ClaimRow | None:
        return session.execute(select(ClaimRow).where(
            ClaimRow.owner_id == owner, ClaimRow.agent_id == agent_id, ClaimRow.wallet_id == wallet_id,
            ClaimRow.network_id == network_id, ClaimRow.released_at.is_(None),
        ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()

    def _select_next(self, session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                     network_id: str) -> QueueRow | None:
        return session.execute(select(QueueRow).where(
            QueueRow.owner_id == owner, QueueRow.agent_id == agent_id, QueueRow.wallet_id == wallet_id,
            QueueRow.network_id == network_id, QueueRow.state == "QUEUED",
        ).order_by(QueueRow.priority, QueueRow.enqueued_at, QueueRow.queue_id).limit(1)
            .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()


def _decision_view(row: DecisionRow) -> SavedDecisionView:
    return SavedDecisionView(
        decision_id=row.decision_id, owner_id=row.owner_id, agent_id=row.agent_id,
        wallet_id=row.wallet_id, network_id=row.network_id, strategy_id=row.strategy_id,
        revision_id=row.revision_id, content_hash=row.content_hash, manifest_hash=row.manifest_hash,
        market_binding_id=row.market_binding_id, decision_at=_iso(row.decision_at), status=row.status,
        operation=row.operation, reasons=list(row.reasons),
        rule_results=[RuleEvaluation.model_validate(item) for item in row.rule_results],
        inputs_hash=row.inputs_hash, created_at=_iso(row.created_at))


def _queue_view(row: QueueRow, now: dt.datetime) -> QueueEntryView:
    reference = row.updated_at if row.state in _TERMINAL_QUEUE else now
    waiting = max(0, int((reference - row.enqueued_at).total_seconds()))
    return QueueEntryView(
        queue_id=row.queue_id, owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
        network_id=row.network_id, position_id=row.position_id, operation=row.operation,
        action_id=row.action_id, decision_id=row.decision_id, priority=int(row.priority),
        state=row.state, blocking_reason=row.blocking_reason, enqueued_at=_iso(row.enqueued_at),
        updated_at=_iso(row.updated_at), waiting_seconds=waiting,
        delayed_exit=row.operation == "EXIT" and row.state in _DELAYED_EXIT_STATES)


def _enqueue_result(intent: IntentRow, entry: QueueRow | None, now: dt.datetime) -> EnqueueResult:
    return EnqueueResult(
        intent=IntentPlan(
            intent_id=intent.intent_id, action_id=intent.action_id, decision_id=intent.decision_id,
            review_hash=intent.review_hash, operation=intent.operation, position_id=intent.position_id,
            binding=IdentityBinding(
                agent_id=intent.agent_id, wallet_id=intent.wallet_id, network_id=intent.network_id,
                strategy_revision=intent.revision_id, mandate_id=intent.mandate_id),
            payload_hash=intent.payload_hash),
        admission_status=intent.admission_status, admission_reason=intent.admission_reason,
        queue_entry=_queue_view(entry, now) if entry is not None else None)
