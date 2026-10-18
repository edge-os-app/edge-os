"""Synthetic /2 producer -> admission -> PostgreSQL -> saved consumer and fresh-session rerun.

Requires a separately granted DB boundary. The actual producer uses an in-memory HTTPS peer, never a provider.
The existing stand-in journey suite separately covers HTTP adoption/replay and API/worker restart.
"""
from __future__ import annotations

import copy
import datetime as dt
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from edge_os_api.core.authentication import Principal
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.core.errors import AppError
from edge_os_api.core.research.operating_release import _check_history
from edge_os_api.records.contract_adapter import sha256_hex
from edge_os_api.research import history_dataset, history_payload_binding as binding
from edge_os_api.research.investigation_jobs import InvestigationEventRow
from edge_os_api.research_history.qualification_engine import raw_sha256
from test_actual_binding_admission import history_for
from test_saved_history_payload_binding import env, settings  # existing isolated DB/migration fixtures
from tests.test_history_payload_binding_v2 import graph


@pytest.fixture
def persisted_actual(settings, tmp_path, monkeypatch):
    anchor, export, _ = graph(tmp_path, monkeypatch)
    _check_history("ACTUAL", history_for(anchor))
    # Each case has independent application identities in the same module-owned database.
    content = copy.deepcopy(export["content"])
    for name in ("dataset_id", "owner_id", "job_id", "attempt_id", "declaration_id"):
        content[name] = str(uuid.uuid4())
    owner, dataset, job, attempt = (uuid.UUID(content[key]) for key in ("owner_id", "dataset_id", "job_id", "attempt_id"))
    content[binding.REQUIREMENT_KEY] = binding.requirement(anchor)
    started = {"operating_release": content["operating_release"], "input": {"source_id": content["source_id"]},
               binding.REQUIREMENT_KEY: content[binding.REQUIREMENT_KEY]}
    engine = make_engine(settings.database_url, statement_timeout_ms=10000)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            session.add(InvestigationEventRow(event_id=uuid.uuid4(), owner_id=owner, job_id=job, attempt_id=attempt,
                        kind="ATTEMPT_STARTED", content=started, created_at=dt.datetime.now(dt.timezone.utc)))
            history_dataset.save_dataset(session, content, export["raw_records"])
            event = binding.record_binding(session, owner_id=owner, job_id=job, attempt_id=attempt,
                                            dataset_id=dataset, definition=anchor)
            assert event["result"] == "PASS"
            session.commit()
        yield engine, factory, owner, dataset, job, attempt, event
    finally:
        engine.dispose()


def consumer(factory, owner, dataset):
    with factory() as session:
        row = binding._stored_row(session, owner, dataset)
        return binding.require_bound(session, Principal(owner, "synthetic-owner"), row,
                                     stage="TEST_ACTUAL_SAVED_CONSUMER", path="history_dataset")


def test_actual_bound_dataset_reopens_with_exact_graph_after_connections_restart(persisted_actual):
    engine, factory, owner, dataset, job, attempt, event = persisted_actual
    before = consumer(factory, owner, dataset)
    assert before["status"] == "PASS"
    engine.dispose()  # discard connections and identity maps; load persisted rows through a fresh session
    after = consumer(factory, owner, dataset)
    assert before == after and after["report_sha256"] == event["report_sha256"]
    with factory() as session:
        saved = session.execute(select(InvestigationEventRow).where(InvestigationEventRow.job_id == job,
                                InvestigationEventRow.kind == binding.EVENT_KIND)).scalar_one()
        assert saved.content["provenance_json"] == event["provenance_json"]
        assert binding._stored_row(session, uuid.uuid4(), dataset) is None
        shown = binding.public_event(binding.EVENT_KIND, saved.content)
        assert "handoff_json" not in shown and "provenance_json" not in shown
        saved.content = {**saved.content, "result": "MISMATCH"}
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_actual_consumer_rereads_saved_rows_and_rejects_rehashed_mutation(persisted_actual):
    _, factory, owner, dataset, *_ = persisted_actual
    with factory() as session:
        row = binding._stored_row(session, owner, dataset)
        raw, content = copy.deepcopy(row.raw_records), copy.deepcopy(row.content)
        raw[0]["data"] = "0x" + "00" * 128
        content["raw_evidence"]["sha256"] = raw_sha256(raw)
        # Model corrupt storage in this module-owned test DB; restore its trigger in the same transaction.
        session.execute(text("ALTER TABLE research_local.history_datasets DISABLE TRIGGER history_datasets_immutable"))
        try:
            row.raw_records, row.content, row.content_sha256 = raw, content, sha256_hex(content)
            session.flush()
        finally:
            session.execute(text("ALTER TABLE research_local.history_datasets ENABLE TRIGGER history_datasets_immutable"))
        session.commit()
    with pytest.raises(AppError) as caught:
        consumer(factory, owner, dataset)
    assert caught.value.code == "payload_binding_mismatch"
