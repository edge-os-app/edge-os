"""Authored synthetic fixtures for the P30 local revocation tests.

Everything here is invented local data labelled SYNTHETIC. It is not provider,
chain, wallet or financial evidence. The helpers seed accepted-module rows so a
test can prove the removal package leaves them unchanged. No provider, wallet or
network call is made.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from admission import _builders as admission_builders
from consent import _support as consent_support

from edge_os_api.admission.service import AdmissionService
from edge_os_api.consent.service import ConsentService
from edge_os_api.consent.types import AdoptionRequest
from edge_os_api.revocation.types import Provenance, RemovalObservation, RemovalRequest
from edge_os_api.stops.service import StopService
from edge_os_api.stops.types import StopRequest
from edge_os_api.wallet_setup.persistence import WalletSetupRow, utcnow

OWNER_A = uuid.UUID("b212b4e8-88d0-4233-bc92-084bace61d08")
OWNER_B = uuid.UUID("22ad0953-197e-4f96-b003-3459cb7b02cf")
AGENT_A = "agent-a"
AGENT_B = "agent-b"
WALLET_A = "wallet-a"
WALLET_B = "wallet-b"
NETWORK = "monad:143"
NETWORK_TESTNET = "monad-testnet:10143"
NETWORK_INT = 143
NETWORK_TESTNET_INT = 10143
SIGNER_A = "signer-a"
SIGNER_OTHER = "signer-x"
POLICY_A = "policy-a"
POLICY_OTHER = "policy-x"
NOW_ISO = "2026-01-01T00:16:00Z"
STALE_ISO = "2026-01-01T00:15:00Z"

# Owned schemas plus the migrated public wallet-setup table inside the snapshot.
SNAPSHOT_SCHEMAS = ("revocation_local", "admission_local", "stops_local", "funding_local", "consent_local")
SNAPSHOT_PUBLIC_TABLES = ("wallet_setups",)


def seed_wallet_binding(engine, owner_id: uuid.UUID, *, agent_id: str = AGENT_A, wallet_id: str = WALLET_A,
                        network_id: int = NETWORK_INT, state: str = "CONFIRMED") -> None:
    """Insert one saved accepted wallet-setup binding row directly."""
    now = utcnow()
    row = WalletSetupRow(
        setup_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, network_id=network_id,
        strategy_id="strategy-rev-1", strategy_revision_id=uuid.uuid4(),
        content_sha256="a" * 64, manifest_sha256="b" * 64, state=state, cancellation_intent="NONE",
        creation_dispatched=True, request_key=f"seed-{owner_id}-{agent_id}",
        wallet_id=wallet_id if state == "CONFIRMED" else None, created_at=now, updated_at=now)
    with Session(engine) as session:
        session.add(row)
        session.commit()


def removal_request(*, request_key: str = "req-1", agent_id: str = AGENT_A, network_id: str = NETWORK,
                    expected_wallet_id: str | None = None, reason: str = "owner requested removal",
                    signer_identity: str | None = SIGNER_A, policy_identity: str | None = POLICY_A,
                    source: str = "SYNTHETIC_AUTHORED", requested_at: str = NOW_ISO) -> RemovalRequest:
    return RemovalRequest(
        request_key=request_key, agent_id=agent_id, network_id=network_id,
        expected_wallet_id=expected_wallet_id, reason=reason, signer_identity=signer_identity,
        policy_identity=policy_identity, provenance=Provenance(source=source), requested_at=requested_at)


def observation(request_id: uuid.UUID, *, observation_key: str = "obs-1", observed_state: str = "CONFIRMED",
                agent_id: str = AGENT_A, wallet_id: str = WALLET_A, network_id: str = NETWORK,
                signer_identity: str | None = SIGNER_A, policy_identity: str | None = POLICY_A,
                source: str = "SYNTHETIC_AUTHORED", observed_at: str = NOW_ISO) -> RemovalObservation:
    return RemovalObservation(
        observation_key=observation_key, request_id=request_id, observed_state=observed_state,
        agent_id=agent_id, wallet_id=wallet_id, network_id=network_id, signer_identity=signer_identity,
        policy_identity=policy_identity, provenance=Provenance(source=source), observed_at=observed_at)


def _factory(engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)


def seed_admission_unknown(engine, owner_id: uuid.UUID) -> str:
    """Admit one authored entry with usable allowances, then move it to SUBMISSION_UNKNOWN."""
    admission = AdmissionService(_factory(engine))
    intent = admission_builders.intent_entry()
    admission.admit_and_reserve(owner_id, intent, admission_builders.approval_a(), admission_builders.context_a())
    admission.acquire_submission(owner_id, intent.action_id)
    return intent.action_id


def seed_admission_admitted(engine, owner_id: uuid.UUID) -> str:
    """Admit one authored entry with usable allowances and leave it ADMITTED."""
    admission = AdmissionService(_factory(engine))
    intent = admission_builders.intent_entry()
    admission.admit_and_reserve(owner_id, intent, admission_builders.approval_a(), admission_builders.context_a())
    return intent.action_id


def seed_admission_admitted_b(engine, owner_id: uuid.UUID) -> str:
    """Admit one authored B-wallet entry with usable allowances and leave it ADMITTED."""
    admission = AdmissionService(_factory(engine))
    intent = admission_builders.intent_entry_b()
    admission.admit_and_reserve(owner_id, intent, admission_builders.approval_b(),
                                admission_builders.context_b())
    return intent.action_id


def seed_stop(engine, owner_id: uuid.UUID, *, agent_id: str = AGENT_A, wallet_id: str = WALLET_A,
              network_id: str = NETWORK, mode: str = "STOP_NEW_ENTRIES") -> None:
    StopService(_factory(engine)).request_stop(owner_id, StopRequest(
        agent_id=agent_id, wallet_id=wallet_id, network_id=network_id, scope="AGENT_WALLET_NETWORK",
        mode=mode, trigger="USER"))


def seed_funding_and_consent(engine, owner_id: uuid.UUID) -> dict:
    """Author accepted funding rows and one inactive consent adoption for owner A."""
    revision = consent_support.seed_revision(engine, owner_id)
    consent_support.seed_wallet_setup(engine, owner_id, revision)
    consent_support.seed_funding_credit(engine, owner_id)
    consent = ConsentService(_factory(engine), admission=AdmissionService(_factory(engine)),
                             stops=StopService(_factory(engine)))
    review = consent.review(owner_id, consent_support.review_request(revision))
    consent.adopt(owner_id, AdoptionRequest(review_id=str(review.review_id),
                                            expected_review_hash=review.review_hash))
    return revision


def snapshot(engine) -> dict[str, list[str]]:
    """A stable snapshot of every owned-schema table plus the public wallet-setup table."""
    captured: dict[str, list[str]] = {}
    with engine.connect() as connection:
        for schema in SNAPSHOT_SCHEMAS:
            tables = connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = :schema ORDER BY tablename"),
                {"schema": schema}).scalars().all()
            for table in tables:
                rows = connection.execute(text(f'SELECT * FROM "{schema}"."{table}"')).fetchall()
                captured[f"{schema}.{table}"] = sorted(str(row) for row in rows)
        for table in SNAPSHOT_PUBLIC_TABLES:
            rows = connection.execute(text(f'SELECT * FROM public."{table}"')).fetchall()
            captured[f"public.{table}"] = sorted(str(row) for row in rows)
    return captured


API_SRC = Path(__file__).resolve().parents[2] / "src"
API_DIR = API_SRC.parent


def _db_url(url: object) -> str:
    """Render a SQLAlchemy URL with its password, or pass a plain string through."""
    return url.render_as_string(hide_password=False) if hasattr(url, "render_as_string") else str(url)

_PROBE = r"""
import json, sys, uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from edge_os_api.revocation.removal_service import RemovalService

