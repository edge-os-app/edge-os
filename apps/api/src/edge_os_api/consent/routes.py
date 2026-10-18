"""Authenticated, owner-scoped grouped review and INACTIVE adoption routes.

The body names the reviewed terms only. The service resolves the exact owned revision and the confirmed
wallet binding on the server; the strategy, revision and network come from the agent's saved setup, never
from the body. Adoption stays INACTIVE. Whether the server can derive an approval from it is reported
separately as `activation`, from the server's own qualification profile.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.consent.records import ConsentReviewRow
from edge_os_api.consent.service import ConsentConflict, ConsentDenied, ConsentNotFound
from edge_os_api.consent.types import AdoptionRequest, ReviewedTerms, ReviewRequest
from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import AppError, finding, not_found
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.connected_identity import adopted_consent, resolve_agent

router = APIRouter(prefix="/v1/agents", tags=["consent"], dependencies=[Depends(require_principal)])


class ReviewBody(StrictModel):
    terms: ReviewedTerms


class AdoptBody(StrictModel):
    review_id: str = Field(min_length=1, max_length=64)
    expected_review_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def consent_error(error: Exception) -> AppError:
    if isinstance(error, ConsentNotFound):
        return not_found("consent record")
    code = getattr(error, "code", "consent_denied")
    return AppError(409, "CONSENT", "CONFLICTED" if isinstance(error, ConsentConflict) else "DENIED", str(code),
                    [finding(str(code), "/", "The review or adoption was refused. Nothing was adopted.")])


def controlled_profile(request: Request, principal: Principal, agent: Any) -> dict[str, Any] | None:
    """Prepared exact terms for the owned saved revision. Activation remains a separate verdict."""
    if agent is None:
        return None
    runtime = request.app.state.financial.ports.controlled.get(agent.agent_id)
    if runtime is None:
        return None
    identity = runtime.binding.identity()
    if str(principal.user_id) != identity["owner_id"] or any(identity.get(key) != value for key, value in agent.identity().items()):
        return None
    from edge_os_api.execution.operating_release import release_sha256

    release = runtime.binding.release.content()
    route = release["route"]
    def amount(asset: dict[str, Any], raw: str) -> dict[str, Any]:
        return {"asset_id": asset["asset_id"], "decimals": asset["decimals"], "raw": raw}
    return {"scope": release["purpose"], "release_id": release["release_id"],
        "release_sha256": release_sha256(runtime.binding.release), "binding_sha256": runtime.binding.sha256,
        "evidence_class": release["evidence_class"], "input": amount(route["input_asset"], route["approved_input_raw"]),
        "minimum_output": amount(route["output_asset"], route["approved_min_output_raw"]),
        "recipient": route["recipient"], "entrypoint": route["entrypoint_address"], "method": route["method"],
        "allowance_raw": route["approved_allowance_raw"],
        "gas": {key: str(value) for key, value in release["gas"].items()}, "fees": route["fees"],
        "expires_at": release["valid_until"], "signer_id": release["signer_id"], "policy_id": release["policy_id"],
        "policy_content_sha256": release["policy_content_sha256"], "recurring": "UNAVAILABLE", "exit_execution": "UNAVAILABLE"}


def activation(request: Request, session: Session, principal: Principal, agent_id: str) -> dict[str, Any]:
    """Whether the server can derive an approval for this agent now, and why not when it cannot."""
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        return {"state": "UNAVAILABLE", "reason": "AGENT_NOT_READY", "evidence_class": None}
    consent = adopted_consent(session, agent)
    if consent is None:
        return {"state": "UNAVAILABLE", "reason": "CONSENT_NOT_ADOPTED", "evidence_class": None}
    approval, reason = request.app.state.financial.connected.approval(agent, consent, now=dt.datetime.now(dt.timezone.utc))
    if approval is None:
        return {"state": "UNAVAILABLE", "reason": reason, "evidence_class": None}
    return {"state": "CONTROLLED_QUALIFIED" if approval.controlled is not None else "FIXTURE_QUALIFIED",
            "reason": None, "evidence_class": approval.fixture_label,
            "mandate_id": approval.binding.mandate_id, "policy_binding": approval.policy_binding,
            "execution_revision_id": approval.binding.strategy_revision, "expires_at": approval.expires_at,
            **({"scope": approval.controlled.purpose, "release_sha256": approval.controlled.release_sha256,
                "binding_sha256": approval.controlled.binding_sha256} if approval.controlled is not None else {})}


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
    rows = session.execute(select(ConsentReviewRow.review_id).where(
        ConsentReviewRow.owner_id == principal.user_id, ConsentReviewRow.agent_id == agent_id)
        .order_by(ConsentReviewRow.created_at.desc())).scalars().all()
    session.rollback()
    reviews = [consent.read_review(principal.user_id, str(review_id)).model_dump(mode="json") for review_id in rows]
    agent = resolve_agent(session, principal.user_id, agent_id)
    assets = None if agent is None else {name: {"asset_id": identity.asset_id, "decimals": identity.decimals}
                                         for name, identity in (("quote", agent.quote), ("base", agent.base),
                                                                ("gas", agent.gas))}
    return {"agent_id": agent_id, "adoptions": adoptions, "reviews": reviews, "assets": assets,
            "identity": None if agent is None else agent.identity(),
            "provider_mode": request.app.state.financial.ports.mode,
            "controlled_action": controlled_profile(request, principal, agent),
            "activation": activation(request, session, principal, agent_id)}
