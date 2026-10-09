"""Owner-scoped persistence and retrieval for deterministic P13 replay results."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import p02, p06, spot_replay
from .auth import Principal
from .errors import AppError, finding, not_found
from .models import SpotReplayRun
from .schemas import SpotReplayBody
from .service import get_revision, parse_uuid

SCHEMA_VERSION = "p13.spot-replay-run/1"
FIXTURE_ID = "p13.wc01/1"
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "spot_replay" / "runtime_wc01.json"
PROFILE_PATH = Path(__file__).resolve().parents[4] / "docs" / "implementation" / "SPOT_REPLAY_RUNTIME_PROFILE.md"
_PATH = "/v1/spot-replays"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        return p02.utc_string(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _response(row: SpotReplayRun) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "record_type": "SpotReplayRun",
            "replay_id": str(row.replay_id), "created_at": p02.utc_string(row.created_at),
            "content_sha256": row.content_sha256, "content": row.content}


def _owned(session: Session, principal: Principal, replay_id: str) -> SpotReplayRun:
    parsed = parse_uuid(replay_id)
    row = None if parsed is None else session.execute(select(SpotReplayRun).where(
        SpotReplayRun.owner_id == principal.user_id, SpotReplayRun.replay_id == parsed)).scalar_one_or_none()
    if row is None:
        raise not_found("spot replay")
    return row


def _descriptor(body: SpotReplayBody, strategy: dict[str, Any], dataset_revision_id: str,
                market_binding_id: str) -> dict[str, Any]:
    return {
        "schema_version": spot_replay.ESSENTIAL_VERSION,
        "strategy_revision": body.strategy_revision_id,
        "run_configuration_id": body.run_configuration_id,
        "dataset_revision": dataset_revision_id,
        "market_binding_id": market_binding_id,
        "fields": body.essential_fields.model_dump(mode="json"),
    }


def _input_snapshot(body: SpotReplayBody, strategy: dict[str, Any], fixture: dict[str, Any],
                    descriptor: dict[str, Any], market_binding_id: str) -> dict[str, Any]:
    return {
        "profile_version": spot_replay.PROFILE_VERSION,
        "strategy_revision_id": body.strategy_revision_id,
        "strategy_id": body.strategy_id,
        "strategy_sha256": p02.sha256_hex(strategy),
        "strategy": strategy,
        "run_configuration_id": body.run_configuration_id,
        "dataset_fixture_id": body.dataset_fixture_id,
        "dataset_revision_id": fixture["dataset_revision_id"],
        "dataset_qualification": "QUALIFIED",
        "coverage_complete": True,
        "evidence_class": "SYNTHETIC_FIXTURE",
        "fixture_sha256": _sha256(FIXTURE_PATH),
        "profile_sha256": _sha256(PROFILE_PATH),
        "market_binding_id": market_binding_id,
        "window_start": p02.utc_string(body.window_start),
        "window_end": p02.utc_string(body.window_end),
        "initial_cash_quote": body.initial_cash_quote,
        "initial_base_amount": body.initial_base_amount,
        "initial_basis_quote": body.initial_basis_quote,
        "essential_evidence": descriptor,
        "buckets": fixture["buckets"],
        "fixture_limitation": "Explicit authored synthetic schedule; not observed market history.",
    }


def _replay_input(body: SpotReplayBody, fixture: dict[str, Any], descriptor: dict[str, Any],
                  market_binding_id: str) -> spot_replay.ReplayInput:
    buckets = tuple(
        spot_replay.ReplayBucket(
            bucket_end=dt.datetime.fromisoformat(bucket["bucket_end"].replace("Z", "+00:00")),
            status=bucket["status"],
            price=p06.Observation(
                value=bucket["price"],
                bucket_end=dt.datetime.fromisoformat(bucket["bucket_end"].replace("Z", "+00:00")),
                market_binding_id=market_binding_id,
                qualified=bucket["status"] == "COMPLETE_OCCUPIED",
                available_at=(dt.datetime.fromisoformat(bucket["available_at"].replace("Z", "+00:00"))
                              if bucket["available_at"] else None),
                reasons=tuple(bucket.get("price_reasons", ())),
            ),
            quote_volume=p06.Observation(
                value=bucket["quote_volume"],
                bucket_end=dt.datetime.fromisoformat(bucket["bucket_end"].replace("Z", "+00:00")),
                market_binding_id=market_binding_id,
                qualified=bucket["status"] in {"COMPLETE_OCCUPIED", "COMPLETE_EMPTY"},
                available_at=(dt.datetime.fromisoformat(bucket["available_at"].replace("Z", "+00:00"))
                              if bucket["available_at"] else None),
                reasons=tuple(bucket.get("volume_reasons", ())),
            ),
        ) for bucket in fixture["buckets"]
    )
    dataset = spot_replay.ReplayDataset(
        revision_id=fixture["dataset_revision_id"], qualification="QUALIFIED", coverage_complete=True,
        market_binding_id=market_binding_id, buckets=buckets, evidence_class="SYNTHETIC_FIXTURE")
    return spot_replay.ReplayInput(
        strategy_revision_id=body.strategy_revision_id,
        run_configuration_id=body.run_configuration_id,
        dataset=dataset,
        essential_evidence=descriptor,
        window_start=body.window_start,
        window_end=body.window_end,
        initial_cash_quote=body.initial_cash_quote,
        initial_base_amount=body.initial_base_amount,
        initial_basis_quote=body.initial_basis_quote,
    )


def _unavailable(error: spot_replay.ReplayError) -> dict[str, Any]:
    return {"status": "UNAVAILABLE", "reason": {"code": error.code, "path": error.path,
            "detail": error.detail}, "evidence_class": "SYNTHETIC_FIXTURE", "samples": [], "events": [],
            "trades": [], "metrics": {}, "metric_statuses": {}, "metric_reasons": {},
            "repeatability_id": None, "open_position": None}


def create_spot_replay(session: Session, principal: Principal, body: SpotReplayBody) -> tuple[int, dict[str, Any]]:
    """Create one immutable replay, or return the identical result for its idempotency key."""
    request = body.model_dump(mode="json")
    fingerprint_body = {key: value for key, value in request.items() if key != "idempotency_key"}
    fingerprint = p02.sha256_hex({"owner_id": str(principal.user_id), "method": "POST", "path": _PATH,
                                  "request": fingerprint_body})
    existing = session.execute(select(SpotReplayRun).where(
        SpotReplayRun.owner_id == principal.user_id,
        SpotReplayRun.method == "POST", SpotReplayRun.path == _PATH,
        SpotReplayRun.idempotency_key == body.idempotency_key)).scalar_one_or_none()
    if existing is not None:
        if existing.fingerprint != fingerprint:
            raise AppError(409, "SPOT_REPLAY", "CONFLICTED", "idempotency_key_reused",
                           [finding("idempotency_key_reused", "/idempotency_key",
                                    "This key was used for different replay inputs.")])
        return 200, _response(existing)

    revision_id = parse_uuid(body.strategy_revision_id)
    if revision_id is None:
        raise AppError(422, "SPOT_REPLAY", "INVALID_INPUT", "invalid_strategy_revision",
                       [finding("invalid_strategy_revision", "/strategy_revision_id",
                                "Use the exact saved strategy revision identifier.")])
    revision = get_revision(session, principal, body.strategy_id, body.strategy_revision_id)
    if not revision["stored_hash_matches_content"] or not revision["stored_manifest_hash_matches_content"]:
        raise AppError(422, "SPOT_REPLAY", "INVALID_INPUT", "stale_strategy_revision",
                       [finding("stale_strategy_revision", "/strategy_revision_id",
                                "The saved strategy revision failed its integrity check.")])
    strategy = revision["strategy"]
    if body.dataset_fixture_id != FIXTURE_ID:
        raise AppError(422, "SPOT_REPLAY", "INVALID_INPUT", "unsupported_dataset_fixture",
                       [finding("unsupported_dataset_fixture", "/dataset_fixture_id",
                                "Select the authored P13 synthetic fixture.")])
    try:
        fixture_hash, profile_hash = _sha256(FIXTURE_PATH), _sha256(PROFILE_PATH)
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if fixture.get("evidence_class") not in (None, "SYNTHETIC_FIXTURE"):
            raise ValueError("fixture evidence class changed")
    except (OSError, ValueError, json.JSONDecodeError):
        raise AppError(503, "SPOT_REPLAY", "UNAVAILABLE", "fixture_profile_unavailable", []) from None

    market_binding_id = p06.market_binding_id(strategy["market"])
    descriptor = _descriptor(body, strategy, fixture["dataset_revision_id"], market_binding_id)
    snapshot = _input_snapshot(body, strategy, fixture, descriptor, market_binding_id)
    snapshot["fixture_sha256"], snapshot["profile_sha256"] = fixture_hash, profile_hash
    try:
        result = spot_replay.run_spot_replay(strategy, _replay_input(body, fixture, descriptor, market_binding_id))
        result_snapshot = {"status": "COMPLETE", "evidence_class": result.evidence_class,
                           "repeatability_id": result.repeatability_id,
                           "samples": _json_value(result.samples), "events": _json_value(result.events),
                           "trades": _json_value(result.trades), "metrics": _json_value(result.metrics),
                           "metric_statuses": result.metric_statuses,
                           "metric_reasons": _json_value(result.metric_reasons),
                           "open_position": _json_value(result.open_position)}
    except spot_replay.ReplayError as error:
        result_snapshot = _unavailable(error)

    replay_id = uuid.uuid4()
    now = dt.datetime.now(dt.timezone.utc)
    content = {"schema_version": SCHEMA_VERSION, "owner_id": str(principal.user_id),
               "replay_id": str(replay_id), "strategy_revision_id": body.strategy_revision_id,
               "dataset_fixture_id": body.dataset_fixture_id, "run_configuration_id": body.run_configuration_id,
               "idempotency": {"method": "POST", "path": _PATH, "key": body.idempotency_key,
                               "fingerprint": fingerprint},
               "inputs": snapshot, "result": result_snapshot,
               "notice": "Synthetic replay only. Assumed fills; no gas, spread, additional impact, or capacity model. "
                         "No trading permission is granted."}
    content_sha256 = p02.sha256_hex(content)
    row = SpotReplayRun(
        replay_id=replay_id, owner_id=principal.user_id, strategy_id=body.strategy_id,
        strategy_revision_id=revision_id, method="POST", path=_PATH,
        idempotency_key=body.idempotency_key, fingerprint=fingerprint,
        content_sha256=content_sha256, content=content, created_at=now)
    try:
        session.add(row)
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = session.execute(select(SpotReplayRun).where(
            SpotReplayRun.owner_id == principal.user_id,
            SpotReplayRun.method == "POST", SpotReplayRun.path == _PATH,
            SpotReplayRun.idempotency_key == body.idempotency_key)).scalar_one_or_none()
        if replay is None or replay.fingerprint != fingerprint:
            raise AppError(409, "SPOT_REPLAY", "CONFLICTED", "run_create_conflict", []) from None
        return 200, _response(replay)
    return 201, _response(row)


def get_spot_replay(session: Session, principal: Principal, replay_id: str) -> dict[str, Any]:
    """Return only the owner's exact stored result; never invoke the evaluator."""
    row = _owned(session, principal, replay_id)
    required = {"schema_version", "owner_id", "replay_id", "strategy_revision_id", "dataset_fixture_id",
                "run_configuration_id", "idempotency", "inputs", "result", "notice"}
    if set(row.content) != required or row.content.get("schema_version") != SCHEMA_VERSION \
            or row.content.get("owner_id") != str(principal.user_id) \
            or row.content.get("replay_id") != str(row.replay_id) \
            or p02.sha256_hex(row.content) != row.content_sha256:
        raise AppError(500, "SPOT_REPLAY", "UNAVAILABLE", "stored_replay_invalid",
                       [finding("stored_replay_invalid", "/", "The saved replay failed its integrity check.")])
    return _response(row)
