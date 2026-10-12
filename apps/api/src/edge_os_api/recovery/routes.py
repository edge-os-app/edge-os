"""Authenticated original-action reconciliation route.

The server reads an independent receipt for the exact saved action and settles it through the accepted
recovery service. A body can never supply an outcome or an amount, and reconciling never submits, reprices
or replaces the action. An unknown outcome keeps every reservation and the exclusive claim.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.routes import refused
from edge_os_api.execution.worker import JobRefused

router = APIRouter(prefix="/v1", tags=["recovery"], dependencies=[Depends(require_principal)])


class EmptyBody(StrictModel):
    """No outcome, amount or identity can be supplied."""


@router.post("/actions/{action_id}/reconcile")
def reconcile(action_id: str, request: Request, data: EmptyBody | None = Body(default=None),
              principal: Principal = Depends(require_principal)) -> dict[str, Any]:
    try:
        view = request.app.state.financial.connected.reconcile_action(principal.user_id, action_id)
    except JobRefused as error:
        raise refused(error) from None
    return asdict(view)
