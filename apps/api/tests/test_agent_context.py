"""P19 context controls append owner and agent scoped versions only."""

from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from edge_os_api.core.errors import AppError
from edge_os_api.records.models import Record
from conftest import run_threads

FIXTURE = Path(__file__).parent / "fixtures" / "account_views" / "agent-context-v1.json"
ACCOUNT_FIXTURE = Path(__file__).parent / "fixtures" / "account_views" / "account-records-v1.json"


def _mount_context(client):
    if not getattr(client.app.state, "p19_context_mounted", False):
        from edge_os_api.agent_context.controls import router

        client.app.include_router(router)
        client.app.state.p19_context_mounted = True


def _owner(client, headers):
    return client.get("/v1/me", headers=headers).json()["user_id"]


def _seed_context(client, headers, source_refs=(), agent_id="agent-a"):
    owner_id = _owner(client, headers)
    content = json.loads(FIXTURE.read_text(encoding="utf-8"))
    content.update(owner_id=owner_id, agent_id=agent_id)
    if agent_id != "agent-a":
        for entry in content["entries"]:
            entry["text"] = f"Private to {agent_id}: {entry['text']}"
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


def _seed_account_history(client, owner_id):
    records = json.loads(ACCOUNT_FIXTURE.read_text(encoding="utf-8"))
    records.append({"content": {
        "evidence_class": "SYNTHETIC_AUTHORED", "record_kind": "AGENT", "agent_id": "agent-a",
        "wallet_id": "wallet-a", "network_id": "monad:143", "status": "STOPPED",
        "health": "SYNTHETIC_HEALTH", "updated_at": "2026-10-09T12:05:00Z",
        "wallet_balance": {"asset_id": "monad:143/asset:MOE", "raw": "19", "decimals": 0},
        "available_balance": {"asset_id": "monad:143/asset:MOE", "raw": "18", "decimals": 0},
        "reserved_amount": {"asset_id": "monad:143/asset:MOE", "raw": "1", "decimals": 0},
        "remaining_authority": {"asset_id": "monad:143/asset:WMON", "raw": "0", "decimals": 18},
        "native_gas": {"asset_id": "monad:143/asset:MON", "raw": "50000000000000000", "decimals": 18},
        "permission_state": "REMOVED",
    }})
    with client.app.state.session_factory() as session:
        for item in records:
            session.add(Record(
                record_id=uuid.uuid4(), owner_id=uuid.UUID(owner_id), record_type="AccountViewRecord",
                schema_version="account-view/1", operation_id=uuid.uuid4(),
                created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc),
                content={**item["content"], "owner_id": owner_id},
            ))
        session.commit()


def _financial_snapshot(client, owner_id):
    with client.app.state.session_factory() as session:
        return session.execute(
            text(
                "select coalesce(jsonb_agg(to_jsonb(r) order by r.seq), '[]'::jsonb)::text "
                "from records r where r.owner_id = :owner_id and r.record_type <> 'AgentContextRecord'"
            ), {"owner_id": owner_id},
        ).scalar_one()


def _context_versions(client, owner_id, agent_id="agent-a"):
    with client.app.state.session_factory() as session:
        return session.execute(select(Record.content).where(
            Record.owner_id == uuid.UUID(owner_id),
            Record.record_type == "AgentContextRecord",
            Record.content["agent_id"].astext == agent_id,
        ).order_by(Record.seq)).scalars().all()


def test_suggestion_stays_out_of_task_context_until_owner_adopts_it(client, owner_a):
    _mount_context(client)
    expected, _ = _seed_context(client, owner_a)
    from edge_os_api.agent_context.controls import retrieve_agent_context
    from edge_os_api.core.authentication import Principal

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


