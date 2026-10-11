"""ConsentService: owner-scoped grouped review, durable INACTIVE adoption and reads.

Every call receives `verified_owner_id` from the caller's verified identity. A
request never carries an owner, wallet, balance or approval. The service resolves
the exact owner-scoped revision and the confirmed wallet binding through their
public read interfaces and reads the accepted modules read-only. It writes only
the owned `consent_local` tables. No outcome activates anything: a consent is
always INACTIVE and the stage mints no active authority snapshot and exposes no
activation, signing, admission, scheduler or provider-policy operation.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.consent.adoption import (acquire_review_lock, consent_content, consent_hash, find_adoption,
                                          save_adoption, to_consent_view)
from edge_os_api.consent.grouped_review import (assets_outside_network, build_review_content, content_hash,
                                                network_name, parse_saved_strategy, review_meaning,
                                                strategy_block, strategy_identity)
from edge_os_api.consent.records import ConsentAdoptionRow, ConsentDenialRow, ConsentReviewRow
from edge_os_api.consent.types import (AdoptionRequest, ConsentView, GroupedReviewView, ReviewRequest,
                                       ReviewedTerms, CONSENT_STATUS, parse_utc)
from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError
from edge_os_api.funding.service import wallet_funding_summary
from edge_os_api.records.models import StrategyRevision
from edge_os_api.wallet_setup.persistence import load_setup
from edge_os_api.wallet_setup.service import get_setup
from edge_os_api.wallet_setup.types import SetupState

log = logging.getLogger("edge_os.consent")


class ConsentError(Exception):
    """A consent-domain failure."""

    code = "consent_error"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.code)
        self.detail = detail


class ConsentNotFound(ConsentError):
    """An owner-scoped record that does not exist for this owner. Another owner sees the same result."""

    code = "consent_not_found"


class ConsentDenied(ConsentError):
    """A fail-closed denial. The denial is saved; no affirmative consent is written."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


class ConsentConflict(ConsentDenied):
    """A reuse of one identity with changed meaning."""


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


