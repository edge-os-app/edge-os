"""Authenticated, owner-scoped grouped review and INACTIVE adoption routes.

The body names the reviewed terms only. The service resolves the exact owned revision and the confirmed
wallet binding on the server; the strategy, revision and network come from the agent's saved setup, never
from the body. Adoption stays INACTIVE. Whether the server can derive an approval from it is reported
separately as `activation`, from the server's own qualification profile.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from edge_os_api.consent.service import ConsentConflict, ConsentDenied, ConsentNotFound
from edge_os_api.consent.types import AdoptionRequest, ReviewedTerms, ReviewRequest
from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import AppError, finding, not_found
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.connected_identity import adopted_consent, derive_approval, resolve_agent

router = APIRouter(prefix="/v1/agents", tags=["consent"], dependencies=[Depends(require_principal)])


class ReviewBody(StrictModel):
    terms: ReviewedTerms


class AdoptBody(StrictModel):
    review_id: str = Field(min_length=1, max_length=64)
    expected_review_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def get_session(request: Request) -> Any:
    with request.app.state.session_factory() as session:
        yield session


def consent_error(error: Exception) -> AppError:
    if isinstance(error, ConsentNotFound):
        return not_found("consent record")
    code = getattr(error, "code", "consent_denied")
    return AppError(409, "CONSENT", "CONFLICTED" if isinstance(error, ConsentConflict) else "DENIED", str(code),
                    [finding(str(code), "/", "The review or adoption was refused. Nothing was adopted.")])


def activation(request: Request, session: Session, principal: Principal, agent_id: str) -> dict[str, Any]:
    """Whether the server can derive an approval for this agent now, and why not when it cannot."""
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        return {"state": "UNAVAILABLE", "reason": "AGENT_NOT_READY", "evidence_class": None}
    consent = adopted_consent(session, agent)
    if consent is None:
        return {"state": "UNAVAILABLE", "reason": "CONSENT_NOT_ADOPTED", "evidence_class": None}
    mode = request.app.state.financial.ports.mode
    approval, reason = derive_approval(agent, consent, qualification=mode, now=dt.datetime.now(dt.timezone.utc))
    if approval is None:
        return {"state": "UNAVAILABLE", "reason": reason, "evidence_class": None}
    return {"state": "FIXTURE_QUALIFIED", "reason": None, "evidence_class": approval.fixture_label,
            "mandate_id": approval.binding.mandate_id, "policy_binding": approval.policy_binding,
            "execution_revision_id": approval.binding.strategy_revision, "expires_at": approval.expires_at}


@router.post("/{agent_id}/consent/review")
def review(agent_id: str, data: ReviewBody, request: Request, principal: Principal = Depends(require_principal),
           session: Session = Depends(get_session)) -> dict[str, Any]:
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        raise not_found("agent wallet")
    session.rollback()
    consent = request.app.state.financial.consent
    try:
        view = consent.review(principal.user_id, ReviewRequest(
            agent_id=agent_id, strategy_id=agent.strategy_id, strategy_revision_id=str(agent.publication_revision_id),
            network_id=agent.network_id, terms=data.terms))
    except (ConsentNotFound, ConsentDenied) as error:
        raise consent_error(error) from None
    return view.model_dump(mode="json")


@router.post("/{agent_id}/consent/adopt")
def adopt(agent_id: str, data: AdoptBody, request: Request, principal: Principal = Depends(require_principal),
          session: Session = Depends(get_session)) -> dict[str, Any]:
    consent = request.app.state.financial.consent
    try:
        saved = consent.read_review(principal.user_id, data.review_id)
        if saved.agent_id != agent_id:
            raise ConsentNotFound("review")
        view = consent.adopt(principal.user_id, AdoptionRequest(review_id=data.review_id,
                                                                expected_review_hash=data.expected_review_hash))
    except (ConsentNotFound, ConsentDenied) as error:
        raise consent_error(error) from None
    return {**view.model_dump(mode="json"), "activation": activation(request, session, principal, agent_id)}


@router.get("/{agent_id}/consent")
def read(agent_id: str, request: Request, principal: Principal = Depends(require_principal),
         session: Session = Depends(get_session)) -> dict[str, Any]:
    consent = request.app.state.financial.consent
    adoptions = [view.model_dump(mode="json") for view in consent.list_consents(principal.user_id)
                 if view.content.get("agent_id") == agent_id]
    reviews = []
    for adoption in adoptions:
        try:
            reviews.append(consent.read_review(principal.user_id, adoption["review_id"]).model_dump(mode="json"))
        except ConsentNotFound:
            continue
    return {"agent_id": agent_id, "adoptions": adoptions, "reviews": reviews,
            "activation": activation(request, session, principal, agent_id)}
