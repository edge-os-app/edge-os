"""Request bodies. Every model forbids extra fields at every depth, so a body can never carry an owner."""

from __future__ import annotations

from datetime import datetime
import unicodedata
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Job = Literal["COMPARE", "INVESTIGATE_EFFECT", "CREATE_STRATEGY", "SIMULATE", "OBSERVE_FORWARD", "REQUEST_LIVE"]
InputClass = Literal["CONCRETE_THESIS", "LOOSE_INTUITION", "BOUNDED_NO_THESIS"]
Restriction = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]


def _nfc_text(value: str) -> str:
    if not unicodedata.is_normalized("NFC", value):
        raise PydanticCustomError("text_not_nfc", "Text must use composed Unicode characters (NFC).")
    return value


def _bounded_text(max_length: int) -> Any:
    return Annotated[str, StringConstraints(min_length=1, max_length=max_length), AfterValidator(_nfc_text)]


ReviewText = _bounded_text(2000)
ShortReviewText = _bounded_text(1000)


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
    """One answer to an open question: a listed choice, or the user's own words (read by the interpreter)."""

    previous_revision_id: Identifier
    question_id: Identifier
    choice_id: Identifier | None = None
    answer_text: ReviewText | None = None

    @model_validator(mode="after")
    def _one_kind_of_answer(self) -> "ClarificationBody":
        if (self.choice_id is None) == (self.answer_text is None):
            raise PydanticCustomError("one_answer_required", "Give either choice_id or answer_text, not both.")
        if self.answer_text is not None and not self.answer_text.strip():
            raise PydanticCustomError("answer_text_blank", "Write something in your own words, or choose an option.")
        return self


class RetryBody(StrictModel):
    """Explicit retry of interpretation. It names the earlier attempt it follows, or null when none exists."""

    retry_of: Identifier | None


class PublicationBody(StrictModel):
    operation_id: Identifier
    idempotency_key: Identifier
    expected_parent_revision_id: Identifier | None
    draft_id: Identifier
    strategy: dict[str, Any]


class SpotReplayDependency(StrictModel):
    series: Literal["price", "quote_volume"]
    offset_buckets: int = Field(le=0)


class SpotReplayEssentialField(StrictModel):
    state: Literal["BOUND", "UNBOUND"]
    essential_dependencies: list[SpotReplayDependency] | None = Field(default=None, max_length=64)


class SpotReplayEssentialFields(StrictModel):
    entry: SpotReplayEssentialField
    exit: SpotReplayEssentialField


class SpotReplayBody(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    strategy_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    strategy_revision_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F-]{36}$")]
    # Exactly one input: the authored P13 fixture, or one of the owner's saved recorded-history datasets.
    dataset_fixture_id: Literal["p13.wc01/1"] | None = None
    history_dataset_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")] | None = None
    run_configuration_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    window_start: datetime
    window_end: datetime
    initial_cash_quote: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    initial_base_amount: Annotated[str, StringConstraints(min_length=1, max_length=100)] = "0"
    initial_basis_quote: Annotated[str, StringConstraints(min_length=1, max_length=100)] = "0"
    essential_fields: SpotReplayEssentialFields

    @model_validator(mode="after")
    def one_dataset(self) -> "SpotReplayBody":
        if (self.dataset_fixture_id is None) == (self.history_dataset_id is None):
            raise PydanticCustomError("one_dataset_required",
                                      "Choose either the synthetic fixture or one saved history dataset.")
        return self


class EdgeClaim(StrictModel):
    status: Literal["HYPOTHESIS", "DESCRIPTIVE_ONLY"]
    text: ReviewText


class EdgeFalsification(StrictModel):
    status: Literal["DECLARED", "DESCRIPTIVE_ONLY"]
    criteria: ReviewText


class InvestigationEdgeSpec(StrictModel):
    edge_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    version: int = Field(ge=1, le=1000)
    parent_declaration_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")] | None
    hypothesis: ReviewText
    claim: EdgeClaim
    falsification: EdgeFalsification
    alternatives: list[ShortReviewText] = Field(min_length=1, max_length=10)
    unknowns: list[ShortReviewText] = Field(min_length=1, max_length=20)


class InvestigationPoolBinding(StrictModel):
    profile_id: Literal["fixture-unqualified-pool/1"]
    qualification: Literal["UNQUALIFIED_FIXTURE"]
    limitations: list[ShortReviewText] = Field(min_length=1, max_length=20)


class InvestigationVariant(StrictModel):
    variant_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    hypothesis: ShortReviewText


