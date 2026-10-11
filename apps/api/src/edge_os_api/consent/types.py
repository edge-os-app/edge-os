"""Strict typed models for the inactive controlled-qualification consent domain.

Every reviewed amount is an asset-specific canonical raw integer with decimals.
Amounts that name different assets are never summed. A request never carries an
owner: the service derives the owner from the verified identity. A consent is
always INACTIVE. This module mints no active authority and exposes no
activation, signing, admission, scheduler or provider-policy operation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The two accepted Monad networks. Approval for one does not approve the other.
NETWORKS = ("monad:143", "monad-testnet:10143")
# Accepted economic operations (P15 / compiler action scope).
OPERATIONS = ("ENTRY", "ADDITION", "EXIT")
OPERATING_PURPOSES = ("ONGOING", "TRIAL")
# Evidence classes from the accepted account-view contract. UNKNOWN is explicit.
EVIDENCE_STATUSES = ("HYPOTHESIS", "DESCRIPTIVE_ONLY", "UNRESOLVED", "SUPPORTED", "CONFLICTED", "UNKNOWN")
# Inactive preparation may retain only explicitly unqualified or unknown
# route/policy evidence. A QUALIFIED value is deliberately not representable so
# this stage can never claim a live operational gate passed.
UNQUALIFIED_STATES = ("UNQUALIFIED", "UNKNOWN")
CONSENT_STATUS = "INACTIVE"
# Storage bound: the accepted funding ledger uses NUMERIC(78, 0). A raw integer
# longer than this cannot be stored exactly by that accepted ledger, so consent
# rejects it at validation too.
MAX_RAW_DIGITS = 78

AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def canonical_sha256(payload: dict[str, Any]) -> str:
    """One canonical SHA256 for every reviewed or adopted meaning. Never a second hash shape."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("an identifier must not be blank")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def parse_utc(value: str) -> dt.datetime:
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as error:
        raise ValueError("timestamps must be RFC 3339 UTC") from error
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamps must carry an explicit UTC offset")
    return moment.astimezone(dt.timezone.utc)


class AssetAmount(StrictModel):
    """An asset-specific canonical unsigned base-10 raw integer with decimals."""

    asset_id: str = Field(min_length=1, max_length=200)
    raw: str = Field(pattern=r"^(?:0|[1-9][0-9]*)$")
    decimals: int = Field(ge=0, le=255)

    @field_validator("raw")
    @classmethod
    def raw_within_storage_bound(cls, value: str) -> str:
        if len(value) > MAX_RAW_DIGITS:
            raise ValueError(f"raw amount exceeds the {MAX_RAW_DIGITS}-digit storage bound")
        return value

    def as_int(self) -> int:
        return int(self.raw)


class ReviewedRoute(StrictModel):
    """The proposed execution route. Inactive preparation keeps it unqualified."""

    adapter: str = Field(min_length=1, max_length=120)
    qualification: Literal["UNQUALIFIED", "UNKNOWN"] = "UNQUALIFIED"
    identity_state: Literal["KNOWN", "UNKNOWN"] = "UNKNOWN"
    identity: str | None = Field(default=None, max_length=200)

    @field_validator("adapter")
    @classmethod
    def adapter_not_blank(cls, value: str) -> str:
        return _not_blank(value)

    @model_validator(mode="after")
    def identity_matches_state(self) -> "ReviewedRoute":
        if (self.identity_state == "KNOWN") != (self.identity is not None):
            raise ValueError("a known route identity requires an identity value")
        return self


class ReviewedPolicy(StrictModel):
    """The attached signer/policy binding, when one is present. Never qualified here."""

    policy_id: str = Field(min_length=1, max_length=200)
    status: Literal["UNQUALIFIED", "UNKNOWN"]
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("policy_id")
    @classmethod
    def policy_id_not_blank(cls, value: str) -> str:
        return _not_blank(value)


class ReviewedEvidence(StrictModel):
    """The evidence status and limitations carried by the exact revision."""

    status: Literal["HYPOTHESIS", "DESCRIPTIVE_ONLY", "UNRESOLVED", "SUPPORTED", "CONFLICTED", "UNKNOWN"]
    source: str = Field(min_length=1, max_length=120)
    material_limitations: list[str] = Field(default_factory=list, max_length=20)
    historical_success_required: Literal[False] = False


class AllowanceTerm(StrictModel):
    """One cumulative per-asset allowance term of the reviewed mandate."""

    name: str = Field(min_length=1, max_length=40)
    amount: AssetAmount

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _not_blank(value)