job = json.load(sys.stdin)
engine = create_engine(job["url"], pool_pre_ping=True,
                       connect_args={"options": "-csearch_path=revocation_local,public"})
factory = sessionmaker(engine, expire_on_commit=False)
service = RemovalService(factory)
owner = uuid.UUID(job["owner"])
with factory() as session:
    reasons = service.submission_denial(session, owner, agent_id=job["agent_id"],
                                        wallet_id=job["wallet_id"], network_id=job["network_id"])
views = service.read_removal(owner, agent_id=job["agent_id"], wallet_id=job["wallet_id"],
                             network_id=job["network_id"])
print(json.dumps({"denial": reasons, "states": [v.state for v in views]}))
"""


def restart_probe(url: str, owner: uuid.UUID, *, agent_id: str, wallet_id: str, network_id: str) -> dict:
    """Read the persisted removal state in a separate Python process against the same database."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(API_SRC), env.get("PYTHONPATH", "")]))
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        input=json.dumps({"url": _db_url(url), "owner": str(owner), "agent_id": agent_id,
                          "wallet_id": wallet_id, "network_id": network_id}),
        capture_output=True, text=True, cwd=str(API_DIR), env=env, check=False)
    assert completed.returncode == 0, f"probe failed: {completed.stderr}"
    return json.loads(completed.stdout)


_REQUEST_PROBE = r"""
import json, sys, uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from edge_os_api.revocation.removal_service import RemovalService
from edge_os_api.revocation.types import RemovalRequest

job = json.load(sys.stdin)
engine = create_engine(job["url"], pool_pre_ping=True,
                       connect_args={"options": "-csearch_path=revocation_local,public"})
service = RemovalService(sessionmaker(engine, expire_on_commit=False))
try:
    view = service.request_removal(uuid.UUID(job["owner"]), RemovalRequest.model_validate(job["request"]))
    print(json.dumps({"ok": True, "request_id": str(view.request_id), "state": view.state}))
except Exception as error:  # noqa: BLE001 - the probe reports the refusal class only
    print(json.dumps({"ok": False, "error": type(error).__name__}))
"""


def request_probe(url: str, owner: uuid.UUID, request) -> dict:
    """Run one owner request in a separate Python process against the same database."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(API_SRC), env.get("PYTHONPATH", "")]))
    completed = subprocess.run(
        [sys.executable, "-c", _REQUEST_PROBE],
        input=json.dumps({"url": _db_url(url), "owner": str(owner), "request": request.model_dump(mode="json")}),
        capture_output=True, text=True, cwd=str(API_DIR), env=env, check=False)
    assert completed.returncode == 0, f"probe failed: {completed.stderr}"
    return json.loads(completed.stdout)