class InvestigationHorizon(StrictModel):
    value: int = Field(gt=0)
    unit: Literal["SECONDS", "MINUTES", "HOURS", "DAYS"]


class InvestigationEvaluationPlan(StrictModel):
    evaluation_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    trial_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    variant_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    horizon: InvestigationHorizon
    partition_ids: list[Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def partitions_are_unique(self) -> "InvestigationEvaluationPlan":
        if len(set(self.partition_ids)) != len(self.partition_ids):
            raise ValueError("Evaluation partition references must be unique.")
        return self


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
    model_config = ConfigDict(extra="forbid", strict=False)

    partition_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    role: Literal["DESCRIPTIVE", "TRAINING", "VALIDATION", "HOLDOUT"]
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def interval_is_ordered_and_utc(self) -> "InvestigationPartition":
        if (self.start.tzinfo is None or self.end.tzinfo is None or self.start.utcoffset() is None
                or self.end.utcoffset() is None or self.start.utcoffset().total_seconds() != 0
                or self.end.utcoffset().total_seconds() != 0 or self.start >= self.end):
            raise ValueError("Partition boundaries must be ordered UTC timestamps.")
        return self


OptionalTool = Literal["UNAVAILABLE", "NOT_REQUIRED"]


class OptionalResearchTools(StrictModel):
    creator_history: OptionalTool
    wallet_pnl: OptionalTool
    social_signals: OptionalTool


class InvestigationConfiguration(StrictModel):
    question: Annotated[str, StringConstraints(min_length=1, max_length=10000), AfterValidator(_nfc_text)]
    pool_binding: InvestigationPoolBinding
    variants: list[InvestigationVariant] = Field(min_length=2, max_length=20)
    direction: Literal["OUTPERFORM", "UNDERPERFORM", "DESCRIPTIVE"]
    horizons: list[InvestigationHorizon] = Field(min_length=1, max_length=20)
    sources: list[Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]] = Field(min_length=1, max_length=20)
    candidate_limit: int = Field(ge=1, le=100)
    parameter_limit: int = Field(ge=1, le=1000)
    compute_limit: InvestigationComputeLimit
    period: InvestigationPeriod
    partitions: list[InvestigationPartition] = Field(min_length=1, max_length=10)
    permitted_access: list[Literal["FIXTURE_ONLY"]] = Field(min_length=1, max_length=1)
    stopping_rule: ReviewText
    evaluation_plan: list[InvestigationEvaluationPlan] = Field(min_length=1, max_length=100)
    budget_version: Literal["p08-research-budget/2"]
    optional_tools: OptionalResearchTools

    @model_validator(mode="after")
    def identities_are_unique(self) -> "InvestigationConfiguration":
        if len({item.variant_id for item in self.variants}) != len(self.variants):
            raise ValueError("Variant identities must be unique.")
        if len({item.partition_id for item in self.partitions}) != len(self.partitions):
            raise ValueError("Partition identities must be unique.")
        horizon_ids = [(item.value, item.unit) for item in self.horizons]
        if len(set(horizon_ids)) != len(horizon_ids) or len(set(self.sources)) != len(self.sources):
            raise ValueError("Horizons and sources must be unique.")
        if self.pool_binding.profile_id not in self.sources:
            raise ValueError("The selected pool binding must appear in the declared sources.")
        if self.candidate_limit < len(self.variants):
            raise ValueError("Candidate limit must cover every declared variant.")
        period_start, period_end = self.period.start, self.period.end
        ordered = self.partitions
        if any(item.start < period_start or item.end > period_end for item in ordered):
            raise ValueError("Partition boundaries must be contained within the declared period.")
        if any(left.start > right.start or left.end > right.start for left, right in zip(ordered, ordered[1:])):
            raise ValueError("Partition boundaries must be ordered and non-overlapping.")
        roles = {item.role for item in self.partitions}
        if self.direction == "DESCRIPTIVE":
            if (len(ordered) != 1 or ordered[0].role != "DESCRIPTIVE" or ordered[0].start != period_start
                    or ordered[0].end != period_end):
                raise ValueError("Descriptive work must declare one partition covering the full period.")
        elif not {"TRAINING", "VALIDATION", "HOLDOUT"}.issubset(roles) or "DESCRIPTIVE" in roles:
            raise PydanticCustomError("predictive_partitions_incomplete",
                                      "Predictive adoption requires bounded training, validation, and holdout partitions.")
        partition_ids = {item.partition_id for item in self.partitions}
        variant_ids = {item.variant_id for item in self.variants}
        horizon_set = set(horizon_ids)
        plan_evaluation_ids = [item.evaluation_id for item in self.evaluation_plan]
        if len(plan_evaluation_ids) != len(set(plan_evaluation_ids)):
            raise ValueError("Each evaluation identity must have one explicit plan row.")
        if any(item.variant_id not in variant_ids or (item.horizon.value, item.horizon.unit) not in horizon_set
               or not set(item.partition_ids).issubset(partition_ids) for item in self.evaluation_plan):
            raise ValueError("Each evaluation plan must reference declared variants, horizons, and partitions.")
        seconds_per_unit = {"SECONDS": 1, "MINUTES": 60, "HOURS": 3600, "DAYS": 86400}
        partitions_by_id = {item.partition_id: item for item in self.partitions}
        if any(item.horizon.value * seconds_per_unit[item.horizon.unit] >
               (partitions_by_id[partition_id].end - partitions_by_id[partition_id].start).total_seconds()
               for item in self.evaluation_plan for partition_id in item.partition_ids):
            raise ValueError("Each evaluation horizon must fit within every mapped temporal partition.")
        if self.compute_limit.max_evaluations < len(self.evaluation_plan):
            raise ValueError("Evaluation limit must cover every explicit evaluation plan row.")
        return self


