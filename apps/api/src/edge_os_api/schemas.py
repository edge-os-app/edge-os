"""Request bodies. Every model forbids extra fields at every depth, so a body can never carry an owner."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError


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


class EdgeClaim(StrictModel):
    status: Literal["HYPOTHESIS", "DESCRIPTIVE_ONLY"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class EdgeFalsification(StrictModel):
    status: Literal["DECLARED", "DESCRIPTIVE_ONLY"]
    criteria: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class InvestigationEdgeSpec(StrictModel):
    edge_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    version: int = Field(ge=1, le=1000)
    parent_declaration_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")] | None
    hypothesis: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    claim: EdgeClaim
    falsification: EdgeFalsification
    alternatives: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=10)
    unknowns: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=20)


class InvestigationPoolBinding(StrictModel):
    profile_id: Literal["fixture-unqualified-pool/1"]
    qualification: Literal["UNQUALIFIED_FIXTURE"]
    limitations: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=20)


class InvestigationVariant(StrictModel):
    variant_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    hypothesis: Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class InvestigationComputeLimit(StrictModel):
    max_evaluations: int = Field(ge=1, le=100)
    max_runtime_seconds: int = Field(ge=1, le=3600)
    max_cost_usd: Literal["0"]


class InvestigationPeriod(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def period_is_ordered_and_utc(self) -> "InvestigationPeriod":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Period timestamps must include a UTC offset.")
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("Period timestamps must include a UTC offset.")
        if self.start.utcoffset().total_seconds() != 0 or self.end.utcoffset().total_seconds() != 0:
            raise ValueError("Period timestamps must use UTC.")
        if self.start >= self.end:
            raise ValueError("Period start must be before period end.")
        return self


class InvestigationPartition(StrictModel):
    partition_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    role: Literal["DESCRIPTIVE", "TRAINING", "VALIDATION", "HOLDOUT"]


OptionalTool = Literal["UNAVAILABLE", "NOT_REQUIRED"]


class OptionalResearchTools(StrictModel):
    creator_history: OptionalTool
    wallet_pnl: OptionalTool
    social_signals: OptionalTool


class InvestigationConfiguration(StrictModel):
    question: Annotated[str, StringConstraints(min_length=1, max_length=10000)]
    pool_binding: InvestigationPoolBinding
    variants: list[InvestigationVariant] = Field(min_length=2, max_length=20)
    direction: Literal["OUTPERFORM", "UNDERPERFORM", "DESCRIPTIVE"]
    horizons: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(min_length=1, max_length=20)
    sources: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(min_length=1, max_length=20)
    candidate_limit: int = Field(ge=1, le=100)
    parameter_limit: int = Field(ge=1, le=1000)
    compute_limit: InvestigationComputeLimit
    period: InvestigationPeriod
    partitions: list[InvestigationPartition] = Field(min_length=1, max_length=10)
    permitted_access: list[Literal["FIXTURE_ONLY"]] = Field(min_length=1, max_length=1)
    stopping_rule: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    budget_version: Literal["p08-research-budget/1"]
    optional_tools: OptionalResearchTools

    @model_validator(mode="after")
    def identities_are_unique(self) -> "InvestigationConfiguration":
        if len({item.variant_id for item in self.variants}) != len(self.variants):
            raise ValueError("Variant identities must be unique.")
        if len({item.partition_id for item in self.partitions}) != len(self.partitions):
            raise ValueError("Partition identities must be unique.")
        if len(set(self.horizons)) != len(self.horizons) or len(set(self.sources)) != len(self.sources):
            raise ValueError("Horizons and sources must be unique.")
        if self.pool_binding.profile_id not in self.sources:
            raise ValueError("The selected pool binding must appear in the declared sources.")
        if self.candidate_limit < len(self.variants):
            raise ValueError("Candidate limit must cover every declared variant.")
        if self.compute_limit.max_evaluations < len(self.variants):
            raise ValueError("Evaluation limit must cover every declared variant.")
        return self


AdoptedField = Literal[
    "edge_spec", "question", "pool_binding", "variants", "direction", "horizons", "sources", "candidate_limit",
    "parameter_limit", "compute_limit", "period", "partitions", "permitted_access", "stopping_rule",
    "budget_version", "optional_tools",
]


class FieldAdoption(StrictModel):
    origin: Literal["USER_STATED", "USER_CONFIRMED", "APPLICATION_CONFIGURED", "AGENT_PROPOSED"]
    source_ref: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    adoption: Literal["ADOPTED"]


class InvestigationBody(StrictModel):
    operation_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    idempotency_key: Identifier
    expected_interpretation_revision_id: Identifier | None
    edge_spec: InvestigationEdgeSpec
    configuration: InvestigationConfiguration
    adopted_fields: list[AdoptedField] = Field(min_length=1, max_length=16)
    field_origins: dict[AdoptedField, FieldAdoption]
    trial_ids: list[Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]] = Field(min_length=1, max_length=20)
    evaluation_ids: list[Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def all_required_fields_are_adopted(self) -> "InvestigationBody":
        required = set(InvestigationConfiguration.model_fields) | {"edge_spec"}
        if set(self.adopted_fields) != required or len(self.adopted_fields) != len(required):
            raise PydanticCustomError("required_setting_not_adopted",
                                      "Every required setting needs explicit adoption before saving.")
        if set(self.field_origins) != required:
            raise PydanticCustomError("required_setting_not_adopted",
                                      "Every required setting needs a source and origin.")
        if len(set(self.trial_ids)) != len(self.trial_ids) or len(set(self.evaluation_ids)) != len(self.evaluation_ids):
            raise ValueError("Trial and evaluation identities must be unique.")
        return self
