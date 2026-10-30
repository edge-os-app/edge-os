"""Mounted controlled clients select the direct quote source without a Kuru credential.

The database and HTTP boundary are in-memory fakes. No network, signer, credential or send is used.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from types import SimpleNamespace

import pytest

from edge_os_api.core.provider_ports import ControlledRuntime
from edge_os_api.execution.direct_route_quote_client import DirectRoutePins, build_calldata_hex
from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
from edge_os_api.execution.original_transaction import Leg, OriginalContext
from edge_os_api.execution.transport import PreparedSubmission
from edge_os_api.kuru_flow import ApprovedAdapterConfiguration, PreparationOutcome, ResponseProvenance
from edge_os_api.kuru_flow.transaction_preparation import prepare_unsigned_transaction

from execution.test_direct_route_quote_client import (
    AMOUNT,
    INPUT,
    MINIMUM,
    OUTPUT,
    POOL,
    USER,
    Http,
    direct_definition,
    request,
    reserves_reply,
)

NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
OWNER = "11111111-1111-4111-8111-111111111111"
ATTEMPT = "22222222-2222-4222-8222-222222222222"
WALLET = "0x" + "1" * 40
WALLET_ID = "synthetic-wallet-a"
SAVED = {
    "strategy_id": "strategy-a", "publication_revision_id": "publication-a",
    "execution_revision_id": "execution-a", "market_binding_id": "market-a",
    "content_sha256": "1" * 64, "manifest_sha256": "2" * 64, "consent_adoption_id": "consent-a",
    "consent_hash": "sha256:" + "3" * 64, "review_hash": "sha256:" + "4" * 64,
    "terms_hash": "sha256:" + "5" * 64,
}


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, results):
        self.results = results

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        return Result(self.results.pop(0))


class Factory:
    def __init__(self):
        self.results = []

    def seed(self, release, prepared):
        attempt = SimpleNamespace(owner_id=uuid.UUID(OWNER), attempt_id=uuid.UUID(prepared.attempt_id),
            state="IN_FLIGHT", transport_id="original-transaction/1", agent_id="agent-a",
            action_id="action-a", wallet_id=WALLET_ID, network_id="monad:143",
            payload_hash="sha256:payload", queue_id=uuid.uuid4(), content={"original_transaction": {}})
        claim = SimpleNamespace(owner_id=uuid.UUID(OWNER), queue_id=uuid.uuid4(), action_id="action-a",
            agent_id="agent-a", wallet_id=WALLET_ID, network_id="monad:143", state="ACTIVE", released_at=None)
        admission = SimpleNamespace(owner_id=uuid.UUID(OWNER), action_id="action-a", agent_id="agent-a",
            wallet_id=WALLET_ID, network_id="monad:143", status="SUBMISSION_UNKNOWN")
        self.results = [attempt, claim, admission, None, attempt, claim, admission]

    def __call__(self):
        return Session(self.results)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


def test_mounted_direct_source_reads_reserves_once_and_prepares_the_release_calldata():
    release = OperatingRelease(direct_definition())
    content = release.content()
    identity = {"owner_id": OWNER, "agent_id": "agent-a", "wallet_id": WALLET_ID, "wallet_address": WALLET,
                "network_id": "monad:143", **SAVED}
    binding = BoundRelease(release, identity, position_inventory_proof_sha256="6" * 64,
                           market_proof_sha256="7" * 64, finality_proof_sha256="8" * 64)
    http = Http(reserves_reply(10**18, 10**18))
    runtime = ControlledRuntime(binding=binding, http=http, quote_token=None, signer_access=lambda: {},
                                clock=lambda: NOW, monotonic=lambda: 10.0,
                                synthetic_bindings={binding.sha256: release_sha256(release)})
    prepared = PreparedSubmission(action_id="action-a", owner_id=OWNER, wallet_id=WALLET_ID,
        network_id="monad:143", operation="ENTRY", payload_hash="sha256:payload", attempt_id=ATTEMPT)
    factory = Factory()
    factory.seed(release, prepared)
    context = OriginalContext(owner_id=OWNER, agent_id="agent-a", wallet_id=WALLET_ID, wallet_address=WALLET,
        network_id="monad:143", chain_id=143, identity=dict(SAVED), action_id="action-a",
        payload_hash="sha256:payload", operation="ENTRY",
        sell=Leg(asset_id=f"monad:143/{INPUT}", token=INPUT, decimals=6, raw=AMOUNT),
        buy=Leg(asset_id=f"monad:143/{OUTPUT}", token=OUTPUT, decimals=18, raw=1000),
        gas_asset_id="monad:143/native", gas_cap_raw=10**18, allowance_raw=AMOUNT,
        decision_slot=NOW - dt.timedelta(minutes=1), intent_expires_at=NOW + dt.timedelta(minutes=5),
        mandate_expires_at=(NOW + dt.timedelta(hours=1)).isoformat())

    clients = runtime.clients(factory, context, lambda: [], role="worker")
    clients.begin_attempt(prepared)
    reply = clients.route.quote(request())

    assert len(http.calls) == 1
    assert http.calls[0]["url"] == content["quote"]["endpoint"]
    assert "authorization" not in http.calls[0]["headers"]
    assert json.loads(http.calls[0]["body"])["params"][0]["to"] == POOL
    assert reply["transaction"]["to"] == content["route"]["entrypoint_address"]
    assert reply["minOut"] == str(MINIMUM)

    config = ApprovedAdapterConfiguration.model_validate(content["route"])
    result = prepare_unsigned_transaction(quote_response=reply, provenance=ResponseProvenance.AUTHORED,
        config=config, now=NOW.isoformat(), quote_age_seconds=0, input_age_seconds=0)
    assert result.outcome is PreparationOutcome.ACCEPTED, result.reasons
    assert result.candidate is not None
    assert result.candidate.data_hex == build_calldata_hex(DirectRoutePins.from_release(content))
    assert result.candidate.intent.min_amount_user_buys == str(MINIMUM)
    assert result.candidate.intent.amount_user_sells == str(AMOUNT)
    assert result.candidate.program_hex == content["route"]["approved_program_hex"]