AdoptedField = Literal[
    "edge_spec", "question", "pool_binding", "variants", "direction", "horizons", "sources", "candidate_limit",
    "parameter_limit", "compute_limit", "period", "partitions", "permitted_access", "stopping_rule",
    "evaluation_plan", "budget_version", "optional_tools",
]


class FieldAdoption(StrictModel):
    origin: Literal["USER_STATED", "USER_CONFIRMED", "APPLICATION_CONFIGURED", "AGENT_PROPOSED"]
    source_ref: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]
    adoption: Literal["ADOPTED"]


class InvestigationBody(StrictModel):
    operation_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]
    expected_interpretation_revision_id: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)] | None
    edge_spec: InvestigationEdgeSpec
    configuration: InvestigationConfiguration
    adopted_fields: list[AdoptedField] = Field(min_length=1, max_length=18)
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
        plan = self.configuration.evaluation_plan
        if {item.evaluation_id for item in plan} != set(self.evaluation_ids):
            raise PydanticCustomError("evaluation_plan_identity_mismatch",
                                      "Every declared evaluation identity needs exactly one explicit plan row.")
        if {item.trial_id for item in plan} != set(self.trial_ids):
            raise PydanticCustomError("trial_plan_identity_mismatch",
                                      "Every declared trial identity must be bound by the explicit evaluation plan.")
        descriptive = self.edge_spec.claim.status == "DESCRIPTIVE_ONLY"
        semantic_match = ((descriptive and self.edge_spec.falsification.status == "DESCRIPTIVE_ONLY"
                           and self.configuration.direction == "DESCRIPTIVE")
                          or (not descriptive and self.edge_spec.falsification.status == "DECLARED"
                              and self.configuration.direction in {"OUTPERFORM", "UNDERPERFORM"}))
        if not semantic_match:
            raise PydanticCustomError("declaration_semantics_conflict",
                                      "Claim, falsification status, and direction must describe the same work.")
        return self


class EffectRunSchedule(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    version: Literal["p09.decision-clock/1"]
    start: datetime
    end: datetime
    interval_seconds: int = Field(ge=1, le=3600)

    @model_validator(mode="after")
    def ordered_utc_schedule(self) -> "EffectRunSchedule":
        if (self.start.tzinfo is None or self.end.tzinfo is None or self.start.utcoffset() is None
                or self.end.utcoffset() is None or self.start.utcoffset().total_seconds() != 0
                or self.end.utcoffset().total_seconds() != 0 or self.start >= self.end
                or (self.end - self.start).total_seconds() % self.interval_seconds):
            raise ValueError("Decision schedule bounds must be ordered UTC instants containing whole intervals.")
        if (self.start.microsecond or self.end.microsecond
                or int(self.start.timestamp()) % self.interval_seconds
                or int(self.end.timestamp()) % self.interval_seconds):
            raise ValueError("Decision times must align to the declared interval.")
        return self


class EffectRunBinding(StrictModel):
    evaluation_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    trial_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    variant_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    price_expression: dict[str, Any]
    volume_expression: dict[str, Any]
    essential_inputs: list[Literal["price", "quote_volume"]] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def unique_essential_inputs(self) -> "EffectRunBinding":
        if len(set(self.essential_inputs)) != len(self.essential_inputs):
            raise ValueError("Essential input mappings must be unique.")
        return self


class EffectRunBody(StrictModel):
    operation_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]
    fixture_id: Literal["synthetic-effect-comparison/1"]
    adoption: Literal["ADOPT"]
    schedule: EffectRunSchedule
    bindings: list[EffectRunBinding] = Field(min_length=1, max_length=100)
    incremental_volume_declared: bool

    @model_validator(mode="after")
    def unique_binding_ids(self) -> "EffectRunBody":
        ids = [item.evaluation_id for item in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("Each adopted evaluation identity must have exactly one P06 binding.")
        return self


class EffectAttemptBody(StrictModel):
    operation_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]