class ReviewedTerms(StrictModel):
    """The exact, adopted-meaning terms shown in one grouped review.

    Required limits are required. Zero is a valid explicit amount and is distinct
    from an absent or unknown limit. Optional limits stay `None` (unknown) and are
    never replaced with an invented number.
    """

    terms_version: str = Field(min_length=1, max_length=40)
    operating_purpose: Literal["ONGOING", "TRIAL"]
    trial_objective: str | None = Field(default=None, max_length=200)
    allocation: list[AssetAmount] = Field(min_length=1, max_length=20)
    allowances: list[AllowanceTerm] = Field(min_length=1, max_length=20)
    attempt_budget: int = Field(ge=0, le=1_000_000)
    gas_budget: AssetAmount | None = None
    expiry: str = Field(min_length=1, max_length=40)
    supported_actions: list[str] = Field(min_length=1, max_length=20)
    supported_assets: list[str] = Field(min_length=1, max_length=50)
    supported_routes: list[str] = Field(min_length=1, max_length=50)
    route: ReviewedRoute
    policy: ReviewedPolicy | None = None
    signer: str | None = Field(default=None, max_length=200)
    evidence: ReviewedEvidence
    stop_effects: list[str] = Field(min_length=1, max_length=20)

    @field_validator("expiry")
    @classmethod
    def expiry_must_parse(cls, value: str) -> str:
        parse_utc(value)
        return value

    @field_validator("supported_routes")
    @classmethod
    def routes_must_not_be_blank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("a supported route must not be blank")
        return values

    @field_validator("stop_effects")
    @classmethod
    def stop_effects_must_not_be_blank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("a stop effect must not be blank")
        return values

    @field_validator("signer")
    @classmethod
    def signer_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("a signer identifier must not be blank")
        return value

    @field_validator("supported_actions")
    @classmethod
    def actions_must_be_supported(cls, values: list[str]) -> list[str]:
        unknown = [value for value in values if value not in OPERATIONS]
        if unknown:
            raise ValueError(f"unsupported approved actions: {unknown}")
        if len(set(values)) != len(values):
            raise ValueError("approved actions must be unique")
        return values

    @model_validator(mode="after")
    def terms_are_consistent(self) -> "ReviewedTerms":
        if self.operating_purpose == "TRIAL" and (self.trial_objective is None or not self.trial_objective.strip()):
            raise ValueError("a TRIAL operating purpose requires its learning objective")
        if self.operating_purpose == "ONGOING" and self.trial_objective is not None:
            raise ValueError("an ONGOING operating purpose does not carry a trial objective")
        names = [term.name for term in self.allowances]
        if len(set(names)) != len(names):
            raise ValueError("allowance names must be unique")
        allocation_assets = [amount.asset_id for amount in self.allocation]
        if len(set(allocation_assets)) != len(allocation_assets):
            raise ValueError("allocation assets must be unique")
        if self.gas_budget is not None and self.gas_budget.asset_id in allocation_assets:
            raise ValueError("the native gas budget stays separate from the allocated capital")
        return self

    def content_hash(self) -> str:
        """Canonical SHA256 of the full reviewed meaning, independent of the fixture label."""
        return canonical_sha256(self.model_dump(mode="json", exclude_none=False))


class ReviewRequest(StrictModel):
    """A request to review one exact saved revision, wallet and term set. Never an owner."""

    agent_id: str = Field(min_length=1, max_length=64)
    strategy_id: str = Field(min_length=1, max_length=200)
    strategy_revision_id: str = Field(min_length=1, max_length=64)
    network_id: str = Field(min_length=1, max_length=40)
    terms: ReviewedTerms

    @field_validator("agent_id")
    @classmethod
    def agent_id_is_url_safe(cls, value: str) -> str:
        if AGENT_ID.fullmatch(value) is None:
            raise ValueError("the agent ID must use 1 to 64 URL-safe characters")
        return value

    @field_validator("network_id")
    @classmethod
    def network_must_be_supported(cls, value: str) -> str:
        if value not in NETWORKS:
            raise ValueError("the network must name Monad 143 or testnet 10143")
        return value


class AdoptionRequest(StrictModel):
    """A request to adopt one exact, previously reviewed meaning. Never an owner."""

    review_id: str = Field(min_length=1, max_length=64)
    expected_review_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class GroupedReviewView(StrictModel):
    """The owner-scoped grouped review returned by the review seam."""

    review_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    strategy_id: str
    strategy_revision_id: uuid.UUID
    content_sha256: str
    manifest_sha256: str
    terms_version: str
    terms_hash: str
    review_hash: str
    status: Literal["INACTIVE"]
    content: dict[str, Any]
    created_at: str


class ConsentView(StrictModel):
    """The owner-scoped, clearly INACTIVE consent returned by the adopt/read seams."""

    adoption_id: uuid.UUID
    owner_id: uuid.UUID
    review_id: uuid.UUID
    review_hash: str
    consent_hash: str
    status: Literal["INACTIVE"]
    content: dict[str, Any]
    created_at: str
