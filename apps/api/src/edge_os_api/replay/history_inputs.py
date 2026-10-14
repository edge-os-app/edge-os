"""Saved recorded-history datasets as inputs to the unchanged P13 replay runtime (`edge-os.history-replay-input/1`).

The adapter copies one owner's saved, hash-verified dataset into `ReplayDataset` and `ReplayBucket` values. It never
changes a bucket, fills a gap, moves an availability time, upgrades a verdict or relabels evidence: the runtime's own
checks decide warm-up, coverage, truncation, lookahead and market identity. The P07 profile's evidence class is passed
through as stated. `PROVIDER_ACTUAL` passes only from a dataset an approved actual release wrote (source class
`PROVIDER_ACTUAL`, saved release kind `ACTUAL`); the runtime then applies the same qualification, coverage and market
checks as to a fixture, so the class upgrades nothing.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding
from edge_os_api.replay import simulator as spot_replay
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import history_dataset
from edge_os_api.strategies import compiler as strategy_compiler

INPUT_VERSION = "edge-os.history-replay-input/1"
FILL_LABEL = "simulated fills"


def _moment(value: str | None) -> dt.datetime | None:
    return None if value is None else dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load(session: Session, principal: Principal, dataset_id: str) -> history_dataset.HistoryDatasetRow:
    """The owner's dataset with its stored hashes recomputed. A mismatch refuses the replay."""
    row = history_dataset.owned_dataset(session, principal, dataset_id)
    if not all(history_dataset.verify_hashes(row).values()):
        raise AppError(409, "SPOT_REPLAY", "CONFLICTED", "dataset_hash_mismatch",
                       [finding("dataset_hash_mismatch", "/history_dataset_id",
                                "The saved dataset no longer matches its recorded hashes.")])
    return row


def refuse_protected(session: Session, row: history_dataset.HistoryDatasetRow, window_end: dt.datetime) -> None:
    """Refuse a window that would pass validation or holdout buckets to the runtime. Nothing is read or saved."""
    protected = history_dataset.protected_from(session, row)
    if protected is not None and window_end > _moment(protected):
        raise AppError(409, "SPOT_REPLAY", "UNAVAILABLE", "protected_partition_not_authorized",
                       [finding("protected_partition_not_authorized", "/window_end",
                                f"The declaration protects data from {protected}. "
                                "End the replay window at or before that time.")])


def replay_dataset(row: history_dataset.HistoryDatasetRow, window_end: dt.datetime) -> spot_replay.ReplayDataset:
    """Every saved bucket that ends before the run's exclusive end, unchanged. Later buckets are not passed in."""
    content = row.content
    if content["profile_evidence_class"] == "PROVIDER_ACTUAL" and (
            content["evidence_class"] != "PROVIDER_ACTUAL"
            or (content.get("operating_release") or {}).get("kind") != "ACTUAL"):
        raise AppError(409, "SPOT_REPLAY", "CONFLICTED", "evidence_class_inconsistent",
                       [finding("evidence_class_inconsistent", "/history_dataset_id",
                                "Only a dataset an approved actual release collected can be replayed as provider "
                                "history. Nothing was replayed.")])
    market_id = content["market_binding_id"] or ""
    buckets = []
    for bucket in content["buckets"]:
        end = _moment(bucket["bucket_end"])
        if end is None or end >= window_end:
            continue
        available = _moment(bucket["available_at"])
        proven = bucket["status"] in history_dataset.COMPLETE_STATUSES
        reasons = tuple(bucket["reasons"])
        price = strategy_compiler.Observation(
            value=bucket["close"], bucket_end=end, market_binding_id=market_id,
            qualified=bucket["status"] == "COMPLETE_OCCUPIED", available_at=available, reasons=reasons)
        volume = strategy_compiler.Observation(
            value=bucket["quote_volume"], bucket_end=end, market_binding_id=market_id, qualified=proven,
            available_at=available, reasons=reasons)
        buckets.append(spot_replay.ReplayBucket(bucket_end=end, status=bucket["status"],
                                                price=price, quote_volume=volume))
    return spot_replay.ReplayDataset(
        revision_id=str(row.dataset_id), qualification=content["verdict"]["overall"],
        coverage_complete=content["status"] == "COMPLETE" and content["coverage"]["covers_requested_scan"] is True,
        market_binding_id=market_id, buckets=tuple(buckets),
        evidence_class=content["profile_evidence_class"])


def rule_linkage(session: Session, row: history_dataset.HistoryDatasetRow, strategy: dict[str, Any]) -> dict[str, Any]:
    """Whether the replayed entry is exactly one rule the dataset's own declaration adopted. Reported, not enforced."""
    from edge_os_api.records.models import InvestigationDeclaration
    from edge_os_api.research.market_adoption import declared_entry

    declaration = session.get(InvestigationDeclaration, row.content["declaration_id"])
    rules = [] if declaration is None else declaration.content.get("rule_map", {}).get("rules", [])
    entry = record_contract.sha256_hex(strategy["entry"])
    match = next((rule for rule in rules if record_contract.sha256_hex(declared_entry(rule)) == entry), None)
    return {"state": "ENTRY_IS_DECLARED_RULE" if match else "ENTRY_NOT_FROM_THIS_DECLARATION",
            "evaluation_id": None if match is None else match["evaluation_id"],
            "rule_map_sha256": None if declaration is None else declaration.content["frozen"]["rule_map_sha256"]}


def snapshot(row: history_dataset.HistoryDatasetRow, strategy: dict[str, Any],
             linkage: dict[str, Any]) -> dict[str, Any]:
    """The lineage saved beside the replay: exact dataset, declaration, job, source and both market identities."""
    content = row.content
    return {
        "schema_version": INPUT_VERSION, "dataset_id": str(row.dataset_id),
        "dataset_content_sha256": row.content_sha256, "normalized_sha256": content["normalized_sha256"],
        "collection_sha256": content["collection_sha256"], "declaration_id": content["declaration_id"],
        "job_id": content["job_id"], "source_id": content["source_id"],
        "source_evidence_class": content["evidence_class"], "content_label": content["content_label"],
        "profile_evidence_class": content["profile_evidence_class"],
        "verdict": content["verdict"], "status": content["status"], "binding_state": content["binding_state"],
        "dataset_market_binding_id": content["market_binding_id"],
        "strategy_market_binding_id": strategy_compiler.market_binding_id(strategy["market"]),
        "window_start": content["window_start"], "window_end": content["window_end"],
        "rule_linkage": linkage, "fill_label": FILL_LABEL,
        "fill_assumptions": {"price": "bucket close of the decision bucket", "costs": strategy["cost_assumptions"],
                             "not_modeled": ["gas", "spread", "extra price impact", "capacity"]},
    }