class ConsentService:
    def __init__(self, session_factory: sessionmaker[Session], *, admission: Any = None, stops: Any = None,
                 clock: Any = None) -> None:
        self._factory = session_factory
        self._admission = admission
        self._stops = stops
        self._clock = clock or _utc_now

    # ------------------------------------------------------------------ helpers

    def _deny(self, owner_id: uuid.UUID, agent_id: str | None, operation: str, code: str,
              detail: dict[str, Any]) -> None:
        try:
            with self._factory() as session:
                session.add(ConsentDenialRow(denial_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id,
                                             operation=operation, code=code, detail=detail))
                session.commit()
        except SQLAlchemyError:
            # Recording the denial must never mask the domain denial or write a consent.
            log.warning("consent denial could not be saved operation=%s code=%s", operation, code)

    @staticmethod
    def _load_owned_revision(session: Session, owner_id: uuid.UUID, strategy_id: str,
                             strategy_revision_id: str) -> dict[str, Any] | None:
        revision_uuid = _parse_uuid(strategy_revision_id)
        if revision_uuid is None:
            return None
        row = session.execute(select(StrategyRevision).where(
            StrategyRevision.owner_id == owner_id,
            StrategyRevision.strategy_id == strategy_id,
            StrategyRevision.revision_id == revision_uuid,
        )).scalar_one_or_none()
        if row is None:
            return None
        return {"strategy_id": row.strategy_id, "revision_id": row.revision_id, "content_sha256": row.content_sha256,
                "manifest_sha256": row.manifest_sha256, "strategy_canonical": row.strategy_canonical}

    @staticmethod
    def _principal(owner_id: uuid.UUID) -> Principal:
        """The owner id is already verified; the accepted P17/funding reads consume only `user_id`."""
        return Principal(user_id=owner_id, privy_did="consent-verified-owner")

    def _confirmed_setup(self, owner_id: uuid.UUID, agent_id: str):
        """Resolve the accepted P17 confirmed setup through its public read. Missing/unconfirmed is `None`."""
        try:
            with self._factory() as session:
                return get_setup(session, self._principal(owner_id), agent_id=agent_id)
        except (AppError, SQLAlchemyError):
            # A missing or unreadable binding is treated as not confirmed.
            return None

    def _funding_facts(self, owner_id: uuid.UUID, agent_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        """The confirmed wallet balance per declared asset, kept distinct from the adopted allocation."""
        try:
            with self._factory() as session:
                balances = wallet_funding_summary(session, self._principal(owner_id), agent_id=agent_id)
        except (AppError, SQLAlchemyError):
            # A missing or unreadable funding state stays explicitly unknown, never an invented balance.
            return [], ["FUNDING_STATE_UNKNOWN"]
        facts = [{"asset_class": str(balance.asset_class), "asset_id": balance.asset_id,
                  "available": {"asset_id": balance.available.asset_id, "raw": balance.available.raw,
                                "decimals": balance.available.decimals},
                  "pending": {"asset_id": balance.pending.asset_id, "raw": balance.pending.raw,
                              "decimals": balance.pending.decimals}}
                 for balance in balances]
        return facts, []

    def _allowance_facts(self, owner_id: uuid.UUID, agent_id: str, wallet_id: str,
                         network_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        if self._admission is None:
            return [], ["ALLOWANCE_STATE_UNKNOWN"]
        try:
            summaries = self._admission.balances(owner_id, agent_id=agent_id, wallet_id=wallet_id,
                                                 network_id=network_id)
        except (AppError, SQLAlchemyError):
            return [], ["ALLOWANCE_STATE_UNKNOWN"]
        return [summary.model_dump(mode="json") for summary in summaries], []

    def _decision_facts(self, owner_id: uuid.UUID, agent_id: str, wallet_id: str,
                        network_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        if self._admission is None:
            return [], ["DECISION_STATE_UNKNOWN"]
        try:
            decisions = self._admission.retrieve_decisions(owner_id, agent_id=agent_id, wallet_id=wallet_id,
                                                           network_id=network_id)
        except (AppError, SQLAlchemyError):
            return [], ["DECISION_STATE_UNKNOWN"]
        return [{"action_id": item.action_id, "operation": item.operation, "status": item.status,
                 "reason": item.reason} for item in decisions], []

    def _stop_facts(self, owner_id: uuid.UUID, agent_id: str, wallet_id: str,
                    network_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        if self._stops is None:
            return [], ["STOP_STATE_UNKNOWN"]
        try:
            views = self._stops.retrieve_stops(owner_id, agent_id=agent_id, wallet_id=wallet_id,
                                               network_id=network_id)
        except (AppError, SQLAlchemyError):
            return [], ["STOP_STATE_UNKNOWN"]
        return [{"scope": view.scope, "mode": view.mode, "trigger": view.trigger,
                 "position_id": view.position_id, "created_at": view.created_at} for view in views], []

    @staticmethod
    def _review_view(row: ConsentReviewRow) -> GroupedReviewView:
        return GroupedReviewView(
            review_id=row.review_id, owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
            network_id=row.network_id, strategy_id=row.strategy_id, strategy_revision_id=row.strategy_revision_id,
            content_sha256=row.content_sha256, manifest_sha256=row.manifest_sha256, terms_version=row.terms_version,
            terms_hash=row.terms_hash, review_hash=row.review_hash, status=row.status, content=row.content,
            created_at=row.created_at.astimezone(dt.timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------- review

    def review(self, verified_owner_id: uuid.UUID, request: ReviewRequest) -> GroupedReviewView:
        """Group and save one exact-revision/wallet/terms review. Always INACTIVE."""
        now = self._clock()
        with self._factory() as session:
            revision = self._load_owned_revision(session, verified_owner_id, request.strategy_id,
                                                 request.strategy_revision_id)
        if revision is None:
            self._deny(verified_owner_id, request.agent_id, "REVIEW", "UNKNOWN_REVISION",
                       {"strategy_id": request.strategy_id, "strategy_revision_id": request.strategy_revision_id})
            raise ConsentNotFound("strategy revision")
        try:
            strategy = parse_saved_strategy(revision["strategy_canonical"])
        except Exception as error:  # noqa: BLE001 - a saved revision that the accepted compiler rejects
            self._deny(verified_owner_id, request.agent_id, "REVIEW", "UNREADABLE_REVISION",
                       {"strategy_revision_id": request.strategy_revision_id, "error": type(error).__name__})
            raise ConsentDenied("unreadable_revision") from None

        setup = self._confirmed_setup(verified_owner_id, request.agent_id)
        if setup is None or setup.state != SetupState.CONFIRMED or not setup.wallet_id:
            self._deny(verified_owner_id, request.agent_id, "REVIEW", "WALLET_NOT_CONFIRMED",
                       {"agent_id": request.agent_id})
            raise ConsentNotFound("wallet setup")
        if (setup.strategy_revision_id != revision["revision_id"]
                or setup.content_sha256 != revision["content_sha256"]
                or setup.manifest_sha256 != revision["manifest_sha256"]):
            self._deny(verified_owner_id, request.agent_id, "REVIEW", "REVISION_WALLET_MISMATCH",
                       {"agent_id": request.agent_id, "strategy_revision_id": str(revision["revision_id"])})
            raise ConsentDenied("revision_wallet_mismatch")
        wallet_id = setup.wallet_id

        resolved_network = network_name(setup.network_id)
        if resolved_network is None or resolved_network != request.network_id:
            self._deny(verified_owner_id, request.agent_id, "REVIEW", "NETWORK_MISMATCH",
                       {"requested": request.network_id, "bound": resolved_network})
            raise ConsentDenied("network_mismatch")

        terms = request.terms
        reviewed_assets = [amount.asset_id for amount in terms.allocation]
        reviewed_assets += [term.amount.asset_id for term in terms.allowances]
        if terms.gas_budget is not None:
            reviewed_assets.append(terms.gas_budget.asset_id)
        reviewed_assets += list(terms.supported_assets)
        offenders = assets_outside_network(resolved_network, reviewed_assets)
        if offenders:
            self._deny(verified_owner_id, request.agent_id, "REVIEW", "WRONG_NETWORK_ASSET",
                       {"network_id": resolved_network, "assets": offenders})
            raise ConsentDenied("wrong_network_asset")

        identity = strategy_identity(strategy_id=revision["strategy_id"], revision_id=str(revision["revision_id"]),
                                     content_sha256=revision["content_sha256"],
                                     manifest_sha256=revision["manifest_sha256"])
        meaning = review_meaning(strategy_identity=identity, terms=terms, agent_id=request.agent_id,
                                 wallet_id=wallet_id, network_id=resolved_network)
        review_hash = content_hash(meaning)

        funding, funding_unknowns = self._funding_facts(verified_owner_id, request.agent_id)
        allowances, allowance_unknowns = self._allowance_facts(verified_owner_id, request.agent_id, wallet_id,
                                                               resolved_network)
        decisions, decision_unknowns = self._decision_facts(verified_owner_id, request.agent_id, wallet_id, resolved_network)
        stops, stop_unknowns = self._stop_facts(verified_owner_id, request.agent_id, wallet_id,
                                                resolved_network)
        unknowns = funding_unknowns + allowance_unknowns + decision_unknowns + stop_unknowns
        content = build_review_content(meaning=meaning, terms=terms, strategy=strategy_block(strategy),
                                       funding=funding, existing_allowances=allowances,
                                       existing_decisions=decisions, stops=stops, unknowns=unknowns)

        with self._factory() as session:
            existing = session.execute(select(ConsentReviewRow).where(
                ConsentReviewRow.owner_id == verified_owner_id,
                ConsentReviewRow.agent_id == request.agent_id,
                ConsentReviewRow.strategy_revision_id == revision["revision_id"],
            )).scalar_one_or_none()
            if existing is not None:
                if existing.review_hash != review_hash:
                    session.rollback()
                    self._deny(verified_owner_id, request.agent_id, "REVIEW", "CHANGED_REVIEW",
                               {"saved_review_hash": existing.review_hash, "requested_review_hash": review_hash})
                    raise ConsentConflict("changed_review")
                view = self._review_view(existing)
                session.rollback()
                return view
            row = ConsentReviewRow(
                review_id=uuid.uuid4(), owner_id=verified_owner_id, agent_id=request.agent_id,
                wallet_id=wallet_id, network_id=resolved_network, strategy_id=revision["strategy_id"],
                strategy_revision_id=revision["revision_id"], content_sha256=revision["content_sha256"],
                manifest_sha256=revision["manifest_sha256"], terms_version=terms.terms_version,
                terms_hash=terms.content_hash(), review_hash=review_hash, status=CONSENT_STATUS, content=content,
                created_at=now,
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                existing = session.execute(select(ConsentReviewRow).where(
                    ConsentReviewRow.owner_id == verified_owner_id,
                    ConsentReviewRow.agent_id == request.agent_id,
                    ConsentReviewRow.strategy_revision_id == revision["revision_id"],
                )).scalar_one_or_none()
                if existing is not None and existing.review_hash == review_hash:
                    return self._review_view(existing)
                self._deny(verified_owner_id, request.agent_id, "REVIEW", "CHANGED_REVIEW",
                           {"strategy_revision_id": str(revision["revision_id"])})
                raise ConsentConflict("changed_review") from None
            session.commit()
            return self._review_view(row)

    # -------------------------------------------------------------------- adopt

    def adopt(self, verified_owner_id: uuid.UUID, request: AdoptionRequest) -> ConsentView:
        """Persist explicit owner adoption of one exact reviewed meaning. Always INACTIVE.

        The whole check-and-save runs in one transaction. After acquiring the
        per-review advisory lock, the current wallet binding is re-read with the
        accepted wallet-setup row lock (`SELECT ... FOR UPDATE`) and held through
        commit, so a binding that becomes unconfirmed between any earlier read and
        the save cannot be adopted.
        """
        now = self._clock()
        review_id = _parse_uuid(request.review_id)
        if review_id is None:
            raise ConsentNotFound("review")
        with self._factory() as session:
            review = session.execute(select(ConsentReviewRow).where(
                ConsentReviewRow.owner_id == verified_owner_id,
                ConsentReviewRow.review_id == review_id,
            )).scalar_one_or_none()
            if review is None:
                session.rollback()
                self._deny(verified_owner_id, None, "ADOPT", "UNKNOWN_REVIEW", {"review_id": request.review_id})
                raise ConsentNotFound("review")
            agent_id = review.agent_id
            if request.expected_review_hash != review.review_hash:
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "STALE_REVIEW",
                           {"expected": request.expected_review_hash, "saved": review.review_hash})
                raise ConsentDenied("stale_review")
            meaning = review.content.get("meaning")
            if not isinstance(meaning, dict) or content_hash(meaning) != review.review_hash:
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "CORRUPT_REVIEW", {"error": "MEANING_MISMATCH"})
                raise ConsentDenied("corrupt_review")
            try:
                terms = ReviewedTerms.model_validate(review.content["terms"])
            except Exception as error:  # noqa: BLE001 - a corrupt stored term set is not adoptable
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "CORRUPT_REVIEW", {"error": type(error).__name__})
                raise ConsentDenied("corrupt_review") from None
            # The adopted terms must equal the exact reviewed meaning: the stored
            # terms still hash to the recorded terms_hash, and the meaning binds it.
            if terms.content_hash() != review.terms_hash or meaning.get("terms_hash") != review.terms_hash:
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "CORRUPT_REVIEW",
                           {"stored_terms_hash": terms.content_hash(), "review_terms_hash": review.terms_hash})
                raise ConsentDenied("corrupt_review")
            if parse_utc(terms.expiry) <= now:
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "EXPIRED_TERMS", {"expiry": terms.expiry})
                raise ConsentDenied("expired_terms")

            # Serialize competing adopters, then hold the accepted wallet-setup row
            # lock through commit so a concurrent binding change cannot slip in.
            acquire_review_lock(session, verified_owner_id, review_id)
            setup_row = load_setup(session, verified_owner_id, agent_id, lock=True)
            if (setup_row is None or setup_row.state != SetupState.CONFIRMED.value
                    or setup_row.wallet_id != review.wallet_id
                    or network_name(setup_row.network_id) != review.network_id):
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "WALLET_DRIFTED",
                           {"agent_id": agent_id, "saved_wallet_id": review.wallet_id})
                raise ConsentDenied("wallet_drifted")
            current_revision = self._load_owned_revision(session, verified_owner_id, review.strategy_id,
                                                         str(review.strategy_revision_id))
            if (current_revision is None or current_revision["content_sha256"] != review.content_sha256
                    or current_revision["manifest_sha256"] != review.manifest_sha256):
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "REVISION_DRIFTED",
                           {"strategy_revision_id": str(review.strategy_revision_id)})
                raise ConsentDenied("revision_drifted")

            content = consent_content(
                review_row=review, meaning=meaning, route=terms.route.model_dump(mode="json"),
                policy=terms.policy.model_dump(mode="json") if terms.policy is not None else None,
                evidence_status=terms.evidence.status, operating_purpose=terms.operating_purpose,
                adopted_at=_iso(now),
            )
            expected_consent_hash = consent_hash(content)
            existing = find_adoption(session, verified_owner_id, review_id)
            if existing is not None:
                if existing.consent_hash == expected_consent_hash:
                    view = to_consent_view(existing)
                    session.rollback()
                    return view
                session.rollback()
                self._deny(verified_owner_id, agent_id, "ADOPT", "CHANGED_ADOPTION",
                           {"saved_consent_hash": existing.consent_hash,
                            "requested_consent_hash": expected_consent_hash})
                raise ConsentConflict("changed_adoption")
            try:
                row = save_adoption(session, verified_owner_id, review, content, adopted_at=now)
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = find_adoption(session, verified_owner_id, review_id)
                if existing is not None and existing.consent_hash == expected_consent_hash:
                    return to_consent_view(existing)
                self._deny(verified_owner_id, agent_id, "ADOPT", "CHANGED_ADOPTION", {"review_id": str(review_id)})
                raise ConsentConflict("changed_adoption") from None
            except SQLAlchemyError:
                session.rollback()
                raise
            return to_consent_view(row)

    # --------------------------------------------------------------------- read

    def read_review(self, verified_owner_id: uuid.UUID, review_id: str) -> GroupedReviewView:
        """Owner-scoped read. A foreign or absent review is indistinguishable from a missing one."""
        parsed = _parse_uuid(review_id)
        if parsed is None:
            raise ConsentNotFound("review")
        with self._factory() as session:
            row = session.execute(select(ConsentReviewRow).where(
                ConsentReviewRow.owner_id == verified_owner_id,
                ConsentReviewRow.review_id == parsed,
            )).scalar_one_or_none()
            if row is None:
                session.rollback()
                raise ConsentNotFound("review")
            view = self._review_view(row)
            session.rollback()
            return view

    def read_consent(self, verified_owner_id: uuid.UUID, review_id: str) -> ConsentView:
        """Owner-scoped read of the consent adopted for one review. Another owner sees nothing."""
        parsed = _parse_uuid(review_id)
        if parsed is None:
            raise ConsentNotFound("consent")
        with self._factory() as session:
            row = find_adoption(session, verified_owner_id, parsed)
            if row is None:
                session.rollback()
                raise ConsentNotFound("consent")
            view = to_consent_view(row)
            session.rollback()
            return view

    def list_consents(self, verified_owner_id: uuid.UUID) -> list[ConsentView]:
        """Owner-scoped list of adopted consents, oldest first."""
        with self._factory() as session:
            rows = session.execute(select(ConsentAdoptionRow).where(
                ConsentAdoptionRow.owner_id == verified_owner_id,
            ).order_by(ConsentAdoptionRow.created_at, ConsentAdoptionRow.adoption_id)).scalars().all()
            views = [to_consent_view(row) for row in rows]
            session.rollback()
            return views
