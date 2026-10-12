"""Authored synthetic fixtures for the P26 inactive-consent tests.

Everything here is invented local data labelled SYNTHETIC. It is not provider,
chain, wallet or financial evidence. The helpers insert the accepted modules'
rows so a test can prove that review and adoption leave them unchanged.
"""

from __future__ import annotations

import copy
import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from admission import _builders as admission_builders
from funding.fake_observer import AuthoredFakeDepositObserver, observation

from edge_os_api.admission.service import AdmissionService
from edge_os_api.consent.types import (AllowanceTerm, AssetAmount, ReviewedEvidence, ReviewedPolicy, ReviewedRoute,
                                       ReviewedTerms, ReviewRequest)
from edge_os_api.core.authentication import Principal
from edge_os_api.funding import service as funding_service
from edge_os_api.funding.types import ObservationStatus
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.stops.service import StopService
from edge_os_api.stops.types import StopRequest
from edge_os_api.strategies import compiler
from edge_os_api.wallet_setup.persistence import WalletSetupRow, utcnow

OWNER_A = uuid.UUID("b212b4e8-88d0-4233-bc92-084bace61d08")
OWNER_B = uuid.UUID("22ad0953-197e-4f96-b003-3459cb7b02cf")
# Aligned with the accepted admission builders so the review's owner-scoped reads match.
AGENT_A = "agent-a"
WALLET_A = "wallet-a"
NETWORK = "monad:143"
NETWORK_ID = 143
QUOTE = "monad:143/asset:USDC"
BASE = "monad:143/asset:MOE"
NATIVE = "monad:143/native"
EXPIRY = "2030-01-01T00:00:00Z"


def p06_strategy(strategy_id: str) -> dict:
    values = {}
    for name in record_contract.CREATE_STRATEGY_FIELDS:
        if name != "restrictions" and name in record_contract.FIXTURE_STRATEGY:
            values[name] = copy.deepcopy(record_contract.FIXTURE_STRATEGY[name])
    return compiler.build_strategy(strategy_id, values)


def seed_revision(engine, owner_id: uuid.UUID, *, strategy_id: str = "strategy-consent-1",
                  revision_id: uuid.UUID | None = None) -> dict:
    """Insert one owner-scoped immutable saved revision plus its required users/draft rows."""
    strategy = p06_strategy(strategy_id)
    canonical = record_contract.canonical_bytes(strategy).decode("utf-8")
    revision_id = revision_id or uuid.uuid4()
    draft_id, operation_id, publication_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = dt.datetime.now(dt.timezone.utc)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users (id, privy_did) VALUES (:id, :did) ON CONFLICT (privy_did) DO NOTHING"),
            {"id": owner_id, "did": f"did:privy:consent-{owner_id}"})
        connection.execute(text(
            "INSERT INTO records (record_id, owner_id, record_type, schema_version, operation_id, created_at, content) "
            "VALUES (:rid, :oid, 'StrategyDraft', 'p02.draft/1', :op, :now, '{}'::jsonb)"),
            {"rid": draft_id, "oid": owner_id, "op": operation_id, "now": now})
        connection.execute(text(
            "INSERT INTO strategy_revisions (revision_id, owner_id, strategy_id, parent_revision_id, draft_record_id, "
            "publication_id, operation_id, content_sha256, manifest_sha256, strategy_canonical, created_at) "
            "VALUES (:rev, :oid, :sid, NULL, :draft, :pub, :op, :content, :manifest, :canonical, :now)"),
            {"rev": revision_id, "oid": owner_id, "sid": strategy_id, "draft": draft_id, "pub": publication_id,
             "op": operation_id, "content": record_contract.sha256_hex(strategy),
             "manifest": record_contract.sha256_hex(strategy["semantic_manifest"]), "canonical": canonical, "now": now})
    return {"strategy_id": strategy_id, "revision_id": revision_id, "content_sha256": record_contract.sha256_hex(strategy),
            "manifest_sha256": record_contract.sha256_hex(strategy["semantic_manifest"]), "strategy": strategy}


def seed_wallet_setup(engine, owner_id: uuid.UUID, revision: dict, *, agent_id: str = AGENT_A,
                      wallet_id: str = WALLET_A, network_id: int = NETWORK_ID, state: str = "CONFIRMED") -> WalletSetupRow:
    now = utcnow()
    row = WalletSetupRow(
        setup_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, network_id=network_id,
        strategy_id=revision["strategy_id"], strategy_revision_id=revision["revision_id"],
        content_sha256=revision["content_sha256"], manifest_sha256=revision["manifest_sha256"], state=state,
        cancellation_intent="NONE", creation_dispatched=True, request_key="consent-seed",
        wallet_id=wallet_id if state == "CONFIRMED" else None, created_at=now, updated_at=now)
    with Session(engine) as session:
        session.add(row)
        session.commit()
    return row


