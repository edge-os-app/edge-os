"""Durable bounded evaluation, submission and reconciliation for the connected journey.

`schedule` saves one evaluation job per owner, agent, adopted consent and five-minute decision slot.
`run_job` advances that job through the accepted services, each stage idempotent and saved before the next:

1. QUEUED: read trusted market observations for the exact revision and slot, then save the
   signal/no-signal/ineligible decision (an existing decision for the same slot is reused).
2. DECIDED: derive the exact intent terms on the server from the revision sizing, a trusted quote, current
   holdings and the adopted consent, then admit and enqueue the one intent the decision identifies.
3. ENQUEUED: revalidate and submit through the transport under the accepted exclusive claim. A restart
   finds the retained claim and makes no second attempt.

`reconcile_action` reads an independent receipt for the original action and settles it through the accepted
recovery service. It never submits, reprices or replaces the action. The job table, the decision, the intent,
the claim and the attempt are the only truth; nothing lives only in process memory.

Run `python -m edge_os_api.execution.worker` for a bounded loop over runnable jobs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import uuid
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.models import PositionRow
from edge_os_api.admission.types import (AdmissionContext, ApprovalSnapshot, AssetAmount, Holding,
                                         HoldingsSnapshot, IdentityBinding, PositionState, ValueState)
from edge_os_api.core.provider_ports import (MarketObservationRequest, PlannedFixtureEffect, ProviderUnavailable,
                                             QuoteRequest)
from edge_os_api.execution.connected_identity import (AdoptedConsent, ConnectedAgent, adopted_consent,
                                                      derive_approval, resolve_agent)
from edge_os_api.execution.models import DecisionRow, EvaluationJobRow, IntentRow, QueueRow
from edge_os_api.execution.types import ActionQuote, IntentTerms, utc_iso
from edge_os_api.recovery.types import OutcomeEvidence

log = logging.getLogger("edge_os.worker")

RUNNABLE = ("QUEUED", "DECIDED", "ENQUEUED")
# An intent is valid only before the next scheduled decision (the accepted P23 local bound).
INTENT_VALIDITY = dt.timedelta(minutes=5)
TERMINAL_QUEUE = {"SUBMITTED_CONFIRMED", "SUBMITTED_REVERTED", "DENIED_UNSENT", "REVALIDATION_DENIED",
                  "ADMISSION_DENIED", "SUBMISSION_NOT_OWNED"}
SLOT = dt.timedelta(minutes=5)


def decision_slot(now: dt.datetime) -> dt.datetime:
    """The five-minute UTC decision time a job evaluates: the latest grid point at or before `now`."""
    moment = now.astimezone(dt.timezone.utc).replace(second=0, microsecond=0)
    return moment - dt.timedelta(minutes=moment.minute % 5)


class JobRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReconcileView:
    action_id: str
    receipt_outcome: str
    case_state: str
    decision_status: str
    applied: bool
    duplicate: bool
    detail: str | None


def _lock_key(job_id: uuid.UUID) -> tuple[int, int]:
    digest = hashlib.sha256(f"edge-os-job:{job_id}".encode()).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    return int4(0), int4(4)


def job_view(row: EvaluationJobRow) -> dict[str, Any]:
    return {"job_id": str(row.job_id), "agent_id": row.agent_id, "wallet_id": row.wallet_id,
            "network_id": row.network_id, "request_key": row.request_key,
            "decision_slot": utc_iso(row.decision_slot), "strategy_id": row.strategy_id,
            "publication_revision_id": str(row.publication_revision_id),
            "execution_revision_id": row.execution_revision_id, "content_hash": row.content_hash,
            "consent_adoption_id": str(row.consent_adoption_id), "consent_hash": row.consent_hash,
            "state": row.state, "decision_id": str(row.decision_id) if row.decision_id else None,
            "action_id": row.action_id, "outcome": row.outcome, "reason": row.reason, "runs": int(row.runs),
            "provenance": row.provenance, "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat()}


class ConnectedExecution:
    def __init__(self, factory: sessionmaker[Session], services: Any, ports: Any, *, qualification: str,
                 clock: Any = None) -> None:
        self._factory = factory
        self._services = services
        self._ports = ports
        self._qualification = qualification
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    # ----------------------------------------------------------------------------------- schedule

    def schedule(self, owner_id: uuid.UUID, agent_id: str, request_key: str) -> tuple[bool, dict[str, Any]]:
        """Save the one job for this agent's adopted consent and the current slot. Returns (created, job)."""
        now = self._clock()
        with self._factory() as session:
            existing = self._job_by_key(session, owner_id, agent_id, request_key)
            if existing is not None:
                return False, job_view(existing)
            agent = resolve_agent(session, owner_id, agent_id)
            if agent is None:
                raise JobRefused("agent_not_ready")
            consent = adopted_consent(session, agent)
            if consent is None:
                raise JobRefused("consent_not_adopted")
            slot = decision_slot(now)
            identity = agent.identity()
            values = dict(
                job_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, wallet_id=agent.wallet_id,
                network_id=agent.network_id, request_key=request_key, decision_slot=slot,
                strategy_id=agent.strategy_id, publication_revision_id=agent.publication_revision_id,
                execution_revision_id=agent.revision.revision_id, content_hash=agent.revision.content_hash,
                manifest_hash=agent.revision.manifest_hash, consent_adoption_id=consent.adoption_id,
                consent_hash=consent.consent_hash, state="QUEUED",
                provenance={"identity": identity, "scheduled_at": now.isoformat()}, created_at=now, updated_at=now)
            inserted = session.execute(pg_insert(EvaluationJobRow).values(**values).on_conflict_do_nothing()
                                       .returning(EvaluationJobRow.job_id)).scalar_one_or_none()
            session.commit()
            row = (self._job_by_key(session, owner_id, agent_id, request_key)
                   or session.execute(select(EvaluationJobRow).where(
                       EvaluationJobRow.owner_id == owner_id, EvaluationJobRow.agent_id == agent_id,
                       EvaluationJobRow.consent_adoption_id == consent.adoption_id,
                       EvaluationJobRow.decision_slot == slot)).scalar_one())
            return inserted is not None, job_view(row)

    @staticmethod
    def _job_by_key(session: Session, owner_id: uuid.UUID, agent_id: str, key: str) -> EvaluationJobRow | None:
        return session.execute(select(EvaluationJobRow).where(
            EvaluationJobRow.owner_id == owner_id, EvaluationJobRow.agent_id == agent_id,
            EvaluationJobRow.request_key == key)).scalar_one_or_none()

    def list_jobs(self, owner_id: uuid.UUID, agent_id: str) -> list[dict[str, Any]]:
        with self._factory() as session:
            rows = session.execute(select(EvaluationJobRow).where(
                EvaluationJobRow.owner_id == owner_id, EvaluationJobRow.agent_id == agent_id)
                .order_by(EvaluationJobRow.created_at, EvaluationJobRow.job_id)).scalars().all()
            return [job_view(row) for row in rows]

    # ------------------------------------------------------------------------------------- run

    def run_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        """Advance up to `limit` runnable jobs, oldest first. A job another worker holds is skipped."""
        results = []
        for job_id in self._runnable_ids(limit):
            try:
                result = self.run_job(job_id)
            except Exception as error:  # noqa: BLE001 - one failing job must not stop other owners' jobs
                # Saved stage state stays as it was; the failure is recorded on this job only and retried later.
                log.exception("worker job %s failed: %s", job_id, type(error).__name__)
                self._update(job_id, reason=f"WORKER_ERROR:{type(error).__name__}")
                continue
            if result is not None:
                results.append(result)
        return results

    def _runnable_ids(self, limit: int) -> list[uuid.UUID]:
        with self._factory() as session:
            return list(session.execute(select(EvaluationJobRow.job_id).where(EvaluationJobRow.state.in_(RUNNABLE))
                                        .order_by(EvaluationJobRow.created_at).limit(limit)).scalars().all())

    def run_job(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        """Advance one job as far as it can go now. Returns None when another worker holds it."""
        with self._factory() as guard:
            key_a, key_b = _lock_key(job_id)
            held = guard.execute(text("SELECT pg_try_advisory_xact_lock(:a, :b)"), {"a": key_a, "b": key_b}).scalar()
            if not held:
                return None
            try:
                for _ in range(len(RUNNABLE) + 1):
                    job = self._load(job_id)
                    if job.state not in RUNNABLE:
                        break
                    self._update(job_id, runs_increment=True)
                    self._advance(job)
                return job_view(self._load(job_id))
            finally:
                guard.rollback()  # releases the job lock

    def _load(self, job_id: uuid.UUID) -> EvaluationJobRow:
        with self._factory() as session:
            return session.execute(select(EvaluationJobRow).where(EvaluationJobRow.job_id == job_id)).scalar_one()

    def _update(self, job_id: uuid.UUID, *, runs_increment: bool = False, **values: Any) -> None:
        with self._factory() as session:
            row = session.execute(select(EvaluationJobRow).where(EvaluationJobRow.job_id == job_id)
                                  .with_for_update()).scalar_one()
            for name, value in values.items():
                setattr(row, name, value)
            if runs_increment:
                row.runs = int(row.runs) + 1
            row.updated_at = self._clock()
            session.commit()

    def _context_for(self, job: EvaluationJobRow) -> tuple[ConnectedAgent | None, AdoptedConsent | None, str | None]:
        """Re-resolve the saved identities. A drifted binding, revision or consent never runs this job."""
        with self._factory() as session:
            agent = resolve_agent(session, job.owner_id, job.agent_id)
            consent = adopted_consent(session, agent) if agent is not None else None
        if agent is None:
            return None, None, "IDENTITY_UNAVAILABLE"
        if (agent.wallet_id, agent.network_id, agent.publication_revision_id, agent.revision.revision_id) != (
                job.wallet_id, job.network_id, job.publication_revision_id, job.execution_revision_id):
            return None, None, "IDENTITY_CHANGED"
        if consent is None or consent.adoption_id != job.consent_adoption_id or consent.consent_hash != job.consent_hash:
            return None, None, "CONSENT_CHANGED"
        return agent, consent, None

    def _advance(self, job: EvaluationJobRow) -> None:
        agent, consent, problem = self._context_for(job)
        if problem is not None:
            self._update(job.job_id, state="COMPLETED", outcome="DENIED", reason=problem)
            return
        assert agent is not None and consent is not None
        if job.state == "QUEUED":
            self._decide(job, agent)
        elif job.state == "DECIDED":
            self._enqueue(job, agent, consent)
        elif job.state == "ENQUEUED":
            self._submit(job, agent, consent)

    # ---------------------------------------------------------------------------- stages

    def _observe(self, agent: ConnectedAgent, slot: dt.datetime, position_open: bool) -> Any:
        return self._ports.market.observe(MarketObservationRequest(
            agent_id=agent.agent_id, market_binding_id=agent.revision.market_binding_id, decision_time=slot,
            warmup_buckets=agent.revision.warmup_buckets, position_open=position_open))

    def _position(self, agent: ConnectedAgent) -> PositionRow | None:
        """The agent's open position for this exact revision, if any. Closed or never-filled rows are not open."""
        with self._factory() as session:
            return session.execute(select(PositionRow).where(
                PositionRow.owner_id == agent.owner_id, PositionRow.agent_id == agent.agent_id,
                PositionRow.wallet_id == agent.wallet_id, PositionRow.network_id == agent.network_id,
                PositionRow.strategy_revision == agent.revision.revision_id, PositionRow.inventory > 0,
            ).order_by(PositionRow.position_id).limit(1)).scalar_one_or_none()

    @staticmethod
    def entry_position_id(agent: ConnectedAgent, decision_id: uuid.UUID) -> str:
        """Each entry opens its own position, so a closed or cancelled position never blocks a later entry."""
        return f"{agent.agent_id}:{agent.revision.revision_id}:{decision_id}"

    def _decide(self, job: EvaluationJobRow, agent: ConnectedAgent) -> None:
        with self._factory() as session:
            existing = session.execute(select(DecisionRow).where(
                DecisionRow.owner_id == job.owner_id, DecisionRow.agent_id == job.agent_id,
                DecisionRow.wallet_id == job.wallet_id, DecisionRow.network_id == job.network_id,
                DecisionRow.revision_id == job.execution_revision_id,
                DecisionRow.decision_at == job.decision_slot)).scalars().first()
            decision_id, status = (existing.decision_id, existing.status) if existing is not None else (None, None)
        if decision_id is None:
            position_open = self._position(agent) is not None
            try:
                observed = self._observe(agent, job.decision_slot, position_open)
            except ProviderUnavailable:
                self._update(job.job_id, state="UNAVAILABLE", outcome="UNAVAILABLE", reason="OBSERVATIONS_UNAVAILABLE")
                return
            # Observations for another market or another decision time are never evaluated for this one.
            if observed.provenance.get("market_binding_id") != agent.revision.market_binding_id:
                self._update(job.job_id, state="UNAVAILABLE", outcome="UNAVAILABLE", reason="OBSERVATIONS_WRONG_MARKET")
                return
            if observed.inputs.observed_at() != job.decision_slot:
                self._update(job.job_id, state="UNAVAILABLE", outcome="UNAVAILABLE", reason="OBSERVATIONS_WRONG_TIME")
                return
            view = self._services.execution.evaluate_and_decide(
                job.owner_id, agent.revision, observed.inputs, agent_id=agent.agent_id, wallet_id=agent.wallet_id,
                network_id=agent.network_id)
            decision_id, status = view.decision_id, view.status
            provenance = {**job.provenance, "observations": observed.provenance}
        else:
            provenance = job.provenance
        if status != "SIGNAL":
            self._update(job.job_id, state="COMPLETED", decision_id=decision_id, outcome=status,
                         reason=None, provenance=provenance)
            return
        self._update(job.job_id, state="DECIDED", decision_id=decision_id, provenance=provenance)

    def _holdings(self, agent: ConnectedAgent, now: dt.datetime) -> AdmissionContext:
        assets = [(agent.quote.asset_id, agent.quote.decimals), (agent.base.asset_id, agent.base.decimals),
                  (agent.gas.asset_id, agent.gas.decimals)]
        observed = self._ports.holdings.observe(owner_id=agent.owner_id, agent_id=agent.agent_id,
                                                wallet_id=agent.wallet_id, network_id=agent.network_id, assets=assets)
        balances = {asset_id: Holding(asset_id=asset_id, decimals=amount.decimals, raw=amount.raw)
                    for asset_id, amount in observed.items()}
        # Attributed inventory comes from the durable admission position, never from a caller.
        positions = {}
        position = self._position(agent)
        if position is not None:
            positions[position.position_id] = PositionState(
                position_id=position.position_id,
                binding=IdentityBinding(agent_id=position.agent_id, wallet_id=position.wallet_id,
                                        network_id=position.network_id, strategy_revision=position.strategy_revision,
                                        mandate_id=position.mandate_id),
                asset_id=position.asset_id, decimals=int(position.decimals), inventory_raw=str(int(position.inventory)))
        return AdmissionContext(checked_at=utc_iso(now), holdings=HoldingsSnapshot(
            agent_id=agent.agent_id, wallet_id=agent.wallet_id, network_id=agent.network_id, balances=balances,
            positions=positions))

    @staticmethod
    def _entry_input_raw(agent: ConnectedAgent) -> str:
        """The revision's fixed quote size in exact base units. A size finer than the quote decimals is refused."""
        try:
            scaled = Decimal(str(agent.strategy["sizing"]["amount"])).scaleb(agent.quote.decimals)
        except (InvalidOperation, KeyError, TypeError):
            raise JobRefused("SIZING_UNSUPPORTED") from None
        if scaled <= 0 or scaled != scaled.to_integral_value():
            raise JobRefused("SIZING_NOT_REPRESENTABLE")
        return str(int(scaled))

    def _terms(self, agent: ConnectedAgent, consent: AdoptedConsent, operation: str, now: dt.datetime,
               decision_id: uuid.UUID) -> tuple[IntentTerms, Any]:
        """Server-derived exact terms. Entry size comes from the revision; output from a trusted quote."""
        policy, mandate = consent.consent_hash, str(consent.adoption_id)
        if operation == "ENTRY":
            quote_raw = self._entry_input_raw(agent)
            quoted = self._ports.quotes.quote(QuoteRequest(
                operation="ENTRY", quote_asset_id=agent.quote.asset_id, quote_decimals=agent.quote.decimals,
                base_asset_id=agent.base.asset_id, base_decimals=agent.base.decimals, quote_input_raw=quote_raw,
                base_input_raw=None, observed_at=now))
            quote_input = AssetAmount(asset_id=agent.quote.asset_id, raw=quote_raw, decimals=agent.quote.decimals)
            terms = IntentTerms(operation="ENTRY", position_id=self.entry_position_id(agent, decision_id),
                                policy_binding=policy,
                                mandate_id=mandate, quote_asset_id=agent.quote.asset_id, quantity=quoted.output,
                                quote_input=quote_input, expected_quote=quote_input, mark=None, quote_status="FRESH")
            return terms, quoted
        position = self._position(agent)
        if position is None:
            raise JobRefused("NO_OPEN_POSITION")
        base_raw = str(int(position.inventory))
        quoted = self._ports.quotes.quote(QuoteRequest(
            operation="EXIT", quote_asset_id=agent.quote.asset_id, quote_decimals=agent.quote.decimals,
            base_asset_id=agent.base.asset_id, base_decimals=agent.base.decimals, quote_input_raw=None,
            base_input_raw=base_raw, observed_at=now))
        terms = IntentTerms(operation="EXIT", position_id=position.position_id, policy_binding=policy,
                            mandate_id=mandate, quote_asset_id=agent.quote.asset_id,
                            quantity=AssetAmount(asset_id=agent.base.asset_id, raw=base_raw,
                                                 decimals=agent.base.decimals),
                            quote_input=None, expected_quote=quoted.output,
                            mark=ValueState(state="KNOWN", amount=quoted.output), quote_status="FRESH")
        return terms, quoted

    def _enqueue(self, job: EvaluationJobRow, agent: ConnectedAgent, consent: AdoptedConsent) -> None:
        assert job.decision_id is not None
        now = self._clock()
        approval, reason = derive_approval(agent, consent, qualification=self._qualification, now=now)
        if approval is None:
            self._update(job.job_id, state="UNAVAILABLE", outcome="UNAVAILABLE", reason=reason)
            return
        with self._factory() as session:
            decision = session.execute(select(DecisionRow).where(
                DecisionRow.owner_id == job.owner_id, DecisionRow.decision_id == job.decision_id)).scalar_one()
            saved_intent = session.execute(select(IntentRow).where(
                IntentRow.owner_id == job.owner_id, IntentRow.decision_id == job.decision_id)).scalar_one_or_none()
        if saved_intent is not None:  # a restart after enqueue: reuse the one saved intent, never rebuild it
            self._after_enqueue(job, saved_intent.action_id, saved_intent.admission_status,
                                saved_intent.admission_reason)
            return
        try:
            terms, _ = self._terms(agent, consent, str(decision.operation), now, job.decision_id)
            context = self._holdings(agent, now)
        except ProviderUnavailable as error:
            self._update(job.job_id, state="UNAVAILABLE", outcome="UNAVAILABLE",
                         reason=f"{str(error).upper() or 'PROVIDER'}_UNAVAILABLE")
            return
        except JobRefused as refused:
            self._update(job.job_id, state="COMPLETED", outcome="DENIED", reason=refused.code)
            return
        result = self._services.execution.enqueue(job.owner_id, job.decision_id, terms, approval, context)
        self._after_enqueue(job, result.intent.action_id, result.admission_status, result.admission_reason)

    def _after_enqueue(self, job: EvaluationJobRow, action_id: str, status: str, reason: str | None) -> None:
        if status != "ADMITTED":
            self._update(job.job_id, state="COMPLETED", action_id=action_id, outcome="ADMISSION_DENIED", reason=reason)
            return
        self._update(job.job_id, state="ENQUEUED", action_id=action_id)

    def _submit(self, job: EvaluationJobRow, agent: ConnectedAgent, consent: AdoptedConsent) -> None:
        assert job.action_id is not None
        now = self._clock()
        queue = self._queue(job.owner_id, job.action_id)
        if queue is not None and queue.state != "QUEUED":
            self._settle_from_queue(job, queue)
            return
        approval, reason = derive_approval(agent, consent, qualification=self._qualification, now=now)
        if approval is None:
            # Authority is gone and the action was never sent: release it through the accepted cancellation.
            self._release_unsent(job, "UNAVAILABLE", reason)
            return
        if now - job.decision_slot >= INTENT_VALIDITY:
            # Past the next decision the intent can never pass revalidation; it was never sent.
            self._release_unsent(job, "INTENT_EXPIRED", "INTENT_EXPIRED")
            return
        with self._factory() as session:
            intent = session.execute(select(IntentRow).where(
                IntentRow.owner_id == job.owner_id, IntentRow.action_id == job.action_id)).scalar_one()
        payload = intent.payload
        try:
            observed = self._observe(agent, job.decision_slot, intent.operation == "EXIT")
            context = self._holdings(agent, now)
            terms_quote = self._ports.quotes.quote(QuoteRequest(
                operation=intent.operation, quote_asset_id=agent.quote.asset_id, quote_decimals=agent.quote.decimals,
                base_asset_id=agent.base.asset_id, base_decimals=agent.base.decimals,
                quote_input_raw=(payload["input"]["quote_input"] or {}).get("raw"),
                base_input_raw=payload["quantity"]["raw"] if intent.operation == "EXIT" else None, observed_at=now))
        except ProviderUnavailable as error:
            # A submission-stage outage keeps the saved action queued; a later pass ticks the same action.
            self._update(job.job_id, reason=f"WAITING:{str(error).upper() or 'PROVIDER'}_UNAVAILABLE")
            return
        if intent.operation == "ENTRY":
            # The quote cost of the saved quantity at the fresh price. Unchanged prices reproduce the saved input;
            # a moved price yields a different amount, which revalidation denies as QUOTE_CHANGED.
            fresh_output = int(terms_quote.output.raw)
            saved_input = int(payload["input"]["quote_input"]["raw"])
            cost = saved_input * int(payload["quantity"]["raw"]) // fresh_output if fresh_output else 0
            quote_amount = AssetAmount(asset_id=agent.quote.asset_id, raw=str(cost), decimals=agent.quote.decimals)
        else:
            quote_amount = terms_quote.output
        action_quote = ActionQuote(
            action_id=job.action_id, revision_id=agent.revision.revision_id,
            revision_content_hash=agent.revision.content_hash, market_binding_id=agent.revision.market_binding_id,
            quote_asset_id=agent.quote.asset_id, amount=quote_amount, observed_at=utc_iso(terms_quote.observed_at),
            expires_at=utc_iso(terms_quote.expires_at), source_ref=terms_quote.source_ref)
        plan = self._planned_effect(payload, approval)
        try:
            transport = self._ports.transport(agent_id=agent.agent_id, plan=plan, operation=intent.operation)
        except ProviderUnavailable:
            self._update(job.job_id, reason="WAITING:TRANSPORT_UNAVAILABLE")
            return
        tick = self._services.execution.tick(
            job.owner_id, agent_id=agent.agent_id, wallet_id=agent.wallet_id, network_id=agent.network_id,
            approval=approval, context=context, revision=agent.revision, inputs=observed.inputs, quote=action_quote,
            transport=transport, now=now)
        if tick.status == "IDLE" or (tick.selected_action_id not in (None, job.action_id)):
            queue = self._queue(job.owner_id, job.action_id)
            if queue is not None and queue.state != "QUEUED":
                self._settle_from_queue(job, queue)
            else:  # another action of this wallet holds the claim; this job waits for its own turn
                self._update(job.job_id, reason=tick.reason or tick.status)
            return
        if tick.status == "BLOCKED_UNKNOWN":
            self._update(job.job_id, state="SUBMITTED", outcome="SUBMITTED_UNKNOWN", reason=tick.reason)
            return
        queue = self._queue(job.owner_id, job.action_id)
        assert queue is not None
        self._settle_from_queue(job, queue)

    def _release_unsent(self, job: EvaluationJobRow, outcome: str, reason: str | None) -> None:
        """End a job whose admitted action was never submitted, releasing it through the accepted cancellation.

        `AdmissionService.cancel` refuses anything already submission-owned, so a possibly-sent action keeps its
        reservations and stays reconcilable.
        """
        assert job.action_id is not None
        cancelled = self._services.admission.cancel(job.owner_id, job.action_id)
        if cancelled.decision_status not in ("CANCELLED", "DENIED", "NOT_FOUND"):
            self._update(job.job_id, state="SUBMITTED", outcome=cancelled.decision_status,
                         reason=cancelled.reason or reason)
            return
        # A still-queued entry for the released action is retired so no later tick selects it.
        self._services.execution.retire_unsent(job.owner_id, action_id=job.action_id, reason=reason)
        self._update(job.job_id, state="COMPLETED", outcome=outcome, reason=reason)

    def _settle_from_queue(self, job: EvaluationJobRow, queue: QueueRow) -> None:
        if queue.state in ("REVALIDATION_DENIED", "SUBMISSION_NOT_OWNED"):
            # Definitely unsent: release the admitted action instead of holding its reservations forever.
            self._release_unsent(job, queue.state, queue.blocking_reason)
        elif queue.state in TERMINAL_QUEUE:
            self._update(job.job_id, state="COMPLETED", outcome=queue.state, reason=queue.blocking_reason)
        else:  # CLAIMED, SUBMITTED_UNKNOWN, BREACHED, RECONCILE_MISMATCH: the original action needs reconciling
            self._update(job.job_id, state="SUBMITTED", outcome=queue.state, reason=queue.blocking_reason)

    @staticmethod
    def _planned_effect(payload: dict[str, Any], approval: ApprovalSnapshot) -> PlannedFixtureEffect:
        """The authored fixture effect for the exact payload. Fixture input only, never a live actual."""
        quantity = AssetAmount.model_validate(payload["quantity"])
        if payload["operation"] in ("ENTRY", "ADDITION"):
            return PlannedFixtureEffect(actual_input=AssetAmount.model_validate(payload["input"]["quote_input"]),
                                        actual_output=quantity,
                                        actual_gas=AssetAmount(asset_id=approval.per_action_gas.asset_id,
                                                               raw=approval.per_action_gas.approved_raw,
                                                               decimals=approval.per_action_gas.decimals))
        return PlannedFixtureEffect(actual_input=quantity,
                                    actual_output=AssetAmount.model_validate(payload["input"]["expected_quote"]),
                                    actual_gas=AssetAmount(asset_id=approval.per_exit_gas.asset_id,
                                                           raw=approval.per_exit_gas.approved_raw,
                                                           decimals=approval.per_exit_gas.decimals))

    def _queue(self, owner_id: uuid.UUID, action_id: str) -> QueueRow | None:
        with self._factory() as session:
            return session.execute(select(QueueRow).where(
                QueueRow.owner_id == owner_id, QueueRow.action_id == action_id)).scalar_one_or_none()

    # ---------------------------------------------------------------------------- reconcile

    def reconcile_action(self, owner_id: uuid.UUID, action_id: str) -> ReconcileView:
        """Settle the original action from an independent receipt. Never submits or replaces it."""
        with self._factory() as session:
            intent = session.execute(select(IntentRow).where(
                IntentRow.owner_id == owner_id, IntentRow.action_id == action_id)).scalar_one_or_none()
        if intent is None:
            raise JobRefused("action_not_found")
        try:
            receipt = self._ports.receipts.observe(action_id=action_id, wallet_id=intent.wallet_id,
                                                   network_id=intent.network_id)
        except ProviderUnavailable:
            raise JobRefused("receipt_unavailable") from None
        evidence = OutcomeEvidence(
            action_id=action_id, binding=IdentityBinding.model_validate(intent.payload["binding"]),
            operation=intent.operation, revision_id=intent.revision_id, policy_binding=intent.policy_binding,
            payload_hash=intent.payload_hash, outcome=receipt.outcome, detail=f"receipt:{receipt.outcome}",
            actual_input=receipt.actual_input if receipt.outcome == "CONFIRMED" else None,
            actual_output=receipt.actual_output if receipt.outcome == "CONFIRMED" else None,
            actual_gas=receipt.actual_gas if receipt.outcome in ("CONFIRMED", "REVERTED") else None,
            observed_at=utc_iso(receipt.observed_at), source_ref=receipt.source_ref)
        result = self._services.recovery.reconcile(owner_id, action_id, evidence)
        queue = self._queue(owner_id, action_id)
        with self._factory() as session:
            job = session.execute(select(EvaluationJobRow).where(
                EvaluationJobRow.owner_id == owner_id, EvaluationJobRow.action_id == action_id)).scalar_one_or_none()
        if job is not None and queue is not None and job.state in ("SUBMITTED", "ENQUEUED"):
            self._settle_from_queue(job, queue)
        return ReconcileView(action_id=action_id, receipt_outcome=receipt.outcome, case_state=result.case.state,
                             decision_status=result.decision_status, applied=result.applied,
                             duplicate=result.duplicate, detail=result.detail)


def main() -> None:
    """Bounded worker loop. Each pass advances runnable jobs; nothing here schedules new work."""
    from edge_os_api.core.database import make_engine, make_session_factory
    from edge_os_api.core.financial_services import build_financial_services
    from edge_os_api.core.settings import load_settings

    parser = argparse.ArgumentParser(description="Advance saved evaluation jobs.")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between passes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    services = build_financial_services(make_session_factory(engine), settings)
    from edge_os_api.core import worker_loop

    worker_loop.exit_with(worker_loop.run("worker", engine, services.connected.run_pending, once=args.once,
                                          interval=args.interval, log=log))

if __name__ == "__main__":
    main()
