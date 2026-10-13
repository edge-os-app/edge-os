"""Owner-scoped recorded-history datasets (`edge-os.history-dataset/1`).

This module is the #58 consumer of the accepted P07 `research_history` library. It serves only the declared recorded
sources in the local bundle, collects through P07 `collect`, qualifies through P07 `normalize`, and saves the result
verbatim beside the owner's declaration. It never relabels a fixture as observed history, never turns a LIMITED or
UNRESOLVED verdict into a market binding, and never fills a missing bucket. It opens no socket and reads no credential.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, MetaData, Text, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import not_found
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research.service import parse_uuid
from edge_os_api.research_history import (
    CollectionLimits,
    HistoryRequest,
    RecordedResponseSource,
    SourceCancelled,
    SourceFailure,
    SourceTimeout,
    collect,
    normalize,
    project_binding,
)
from edge_os_api.research_history.qualification_engine import raw_sha256
from edge_os_api.strategies import compiler as strategy_compiler

DATASET_VERSION = "edge-os.history-dataset/1"
P07_PROFILE_VERSION = "p07.market_dataset_profile/1"
BUNDLE_VERSION = "edge-os.recorded-history-bundle/1"
BUNDLE_PATH = (Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "research_history_recorded"
               / "recorded_history_v1.json")
NATIVE_BUNDLE_VERSION = "edge-os.recorded-native-bundle/1"
NATIVE_BUNDLE_PATH = (Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "research_history_native"
                      / "native_history_v1.json")
NATIVE_CLASS = "RECORDED_NATIVE_RESPONSE"
# A native-shaped source collected through the accepted P07 HTTP clients over the application's AUTHORED transport.
HTTP_CLASS = "AUTHORED_HTTP_RESPONSE"
NATIVE_SHAPED = frozenset({NATIVE_CLASS, HTTP_CLASS})
HTTP_SOURCE_ID = "native-http-qualified/1"
HTTP_SOURCE_OF = "native-syn-qualified/1"
COMPLETE_STATUSES = frozenset({"COMPLETE_OCCUPIED", "COMPLETE_EMPTY"})
UNAVAILABLE_STATES = ("SOURCE_UNAVAILABLE", "PARTIAL_COVERAGE", "VERDICT_LIMITED", "VERDICT_UNRESOLVED")
# Partitions whose outcomes no research surface may read: the comparison skips them and replays stop before them.
PROTECTED_ROLES = frozenset({"VALIDATION", "HOLDOUT"})

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}


class ResearchBase(DeclarativeBase):
    """#58 research tables. Migration 0009 creates them in the `research_local` schema."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="research_local")


class HistoryDatasetRow(ResearchBase):
    """One immutable saved dataset. The raw records stay beside it so their hash can be recomputed."""

    __tablename__ = "history_datasets"
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_records: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                    server_default=text("now()"))
    __table_args__ = (CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="hash"),)