class WalletSetupPrepareBody(StrictModel):
    """One durable agent setup. The owner comes from the verified credential, never the body."""

    network_id: Literal[143, 10143]
    strategy_id: Identifier
    strategy_revision_id: Identifier
    request_key: Identifier


class WalletSetupMutationBody(StrictModel):
    """A dispatch, resume or cancel accepts no identity; any supplied field is rejected."""

    model_config = ConfigDict(extra="forbid", strict=True)


Uuid4Text = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")]
Address = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class HistorySourceBinding(StrictModel):
    """The one declared recorded source. Its id and profile digest must match the served source exactly."""

    source_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,62}/[0-9]{1,4}$")]
    profile_sha256: Sha256Hex
    evidence_class: Literal["RECORDED_RESPONSE", "RECORDED_NATIVE_RESPONSE", "AUTHORED_HTTP_RESPONSE", "PROVIDER_ACTUAL"]


class HistoryMarket(StrictModel):
    network: Literal["MONAD"]
    pool_address: Address
    base_asset: Address
    quote_asset: Address


class HistoryWindow(InvestigationPeriod):
    """A UTC window on the five-minute grid."""

    @model_validator(mode="after")
    def on_bucket_grid(self) -> "HistoryWindow":
        if any(moment.microsecond or moment.second or moment.minute % 5 for moment in (self.start, self.end)):
            raise ValueError("Window bounds must fall on the five-minute UTC grid.")
        return self


class HistoryResourceBounds(StrictModel):
    """Reserved before any adapter effect. Each provider page is one provider request."""

    provider_requests: int = Field(ge=1, le=64)
    compute_seconds: int = Field(ge=1, le=600)
    max_pages: int = Field(ge=1, le=64)
    max_rows: int = Field(ge=1, le=10000)
    max_bytes: int = Field(ge=1024, le=4_194_304)
    deadline_seconds: int = Field(ge=1, le=3600)

    @model_validator(mode="after")
    def pages_fit_requests(self) -> "HistoryResourceBounds":
        if self.max_pages > self.provider_requests:
            raise ValueError("The page limit cannot exceed the reserved provider requests.")
        return self


class HypothesisRule(StrictModel):
    """One adopted evaluation's exact P06 rules. Only the user's own adopted rule is accepted."""

    evaluation_id: Uuid4Text
    trial_id: Uuid4Text
    variant_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    price_expression: dict[str, Any]
    volume_expression: dict[str, Any]
    essential_inputs: list[Literal["price", "quote_volume"]] = Field(min_length=1, max_length=2)
    rule_source: Literal["USER_ADOPTED"]

    @model_validator(mode="after")
    def unique_essential_inputs(self) -> "HypothesisRule":
        if len(set(self.essential_inputs)) != len(self.essential_inputs):
            raise ValueError("Essential input mappings must be unique.")
        return self


class HypothesisRuleMap(StrictModel):
    schema_version: Literal["edge-os.hypothesis-rule-map/1"]
    rules: list[HypothesisRule] = Field(min_length=1, max_length=20)
    control: Literal["UNTRIGGERED_DECISIONS"]
    incremental_volume_declared: bool