def seed_funding_credit(engine, owner_id: uuid.UUID, *, agent_id: str = AGENT_A, wallet_id: str = WALLET_A,
                        network_id: int = NETWORK_ID, asset_id: str = QUOTE, raw: str = "4000",
                        decimals: int = 0, reference: str = "consent-ref-1") -> None:
    """Author a confirmed deposit credit through the accepted funding service."""
    principal = Principal(user_id=owner_id, privy_did="did:privy:consent-test")
    with Session(engine) as session:
        funding_service.declare_funding_assets(session, principal, agent_id=agent_id, network_id=network_id,
                                               trading_asset_id=asset_id, trading_decimals=decimals,
                                               gas_asset_id=NATIVE, gas_decimals=0)
        funding_service.prepare_funding(session, principal, agent_id=agent_id, kind="DEPOSIT", asset_id=asset_id,
                                        raw=raw, decimals=decimals, transport="deposit-address",
                                        reference=reference)
        observer = AuthoredFakeDepositObserver([observation(
            wallet_id=wallet_id, network_id=network_id, reference=reference, status=ObservationStatus.CONFIRMED,
            asset_id=asset_id, raw=raw, decimals=decimals, event_id="consent-event-1")])
        funding_service.reconcile_funding(session, principal, agent_id=agent_id, observer=observer)


def seed_allowance_and_unknown_decision(engine, owner_id: uuid.UUID) -> str:
    """Author an admitted action, then move it to SUBMISSION_UNKNOWN through the accepted admission service."""
    admission = AdmissionService(lambda: Session(engine))
    intent = admission_builders.intent_entry()
    approval = admission_builders.approval_a()
    context = admission_builders.context_a()
    admission.admit_and_reserve(owner_id, intent, approval, context)
    admission.acquire_submission(owner_id, intent.action_id)
    return intent.action_id


def seed_stop(engine, owner_id: uuid.UUID, *, agent_id: str = AGENT_A, wallet_id: str = WALLET_A,
              network_id: str = NETWORK, mode: str = "HALT_ALL_SWAPS") -> None:
    stops = StopService(lambda: Session(engine))
    stops.request_stop(owner_id, StopRequest(agent_id=agent_id, wallet_id=wallet_id, network_id=network_id,
                                             scope="AGENT_WALLET_NETWORK", mode=mode, trigger="USER"))


def terms(*, purpose: str = "ONGOING", allocation_raw: str = "5000", quote_raw: str = "500",
          base_raw: str = "1000", gas_raw: str = "50", attempt_budget: int = 5, expiry: str = EXPIRY,
          evidence_status: str = "UNRESOLVED", policy: ReviewedPolicy | None = None,
          supported_actions: tuple[str, ...] = ("ENTRY", "EXIT")) -> ReviewedTerms:
    return ReviewedTerms(
        terms_version="consent-terms/1",
        operating_purpose=purpose,
        trial_objective="learn-permitted-actions" if purpose == "TRIAL" else None,
        allocation=[AssetAmount(asset_id=QUOTE, raw=allocation_raw, decimals=0)],
        allowances=[AllowanceTerm(name="QUOTE_BUY", amount=AssetAmount(asset_id=QUOTE, raw=quote_raw, decimals=0)),
                    AllowanceTerm(name="BASE_SELL", amount=AssetAmount(asset_id=BASE, raw=base_raw, decimals=0))],
        attempt_budget=attempt_budget,
        gas_budget=AssetAmount(asset_id=NATIVE, raw=gas_raw, decimals=0),
        expiry=expiry,
        supported_actions=list(supported_actions),
        supported_assets=[QUOTE, BASE],
        supported_routes=["KURU_FLOW_FIXED_INPUT"],
        route=ReviewedRoute(adapter="KURU_FLOW_FIXED_INPUT", qualification="UNQUALIFIED"),
        policy=policy,
        signer="signer-consent-a",
        evidence=ReviewedEvidence(status=evidence_status, source="SYNTHETIC_AUTHORED",
                                  material_limitations=["route_unqualified", "provider_unqualified"]),
        stop_effects=["STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"],
    )


def review_request(revision: dict, *, agent_id: str = AGENT_A, network_id: str = NETWORK,
                   reviewed_terms: ReviewedTerms | None = None) -> ReviewRequest:
    return ReviewRequest(agent_id=agent_id, strategy_id=revision["strategy_id"],
                         strategy_revision_id=str(revision["revision_id"]), network_id=network_id,
                         terms=reviewed_terms or terms())