def test_owner_can_manage_but_agent_scope_cannot_read_another_same_owner_agent(client, owner_a):
    _mount_context(client)
    _seed_context(client, owner_a)
    _seed_context(client, owner_a, agent_id="agent-b")
    from edge_os_api.agent_context.controls import retrieve_agent_context
    from edge_os_api.core.authentication import Principal

    principal = Principal(uuid.UUID(_owner(client, owner_a)), "test")
    managed_b = client.get("/v1/agents/agent-b/context", headers=owner_a)
    assert managed_b.status_code == 200
    assert managed_b.json()["agent_id"] == "agent-b"
    with client.app.state.session_factory() as session:
        version, entries = retrieve_agent_context(session, principal, "agent-b", "agent-b")
    assert version == 1
    assert entries[0]["text"].startswith("Private to agent-b:")
    with client.app.state.session_factory() as session, pytest.raises(AppError) as error:
        retrieve_agent_context(session, principal, "agent-a", "agent-b")
    assert error.value.code == "not_found"


def test_invalid_agent_path_is_rejected_before_context_lookup_or_write(client, owner_a):
    _mount_context(client)
    owner_id = _owner(client, owner_a)
    _seed_context(client, owner_a)
    before = _context_versions(client, owner_id)
    owner_claim = client.post("/v1/agents/agent-a/context/corrections", headers=owner_a, json={
        "expected_version": 1, "context_id": "preference-1", "replacement": "No identity claim.",
        "owner_id": owner_id, "agent_id": "agent-b",
    })
    assert owner_claim.status_code == 422
    invalid_path = "/v1/agents/" + ("x" * 201) + "/context"
    read = client.get(invalid_path, headers=owner_a)
    assert read.status_code == 422
    assert read.json()["code"] == "validation_error"
    write = client.post(invalid_path + "/corrections", headers=owner_a, json={
        "expected_version": 1, "context_id": "preference-1", "replacement": "Must not write.",
    })
    assert write.status_code == 422
    assert write.json()["code"] == "validation_error"
    assert _context_versions(client, owner_id) == before


