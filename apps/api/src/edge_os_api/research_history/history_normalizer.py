"""Normalize a bounded collection into the existing P07 evidence and verdicts.

The normalizer maps supplied provider events to P07 log records, materializes a
bound P07 profile whose dataset carries the collected pages, runs the reused
``history_observations`` and ``qualify`` seams, and returns the raw evidence, the
per-claim result, an ordered bucket view and the hashes that bind the result to
its inputs.

Only facts a provider read can give arrive from the caller. Everything the pages
and logs prove is derived by the reused engine. The result never claims that
self-reported observations were independently checked.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from edge_os_api.research_history.errors import AdapterInputError
from edge_os_api.research_history.qualification_engine import (
    InvalidInput,
    assemble_segments,
    bucket_available_at,
    bucketize,
    canonical_sha256,
    dataset_revision,
    feasibility,
    history_observations,
    ingest,
    profile_problems,
    profile_sha256,
    qualify,
    research_binding_view,
    to_p02_binding,
    trade_identity,
)

_REQUIRED_EVIDENCE = (
    "collected_at_utc",
    "archive_height",
    "chain_id_source",
    "pool_tokens",
    "pool_venue",
    "decimals",
    "fee_transfer_semantics",
    "corroboration",
    "finality_at_collection",
    "feasibility_claim",
)


def _log_record(record: Any) -> Any:
    """Map one supplied provider event to the P07 log shape. Raw values are kept."""
    if not isinstance(record, Mapping):
        return record  # ingest() rejects a non-object with NOT_AN_OBJECT and continues
    log: dict[str, Any] = {}
    if "topics" in record:
        log["topics"] = record["topics"]
    else:
        log["topics"] = [record[key] for key in ("topic0", "topic1", "topic2") if key in record]
    for key in ("address", "data", "block_number", "block_hash", "block_timestamp",
                "transaction_hash", "transaction_index", "log_index", "removed"):
        if key in record:
            log[key] = record[key]
    return log


def _materialize_profile(profile: Mapping[str, Any], collection: Mapping[str, Any],
                         evidence: Mapping[str, Any], row_count: int) -> dict[str, Any]:
    bound = copy.deepcopy(dict(profile))
    pages = [dict(page) for page in collection["pages"]]
    if pages:
        try:
            digest = dataset_revision(pages)
        except (KeyError, TypeError):
            digest = None  # a malformed page is reported by profile_problems below
        revision = {"basis": "PAGE_DIGESTS", "manifest_sha256": digest,
                    "page_count": len(pages), "row_count": row_count}
    else:
        revision = {"basis": "NONE", "manifest_sha256": None, "page_count": 0, "row_count": None}
    bound["dataset"] = {
        "window": dict(profile["dataset"]["window"]),
        "collection": {"collected_at_utc": evidence["collected_at_utc"], "collected_on_utc": None,
                       "archive_height": evidence["archive_height"]},
        "query": {"identity_sha256": collection["query"]["identity_sha256"],
                  "definition": copy.deepcopy(collection["query"]["definition"]),
                  "from_block": collection["requested_scan"]["from_block"],
                  "to_block_exclusive": collection["requested_scan"]["to_block_exclusive"]},
        "pages": pages,
        "dataset_revision": revision,
    }
    return bound


def _resolve_feasibility(evidence: Mapping[str, Any], assembled: Mapping[str, Any],
                         availability: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return feasibility(evidence["feasibility_claim"], assembled["segments"], availability)
    except InvalidInput as error:
        raise AdapterInputError("FEASIBILITY_CLAIM_INVALID", str(error)) from error


def _trade_view(profile: Mapping[str, Any], trade: Any) -> dict[str, Any]:
    return {
        "identity": trade_identity(profile, trade),
        "price": trade.price,
        "quote_amount": trade.quote_amount,
        "base_amount": trade.base_amount,
        "quote_raw": str(trade.quote_raw),
        "base_raw": str(trade.base_raw),
        "pool_side": trade.pool_side,
        "block_number": trade.block_number,
        "transaction_index": trade.transaction_index,
        "log_index": trade.log_index,
    }


def _bucket_views(bound: Mapping[str, Any], decoded: Any, assembled: Mapping[str, Any],
                  delivered: Mapping[str, str]) -> list[dict[str, Any]]:
    """One ordered view per existing 300-second window bucket.

    Uses the accepted ``bucketize`` and ``bucket_available_at`` seams unchanged. A
    complete-empty bucket keeps a null close and its proved zero volume. Incomplete
    or unqualified data never becomes complete or zero here.
    """
    buckets = bucketize(bound, decoded, assembled["segments"], bound["dataset"]["window"])
    views: list[dict[str, Any]] = []
    for bucket in buckets:
        when = bucket_available_at(bound["availability"], bucket, delivered)
        status = bucket["status"]
        proven = status in ("COMPLETE_OCCUPIED", "COMPLETE_EMPTY")
        close = bucket["close"]["price"] if (proven and bucket["close"]) else None
        reasons = list(bucket["reasons"])
        if when.get("reason"):
            reasons.append(when["reason"])
        views.append({
            "bucket_start": bucket["start"],
            "bucket_end": bucket["end"],
            "status": status,
            "close": close,
            "quote_volume": bucket["quote_volume"] if proven else None,
            "available_at": when.get("at"),
            "availability_basis": when["basis"],
            "reasons": reasons,
        })
    return views


def _evidence_gaps(collection: Mapping[str, Any], assembled: Mapping[str, Any],
                   observations: Mapping[str, Any]) -> list[dict[str, str]]:
    gaps = [dict(gap) for gap in collection["gaps"]]
    for item in assembled["breaks"]:
        gaps.append({"code": f"SEGMENT_{item['code']}", "detail": str(item.get("page_id"))})
    summary = observations["ingest"]
    if summary["conflicts"]:
        gaps.append({"code": "INGEST_CONFLICTS", "detail": str(summary["conflicts"])})
    if summary["removed"]:
        gaps.append({"code": "INGEST_REMOVED", "detail": str(summary["removed"])})
    if summary["foreign"]:
        gaps.append({"code": "INGEST_FOREIGN", "detail": str(summary["foreign"])})
    if summary["unlocated_rejections"]:
        gaps.append({"code": "INGEST_UNLOCATED", "detail": str(summary["unlocated_rejections"])})
    for code, count in sorted(summary["rejected_codes"].items()):
        gaps.append({"code": f"REJECTED_{code}", "detail": str(count)})
    return gaps


def _collection_view(collection: Mapping[str, Any]) -> dict[str, Any]:
    """The portable collection summary. The raw records stay with the caller."""
    return {key: value for key, value in collection.items() if key != "records"}


def normalize(profile: Mapping[str, Any], collection: Mapping[str, Any],
              evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a bounded collection and caller-held provider facts into P07 evidence."""
    if not isinstance(evidence, Mapping) or any(key not in evidence for key in _REQUIRED_EVIDENCE):
        missing = [key for key in _REQUIRED_EVIDENCE if not isinstance(evidence, Mapping) or key not in evidence]
        raise AdapterInputError("EVIDENCE_MALFORMED", f"missing evidence facts: {', '.join(missing)}")
    if not isinstance(collection, Mapping) or "pages" not in collection or "records" not in collection:
        raise AdapterInputError("COLLECTION_MALFORMED", "collection needs pages and records")

    logs = [_log_record(record) for record in collection["records"]]
    bound = _materialize_profile(profile, collection, evidence, len(logs))
    problems = profile_problems(bound)
    if problems:
        raise AdapterInputError("BOUND_PROFILE_INVALID",
                                "; ".join(f"{item['code']}@{item['path']}" for item in problems))

    dataset = bound["dataset"]
    assembled = assemble_segments(bound, dataset["query"], dataset["pages"],
                                  dataset["collection"]["archive_height"] or 0)
    decoded = ingest(bound, logs)
    delivered = evidence.get("delivery_records")
    delivered = dict(delivered) if isinstance(delivered, Mapping) else {}

    window = dict(dataset["window"])
    observations = history_observations(bound, logs, window)
    observations["binding"] = {
        "chain_id": evidence["chain_id_source"],
        "pool_tokens": evidence["pool_tokens"],
        "pool_venue": evidence["pool_venue"],
    }
    observations["event_meaning"] = {"decimals": evidence["decimals"],
                                     "fee_transfer_semantics": evidence["fee_transfer_semantics"]}
    observations["corroboration"] = dict(evidence["corroboration"])
    observations["finality_at_collection"] = evidence["finality_at_collection"]
    observations["feasibility"] = _resolve_feasibility(evidence, assembled, bound["availability"])
    observations["provenance"] = {
        "supplied_by_caller": sorted(_REQUIRED_EVIDENCE),
        "derived_by_engine": ["ingest", "bucket_status_counts", "bucket_window", "segment_breaks", "feasibility"],
        "collection_sha256": collection.get("collection_sha256"),
        "history_provider": collection.get("provider", {}).get("history_provider"),
        "provider_version": collection.get("provider", {}).get("provider_version"),
    }

    result = qualify(bound, observations)
    quote_token = next(token for token in bound["pool_tokens"] if token["role"] == "QUOTE")
    base_token = next(token for token in bound["pool_tokens"] if token["role"] == "BASE")

    try:
        input_digest = profile_sha256(profile)
    except ValueError as error:
        raise AdapterInputError("INPUT_PROFILE_NOT_CANONICAL", str(error)) from error

    normalized = {
        "input_profile_sha256": input_digest,
        "bound_profile": bound,
        "bound_profile_sha256": profile_sha256(bound),
        "window": window,
        "decimals": {"base": base_token["decimals"], "quote": quote_token["decimals"]},
        "trades": [_trade_view(bound, trade) for trade in decoded.trades],
        "pages": [dict(page) for page in collection["pages"]],
        "collection": _collection_view(collection),
        "buckets": _bucket_views(bound, decoded, assembled, delivered),
        "observations": observations,
        "observations_sha256": canonical_sha256(observations),
        "qualification": result,
        "result_sha256": canonical_sha256(result),
        "binding_view": research_binding_view(bound),
        "overall": result["overall"],
        "gaps": _evidence_gaps(collection, assembled, observations),
    }
    normalized["normalized_sha256"] = canonical_sha256(normalized)
    return normalized


def project_binding(profile: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Project a portfolio-free P07 result to the accepted P02 binding. Refusal is preserved."""
    return to_p02_binding(profile, result)