class HistoryInvestigationConfiguration(StrictModel):
    question: Annotated[str, StringConstraints(min_length=1, max_length=10000), AfterValidator(_nfc_text)]
    source: HistorySourceBinding
    market: HistoryMarket
    window: HistoryWindow
    variants: list[InvestigationVariant] = Field(min_length=1, max_length=20)
    direction: Literal["OUTPERFORM", "UNDERPERFORM", "DESCRIPTIVE"]
    horizons: list[InvestigationHorizon] = Field(min_length=1, max_length=20)
    partitions: list[InvestigationPartition] = Field(min_length=1, max_length=10)
    evaluation_plan: list[InvestigationEvaluationPlan] = Field(min_length=1, max_length=20)
    schedule: EffectRunSchedule
    rule_map: HypothesisRuleMap
    resource_bounds: HistoryResourceBounds
    permitted_access: list[Literal["RECORDED_RESPONSE", "RECORDED_NATIVE_RESPONSE", "AUTHORED_HTTP_RESPONSE", "PROVIDER_ACTUAL"]] = Field(
        min_length=1, max_length=1)
    stopping_rule: ReviewText
    budget_version: Literal["edge-os.research-budget/1"]

    @model_validator(mode="after")
    def consistent_plan(self) -> "HistoryInvestigationConfiguration":
        if len({item.variant_id for item in self.variants}) != len(self.variants):
            raise ValueError("Variant identities must be unique.")
        if len({item.partition_id for item in self.partitions}) != len(self.partitions):
            raise ValueError("Partition identities must be unique.")
        if self.permitted_access[0] != self.source.evidence_class:
            raise ValueError("The permitted access route must match the declared source's evidence class.")
        if any(item.start < self.window.start or item.end > self.window.end for item in self.partitions):
            raise ValueError("Partition boundaries must be contained within the declared window.")
        ordered = self.partitions
        if any(left.end > right.start for left, right in zip(ordered, ordered[1:])):
            raise ValueError("Partition boundaries must be ordered and non-overlapping.")
        roles = {item.role for item in ordered}
        if self.direction == "DESCRIPTIVE" and roles != {"DESCRIPTIVE"}:
            raise ValueError("Descriptive work uses descriptive partitions only.")
        if self.direction != "DESCRIPTIVE" and (not {"TRAINING", "VALIDATION", "HOLDOUT"} <= roles
                                                 or "DESCRIPTIVE" in roles):
            raise PydanticCustomError("predictive_partitions_incomplete",
                                      "Predictive adoption requires bounded training, validation, and holdout partitions.")
        partition_ids = {item.partition_id for item in ordered}
        variant_ids = {item.variant_id for item in self.variants}
        horizons = {(item.value, item.unit) for item in self.horizons}
        plan_ids = [item.evaluation_id for item in self.evaluation_plan]
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("Each evaluation identity must have one explicit plan row.")
        if any(item.variant_id not in variant_ids or (item.horizon.value, item.horizon.unit) not in horizons
               or len(item.partition_ids) != 1 or item.partition_ids[0] not in partition_ids
               for item in self.evaluation_plan):
            raise ValueError("Each evaluation must reference a declared variant, horizon and exactly one partition.")
        rules = {item.evaluation_id: item for item in self.rule_map.rules}
        if len(rules) != len(self.rule_map.rules) or set(rules) != set(plan_ids):
            raise PydanticCustomError("rule_map_plan_mismatch",
                                      "Map every declared evaluation to exactly one adopted rule.")
        if any(rules[item.evaluation_id].trial_id != item.trial_id
               or rules[item.evaluation_id].variant_id != item.variant_id for item in self.evaluation_plan):
            raise PydanticCustomError("rule_map_plan_mismatch",
                                      "Each rule must keep its evaluation's exact trial and variant identity.")
        if self.schedule.start < self.window.start or self.schedule.end > self.window.end:
            raise ValueError("The decision schedule must stay inside the declared window.")
        return self


HistoryAdoptedField = Literal[
    "edge_spec", "question", "source", "market", "window", "variants", "direction", "horizons", "partitions",
    "evaluation_plan", "schedule", "rule_map", "resource_bounds", "permitted_access", "stopping_rule",
    "budget_version",
]


class HistoryFieldAdoption(StrictModel):
    origin: Literal["USER_STATED", "USER_CONFIRMED"]
    source_ref: Literal["original_request", "history-investigation-review/1"]
    adoption: Literal["ADOPTED"]