def test_concurrent_edits_with_one_expected_version_commit_exactly_one_successor(client, owner_a):
    _mount_context(client)
    owner_id = _owner(client, owner_a)
    _seed_context(client, owner_a)
    path = "/v1/agents/agent-a/context/corrections"
    replacements = ["Concurrent correction A.", "Concurrent correction B."]
    responses = run_threads(2, lambda index: client.post(
        path, headers=owner_a,
        json={"expected_version": 1, "context_id": "preference-1", "replacement": replacements[index]},
    ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    history = _context_versions(client, owner_id)
    assert [item["memory_version"] for item in history] == [1, 2]
    winning_text = next(item for item in history[1]["entries"] if item["context_id"] == "preference-1")["text"]
    assert winning_text in replacements
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["code"] == "context_version_conflict"


@pytest.mark.parametrize(
    ("stale_path", "stale_body", "concurrent_path", "concurrent_body", "preserved_entry", "preserved_value"),
    [
        (
            "/v1/agents/agent-a/context/corrections",
            {"expected_version": 2, "context_id": "preference-1", "replacement": "Prepared from old state."},
            "/v1/agents/agent-a/context/suggestions/adopt",
            {"expected_version": 1, "context_id": "lesson-1"},
            "lesson-1",
            "ADOPTED",
        ),
        (
            "/v1/agents/agent-a/context/suggestions/adopt",
            {"expected_version": 2, "context_id": "lesson-1"},
            "/v1/agents/agent-a/context/corrections",
            {"expected_version": 1, "context_id": "preference-1", "replacement": "Concurrent correction."},
            "preference-1",
            "Concurrent correction.",
        ),
    ],
)
def test_update_from_stale_context_snapshot_cannot_overwrite_newer_version(
    client,
    owner_a,
    monkeypatch,
    stale_path,
    stale_body,
    concurrent_path,
    concurrent_body,
    preserved_entry,
    preserved_value,
):
    import edge_os_api.agent_context.controls as context_api

    _mount_context(client)
    owner_id = _owner(client, owner_a)
    _seed_context(client, owner_a)
    _seed_account_history(client, owner_id)
    financial_before = _financial_snapshot(client, owner_id)
    captured = threading.Event()
    resume = threading.Event()
    first_read_lock = threading.Lock()
    paused = False
    original_current = context_api._current

    def pause_first_snapshot(session, principal, agent_id):
        nonlocal paused
        snapshot = original_current(session, principal, agent_id)
        with first_read_lock:
            should_pause = not paused
            if should_pause:
                paused = True
        if should_pause:
            assert snapshot.memory_version == 1
            captured.set()
            assert resume.wait(timeout=10)
        return snapshot

    monkeypatch.setattr(context_api, "_current", pause_first_snapshot)
    with ThreadPoolExecutor(max_workers=1) as executor:
        stale_update = executor.submit(
            client.post, stale_path, headers=owner_a, json=stale_body
        )
        try:
            assert captured.wait(timeout=10)
            concurrent_update = client.post(concurrent_path, headers=owner_a, json=concurrent_body)
            assert concurrent_update.status_code == 200, concurrent_update.text
            assert concurrent_update.json()["memory_version"] == 2
        finally:
            resume.set()
        stale_response = stale_update.result(timeout=15)

    latest = client.get("/v1/agents/agent-a/context", headers=owner_a)
    assert stale_response.status_code == 409
    assert stale_response.json()["code"] == "context_version_conflict"
    assert latest.status_code == 200
    assert latest.json()["memory_version"] == 2
    preserved = next(entry for entry in latest.json()["entries"] if entry["context_id"] == preserved_entry)
    observed_value = preserved["status"] if preserved_entry == "lesson-1" else preserved["text"]
    assert observed_value == preserved_value
    assert [row["memory_version"] for row in _context_versions(client, owner_id)] == [1, 2]
    assert _financial_snapshot(client, owner_id) == financial_before


def test_commit_failure_rolls_back_and_lost_commit_reply_reconciles_before_retry(client, owner_a):
    import edge_os_api.agent_context.controls as context_api

    _mount_context(client)
    owner_id = _owner(client, owner_a)
    _seed_context(client, owner_a)
    path = "/v1/agents/agent-a/context/corrections"
    body = {"expected_version": 1, "context_id": "preference-1", "replacement": "Reconcile the saved version."}
    financial_before = _financial_snapshot(client, owner_id)

    def failing_before_commit():
        with client.app.state.session_factory() as session:
            def fail_commit():
                session.flush()
                raise OperationalError("COMMIT", {}, RuntimeError("synthetic pre-commit failure"))

            session.commit = fail_commit
            yield session

    client.app.dependency_overrides[context_api.get_session] = failing_before_commit
    try:
        failed = client.post(path, headers=owner_a, json=body)
    finally:
        client.app.dependency_overrides.pop(context_api.get_session, None)
    assert failed.status_code == 503
    assert failed.json()["code"] == "service_unavailable"
    assert failed.json()["retry"] == "RECONCILE"
    assert [row["memory_version"] for row in _context_versions(client, owner_id)] == [1]
    assert _financial_snapshot(client, owner_id) == financial_before

    def commit_then_drop_reply():
        with client.app.state.session_factory() as session:
            original_commit = session.commit

            def commit_and_raise():
                original_commit()
                raise OperationalError("COMMIT", {}, RuntimeError("synthetic lost commit reply"))

            session.commit = commit_and_raise
            yield session

    client.app.dependency_overrides[context_api.get_session] = commit_then_drop_reply
    try:
        ambiguous = client.post(path, headers=owner_a, json=body)
    finally:
        client.app.dependency_overrides.pop(context_api.get_session, None)
    assert ambiguous.status_code == 503
    assert ambiguous.json()["retry"] == "RECONCILE"
    stored = client.get("/v1/agents/agent-a/context", headers=owner_a)
    assert stored.status_code == 200 and stored.json()["memory_version"] == 2
    retry = client.post(path, headers=owner_a, json=body)
    assert retry.status_code == 409
    assert [row["memory_version"] for row in _context_versions(client, owner_id)] == [1, 2]
    assert _financial_snapshot(client, owner_id) == financial_before


def test_retrieval_maps_source_lookup_failure_to_reconciliation_error(client, owner_a):
    _mount_context(client)
    owner_id = _owner(client, owner_a)
    source_id = uuid.uuid4()
    with client.app.state.session_factory() as session:
        session.add(Record(
            record_id=source_id, owner_id=uuid.UUID(owner_id), record_type="AccountViewRecord",
            schema_version="account-view/1", operation_id=uuid.uuid4(),
            created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc),
            content={"owner_id": owner_id, "fixture": "synthetic source"},
        ))
        session.commit()
    _seed_context(client, owner_a, source_refs=[str(source_id)])
    from edge_os_api.agent_context.controls import retrieve_agent_context
    from edge_os_api.core.authentication import Principal

    with client.app.state.session_factory() as session:
        execute = session.execute
        calls = 0

        def fail_source_query(statement, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OperationalError("SELECT", {}, RuntimeError("synthetic read failure"))
            return execute(statement, *args, **kwargs)

        session.execute = fail_source_query
        with pytest.raises(AppError) as failure:
            retrieve_agent_context(session, Principal(uuid.UUID(owner_id), "test"), "agent-a", "agent-a")
    assert calls == 2
    assert failure.value.status == 503
    assert failure.value.code == "service_unavailable"
    assert failure.value.retry == "RECONCILE"


def test_correction_disable_clear_are_versioned_and_leave_account_records_unchanged(client, owner_a):
    _mount_context(client)
    owner_id = _owner(client, owner_a)
    _seed_context(client, owner_a)
    _seed_account_history(client, owner_id)
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
    from edge_os_api.agent_context.controls import retrieve_agent_context
    from edge_os_api.core.authentication import Principal

    with client.app.state.session_factory() as session:
        version, entries = retrieve_agent_context(session, Principal(uuid.UUID(owner_id), "test"),
                                                  "agent-a", "agent-a")
    assert version == 3 and entries == []

    cleared = client.post("/v1/agents/agent-a/context/clear", headers=owner_a,
                          json={"expected_version": 3})
    assert cleared.status_code == 200 and cleared.json()["state"] == "CLEARED"
    assert cleared.json()["entries"] == []
    with client.app.state.session_factory() as session:
        version, entries = retrieve_agent_context(session, Principal(uuid.UUID(owner_id), "test"),
                                                  "agent-a", "agent-a")
    assert version == 4 and entries == []
    assert _financial_snapshot(client, owner_id) == before
    versions = _context_versions(client, owner_id)
    assert [item["memory_version"] for item in versions] == [1, 2, 3, 4]
    assert versions[0]["entries"][0]["text"] == "Use short evidence summaries."
    assert next(item for item in versions[1]["entries"] if item["context_id"] == "preference-1")["text"] == "Show the source and time."
    assert versions[2]["state"] == "DISABLED" and versions[2]["entries"]
    assert versions[3]["state"] == "CLEARED" and versions[3]["entries"] == []


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
    assert "foreign source remains private" not in response.text
    _seed_context(client, owner_a, source_refs=[str(uuid.uuid4())], agent_id="agent-b")
    private_missing_source = client.get("/v1/agents/agent-b/context", headers=owner_a)
    assert private_missing_source.status_code == 404
    assert private_missing_source.json()["code"] == response.json()["code"]
    assert private_missing_source.json()["findings"] == response.json()["findings"]
    assert str(foreign_source_id) not in private_missing_source.text
    _seed_context(client, owner_a, source_refs=["not-a-uuid"], agent_id="agent-c")
    malformed_source = client.get("/v1/agents/agent-c/context", headers=owner_a)
    assert malformed_source.status_code == 503
    assert malformed_source.json()["retry"] == "RECONCILE"
    assert "A sample result is not a live receipt." not in malformed_source.text
    foreign_context = client.get("/v1/agents/agent-a/context", headers=owner_b)
    assert foreign_context.status_code == 200
    assert foreign_context.json()["memory_version"] == 0

    from edge_os_api.agent_context.controls import retrieve_agent_context
    from edge_os_api.core.authentication import Principal

    with client.app.state.session_factory() as session, pytest.raises(AppError) as error:
        retrieve_agent_context(session, Principal(uuid.UUID(owner_a_id), "test"), "agent-a", "agent-b")
    assert error.value.code == "not_found"
