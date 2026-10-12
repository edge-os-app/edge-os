"""Versioned typed request, evidence and report models.

Every structure is a frozen dataclass. ``to_dict`` and ``from_dict`` give a
deterministic JSON round-trip through :mod:`edge_os_api.nansen_research.serialization`.
The schema strings are the version identities frozen in
``docs/qualification/nansen-report/INTERFACE_FREEZE.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from edge_os_api.nansen_research.errors import NansenLimitError, NansenRequestError
from edge_os_api.nansen_research.serialization import (
    canonical_sha256,
    parse_instant,
    to_plain,
)

REQUEST_SCHEMA = "nansen-research-request/1"
EVIDENCE_SCHEMA = "nansen-research-evidence/1"
REPORT_SCHEMA = "nansen-research-report/1"

PROVIDER = "NANSEN_TGM"
PROVIDER_VERSION = "nansen-tgm/1"
ENDPOINT = "https://api.nansen.ai"
NETWORK = "monad"
CHAIN_ID = 143
API_SCHEMA_VERSION = "1.0.0"
PROFILE_VERSION = "nansen-descriptive-reviewed/1"
CONVENTIONS_VERSION = "d01-conventions/1"

OPERATION_NAMES = ("holders", "flows")


class Model:
    """Mixin that gives every frozen model a deterministic JSON round-trip."""

    def to_dict(self) -> dict:
        return to_plain(self)

    @classmethod
    def from_dict(cls, data: dict):
        from edge_os_api.nansen_research.serialization import from_plain

        return from_plain(cls, data)

    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True)
class ObservationWindow(Model):
    """The requested observation window. ``end_utc`` is the inclusive flow cutoff."""

    start_utc: str
    end_utc: str

    def validate(self) -> None:
        start = parse_instant(self.start_utc)
        end = parse_instant(self.end_utc)
        if start >= end:
            raise NansenRequestError("WINDOW_INVALID", "window start must be before end")


@dataclass(frozen=True)
class HolderQuery(Model):
    """The pinned holder query. ``value_usd_min`` is ``None`` to send no filter."""

    label_type: str = "all_holders"
    aggregate_by_entity: bool = False
    order_field: str = "token_amount"
    value_usd_min: int | None = None

    def validate(self) -> None:
        if self.label_type not in ("whale", "public_figure", "smart_money", "all_holders", "exchange"):
            raise NansenRequestError("HOLDER_LABEL_INVALID", f"unknown holder label {self.label_type!r}")
        if self.order_field not in ("address", "token_amount", "ownership_percentage", "value_usd"):
            raise NansenRequestError("HOLDER_ORDER_INVALID", f"unknown order field {self.order_field!r}")
        if self.value_usd_min is not None and (
            isinstance(self.value_usd_min, bool) or not isinstance(self.value_usd_min, int)
        ):
            raise NansenRequestError("HOLDER_FILTER_INVALID", "value_usd_min must be an integer or None")


@dataclass(frozen=True)
class FlowQuery(Model):
    """The pinned flow query. There is no all-holder flow label in the schema."""

    label: str = "top_100_holders"

    def validate(self) -> None:
        if self.label not in ("whale", "public_figure", "smart_money", "top_100_holders", "exchange"):
            raise NansenRequestError("FLOW_LABEL_INVALID", f"unknown flow label {self.label!r}")


@dataclass(frozen=True)
class NansenLimits(Model):
    """Finite caller-supplied bounds. Local test parameters, not provider allowances."""

    max_requests: int
    max_pages: int
    max_bytes: int
    max_credits: Decimal
    per_page: int = 100
    deadline_utc: str | None = None

    def validate(self) -> None:
        for name, value in (("max_requests", self.max_requests), ("max_pages", self.max_pages),
                            ("max_bytes", self.max_bytes), ("per_page", self.per_page)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise NansenLimitError(f"{name} must be a positive integer")
        if self.per_page > 1000:
            raise NansenLimitError("per_page must be at most 1000")
        if not isinstance(self.max_credits, Decimal) or not self.max_credits.is_finite() or self.max_credits <= 0:
            raise NansenLimitError("max_credits must be a finite positive decimal")
        if self.deadline_utc is not None:
            if not isinstance(self.deadline_utc, str):
                raise NansenLimitError("deadline_utc must be an ISO-8601 UTC string or None")
            parse_instant(self.deadline_utc)


@dataclass(frozen=True)
class NansenRequest(Model):
    """The exact question and query the report must answer."""

    question: str
    token_address: str
    token_symbol: str
    window: ObservationWindow
    operations: tuple[str, ...]
    limits: NansenLimits
    holder_query: HolderQuery = HolderQuery()
    flow_query: FlowQuery = FlowQuery()
    network: str = NETWORK
    chain_id: int = CHAIN_ID
    profile_version: str = PROFILE_VERSION
    conventions_version: str = CONVENTIONS_VERSION
    request_schema: str = REQUEST_SCHEMA

    def validate(self) -> None:
        if self.request_schema != REQUEST_SCHEMA:
            raise NansenRequestError("REQUEST_SCHEMA_INVALID", f"expected {REQUEST_SCHEMA}")
        if not isinstance(self.question, str) or not self.question.strip():
            raise NansenRequestError("QUESTION_INVALID", "question must be non-empty text")
        if not isinstance(self.token_address, str) or not self.token_address.strip():
            raise NansenRequestError("TOKEN_INVALID", "token_address must be non-empty text")
        if self.network != NETWORK:
            raise NansenRequestError("WRONG_NETWORK", f"network must be {NETWORK}")
        if self.chain_id != CHAIN_ID:
            raise NansenRequestError("WRONG_NETWORK", f"chain_id must be {CHAIN_ID}")
        self.window.validate()
        self.holder_query.validate()
        self.flow_query.validate()
        self.limits.validate()
        if not self.operations:
            raise NansenRequestError("OPERATIONS_EMPTY", "at least one operation is required")
        for operation in self.operations:
            if operation not in OPERATION_NAMES:
                raise NansenRequestError("OPERATION_NOT_ALLOWED", f"unknown operation {operation!r}")


@dataclass(frozen=True)
class NansenContext(Model):
    """The served provider identity. Owned by the caller of the client."""

    network: str = NETWORK
    chain_id: int = CHAIN_ID
    provider: str = PROVIDER
    provider_version: str = PROVIDER_VERSION
    endpoint: str = ENDPOINT
    api_schema_version: str = API_SCHEMA_VERSION

    def validate(self) -> None:
        if self.network != NETWORK or self.chain_id != CHAIN_ID:
            raise NansenRequestError("WRONG_NETWORK", "context network must be Monad mainnet")
        if self.provider != PROVIDER:
            raise NansenRequestError("CONTEXT_INVALID", f"provider must be {PROVIDER}")
        if not isinstance(self.endpoint, str) or not self.endpoint:
            raise NansenRequestError("CONTEXT_INVALID", "endpoint must be non-empty text")


@dataclass(frozen=True)
class HolderRow(Model):
    """One provider holder row. Numbers stay as exact text or null."""

    address: str | None
    token_amount: str | None
    ownership_percentage: str | None
    value_usd: str | None
    address_label: str | None


@dataclass(frozen=True)
class FlowBucket(Model):
    """One provider flow bucket. Numbers stay as exact text or null."""

    date: str
    bucket_end: str | None
    is_complete: bool | None
    price_usd: str | None
    token_amount: str | None
    value_usd: str | None
    holders_count: str | None
    total_inflows_count: str | None
    total_outflows_count: str | None
    total_inflows_dex: str | None
    total_outflows_dex: str | None
    total_inflows_cex: str | None
    total_outflows_cex: str | None


@dataclass(frozen=True)
class SourceRecord(Model):
    """The request/response facts retained for one provider call."""

    operation: str
    method: str
    path: str
    request_body: dict
    request_sha256: str
    status: int | None
    request_id: str | None
    quoted_credits: str | None
    deducted_credits: str | None
    remaining_credits: str | None
    response_sha256: str | None
    collected_at: str
    failure: str | None


@dataclass(frozen=True)
class HolderEvidence(Model):
    rows: tuple[HolderRow, ...]
    pagination_is_last_page: bool | None
    pages: int
    duplicate_addresses: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FlowEvidence(Model):
    buckets: tuple[FlowBucket, ...]
    expected_starts: tuple[str, ...]
    missing_starts: tuple[str, ...]
    duplicate_starts: tuple[str, ...]
    incomplete_starts: tuple[str, ...]
    complete_seconds: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class NansenEvidence(Model):
    """The immutable evidence package the report is bound to."""

    question: str
    token_address: str
    token_symbol: str
    network: str
    chain_id: int
    window: ObservationWindow
    provider: str
    provider_version: str
    endpoint: str
    api_schema_version: str
    profile_version: str
    conventions_version: str
    sources: tuple[SourceRecord, ...]
    attempts: int
    pages: int
    reserved_credits: str
    holder: HolderEvidence | None
    flows: FlowEvidence | None
    stop_reason: str | None
    unknowns: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_schema: str = EVIDENCE_SCHEMA


@dataclass(frozen=True)
class Finding(Model):
    code: str
    verdict: str
    statement: str
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class UnsupportedQuestion(Model):
    question: str
    missing_dependency: str


@dataclass(frozen=True)
class Coverage(Model):
    attempts: int
    pages: int
    holder_rows: int
    flow_buckets: int
    expected_buckets: int
    missing_buckets: int
    incomplete_buckets: int
    complete_seconds: int
    pagination_is_last_page: bool | None
    stop_reason: str | None


@dataclass(frozen=True)
class NansenReport(Model):
    """The deterministic, source-linked report returned to the consumer."""

    question: str
    token_address: str
    token_symbol: str
    network: str
    chain_id: int
    window: ObservationWindow
    request_sha256: str
    findings: tuple[Finding, ...]
    unsupported_questions: tuple[UnsupportedQuestion, ...]
    coverage: Coverage
    unknowns: tuple[str, ...]
    source_hashes: tuple[str, ...]
    engine: dict[str, str]
    report_schema: str = REPORT_SCHEMA
