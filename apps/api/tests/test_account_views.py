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
                record_type="AccountViewRecord", schema_version=entry.get("schema_version", "account-view/1"),
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
    exact_position = client.get(
        "/v1/account-views?record_kind=POSITION&agent_id=agent-a&wallet_id=wallet-a&network_id=monad%3A143"
        "&asset_id=monad%3A143%2Fasset%3AMOE&position_id=position-a-1&strategy_revision=strategy-a-v3",
        headers=owner_a,
    )
    assert exact_position.status_code == 200
    assert {row["content"]["record_kind"] for row in exact_position.json()["records"]} == {"POSITION"}
    assert {row["content"]["position_id"] for row in exact_position.json()["records"]} == {"position-a-1"}
    exact_flow = client.get(
        "/v1/account-views?record_kind=CAPITAL_FLOW&agent_id=agent-a&wallet_id=wallet-a"
        "&network_id=monad%3A143&flow_id=flow-a-deposit-1", headers=owner_a,
    )
    assert exact_flow.status_code == 200
    assert {row["content"]["flow_id"] for row in exact_flow.json()["records"]} == {"flow-a-deposit-1"}
    revision = client.get("/v1/account-views?strategy_revision=strategy-a-v3", headers=owner_a)
    assert {row["content"].get("position_id") for row in revision.json()["records"] if row["content"]["record_kind"] == "POSITION"} == {"position-a-1"}
    actions = [row["content"] for row in rows if row["content"]["record_kind"] == "ACTION"]
    assert {(row["position_id"], row["action_id"], row["status"]) for row in actions} == {
        ("position-a-1", "action-a-sale-1", "SUBMITTED"),
        ("position-a-2", "action-a-failed-2", "REVERTED"),
        ("position-a-2", "action-a-position-confirmed-2", "CONFIRMED"),
        ("position-a-2", "action-a-position-unknown-2", "SUBMISSION_UNKNOWN"),
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


def test_context_source_resolves_a_public_research_request_without_cross_owner_lookup(client, owner_a, owner_b):
    from edge_os_api.models import Record

    from flows import HUNCH, submit

    fixture = _seed(client, owner_a)
    intake = submit(client, owner_a, HUNCH, input_class="LOOSE_INTUITION").json()["intake"]
    source_id = intake["record_id"]

    resolved = client.get(f"/v1/account-views/source/{source_id}", headers=owner_a)
    assert resolved.status_code == 200
    assert resolved.json() == {
        "source_record_id": source_id,
        "source_record_type": "IntakeRequest",
        "destination_type": "RESEARCH",
        "destination_record_id": source_id,
    }
    assert client.get(f"/v1/research/requests/{source_id}", headers=owner_a).status_code == 200
    wallet_action = next(row for row in fixture if row["content"].get("record_kind") == "ACTION"
                         and row["content"].get("flow_id") == "flow-a-withdrawal-1")
    action_resolution = client.get(f"/v1/account-views/source/{wallet_action['record_id']}", headers=owner_a)
    assert action_resolution.status_code == 200
    assert action_resolution.json()["destination_type"] == "ACCOUNT"
    assert action_resolution.json()["destination_record_id"] == wallet_action["record_id"]
    assert action_resolution.json()["record_kind"] == "ACTION"

    foreign = client.get(f"/v1/account-views/source/{source_id}", headers=owner_b)
    malformed = client.get("/v1/account-views/source/not-a-uuid", headers=owner_a)
    assert foreign.status_code == malformed.status_code == 404
    assert foreign.json()["code"] == malformed.json()["code"] == "not_found"

    opaque_id = uuid.uuid4()
    owner_id = client.get("/v1/me", headers=owner_a).json()["user_id"]
    with client.app.state.session_factory() as session:
        session.add(Record(record_id=opaque_id, owner_id=uuid.UUID(owner_id), record_type="OpaquePrivateRecord",
                           schema_version="opaque/1", operation_id=uuid.uuid4(),
                           created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), content={"private": "not returned"}))
        session.commit()
    unsupported = client.get(f"/v1/account-views/source/{opaque_id}", headers=owner_a)
    assert unsupported.status_code == 200
    assert unsupported.json() == {"source_record_id": str(opaque_id), "source_record_type": "OpaquePrivateRecord",
                                  "destination_type": "UNSUPPORTED", "destination_record_id": None}


