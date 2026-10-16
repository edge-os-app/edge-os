"""The strict response format the interpreter sends with each request: the structure of one generated interpretation.

One set of Pydantic models is the only source. `interpretation_response_format()` gives the provider wrapper
(`type: json_schema`, `strict: true`) around the schema generated from them, and `conforms()` checks a decoded answer
against the same models with strict validation (no coercion). The schema follows the provider's strict subset: every
object is closed and lists all of its keys as required, unions are `anyOf`, constants are one-value `enum`s.

The schema describes form only. It shapes what the model may generate; it accepts nothing. The parser in
`interpretation_response` stays the authority for every meaning rule: quoted words, numbers, adoption, conflicts,
field ownership and questions. A value is one of the shapes the prompt's `field_shapes` and `operators` give the model
(P02 `nested_shapes` and `operator_signatures`); it carries no bound, unit or threshold, so a negative or otherwise
wrong value of an accepted shape is still representable and left to the parser, publication and compiler.
"""

from __future__ import annotations

import copy
import functools
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.json_schema import GenerateJsonSchema

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research.interpretation_response import APPLICATION_OWNED_FIELDS

__all__ = ["RESPONSE_FORMAT_NAME", "conforms", "interpretation_response_format"]

RESPONSE_FORMAT_NAME = "edge_os_interpretation"
MODEL_FIELDS = tuple(name for name in record_contract.CREATE_STRATEGY_FIELDS if name not in APPLICATION_OWNED_FIELDS)

FieldName = Literal[MODEL_FIELDS]  # type: ignore[valid-type] - the model-owned P02 strategy fields, in contract order


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# Operator nodes (P02 `operator_signatures`): one closed shape per signature.
class Constant(_Closed):
    op: Literal["constant"]
    value: str
    unit: str


class Series(_Closed):
    op: Literal["price", "quote_volume"]


class PriceReturn(_Closed):
    op: Literal["price_return"]
    lookback_buckets: int


class Window(_Closed):
    op: Literal["lag", "sum", "mean"]
    value: Node
    buckets: int


class Pair(_Closed):
    op: Literal["gt", "gte", "lt", "lte", "and", "or"]
    args: Annotated[list[Node], Field(min_length=2, max_length=2)]


class Negation(_Closed):
    op: Literal["not"]
    value: Node


Node = Union[Constant, Series, PriceReturn, Window, Pair, Negation]


# Closed field shapes (P02 `nested_shapes`) that a model-owned field can hold.
class Sizing(_Closed):
    kind: Literal["FIXED_QUOTE_AMOUNT"]
    amount: str
    unit: str


class CostAssumptions(_Closed):
    fee_rate: str
    slippage_rate: str
    source_ref: str


class RiskLimits(_Closed):
    max_quote_notional: str
    max_open_positions: int


class NotRequestedInvalidation(_Closed):
    state: Literal["NOT_REQUESTED"]
    source_ref: str


# A field value: the scalar and list forms (data_inputs, action_scope, additions, partial_exits) or a closed shape.
Value = Union[str, int, bool, list[str], Sizing, CostAssumptions, RiskLimits, NotRequestedInvalidation, Node]


class Stated(_Closed):
    field_name: FieldName
    state: Literal["KNOWN"]
    origin: Literal["USER_STATED"]
    source_passage: str
    value: Value


class Proposed(_Closed):
    field_name: FieldName
    state: Literal["KNOWN"]
    origin: Literal["AGENT_PROPOSED"]
    adoption: Literal["PENDING"]
    value: Value


class Missing(_Closed):
    field_name: FieldName
    state: Literal["MISSING"]


class Alternative(_Closed):
    value: Value
    source_passage: str


class Conflicting(_Closed):
    field_name: FieldName
    state: Literal["CONFLICTING"]
    conflicts: list[Alternative]


class Option(_Closed):
    id: str
    label: str
    value: Value


class Question(_Closed):
    question_id: str
    field_name: FieldName
    text: str
    options: list[Option]


class Interpretation(_Closed):
    meaning_status: Literal["SUPPORTED", "UNSUPPORTED"]
    missing_capability: str | None
    evidence_readiness: Literal["READY", "UNRESOLVED"]
    field_evidence: list[Union[Stated, Proposed, Missing, Conflicting]]
    questions: list[Question]


class _StrictSubset(GenerateJsonSchema):
    """Pydantic's schema in the provider's strict subset: one-value literals as `enum`, no generated titles."""

    def literal_schema(self, schema: Any) -> dict[str, Any]:
        return {"type": "string", "enum": [str(value) for value in schema["expected"]]}

    def field_title_should_be_set(self, schema: Any) -> bool:
        return False

    def model_schema(self, schema: Any) -> dict[str, Any]:
        generated = super().model_schema(schema)
        generated.pop("title", None)
        return generated


@functools.cache
def _schema() -> dict[str, Any]:
    return Interpretation.model_json_schema(schema_generator=_StrictSubset)


def interpretation_response_format() -> dict[str, Any]:
    """The provider `response_format` for one interpretation. Each call returns its own copy, safe to change."""
    return {"type": "json_schema",
            "json_schema": {"name": RESPONSE_FORMAT_NAME, "strict": True, "schema": copy.deepcopy(_schema())}}


def conforms(decoded: Any) -> bool:
    """Whether a decoded answer has the schema's structure (strict: no coercion). Says nothing about its meaning."""
    try:
        Interpretation.model_validate(decoded, strict=True)
    except ValidationError:
        return False
    return True
