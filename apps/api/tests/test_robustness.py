"""Hostile and malformed authenticated input stays inside the contract error envelope."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from edge_os_api import p02, service
from edge_os_api.auth import Principal
from edge_os_api.main import create_app
from flows import HUNCH, THESIS, compiled_thesis, publication_body, submit


def assert_envelope(response, status):
    assert response.status_code == status, response.text[:200]
    body = response.json()
    p02.validate_http_error(body)
    return body


def test_nul_character_is_a_422_everywhere_text_is_accepted(client, owner_a, pg):
    before = pg.psql("select count(*) from records")
    assert_envelope(submit(client, owner_a, "bad\u0000text"), 422)
    assert_envelope(submit(client, owner_a, THESIS, restrictions=["no\u0000leverage"]), 422)
    bundle = compiled_thesis(client, owner_a)
    body = publication_body(bundle, key="k\u0000ey")
    assert_envelope(client.post(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", json=body, headers=owner_a), 422)
    after_compile = pg.psql("select count(*) from records")
    assert int(after_compile) > int(before)  # only the valid flow saved rows


def test_nul_in_a_path_segment_never_reaches_a_500(client, owner_a):
    for path in ("/v1/strategies/%00/revisions/" + str(uuid.uuid4()), "/v1/operations/%00", "/v1/research/requests/%00"):
        response = client.get(path, headers=owner_a)
        assert response.status_code in {404, 422}, (path, response.status_code)
        p02.validate_http_error(response.json())
    response = client.post("/v1/strategies/%00/revisions", headers=owner_a, json={
        "operation_id": str(uuid.uuid4()), "idempotency_key": "x", "expected_parent_revision_id": None,
        "draft_id": str(uuid.uuid4()), "strategy": {}})
    assert response.status_code in {404, 422}


def test_deeply_nested_and_oversized_bodies_are_422(client, owner_a):
    deep = "[" * 100_000 + "]" * 100_000
    assert_envelope(client.post("/v1/research/requests", headers={**owner_a, "content-type": "application/json"}, content=deep), 422)
    def chunks():
        for _ in range(40):
            yield b" " * 10_000
    response = client.post("/v1/research/requests", headers={**owner_a, "content-type": "application/json"}, content=chunks())
    assert response.status_code == 422 and response.json()["findings"][0]["code"] == "body_too_large"


def test_a_record_id_that_is_not_an_intake_is_not_found(client, owner_a):
    bundle = compiled_thesis(client, owner_a)
    for record in (bundle["interpretations"][0], bundle["clarifications"][0], bundle["drafts"][0], bundle["outcomes"][0]["record"]):
        response = client.get(f"/v1/research/requests/{record['record_id']}", headers=owner_a)
        assert response.status_code == 404, record["record_type"]
    assert client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).status_code == 200


def test_unexpected_exceptions_return_the_contract_envelope_without_details(settings, signer, monkeypatch, caplog):
    def explode(*_a, **_k):
        raise RuntimeError("secret internals SECRETWORDS")
    monkeypatch.setattr(service, "create_request", explode)
    with TestClient(create_app(settings), raise_server_exceptions=False) as quiet:
        headers = {"Authorization": f"Bearer {signer.token('did:privy:boom-' + uuid.uuid4().hex)}"}
        response = submit(quiet, headers, HUNCH, input_class="LOOSE_INTUITION")
    body = assert_envelope(response, 500)
    assert body["code"] == "service_unavailable" and body["retry"] == "RECONCILE"
    assert "SECRETWORDS" not in response.text and "Traceback" not in response.text
    # the log names the exception class and route only: no message, no traceback
    logged = [r for r in caplog.records if r.name == "edge_os"]
    assert logged and all("RuntimeError" in r.getMessage() and r.exc_info is None for r in logged)
    assert "SECRETWORDS" not in caplog.text


def test_sql_parameters_are_hidden_from_error_text(client):
    assert client.app.state.engine.hide_parameters is True


def test_list_marks_when_more_requests_exist(client, owner_a):
    for _ in range(3):
        assert submit(client, owner_a, HUNCH, input_class="LOOSE_INTUITION").status_code == 201
    user_id = uuid.UUID(client.get("/v1/me", headers=owner_a).json()["user_id"])
    with client.app.state.session_factory() as session:
        rows, more = service.list_requests(session, Principal(user_id, "did:privy:x"), limit=2)
        assert len(rows) == 2 and more is True
        rows, more = service.list_requests(session, Principal(user_id, "did:privy:x"), limit=3)
        assert len(rows) == 3 and more is False
    assert client.get("/v1/research/requests", headers=owner_a).json()["has_more"] is False


def test_decomposed_text_gets_a_message_a_person_can_act_on(client, owner_a):
    decomposed = "Café rises seem to keep running."  # e + combining accent, not NFC
    response = submit(client, owner_a, decomposed)
    body = assert_envelope(response, 422)
    detail = body["findings"][0]["detail"].lower()
    assert "nfc" in detail and "composed" in detail


def test_a_database_outage_on_intake_tells_the_client_to_reconcile_not_to_retry_blindly(settings, signer, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def refuse(*_a, **_k):
        raise OperationalError("select", {}, Exception("connection refused"))
    monkeypatch.setattr(service, "create_request", refuse)
    with TestClient(create_app(settings)) as quiet:
        headers = {"Authorization": f"Bearer {signer.token('did:privy:outage-' + uuid.uuid4().hex)}"}
        body = assert_envelope(submit(quiet, headers, HUNCH, input_class="LOOSE_INTUITION"), 503)
    assert body["code"] == "service_unavailable" and body["retry"] == "RECONCILE"  # intake has no idempotency key


def test_pool_exhaustion_is_a_503_with_a_retry_hint_not_a_500(settings, signer, monkeypatch):
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    def exhausted(*_a, **_k):
        raise PoolTimeout("QueuePool limit reached")
    monkeypatch.setattr(service, "list_requests", exhausted)
    with TestClient(create_app(settings)) as quiet:
        headers = {"Authorization": f"Bearer {signer.token('did:privy:pool-' + uuid.uuid4().hex)}"}
        body = assert_envelope(quiet.get("/v1/research/requests", headers=headers), 503)
    assert body["code"] == "service_unavailable" and body["retry"] == "SAFE_SAME_KEY"