def test_signed_position_results_preserve_negative_zero_unknown_and_raw_precision(client, owner_a):
    from edge_os_api.account_views import SCHEMA_VERSION

    owner_id = client.get("/v1/me", headers=owner_a).json()["user_id"]
    source = next(row["content"] for row in json.loads(FIXTURE.read_text(encoding="utf-8"))
                  if row["content"]["record_kind"] == "POSITION")
    cases = [
        ("-2000000", 6, "KNOWN", "1000000000000000001", 18),
        ("0", 8, "KNOWN", "-1", 18),
        (None, None, "UNKNOWN", None, None),
    ]
    record_ids = []
    with client.app.state.session_factory() as session:
        for index, (realized_raw, realized_decimals, estimate_state, estimate_raw, estimate_decimals) in enumerate(cases):
            content = {**source, "owner_id": owner_id, "realized": None, "unrealized": None,
                       "realized_result": {"state": "UNKNOWN"} if realized_raw is None else {
                           "state": "KNOWN", "amount": {"asset_id": "quote:USD", "raw": realized_raw,
                                                            "decimals": realized_decimals}},
                       "estimated_unrealized_result": {"state": "UNKNOWN"} if estimate_state == "UNKNOWN" else {
                           "state": estimate_state, "amount": {"asset_id": "quote:USD", "raw": estimate_raw,
                                                                "decimals": estimate_decimals}}}
            record_id = uuid.uuid4()
            record_ids.append(str(record_id))
            session.add(Record(record_id=record_id, owner_id=uuid.UUID(owner_id), record_type="AccountViewRecord",
                               schema_version=SCHEMA_VERSION, operation_id=uuid.uuid4(),
                               created_at=dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc), content=content))
        session.commit()

    rows = [client.get(f"/v1/account-views/{record_id}", headers=owner_a) for record_id in record_ids]
    assert [row.status_code for row in rows] == [200, 200, 200]
    first = rows[0].json()["content"]
    assert first["realized_result"]["amount"] == {"asset_id": "quote:USD", "raw": "-2000000", "decimals": 6}
    assert first["estimated_unrealized_result"]["amount"]["raw"] == "1000000000000000001"
    zero = rows[1].json()["content"]
    assert zero["realized_result"]["amount"]["raw"] == "0"
    assert zero["estimated_unrealized_result"]["amount"]["raw"] == "-1"
    unknown = rows[2].json()["content"]
    assert unknown["realized_result"] == unknown["estimated_unrealized_result"] == {"state": "UNKNOWN", "amount": None}


def test_owner_can_read_current_earlier_changed_and_never_active_permission_snapshots(client, owner_a, owner_b):
    _seed(client, owner_a)
    response = client.get("/v1/account-views?record_kind=PERMISSION_SNAPSHOT", headers=owner_a)
    assert response.status_code == 200
    records = response.json()["records"]
    snapshots = [row["content"] for row in records]
    assert {row["status"] for row in snapshots} >= {"CURRENT", "EARLIER", "CHANGE_APPLIED", "FAILED", "CANCELLED"}
    failed_record = next(row for row in records if row["content"]["status"] == "FAILED")
    failed = failed_record["content"]
    assert failed["activation_state"] == "NEVER_ACTIVE"
    assert failed["approval_id"] and failed["predecessor_approval_id"]
    assert failed["terms"]["actions"] and failed["terms"]["limits"]
    assert failed["checked_at"] and failed["failed_at"] and failed["terms_hash"]
    foreign = client.get(f"/v1/account-views/{failed_record['record_id']}", headers=owner_b)
    assert foreign.status_code == 404 and foreign.json()["code"] == "not_found"


