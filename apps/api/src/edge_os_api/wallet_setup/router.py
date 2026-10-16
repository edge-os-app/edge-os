"""Authenticated wallet-setup routes mounted by the application.

Owner-scoped prepare, read, dispatch, cancel and resume over the verified `Principal`. The
creation-capable provider comes from `app.state.wallet_provider`: the authored local fixture in
local/test configuration, or the fail-closed unavailable provider in production. A foreign or
absent setup is a `404`; the owner is never read from the request body.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.request_schemas import StrictModel, WalletSetupMutationBody, WalletSetupPrepareBody
from edge_os_api.wallet_setup import browser_intent, service
from edge_os_api.wallet_setup.adapter import provider_info
from edge_os_api.wallet_setup.lookup_client import OwnerBoundLookupProvider
from edge_os_api.wallet_setup.provider import WalletCreationPort
from edge_os_api.wallet_setup.types import SetupRecord

router = APIRouter(prefix="/v1/wallet-setup", tags=["wallet setup"])


class BrowserCompletionBody(StrictModel):
    """The wallet id the owner's browser received from owner-linked creation. Untrusted until looked up."""

    wallet_id: str | None = Field(default=None, min_length=1, max_length=200)
    # The exact address the SDK returned. Untrusted; required for the owner-bound lookup, optional for the fixture.
    # An address-only claim (the SDK returned no ID) is resolved by the server's own lookup.
    wallet_index: int | None = Field(default=None, ge=0, le=2_147_483_647)
    address: str | None = Field(default=None, min_length=42, max_length=42)


def serialize(record: SetupRecord) -> dict[str, Any]:
    return {
        "setup_id": str(record.setup_id), "owner_id": str(record.owner_id), "agent_id": record.agent_id,
        "network_id": record.network_id, "strategy_id": record.strategy_id,
        "strategy_revision_id": str(record.strategy_revision_id),
        "content_sha256": record.content_sha256, "manifest_sha256": record.manifest_sha256,
        "state": record.state.value, "cancellation_intent": record.cancellation_intent.value,
        "creation_dispatched": record.creation_dispatched, "wallet_id": record.wallet_id,
        "reason": record.reason, "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def get_provider(request: Request, principal: Principal = Depends(require_principal)) -> WalletCreationPort:
    """The configured provider. With a lookup socket it is bound to the verified owner, never a request body."""
    socket_path = getattr(request.app.state.settings, "wallet_lookup_socket", None)
    if socket_path:
        return OwnerBoundLookupProvider(socket_path=socket_path, owner_id=principal.user_id,
                                        privy_did=principal.privy_did)
    return request.app.state.wallet_provider


@router.post("/agents/{agent_id}/prepare")
def prepare(agent_id: str, data: WalletSetupPrepareBody, principal: Principal = Depends(require_principal),
            session: Session = Depends(get_session)) -> dict[str, Any]:
    """Persist one durable setup identity before any creation-capable call."""
    record = service.prepare_setup(session, principal, agent_id=agent_id, network_id=data.network_id,
                                   strategy_id=data.strategy_id, strategy_revision_id=data.strategy_revision_id,
                                   request_key=data.request_key)
    return serialize(record)


@router.post("/agents/{agent_id}/dispatch")
def dispatch(agent_id: str, data: WalletSetupMutationBody | None = Body(default=None),
             principal: Principal = Depends(require_principal), session: Session = Depends(get_session),
             provider: WalletCreationPort = Depends(get_provider)) -> dict[str, Any]:
    """Dispatch a prepared setup exactly once; a replay never creates again."""
    return serialize(service.dispatch_setup(session, principal, agent_id=agent_id, provider=provider))


@router.post("/agents/{agent_id}/resume")
def resume(agent_id: str, data: WalletSetupMutationBody | None = Body(default=None),
           principal: Principal = Depends(require_principal), session: Session = Depends(get_session),
           provider: WalletCreationPort = Depends(get_provider)) -> dict[str, Any]:
    """Resume or reconcile an existing setup without creating a second wallet."""
    if isinstance(provider, OwnerBoundLookupProvider):
        return serialize(browser_intent.resume_retained_claim(session, principal, agent_id=agent_id,
                                                              provider=provider))
    return serialize(service.resume_setup(session, principal, agent_id=agent_id, provider=provider))


@router.post("/agents/{agent_id}/browser-begin")
def browser_begin(agent_id: str, data: WalletSetupMutationBody | None = Body(default=None),
                  principal: Principal = Depends(require_principal),
                  session: Session = Depends(get_session)) -> dict[str, Any]:
    """Commit dispatch intent before the browser may create. Only the first claim is permitted."""
    begun = browser_intent.begin_browser_creation(session, principal, agent_id=agent_id)
    return {**serialize(begun.record), "create_permitted": begun.create_permitted}


@router.post("/agents/{agent_id}/cancel")
def cancel(agent_id: str, data: WalletSetupMutationBody | None = Body(default=None),
           principal: Principal = Depends(require_principal),
           session: Session = Depends(get_session)) -> dict[str, Any]:
    """Record cancellation intent separately from setup state."""
    return serialize(service.cancel_setup(session, principal, agent_id=agent_id))


@router.post("/agents/{agent_id}/complete")
def complete(agent_id: str, data: BrowserCompletionBody, principal: Principal = Depends(require_principal),
             session: Session = Depends(get_session),
             provider: WalletCreationPort = Depends(get_provider)) -> dict[str, Any]:
    """Bind a browser-created wallet only after an independent provider lookup confirms the exact owner."""
    if isinstance(provider, OwnerBoundLookupProvider):
        provider = provider.with_claim(data.address)
    return serialize(service.complete_from_browser(session, principal, agent_id=agent_id, wallet_id=data.wallet_id,
                                                   provider=provider, address=data.address,
                                                   wallet_index=data.wallet_index))


@router.get("/agents/{agent_id}")
def read(agent_id: str, principal: Principal = Depends(require_principal),
         session: Session = Depends(get_session)) -> dict[str, Any]:
    """Owner-scoped read. A foreign or absent setup is a `404`."""
    return serialize(service.get_setup(session, principal, agent_id=agent_id))


@router.get("/provider")
def provider_status(principal: Principal = Depends(require_principal),
                    provider: WalletCreationPort = Depends(get_provider)) -> dict[str, Any]:
    """The active provider mode and, in local fixture mode, its independent call counters.

    It never reports a real provider: production refuses the fixture and answers `unavailable`.
    """
    return provider_info(provider)
