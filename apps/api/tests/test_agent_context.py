"""P19 context controls append owner and agent scoped versions only."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from edge_os_api.errors import AppError
from edge_os_api.models import Record

FIXTURE = Path(__file__).parent / "fixtures" / "account_views" / "agent-context-v1.json"


def _mount_context(client):
    if not getattr(client.app.state, "p19_context_mounted", False):
        from edge_os_api.agent_context import router

        client.app.include_router(router)
        client.app.state.p19_context_mounted = True


def _owner(client, headers):
    return client.get("/v1/me", headers=headers).json()["user_id"]


def _seed_context(client, headers, source_refs=()):
    owner_id = _owner(client, headers)
    content = json.loads(FIXTURE.read_text(encoding="utf-8"))
    content.update(owner_id=owner_id)
    for entry in content["entries"]:
        entry["source_refs"] = list(source_refs) if entry["context_id"] == "lesson-1" else []
    record_id, operation_id = uuid.uuid4(), uuid.uuid4()
    with client.app.state.session_factory() as session:
        session.add(Record(
            record_id=record_id, owner_id=uuid.UUID(owner_id), record_type="AgentContextRecord",
            schema_version="agent-context/1", operation_id=operation_id,
            created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), content=content,
        ))
        session.commit()
    return content, record_id


def _financial_snapshot(client, owner_id):
    with client.app.state.session_factory() as session:
        rows = session.execute(select(Record.record_id, Record.content).where(
            Record.owner_id == uuid.UUID(owner_id), Record.record_type == "AccountViewRecord",
        ).order_by(Record.seq)).all()
    return [(str(record_id), content) for record_id, content in rows]


def test_suggestion_stays_out_of_task_context_until_owner_adopts_it(client, owner_a):
    _mount_context(client)
    expected, _ = _seed_context(client, owner_a)
    from edge_os_api.agent_context import retrieve_agent_context
    from edge_os_api.auth import Principal

    owner_id = uuid.UUID(_owner(client, owner_a))
    with client.app.state.session_factory() as session:
        version, entries = retrieve_agent_context(session, Principal(owner_id, "test"), "agent-a", "agent-a")
    assert version == 1
    assert entries == [{"context_id": "preference-1", "text": "Use short evidence summaries."}]
    assert expected["entries"][1]["status"] == "SUGGESTED"

    response = client.post("/v1/agents/agent-a/context/suggestions/adopt", headers=owner_a,
                           json={"expected_version": 1, "context_id": "lesson-1"})
    assert response.status_code == 200
    assert response.json()["memory_version"] == 2
    with client.app.state.session_factory() as session:
        version, entries = retrieve_agent_context(session, Principal(owner_id, "test"), "agent-a", "agent-a")
    assert version == 2
    assert {entry["context_id"] for entry in entries} == {"preference-1", "lesson-1"}


def test_correction_disable_clear_are_versioned_and_leave_account_records_unchanged(client, owner_a):
    _mount_context(client)
    owner_id = _owner(client, owner_a)
    _seed_context(client, owner_a)
    with client.app.state.session_factory() as session:
        session.add(Record(
            record_id=uuid.uuid4(), owner_id=uuid.UUID(owner_id), record_type="AccountViewRecord",
            schema_version="account-view/1", operation_id=uuid.uuid4(),
            created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc),
            content={
                "owner_id": owner_id, "record_kind": "AGENT", "agent_id": "agent-a",
                "wallet_id": "wallet-a", "network_id": "monad:143", "status": "STOPPED",
                "health": "SYNTHETIC_HEALTH", "updated_at": "2026-10-09T12:00:00Z",
                "wallet_balance": {"asset_id": "monad:143/asset:MOE", "raw": "12", "decimals": 0},
                "available_balance": {"asset_id": "monad:143/asset:MOE", "raw": "10", "decimals": 0},
                "reserved_amount": {"asset_id": "monad:143/asset:MOE", "raw": "2", "decimals": 0},
                "remaining_authority": {"asset_id": "monad:143/asset:WMON", "raw": "0", "decimals": 18},
                "native_gas": {"asset_id": "monad:143/asset:MON", "raw": "3", "decimals": 18},
                "permission_state": "REMOVED", "evidence_class": "SYNTHETIC_AUTHORED",
            },
        ))
        session.commit()
    before = _financial_snapshot(client, owner_id)

    corrected = client.post("/v1/agents/agent-a/context/corrections", headers=owner_a,
                            json={"expected_version": 1, "context_id": "preference-1",
                                  "replacement": "Show the source and time."})
    assert corrected.status_code == 200
    assert corrected.json()["memory_version"] == 2
    assert next(item for item in corrected.json()["entries"] if item["context_id"] == "preference-1")["text"] == "Show the source and time."

    stale = client.post("/v1/agents/agent-a/context/disable", headers=owner_a,
                        json={"expected_version": 1})
    assert stale.status_code == 409
    disabled = client.post("/v1/agents/agent-a/context/disable", headers=owner_a,
                           json={"expected_version": 2})
    assert disabled.status_code == 200 and disabled.json()["state"] == "DISABLED"
    from edge_os_api.agent_context import retrieve_agent_context
    from edge_os_api.auth import Principal

    with client.app.state.session_factory() as session:
        version, entries = retrieve_agent_context(session, Principal(uuid.UUID(owner_id), "test"),
                                                  "agent-a", "agent-a")
    assert version == 3 and entries == []

    cleared = client.post("/v1/agents/agent-a/context/clear", headers=owner_a,
                          json={"expected_version": 3})
    assert cleared.status_code == 200 and cleared.json()["state"] == "CLEARED"
    assert cleared.json()["entries"] == []
    assert _financial_snapshot(client, owner_id) == before


def test_cross_agent_task_scope_and_foreign_source_links_are_denied(client, owner_a, owner_b):
    _mount_context(client)
    owner_a_id = _owner(client, owner_a)
    owner_b_id = _owner(client, owner_b)
    foreign_source_id = uuid.uuid4()
    with client.app.state.session_factory() as session:
        session.add(Record(
            record_id=foreign_source_id, owner_id=uuid.UUID(owner_b_id), record_type="AccountViewRecord",
            schema_version="account-view/1", operation_id=uuid.uuid4(),
            created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc),
            content={"test": "foreign source remains private"},
        ))
        session.commit()
    _seed_context(client, owner_a, source_refs=[str(foreign_source_id)])

    response = client.get("/v1/agents/agent-a/context", headers=owner_a)
    assert response.status_code == 404 and response.json()["code"] == "not_found"
    foreign_context = client.get("/v1/agents/agent-a/context", headers=owner_b)
    assert foreign_context.status_code == 200
    assert foreign_context.json()["memory_version"] == 0

    from edge_os_api.agent_context import retrieve_agent_context
    from edge_os_api.auth import Principal

    with client.app.state.session_factory() as session, pytest.raises(AppError) as error:
        retrieve_agent_context(session, Principal(uuid.UUID(owner_a_id), "test"), "agent-a", "agent-b")
    assert error.value.code == "not_found"
