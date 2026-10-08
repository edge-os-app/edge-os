"""Request bodies. Every model forbids extra fields at every depth, so a body can never carry an owner."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Job = Literal["COMPARE", "INVESTIGATE_EFFECT", "CREATE_STRATEGY", "SIMULATE", "OBSERVE_FORWARD", "REQUEST_LIVE"]
InputClass = Literal["CONCRETE_THESIS", "LOOSE_INTUITION", "BOUNDED_NO_THESIS"]
Restriction = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class DeclaredMarket(StrictModel):
    network: Literal["MONAD"]
    base_asset: Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
    quote_asset: Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]


class IntakeBody(StrictModel):
    original_request: Annotated[str, StringConstraints(min_length=1, max_length=10000)]
    restrictions: Annotated[list[Restriction], Field(max_length=20)]
    requested_job: Job
    input_class: InputClass
    declared_market: DeclaredMarket | None = None


class ClarificationBody(StrictModel):
    previous_revision_id: Identifier
    question_id: Identifier
    choice_id: Identifier


class PublicationBody(StrictModel):
    operation_id: Identifier
    idempotency_key: Identifier
    expected_parent_revision_id: Identifier | None
    draft_id: Identifier
    strategy: dict[str, Any]
