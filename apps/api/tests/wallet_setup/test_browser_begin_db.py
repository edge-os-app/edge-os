"""Browser-begin permission and owner-bound lookup completion over the real application and run-labelled PostgreSQL.

Characterisation of source2 behaviour (candidate ffd4cfd), not a retroactive RED: the behaviour already exists.
The application is built by the ordinary `create_app(load_settings(...))` with `EDGE_OS_WALLET_LOOKUP_SOCKET`, so the
router's own `get_provider` selects the owner-bound lookup; no `app.state` provider is swapped. The lookup socket is
served by the real `lookup_server.handle` with authored in-memory user and wallet records: no credential, no network,
no Privy call. Each owner gets a fresh DID so records never leak between tests.
"""

from __future__ import annotations

import shutil
import socket
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import helpers

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app

sys.path.insert(0, str(helpers.API_DIR.parents[1] / "scripts" / "privy_wallet_lookup"))
import lookup_server  # noqa: E402

NETWORK = 10143
ADDRESS = "0x" + "ab" * 20


def _at_once(count: int, target) -> list:
    """Start `count` calls together behind one barrier (the root suite's `run_threads` shape)."""
    barrier, results = threading.Barrier(count), [None] * count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = target(index)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


class AuthoredPrivyRecords:
    """In-memory stand-in for the two fixed reads. Counts every read so tests see what the process asked."""

    def __init__(self) -> None:
        self.users: dict[str, object] = {}
        self.wallets: dict[str, object] = {}
        self.available = True
        self.reads: list[tuple[str, str]] = []

    def link(self, did: str, address: str = ADDRESS, linked_id: str | None = None) -> None:
        self.users[did] = {"id": did, "linked_accounts": [
            {"type": "wallet", "wallet_client_type": "privy", "chain_type": "ethereum", "address": address,
             "id": linked_id, "wallet_index": 1}]}

    def fetch_user(self, did: str) -> object:
        self.reads.append(("user", did))
        return self.users.get(did) if self.available else None

    def fetch_wallet(self, address: str) -> object:
        self.reads.append(("wallet", address))
        return self.wallets.get(address) if self.available else None


@pytest.fixture
def records() -> AuthoredPrivyRecords:
    return AuthoredPrivyRecords()


@pytest.fixture
def lookup_socket(records):
    """The real private-socket handler on a short owned 0700 directory, stopped and removed after the test."""
    directory = Path(tempfile.mkdtemp(prefix="l3w"))
    directory.chmod(0o700)
    path = lookup_server.prepare_socket_path(str(directory / "lookup.sock"))
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    path.chmod(0o600)
    server.listen(8)
    server.settimeout(0.2)
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            with conn:
                lookup_server.handle(conn, records.fetch_user, records.fetch_wallet)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    try:
        yield str(path)
    finally:
        stop.set()
        thread.join(timeout=5)
        server.close()
        shutil.rmtree(directory)
        assert not thread.is_alive()


@pytest.fixture
def lookup_settings(env, migrated, lookup_socket):
    return load_settings({**env, "EDGE_OS_WALLET_LOOKUP_SOCKET": lookup_socket})


@pytest.fixture
def lookup_client(lookup_settings, wallet_schema):
    with TestClient(create_app(lookup_settings)) as client:
        yield client


def _owner(signer) -> tuple[str, dict[str, str]]:
    did = f"did:privy:l3w-{uuid.uuid4().hex[:10]}"
    return did, {"Authorization": f"Bearer {signer.token(did)}"}


def _prepare(client, headers, agent_id: str) -> None:
    strategy_id, revision_id = helpers.publish_revision(client, headers)
    response = client.post(f"/v1/wallet-setup/agents/{agent_id}/prepare", headers=headers, json={
        "network_id": NETWORK, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
        "request_key": f"key-{agent_id}"})
    assert response.status_code == 200, response.text