def test_truthful_permission_lifecycle_states_are_readable_without_invented_history(client, owner_a):
    from edge_os_api.account_views import SCHEMA_VERSION

    fixture = _seed(client, owner_a)
    source = next(row["content"] for row in fixture
                  if row["content"]["record_kind"] == "PERMISSION_SNAPSHOT"
                  and row["content"]["status"] == "FAILED")
    owner_id = client.get("/v1/me", headers=owner_a).json()["user_id"]
    cases = [
        ("pending-change", {
            "status": "CHANGE_PENDING", "activation_state": "NEVER_ACTIVE",
            "approval_id": "approval-a-change-pending", "predecessor_approval_id": "approval-a-v4",
            "requested_at": "2026-10-09T13:00:00Z", "approved_at": "2026-10-09T13:01:00Z",
            "checked_at": None, "applied_at": None, "failed_at": None, "cancelled_at": None,
            "updated_at": "2026-10-09T13:01:00Z",
        }),
        ("cancelled-change-before-check", {
            "status": "CANCELLED", "activation_state": "NEVER_ACTIVE",
            "approval_id": "approval-a-change-cancelled", "predecessor_approval_id": "approval-a-v4",
            "requested_at": "2026-10-09T14:00:00Z", "approved_at": "2026-10-09T14:01:00Z",
            "checked_at": None, "applied_at": None, "failed_at": None,
            "cancelled_at": "2026-10-09T14:02:00Z", "updated_at": "2026-10-09T14:02:00Z",
        }),
        ("failed-initial-approval", {
            "status": "FAILED", "activation_state": "NEVER_ACTIVE",
            "approval_id": "approval-a-initial-failed", "predecessor_approval_id": None,
            "requested_at": "2026-10-09T15:00:00Z", "approved_at": "2026-10-09T15:01:00Z",
            "checked_at": "2026-10-09T15:02:00Z", "applied_at": None,
            "failed_at": "2026-10-09T15:03:00Z", "cancelled_at": None,
            "updated_at": "2026-10-09T15:03:00Z",
        }),
        ("cancelled-initial-attempt", {
            "status": "CANCELLED", "activation_state": "NEVER_ACTIVE",
            "approval_id": "approval-a-initial-cancelled", "predecessor_approval_id": None,
            "requested_at": "2026-10-09T16:00:00Z", "approved_at": None,
            "checked_at": None, "applied_at": None, "failed_at": None,
            "cancelled_at": "2026-10-09T16:01:00Z", "updated_at": "2026-10-09T16:01:00Z",
        }),
    ]
    record_ids: dict[str, str] = {}
    with client.app.state.session_factory() as session:
        for index, (case_name, updates) in enumerate(cases, start=1):
            record_id = uuid.uuid4()
            record_ids[case_name] = str(record_id)
            content = {**source, **updates, "owner_id": owner_id}
            session.add(Record(
                record_id=record_id, owner_id=uuid.UUID(owner_id), record_type="AccountViewRecord",
                schema_version=SCHEMA_VERSION, operation_id=uuid.uuid4(),
                created_at=dt.datetime(2026, 10, 9, 17, index, tzinfo=dt.timezone.utc), content=content,
            ))
        session.commit()

    for case_name, record_id in record_ids.items():
        exact = client.get(f"/v1/account-views/{record_id}", headers=owner_a)
        assert exact.status_code == 200, case_name
        exact_content = exact.json()["content"]
        expected = next(updates for name, updates in cases if name == case_name)
        assert exact_content["approval_id"] == expected["approval_id"]
        assert exact_content["predecessor_approval_id"] == expected["predecessor_approval_id"]
        assert exact_content["checked_at"] == expected["checked_at"]
        assert exact_content["applied_at"] is None
        assert exact_content["terms_hash"] == source["terms_hash"]
        assert exact_content["terms"] == source["terms"]
        source_read = client.get(f"/v1/account-views/source/{record_id}", headers=owner_a)
        assert source_read.status_code == 200, case_name
        assert source_read.json()["destination_record_id"] == record_id

    listed = client.get("/v1/account-views?record_kind=PERMISSION_SNAPSHOT", headers=owner_a)
    assert listed.status_code == 200
    listed_ids = {record["record_id"] for record in listed.json()["records"]}
    assert set(record_ids.values()) <= listed_ids


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
