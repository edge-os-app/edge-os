"""Declared types, coverage classes and reason codes for the offline
independent wallet-policy binding.

Standard library and the offline Flow adapter types only. This module has no
network, credential, signing or broadcast code path. A local pass is authored
behavior; it is never an independent provider result.

Coverage classes are derived from the reviewed public sources. A control is
``documented`` when a published example shows the condition, ``unproven`` when
the condition is attempted but the provider support is not published, and
``unexpressible`` when the policy cannot read the needed fact.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import Field, field_validator

from ..types import FrozenModel, StrictModel

POLICY_SCHEMA_VERSION = "1.0"
POLICY_CHAIN_TYPE = "ethereum"
PROVIDER_EXECUTED = "NOT_RUN"

RESULT_AUTHORED_POLICY_ALLOW = "AUTHORED_POLICY_ALLOW"
RESULT_BLOCKED = "BLOCKED"

POLICY_ACTION_ALLOW = "ALLOW"
POLICY_ACTION_DENY = "DENY"

R_POLICY_REQUEST_INCOMPLETE = "POLICY_REQUEST_INCOMPLETE"
R_POLICY_PROVIDER_EXECUTED = "POLICY_PROVIDER_EXECUTED"
R_POLICY_NO_ALLOW_RULE = "POLICY_NO_ALLOW_RULE"
R_POLICY_DENY_RULE = "POLICY_DENY_RULE"
R_POLICY_ADMIN_OWNER_MISSING = "POLICY_ADMIN_OWNER_MISSING"
R_POLICY_ADMIN_NOT_SEPARATED = "POLICY_ADMIN_NOT_SEPARATED"

MAX_RULES = 32
MAX_CONDITIONS_PER_RULE = 64
MAX_CONDITION_VALUE_ITEMS = 256

DOCUMENTED_CONTROLS: tuple[str, ...] = ("chain", "entrypoint_method", "native_value")
UNPROVEN_CONTROLS: tuple[str, ...] = (
    "input_output_assets",
    "raw_input",
    "minimum_output",
    "recipient",
    "fees",
    "opaque_program",
)
UNEXPRESSIBLE_CONTROLS: tuple[str, ...] = ("position_inventory",)


class PolicyFieldSource(str, enum.Enum):
    """The documented Privy condition field sources used by this binding."""

    ETHEREUM_TRANSACTION = "ethereum_transaction"
    ETHEREUM_CALLDATA = "ethereum_calldata"


class PolicyOperator(str, enum.Enum):
    """The documented Privy condition operators."""

    EQ = "eq"
    NEQ = "neq"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    IN_CONDITION_SET = "in_condition_set"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class PolicyAction(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PolicyCondition(StrictModel):
    """One declared Privy policy condition."""

    field_source: PolicyFieldSource
    field: str = Field(min_length=1, max_length=200)
    operator: PolicyOperator
    value: str | list[str]
    abi: list[dict[str, Any]] | None = None

    @field_validator("value")
    @classmethod
    def value_is_bounded(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, list):
            if not value or len(value) > MAX_CONDITION_VALUE_ITEMS:
                raise ValueError(
                    f"a list condition value must hold 1..{MAX_CONDITION_VALUE_ITEMS} items"
                )
            if any(not isinstance(item, str) for item in value):
                raise ValueError("condition list items must be strings")
        return value


class PolicyRule(StrictModel):
    """One declared Privy policy rule."""

    name: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=80)
    action: PolicyAction
    conditions: list[PolicyCondition] = Field(
        min_length=1, max_length=MAX_CONDITIONS_PER_RULE
    )


class PolicyRequest(FrozenModel):
    """A frozen, Privy-shaped policy request. It is data, not a live change.

    ``owner_id`` mirrors the optional Privy policy owner. Absent ownership is a
    documented ownerless policy; the application secret can then update it.
    """

    version: str = POLICY_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=200)
    chain_type: str = POLICY_CHAIN_TYPE
    rules: list[PolicyRule] = Field(max_length=MAX_RULES)
    owner_id: str | None = None

    @field_validator("version")
    @classmethod
    def version_is_supported(cls, value: str) -> str:
        if value != POLICY_SCHEMA_VERSION:
            raise ValueError(f"unsupported policy schema version {value!r}")
        return value

    @field_validator("chain_type")
    @classmethod
    def chain_type_is_supported(cls, value: str) -> str:
        if value != POLICY_CHAIN_TYPE:
            raise ValueError(f"unsupported policy chain type {value!r}")
        return value


class PreparedPolicyRequest(FrozenModel):
    """A policy request plus its coverage split and provider state.

    ``provider_executed`` is always ``NOT_RUN``. The coverage classes keep the
    documented, unproven and unexpressible controls separate. The administration
    fields record the required policy-resource owner. An absent owner is the
    documented ownerless policy and keeps administration separation unresolved.
    """

    wallet_id: str = Field(min_length=1, max_length=200)
    request: PolicyRequest
    documented_controls: tuple[str, ...]
    unproven_controls: tuple[str, ...]
    unexpressible_controls: tuple[str, ...]
    policy_owner_id: str | None = None
    administration_separated: bool = False
    provider_executed: str = PROVIDER_EXECUTED


class PolicyFacts(StrictModel):
    """The declared facts a local simulation evaluates. Absent facts are unknown."""

    rpc_method: str = Field(min_length=1, max_length=80)
    chain_id: str = Field(min_length=1, max_length=40)
    to: str = Field(min_length=1, max_length=200)
    function_name: str = Field(min_length=1, max_length=80)
    value_raw: str | None = None
    arguments: dict[str, str] = Field(default_factory=dict)


class PolicySimulationVerdict(StrictModel):
    """The result of one authored local simulation."""

    allowed: bool
    result_class: str
    matched_rule: str | None = None
    reasons: list[str] = Field(default_factory=list)
    provider_executed: str = PROVIDER_EXECUTED
    independent_provider_pass: bool = False