class FaultingRecordedSource:
    """Serves recorded responses in order; a `{"fault": ...}` entry raises the matching P07 source failure.

    The fault entries are part of the authored recording. They let a local run show a provider failure or a timeout
    without a network. Any other fault name is an authoring defect and raises `ValueError`.
    """

    def __init__(self, responses: Sequence[Mapping[str, Any]], cancelled: Callable[[], bool] | None = None) -> None:
        self._responses = list(responses)
        self._cancelled = cancelled or (lambda: False)
        self._index = 0

    def next_response(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        if self._cancelled():
            raise SourceCancelled("cancellation requested before the next page")
        if self._index >= len(self._responses):
            return None
        item = self._responses[self._index]
        self._index += 1
        fault = item.get("fault")
        if fault == "SOURCE_FAILURE":
            raise SourceFailure("recorded provider failure")
        if fault == "SOURCE_TIMEOUT":
            raise SourceTimeout("recorded provider timeout")
        if fault is not None:
            raise ValueError(f"unknown recorded fault {fault!r}")
        return RecordedResponseSource([item]).next_response(request)


@functools.lru_cache(maxsize=1)
def _bundle() -> dict[str, Any]:
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != BUNDLE_VERSION:
        raise ValueError("recorded history bundle has an unsupported version")
    return bundle


@functools.lru_cache(maxsize=1)
def _native_bundle() -> dict[str, Any]:
    bundle = json.loads(NATIVE_BUNDLE_PATH.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != NATIVE_BUNDLE_VERSION:
        raise ValueError("native recorded history bundle has an unsupported version")
    return bundle


def _http_source() -> dict[str, Any]:
    """The SOURCE-LOCAL qualified recording served through the P07 HTTP clients. Same profile, scan and declared facts;
    its own id and class. The recording itself keeps its own class and meaning."""
    native = next(source for source in _native_bundle()["sources"] if source["source_id"] == HTTP_SOURCE_OF)
    return {**native, "source_id": HTTP_SOURCE_ID, "evidence_class": HTTP_CLASS, "http_of": HTTP_SOURCE_OF,
            "title": "Native recording through the HTTP clients (authored transport, qualifies)"}


def recorded_sources() -> dict[str, dict[str, Any]]:
    """Every declared recorded source by id, from both bundles. Each one is a SYNTHETIC recording, not observed
    history. `RECORDED_NATIVE_RESPONSE` sources replay native pages through the P07 transport with recorded clients;
    the `AUTHORED_HTTP_RESPONSE` source runs the same pages through the accepted P07 HTTP clients."""
    sources = [*_bundle()["sources"], *_native_bundle()["sources"], _http_source()]
    return {source["source_id"]: source for source in sources}


def page_requests(source: Mapping[str, Any]) -> int:
    """Recorded history page requests the source needs (including a recorded fault)."""
    return len(source["envio_pages"] if source["evidence_class"] in NATIVE_SHAPED else source["responses"])


def requests_needed(source: Mapping[str, Any]) -> int:
    """Provider requests a full collection needs: pages, plus one chain read and one receipt per sample (native)."""
    if source["evidence_class"] not in NATIVE_SHAPED:
        return page_requests(source)
    return page_requests(source) + 1 + int(source["corroboration_sample_size"])


def transport_view(source: Mapping[str, Any]) -> dict[str, Any] | None:
    if source["evidence_class"] not in NATIVE_SHAPED:
        return None
    view = {"history_provider": "ENVIO_HYPERSYNC", "provider_version": "envio-hypersync/1",
            "corroboration_provider": "QUICKNODE_JSON_RPC",
            "corroboration_sample_size": source["corroboration_sample_size"],
            "provider_requests_needed": requests_needed(source)}
    if source["evidence_class"] == HTTP_CLASS:  # additive; the recorded sources' view is unchanged
        view["clients"] = "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT"
    return view


def profile_sha256(source: Mapping[str, Any]) -> str:
    return hashlib.sha256(record_contract.canonical_bytes(source["profile"])).hexdigest()


def source_market(source: Mapping[str, Any]) -> dict[str, str]:
    profile = source["profile"]
    tokens = {token["role"]: token["address"] for token in profile["pool_tokens"]}
    return {"network": profile["network"]["network"], "pool_address": profile["venue"]["pool_address"],
            "base_asset": tokens["BASE"], "quote_asset": tokens["QUOTE"]}


def source_window(source: Mapping[str, Any]) -> dict[str, str]:
    window = source["profile"]["dataset"]["window"]
    return {"start": window["start_utc"], "end": window["end_utc"]}


def catalog(http_clients_available: bool = False) -> dict[str, Any]:
    """The supported recorded sources, as a user reviews them before declaring one. `available` is false for the HTTP
    source unless this server composes the HTTP clients; a job on an unavailable source is refused before effect."""
    return {"label": _bundle()["label"], "native_label": _native_bundle()["label"], "sources": [
        {"source_id": source_id, "title": source["title"], "evidence_class": source["evidence_class"],
         "available": source["evidence_class"] != HTTP_CLASS or http_clients_available,
         "content_label": source["content_label"], "profile_version": P07_PROFILE_VERSION,
         "profile_sha256": profile_sha256(source), "market": source_market(source), "window": source_window(source),
         "history_provider": source["profile"]["source"]["history_provider"],
         "page_requests_recorded": page_requests(source), "transport": transport_view(source)}
        for source_id, source in recorded_sources().items()]}


def provider_usage(source: Mapping[str, Any]) -> tuple[str, dict[str, int] | None]:
    """Evidenced provider request counts. Missing is UNKNOWN; anything malformed is INVALID. Neither is zero."""
    supplied = source.get("provider_requests")
    if supplied is None:
        return "UNKNOWN", None
    if (isinstance(supplied, dict) and supplied and all(isinstance(key, str) for key in supplied)
            and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
                    for value in supplied.values())):
        return "SUPPLIED_EVIDENCE", dict(supplied)
    return "INVALID", None


def collect_recorded(source: Mapping[str, Any], bounds: Mapping[str, Any], deadline_utc: str | None,
                     cancelled: Callable[[], bool], clock: Callable[[], str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """One bounded P07 collection and normalization. P07 partial results return; other errors propagate."""
    limits = CollectionLimits(max_pages=bounds["max_pages"], max_rows=bounds["max_rows"],
                              max_bytes=bounds["max_bytes"], deadline_utc=deadline_utc)
    collection = collect(source["profile"], FaultingRecordedSource(source["responses"], cancelled), source["scan"],
                         limits, clock=clock)
    return collection, normalize(source["profile"], collection, source["evidence"])


def _trades(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    """P07 trades with their recorded block time and the availability of the bucket that holds them."""
    times = {(record["block_number"], record["transaction_index"], record["log_index"]): int(record["block_timestamp"])
             for record in normalized["raw_records"] if isinstance(record, Mapping)}
    buckets = normalized["buckets"]
    rows = []
    for trade in normalized["trades"]:
        moment = dt.datetime.fromtimestamp(times[(trade["block_number"], trade["transaction_index"],
                                                  trade["log_index"])], dt.timezone.utc)
        event_time = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        bucket = next((item for item in buckets if item["bucket_start"] <= event_time < item["bucket_end"]), None)
        rows.append({"event_id": trade["identity"], "event_time": event_time, "price": trade["price"],
                     "quote_amount": trade["quote_amount"], "base_amount": trade["base_amount"],
                     "pool_side": trade["pool_side"], "block_number": trade["block_number"],
                     "transaction_index": trade["transaction_index"], "log_index": trade["log_index"],
                     "available_at": None if bucket is None else bucket["available_at"],
                     "qualified": bucket is not None and bucket["status"] == "COMPLETE_OCCUPIED"})
    return rows


def strategy_market(binding: Mapping[str, Any]) -> dict[str, Any]:
    """The P02 strategy market for a projected QUALIFIED binding. The execution route stays unqualified."""
    return {"network": "MONAD", "research_binding": dict(binding),
            "execution_route": {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None,
                                "qualification": "UNQUALIFIED"},
            "quote_unit": f"QUOTE:{binding['quote_asset']}"}


def measured_usage(transport: Mapping[str, Any]) -> tuple[str, dict[str, int] | None]:
    """Native usage: the made client calls, known only while they stay within the job's request reservation.

    Through the HTTP clients a made call whose reply did not complete may still have been served: any client
    `unknown_liability` makes the usage UNKNOWN, so the whole reservation stays unknown liability."""
    calls = dict(transport["client_calls"])
    if any(item["unknown_liability"] for item in (transport.get("http_accounting") or {}).values()):
        return "UNKNOWN", None
    if sum(calls.values()) <= transport["request_budget"]:
        return "MEASURED_CLIENT_CALLS", calls
    return "INVALID", None


def dataset_content(*, dataset_id: uuid.UUID, owner_id: uuid.UUID, declaration_id: uuid.UUID, job_id: uuid.UUID,
                    attempt_id: uuid.UUID, source: Mapping[str, Any], collection: Mapping[str, Any],
                    normalized: Mapping[str, Any], transport: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The `edge-os.history-dataset/1` record. Verdicts, buckets and gaps are copied, never upgraded.

    A native source adds `transport` and `evidence_basis` (additive keys); a bundle source's content is unchanged."""
    qualification = normalized["qualification"]
    overall = qualification["overall"]
    usage_state, usage = provider_usage(source) if transport is None else measured_usage(transport)
    binding = None
    if overall == "QUALIFIED" and collection["status"] == "COMPLETE":
        binding = project_binding(normalized["bound_profile"], qualification)
    unavailable = []
    if collection["stop_reason"] in {"PROVIDER_ERROR", "TIMEOUT"}:
        unavailable.append("SOURCE_UNAVAILABLE")
    if collection["status"] != "COMPLETE":
        unavailable.append("PARTIAL_COVERAGE")
    if overall == "LIMITED":
        unavailable.append("VERDICT_LIMITED")
    if overall == "UNRESOLVED":
        unavailable.append("VERDICT_UNRESOLVED")
    profile = source["profile"]
    market = None if binding is None else strategy_market(binding)
    content = {
        "schema_version": DATASET_VERSION, "dataset_id": str(dataset_id), "owner_id": str(owner_id),
        "declaration_id": str(declaration_id), "job_id": str(job_id), "attempt_id": str(attempt_id),
        "source_id": source["source_id"], "evidence_class": source["evidence_class"],
        "content_label": source["content_label"], "profile_evidence_class": profile["evidence_class"],
        "profile": P07_PROFILE_VERSION,
        "profile_sha256": profile_sha256(source), "input_profile_sha256": normalized["input_profile_sha256"],
        "bound_profile_sha256": normalized["bound_profile_sha256"],
        "collection_sha256": collection["collection_sha256"], "normalized_sha256": normalized["normalized_sha256"],
        "observations_sha256": normalized["observations_sha256"], "result_sha256": normalized["result_sha256"],
        "raw_evidence": dict(normalized["raw_evidence"]),
        "window_start": normalized["window"]["start_utc"], "window_end": normalized["window"]["end_utc"],
        "collected_at": profile["dataset"]["collection"]["collected_at_utc"],
        "archive_height": profile["dataset"]["collection"]["archive_height"],
        "query_sha256": collection["query"]["identity_sha256"], "query": collection["query"]["definition"],
        "network": profile["network"], "binding_view": normalized["binding_view"],
        "decimals": normalized["decimals"], "status": collection["status"],
        "stop_reason": collection["stop_reason"], "coverage": collection["coverage"],
        "gaps": list(normalized["gaps"]),
        "verdict": {"overall": overall,
                    "claims": {name: claim["verdict"] for name, claim in qualification["claims"].items()}},
        "qualification": qualification, "buckets": list(normalized["buckets"]), "trades": _trades(normalized),
        "provider_requests": usage, "provider_requests_state": usage_state,
        "invocations_measured": {"count": collection["source_invocations"]["measured_local_attempts"],
                                 "label": "EXACT_LOCAL_COUNT"},
        "binding_state": "QUALIFIED_BINDING" if binding is not None else "UNAVAILABLE_LIMITED_DATA",
        "market_binding": binding, "strategy_market": market,
        "market_binding_id": None if market is None else strategy_compiler.market_binding_id(market),
        "unavailable_states": unavailable,
        "notice": ("Synthetic recorded responses replayed locally. Not provider, chain or market evidence; "
                   "no profitability, execution or statistical claim."),
    }
    if transport is not None:
        content["transport"] = {key: value for key, value in transport.items() if key != "evidence_basis"}
        content["evidence_basis"] = dict(transport["evidence_basis"])
        content["notice"] = ("Synthetic native-shaped Envio and QuickNode recordings replayed locally through the "
                             "accepted P07 transport. The chain id and receipts were checked against recorded "
                             "responses, not a network. Not provider, chain or market evidence; no profitability, "
                             "execution or statistical claim.")
    return content


def save_dataset(session: Session, content: dict[str, Any], raw_records: list[Any]) -> HistoryDatasetRow:
    """Add one immutable dataset row. The caller commits it with the attempt that produced it."""
    row = HistoryDatasetRow(dataset_id=uuid.UUID(content["dataset_id"]), owner_id=uuid.UUID(content["owner_id"]),
                            declaration_id=uuid.UUID(content["declaration_id"]), job_id=uuid.UUID(content["job_id"]),
                            attempt_id=uuid.UUID(content["attempt_id"]),
                            content_sha256=record_contract.sha256_hex(content), content=content,
                            raw_records=list(raw_records))
    session.add(row)
    return row


def verify_hashes(row: HistoryDatasetRow) -> dict[str, bool]:
    """Recompute the stored digests. A mismatch is reported, never repaired."""
    return {"content_sha256": record_contract.sha256_hex(row.content) == row.content_sha256,
            "raw_evidence_sha256": raw_sha256(row.raw_records) == row.content["raw_evidence"]["sha256"]}


def owned_dataset(session: Session, principal: Principal, dataset_id: str) -> HistoryDatasetRow:
    parsed = parse_uuid(dataset_id)
    row = None if parsed is None else session.execute(select(HistoryDatasetRow).where(
        HistoryDatasetRow.owner_id == principal.user_id, HistoryDatasetRow.dataset_id == parsed)).scalar_one_or_none()
    if row is None:
        raise not_found("history dataset")
    return row


def dataset_view(row: HistoryDatasetRow) -> dict[str, Any]:
    return {"dataset_id": str(row.dataset_id), "content_sha256": row.content_sha256,
            "created_at": record_contract.utc_string(row.created_at), "hashes_verified": verify_hashes(row),
            "content": row.content}


def feature_rows(content: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Bucket -> P06 input observations. Unproven buckets stay unqualified; an empty bucket has no price."""
    rows = []
    for bucket in content["buckets"]:
        proven = bucket["status"] in COMPLETE_STATUSES
        reasons = list(bucket["reasons"]) or ([] if proven else [bucket["status"]])
        common = {"qualified": proven and bucket["available_at"] is not None,
                  "available_at": bucket["available_at"], "reasons": reasons}
        rows.append({"bucket_end": bucket["bucket_end"], "price": {"value": bucket["close"], **common},
                     "quote_volume": {"value": bucket["quote_volume"], **common}})
    return rows


def list_datasets(session: Session, principal: Principal) -> dict[str, Any]:
    """The owner's saved datasets, newest first, with the facts a user reviews before adopting a market."""
    rows = session.execute(select(HistoryDatasetRow).where(HistoryDatasetRow.owner_id == principal.user_id)
                           .order_by(HistoryDatasetRow.created_at.desc()).limit(50)).scalars().all()
    from edge_os_api.records.models import InvestigationDeclaration

    declarations = {row.declaration_id: row for row in session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.declaration_id.in_({row.declaration_id for row in rows} or {uuid.UUID(int=0)}))).scalars()}

    def rules(declaration_id: uuid.UUID) -> list[dict[str, Any]]:
        declaration = declarations.get(declaration_id)
        return [] if declaration is None else [
            {key: rule[key] for key in ("evaluation_id", "variant_id", "price_expression", "volume_expression")}
            for rule in declaration.content["rule_map"]["rules"]]
    keys = ("source_id", "evidence_class", "content_label", "profile_evidence_class", "status", "stop_reason",
            "verdict", "binding_state", "unavailable_states", "market_binding", "market_binding_id", "window_start",
            "window_end", "declaration_id", "job_id")
    return {"datasets": [{"dataset_id": str(row.dataset_id), "created_at": record_contract.utc_string(row.created_at),
                          "content_sha256": row.content_sha256, "hashes_verified": verify_hashes(row),
                          "quote_unit": None if row.content["strategy_market"] is None
                          else row.content["strategy_market"]["quote_unit"],
                          "declared_rules": rules(row.declaration_id),
                          "readable_until": readable_until(session, row),
                          **{key: row.content[key] for key in keys}} for row in rows]}


def protected_from(session: Session, row: HistoryDatasetRow) -> str | None:
    """The start of the declaration's first protected partition, or None when it declares none."""
    from edge_os_api.records.models import InvestigationDeclaration

    declaration = session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == row.owner_id,
        InvestigationDeclaration.declaration_id == row.declaration_id)).scalar_one_or_none()
    if declaration is None:  # cannot prove which partitions are readable: protect the whole window
        return row.content["window_start"]
    starts = [_utc_text(item["start"]) for item in declaration.content["configuration"]["partitions"]
              if item["role"] in PROTECTED_ROLES]
    return min(starts) if starts else None


def readable_until(session: Session, row: HistoryDatasetRow) -> str:
    """The latest instant a replay may read: the first protected partition start, else the dataset window end."""
    return protected_from(session, row) or row.content["window_end"]


def _utc_text(value: str) -> str:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
