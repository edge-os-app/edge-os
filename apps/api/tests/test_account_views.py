"""P19 account views use owner-scoped persisted records and exact P15 identities."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

from sqlalchemy import select

from edge_os_api.models import Record

FIXTURE = Path(__file__).parent / "fixtures" / "account_views" / "account-records-v1.json"


def _seed(client, headers):
    owner_id = client.get("/v1/me", headers=headers).json()["user_id"]
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc)
    with client.app.state.session_factory() as session:
        for entry in records:
            entry["record_id"] = str(uuid.uuid4())
            entry["operation_id"] = str(uuid.uuid4())
            content = {**entry["content"], "owner_id": owner_id}
            session.add(Record(
                record_id=uuid.UUID(entry["record_id"]), owner_id=uuid.UUID(owner_id),
                record_type="AccountViewRecord", schema_version="account-view/1",
                operation_id=uuid.UUID(entry["operation_id"]), created_at=now,
                content=content,
            ))
        session.commit()
    return records


def test_account_views_keep_same_asset_positions_and_sales_attributed(client, owner_a):
    from edge_os_api.account_views import router

    client.app.include_router(router)
    fixture = _seed(client, owner_a)
    response = client.get("/v1/account-views?asset_id=monad:143/asset:MOE", headers=owner_a)
    assert response.status_code == 200
    rows = response.json()["records"]
    positions = [row["content"] for row in rows if row["content"]["record_kind"] == "POSITION"]
    assert {(row["wallet_id"], row["position_id"], row["quantity"]["raw"]) for row in positions} == {
        ("wallet-a", "position-a-1", "15"),
        ("wallet-a", "position-a-2", "4"),
        ("wallet-b", "position-b-1", "9"),
    }
    wallet_a = client.get("/v1/account-views?wallet_id=wallet-a&position_id=position-a-2", headers=owner_a)
    assert {row["content"]["position_id"] for row in wallet_a.json()["records"]} == {"position-a-2"}
    revision = client.get("/v1/account-views?strategy_revision=strategy-a-v3", headers=owner_a)
    assert {row["content"].get("position_id") for row in revision.json()["records"] if row["content"]["record_kind"] == "POSITION"} == {"position-a-1"}
    actions = [row["content"] for row in rows if row["content"]["record_kind"] == "ACTION"]
    assert {(row["position_id"], row["action_id"], row["status"]) for row in actions} == {
        ("position-a-1", "action-a-sale-1", "SUBMITTED"),
        ("position-a-2", "action-a-failed-2", "REVERTED"),
    }
    first_page = client.get("/v1/account-views?limit=2", headers=owner_a).json()
    second_page = client.get(f"/v1/account-views?limit=2&offset={first_page['next_offset']}", headers=owner_a).json()
    assert len(first_page["records"]) == len(second_page["records"]) == 2
    assert first_page["next_offset"] == 2 and second_page["next_offset"] == 4
    assert fixture[4]["content"]["position_id"] == "position-a-1"


def test_foreign_and_missing_account_record_ids_have_same_not_found(client, owner_a, owner_b):
    from edge_os_api.account_views import router

    client.app.include_router(router)
    fixture = _seed(client, owner_a)
    foreign_id = fixture[0]["record_id"]
    foreign = client.get(f"/v1/account-views/{foreign_id}", headers=owner_b)
    absent = client.get(f"/v1/account-views/{uuid.uuid4()}", headers=owner_b)
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json()["code"] == absent.json()["code"] == "not_found"
    assert foreign.json()["findings"] == absent.json()["findings"]


def test_filtering_never_reads_another_owners_records(client, owner_a, owner_b):
    from edge_os_api.account_views import router

    client.app.include_router(router)
    _seed(client, owner_a)
    response = client.get("/v1/account-views?agent_id=agent-a", headers=owner_b)
    assert response.status_code == 200
    assert response.json()["records"] == []


def test_account_views_are_mounted_on_a_fresh_application(client, owner_a):
    """The production app must expose the feature without test-only include_router calls."""
    from fastapi.testclient import TestClient

    from edge_os_api.main import create_app

    with TestClient(create_app(client.app.state.settings)) as mounted_client:
        response = mounted_client.get("/v1/account-views", headers=owner_a)
    assert response.status_code == 200
    assert response.json() == {"records": [], "next_offset": None}