class HistoryInvestigationBody(StrictModel):
    """`p08.investigation-declaration/3`: one recorded-history declaration, frozen before any collection."""

    operation_id: Uuid4Text
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]
    expected_interpretation_revision_id: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)] | None
    edge_spec: InvestigationEdgeSpec
    configuration: HistoryInvestigationConfiguration
    field_origins: dict[HistoryAdoptedField, HistoryFieldAdoption]
    trial_ids: list[Uuid4Text] = Field(min_length=1, max_length=20)
    evaluation_ids: list[Uuid4Text] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def everything_adopted(self) -> "HistoryInvestigationBody":
        required = set(HistoryInvestigationConfiguration.model_fields) | {"edge_spec"}
        if set(self.field_origins) != required:
            raise PydanticCustomError("required_setting_not_adopted",
                                      "Every required setting needs explicit adoption before saving.")
        for name, origin in self.field_origins.items():
            expected = ("USER_STATED", "original_request") if name == "question" else (
                "USER_CONFIRMED", "history-investigation-review/1")
            if (origin.origin, origin.source_ref) != expected:
                raise PydanticCustomError("configuration_origin_mismatch",
                                          "Each setting must be confirmed in this review; the question stays as written.")
        plan = self.configuration.evaluation_plan
        if (len(set(self.evaluation_ids)) != len(self.evaluation_ids) or len(set(self.trial_ids)) != len(self.trial_ids)
                or {item.evaluation_id for item in plan} != set(self.evaluation_ids)
                or {item.trial_id for item in plan} != set(self.trial_ids)):
            raise PydanticCustomError("evaluation_plan_identity_mismatch",
                                      "Every declared trial and evaluation identity needs exactly one explicit plan row.")
        descriptive = self.edge_spec.claim.status == "DESCRIPTIVE_ONLY"
        if not ((descriptive and self.edge_spec.falsification.status == "DESCRIPTIVE_ONLY"
                 and self.configuration.direction == "DESCRIPTIVE")
                or (not descriptive and self.edge_spec.falsification.status == "DECLARED"
                    and self.configuration.direction in {"OUTPERFORM", "UNDERPERFORM"})):
            raise PydanticCustomError("declaration_semantics_conflict",
                                      "Claim, falsification status, and direction must describe the same work.")
        return self


class InvestigationJobBody(StrictModel):
    """Start one original investigation job. Repeating the same request key returns the original job."""

    operation_id: Uuid4Text
    request_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]


DecimalText = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$")]


class NansenWindowBody(StrictModel):
    start_utc: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    end_utc: Annotated[str, StringConstraints(min_length=1, max_length=40)]


class NansenHolderQueryBody(StrictModel):
    label_type: Annotated[str, StringConstraints(min_length=1, max_length=40)] = "all_holders"
    aggregate_by_entity: bool = False
    order_field: Annotated[str, StringConstraints(min_length=1, max_length=40)] = "token_amount"
    value_usd_min: int | None = None


class NansenFlowQueryBody(StrictModel):
    label: Annotated[str, StringConstraints(min_length=1, max_length=40)] = "top_100_holders"


class NansenLimitsBody(StrictModel):
    """Finite local caps for one run. Never a provider allowance."""

    max_requests: int = Field(ge=1, le=20)
    max_pages: int = Field(ge=1, le=10)
    max_bytes: int = Field(ge=1, le=5_000_000)
    max_credits: DecimalText
    per_page: int = Field(default=100, ge=1, le=1000)


class NansenReportBody(StrictModel):
    """Start one original Nansen report job for the owner's saved request. The question is the request's own text."""

    operation_id: Uuid4Text
    request_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]
    token_address: Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
    token_symbol: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    window: NansenWindowBody
    operations: Annotated[list[Literal["holders", "flows"]], Field(min_length=1, max_length=2)]
    holder_query: NansenHolderQueryBody = NansenHolderQueryBody()
    flow_query: NansenFlowQueryBody = NansenFlowQueryBody()
    limits: NansenLimitsBody
    deadline_seconds: int = Field(ge=1, le=3600)
    compute_seconds: int = Field(ge=1, le=3600)


class MarketAdoptionBody(StrictModel):
    """Adopt one owner's QUALIFIED recorded-history market for a compiled strategy request, before publication.

    The client names the dataset and restates the amounts for the new quote unit. It never supplies a binding or a
    qualification; the server derives both from the saved dataset.
    """

    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200), AfterValidator(_nfc_text)]
    expected_interpretation_revision_id: Uuid4Text
    expected_parent_revision_id: Uuid4Text | None
    dataset_id: Uuid4Text
    adoption: Literal["ADOPT_DATASET_MARKET"]
    quote_unit: Annotated[str, StringConstraints(pattern=r"^QUOTE:0x[0-9a-fA-F]{40}$")]
    # The entry becomes this exact declared rule of the dataset's own declaration; the exit is restated here.
    evaluation_id: Uuid4Text
    exit_rule: dict[str, Any]
    sizing_amount: DecimalText
    max_quote_notional: DecimalText