def _begin(client, headers, agent_id: str) -> dict:
    response = client.post(f"/v1/wallet-setup/agents/{agent_id}/browser-begin", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _complete(client, headers, agent_id: str, **claim) -> dict:
    response = client.post(f"/v1/wallet-setup/agents/{agent_id}/complete", headers=headers, json=claim)
    assert response.status_code == 200, response.text
    return response.json()


def test_ordinary_factory_selects_the_owner_bound_lookup(lookup_client, signer):
    _, headers = _owner(signer)
    assert lookup_client.get("/v1/wallet-setup/provider", headers=headers).json() == {
        "provider": "privy_lookup", "create_calls": None, "lookup_calls": None}


def test_concurrent_begins_permit_exactly_one_creation(lookup_client, signer, pg):
    _, headers = _owner(signer)
    _prepare(lookup_client, headers, "begin-race")
    results = _at_once(8, lambda i: _begin(lookup_client, headers, "begin-race")["create_permitted"])
    assert sorted(results) == [False] * 7 + [True]
    intents = pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'")
    assert intents == "1"


def test_cancel_before_begin_gives_zero_permission(lookup_client, signer):
    _, headers = _owner(signer)
    _prepare(lookup_client, headers, "begin-cancel")
    cancelled = lookup_client.post("/v1/wallet-setup/agents/begin-cancel/cancel", headers=headers).json()
    assert (cancelled["state"], cancelled["creation_dispatched"]) == ("FAILED", False)
    begun = _begin(lookup_client, headers, "begin-cancel")
    assert begun["create_permitted"] is False and begun["creation_dispatched"] is False


def test_address_only_claim_binds_the_independently_resolved_id(lookup_client, signer, records):
    did, headers = _owner(signer)
    records.link(did, linked_id=None)
    records.wallets[ADDRESS] = {"id": "resolved-wallet-1", "address": ADDRESS, "chain_type": "ethereum",
                                "owner_id": "key-quorum-x"}
    _prepare(lookup_client, headers, "addr-only")
    assert _begin(lookup_client, headers, "addr-only")["create_permitted"] is True
    bound = _complete(lookup_client, headers, "addr-only", wallet_id=None, address=ADDRESS, wallet_index=1)
    assert (bound["state"], bound["wallet_id"]) == ("CONFIRMED", "resolved-wallet-1")
    assert records.reads == [("user", did), ("wallet", ADDRESS)]


def test_another_owner_cannot_bind_a_wallet_linked_to_someone_else(lookup_client, signer, records):
    did_a, _ = _owner(signer)
    _, headers_b = _owner(signer)
    records.link(did_a, linked_id="wallet-of-a")
    _prepare(lookup_client, headers_b, "foreign")
    _begin(lookup_client, headers_b, "foreign")
    result = _complete(lookup_client, headers_b, "foreign", wallet_id="wallet-of-a", address=ADDRESS)
    assert (result["state"], result["wallet_id"]) == ("UNKNOWN", None)


def test_late_completion_never_replaces_a_confirmed_binding(lookup_client, signer, records, pg):
    did, headers = _owner(signer)
    records.link(did, linked_id="first-wallet")
    _prepare(lookup_client, headers, "late")
    _begin(lookup_client, headers, "late")
    assert _complete(lookup_client, headers, "late", wallet_id="first-wallet", address=ADDRESS)["state"] == "CONFIRMED"
    late = _complete(lookup_client, headers, "late", wallet_id=None, address="0x" + "cd" * 20)
    assert (late["state"], late["wallet_id"]) == ("CONFIRMED", "first-wallet")
    assert "CONFLICTING_RESULT" in pg.psql("select string_agg(code, ',') from wallet_setup_denials")


def test_address_only_retry_after_binding_is_idempotent_and_records_no_denial(lookup_client, signer, records, pg):
    """A F1 / B MINOR-1: the lost-completion retry of the same address-only claim leaves no false conflict."""
    did, headers = _owner(signer)
    records.link(did, linked_id=None)
    records.wallets[ADDRESS] = {"id": "resolved-wallet-2", "address": ADDRESS, "chain_type": "ethereum"}
    _prepare(lookup_client, headers, "retry")
    _begin(lookup_client, headers, "retry")
    first = _complete(lookup_client, headers, "retry", wallet_id=None, address=ADDRESS, chain_type="ethereum")
    again = _complete(lookup_client, headers, "retry", wallet_id=None, address=ADDRESS, chain_type="ethereum")
    assert (first["wallet_id"], again["wallet_id"]) == ("resolved-wallet-2", "resolved-wallet-2")
    assert pg.psql("select count(*) from wallet_setup_denials") == "0"


def test_retained_claim_resumes_in_a_new_application_without_browser_storage(lookup_settings, wallet_schema,
                                                                            signer, records):
    did, headers = _owner(signer)
    records.link(did, linked_id="wallet-after-restart")
    records.available = False  # the lookup cannot answer when the browser first completes
    with TestClient(create_app(lookup_settings)) as first:
        _prepare(first, headers, "restart")
        _begin(first, headers, "restart")
        pending = _complete(first, headers, "restart", wallet_id=None, address=ADDRESS)
        assert (pending["state"], pending["wallet_id"]) == ("UNKNOWN", None)
    records.available = True
    with TestClient(create_app(lookup_settings)) as restarted:  # a new process image of the same configuration
        resumed = restarted.post("/v1/wallet-setup/agents/restart/resume", headers=headers).json()
        assert (resumed["state"], resumed["wallet_id"]) == ("CONFIRMED", "wallet-after-restart")
        again = _begin(restarted, headers, "restart")
        assert again["create_permitted"] is False


def test_lost_sdk_reply_without_claim_stays_unknown_and_never_permits_again(lookup_client, signer, records):
    _, headers = _owner(signer)
    _prepare(lookup_client, headers, "lost-sdk")
    assert _begin(lookup_client, headers, "lost-sdk")["create_permitted"] is True
    resumed = lookup_client.post("/v1/wallet-setup/agents/lost-sdk/resume", headers=headers).json()
    assert (resumed["state"], resumed["reason"]) == ("UNKNOWN", "RECONCILE_NO_EXACT_ID")
    assert _begin(lookup_client, headers, "lost-sdk")["create_permitted"] is False
    assert records.reads == []
